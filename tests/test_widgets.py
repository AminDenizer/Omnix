import pytest
from PyQt6.QtWidgets import QLineEdit, QWidget
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent
from ui.widgets import (
    SmoothSpinBox,
    SmoothComboBox,
    DescriptionPlainTextEdit,
    auto_detect_text_direction
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
