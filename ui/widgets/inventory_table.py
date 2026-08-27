from typing import Optional
from PyQt6.QtWidgets import (
    QTableWidget, QWidget, QVBoxLayout, QLabel, QFrame
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
        self.title_lbl = QLabel("No Excel Database File Found")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f8fafc; background: transparent; border: none;"
        )
        card_layout.addWidget(self.title_lbl)

        # 3. Description / Guidance
        self.desc_lbl = QLabel("Place an Excel file (.xlsx) in the app directory and restart or press F5.")
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
            self.title_lbl.setText("No Excel Database File Found")
            self.desc_lbl.setText("Place an Excel (.xlsx) file in the app directory and press [F5] to reload.")


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
