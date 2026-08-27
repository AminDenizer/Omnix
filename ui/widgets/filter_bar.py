from typing import Optional
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent


class SearchLineEdit(QLineEdit):
    """Search line edit supporting keyboard navigation."""

    downPressed = pyqtSignal()
    enterPressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enterPressed.emit()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Down:
            self.downPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class FilterBarWidget(QFrame):
    """Clean full-width search bar for instant table filtering."""

    searchChanged = pyqtSignal(str)
    enterPressed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        filter_layout = QHBoxLayout(self)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(0)

        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("Search across all columns, part numbers, values, footprints, links... (Press / to focus, Esc to deselect/clear)")
        self.search_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.search_input.textChanged.connect(self.searchChanged.emit)
        self.search_input.returnPressed.connect(self.enterPressed.emit)
        self.search_input.enterPressed.connect(self.enterPressed.emit)
        self.search_input.downPressed.connect(self.enterPressed.emit)

        filter_layout.addWidget(self.search_input)
