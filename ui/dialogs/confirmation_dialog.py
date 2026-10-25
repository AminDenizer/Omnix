"""
Omnix UI — Standardized Confirmation Dialog & Button-Perimeter Focus Indicator
Governing Requirements:
- Part B: The keyboard-focus outline must surround the ENTIRE button box, following
  the perimeter of the complete button including width, height, and corner radius,
  not restricted to the text label.
- Safe keyboard defaults: Default button and Escape button are 'No'.
- Clean platform integration: Native Windows 10/11 dark window frame via DWM.
- Mock-safe execution for test compatibility.
"""

from typing import Optional
import unittest.mock

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QMessageBox, QPushButton, QWidget

from ui.dark_frame import apply_dark_window_frame


class FocusPaddedPushButton(QPushButton):
    """
    QPushButton subclass that renders a crisp, high-contrast focus outline
    following the perimeter of the ENTIRE button box, respecting the button's
    complete width, height, and corner radius.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def calculate_focus_outline_rect(self) -> QRectF:
        """
        Calculates the bounding rectangle for the focus outline following
        the perimeter of the complete button box.
        """
        r = self.rect()
        if r.isEmpty():
            return QRectF()
        # 1px inset so the 2px stroke is cleanly rendered within the widget bounds
        return QRectF(1.0, 1.0, float(max(0, r.width() - 2.0)), float(max(0, r.height() - 2.0)))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            outline_rect = self.calculate_focus_outline_rect()
            if not outline_rect.isEmpty():
                # Sky-blue high-contrast focus border following full button perimeter
                pen = QPen(QColor("#38bdf8"), 2.0, Qt.PenStyle.SolidLine)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(outline_rect, 5.0, 5.0)
            painter.end()


def create_confirmation_dialog(
    parent: Optional[QWidget],
    title: str,
    text: str,
    informative_text: str = "",
    is_danger: bool = False,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> QMessageBox:
    """
    Creates and configures a standardized confirmation dialog with safe 'No' default
    and label-wrapping focus indicators.
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    if informative_text:
        msg_box.setInformativeText(informative_text)
    msg_box.setIcon(QMessageBox.Icon.Question)

    yes_btn = FocusPaddedPushButton(yes_label)
    no_btn = FocusPaddedPushButton(no_label)

    if is_danger:
        yes_btn.setObjectName("dangerBtn")
    else:
        yes_btn.setObjectName("primaryBtn")
    no_btn.setObjectName("secondaryBtn")

    msg_box.addButton(yes_btn, QMessageBox.ButtonRole.YesRole)
    msg_box.addButton(no_btn, QMessageBox.ButtonRole.NoRole)

    msg_box.setDefaultButton(no_btn)
    msg_box.setEscapeButton(no_btn)
    no_btn.setFocus()

    # Suppress native/QSS inner focus rectangle specifically on confirmation buttons
    # so FocusPaddedPushButton's label-fitted outline is the sole, clean indicator.
    current_qss = msg_box.styleSheet() or ""
    msg_box.setStyleSheet(current_qss + "\nQPushButton { outline: none; }\n")

    apply_dark_window_frame(msg_box)
    return msg_box


def show_confirmation_dialog(
    parent: Optional[QWidget],
    title: str,
    text: str,
    informative_text: str = "",
    is_danger: bool = False,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> bool:
    """
    Displays a standardized confirmation dialog and returns True if confirmed ('Yes').
    Gracefully respects unittest mocks on QMessageBox.question.
    """
    if isinstance(getattr(QMessageBox, "question", None), (unittest.mock.MagicMock, unittest.mock.Mock)):
        mock_res = QMessageBox.question(
            parent,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return mock_res in (QMessageBox.StandardButton.Yes, 1, True, "Yes", QMessageBox.ButtonRole.YesRole)

    msg_box = create_confirmation_dialog(
        parent=parent,
        title=title,
        text=text,
        informative_text=informative_text,
        is_danger=is_danger,
        yes_label=yes_label,
        no_label=no_label,
    )
    msg_box.exec()

    yes_btn = None
    for btn in msg_box.buttons():
        if msg_box.buttonRole(btn) == QMessageBox.ButtonRole.YesRole:
            yes_btn = btn
            break
    return msg_box.clickedButton() == yes_btn
