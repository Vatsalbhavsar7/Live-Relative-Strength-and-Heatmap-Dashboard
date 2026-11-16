"""
filter_panel.py
---------------
Sidebar panel providing interactive stock filters, checkbox visibility toggles,
and quick presets (Top 5 Bullish, Top 5 Bearish, Show/Hide All, Active Spikers).
"""

from typing import Any, Dict, List, Optional
from PySide6 import QtCore, QtGui, QtWidgets

from config import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PANEL_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)


class StockFilterItem(QtWidgets.QWidget):
    """Row item in the filter list with color swatch, checkbox, % change, and remove button."""

    visibility_changed = QtCore.Signal(str, bool)  # token, is_visible
    remove_clicked = QtCore.Signal(str)           # token
    hover_entered = QtCore.Signal(str)            # token
    hover_left = QtCore.Signal(str)               # token

    def __init__(self, token: str, symbol: str, color_hex: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.token = token
        self.symbol = symbol
        self.color_hex = color_hex
        self.pct_change: float = 0.0
        self.ltp: float = 0.0
        self.initial_index: int = 0

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Color indicator swatch
        self.swatch = QtWidgets.QLabel()
        self.swatch.setFixedSize(10, 10)
        self.swatch.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px;")
        layout.addWidget(self.swatch)

        # Checkbox
        self.chk = QtWidgets.QCheckBox(symbol)
        self.chk.setChecked(True)
        self.chk.setStyleSheet(f"""
            QCheckBox {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 500;
            }}
            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
            }}
        """)
        self.chk.toggled.connect(lambda checked: self.visibility_changed.emit(self.token, checked))
        layout.addWidget(self.chk)

        # Surge indicator tag (e.g. ⚡ +0.55%)
        self.lbl_surge = QtWidgets.QLabel()
        self.lbl_surge.setVisible(False)
        layout.addWidget(self.lbl_surge)

        layout.addStretch()

        # Live LTP Badge
        self.lbl_ltp = QtWidgets.QLabel("₹ 0.00")
        self.lbl_ltp.setStyleSheet("color: #94A3B8; font-size: 10px; font-family: monospace; font-weight: 500;")
        layout.addWidget(self.lbl_ltp)

        # % Change Badge
        self.lbl_pct = QtWidgets.QLabel("0.00%")
        self.lbl_pct.setFixedWidth(54)
        self.lbl_pct.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.lbl_pct.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; font-weight: bold; font-family: monospace;")
        layout.addWidget(self.lbl_pct)

        # Remove 'X' Button
        self.btn_del = QtWidgets.QPushButton("×")
        self.btn_del.setFixedSize(16, 16)
        self.btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #EF4444;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #7F1D1D;
                border-radius: 8px;
            }
        """)
        self.btn_del.setToolTip(f"Remove {symbol} from active basket")
        self.btn_del.clicked.connect(lambda: self.remove_clicked.emit(self.token))
        layout.addWidget(self.btn_del)

    def update_pct(self, pct: float, ltp: float = 0.0, prev_close: float = 0.0) -> None:
        self.pct_change = pct
        self.ltp = ltp
        sign = "+" if pct >= 0 else ""
        color = "#10B981" if pct >= 0 else "#EF4444"
        display_px = ltp if ltp > 0 else prev_close
        if display_px > 0:
            self.lbl_ltp.setText(f"₹ {display_px:,.2f}")
        self.lbl_pct.setText(f"{sign}{pct:.2f}%")
        self.lbl_pct.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold; font-family: monospace;")
        if display_px > 0:
            self.setToolTip(f"{self.symbol}\nLTP: ₹ {display_px:,.2f}\nPrev Close: ₹ {prev_close:,.2f}\nChange: {sign}{pct:.2f}%")

    def set_surge(self, velocity: Optional[float], window_min: int = 2) -> None:
        """Displays or hides real-time momentum velocity indicator tag."""
        if velocity is not None and abs(velocity) > 0:
            color = "#10B981" if velocity >= 0 else "#EF4444"
            icon = "⚡" if velocity >= 0 else "🔻"
            self.lbl_surge.setText(f"{icon} {velocity:+.2f}%")
            self.lbl_surge.setStyleSheet(f"""
                color: {color};
                background-color: #1E293B;
                border: 1px solid {color}88;
                border-radius: 3px;
                padding: 1px 3px;
                font-size: 9px;
                font-weight: bold;
            """)
            self.lbl_surge.setToolTip(f"Sudden momentum move: {velocity:+.2f}% in last {window_min} minutes")
            self.lbl_surge.setVisible(True)
        else:
            self.lbl_surge.setVisible(False)

    def set_visible_checked(self, visible: bool) -> None:
        self.chk.blockSignals(True)
        self.chk.setChecked(visible)
        self.chk.blockSignals(False)
        self.visibility_changed.emit(self.token, visible)

    def enterEvent(self, event) -> None:
        """Emits hover signal and highlights the watchlist row."""
        self.setStyleSheet("background-color: #1E293B; border-radius: 4px;")
        self.hover_entered.emit(self.token)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Emits unhover signal and clears row highlight."""
        self.setStyleSheet("")
        self.hover_left.emit(self.token)
        super().leaveEvent(event)


class FilterPanel(QtWidgets.QWidget):
    """Panel managing all stock checkboxes, quick filters, and removals."""

    visibility_toggled = QtCore.Signal(str, bool)
    remove_token_requested = QtCore.Signal(str)
    bulk_filter_applied = QtCore.Signal()
    stock_hover_entered = QtCore.Signal(str)
    stock_hover_left = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.items: Dict[str, StockFilterItem] = {}
        self.default_order: Dict[str, int] = {}
        self._order_counter: int = 0
        self.current_surges: Dict[str, float] = {}
        self._init_ui()

        # Auto-sort timer: Automatically re-applies current sort order every 1.5 seconds
        self.auto_sort_timer = QtCore.QTimer(self)
        self.auto_sort_timer.setInterval(1500)
        self.auto_sort_timer.timeout.connect(self._on_auto_sort_tick)
        self.auto_sort_timer.start()

    def _init_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Title
        lbl_title = QtWidgets.QLabel("WATCHLIST & FILTERS")
        lbl_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 12px;")
        main_layout.addWidget(lbl_title)

        # Sort Controls (A-Z, % Change, Default)
        sort_container = QtWidgets.QHBoxLayout()
        sort_container.setSpacing(6)

        lbl_sort = QtWidgets.QLabel("Sort:")
        lbl_sort.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        sort_container.addWidget(lbl_sort)

        self.combo_sort = QtWidgets.QComboBox()
        self.combo_sort.addItems([
            "Default View",
            "A -> Z (Alphabetical)",
            "Z -> A (Reverse)",
            "% Change (High -> Low)",
            "% Change (Low -> High)",
            "LTP (High -> Low)",
            "LTP (Low -> High)",
        ])
        self.combo_sort.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
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
        self.combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        sort_container.addWidget(self.combo_sort, stretch=1)

        # Quick Re-sort Button
        self.btn_resort = QtWidgets.QPushButton("↻")
        self.btn_resort.setFixedSize(24, 24)
        self.btn_resort.setToolTip("Re-apply current sort order")
        self.btn_resort.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2D3748;
            }}
        """)
        self.btn_resort.clicked.connect(self.apply_sorting)
        sort_container.addWidget(self.btn_resort)

        main_layout.addLayout(sort_container)

        # Quick Filter Buttons Grid
        btn_layout = QtWidgets.QGridLayout()
        btn_layout.setSpacing(4)

        self.btn_all = QtWidgets.QPushButton("Show All")
        self.btn_none = QtWidgets.QPushButton("Hide All")
        self.btn_top_bulls = QtWidgets.QPushButton("Top 5 Bullish")
        self.btn_top_bears = QtWidgets.QPushButton("Top 5 Bearish")
        self.btn_top_both = QtWidgets.QPushButton("Top 5 Bulls & Bears Together")
        self.btn_spikers = QtWidgets.QPushButton("⚡ Active Spikers (0)")

        btn_style = f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2D3748;
            }}
        """
        for b in [self.btn_all, self.btn_none, self.btn_top_bulls, self.btn_top_bears, self.btn_top_both, self.btn_spikers]:
            b.setStyleSheet(btn_style)

        self.btn_top_both.setStyleSheet(f"""
            QPushButton {{
                background-color: #1E1B4B;
                color: #C7D2FE;
                border: 1px solid #4338CA;
                border-radius: 4px;
                padding: 5px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #312E81;
                color: #FFFFFF;
            }}
        """)

        self.btn_spikers.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #94A3B8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 5px 6px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)

        self.btn_all.clicked.connect(self.select_all)
        self.btn_none.clicked.connect(self.deselect_all)
        self.btn_top_bulls.clicked.connect(self.select_top_bulls)
        self.btn_top_bears.clicked.connect(self.select_top_bears)
        self.btn_top_both.clicked.connect(self.select_top_both)
        self.btn_spikers.clicked.connect(self.select_spikers)

        btn_layout.addWidget(self.btn_all, 0, 0)
        btn_layout.addWidget(self.btn_none, 0, 1)
        btn_layout.addWidget(self.btn_top_bulls, 1, 0)
        btn_layout.addWidget(self.btn_top_bears, 1, 1)
        btn_layout.addWidget(self.btn_top_both, 2, 0, 1, 2)
        btn_layout.addWidget(self.btn_spikers, 3, 0, 1, 2)

        main_layout.addLayout(btn_layout)

        # Scroll area for items
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLOR_BG_DARK};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
        """)

        self.list_container = QtWidgets.QWidget()
        self.list_container.setStyleSheet(f"background-color: {COLOR_BG_DARK};")
        self.list_layout = QtWidgets.QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        main_layout.addWidget(self.scroll)

    def add_or_update_stock(self, token: str, symbol: str, color_hex: str, pct: float = 0.0, ltp: float = 0.0, prev_close: float = 0.0) -> None:
        """Adds a new stock item to the filter list or updates its % badge."""
        if token not in self.items:
            item = StockFilterItem(token=token, symbol=symbol, color_hex=color_hex, parent=self.list_container)
            self._order_counter += 1
            item.initial_index = self._order_counter
            self.default_order[token] = self._order_counter
            item.visibility_changed.connect(self.visibility_toggled.emit)
            item.remove_clicked.connect(self.remove_token_requested.emit)
            item.hover_entered.connect(self.stock_hover_entered.emit)
            item.hover_left.connect(self.stock_hover_left.emit)
            self.items[token] = item
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)

        self.items[token].update_pct(pct, ltp=ltp, prev_close=prev_close)

    def remove_stock(self, token: str) -> None:
        """Removes a stock item from the filter list."""
        if token in self.items:
            item = self.items.pop(token)
            self.default_order.pop(token, None)
            self.list_layout.removeWidget(item)
            item.deleteLater()

    # ==========================================================================
    # SORTING METHODS (A-Z, % CHANGE, DEFAULT) & AUTO-REFRESH
    # ==========================================================================

    def _on_sort_changed(self, index: int) -> None:
        self.apply_sorting()

    def _on_auto_sort_tick(self) -> None:
        """Periodic auto-sort hook: re-applies current sort every 1.5s in real-time."""
        self.apply_sorting()

    def apply_sorting(self) -> None:
        """Sorts the watchlist items according to the selected mode without layout jitter."""
        mode = self.combo_sort.currentText()
        items_list = list(self.items.values())
        if not items_list:
            return

        if "A -> Z" in mode or "A → Z" in mode:
            items_list.sort(key=lambda x: x.symbol.upper())
        elif "Z -> A" in mode or "Z → A" in mode:
            items_list.sort(key=lambda x: x.symbol.upper(), reverse=True)
        elif "High -> Low" in mode or "High → Low" in mode:
            if "LTP" in mode:
                items_list.sort(key=lambda x: x.ltp, reverse=True)
            else:
                items_list.sort(key=lambda x: x.pct_change, reverse=True)
        elif "Low -> High" in mode or "Low → High" in mode:
            if "LTP" in mode:
                items_list.sort(key=lambda x: x.ltp, reverse=False)
            else:
                items_list.sort(key=lambda x: x.pct_change, reverse=False)
        else:
            items_list.sort(key=lambda x: getattr(x, "initial_index", 0))

        current_tokens = []
        for i in range(self.list_layout.count()):
            item_widget = self.list_layout.itemAt(i)
            if item_widget and item_widget.widget() and isinstance(item_widget.widget(), StockFilterItem):
                current_tokens.append(item_widget.widget().token)

        new_tokens = [item.token for item in items_list]
        if current_tokens == new_tokens:
            return

        for i, item in enumerate(items_list):
            self.list_layout.insertWidget(i, item)

    # ==========================================================================
    # QUICK FILTER ACTIONS
    # ==========================================================================

    def select_all(self) -> None:
        for item in self.items.values():
            item.set_visible_checked(True)
        self.bulk_filter_applied.emit()

    def deselect_all(self) -> None:
        for item in self.items.values():
            item.set_visible_checked(False)
        self.bulk_filter_applied.emit()

    def select_top_bulls(self) -> None:
        """Checks only the top 5 highest positive % change stocks."""
        sorted_items = sorted(self.items.values(), key=lambda x: x.pct_change, reverse=True)
        top_5_tokens = set(item.token for item in sorted_items[:5])
        for item in self.items.values():
            item.set_visible_checked(item.token in top_5_tokens)
        self.bulk_filter_applied.emit()

    def select_top_bears(self) -> None:
        """Checks only the top 5 lowest negative % change stocks."""
        sorted_items = sorted(self.items.values(), key=lambda x: x.pct_change, reverse=False)
        top_5_tokens = set(item.token for item in sorted_items[:5])
        for item in self.items.values():
            item.set_visible_checked(item.token in top_5_tokens)
        self.bulk_filter_applied.emit()

    def select_top_both(self) -> None:
        """Checks both Top 5 Bullish AND Top 5 Bearish stocks together (up to 10 stocks)."""
        sorted_bulls = sorted(self.items.values(), key=lambda x: x.pct_change, reverse=True)
        sorted_bears = sorted(self.items.values(), key=lambda x: x.pct_change, reverse=False)
        top_both_tokens = set(item.token for item in sorted_bulls[:5])
        top_both_tokens.update(item.token for item in sorted_bears[:5])
        for item in self.items.values():
            item.set_visible_checked(item.token in top_both_tokens)
        self.bulk_filter_applied.emit()

    def select_spikers(self) -> None:
        """Checks only stocks actively surging or dumping, hiding stagnant lines."""
        if not self.current_surges:
            return
        spiker_tokens = set(self.current_surges.keys())
        for item in self.items.values():
            item.set_visible_checked(item.token in spiker_tokens)
        self.bulk_filter_applied.emit()

    def update_surges(self, surges: Dict[str, float], window_min: int = 2) -> None:
        """Updates surge indicator tags and refreshes the spikers button count."""
        self.current_surges = surges
        count = len(surges)
        self.btn_spikers.setText(f"⚡ Active Spikers ({count})")

        if count > 0:
            self.btn_spikers.setStyleSheet("""
                QPushButton {
                    background-color: #78350F;
                    color: #FDE68A;
                    border: 1px solid #F59E0B;
                    border-radius: 4px;
                    padding: 5px 6px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #B45309;
                    color: #FFFFFF;
                }
            """)
        else:
            self.btn_spikers.setStyleSheet("""
                QPushButton {
                    background-color: #1E293B;
                    color: #94A3B8;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 5px 6px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #334155;
                }
            """)

        for tok, item in self.items.items():
            vel = surges.get(tok)
            item.set_surge(vel, window_min=window_min)
