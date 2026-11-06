"""
token_manager_dialog.py
-----------------------
Dialog enabling the trader to dynamically add or remove any stock from the basket
without restarting the application or collector daemon.
"""

from typing import Any, Dict, Optional
from PySide6 import QtCore, QtGui, QtWidgets

from basket_manager import BasketManager
from config import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    COLOR_PANEL_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)
from db_manager import DatabaseManager


class TokenManagerDialog(QtWidgets.QDialog):
    """Modal dialog to search, preview, add, and remove basket instruments."""

    token_added = QtCore.Signal(dict)    # Emits resolved token info
    token_removed = QtCore.Signal(str)   # Emits token string

    def __init__(self, db: DatabaseManager, basket_mgr: BasketManager, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.basket_mgr = basket_mgr
        self.resolved_candidate: Optional[Dict[str, Any]] = None

        self.setWindowTitle("Manage Tracking Basket (Dynamic Hot-Reload)")
        self.setMinimumSize(540, 480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        self._init_ui()
        self.refresh_table()

    def _init_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header
        lbl_header = QtWidgets.QLabel("Add / Remove Tracking Instruments (Zero-Restart)")
        lbl_header.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(lbl_header)

        lbl_desc = QtWidgets.QLabel("Add any stock by Symbol or Token. The collector daemon and charts will hot-subscribe instantly.")
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(lbl_desc)

        # 2. Search & Add Box
        search_box = QtWidgets.QHBoxLayout()
        self.inp_search = QtWidgets.QLineEdit()
        self.inp_search.setPlaceholderText("Enter Symbol or Token (e.g. IDEA, TATAMOTORS, 14366)...")
        self.inp_search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
        """)
        self.inp_search.returnPressed.connect(self._on_search)
        search_box.addWidget(self.inp_search)

        self.btn_search = QtWidgets.QPushButton("Lookup")
        self.btn_search.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #1D4ED8;
            }}
        """)
        self.btn_search.clicked.connect(self._on_search)
        search_box.addWidget(self.btn_search)

        layout.addLayout(search_box)

        # 3. Preview Card
        self.preview_card = QtWidgets.QFrame()
        self.preview_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_PANEL_DARK};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        self.preview_card.setVisible(False)
        prev_layout = QtWidgets.QHBoxLayout(self.preview_card)

        self.lbl_preview_info = QtWidgets.QLabel()
        self.lbl_preview_info.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        prev_layout.addWidget(self.lbl_preview_info)

        prev_layout.addStretch()

        self.btn_confirm_add = QtWidgets.QPushButton("+ Add to Basket")
        self.btn_confirm_add.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_confirm_add.clicked.connect(self._on_confirm_add)
        prev_layout.addWidget(self.btn_confirm_add)

        layout.addWidget(self.preview_card)

        # 4. Currently Tracked Table
        lbl_active = QtWidgets.QLabel("Currently Tracked Instruments:")
        lbl_active.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(lbl_active)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Token", "Symbol", "Exchange", "Prev Close", "Action"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                gridline-color: {COLOR_BORDER};
            }}
            QHeaderView::section {{
                background-color: #0F172A;
                color: {COLOR_TEXT_SECONDARY};
                font-weight: bold;
                border: none;
                padding: 4px;
            }}
        """)
        layout.addWidget(self.table)

        # Close button
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PANEL_DARK};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 6px 16px;
                align-self: flex-end;
            }}
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=QtCore.Qt.AlignRight)

    def _on_search(self) -> None:
        query = self.inp_search.text().strip()
        if not query:
            return

        res = self.basket_mgr.resolve_instrument(query)
        if res:
            self.resolved_candidate = res
            self.lbl_preview_info.setText(
                f"<b>{res['symbol']}</b> (Token: {res['token']}) | Exch: {res['exchange']} | "
                f"Prev Close: Rs. {res['prev_close']:,.2f}"
            )
            self.preview_card.setVisible(True)
        else:
            QtWidgets.QMessageBox.warning(self, "Not Found", f"Could not resolve instrument '{query}'. Check spelling or token ID.")
            self.preview_card.setVisible(False)

    def _on_confirm_add(self) -> None:
        if not self.resolved_candidate:
            return

        ok = self.db.add_token_dynamically(self.resolved_candidate)
        if ok:
            self.token_added.emit(self.resolved_candidate)
            self.preview_card.setVisible(False)
            self.inp_search.clear()
            self.refresh_table()
        else:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to add token to database.")

    def refresh_table(self) -> None:
        """Reloads active tokens list from MySQL."""
        active = self.db.get_active_basket_tokens()
        self.table.setRowCount(len(active))

        for row_idx, (tok, m) in enumerate(active.items()):
            self.table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(str(m["token"])))
            self.table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(str(m["symbol"])))
            self.table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(str(m.get("exchange", "NSE"))))
            self.table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(f"Rs. {float(m.get('prev_close', 0)):,.2f}"))

            btn_del = QtWidgets.QPushButton("Remove")
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: #FFFFFF;
                    font-size: 10px;
                    font-weight: bold;
                    border: none;
                    border-radius: 3px;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
            btn_del.clicked.connect(lambda _, t=tok: self._on_remove(t))
            self.table.setCellWidget(row_idx, 4, btn_del)

    def _on_remove(self, token: str) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove token {token} from active tracking?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            if self.db.remove_token_dynamically(token):
                self.token_removed.emit(token)
                self.refresh_table()
