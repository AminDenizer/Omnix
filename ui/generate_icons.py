import os
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush,
    QPainterPath, QLinearGradient, QRadialGradient
)
from PyQt6.QtCore import Qt, QRectF, QPointF

ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")


def generate_arrows():
    """Generate modern vector icons for UI form controls (SpinBox, ComboBox, CheckBox, RadioButton, Logo)."""
    os.makedirs(ICONS_DIR, exist_ok=True)

    color_normal = QColor("#94a3b8")
    color_active = QColor("#38bdf8")
    color_white = QColor("#ffffff")

    def draw_chevron_up(color: QColor, filename: str):
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(4, 9, 8, 5)
        p.drawLine(8, 5, 12, 9)
        p.end()
        pix.save(os.path.join(ICONS_DIR, filename))

    def draw_chevron_down(color: QColor, filename: str):
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(4, 7, 8, 11)
        p.drawLine(8, 11, 12, 7)
        p.end()
        pix.save(os.path.join(ICONS_DIR, filename))

    def draw_checkmark(filename: str):
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color_white, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(3, 8, 6, 12)
        p.drawLine(6, 12, 13, 4)
        p.end()
        pix.save(os.path.join(ICONS_DIR, filename))

    def draw_radio(fname, border_col, bg_col, dot_col=None):
        pix = QPixmap(18, 18)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.5, 1.5, 15, 15)
        p.setPen(QPen(QColor(border_col), 1.5))
        p.setBrush(QBrush(QColor(bg_col)))
        p.drawEllipse(rect)
        if dot_col:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(dot_col)))
            p.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
        p.end()
        pix.save(os.path.join(ICONS_DIR, fname))

    def draw_logo(size: int = 128, filename: str = "app_logo.png"):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = size / 128.0

        # 1. Metallic IC pins
        pin_pen = QPen(QColor('#64748b'), 3.0 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pin_pen)
        for py in [38, 54, 70, 86]:
            p.drawLine(QPointF(10 * scale, py * scale), QPointF(24 * scale, py * scale))
            p.drawLine(QPointF(104 * scale, py * scale), QPointF(118 * scale, py * scale))
        for px in [42, 64, 86]:
            p.drawLine(QPointF(px * scale, 10 * scale), QPointF(px * scale, 24 * scale))
            p.drawLine(QPointF(px * scale, 104 * scale), QPointF(px * scale, 118 * scale))

        # 2. Main IC silicon chip body
        grad = QLinearGradient(20 * scale, 20 * scale, 108 * scale, 108 * scale)
        grad.setColorAt(0.0, QColor('#0f172a'))
        grad.setColorAt(1.0, QColor('#021a36'))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor('#0284c7'), 2.5 * scale))
        p.drawRoundedRect(QRectF(22 * scale, 22 * scale, 84 * scale, 84 * scale), 12 * scale, 12 * scale)

        # 3. Cyan PCB traces
        track_pen = QPen(QColor('#38bdf8'), 1.8 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.drawLine(QPointF(34 * scale, 40 * scale), QPointF(52 * scale, 40 * scale))
        p.drawLine(QPointF(52 * scale, 40 * scale), QPointF(64 * scale, 52 * scale))
        p.drawLine(QPointF(94 * scale, 88 * scale), QPointF(76 * scale, 88 * scale))
        p.drawLine(QPointF(76 * scale, 88 * scale), QPointF(64 * scale, 76 * scale))

        # 4. Glowing central microchip core
        core_grad = QRadialGradient(64 * scale, 64 * scale, 20 * scale)
        core_grad.setColorAt(0.0, QColor('#38bdf8'))
        core_grad.setColorAt(0.5, QColor('#0284c7'))
        core_grad.setColorAt(1.0, QColor('#0f172a'))
        p.setBrush(QBrush(core_grad))
        p.setPen(QPen(QColor('#7dd3fc'), 1.5 * scale))

        core_path = QPainterPath()
        core_path.moveTo(64 * scale, 46 * scale)
        core_path.lineTo(82 * scale, 64 * scale)
        core_path.lineTo(64 * scale, 82 * scale)
        core_path.lineTo(46 * scale, 64 * scale)
        core_path.closeSubpath()
        p.drawPath(core_path)

        # 5. Glowing center node
        p.setBrush(QBrush(QColor('#ffffff')))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(60 * scale, 60 * scale, 8 * scale, 8 * scale))

        # Corner PCB nodes
        p.setBrush(QBrush(QColor('#34d399')))
        p.drawEllipse(QRectF(32 * scale, 38 * scale, 4.5 * scale, 4.5 * scale))
        p.drawEllipse(QRectF(91.5 * scale, 85.5 * scale, 4.5 * scale, 4.5 * scale))
        p.end()
        pix.save(os.path.join(ICONS_DIR, filename))

    # Generate all asset files
    draw_chevron_up(color_normal, "up_arrow.png")
    draw_chevron_up(color_active, "up_arrow_hover.png")
    draw_chevron_down(color_normal, "down_arrow.png")
    draw_chevron_down(color_active, "down_arrow_hover.png")
    draw_chevron_down(color_normal, "combo_arrow.png")
    draw_chevron_down(color_active, "combo_arrow_hover.png")
    draw_checkmark("check_mark.png")

    draw_radio("radio_unchecked.png", "#334155", "#0b101b")
    draw_radio("radio_unchecked_hover.png", "#38bdf8", "#0e1726")
    draw_radio("radio_checked.png", "#38bdf8", "#0b101b", "#38bdf8")
    draw_logo(256, "app_logo_256.png")
    draw_logo(128, "app_logo.png")
    draw_logo(64, "app_logo_64.png")
    draw_logo(32, "app_logo_32.png")
    draw_logo(128, "app_logo.ico")


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    generate_arrows()
