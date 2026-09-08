import os
from config import get_bundle_dir
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPolygon
from PyQt6.QtCore import Qt, QPoint

def ensure_spinbox_icons():
    icons_dir = os.path.join(get_bundle_dir(), "ui", "icons")
    try:
        os.makedirs(icons_dir, exist_ok=True)
    except Exception:
        pass
    
    up_p = os.path.join(icons_dir, "spin_up.png")
    up_h_p = os.path.join(icons_dir, "spin_up_hover.png")
    down_p = os.path.join(icons_dir, "spin_down.png")
    down_h_p = os.path.join(icons_dir, "spin_down_hover.png")

    try:
        if not (os.path.exists(up_p) and os.path.exists(up_h_p) and os.path.exists(down_p) and os.path.exists(down_h_p)):
            def make_icon(direction="up", color="#38bdf8", size=32):
                pm = QPixmap(size, size)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                if direction == "up":
                    points = [QPoint(size // 2, 8), QPoint(6, size - 9), QPoint(size - 6, size - 9)]
                else:
                    points = [QPoint(6, 9), QPoint(size - 6, 9), QPoint(size // 2, size - 8)]
                p.drawPolygon(QPolygon(points))
                p.end()
                return pm

            make_icon("up", "#38bdf8", 32).save(up_p)
            make_icon("up", "#ffffff", 32).save(up_h_p)
            make_icon("down", "#38bdf8", 32).save(down_p)
            make_icon("down", "#ffffff", 32).save(down_h_p)
    except Exception:
        pass

    return (
        up_p.replace("\\", "/"),
        up_h_p.replace("\\", "/"),
        down_p.replace("\\", "/"),
        down_h_p.replace("\\", "/")
    )


_RAW_DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #080c14;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Tahoma, Arial, sans-serif;
}

QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    font-size: 13px;
}

/* Tab Bar & Navigation */
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #080c14;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #0d1424;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 9px 22px;
    margin-right: 4px;
    font-size: 13px;
    font-weight: 600;
}

QTabBar::tab:hover {
    background-color: #131d33;
    color: #38bdf8;
    border-color: #2a3e61;
}

QTabBar::tab:selected {
    background-color: #0f172a;
    color: #38bdf8;
    border-color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}

/* Background panels and elevated frames */
QFrame#cardFrame {
    background-color: #0f172a;
    border: 1.5px solid #1e293b;
    border-radius: 8px;
    padding: 10px;
}

QFrame#ribbonFrame {
    background-color: #0d1321;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 6px 12px;
}

/* Status ribbon capsules */
QLabel.statPill {
    background-color: #131d31;
    border: 1px solid #22324e;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    color: #94a3b8;
    font-weight: 500;
}

QLabel.statPillSuccess {
    background-color: rgba(16, 185, 129, 0.10);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

QLabel.statPillWarning {
    background-color: rgba(245, 158, 11, 0.10);
    border: 1px solid rgba(245, 158, 11, 0.25);
    color: #fbbf24;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

QLabel.statPillDanger {
    background-color: rgba(244, 63, 94, 0.10);
    border: 1px solid rgba(244, 63, 94, 0.25);
    color: #f87171;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

/* High-density database table */
QTableWidget {
    background-color: #0b101b;
    border: 1px solid #1e293b;
    border-radius: 8px;
    gridline-color: #162032;
    selection-background-color: #172d47;
    selection-color: #ffffff;
    font-size: 13px;
    outline: none;
}

QTableWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #151f30;
}

QTableWidget::item:selected {
    background-color: #172d47;
    color: #ffffff;
}

QTableWidget::item:hover {
    background-color: #111b2b;
}

QHeaderView {
    background-color: #080c14;
    border: none;
}

QHeaderView::section {
    background-color: #080c14;
    color: #7dd3fc;
    font-weight: 600;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #1e293b;
    font-size: 12px;
}

QTableCornerButton::section {
    background-color: #080c14;
    border: none;
}

/* Context menu */
QMenu {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 5px;
}

QMenu::item {
    background-color: transparent;
    padding: 7px 18px 7px 14px;
    border-radius: 5px;
    color: #e2e8f0;
    font-size: 12px;
}

QMenu::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: #1e293b;
    margin: 4px 6px;
}

/* Tooltips */
QToolTip {
    background-color: #0f172a;
    color: #38bdf8;
    border: 1px solid #38bdf8;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}

/* Search and Text Inputs */
QLineEdit {
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 13px;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}

QLineEdit:hover {
    border: 1.5px solid #3b82f6;
    background-color: #142038;
}

QLineEdit:focus {
    border: 1.5px solid #38bdf8;
    background-color: #162440;
    color: #ffffff;
}

/* In-place Table Cell Editors */
QTableWidget QLineEdit,
QAbstractItemView QLineEdit {
    background-color: #0c182e;
    color: #38bdf8;
    border: 2px solid #38bdf8;
    border-radius: 6px;
    padding: 2px 6px;
    margin: 1px 3px;
    font-size: 13px;
    font-weight: bold;
    qproperty-alignment: 'AlignCenter';
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}

/* General SpinBox */
QSpinBox {
    background-color: #111a2e;
    border: 1.5px solid #23385e;
    border-radius: 6px;
    padding: 4px 38px 4px 12px;
    color: #f8fafc;
    font-size: 14px;
    font-weight: 600;
    font-family: 'Consolas', 'Segoe UI', Tahoma, monospace;
}

QSpinBox:hover, QSpinBox:focus {
    border-color: #38bdf8;
    background-color: #142038;
}

QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 34px;
    height: 16px;
    border-left: 1.5px solid #23385e;
    border-bottom: 1px solid #23385e;
    border-top-right-radius: 5px;
    background-color: #162440;
}

QSpinBox::up-button:hover {
    background-color: #0284c7;
    border-color: #38bdf8;
}

QSpinBox::up-arrow {
    image: url('__SPIN_UP_ICON__');
    width: 13px;
    height: 13px;
}

QSpinBox::up-button:hover QSpinBox::up-arrow {
    image: url('__SPIN_UP_HOVER_ICON__');
}

QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 34px;
    height: 16px;
    border-left: 1.5px solid #23385e;
    border-bottom-right-radius: 5px;
    background-color: #162440;
}

QSpinBox::down-button:hover {
    background-color: #0284c7;
    border-color: #38bdf8;
}

QSpinBox::down-arrow {
    image: url('__SPIN_DOWN_ICON__');
    width: 13px;
    height: 13px;
}

QSpinBox::down-button:hover QSpinBox::down-arrow {
    image: url('__SPIN_DOWN_HOVER_ICON__');
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid #334155;
    background-color: #111a2e;
}

QCheckBox::indicator:checked {
    background-color: #0284c7;
    border-color: #38bdf8;
}

/* Progress Bar */
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    font-size: 11px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
    border-radius: 5px;
}

/* Buttons */
QPushButton {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #0369a1;
}

QPushButton:pressed {
    background-color: #075985;
}

QPushButton:disabled {
    background-color: #1e293b;
    color: #64748b;
}

QPushButton#secondaryBtn {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 6px 16px;
}

QPushButton#secondaryBtn:hover {
    background-color: #334155;
    border: 1px solid #475569;
}

QPushButton#dangerBtn {
    background-color: #b91c1c;
    color: #ffffff;
    padding: 6px 16px;
}

QPushButton#dangerBtn:hover {
    background-color: #991b1b;
}

/* Exit Confirmation Dialog & QMessageBox */
QMessageBox {
    background-color: #0d1526;
    color: #f8fafc;
    border: 1.5px solid #1e3a5f;
    border-radius: 8px;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    min-width: 420px;
}

QMessageBox QLabel {
    color: #f8fafc;
    font-size: 13px;
    font-weight: normal;
    background-color: transparent;
    padding: 4px 6px;
}

QMessageBox QPushButton {
    min-width: 85px;
    min-height: 28px;
    padding: 6px 18px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
}

/* Header branding */
QLabel#brandTitle {
    font-size: 17px;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: 0.5px;
    padding-bottom: 2px;
}

QLabel#brandSubtitle {
    font-size: 11px;
    color: #64748b;
    padding-bottom: 2px;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0px 2px 0px 2px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #334155;
    min-height: 28px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #38bdf8;
}

QScrollBar::handle:vertical:pressed {
    background-color: #0284c7;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    margin: 0px 2px 0px 2px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: #334155;
    min-width: 28px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #38bdf8;
}

QScrollBar::handle:horizontal:pressed {
    background-color: #0284c7;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* Bottom status bar */
QStatusBar {
    background-color: #080c14;
    border-top: 1px solid #1e293b;
    color: #64748b;
    font-size: 11px;
    padding: 3px 8px;
    min-height: 24px;
}

QStatusBar::item {
    border: none;
}
"""

_up_icon, _up_hover, _down_icon, _down_hover = ensure_spinbox_icons()
DARK_STYLESHEET = _RAW_DARK_STYLESHEET.replace("__SPIN_UP_ICON__", _up_icon) \
    .replace("__SPIN_UP_HOVER_ICON__", _up_hover) \
    .replace("__SPIN_DOWN_ICON__", _down_icon) \
    .replace("__SPIN_DOWN_HOVER_ICON__", _down_hover)

