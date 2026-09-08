from typing import Optional
from PyQt6.QtWidgets import (
    QTableWidget, QWidget, QVBoxLayout, QLabel, QFrame, QLineEdit, QStyledItemDelegate
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent


class EmptyStateOverlay(QWidget):
    """Clean, centered placeholder shown when table has no data or no search matches."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._is_filter_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)

        # Center card container
        self.card = QFrame()
        self.card.setObjectName("emptyStateCard")
        self.card.setMinimumWidth(480)
        self.card.setMaximumWidth(580)
        self.card.setStyleSheet(
            "QFrame#emptyStateCard {"
            "   background-color: rgba(15, 23, 42, 0.95);"
            "   border: 1px dashed rgba(56, 189, 248, 0.40);"
            "   border-radius: 12px;"
            "}"
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(8)

        # 1. Icon badge
        self.icon_lbl = QLabel("📊")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size: 40px; background: transparent; border: none;")
        card_layout.addWidget(self.icon_lbl)
        card_layout.addSpacing(4)

        # 2. Main Title
        self.title_lbl = QLabel("Inventory.xlsx Database Not Found")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f8fafc; background: transparent; border: none;"
        )
        card_layout.addWidget(self.title_lbl)

        # 3. Description / Guidance
        self.desc_lbl = QLabel("Please place 'Inventory.xlsx' in the application directory and press [F5] to reload.")
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none;"
        )
        card_layout.addWidget(self.desc_lbl)

        layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

    def set_state(self, is_filter_mode: bool):
        self._is_filter_mode = is_filter_mode
        if is_filter_mode:
            self.icon_lbl.setText("🔍")
            self.title_lbl.setText("No Matching Records Found")
            self.desc_lbl.setText("Try adjusting your search keywords or press [Esc] to clear.")
        else:
            self.icon_lbl.setText("📊")
            self.title_lbl.setText("Inventory.xlsx Database Not Found")
            self.desc_lbl.setText("Please place 'Inventory.xlsx' in the application directory and press [F5] to reload.")


class InventoryTableWidget(QTableWidget):
    """Dynamic table widget supporting sorting and empty state overlay."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.empty_overlay = EmptyStateOverlay(self.viewport())
        self.empty_overlay.hide()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.empty_overlay.setGeometry(0, 0, self.viewport().width(), self.viewport().height())

    def update_empty_state(self, is_empty: bool, is_filter_active: bool = False):
        """Show or hide the empty state placeholder overlay."""
        if is_empty:
            self.empty_overlay.set_state(is_filter_active)
            self.empty_overlay.setGeometry(0, 0, self.viewport().width(), self.viewport().height())
            self.empty_overlay.show()
        else:
            self.empty_overlay.hide()


class StockCellDelegate(QStyledItemDelegate):
    """
    Custom delegate for editable numeric cells (Min Stock & Target Stock).
    Provides a spacious, centered editor with comfortable height and rounded borders.
    """
    def createEditor(self, parent: QWidget, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setStyleSheet("""
            QLineEdit {
                background-color: #0c182e;
                color: #38bdf8;
                border: 2px solid #38bdf8;
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 13px;
                font-weight: bold;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
        """)
        return editor

    def updateEditorGeometry(self, editor: QWidget, option, index):
        rect = option.rect
        h = min(30, rect.height() - 4)
        y = rect.y() + (rect.height() - h) // 2
        w = rect.width() - 8
        x = rect.x() + 4
        editor.setGeometry(x, y, w, h)

