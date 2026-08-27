from PyQt6.QtWidgets import QSpinBox, QComboBox, QPlainTextEdit, QWidget
from PyQt6.QtGui import QWheelEvent, QPainter, QColor, QFont
from PyQt6.QtCore import Qt


def auto_detect_text_direction(widget: QWidget, text: str):
    """
    Auto-detect text direction based on character script.
    Applies RTL for Persian/Arabic characters and LTR for English/ASCII characters.
    """
    clean = text.strip()
    if not clean:
        widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        return

    for ch in clean:
        if ('\u0600' <= ch <= '\u06FF') or ('\uFB50' <= ch <= '\uFDFF') or ('\uFE70' <= ch <= '\uFEFF'):
            widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            return
        elif ch.isalpha() and ch.isascii():
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            return


class SmoothSpinBox(QSpinBox):
    """
    SpinBox that ignores mouse wheel events to prevent accidental
    value changes while scrolling through a form viewport.
    """
    def wheelEvent(self, event: QWheelEvent):
        event.ignore()


class SmoothComboBox(QComboBox):
    """
    ComboBox that ignores scroll wheel events when its drop-down list is closed,
    preventing unintended option changes during page scrolling.
    """
    def wheelEvent(self, event: QWheelEvent):
        if not self.view().isVisible():
            event.ignore()
        else:
            super().wheelEvent(event)


class DescriptionPlainTextEdit(QPlainTextEdit):
    """
    Multi-line plain text editor with custom placeholder text rendering
    and clean styling integration.
    """
    def __init__(self, placeholder: str = "درصد خطا، ولتاژ کاری، شرکت سازنده یا یادداشت‌های فنی...", parent: QWidget = None):
        super().__init__(parent)
        self.custom_placeholder = placeholder
        self.document().setDocumentMargin(8)
        self.setFont(QFont("Segoe UI", 10))

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.toPlainText().strip():
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QColor("#64748b"))
            p.setFont(self.font())
            rect = self.viewport().rect().adjusted(10, 8, -10, -8)
            p.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self.custom_placeholder)
            p.end()
