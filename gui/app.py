"""
app.py
------
Main PySide6 Native Desktop Application Window:
- Tab 1: Full-view Multi-Line Relative Strength Chart & Interactive Watchlist/Filters.
- Tab 2: Full-screen Live Heatmap Matrix (Market Cap Weighted Treemap vs Equal Weighted).
- Zero-restart dynamic stock management (add/remove tokens in real-time).
- Accurate double-digit signed percentage calculations (+X.XX% / -X.XX%).
- Cross-linked navigation: clicking a heatmap tile highlights its line and switches views.
"""

from datetime import datetime, timedelta
import sys
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from basket_manager import BasketManager
from config import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PANEL_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    DAYS_TO_KEEP,
    DEFAULT_SHOW_MULTIDAY,
    MARKET_CLOSE_TIME,
    MARKET_OPEN_TIME,
    UI_POLL_INTERVAL_MS,
)
from db_manager import DatabaseManager
from gui.filter_panel import FilterPanel
from gui.heatmap_widget import HeatmapWidget
from gui.multi_line_chart import RelativeStrengthChart
from gui.token_manager_dialog import TokenManagerDialog
try:
    from core.logger import get_logger
except ImportError:
    from utils.logger import get_logger

logger = get_logger("relative_strength.gui")


class RelativeStrengthDashboard(QtWidgets.QMainWindow):
    """Primary application window connecting chart, heatmap, and MySQL database."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        super().__init__()
        self.db = db or DatabaseManager()
        self.basket_mgr = BasketManager(db=self.db)

        self.last_poll_time: datetime = datetime.now() - timedelta(minutes=10)
        self.active_basket: Dict[str, Dict[str, Any]] = {}

        self.setWindowTitle("Angel One - Live Relative Strength & Heatmap Visualizer (PySide6 / PyQtGraph)")
        self.resize(1550, 920)
        self.setMinimumSize(1100, 700)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLOR_BG_DARK};
            }}
            QSplitter::handle {{
                background-color: {COLOR_BORDER};
            }}
        """)

        self._init_ui()
        self._bootstrap_data()

        # Live poll timer (every 500ms)
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.timeout.connect(self._poll_live_updates)
        self.poll_timer.start(UI_POLL_INTERVAL_MS)

    def _init_ui(self) -> None:
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(8)

        # 1. TOP HEADER & CONTROL BAR
        header_bar = QtWidgets.QHBoxLayout()
        header_bar.setSpacing(12)

        # App Title & Pulse
        title_box = QtWidgets.QHBoxLayout()
        pulse = QtWidgets.QLabel("●")
        pulse.setStyleSheet("color: #10B981; font-size: 14px; margin-right: 4px;")
        title_box.addWidget(pulse)

        title_lbl = QtWidgets.QLabel("ANGEL ONE LIVE RELATIVE STRENGTH & HEATMAP")
        title_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 13px; letter-spacing: 0.5px;")
        title_box.addWidget(title_lbl)
        header_bar.addLayout(title_box)

        # Market Timing & Live Clock
        self.lbl_clock = QtWidgets.QLabel("TIME: --:--:-- | MARKET: 09:15 - 15:30")
        self.lbl_clock.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        header_bar.addWidget(self.lbl_clock)

        header_bar.addStretch()

        # Heatmap Engine ON/OFF Checkbox (DEFAULT OFF to save background CPU)
        self.chk_heatmap_header = QtWidgets.QCheckBox("🔥 Enable Heatmap")
        self.chk_heatmap_header.setChecked(False)  # DEFAULT OFF
        self.chk_heatmap_header.setToolTip("Toggle to activate live Heatmap calculations or keep paused to save CPU.")
        self.chk_heatmap_header.setStyleSheet(f"""
            QCheckBox {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 11px;
                font-weight: bold;
                spacing: 6px;
                margin-right: 8px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid {COLOR_BORDER};
                background-color: {COLOR_PANEL_DARK};
            }}
            QCheckBox::indicator:checked {{
                background-color: #10B981;
                border-color: #10B981;
            }}
        """)
        self.chk_heatmap_header.toggled.connect(self._on_heatmap_toggle)
        header_bar.addWidget(self.chk_heatmap_header)

        # Quick Add Stock Input
        self.inp_quick_add = QtWidgets.QLineEdit()
        self.inp_quick_add.setPlaceholderText("+ Add Stock (e.g. IDEA, SBIN)...")
        self.inp_quick_add.setFixedWidth(200)
        self.inp_quick_add.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
        """)
        self.inp_quick_add.returnPressed.connect(self._on_quick_add)
        header_bar.addWidget(self.inp_quick_add)

        # Manage Basket Button
        self.btn_manage = QtWidgets.QPushButton("Manage Basket")
        self.btn_manage.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2D3748;
            }}
        """)
        self.btn_manage.clicked.connect(self._open_token_manager)
        header_bar.addWidget(self.btn_manage)

        main_layout.addLayout(header_bar)

        # 2. MAIN TABBED INTERFACE
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLOR_BORDER};
                background-color: {COLOR_BG_DARK};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_SECONDARY};
                padding: 8px 24px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: #2563EB;
                color: #FFFFFF;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #2D3748;
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        # ======================================================================
        # TAB 1: RELATIVE STRENGTH MULTI-LINE CHART + WATCHLIST
        # ======================================================================
        tab_chart_widget = QtWidgets.QWidget()
        tab_chart_layout = QtWidgets.QHBoxLayout(tab_chart_widget)
        tab_chart_layout.setContentsMargins(6, 6, 6, 6)
        tab_chart_layout.setSpacing(6)

        self.chart_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left: Multi-Line Relative Strength Chart (PyQtGraph)
        self.chart = RelativeStrengthChart()
        self.chart.multiday_toggled.connect(self._on_multiday_toggled)
        self.chart_splitter.addWidget(self.chart)

        # Right: Watchlist & Quick Filter Sidebar
        self.filter_panel = FilterPanel()
        self.filter_panel.visibility_toggled.connect(self.chart.set_stock_visible)
        self.filter_panel.remove_token_requested.connect(self._on_remove_stock_requested)
        self.filter_panel.bulk_filter_applied.connect(self.chart.auto_fit)
        self.filter_panel.stock_hover_entered.connect(self.chart.hover_stock)
        self.filter_panel.stock_hover_left.connect(self.chart.unhover_stock)
        self.filter_panel.manage_basket_requested.connect(self._open_token_manager)
        self.chart_splitter.addWidget(self.filter_panel)

        # Wire up Surge Radar live parameter changes
        self.chart.chk_surge_radar.toggled.connect(self._evaluate_radar_surges)
        self.chart.spin_window.valueChanged.connect(self._evaluate_radar_surges)
        self.chart.spin_thresh.valueChanged.connect(self._evaluate_radar_surges)

        # 75% Chart / 25% Watchlist
        self.chart_splitter.setStretchFactor(0, 75)
        self.chart_splitter.setStretchFactor(1, 25)

        tab_chart_layout.addWidget(self.chart_splitter)
        self.tabs.addTab(tab_chart_widget, "📈 Relative Strength Line Chart")

        # ======================================================================
        # TAB 2: LIVE HEATMAP MATRIX (FULL-SCREEN DEDICATED VIEW)
        # ======================================================================
        tab_heatmap_widget = QtWidgets.QWidget()
        tab_heatmap_layout = QtWidgets.QVBoxLayout(tab_heatmap_widget)
        tab_heatmap_layout.setContentsMargins(8, 8, 8, 8)
        tab_heatmap_layout.setSpacing(8)

        self.heatmap = HeatmapWidget(default_enabled=False)
        self.heatmap.stock_selected.connect(self._on_heatmap_stock_selected)
        self.heatmap.engine_toggled.connect(self._on_heatmap_widget_toggled)
        tab_heatmap_layout.addWidget(self.heatmap)

        self.tabs.addTab(tab_heatmap_widget, "🔥 Live Heatmap (Market Cap & Equal)")

        main_layout.addWidget(self.tabs)

    # ==========================================================================
    # HEATMAP ENGINE ON/OFF TOGGLE & STATE SYNCHRONIZATION
    # ==========================================================================

    def _on_heatmap_toggle(self, enabled: bool) -> None:
        """Triggered when user clicks '🔥 Enable Heatmap' in top header bar."""
        self.heatmap.set_engine_enabled(enabled)
        if enabled:
            self._sync_heatmap_all()

    def _on_heatmap_widget_toggled(self, enabled: bool) -> None:
        """Triggered when user toggles 'Enable Heatmap Engine' inside Heatmap tab."""
        if self.chk_heatmap_header.isChecked() != enabled:
            self.chk_heatmap_header.blockSignals(True)
            self.chk_heatmap_header.setChecked(enabled)
            self.chk_heatmap_header.blockSignals(False)
        if enabled:
            self._sync_heatmap_all()

    def _sync_heatmap_all(self) -> None:
        """Hydrates all heatmap tiles with the latest snapshot data across active basket."""
        for tok, m in self.active_basket.items():
            sym = m["symbol"]
            mcap = float(m.get("market_cap_crores", 10000.0))
            prev_close = float(m.get("prev_close", 100.0))

            series = self.chart.stock_series.get(tok)
            if series and series.get("pct_series") and len(series["pct_series"]) > 0:
                pct = series["pct_series"][-1]
                ltp = series["ltp_series"][-1] if series.get("ltp_series") and len(series["ltp_series"]) > 0 else prev_close
            else:
                pct = 0.0
                ltp = prev_close

            self.heatmap.register_or_update_tile(tok, sym, pct, ltp, mcap, force=True)

    # ==========================================================================
    # DATA BOOTSTRAP: 09:15 HISTORICAL REPLAY & BASKET SYNC
    # ==========================================================================

    def _bootstrap_data(self) -> None:
        """Initializes database, loads active Nifty 50 tokens, and hydrates chart with today's 1m bars."""
        logger.info("Bootstrapping Relative Strength Dashboard...")
        self.db.initialize_schema()
        # Sync default catalog into MySQL (preserves any custom tokens added by user)
        self.basket_mgr.sync_default_basket(force_reset_to_nifty50=False)
        self.active_basket = self.db.get_active_basket_tokens()

        # Register all active stocks into chart, watchlist, and heatmap
        for tok, m in self.active_basket.items():
            sym = m["symbol"]
            prev_px = float(m.get("prev_close", 100.0))
            mcap = float(m.get("market_cap_crores", 10000.0))

            self.chart.register_stock(tok, sym)
            color_hex = self.chart.stock_series[tok]["color"]
            self.filter_panel.add_or_update_stock(tok, sym, color_hex, pct=0.0, ltp=prev_px, prev_close=prev_px)
            if self.heatmap.is_engine_enabled:
                self.heatmap.register_or_update_tile(tok, sym, pct_change=0.0, ltp=prev_px, mcap=mcap)

        # Load 1-minute historical bars (today or multi-day based on initial checkbox state)
        if self.chart.chk_multiday.isChecked():
            dates = self.db.fetch_distinct_trading_dates(limit=DAYS_TO_KEEP)
            bars = self.db.fetch_multi_day_1m_bars(days_to_keep=DAYS_TO_KEEP)
            logger.info(f"Bootstrapping multi-day continuation bars ({len(dates)} days) for {len(bars)} tokens.")
        else:
            dates = [datetime.now().strftime("%Y-%m-%d")]
            bars = self.db.fetch_today_1m_bars()
            logger.info(f"Bootstrapping today's historical 1m bars for {len(bars)} tokens.")

        if bars:
            self.chart.load_historical_bars(bars, trading_dates=dates)

        self._evaluate_radar_surges()
        self.last_poll_time = datetime.now() - timedelta(seconds=2)

    def _on_multiday_toggled(self, is_multiday: bool) -> None:
        """Reloads chart series when user toggles between today's chart and multi-day continuation."""
        logger.info(f"Multi-day view toggled: {is_multiday} (retention: {DAYS_TO_KEEP} days)")
        self.chart.reset_chart_series()
        if is_multiday:
            dates = self.db.fetch_distinct_trading_dates(limit=DAYS_TO_KEEP)
            bars = self.db.fetch_multi_day_1m_bars(days_to_keep=DAYS_TO_KEEP)
            mode_lbl = f"past {len(dates)} days continuation"
        else:
            dates = [datetime.now().strftime("%Y-%m-%d")]
            bars = self.db.fetch_today_1m_bars()
            mode_lbl = "today's intraday"

        if bars:
            logger.info(f"Loaded {mode_lbl} 1m bars for {len(bars)} tokens.")
            self.chart.load_historical_bars(bars, trading_dates=dates)

            # Replay any granular ticks logged since the newest bar time up to now
            try:
                latest_bar_time = max(
                    (b["bar_time"] for bar_list in bars.values() for b in bar_list if "bar_time" in b),
                    default=None,
                )
                if latest_bar_time:
                    recent_ticks = self.db.fetch_latest_ticks_since(latest_bar_time)
                    for t in recent_ticks:
                        t_tok = str(t["token"])
                        t_sym = str(t["symbol"])
                        t_pct = round(float(t["pct_change"]), 2)
                        t_ltp = round(float(t["ltp"]), 2)
                        t_time = t["tick_time"]
                        self.chart.append_tick(t_tok, t_sym, t_time, t_pct, ltp=t_ltp)
            except Exception as replay_err:
                logger.warning(f"Error replaying post-bar ticks during multi-day reload: {replay_err}")

        self.chart.auto_fit_view()
        self._evaluate_radar_surges()

    # ==========================================================================
    # LIVE STREAMING TICKS POLLER (EVERY 500ms)
    # ==========================================================================

    def _poll_live_updates(self) -> None:
        """Queries recent ticks from MySQL and streams updates across chart, heatmap, and filters."""
        now_dt = datetime.now()
        self.lbl_clock.setText(f"TIME: {now_dt.strftime('%H:%M:%S')} | MARKET: 09:15 - 15:30")

        ticks = self.db.fetch_latest_ticks_since(self.last_poll_time)
        if ticks:
            max_tick_time = self.last_poll_time
            for t in ticks:
                tok = str(t["token"])
                sym = str(t["symbol"])
                pct = round(float(t["pct_change"]), 2)
                ltp = round(float(t["ltp"]), 2)
                t_time = t["tick_time"]

                if t_time > max_tick_time:
                    max_tick_time = t_time

                # 1. Update Chart curve (continuous market session coordinate)
                self.chart.append_tick(tok, sym, t_time, pct, ltp=ltp)

                # 2. Update Heatmap tile (only when enabled by user to save background CPU)
                if self.heatmap.is_engine_enabled:
                    mcap = float(self.active_basket.get(tok, {}).get("market_cap_crores", 10000.0))
                    self.heatmap.register_or_update_tile(tok, sym, pct, ltp, mcap)

                # 3. Update Watchlist badge with double-digit % and live LTP
                color_hex = self.chart.stock_series.get(tok, {}).get("color", "#38BDF8")
                prev_close = float(self.active_basket.get(tok, {}).get("prev_close", 100.0))
                self.filter_panel.add_or_update_stock(tok, sym, color_hex, pct=pct, ltp=ltp, prev_close=prev_close)

            self.last_poll_time = max_tick_time
            self._evaluate_radar_surges()

    def _evaluate_radar_surges(self) -> None:
        """Evaluates active momentum surges and updates chart chips and watchlist badges."""
        radar_enabled = self.chart.chk_surge_radar.isChecked()
        win_min = self.chart.spin_window.value()
        win_seconds = float(win_min * 60)
        thresh_pct = float(self.chart.spin_thresh.value())

        active_surges = self.chart.evaluate_surges(
            window_seconds=win_seconds,
            threshold_pct=thresh_pct,
            enabled=radar_enabled,
        )
        self.chart.update_surge_chips(active_surges)
        surges_dict = {s["token"]: s["velocity"] for s in active_surges} if radar_enabled else {}
        self.filter_panel.update_surges(surges_dict, window_min=win_min)

    # ==========================================================================
    # USER INTERACTIONS & CONTROLS
    # ==========================================================================

    def _on_heatmap_stock_selected(self, token: str) -> None:
        """When user clicks a tile on the heatmap, highlight its line and switch to chart tab."""
        self.chart.highlight_stock(token)
        self.tabs.setCurrentIndex(0)

    def _open_token_manager(self) -> None:
        """Opens modal dialog for dynamic token management."""
        dlg = TokenManagerDialog(db=self.db, basket_mgr=self.basket_mgr, parent=self)
        dlg.token_added.connect(self._on_stock_added)
        dlg.token_removed.connect(self._on_remove_stock_requested)
        dlg.exec()

    def _on_quick_add(self) -> None:
        """Handles fast stock addition from the top search bar."""
        query = self.inp_quick_add.text().strip()
        if not query:
            return

        res = self.basket_mgr.resolve_instrument(query)
        if res:
            if self.db.add_token_dynamically(res):
                self._on_stock_added(res)
                self.inp_quick_add.clear()
            else:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed adding {query} to MySQL.")
        else:
            QtWidgets.QMessageBox.warning(self, "Not Found", f"Could not find stock '{query}'.")

    def _on_stock_added(self, stock_info: Dict[str, Any]) -> None:
        """Registers newly added stock in all live widgets instantly."""
        tok = str(stock_info["token"])
        sym = str(stock_info["symbol"])
        mcap = float(stock_info.get("market_cap_crores", 10000.0))
        prev_close = float(stock_info.get("prev_close", 100.0))

        self.active_basket[tok] = stock_info
        self.chart.register_stock(tok, sym)
        color_hex = self.chart.stock_series[tok]["color"]
        self.filter_panel.add_or_update_stock(tok, sym, color_hex, pct=0.0, ltp=prev_close, prev_close=prev_close)
        if self.heatmap.is_engine_enabled:
            self.heatmap.register_or_update_tile(tok, sym, pct_change=0.0, ltp=prev_close, mcap=mcap)
        logger.info(f"UI dynamically integrated newly added stock: {sym} (Token {tok}).")

    def _on_remove_stock_requested(self, token: str) -> None:
        """Removes a stock from the database and UI."""
        if self.db.remove_token_dynamically(token):
            if token in self.active_basket:
                del self.active_basket[token]
            self.chart.set_stock_visible(token, False)
            self.heatmap.remove_tile(token)
            self.filter_panel.remove_stock(token)
            logger.info(f"UI dynamically removed stock Token {token}.")
