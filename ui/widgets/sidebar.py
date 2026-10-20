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
- Expanded mode: minimal outline icons and full text labels.
- Collapsed mode: narrow rail displaying centered outline icons with rich tooltips.
"""

from typing import Optional, Dict, Tuple
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QByteArray
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
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

# Standardized minimal outline SVG vector icons (24x24, stroke-width 1.8)
SIDEBAR_ICON_SVGS: Dict[str, str] = {
    "assembly_view": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="20" x2="18" y2="10"/>
  <line x1="12" y1="20" x2="12" y2="4"/>
  <line x1="6" y1="20" x2="6" y2="14"/>
</svg>""",
    "component_inventory": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/>
  <circle cx="7" cy="7" r="1.2" fill="currentColor"/>
</svg>""",
    "bom_audit": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
  <polyline points="14 2 14 8 20 8"/>
  <line x1="16" y1="13" x2="8" y2="13"/>
  <line x1="16" y1="17" x2="8" y2="17"/>
  <line x1="10" y1="9" x2="8" y2="9"/>
</svg>""",
    "reference_data": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
</svg>""",
    "general_settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>""",
    "provider_management": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>
  <path d="M2 12h20"/>
</svg>""",
    "backup_restore": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>
  <path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>
  <path d="M7 3v4a1 1 0 0 0 1 1h7"/>
</svg>""",
}

# Compatibility mapping for legacy emoji strings
LEGACY_EMOJI_MAP: Dict[str, str] = {
    "📊": "assembly_view",
    "🏷️": "component_inventory",
    "📑": "bom_audit",
    "📚": "reference_data",
    "⚙️": "general_settings",
    "🌐": "provider_management",
    "💾": "backup_restore",
}

_PIXMAP_CACHE: Dict[Tuple[str, str, int], QPixmap] = {}


def render_outline_pixmap(icon_key: str, color_hex: str, size: int = 36) -> QPixmap:
    """Renders a minimal outline SVG icon to a HiDPI QPixmap with caching."""
    cache_key = (icon_key, color_hex, size)
    if cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    actual_key = LEGACY_EMOJI_MAP.get(icon_key, icon_key)
    svg_tmpl = SIDEBAR_ICON_SVGS.get(actual_key, SIDEBAR_ICON_SVGS["general_settings"])

    svg_colored = (
        svg_tmpl.replace('stroke="currentColor"', f'stroke="{color_hex}"')
        .replace('fill="currentColor"', f'fill="{color_hex}"')
    )
    renderer = QSvgRenderer(QByteArray(svg_colored.encode("utf-8")))

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()

    _PIXMAP_CACHE[cache_key] = pm
    return pm


def create_sidebar_icon(icon_key: str, normal_color: str = "#94a3b8", active_color: str = "#38bdf8", hover_color: str = "#f1f5f9") -> Tuple[QIcon, QIcon, QIcon]:
    """Creates a tuple of (normal, active, hover) QIcon objects for a sidebar item."""
    icon_normal = QIcon(render_outline_pixmap(icon_key, normal_color))
    icon_active = QIcon(render_outline_pixmap(icon_key, active_color))
    icon_hover = QIcon(render_outline_pixmap(icon_key, hover_color))
    return icon_normal, icon_active, icon_hover


class SidebarNavButton(QPushButton):
    """Navigation button supporting expanded and collapsed states with minimal outline icons."""

    def __init__(self, page_id: str, label: str, icon_str: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.page_id = page_id
        self.full_label = label
        self.icon_str = icon_str or page_id
        self._is_collapsed = False
        self._is_active = False

        self._icon_normal, self._icon_active, self._icon_hover = create_sidebar_icon(self.icon_str)

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
        self._update_display()
        self._apply_style()

    def enterEvent(self, event):
        super().enterEvent(event)
        if not self._is_active:
            self.setIcon(self._icon_hover)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self._is_active:
            self.setIcon(self._icon_normal)

    def _update_display(self):
        self.setIcon(self._icon_active if self._is_active else self._icon_normal)
        self.setIconSize(QSize(18, 18))
        if self._is_collapsed:
            self.setText("")
        else:
            self.setText(f"  {self.full_label}")

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
    Hosts all primary Mode A views and system utilities with standardized outline icons.
    """

    pageChanged = pyqtSignal(str)
    collapseChanged = pyqtSignal(bool)

    EXPANDED_WIDTH = 210
    COLLAPSED_WIDTH = 50

    PAGES = [
        ("assembly_view", "Assembly & Stock", "assembly_view"),
        ("component_inventory", "Component Inventory", "component_inventory"),
        ("bom_audit", "BOM Audit", "bom_audit"),
        ("reference_data", "Reference Data", "reference_data"),
        ("general_settings", "General Settings", "general_settings"),
        ("provider_management", "Vendor & Link Providers", "provider_management"),
        ("backup_restore", "Database Backup & Restore", "backup_restore"),
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
