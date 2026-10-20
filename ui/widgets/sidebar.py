"""
Omnix UI — Modern Collapsible Navigation Sidebar
Governing Requirement: Section 5 Navigation Redesign

Provides a collapsible navigation sidebar for Mode A:
- Assembly & Stock
- Component Inventory
- BOM Audit
- Reference Data
- General Settings
- Vendor / Link Provider Management
- Database Backup & Restore

Supports two visual modes:
- Expanded mode: icons and full text labels.
- Collapsed mode: narrow rail displaying centered icons with rich tooltips.
"""

from typing import Optional, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QLabel,
    QWidget,
    QSizePolicy,
)


class SidebarNavButton(QPushButton):
    """Navigation button supporting expanded and collapsed states."""

    def __init__(self, page_id: str, label: str, icon_str: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.page_id = page_id
        self.full_label = label
        self.icon_str = icon_str
        self._is_collapsed = False
        self._is_active = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)
        self.setToolTip(label)
        self.setFont(QFont("Segoe UI", 9))
        self._update_display()
        self._apply_style()

    def set_collapsed(self, collapsed: bool):
        self._is_collapsed = collapsed
        self._update_display()
        self._apply_style()

    def set_active(self, active: bool):
        self._is_active = active
        self._apply_style()

    def _update_display(self):
        if self._is_collapsed:
            self.setText(self.icon_str)
        else:
            self.setText(f"  {self.icon_str}   {self.full_label}")

    def _apply_style(self):
        if self._is_active:
            bg_color = "rgba(56, 189, 248, 0.14)"
            text_color = "#38bdf8"
            border_left = "3px solid #38bdf8"
            font_weight = "bold"
        else:
            bg_color = "transparent"
            text_color = "#94a3b8"
            border_left = "3px solid transparent"
            font_weight = "600"

        align = "center" if self._is_collapsed else "left"
        padding_left = "0px" if self._is_collapsed else "10px"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-left: {border_left};
                border-radius: 4px;
                padding-left: {padding_left};
                padding-right: 6px;
                text-align: {align};
                font-size: 11px;
                font-weight: {font_weight};
                font-family: 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                color: #f1f5f9;
            }}
            QPushButton:focus {{
                outline: none;
                border-left: 3px solid #38bdf8;
            }}
        """)


class CollapsibleSidebar(QFrame):
    """
    Collapsible side navigation rail for Omnix desktop application.
    Hosts all primary Mode A views and system utilities.
    """

    pageChanged = pyqtSignal(str)
    collapseChanged = pyqtSignal(bool)

    EXPANDED_WIDTH = 210
    COLLAPSED_WIDTH = 50

    PAGES = [
        ("assembly_view", "Assembly & Stock", "📊"),
        ("component_inventory", "Component Inventory", "🏷️"),
        ("bom_audit", "BOM Audit", "📑"),
        ("reference_data", "Reference Data", "📚"),
        ("general_settings", "General Settings", "⚙️"),
        ("provider_management", "Vendor & Link Providers", "🌐"),
        ("backup_restore", "Database Backup & Restore", "💾"),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("collapsibleSidebar")
        self._is_collapsed = False
        self._active_page_id = "assembly_view"
        self._buttons: Dict[str, SidebarNavButton] = {}

        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.setStyleSheet("""
            QFrame#collapsibleSidebar {
                background-color: #0b101b;
                border-right: 1px solid #1e293b;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(4)

        # Navigation Buttons
        for page_id, label, icon_str in self.PAGES:
            btn = SidebarNavButton(page_id, label, icon_str, self)
            btn.clicked.connect(lambda checked=False, pid=page_id: self._on_button_clicked(pid))
            layout.addWidget(btn)
            self._buttons[page_id] = btn

        # Set default active
        if "assembly_view" in self._buttons:
            self._buttons["assembly_view"].set_active(True)

        layout.addStretch(1)

    def _on_button_clicked(self, page_id: str):
        self.set_active_page(page_id)
        self.pageChanged.emit(page_id)

    def set_active_page(self, page_id: str):
        self._active_page_id = page_id
        for pid, btn in self._buttons.items():
            btn.set_active(pid == page_id)

    def active_page(self) -> str:
        return self._active_page_id

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def toggle_collapse(self):
        self.set_collapsed(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool):
        if self._is_collapsed == collapsed:
            return
        self._is_collapsed = collapsed
        new_width = self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        self.setFixedWidth(new_width)

        for btn in self._buttons.values():
            btn.set_collapsed(collapsed)

        self.collapseChanged.emit(collapsed)
