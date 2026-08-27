from typing import Optional
from PyQt6.QtWidgets import (
    QTableWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QResizeEvent


class EmptyStateOverlay(QWidget):
    """Clean, centered placeholder shown when table has no data or no search matches."""

    addRequested = pyqtSignal()
    resetFilterRequested = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._is_filter_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Center card container
        self.card = QFrame()
        self.card.setObjectName("cardFrame")
        self.card.setStyleSheet(
            "QFrame#cardFrame {"
            "   background-color: rgba(30, 41, 59, 0.75);"
            "   border: 1px dashed rgba(56, 189, 248, 0.35);"
            "   border-radius: 12px;"
            "   padding: 24px 36px;"
            "   min-width: 440px;"
            "   max-width: 520px;"
            "}"
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(10)

        # 1. Icon badge
        self.icon_lbl = QLabel("📦")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size: 38px; background: transparent; border: none;")
        card_layout.addWidget(self.icon_lbl)

        # 2. Main Title
        self.title_lbl = QLabel("هنوز قطعه‌ای در انبار ثبت نشده است")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f1f5f9; background: transparent; border: none;"
        )
        card_layout.addWidget(self.title_lbl)

        # 3. Description / Guidance
        self.desc_lbl = QLabel("برای شروع مدیریت قطعات، اولین قطعه خود را به سیستم اضافه کنید.")
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none; max-width: 440px;"
        )
        card_layout.addWidget(self.desc_lbl)

        # 4. Action Button
        self.action_btn = QPushButton("ثبت قطعه جدید +")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setStyleSheet(
            "QPushButton {"
            "   background-color: #0284c7;"
            "   color: #ffffff;"
            "   font-size: 12px;"
            "   font-weight: 700;"
            "   padding: 8px 22px;"
            "   border-radius: 6px;"
            "   border: none;"
            "}"
            "QPushButton:hover {"
            "   background-color: #0369a1;"
            "}"
        )
        self.action_btn.clicked.connect(self._on_action_clicked)
        card_layout.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

    def set_state(self, is_filter_mode: bool):
        self._is_filter_mode = is_filter_mode
        if is_filter_mode:
            self.icon_lbl.setText("🔍")
            self.title_lbl.setText("قطعه‌ای با مشخصات مورد نظر یافت نشد")
            self.desc_lbl.setText("عبارت جستجو یا فیلترهای اعمال‌شده را تغییر دهید یا دکمه پاکسازی را بزنید.")
            self.action_btn.setText("پاکسازی فیلترها")
            self.action_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #334155;"
                "   color: #e2e8f0;"
                "   font-size: 12px;"
                "   font-weight: 600;"
                "   padding: 8px 20px;"
                "   border-radius: 6px;"
                "   border: 1px solid #475569;"
                "}"
                "QPushButton:hover {"
                "   background-color: #475569;"
                "}"
            )
        else:
            self.icon_lbl.setText("📦")
            self.title_lbl.setText("هنوز قطعه‌ای در انبار ثبت نشده است")
            self.desc_lbl.setText("برای شروع، کلید میانبر [Ctrl+N] را بزنید یا روی دکمه زیر کلیک کنید.")
            self.action_btn.setText("ثبت قطعه جدید +")
            self.action_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #0284c7;"
                "   color: #ffffff;"
                "   font-size: 12px;"
                "   font-weight: 700;"
                "   padding: 8px 22px;"
                "   border-radius: 6px;"
                "   border: none;"
                "}"
                "QPushButton:hover {"
                "   background-color: #0369a1;"
                "}"
            )

    def _on_action_clicked(self):
        if self._is_filter_mode:
            self.resetFilterRequested.emit()
        else:
            self.addRequested.emit()


class InventoryTableWidget(QTableWidget):
    """Custom table widget supporting keyboard navigation, expansion, and empty-state overlay."""

    rowActivateRequested = pyqtSignal(int)
    rowExpandRequested = pyqtSignal(int)
    rowDeselectRequested = pyqtSignal()
    addRequested = pyqtSignal()
    resetFilterRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._last_clicked_row = None
        self.empty_overlay = EmptyStateOverlay(self.viewport())
        self.empty_overlay.addRequested.connect(self.addRequested)
        self.empty_overlay.resetFilterRequested.connect(self.resetFilterRequested)
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

    def selectRow(self, row: int):
        """Safely select row across columns even when column 0 is hidden and RTL is active."""
        if 0 <= row < self.rowCount():
            target_col = 0
            for col in range(self.columnCount()):
                if not self.isColumnHidden(col) and self.item(row, col) is not None:
                    target_col = col
                    break
            self.setCurrentCell(row, target_col)

    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.pos())
        if item is None:
            self.clearSelection()
            self.setCurrentItem(None)
            self._last_clicked_row = None
            self.rowDeselectRequested.emit()
            event.accept()
            return

        clicked_row = item.row()
        selected_rows = [i.row() for i in self.selectedItems()]

        if clicked_row in selected_rows and self._last_clicked_row == clicked_row:
            self.rowExpandRequested.emit(clicked_row)

        self._last_clicked_row = clicked_row
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            selected = self.selectedItems()
            if selected:
                row = selected[0].row()
                self.rowActivateRequested.emit(row)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            self.setCurrentItem(None)
            self.rowDeselectRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
