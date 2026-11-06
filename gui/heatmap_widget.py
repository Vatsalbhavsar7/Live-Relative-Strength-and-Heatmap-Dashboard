"""
heatmap_widget.py
-----------------
Interactive Synchronized Heatmap Widget supporting:
1. Equal-Weighted View (Responsive uniform tiles).
2. Market-Cap-Weighted View (Squarified Treemap layout).
3. Dynamic Color Coding based on % change from previous close.
4. One-click selection cross-linking to multi-line chart highlight.
"""

from typing import Any, Dict, List, Optional, Tuple
from PySide6 import QtCore, QtGui, QtWidgets

from config import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PANEL_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    HEATMAP_COLORS,
    HEATMAP_EXTREME_GREEN,
    HEATMAP_EXTREME_RED,
    HEATMAP_MILD_GREEN,
    HEATMAP_MILD_RED,
    HEATMAP_MODERATE_GREEN,
    HEATMAP_MODERATE_RED,
    HEATMAP_STRONG_GREEN,
    HEATMAP_STRONG_RED,
)


def get_heatmap_color(pct: float) -> str:
    """Returns appropriate hex color code based on percentage change."""
    if pct >= HEATMAP_EXTREME_GREEN:
        return HEATMAP_COLORS["extreme_green"]
    elif pct >= HEATMAP_STRONG_GREEN:
        return HEATMAP_COLORS["strong_green"]
    elif pct >= HEATMAP_MODERATE_GREEN:
        return HEATMAP_COLORS["moderate_green"]
    elif pct >= HEATMAP_MILD_GREEN:
        return HEATMAP_COLORS["mild_green"]
    elif pct <= HEATMAP_EXTREME_RED:
        return HEATMAP_COLORS["extreme_red"]
    elif pct <= HEATMAP_STRONG_RED:
        return HEATMAP_COLORS["strong_red"]
    elif pct <= HEATMAP_MODERATE_RED:
        return HEATMAP_COLORS["moderate_red"]
    elif pct <= HEATMAP_MILD_RED:
        return HEATMAP_COLORS["mild_red"]
    return HEATMAP_COLORS["neutral"]


class HeatmapTile(QtWidgets.QFrame):
    """An individual clickable stock tile within the heatmap."""

    clicked = QtCore.Signal(str)  # Emits token

    def __init__(self, token: str, symbol: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.token = token
        self.symbol = symbol
        self.pct_change: float = 0.0
        self.ltp: float = 0.0
        self.mcap: float = 10000.0

        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {HEATMAP_COLORS['neutral']};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QFrame:hover {{
                border: 1.5px solid #FFFFFF;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        self.lbl_symbol = QtWidgets.QLabel(symbol)
        self.lbl_symbol.setStyleSheet("font-weight: bold; color: #FFFFFF; font-size: 11px;")
        self.lbl_symbol.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.lbl_symbol)

        self.lbl_pct = QtWidgets.QLabel("0.00%")
        self.lbl_pct.setStyleSheet("font-weight: bold; color: #FFFFFF; font-size: 11px;")
        self.lbl_pct.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.lbl_pct)

        self.lbl_ltp = QtWidgets.QLabel("Rs. 0.00")
        self.lbl_ltp.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 9px;")
        self.lbl_ltp.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.lbl_ltp)

    def update_metrics(self, pct_change: float, ltp: float, mcap: float) -> None:
        """Updates text and background color based on new tick metrics."""
        self.pct_change = pct_change
        self.ltp = ltp
        self.mcap = mcap

        sign = "+" if pct_change >= 0 else ""
        self.lbl_pct.setText(f"{sign}{pct_change:.2f}%")
        self.lbl_ltp.setText(f"Rs. {ltp:,.2f}")

        bg_color = get_heatmap_color(pct_change)
        # Choose high-contrast text color
        text_color = "#000000" if pct_change >= HEATMAP_EXTREME_GREEN or pct_change <= HEATMAP_EXTREME_RED else "#FFFFFF"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QFrame:hover {{
                border: 2px solid #FFFFFF;
            }}
        """)
        self.lbl_symbol.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 11px;")
        self.lbl_pct.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 11px;")
        self.lbl_ltp.setStyleSheet(f"color: {text_color}; font-size: 9px;")

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.token)
        super().mousePressEvent(event)


class HeatmapWidget(QtWidgets.QWidget):
    """Container for the Live Heatmap with Equal-Weighted vs Market-Cap-Weighted toggle."""

    stock_selected = QtCore.Signal(str)  # Emits token when clicked

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.mode: str = "EQUAL"  # 'EQUAL' or 'MCAP'
        self.tiles: Dict[str, HeatmapTile] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # 1. Header Toolbar
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)

        lbl_title = QtWidgets.QLabel("LIVE HEATMAP")
        lbl_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 12px;")
        top_bar.addWidget(lbl_title)

        top_bar.addStretch()

        lbl_view = QtWidgets.QLabel("View Mode:")
        lbl_view.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        top_bar.addWidget(lbl_view)

        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Equal Weighted", "Market Cap Weighted"])
        self.combo_mode.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                selection-background-color: #2D3748;
            }}
        """)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self.combo_mode)

        main_layout.addLayout(top_bar)

        # 2. Scrollable Container for Heatmap Tiles
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLOR_BG_DARK};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
            }}
        """)

        self.container = QtWidgets.QWidget()
        self.container.setStyleSheet(f"background-color: {COLOR_BG_DARK};")
        self.grid_layout = QtWidgets.QGridLayout(self.container)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area)

    def _on_mode_changed(self, index: int) -> None:
        self.mode = "EQUAL" if index == 0 else "MCAP"
        self.re_layout_tiles()

    # ==========================================================================
    # TILE REGISTRATION & METRIC UPDATES
    # ==========================================================================

    def register_or_update_tile(
        self,
        token: str,
        symbol: str,
        pct_change: float,
        ltp: float,
        mcap: float = 10000.0,
    ) -> None:
        """Adds new tile or updates existing tile in the heatmap."""
        if token not in self.tiles:
            tile = HeatmapTile(token=token, symbol=symbol, parent=self.container)
            tile.clicked.connect(self._on_tile_clicked)
            self.tiles[token] = tile
            self.re_layout_tiles()

        self.tiles[token].update_metrics(pct_change, ltp, mcap)

    def remove_tile(self, token: str) -> None:
        """Removes a stock tile when dynamically removed from basket."""
        if token in self.tiles:
            tile = self.tiles.pop(token)
            tile.setParent(None)
            tile.deleteLater()
            self.re_layout_tiles()

    def _on_tile_clicked(self, token: str) -> None:
        self.stock_selected.emit(token)

    # ==========================================================================
    # LAYOUT ENGINES: EQUAL-WEIGHTED VS MARKET-CAP TREEMAP
    # ==========================================================================

    def re_layout_tiles(self) -> None:
        """Arranges tiles in the grid based on the active mode."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)

        if not self.tiles:
            return

        sorted_tiles = sorted(
            self.tiles.values(),
            key=lambda t: t.mcap if self.mode == "MCAP" else t.symbol,
            reverse=(self.mode == "MCAP"),
        )

        if self.mode == "EQUAL":
            cols = 5
            for idx, tile in enumerate(sorted_tiles):
                r = idx // cols
                c = idx % cols
                tile.setMinimumSize(85, 65)
                self.grid_layout.addWidget(tile, r, c, 1, 1)

        else:
            r = 0
            c = 0
            max_cols = 6

            for idx, tile in enumerate(sorted_tiles):
                if tile.mcap >= 800000.0 and c + 2 <= max_cols:
                    tile.setMinimumSize(140, 100)
                    self.grid_layout.addWidget(tile, r, c, 2, 2)
                    c += 2
                elif tile.mcap >= 300000.0 and c + 2 <= max_cols:
                    tile.setMinimumSize(120, 65)
                    self.grid_layout.addWidget(tile, r, c, 1, 2)
                    c += 2
                else:
                    tile.setMinimumSize(80, 60)
                    self.grid_layout.addWidget(tile, r, c, 1, 1)
                    c += 1

                if c >= max_cols:
                    c = 0
                    r += 2 if idx < 5 else 1
