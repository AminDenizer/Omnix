import pytest
from PyQt6.QtWidgets import QLineEdit, QWidget, QTableWidgetItem
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent, QKeyEvent
from models import Component
from ui.widgets import (
    SmoothSpinBox,
    SmoothComboBox,
    DescriptionPlainTextEdit,
    auto_detect_text_direction,
    DrawerChipsWidget,
    InventoryTableWidget
)


class TestCustomWidgets:
    """Test suite for custom input controls and UI helpers."""

    def test_auto_detect_text_direction_persian(self, qapp):
        widget = QLineEdit()
        auto_detect_text_direction(widget, "مقاومت اس ام دی")
        assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft

    def test_auto_detect_text_direction_english(self, qapp):
        widget = QLineEdit()
        auto_detect_text_direction(widget, "Resistor 10k")
        assert widget.layoutDirection() == Qt.LayoutDirection.LeftToRight

    def test_auto_detect_text_direction_empty(self, qapp):
        widget = QLineEdit()
        auto_detect_text_direction(widget, "   ")
        assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft

    def test_smooth_spinbox_wheel_event_ignored(self, qapp):
        spin = SmoothSpinBox()
        spin.setValue(50)
        
        # Simulate mouse wheel event
        event = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        spin.wheelEvent(event)
        # Value must remain untouched because wheelEvent is ignored
        assert spin.value() == 50

    def test_smooth_combobox_initialization(self, qapp):
        combo = SmoothComboBox()
        combo.addItems(["Item 1", "Item 2", "Item 3"])
        assert combo.count() == 3
        assert combo.currentIndex() == 0

    def test_description_plaintext_edit(self, qapp):
        edit = DescriptionPlainTextEdit(placeholder="یادداشت تست")
        assert edit.custom_placeholder == "یادداشت تست"
        assert edit.toPlainText() == ""

    def test_drawer_chips_widget_rendering(self, qapp):
        comp = Component(quantity=60, min_alert=10, drawers="1:20, 2:20, 3:20, 4:0")
        clicked_drawers = []
        expanded_calls = []

        chips_w = DrawerChipsWidget(
            component=comp,
            on_click_filter=lambda d: clicked_drawers.append(d),
            on_toggle_expand=lambda: expanded_calls.append(True)
        )
        assert chips_w is not None
        assert chips_w.is_expanded is False

        # Test expand rebuild
        chips_w.rebuild(expanded=True)
        assert chips_w.is_expanded is True

    def test_inventory_table_widget_keyboard_navigation(self, qapp):
        table = InventoryTableWidget()
        table.setRowCount(2)
        table.setColumnCount(2)
        table.setItem(0, 0, QTableWidgetItem("Item 1"))
        table.selectRow(0)

        expanded_rows = []
        table.rowExpandRequested.connect(lambda r: expanded_rows.append(r))

        # Simulate Enter key press
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        table.keyPressEvent(key_event)
        assert len(expanded_rows) == 1
        assert expanded_rows[0] == 0
