import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
UP_ARROW_PATH = f"{CURRENT_DIR}/icons/up_arrow.png"
UP_ARROW_HOVER_PATH = f"{CURRENT_DIR}/icons/up_arrow_hover.png"
DOWN_ARROW_PATH = f"{CURRENT_DIR}/icons/down_arrow.png"
DOWN_ARROW_HOVER_PATH = f"{CURRENT_DIR}/icons/down_arrow_hover.png"
COMBO_ARROW_PATH = f"{CURRENT_DIR}/icons/combo_arrow.png"
COMBO_ARROW_HOVER_PATH = f"{CURRENT_DIR}/icons/combo_arrow_hover.png"
CHECK_MARK_PATH = f"{CURRENT_DIR}/icons/check_mark.png"
RADIO_UNCHECKED_PATH = f"{CURRENT_DIR}/icons/radio_unchecked.png"
RADIO_UNCHECKED_HOVER_PATH = f"{CURRENT_DIR}/icons/radio_unchecked_hover.png"
RADIO_CHECKED_PATH = f"{CURRENT_DIR}/icons/radio_checked.png"
RADIO_CHECKED_HOVER_PATH = f"{CURRENT_DIR}/icons/radio_checked_hover.png"

DARK_STYLESHEET = f"""
QMainWindow, QDialog, QMessageBox {{
    background-color: #080c14;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Tahoma, Arial, sans-serif;
}}

QWidget {{
    color: #e2e8f0;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    font-size: 13px;
}}

/* Background panels and elevated frames (Matte Elevation) */
QFrame#cardFrame {{
    background-color: #0f172a;
    border: 1.5px solid #1e293b;
    border-radius: 8px;
    padding: 12px;
}}

QScrollArea#dialogScrollArea, QScrollArea#dialogScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

QFrame#ribbonFrame {{
    background-color: #0d1321;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 6px 12px;
    margin-top: 2px;
}}

/* Status ribbon capsules (Status Ribbon Pills) */
QLabel.statPill {{
    background-color: #131d31;
    border: 1px solid #22324e;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    color: #94a3b8;
    font-weight: 500;
}}

QLabel.statPillSuccess {{
    background-color: rgba(16, 185, 129, 0.10);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel.statPillWarning {{
    background-color: rgba(245, 158, 11, 0.10);
    border: 1px solid rgba(245, 158, 11, 0.25);
    color: #fbbf24;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel.statPillDanger {{
    background-color: rgba(244, 63, 94, 0.10);
    border: 1px solid rgba(244, 63, 94, 0.25);
    color: #f87171;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}

/* Engineering high-density table */
QTableWidget {{
    background-color: #0b101b;
    border: 1px solid #1e293b;
    border-radius: 8px;
    gridline-color: #162032;
    selection-background-color: #1e3a5f;
    selection-color: #ffffff;
    font-size: 13px;
    outline: none;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #151f30;
}}

QTableWidget::item:selected {{
    background-color: #172d47;
    color: #ffffff;
}}

QTableWidget::item:hover {{
    background-color: #111b2b;
}}

QHeaderView {{
    background-color: #080c14;
    border: none;
}}

QHeaderView::section {{
    background-color: #080c14;
    color: #7dd3fc;
    font-weight: 600;
    padding: 8px 6px;
    border: none;
    border-bottom: 1px solid #1e293b;
    font-size: 12px;
}}

QHeaderView::section:vertical {{
    background-color: #080c14;
    color: #475569;
    border-right: 1px solid #1e293b;
    border-bottom: 1px solid #1e293b;
    padding: 2px;
}}

QTableCornerButton::section {{
    background-color: #080c14;
    border: none;
}}

/* Context menus and popups */
QMenu {{
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 5px;
}}

QMenu::item {{
    background-color: transparent;
    padding: 7px 20px 7px 14px;
    border-radius: 5px;
    color: #e2e8f0;
    font-size: 12px;
}}

QMenu::item:selected {{
    background-color: #0284c7;
    color: #ffffff;
}}

QMenu::item:disabled {{
    color: #64748b;
}}

QMenu::separator {{
    height: 1px;
    background-color: #1e293b;
    margin: 4px 6px;
}}

/* Tooltips */
QToolTip {{
    background-color: #0f172a;
    color: #38bdf8;
    border: 1px solid #38bdf8;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* Single-line text inputs */
QLineEdit {{
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 13px;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}}

QLineEdit:hover {{
    border: 1.5px solid #3b82f6;
    background-color: #142038;
}}

QLineEdit:focus {{
    border: 1.5px solid #38bdf8;
    background-color: #162440;
}}

/* Multi-line text inputs */
QTextEdit, QPlainTextEdit {{
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    font-size: 13px;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}}

QTextEdit:hover, QPlainTextEdit:hover {{
    border: 1.5px solid #3b82f6;
    background-color: #142038;
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1.5px solid #38bdf8;
    background-color: #162440;
}}

/* Numerical inputs (QSpinBox) */
QSpinBox {{
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    font-size: 13px;
    font-weight: 600;
    min-height: 28px;
}}

QSpinBox:hover {{
    border: 1.5px solid #3b82f6;
    background-color: #142038;
}}

QSpinBox:focus {{
    border: 1.5px solid #38bdf8;
    background-color: #162440;
}}

QSpinBox::up-button {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    width: 22px;
    border: none;
    background: transparent;
    margin: 2px 0px 0px 2px;
}}

QSpinBox::up-button:hover {{
    background-color: rgba(56, 189, 248, 0.20);
    border-radius: 3px;
}}

QSpinBox::up-arrow {{
    image: url("{UP_ARROW_PATH}");
    width: 10px;
    height: 10px;
}}

QSpinBox::up-arrow:hover {{
    image: url("{UP_ARROW_HOVER_PATH}");
}}

QSpinBox::down-button {{
    subcontrol-origin: padding;
    subcontrol-position: bottom left;
    width: 22px;
    border: none;
    background: transparent;
    margin: 0px 0px 2px 2px;
}}

QSpinBox::down-button:hover {{
    background-color: rgba(56, 189, 248, 0.20);
    border-radius: 3px;
}}

QSpinBox::down-arrow {{
    image: url("{DOWN_ARROW_PATH}");
    width: 10px;
    height: 10px;
}}

QSpinBox::down-arrow:hover {{
    image: url("{DOWN_ARROW_HOVER_PATH}");
}}

/* Dropdown list (QComboBox) */
QComboBox {{
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 6px;
    padding: 7px 12px;
    padding-left: 32px;
    color: #f8fafc;
    font-size: 13px;
    min-height: 24px;
}}

QComboBox:hover {{
    border: 1.5px solid #3b82f6;
    background-color: #142038;
}}

QComboBox:focus {{
    border: 1.5px solid #38bdf8;
    background-color: #162440;
}}

QComboBox:on {{
    border: 1.5px solid #38bdf8;
    background-color: #162440;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center left;
    width: 28px;
    border: none;
    background: transparent;
}}

QComboBox::down-arrow {{
    image: url("{COMBO_ARROW_PATH}");
    width: 11px;
    height: 11px;
}}

QComboBox::down-arrow:hover {{
    image: url("{COMBO_ARROW_HOVER_PATH}");
}}

QComboBox QAbstractItemView {{
    background-color: #0e1626;
    border: 1.5px solid #38bdf8;
    border-radius: 6px;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    color: #f8fafc;
    padding: 5px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 30px;
    padding: 6px 12px;
    border-radius: 4px;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: #0284c7;
    color: #ffffff;
    font-weight: 600;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: #1e3a5f;
    color: #38bdf8;
}}

/* Checkboxes (QCheckBox) */
QCheckBox {{
    spacing: 8px;
    color: #e2e8f0;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #334155;
    background-color: #0b101b;
}}

QCheckBox::indicator:hover {{
    border: 1px solid #38bdf8;
}}

QCheckBox::indicator:checked {{
    background-color: #0284c7;
    border: 1px solid #38bdf8;
    image: url("{CHECK_MARK_PATH}");
}}

/* Radio buttons with custom center dot indicator */
QRadioButton {{
    spacing: 10px;
    color: #e2e8f0;
    font-size: 13px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    background: transparent;
    border: none;
    image: url("{RADIO_UNCHECKED_PATH}");
}}

QRadioButton::indicator:hover {{
    image: url("{RADIO_UNCHECKED_HOVER_PATH}");
}}

QRadioButton::indicator:checked {{
    image: url("{RADIO_CHECKED_PATH}");
}}

QRadioButton::indicator:checked:hover {{
    image: url("{RADIO_CHECKED_HOVER_PATH}");
}}

/* List widgets with full item highlight */
QListWidget {{
    background-color: #111a2e;
    border: 1.5px solid #233352;
    border-radius: 8px;
    padding: 6px;
    color: #e2e8f0;
    outline: none;
}}

QListWidget::item {{
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 13px;
    margin: 2px 0px;
    border: 1px solid transparent;
}}

QListWidget::item:hover {{
    background-color: #162440;
    color: #38bdf8;
    border: 1px solid #233352;
}}

QListWidget::item:selected {{
    background-color: #0284c7;
    color: #ffffff;
    font-weight: 700;
    border: 1px solid #38bdf8;
}}

QListWidget::item:selected:hover {{
    background-color: #0369a1;
    color: #ffffff;
    border: 1px solid #38bdf8;
}}

/* Primary buttons */
QPushButton {{
    background-color: #0284c7;
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: #0369a1;
}}

QPushButton:pressed {{
    background-color: #075985;
}}

/* Button popup menu indicator arrow */
QPushButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center left;
    left: 10px;
    width: 9px;
    height: 9px;
    image: url("{COMBO_ARROW_PATH}");
}}

QPushButton::menu-indicator:hover {{
    image: url("{COMBO_ARROW_HOVER_PATH}");
}}

/* Secondary / Neutral buttons */
QPushButton#secondaryBtn {{
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding-left: 16px;
    padding-right: 16px;
}}

QPushButton#secondaryBtn:hover {{
    background-color: #334155;
    border: 1px solid #475569;
}}

/* Success action buttons */
QPushButton#successBtn {{
    background-color: #15803d;
    color: #ffffff;
}}

QPushButton#successBtn:hover {{
    background-color: #166534;
}}

/* Danger action buttons */
QPushButton#dangerBtn {{
    background-color: #b91c1c;
    color: #ffffff;
}}

QPushButton#dangerBtn:hover {{
    background-color: #991b1b;
}}

/* Ghost action buttons inside table */
QPushButton.ghostActionBtn {{
    font-family: 'Segoe UI Symbol', 'Segoe UI', 'Arial', sans-serif;
    border-radius: 4px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
    border: 1px solid transparent;
    background-color: transparent;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton.ghostActionBtnPlus {{
    color: #34d399;
}}
QPushButton.ghostActionBtnPlus:hover {{
    background-color: rgba(16, 185, 129, 0.20);
    border: 1px solid rgba(16, 185, 129, 0.40);
}}

QPushButton.ghostActionBtnMinus {{
    color: #fbbf24;
}}
QPushButton.ghostActionBtnMinus:hover {{
    background-color: rgba(245, 158, 11, 0.20);
    border: 1px solid rgba(245, 158, 11, 0.40);
}}

QPushButton.ghostActionBtnStock {{
    color: #38bdf8;
}}
QPushButton.ghostActionBtnStock:hover {{
    background-color: rgba(56, 189, 248, 0.20);
    border: 1px solid rgba(56, 189, 248, 0.40);
}}

QPushButton.ghostActionBtnEdit {{
    color: #a5b4fc;
}}
QPushButton.ghostActionBtnEdit:hover {{
    background-color: rgba(99, 102, 241, 0.20);
    border: 1px solid rgba(99, 102, 241, 0.40);
}}

QPushButton.ghostActionBtnDelete {{
    color: #f87171;
}}
QPushButton.ghostActionBtnDelete:hover {{
    background-color: rgba(244, 63, 94, 0.20);
    border: 1px solid rgba(244, 63, 94, 0.40);
}}

/* Drawer chips in table cells */
QPushButton.drawerChip {{
    background-color: #131f33;
    color: #38bdf8;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 2px 7px;
    font-family: 'Consolas', 'Segoe UI Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    min-width: 22px;
    min-height: 20px;
    max-height: 22px;
}}

QPushButton.drawerChip:hover {{
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
}}

QPushButton.drawerChipEmpty {{
    background-color: rgba(244, 63, 94, 0.12);
    color: #f87171;
    border: 1px solid rgba(244, 63, 94, 0.35);
    border-radius: 4px;
    padding: 2px 7px;
    font-family: 'Consolas', 'Segoe UI Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    min-width: 22px;
    min-height: 20px;
    max-height: 22px;
}}

QPushButton.drawerChipEmpty:hover {{
    background-color: #e11d48;
    color: #ffffff;
    border: 1px solid #f43f5e;
}}

QPushButton.drawerChipLow {{
    background-color: rgba(245, 158, 11, 0.14);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.40);
    border-radius: 4px;
    padding: 2px 7px;
    font-family: 'Consolas', 'Segoe UI Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    min-width: 22px;
    min-height: 20px;
    max-height: 22px;
}}

QPushButton.drawerChipLow:hover {{
    background-color: #d97706;
    color: #ffffff;
    border: 1px solid #f59e0b;
}}

QPushButton.drawerChipMore {{
    background-color: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.30);
    border-radius: 4px;
    padding: 0px 5px;
    font-family: 'Consolas', 'Segoe UI Mono', monospace;
    font-size: 12px;
    font-weight: 700;
    min-width: 22px;
    min-height: 20px;
    max-height: 22px;
}}

QPushButton.drawerChipMore:hover {{
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
}}

/* Header labels and brand text */
QLabel {{
    color: #e2e8f0;
}}

QLabel#brandTitle {{
    font-size: 17px;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: 0.5px;
    padding-bottom: 2px;
}}

QLabel#brandSubtitle {{
    font-size: 11px;
    color: #64748b;
    padding-bottom: 2px;
}}

/* Settings tabs (QTabWidget & QTabBar) */
QTabWidget::pane {{
    border: 1px solid #233352;
    border-radius: 8px;
    background-color: #0b111e;
    top: -1px;
}}

QTabBar::tab {{
    background-color: #111a2e;
    color: #94a3b8;
    border: 1px solid #233352;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-left: 4px;
    font-weight: 600;
    font-size: 12px;
}}

QTabBar::tab:hover {{
    background-color: #162440;
    color: #38bdf8;
}}

QTabBar::tab:selected {{
    background-color: #0b111e;
    color: #38bdf8;
    border-color: #38bdf8 #233352 #0b111e #233352;
    border-top: 2px solid #38bdf8;
    font-weight: 700;
}}

/* Modern smooth vertical scrollbar */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0px 2px 0px 2px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: #334155;
    min-height: 28px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #38bdf8;
}}

QScrollBar::handle:vertical:pressed {{
    background-color: #0284c7;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* Horizontal scrollbar */
QScrollBar:horizontal {{
    height: 0px;
    background: transparent;
}}

QScrollBar::handle:horizontal, QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    height: 0px;
    width: 0px;
    border: none;
}}

/* Bottom status bar */
QStatusBar {{
    background-color: #080c14;
    border-top: 1px solid #1e293b;
    color: #64748b;
    font-size: 11px;
    padding: 3px 6px;
    min-height: 24px;
}}

QStatusBar::item {{
    border: none;
}}
"""
