"""
Omnix Dark Stylesheet (Lightweight View-Only Edition)
"""

DARK_STYLESHEET = """
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

/* Background panels and elevated frames */
QFrame#cardFrame {
    background-color: #0f172a;
    border: 1.5px solid #1e293b;
    border-radius: 8px;
    padding: 8px;
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

/* Search input */
QLineEdit {
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 9px 14px;
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

/* Exit Confirmation Dialog (QMessageBox) */
QMessageBox {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1.5px solid #1e3a5f;
    border-radius: 10px;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
}

QMessageBox QLabel {
    color: #f8fafc;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    padding: 6px 10px;
}

QMessageBox QPushButton {
    min-width: 80px;
    min-height: 28px;
    padding: 6px 18px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
}

/* Header branding */
QLabel {
    color: #e2e8f0;
}

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
