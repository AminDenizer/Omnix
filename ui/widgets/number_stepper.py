"""
Omnix UI — Dedicated Number Stepper Widget
Extracted from bom_audit_widget to break circular import dependencies.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class NumberStepperWidget(QWidget):
    """
    Modern counter with external dedicated minus/plus buttons and centered numeric input.
    """
    valueChanged = pyqtSignal(int)

    def __init__(self, value: int = 1, min_val: int = 1, max_val: int = 100000, parent=None):
        super().__init__(parent)
        self._val = value
        self.min_val = min_val
        self.max_val = max_val
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #f8fafc;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                border-color: #38bdf8;
                color: #0f172a;
            }
            QPushButton:pressed {
                background-color: #0284c7;
                color: #ffffff;
            }
        """

        # Minus button [-]
        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedSize(34, 32)
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.setAutoRepeat(True)
        self.btn_minus.setAutoRepeatDelay(350)
        self.btn_minus.setAutoRepeatInterval(80)
        self.btn_minus.setStyleSheet(btn_style)
        self.btn_minus.clicked.connect(self._step_down)
        layout.addWidget(self.btn_minus)

        # Number Entry Input
        self.input_field = QLineEdit(str(self._val))
        self.input_field.setFixedSize(56, 32)
        self.input_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_field.setValidator(QIntValidator(self.min_val, self.max_val, self))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 13px;
                font-weight: bold;
                padding: 2px;
            }
            QLineEdit:focus {
                border: 1.5px solid #38bdf8;
                background-color: #0f172a;
            }
        """)
        self.input_field.textChanged.connect(self._on_text_changed)
        self.input_field.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.input_field)

        # Plus button [+]
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(34, 32)
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.setAutoRepeat(True)
        self.btn_plus.setAutoRepeatDelay(350)
        self.btn_plus.setAutoRepeatInterval(80)
        self.btn_plus.setStyleSheet(btn_style)
        self.btn_plus.clicked.connect(self._step_up)
        layout.addWidget(self.btn_plus)

    def _step_down(self):
        new_val = max(self.min_val, self._val - 1)
        self.setValue(new_val)

    def _step_up(self):
        new_val = min(self.max_val, self._val + 1)
        self.setValue(new_val)

    def _on_text_changed(self, text: str):
        if text.strip().isdigit():
            v = int(text.strip())
            if self.min_val <= v <= self.max_val:
                self._val = v
                self.valueChanged.emit(v)

    def _on_editing_finished(self):
        text = self.input_field.text().strip()
        if not text.isdigit() or int(text) < self.min_val:
            self.setValue(self.min_val)
        elif int(text) > self.max_val:
            self.setValue(self.max_val)
        else:
            self.setValue(int(text))

    def value(self) -> int:
        return self._val

    def setValue(self, val: int):
        val = max(self.min_val, min(val, self.max_val))
        if self._val != val or self.input_field.text() != str(val):
            self._val = val
            self.input_field.setText(str(val))
            self.valueChanged.emit(val)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self._step_up()
        else:
            self._step_down()
        event.accept()

    def setRange(self, min_val: int, max_val: int):
        self.min_val = min_val
        self.max_val = max_val
        self.input_field.setValidator(QIntValidator(min_val, max_val, self))
        self.setValue(self._val)
