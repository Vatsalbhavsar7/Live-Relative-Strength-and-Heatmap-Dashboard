"""
multi_line_chart.py
-------------------
High-performance OpenGL-accelerated Multi-Line Relative Strength Chart.
- Plots percentage change (%) from previous close against a prominent 0.00% baseline.
- Real-time crosshair HUD tooltip showing time, stock, LTP, and % change.
- One-click auto-fit button and mouse-wheel zoom/pan.
- Single-stock focus highlight (dims non-selected lines on hover/click).
- Multi-Timeframe compression (1m, 2m, 3m, 4m, 5m, 10m, 15m, 30m, 1h, 2h, 3h, 4h, Live).
- ⚡ Surge Radar: Real-time momentum velocity detection, automatic line-thickening & alert chips.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from config import (
    COLOR_BASELINE_WHITE,
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PANEL_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    DAYS_TO_KEEP,
    DEFAULT_SHOW_MULTIDAY,
    DEFAULT_Y_MAX,
    DEFAULT_Y_MIN,
    LINE_PALETTE,
    Y_AXIS_PADDING_PCT,
)

# Enable OpenGL acceleration and anti-aliasing in PyQtGraph
pg.setConfigOptions(useOpenGL=True, antialias=True)


class TimeAxisItem(pg.AxisItem):
    """Custom PyQtGraph Axis displaying timestamps formatted dynamically (intraday vs multi-day)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multiday_mode: bool = False

    def tickStrings(self, values, scale, spacing):
        strings = []
        valid_dates = []
        for val in values:
            try:
                dt = datetime.fromtimestamp(val)
                valid_dates.append(dt)
            except Exception:
                pass

        span_days = self.multiday_mode
        if not span_days and len(valid_dates) >= 2:
            if (max(valid_dates).date() - min(valid_dates).date()).days > 0:
                span_days = True

        for val in values:
            try:
                dt = datetime.fromtimestamp(val)
                if span_days:
                    strings.append(dt.strftime("%d %b %H:%M"))
                else:
                    strings.append(dt.strftime("%H:%M:%S"))
            except Exception:
                strings.append("")
        return strings


class RelativeStrengthChart(QtWidgets.QWidget):
    """PyQtGraph-based multi-line relative performance chart."""

    multiday_toggled = QtCore.Signal(bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        # Storage
        self.stock_series: Dict[str, Dict[str, Any]] = {}
        self.color_index: int = 0
        self.highlighted_token: Optional[str] = None
        self.surging_tokens: Dict[str, float] = {}  # token -> velocity
        self.active_timeframe_minutes: int = 0     # 0 = Live (Raw Ticks)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 1. Chart Toolbar Header
        header_bar = QtWidgets.QHBoxLayout()
        header_bar.setContentsMargins(8, 4, 8, 4)

        title_lbl = QtWidgets.QLabel("RELATIVE STRENGTH (PERCENTAGE CHANGE FROM PREV CLOSE)")
        title_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 12px;")
        header_bar.addWidget(title_lbl)

        header_bar.addStretch()

        # Timeframe Selector (1m, 2m, 3m, 4m, 5m, 10m, 15m, 30m, 1h, 2h, 3h, 4h, Live)
        lbl_tf = QtWidgets.QLabel("Timeframe:")
        lbl_tf.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        header_bar.addWidget(lbl_tf)

        self.combo_timeframe = QtWidgets.QComboBox()
        self.timeframe_options = [
            ("⚡ Live (Raw Ticks)", 0),
            ("1 minute", 1),
            ("2 minutes", 2),
            ("3 minutes", 3),
            ("4 minutes", 4),
            ("5 minutes", 5),
            ("10 minutes", 10),
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("1 hour", 60),
            ("2 hours", 120),
            ("3 hours", 180),
            ("4 hours", 240),
        ]
        for label, val in self.timeframe_options:
            self.combo_timeframe.addItem(label, val)

        self.combo_timeframe.setCurrentIndex(0)  # Default: Live
        self.combo_timeframe.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR_PANEL_DARK};
                color: #38BDF8;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                selection-background-color: #2563EB;
                border: 1px solid {COLOR_BORDER};
            }}
        """)
        self.combo_timeframe.currentIndexChanged.connect(self._on_timeframe_changed)
        header_bar.addWidget(self.combo_timeframe)

        # Multi-day continuation checkbox (Past DAYS_TO_KEEP Days)
        self.chk_multiday = QtWidgets.QCheckBox(f"Past {DAYS_TO_KEEP} Days Continuation")
        self.chk_multiday.setChecked(DEFAULT_SHOW_MULTIDAY)
        self.chk_multiday.setToolTip(f"Toggle to view continuous multi-day line chart ({DAYS_TO_KEEP} trading days + live). Uncheck for today's intraday chart only.")
        self.chk_multiday.setStyleSheet(f"""
            QCheckBox {{
                color: #38BDF8;
                font-size: 11px;
                font-weight: bold;
                padding-left: 6px;
                padding-right: 4px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid {COLOR_BORDER};
                background-color: {COLOR_PANEL_DARK};
            }}
            QCheckBox::indicator:checked {{
                background-color: #0284C7;
                border-color: #38BDF8;
            }}
        """)
        self.chk_multiday.toggled.connect(self._on_multiday_toggled)
        header_bar.addWidget(self.chk_multiday)

        self.btn_autofit = QtWidgets.QPushButton("Auto-Fit View")
        self.btn_autofit.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2D3748;
                border-color: #4A5568;
            }}
        """)
        self.btn_autofit.clicked.connect(self.auto_fit_view)
        header_bar.addWidget(self.btn_autofit)

        self.btn_reset_focus = QtWidgets.QPushButton("Reset Focus")
        self.btn_reset_focus.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2D3748;
            }}
        """)
        self.btn_reset_focus.clicked.connect(self.clear_highlight)
        header_bar.addWidget(self.btn_reset_focus)

        layout.addLayout(header_bar)

        # 2. Surge Radar Controls & Alert Ribbon Sub-Bar
        self.radar_bar = QtWidgets.QHBoxLayout()
        self.radar_bar.setContentsMargins(8, 2, 8, 4)
        self.radar_bar.setSpacing(8)

        # 2a. Enable Toggle
        self.chk_surge_radar = QtWidgets.QCheckBox("⚡ Surge Radar")
        self.chk_surge_radar.setChecked(True)
        self.chk_surge_radar.setToolTip("Toggle real-time momentum velocity detection & auto-line thickening")
        self.chk_surge_radar.setStyleSheet(f"""
            QCheckBox {{
                color: #F59E0B;
                font-size: 11px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
            }}
        """)
        self.radar_bar.addWidget(self.chk_surge_radar)

        # 2b. Window (Minutes)
        lbl_win = QtWidgets.QLabel("Window:")
        lbl_win.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.radar_bar.addWidget(lbl_win)

        self.spin_window = QtWidgets.QSpinBox()
        self.spin_window.setRange(1, 15)
        self.spin_window.setValue(2)
        self.spin_window.setSuffix(" min")
        self.spin_window.setToolTip("Lookback window for velocity calculation (e.g. price change over last 2 minutes)")
        self.spin_window.setStyleSheet(f"""
            QSpinBox {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self.radar_bar.addWidget(self.spin_window)

        # 2c. Threshold (%)
        lbl_thresh = QtWidgets.QLabel("Min Move:")
        lbl_thresh.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.radar_bar.addWidget(lbl_thresh)

        self.spin_thresh = QtWidgets.QDoubleSpinBox()
        self.spin_thresh.setRange(0.10, 5.00)
        self.spin_thresh.setValue(0.30)
        self.spin_thresh.setSingleStep(0.05)
        self.spin_thresh.setSuffix(" %")
        self.spin_thresh.setToolTip("Minimum percentage movement within window required to trigger a surge highlight")
        self.spin_thresh.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self.radar_bar.addWidget(self.spin_thresh)

        # Separator line
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet("color: #334155;")
        self.radar_bar.addWidget(sep)

        # 2d. Clickable Chips Container
        self.chips_layout = QtWidgets.QHBoxLayout()
        self.chips_layout.setSpacing(4)
        self.radar_bar.addLayout(self.chips_layout)

        self.lbl_radar_status = QtWidgets.QLabel("Radar Active (Monitoring 2m velocity)")
        self.lbl_radar_status.setStyleSheet("color: #64748B; font-size: 10px; font-style: italic;")
        self.chips_layout.addWidget(self.lbl_radar_status)

        self.radar_bar.addStretch()
        layout.addLayout(self.radar_bar)

        # 3. PyQtGraph Plot Widget
        self.time_axis = TimeAxisItem(orientation="bottom")
        self.plot_widget = pg.PlotWidget(axisItems={"bottom": self.time_axis})
        self.plot_widget.setBackground(COLOR_BG_DARK)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setLabel("left", "Relative Performance (%)", color=COLOR_TEXT_SECONDARY, size="11pt")
        self.plot_widget.setLabel("bottom", "Market Time", color=COLOR_TEXT_SECONDARY, size="11pt")
        self.plot_widget.setYRange(DEFAULT_Y_MIN, DEFAULT_Y_MAX, padding=0.1)

        # Midline: 0.00% dashed reference
        self.baseline_zero = pg.InfiniteLine(
            pos=0.0,
            angle=0,
            pen=pg.mkPen(color=COLOR_BASELINE_WHITE, width=1.2, style=QtCore.Qt.DashLine),
        )
        self.plot_widget.addItem(self.baseline_zero)

        # Crosshair: Vertical time marker
        self.v_crosshair = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(color="#CBD5E1", width=1, style=QtCore.Qt.DotLine),
        )
        self.v_crosshair.setVisible(False)
        self.plot_widget.addItem(self.v_crosshair)

        # Floating HUD Tooltip Overlay
        self.hud_label = QtWidgets.QLabel(self.plot_widget)
        self.hud_label.setStyleSheet(f"""
            background-color: rgba(18, 24, 38, 0.90);
            color: #FFFFFF;
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 11px;
            font-family: Consolas, monospace;
        """)
        self.hud_label.setVisible(False)

        # Mouse tracking
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        layout.addWidget(self.plot_widget)

    # ==========================================================================
    # DATA INGESTION, TIMEFRAME RESAMPLING & SERIES REGISTRATION
    # ==========================================================================

    def _resample_series(self, x_vals: List[float], y_vals: List[float], interval_minutes: int) -> Tuple[List[float], List[float]]:
        """
        Compresses high-frequency series into discrete timeframe bars:
        Takes the close percentage of each interval bucket.
        """
        if not x_vals or interval_minutes <= 0:
            return list(x_vals), list(y_vals)

        bucket_sec = interval_minutes * 60
        res_x: List[float] = []
        res_y: List[float] = []

        current_bucket = None
        last_val = None

        for t, y in zip(x_vals, y_vals):
            b = int(t // bucket_sec) * bucket_sec
            if current_bucket is None:
                current_bucket = b
                last_val = y
            elif b == current_bucket:
                last_val = y
            else:
                res_x.append(current_bucket + bucket_sec)
                res_y.append(last_val)
                current_bucket = b
                last_val = y

        if current_bucket is not None and last_val is not None:
            res_x.append(x_vals[-1])
            res_y.append(last_val)

        return res_x, res_y

    def _on_timeframe_changed(self, index: int) -> None:
        """Handles user selecting a new timeframe from dropdown."""
        interval_minutes = self.combo_timeframe.currentData()
        self.set_timeframe(interval_minutes)

    def set_timeframe(self, interval_minutes: int) -> None:
        """Compresses/resamples all stock series to the specified timeframe interval."""
        self.active_timeframe_minutes = interval_minutes
        for tok, s in self.stock_series.items():
            if not s["raw_x"]:
                continue
            if interval_minutes <= 0:
                s["x"] = list(s["raw_x"])
                s["y"] = list(s["raw_y"])
                s["last_bucket"] = None
            else:
                s["x"], s["y"] = self._resample_series(s["raw_x"], s["raw_y"], interval_minutes)
                bucket_sec = interval_minutes * 60
                s["last_bucket"] = int(s["raw_x"][-1] // bucket_sec) * bucket_sec

            if s["visible"]:
                s["curve"].setData(s["x"], s["y"])

        self.auto_fit_view()

    def _on_multiday_toggled(self, checked: bool) -> None:
        """Handles user clicking the multi-day continuation checkbox."""
        self.time_axis.multiday_mode = checked
        self.multiday_toggled.emit(checked)

    def reset_chart_series(self) -> None:
        """Clears all plotted data points while keeping stock registrations, colors, and curve objects."""
        for s in self.stock_series.values():
            s["x"] = []
            s["y"] = []
            s["raw_x"] = []
            s["raw_y"] = []
            s["last_bucket"] = None
            s["curve"].setData([], [])

    def register_stock(self, token: str, symbol: str) -> None:
        """Registers a stock series into the chart if not already present."""
        if token in self.stock_series:
            return

        color_hex = LINE_PALETTE[self.color_index % len(LINE_PALETTE)]
        self.color_index += 1

        pen = pg.mkPen(color=color_hex, width=1.5)
        curve = self.plot_widget.plot([], [], pen=pen, name=symbol)

        self.stock_series[token] = {
            "symbol": symbol,
            "x": [],
            "y": [],
            "raw_x": [],
            "raw_y": [],
            "last_bucket": None,
            "curve": curve,
            "color": color_hex,
            "visible": True,
            "last_ltp": 0.0,
        }

    def append_tick(self, token: str, symbol: str, timestamp_epoch: float, pct_change: float, ltp: float = 0.0) -> None:
        """Appends a single real-time data point to the stock curve."""
        if token not in self.stock_series:
            self.register_stock(token, symbol)

        s = self.stock_series[token]
        s["raw_x"].append(timestamp_epoch)
        s["raw_y"].append(pct_change)
        if ltp > 0:
            s["last_ltp"] = ltp

        if len(s["raw_x"]) > 50000:
            s["raw_x"] = s["raw_x"][-45000:]
            s["raw_y"] = s["raw_y"][-45000:]

        tf = self.active_timeframe_minutes
        if tf <= 0:
            s["x"].append(timestamp_epoch)
            s["y"].append(pct_change)
            if len(s["x"]) > 50000:
                s["x"] = s["x"][-45000:]
                s["y"] = s["y"][-45000:]
            if s["visible"]:
                s["curve"].setData(s["x"], s["y"])
        else:
            bucket_sec = tf * 60
            curr_bucket = int(timestamp_epoch // bucket_sec) * bucket_sec
            if s.get("last_bucket") == curr_bucket and len(s["x"]) > 0:
                s["x"][-1] = timestamp_epoch
                s["y"][-1] = pct_change
            else:
                s["last_bucket"] = curr_bucket
                s["x"].append(timestamp_epoch)
                s["y"].append(pct_change)

            if s["visible"]:
                s["curve"].setData(s["x"], s["y"])

    def load_historical_bars(self, bars_by_token: Dict[str, List[Dict[str, Any]]]) -> None:
        """Pre-populates the chart with today's historical data (09:15 - present)."""
        all_y_values = []
        for token, bars in bars_by_token.items():
            if not bars:
                continue
            symbol = bars[0]["symbol"]
            self.register_stock(token, symbol)

            x_vals = []
            y_vals = []
            for b in bars:
                dt_obj = b["bar_time"]
                epoch = dt_obj.timestamp() if isinstance(dt_obj, datetime) else datetime.fromisoformat(str(dt_obj)).timestamp()
                x_vals.append(epoch)
                y_vals.append(float(b["close_pct"]))
                all_y_values.append(float(b["close_pct"]))

            s = self.stock_series[token]
            s["raw_x"] = list(x_vals)
            s["raw_y"] = list(y_vals)
            if bars:
                s["last_ltp"] = float(bars[-1].get("last_ltp", 0.0))

            if self.active_timeframe_minutes <= 0:
                s["x"] = list(x_vals)
                s["y"] = list(y_vals)
                s["last_bucket"] = None
            else:
                s["x"], s["y"] = self._resample_series(x_vals, y_vals, self.active_timeframe_minutes)
                bucket_sec = self.active_timeframe_minutes * 60
                s["last_bucket"] = int(x_vals[-1] // bucket_sec) * bucket_sec

            if s["visible"]:
                s["curve"].setData(s["x"], s["y"])

        if all_y_values:
            y_min = min(all_y_values)
            y_max = max(all_y_values)
            padding = max(1.5, (y_max - y_min) * 0.15)
            self.plot_widget.setYRange(y_min - padding, y_max + padding)

    # ==========================================================================
    # INTERACTIVE HIGHLIGHTING & FOCUS
    # ==========================================================================

    def highlight_stock(self, target_token: str) -> None:
        """Emphasizes a selected stock (thick line) while dimming all other lines."""
        if target_token not in self.stock_series:
            return

        self.highlighted_token = target_token
        for tok, s in self.stock_series.items():
            if not s["visible"]:
                continue
            if tok == target_token:
                s["curve"].setPen(pg.mkPen(color=s["color"], width=3.5))
                s["curve"].setZValue(100)
            else:
                c = QtGui.QColor(s["color"])
                c.setAlpha(60)
                s["curve"].setPen(pg.mkPen(color=c, width=1.0))
                s["curve"].setZValue(1)

    def hover_stock(self, target_token: str) -> None:
        """Emphasizes the hovered stock line from watchlist hover (thick bold line) while dimming others."""
        if target_token not in self.stock_series:
            return

        for tok, s in self.stock_series.items():
            if not s["visible"]:
                continue
            if tok == target_token:
                s["curve"].setPen(pg.mkPen(color=s["color"], width=3.8))
                s["curve"].setZValue(120)
            else:
                c = QtGui.QColor(s["color"])
                c.setAlpha(45)
                s["curve"].setPen(pg.mkPen(color=c, width=1.0))
                s["curve"].setZValue(1)

    def unhover_stock(self, target_token: str = "") -> None:
        """Restores line widths and opacities when mouse leaves the watchlist item."""
        if self.highlighted_token:
            self.highlight_stock(self.highlighted_token)
        else:
            for tok, s in self.stock_series.items():
                if s["visible"]:
                    is_surging = tok in self.surging_tokens and self.chk_surge_radar.isChecked()
                    w = 3.5 if is_surging else 1.5
                    z = 90 if is_surging else 5
                    s["curve"].setPen(pg.mkPen(color=s["color"], width=w))
                    s["curve"].setZValue(z)

    def clear_highlight(self) -> None:
        """Restores all visible lines to their standard width and normal opacity."""
        self.highlighted_token = None
        for tok, s in self.stock_series.items():
            if s["visible"]:
                is_surging = tok in self.surging_tokens and self.chk_surge_radar.isChecked()
                w = 3.5 if is_surging else 1.5
                z = 90 if is_surging else 5
                s["curve"].setPen(pg.mkPen(color=s["color"], width=w))
                s["curve"].setZValue(z)

    # ==========================================================================
    # REAL-TIME MOMENTUM VELOCITY & SURGE DETECTION
    # ==========================================================================

    def evaluate_surges(self, window_seconds: float = 120.0, threshold_pct: float = 0.30, enabled: bool = True) -> List[Dict[str, Any]]:
        """
        Calculates short-term momentum velocity for all visible lines:
            velocity = pct_now - pct_at_(now - window_seconds)
        If enabled and |velocity| >= threshold_pct:
            Auto-thickens the line to width 3.5 and brings to front (zValue 90).
        Returns list of active surge records sorted by highest velocity magnitude.
        """
        if not enabled:
            if self.surging_tokens:
                self.surging_tokens.clear()
                if not self.highlighted_token:
                    for s in self.stock_series.values():
                        if s["visible"]:
                            s["curve"].setPen(pg.mkPen(color=s["color"], width=1.5))
                            s["curve"].setZValue(5)
            return []

        active_surges = []
        new_surging: Dict[str, float] = {}

        for tok, s in self.stock_series.items():
            if not s["visible"] or len(s["x"]) < 2:
                continue

            t_now = s["x"][-1]
            t_target = t_now - window_seconds

            idx = np.searchsorted(s["x"], t_target)
            if idx >= len(s["x"]):
                idx = len(s["x"]) - 1
            elif idx > 0 and abs(s["x"][idx - 1] - t_target) < abs(s["x"][idx] - t_target):
                idx = idx - 1

            pct_now = s["y"][-1]
            pct_prev = s["y"][idx]
            velocity = round(pct_now - pct_prev, 2)

            if abs(velocity) >= threshold_pct:
                new_surging[tok] = velocity
                active_surges.append({
                    "token": tok,
                    "symbol": s["symbol"],
                    "velocity": velocity,
                    "pct_now": pct_now,
                    "color": s["color"],
                    "last_ltp": s.get("last_ltp", 0.0),
                })
                if not self.highlighted_token:
                    s["curve"].setPen(pg.mkPen(color=s["color"], width=3.5))
                    s["curve"].setZValue(90)
            else:
                if tok in self.surging_tokens and not self.highlighted_token:
                    s["curve"].setPen(pg.mkPen(color=s["color"], width=1.5))
                    s["curve"].setZValue(5)

        self.surging_tokens = new_surging
        active_surges.sort(key=lambda x: abs(x["velocity"]), reverse=True)
        return active_surges

    def update_surge_chips(self, surges: List[Dict[str, Any]]) -> None:
        """Updates the clickable chip buttons in the radar sub-bar."""
        while self.chips_layout.count() > 0:
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.chk_surge_radar.isChecked():
            lbl = QtWidgets.QLabel("Surge Radar Disabled")
            lbl.setStyleSheet("color: #64748B; font-size: 10px;")
            self.chips_layout.addWidget(lbl)
            return

        win_min = self.spin_window.value()
        thresh = self.spin_thresh.value()

        if not surges:
            lbl = QtWidgets.QLabel(f"No sudden breakouts (threshold ±{thresh:.2f}% / {win_min}m)")
            lbl.setStyleSheet("color: #64748B; font-size: 10px; font-style: italic;")
            self.chips_layout.addWidget(lbl)
            return

        for s in surges[:5]:
            vel = s["velocity"]
            sym = s["symbol"].replace("-EQ", "")
            icon = "⚡" if vel > 0 else "🔻"
            bg_col = "#064E3B" if vel > 0 else "#7F1D1D"
            border_col = "#10B981" if vel > 0 else "#EF4444"
            text_col = "#A7F3D0" if vel > 0 else "#FECACA"

            btn_chip = QtWidgets.QPushButton(f"{icon} {sym} {vel:+.2f}% ({win_min}m)")
            btn_chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_col};
                    color: {text_col};
                    border: 1px solid {border_col};
                    border-radius: 3px;
                    padding: 2px 7px;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {border_col};
                    color: #FFFFFF;
                }}
            """)
            btn_chip.setToolTip(
                f"Click to focus {s['symbol']}\n"
                f"Recent Velocity: {vel:+.2f}% in last {win_min}m\n"
                f"Total Day Change: {s['pct_now']:+.2f}%\n"
                f"LTP: Rs. {s.get('last_ltp', 0.0):,.2f}"
            )
            btn_chip.clicked.connect(lambda checked=False, tok=s["token"]: self.highlight_stock(tok))
            self.chips_layout.addWidget(btn_chip)

    def set_stock_visible(self, token: str, is_visible: bool) -> None:
        """Hides or reveals an individual stock series."""
        if token in self.stock_series:
            s = self.stock_series[token]
            s["visible"] = is_visible
            if is_visible:
                s["curve"].setData(s["x"], s["y"])
            else:
                s["curve"].setData([], [])

    def auto_fit_view(self) -> None:
        """Auto-scales X and Y axes to frame all available data."""
        self.plot_widget.enableAutoRange()
        vb = self.plot_widget.getViewBox()
        view_range = vb.viewRange()
        y_min, y_max = view_range[1]
        y_min = min(y_min, -3.0)
        y_max = max(y_max, 3.0)
        self.plot_widget.setYRange(y_min * Y_AXIS_PADDING_PCT, y_max * Y_AXIS_PADDING_PCT)

    auto_fit = auto_fit_view

    # ==========================================================================
    # CROSSHAIR & TOOLTIP HOVER
    # ==========================================================================

    def _on_mouse_moved(self, pos) -> None:
        """Updates crosshair and floating HUD info showing only lines closest to cursor position."""
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            self.v_crosshair.setVisible(False)
            self.hud_label.setVisible(False)
            return

        mouse_point = self.plot_widget.getViewBox().mapSceneToView(pos)
        x_val = mouse_point.x()
        y_val = mouse_point.y()

        self.v_crosshair.setPos(x_val)
        self.v_crosshair.setVisible(True)

        try:
            if getattr(self, "chk_multiday", None) and self.chk_multiday.isChecked():
                hover_time = datetime.fromtimestamp(x_val).strftime("%d %b %H:%M:%S")
            else:
                hover_time = datetime.fromtimestamp(x_val).strftime("%H:%M:%S")
        except Exception:
            hover_time = "--:--:--"

        candidates = []
        for tok, s in self.stock_series.items():
            if not s["visible"] or not s["x"]:
                continue
            if self.highlighted_token and tok != self.highlighted_token:
                continue

            idx = np.searchsorted(s["x"], x_val)
            if idx >= len(s["x"]):
                idx = len(s["x"]) - 1
            elif idx > 0 and abs(s["x"][idx - 1] - x_val) < abs(s["x"][idx] - x_val):
                idx = idx - 1

            pct = s["y"][idx] if idx < len(s["y"]) else 0.0
            dist = abs(pct - y_val)
            candidates.append((dist, pct, s))

        if not candidates:
            self.hud_label.setVisible(False)
            return

        candidates.sort(key=lambda item: item[0])

        hud_lines = [
            f"<div style='border-bottom: 1px solid #334155; padding-bottom: 3px; margin-bottom: 4px; font-size: 11px;'>"
            f"<b>TIME: {hover_time}</b> &nbsp;|&nbsp; Cursor: <b>{y_val:+.2f}%</b>"
            f"</div>"
        ]

        display_candidates = candidates[:4]
        for idx, (dist, pct, s) in enumerate(display_candidates):
            sign = "+" if pct >= 0 else ""
            color = "#10B981" if pct >= 0 else "#EF4444"
            ltp_val = s.get("last_ltp", 0.0)
            ltp_str = f" (Rs. {ltp_val:,.2f})" if ltp_val > 0 else ""

            if idx == 0:
                hud_lines.append(
                    f"<div style='font-size: 12px; font-weight: bold; margin: 2px 0;'>"
                    f"<span style='color:{s['color']};'>●</span> "
                    f"<span style='color: #F8FAFC;'>{s['symbol']}</span>: "
                    f"<span style='color:{color};'>{sign}{pct:.2f}%</span>"
                    f"<span style='color: #94A3B8; font-size: 10px;'>{ltp_str}</span>"
                    f"</div>"
                )
            else:
                hud_lines.append(
                    f"<div style='font-size: 10px; color: #CBD5E1; margin: 1px 0;'>"
                    f"&nbsp;&nbsp;<span style='color:{s['color']};'>■</span> "
                    f"{s['symbol']}: <span style='color:{color};'>{sign}{pct:.2f}%</span>"
                    f"</div>"
                )

        self.hud_label.setText("".join(hud_lines))
        self.hud_label.adjustSize()

        hud_w = self.hud_label.width()
        hud_h = self.hud_label.height()
        view_w = self.plot_widget.width()
        view_h = self.plot_widget.height()

        target_x = int(pos.x() + 15)
        if target_x + hud_w > view_w - 20:
            target_x = int(pos.x() - hud_w - 15)

        target_y = int(pos.y() + 15)
        if target_y + hud_h > view_h - 20:
            target_y = int(pos.y() - hud_h - 15)

        self.hud_label.move(max(10, target_x), max(10, target_y))
        self.hud_label.setVisible(True)
