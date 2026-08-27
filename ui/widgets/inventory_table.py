from typing import Optional
from PyQt6.QtWidgets import QTableWidget, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QKeyEvent


class InventoryTableWidget(QTableWidget):
    """Custom table widget supporting keyboard navigation, expansion, and background deselection."""

    rowExpandRequested = pyqtSignal(int)
    rowDeselectRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._last_clicked_row = None

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
                self.rowExpandRequested.emit(row)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            self.setCurrentItem(None)
            self.rowDeselectRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
