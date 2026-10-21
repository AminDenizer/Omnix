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

import os
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
        """Sidebar contains Workspace, Tools, and Settings sections and exactly 6 primary buttons."""
        sb = main_window.sidebar
        expected_keys = [
            "assembly_view",
            "component_inventory",
            "bom_audit",
            "assembly_prep",
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
        for key in ["assembly_view", "component_inventory", "bom_audit", "assembly_prep", "vendor_plugins", "settings", "general_settings"]:
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
    """Verifies settings collapsible sidebar submenu, the 5 subsections, and factual metadata in About."""

    def test_settings_subsections_structure_and_submenu(self, main_window, qapp):
        """Settings page has a collapsible sidebar submenu with 5 children and NO top tabs."""
        sb = main_window.sidebar
        assert hasattr(sb, "settings_parent_btn")
        assert hasattr(sb, "SETTINGS_CHILDREN")

        expected_children = [
            ("general_settings", "General", "general_settings"),
            ("reference_data", "Reference Data", "reference_data"),
            ("provider_management", "Supplier Directory", "provider_management"),
            ("backup_restore", "Export & Backup", "backup_restore"),
            ("about", "About", "about"),
        ]
        assert sb.SETTINGS_CHILDREN == expected_children

        # Verify all children are present in _submenu_buttons
        for child_id, label, _ in expected_children:
            assert child_id in sb._submenu_buttons
            btn = sb._submenu_buttons[child_id]
            assert label in btn.text()
            assert not btn.icon().isNull()

        # Test expand / collapse behavior and vector outline chevron indicator
        sb.set_submenu_expanded(False)
        qapp.processEvents()
        assert sb.is_submenu_expanded() is False
        assert sb.settings_parent_btn._chevron.text() == "▸"
        assert not sb.settings_parent_btn._chevron.pixmap().isNull()
        for btn in sb._submenu_buttons.values():
            assert btn.isVisible() is False

        sb.set_submenu_expanded(True)
        qapp.processEvents()
        assert sb.is_submenu_expanded() is True
        assert sb.settings_parent_btn._chevron.text() == "▾"
        assert not sb.settings_parent_btn._chevron.pixmap().isNull()
        for btn in sb._submenu_buttons.values():
            assert btn.isVisible() is True
            # Indented styling
            assert "padding-left: 24px;" in btn.styleSheet()

        # Collapsing the sidebar rail centers submenu icons without breaking layout
        sb.set_collapsed(True)
        qapp.processEvents()
        assert sb.settings_parent_btn._chevron.isVisible() is False
        for btn in sb._submenu_buttons.values():
            assert "padding-left: 0px;" in btn.styleSheet()
            assert "text-align: center;" in btn.styleSheet()

        sb.set_collapsed(False)
        qapp.processEvents()

    def test_no_tabs_across_content_area(self, main_window):
        """Settings views must render directly in main content area without a top QTabWidget."""
        from PyQt6.QtWidgets import QTabWidget
        assert not hasattr(main_window, "settings_subtabs")
        assert main_window.content_stack.currentWidget() != None
        # Verify content_stack pages for settings do not wrap themselves in a QTabWidget
        for page in (
            main_window.general_settings_page,
            main_window.reference_data_page,
            main_window.providers_page,
            main_window.backup_restore_page,
            main_window.about_page,
        ):
            assert page.findChild(QTabWidget) is None

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
        """Workspace buttons route to corresponding views in main tabs and render literal ampersand."""
        win = main_window

        # Literal ampersand check on Assembly & Stock button
        btn_assembly = win.sidebar._buttons["assembly_view"]
        assert "Assembly & Stock" in btn_assembly.text()
        assert "&" in btn_assembly.text()

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

        # 4. Restored Third Workspace Tab: Assembly & BOM Preparation
        win.sidebar._on_button_clicked("assembly_prep")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.tabs
        assert win.tabs.currentIndex() == 2
        assert "Assembly" in win.tabs.tabText(2)
        assert win.sidebar.active_page() == "assembly_prep"

    def test_tools_vendor_plugins_routing(self, main_window, qapp):
        """Vendor Plugins routes to vendor plugins page in content stack."""
        win = main_window
        win.sidebar._on_button_clicked("vendor_plugins")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.vendor_plugins_page
        assert win.sidebar.active_page() == "vendor_plugins"

    def test_settings_routing_and_legacy_aliases(self, main_window, qapp):
        """Settings button and child navigation activate individual content pages without tabs."""
        win = main_window

        # Settings top-level (activates General settings page and expands submenu)
        win.sidebar._on_button_clicked("settings")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.general_settings_page
        assert win.sidebar.active_page() == "settings"
        assert win.sidebar.settings_parent_btn._is_active is True
        assert win.sidebar._submenu_buttons["general_settings"]._is_active is True
        assert win.sidebar.is_submenu_expanded() is True

        # Child: reference_data
        win.sidebar._on_button_clicked("reference_data")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.reference_data_page
        assert win.sidebar.active_page() == "reference_data"
        assert win.sidebar.settings_parent_btn._is_active is True
        assert win.sidebar._submenu_buttons["reference_data"]._is_active is True
        assert win.sidebar._submenu_buttons["general_settings"]._is_active is False

        # Child: provider_management (Supplier Directory)
        win.sidebar._on_button_clicked("provider_management")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.providers_page
        assert win.sidebar.active_page() == "provider_management"
        assert win.sidebar.settings_parent_btn._is_active is True
        assert win.sidebar._submenu_buttons["provider_management"]._is_active is True

        # Child: backup_restore (Export & Backup)
        win.sidebar._on_button_clicked("backup_restore")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.backup_restore_page
        assert win.sidebar.active_page() == "backup_restore"
        assert win.sidebar.settings_parent_btn._is_active is True
        assert win.sidebar._submenu_buttons["backup_restore"]._is_active is True

        # Child: about
        win.sidebar._on_button_clicked("about")
        qapp.processEvents()
        assert win.content_stack.currentWidget() == win.about_page
        assert win.sidebar.active_page() == "about"
        assert win.sidebar.settings_parent_btn._is_active is True
        assert win.sidebar._submenu_buttons["about"]._is_active is True

        # Navigating back to Workspace clears settings parent active state
        win.sidebar._on_button_clicked("assembly_view")
        qapp.processEvents()
        assert win.sidebar.settings_parent_btn._is_active is False
        assert win.sidebar._submenu_buttons["about"]._is_active is False


class TestExcelExport:
    """Verifies restored Excel export button, wiring, and deterministic output."""

    def test_excel_export_action_and_path(self, main_window, tmp_path):
        """Excel export action exists, is enabled, and produces the 2-sheet specification."""
        import openpyxl
        win = main_window

        assert hasattr(win.backup_restore_widget, "export_excel_btn")
        assert win.backup_restore_widget.export_excel_btn.text() == "Export to Excel..."
        assert win.backup_restore_widget.export_excel_btn.isEnabled() is True
        assert win.export_excel_btn == win.backup_restore_widget.export_excel_btn

        # Test underlying exporter path directly to a temporary file
        out_file = str(tmp_path / "test_inventory_export.xlsx")
        from core.inventory.exporter import InventoryExcelExporter
        result = InventoryExcelExporter.export(win.inventory_repo, out_file)

        assert os.path.exists(result)
        wb = openpyxl.load_workbook(result)
        assert wb.sheetnames == ["Inventory", "Assembly View"]
        wb.close()
