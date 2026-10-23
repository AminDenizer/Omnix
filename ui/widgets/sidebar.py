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
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QByteArray, QRectF
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
    "assembly_prep": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
</svg>""",
    "reference_data": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
</svg>""",
    "general_settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <line x1="4" y1="21" x2="4" y2="14"/>
  <line x1="4" y1="10" x2="4" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12" y2="3"/>
  <line x1="20" y1="21" x2="20" y2="16"/>
  <line x1="20" y1="12" x2="20" y2="3"/>
  <line x1="1" y1="14" x2="7" y2="14"/>
  <line x1="9" y1="8" x2="15" y2="8"/>
  <line x1="17" y1="16" x2="23" y2="16"/>
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
    "vendor_plugins": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
  <line x1="12" y1="22.08" x2="12" y2="12"/>
</svg>""",
    "live_log": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="4 17 10 11 4 5"/>
  <line x1="12" y1="19" x2="20" y2="19"/>
</svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>""",
    "about": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="12" y1="16" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12.01" y2="8"/>
</svg>""",
    "chevron_right": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="9 18 15 12 9 6"/>
</svg>""",
    "chevron_down": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="6 9 12 15 18 9"/>
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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, float(size), float(size)))
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
            self.setText(f"  {self.full_label.replace('&', '&&')}")

    def text(self) -> str:
        return super().text().replace("&&", "&")

    def _apply_style(self):
        if self._is_active:
            bg_color = "#1e293b"
            text_color = "#f8fafc"
            border_left = "2px solid #38bdf8"
            hover_bg = "#273549"
            hover_text = "#ffffff"
            font_weight = "600"
        else:
            bg_color = "transparent"
            text_color = "#94a3b8"
            border_left = "2px solid transparent"
            hover_bg = "rgba(255, 255, 255, 0.05)"
            hover_text = "#e2e8f0"
            font_weight = "500"

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
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_text};
            }}
            QPushButton:pressed {{
                background-color: #334155;
                color: #ffffff;
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """)


class ChevronLabel(QLabel):
    """Custom label rendering an outline SVG chevron and preserving .text() compatibility."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent;")
        self._direction = "right"

    @property
    def direction(self) -> str:
        return self._direction

    def set_direction(self, direction: str, is_active: bool = False, is_hover: bool = False):
        self._direction = direction
        icon_key = "chevron_down" if direction == "down" else "chevron_right"
        if is_active:
            color = "#38bdf8"
        elif is_hover:
            color = "#e2e8f0"
        else:
            color = "#64748b"
        self.setPixmap(render_outline_pixmap(icon_key, color, size=14))

    def text(self) -> str:
        return "▾" if self._direction == "down" else "▸"


class SidebarParentButton(SidebarNavButton):
    """Parent navigation button that toggles child submenu visibility."""

    def __init__(self, page_id: str, label: str, icon_str: str = "", parent: Optional[QWidget] = None):
        self._is_submenu_open = False
        super().__init__(page_id, label, icon_str, parent)

        self._chevron = ChevronLabel(self)
        self._chevron.setGeometry(180, (38 - 14) // 2, 14, 14)
        self._chevron.set_direction("right", is_active=self._is_active)
        self._chevron.setVisible(not self._is_collapsed)

    def set_submenu_open(self, open_state: bool):
        self._is_submenu_open = open_state
        self._chevron.set_direction("down" if open_state else "right", is_active=self._is_active)

    def is_submenu_open(self) -> bool:
        return self._is_submenu_open

    def set_active(self, active: bool):
        super().set_active(active)
        self._chevron.set_direction("down" if self._is_submenu_open else "right", is_active=active)

    def enterEvent(self, event):
        super().enterEvent(event)
        if not self._is_active:
            self._chevron.set_direction("down" if self._is_submenu_open else "right", is_active=False, is_hover=True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self._is_active:
            self._chevron.set_direction("down" if self._is_submenu_open else "right", is_active=False, is_hover=False)

    def set_collapsed(self, collapsed: bool):
        super().set_collapsed(collapsed)
        self._chevron.setVisible(not collapsed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        self._chevron.setGeometry(w - 24, (h - 14) // 2, 14, 14)


class SidebarSubmenuButton(SidebarNavButton):
    """Indented submenu child navigation button."""

    def __init__(self, page_id: str, label: str, icon_str: str = "", parent: Optional[QWidget] = None):
        super().__init__(page_id, label, icon_str, parent)
        self.setFixedHeight(34)
        self.setFont(QFont("Segoe UI", 9))

    def _update_display(self):
        self.setIcon(self._icon_active if self._is_active else self._icon_normal)
        self.setIconSize(QSize(16, 16))
        if self._is_collapsed:
            self.setText("")
        else:
            self.setText(f"  {self.full_label.replace('&', '&&')}")

    def text(self) -> str:
        return super().text().replace("&&", "&")

    def _apply_style(self):
        if self._is_active:
            bg_color = "#1e293b"
            text_color = "#f8fafc"
            border_left = "2px solid #38bdf8"
            hover_bg = "#273549"
            hover_text = "#ffffff"
            font_weight = "600"
        else:
            bg_color = "transparent"
            text_color = "#94a3b8"
            border_left = "2px solid transparent"
            hover_bg = "rgba(255, 255, 255, 0.05)"
            hover_text = "#e2e8f0"
            font_weight = "500"

        align = "center" if self._is_collapsed else "left"
        padding_left = "0px" if self._is_collapsed else "24px"

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
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_text};
            }}
            QPushButton:pressed {{
                background-color: #334155;
                color: #ffffff;
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """)


class _ButtonsDict(dict):
    """Dictionary supporting transparent alias lookups for legacy page IDs and submenu children."""
    def __init__(self, alias_map: Dict[str, str], sidebar: Optional['CollapsibleSidebar'] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._alias_map = alias_map
        self._sidebar = sidebar

    def __getitem__(self, key: str):
        if super().__contains__(key):
            return super().__getitem__(key)
        if key in self._alias_map and super().__contains__(self._alias_map[key]):
            return super().__getitem__(self._alias_map[key])
        if self._sidebar is not None and hasattr(self._sidebar, "_submenu_buttons") and key in self._sidebar._submenu_buttons:
            return self._sidebar._submenu_buttons[key]
        if key in self._alias_map and self._sidebar is not None and hasattr(self._sidebar, "_submenu_buttons") and self._alias_map[key] in self._sidebar._submenu_buttons:
            return self._sidebar._submenu_buttons[self._alias_map[key]]
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str):
            if key in self._alias_map and super().__contains__(self._alias_map[key]):
                return True
            if self._sidebar is not None and hasattr(self._sidebar, "_submenu_buttons") and key in self._sidebar._submenu_buttons:
                return True
            if key in self._alias_map and self._sidebar is not None and hasattr(self._sidebar, "_submenu_buttons") and self._alias_map[key] in self._sidebar._submenu_buttons:
                return True
        return False

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class CollapsibleSidebar(QFrame):
    """
    Collapsible side navigation rail for Omnix desktop application.
    Hosts Workspace, Tools, and Settings destinations with minimal outline icons.
    """

    pageChanged = pyqtSignal(str)
    collapseChanged = pyqtSignal(bool)

    EXPANDED_WIDTH = 210
    COLLAPSED_WIDTH = 50

    SECTIONS = [
        ("WORKSPACE", [
            ("assembly_view", "Assembly & Stock", "assembly_view"),
            ("component_inventory", "Component Inventory", "component_inventory"),
            ("bom_audit", "BOM Audit", "bom_audit"),
            ("assembly_prep", "Assembly & BOM Prep", "assembly_prep"),
        ]),
        ("TOOLS", [
            ("vendor_plugins", "Vendor Plugins", "vendor_plugins"),
            ("live_log", "Live Log", "live_log"),
        ]),
        ("SETTINGS", [
            ("settings", "Settings", "settings"),
        ]),
    ]

    SETTINGS_CHILDREN = [
        ("general_settings", "General", "general_settings"),
        ("reference_data", "Reference Data", "reference_data"),
        ("provider_management", "Supplier Directory", "provider_management"),
        ("backup_restore", "Export & Backup", "backup_restore"),
        ("about", "About", "about"),
    ]

    PAGES = [
        ("assembly_view", "Assembly & Stock", "assembly_view"),
        ("component_inventory", "Component Inventory", "component_inventory"),
        ("bom_audit", "BOM Audit", "bom_audit"),
        ("assembly_prep", "Assembly & BOM Prep", "assembly_prep"),
        ("vendor_plugins", "Vendor Plugins", "vendor_plugins"),
        ("live_log", "Live Log", "live_log"),
        ("settings", "Settings", "settings"),
    ]

    PAGE_ALIAS_MAP: Dict[str, str] = {
        "log": "live_log",
        "logs": "live_log",
        "event_log": "live_log",
        "assembly_preparation": "assembly_prep",
        "export_backup": "backup_restore",
        "supplier_directory": "provider_management",
        "supplier_settings": "provider_management",
        "settings_general": "general_settings",
        "settings_reference_data": "reference_data",
        "settings_supplier_directory": "provider_management",
        "settings_backup_restore": "backup_restore",
        "settings_about": "about",
        "about_settings": "about",
        "backup": "backup_restore",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("collapsibleSidebar")
        self._is_collapsed = False
        self._active_page_id = "assembly_view"
        self._submenu_expanded = False
        self._last_settings_child = "general_settings"
        self._buttons: _ButtonsDict = _ButtonsDict(self.PAGE_ALIAS_MAP, sidebar=self)
        self._section_headers = []
        self._submenu_buttons: Dict[str, SidebarSubmenuButton] = {}

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
        self._section_headers.clear()
        self._submenu_buttons.clear()

        for sec_idx, (sec_title, items) in enumerate(self.SECTIONS):
            if sec_title:
                hdr = QLabel(sec_title)
                hdr.setStyleSheet("""
                    font-size: 9px;
                    font-weight: 800;
                    color: #475569;
                    letter-spacing: 1px;
                    padding-left: 10px;
                    margin-top: 6px;
                    margin-bottom: 2px;
                """)
                layout.addWidget(hdr)
                self._section_headers.append(hdr)

            for page_id, label, icon_str in items:
                if page_id == "settings":
                    self.settings_parent_btn = SidebarParentButton(page_id, label, icon_str, self)
                    self.settings_parent_btn.clicked.connect(self._on_settings_parent_clicked)
                    layout.addWidget(self.settings_parent_btn)
                    self._buttons[page_id] = self.settings_parent_btn

                    # Add submenu children immediately under Settings
                    for child_id, child_label, child_icon in self.SETTINGS_CHILDREN:
                        c_btn = SidebarSubmenuButton(child_id, child_label, child_icon, self)
                        c_btn.clicked.connect(lambda checked=False, pid=child_id: self._on_button_clicked(pid))
                        layout.addWidget(c_btn)
                        self._submenu_buttons[child_id] = c_btn
                        c_btn.setVisible(False)
                else:
                    btn = SidebarNavButton(page_id, label, icon_str, self)
                    btn.clicked.connect(lambda checked=False, pid=page_id: self._on_button_clicked(pid))
                    layout.addWidget(btn)
                    self._buttons[page_id] = btn

            if sec_idx < len(self.SECTIONS) - 1:
                layout.addSpacing(6)

        # Set default active
        if "assembly_view" in self._buttons:
            self._buttons["assembly_view"].set_active(True)

        layout.addStretch(1)

    def _on_button_clicked(self, page_id: str):
        if page_id == "settings":
            self.set_submenu_expanded(True)
        self.set_active_page(page_id)
        self.pageChanged.emit(page_id)

    def _on_settings_parent_clicked(self):
        new_state = not self._submenu_expanded
        self.set_submenu_expanded(new_state)
        if new_state:
            # If current active page is already one of the settings children, keep it
            if self._active_page_id in self._submenu_buttons:
                target_page = self._active_page_id
            else:
                target_page = getattr(self, "_last_settings_child", "general_settings")
            self.set_active_page(target_page)
            self.pageChanged.emit(target_page)
        else:
            is_settings = self._active_page_id in self._submenu_buttons or self._active_page_id == "settings"
            self.settings_parent_btn.set_active(is_settings)

    def set_submenu_expanded(self, expanded: bool):
        self._submenu_expanded = expanded
        self.settings_parent_btn.set_submenu_open(expanded)
        if not self._is_collapsed:
            for btn in self._submenu_buttons.values():
                btn.setVisible(expanded)

    def is_submenu_expanded(self) -> bool:
        return self._submenu_expanded

    def set_active_page(self, page_id: str):
        canonical_id = self.PAGE_ALIAS_MAP.get(page_id, page_id)
        self._active_page_id = canonical_id
        is_settings_section = canonical_id in self._submenu_buttons or canonical_id == "settings"

        # Record last settings child if in settings
        if canonical_id in self._submenu_buttons:
            self._last_settings_child = canonical_id
            if not self._is_collapsed:
                self.set_submenu_expanded(True)

        # Parent Settings button active state (communicates section)
        self.settings_parent_btn.set_active(is_settings_section)

        # Submenu children active state (communicates destination)
        for child_id, btn in self._submenu_buttons.items():
            if canonical_id == "settings":
                target = getattr(self, "_last_settings_child", "general_settings")
                btn.set_active(child_id == target)
            else:
                btn.set_active(child_id == canonical_id)

        # Primary section buttons (Workspace, Tools)
        for pid, btn in self._buttons.items():
            if pid != "settings" and pid not in self._submenu_buttons:
                btn.set_active(pid == canonical_id)

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

        for hdr in self._section_headers:
            hdr.setVisible(not collapsed)

        for btn in self._buttons.values():
            btn.set_collapsed(collapsed)

        for btn in self._submenu_buttons.values():
            btn.set_collapsed(collapsed)
            btn.setVisible(not collapsed and self._submenu_expanded)

        self.collapseChanged.emit(collapsed)
