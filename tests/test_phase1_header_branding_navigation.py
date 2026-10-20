"""
Tests for OMNIX Phase 1: Header, Branding & Navigation Refactoring.

Verifies:
1. Header & Title Bar: OMNIX wordmark, subtle separator, frameless hamburger, window controls.
2. Removal of redundant in-content header, maximizing vertical workspace.
3. Sidebar Structure: 3-section hierarchy (WORKSPACE, TOOLS, SETTINGS).
4. 5 primary destinations (Assembly & Stock, Component Inventory, BOM Audit, Vendor Plugins, Settings).
5. Outline icon consistency (24x24 viewBox, 1.8 stroke, fill="none", no emojis).
6. Subtle active button styling (neutral dark background, slim 2px indicator).
7. Settings Subsections: General, Reference Data, Supplier Directory, Backup & Restore, About.
8. About Section: Application logo, factual project metadata (Amin Denizer / DOT, MIT, Mode A).
9. Full navigation routing between Workspace, Tools, and Settings.
"""

import pytest
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QApplication, QLabel

from config import (
    APP_NAME,
    APP_VERSION,
    DEVELOPER_NAME,
    DEVELOPER_ORG,
    DEVELOPER_EMAIL,
    REPOSITORY_URL,
    LICENSE_TYPE,
)
from core.inventory import resolve_inventory_database_path
from ui.main_window import MainWindow
from ui.widgets.sidebar import (
    CollapsibleSidebar,
    SidebarNavButton,
    SIDEBAR_ICON_SVGS,
)


@pytest.fixture
def main_window(qapp):
    """Fixture providing an instance of MainWindow with clean teardown."""
    db_path = resolve_inventory_database_path()
    win = MainWindow(default_file=db_path)
    win.show()
    qapp.processEvents()
    yield win
    win._is_force_closing = True
    win.close()


class TestHeaderAndBranding:
    """Verifies title bar ordering, separator, frameless toggle, and reclaimed space."""

    def test_title_bar_header_order(self, main_window):
        """Title bar order must be: wordmark -> separator -> hamburger -> stretch -> actions -> controls."""
        tb = main_window.title_bar
        layout = tb.layout()
        items = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]

        assert tb.title_lbl in items
        assert tb.sep in items
        assert tb.hamburger_btn in items

        idx_wordmark = items.index(tb.title_lbl)
        idx_sep = items.index(tb.sep)
        idx_hamb = items.index(tb.hamburger_btn)

        assert idx_wordmark < idx_sep < idx_hamb
        assert "OMNIX" in tb.title_lbl.text()
        assert "|" in tb.sep.text()

    def test_hamburger_resting_frameless_appearance(self, main_window):
        """Hamburger button has transparent background and no persistent frame in resting state."""
        tb = main_window.title_bar
        sheet = tb.hamburger_btn.styleSheet()
        assert "background-color: transparent;" in sheet
        assert "border: none;" in sheet
        assert "outline: none;" in sheet

    def test_no_redundant_in_content_header(self, main_window):
        """Central widget layout must not contain redundant graphic logo/title banner above content."""
        central = main_window.centralWidget()
        layout = central.layout()
        assert layout.contentsMargins().top() == 0
        assert layout.spacing() == 0
        # No duplicate brand banner label exists directly in main_layout
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, QLabel) and "Omnix" in w.text():
                pytest.fail("Found redundant in-content brand header widget in central layout")


class TestSidebarHierarchyAndIcons:
    """Verifies 3-section sidebar hierarchy, primary navigation keys, outline icons, and styling."""

    def test_primary_destinations_and_sections(self, main_window):
        """Sidebar contains Workspace, Tools, and Settings sections and exactly 5 primary buttons."""
        sb = main_window.sidebar
        expected_keys = [
            "assembly_view",
            "component_inventory",
            "bom_audit",
            "vendor_plugins",
            "settings",
        ]
        assert [p[0] for p in sb.PAGES] == expected_keys
        for key in expected_keys:
            assert key in sb._buttons

        # Verify section headers exist
        assert len(sb._section_headers) == 3
        section_texts = [h.text() for h in sb._section_headers]
        assert "WORKSPACE" in section_texts
        assert "TOOLS" in section_texts
        assert "SETTINGS" in section_texts

    def test_all_sidebar_icons_are_clean_outlines(self):
        """All primary outline SVGs must use stroke-width 1.8, fill=none, and viewBox 0 0 24 24."""
        for key in ["assembly_view", "component_inventory", "bom_audit", "vendor_plugins", "settings"]:
            assert key in SIDEBAR_ICON_SVGS
            svg = SIDEBAR_ICON_SVGS[key]
            assert 'viewBox="0 0 24 24"' in svg
            assert 'stroke-width="1.8"' in svg
            assert 'fill="none"' in svg

    def test_active_button_styling(self, main_window, qapp):
        """Active selection uses subtle neutral dark background and slim 2px indicator."""
        sb = main_window.sidebar
        sb.set_active_page("assembly_view")
        qapp.processEvents()

        btn = sb._buttons["assembly_view"]
        assert btn._is_active is True
        sheet = btn.styleSheet()
        assert "border-left: 2px solid #38bdf8;" in sheet
        assert "background-color: #1e293b;" in sheet

        # Inactive button has transparent border
        inactive_btn = sb._buttons["component_inventory"]
        assert inactive_btn._is_active is False
        assert "border-left: 2px solid transparent;" in inactive_btn.styleSheet()

    def test_collapse_toggle_hides_headers(self, main_window, qapp):
        """Collapsing sidebar hides section headers; expanding restores them."""
        sb = main_window.sidebar
        sb.set_collapsed(False)
        qapp.processEvents()
        for h in sb._section_headers:
            assert h.isVisible() is True

        sb.set_collapsed(True)
        qapp.processEvents()
        for h in sb._section_headers:
            assert h.isVisible() is False


class TestSettingsSubsectionsAndAbout:
    """Verifies settings tab container, the 5 subsections, and factual metadata in About."""

    def test_settings_subsections_structure(self, main_window):
        """Settings page contains 5 subtabs: General, Reference Data, Supplier Directory, Backup & Restore, About."""
        assert hasattr(main_window, "settings_subtabs")
        tabs = main_window.settings_subtabs
        assert tabs.count() == 5
        tab_titles = [tabs.tabText(i) for i in range(tabs.count())]
        assert tab_titles == [
            "General",
            "Reference Data",
            "Supplier Directory",
            "Backup & Restore",
            "About",
        ]

    def test_about_page_metadata_and_factual_integrity(self, main_window):
        """About page displays app logo, verified metadata, and uninvented project details."""
        about = main_window.about_page
        text_content = ""
        for lbl in about.findChildren(QLabel):
            text_content += " " + lbl.text()

        assert APP_NAME in text_content
        assert APP_VERSION in text_content
        assert DEVELOPER_NAME in text_content
        assert DEVELOPER_ORG in text_content
        assert DEVELOPER_EMAIL in text_content
        assert REPOSITORY_URL in text_content
        assert LICENSE_TYPE in text_content
        assert "Mode A" in text_content


class TestNavigationRouting:
    """Verifies page routing across Workspace, Tools, and Settings."""

    def test_workspace_navigation_routing(self, main_window, qapp):
        """Workspace buttons route to corresponding views in main tabs."""
        win = main_window

        # 1. Assembly & Stock
        win.sidebar._on_button_clicked("assembly_view")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.tabs
        assert win.tabs.currentIndex() == 0
        assert win.inventory_subtabs.currentIndex() == 0

        # 2. Component Inventory
        win.sidebar._on_button_clicked("component_inventory")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.tabs
        assert win.tabs.currentIndex() == 0
        assert win.inventory_subtabs.currentIndex() == 1

        # 3. BOM Audit
        win.sidebar._on_button_clicked("bom_audit")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.tabs
        assert win.tabs.currentIndex() == 1

    def test_tools_vendor_plugins_routing(self, main_window, qapp):
        """Vendor Plugins routes to vendor plugins page in content stack."""
        win = main_window
        win.sidebar._on_button_clicked("vendor_plugins")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.vendor_plugins_page
        assert win.sidebar.active_page() == "vendor_plugins"

    def test_settings_routing_and_legacy_aliases(self, main_window, qapp):
        """Settings button and legacy aliases activate settings page and appropriate subsection."""
        win = main_window

        # Settings top-level
        win.sidebar._on_button_clicked("settings")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.settings_page
        assert win.settings_subtabs.currentIndex() == 0
        assert win.sidebar.active_page() == "settings"

        # Legacy alias: reference_data
        win._on_sidebar_page_changed("reference_data")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.settings_page
        assert win.settings_subtabs.currentIndex() == 1
        assert win.sidebar.active_page() == "settings"

        # Legacy alias: provider_management
        win._on_sidebar_page_changed("provider_management")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.settings_page
        assert win.settings_subtabs.currentIndex() == 2
        assert win.sidebar.active_page() == "settings"

        # Legacy alias: backup_restore
        win._on_sidebar_page_changed("backup_restore")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.settings_page
        assert win.settings_subtabs.currentIndex() == 3
        assert win.sidebar.active_page() == "settings"
