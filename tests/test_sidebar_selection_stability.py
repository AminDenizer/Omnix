"""
Regression tests for sidebar persistent selection state stability in Omnix.
Verifies that:
1. Navigating across all sidebar destinations in arbitrary sequences never desynchronizes the active button.
2. Hovering or focusing inactive buttons never paints or steals the active cyan selection indicator.
3. Collapsing and expanding the sidebar preserves the active selection state.
4. Subtab changes synchronize with the sidebar state reliably.
"""

import pytest
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QEnterEvent

from unittest.mock import patch
from ui.main_window import MainWindow
from core.inventory import resolve_database_path


@pytest.fixture
def main_window(qapp):
    """Fixture providing a managed MainWindow instance for navigation tests."""
    with patch.object(MainWindow, "_check_startup_shortages"):
        win = MainWindow()
        win.show()
        qapp.processEvents()
        yield win
        win._is_force_closing = True
        win.close()


class TestSidebarSelectionStability:
    """Verifies that sidebar selection state is robust across all transitions, hover, and focus."""

    DESTINATIONS = [
        "component_inventory",
        "assembly_view",
        "bom_audit",
        "assembly_prep",
        "reference_data",
        "provider_management",
        "backup_restore",
        "live_log",
        "settings",
    ]

    def test_pairwise_navigation_matrix(self, main_window, qapp):
        """All pairwise transitions between sidebar pages must leave the correct button active."""
        win = main_window

        for src in self.DESTINATIONS:
            win.sidebar._on_button_clicked(src)
            qapp.processEvents()
            assert win.sidebar.active_page() == src

            for dst in self.DESTINATIONS:
                win.sidebar._on_button_clicked(dst)
                qapp.processEvents()

                # Authoritative active page check
                assert win.sidebar.active_page() == dst, f"Failed transition {src} -> {dst}"

                # Exactly one button must be active
                active_buttons = [pid for pid, btn in win.sidebar._buttons.items() if btn._is_active]
                assert active_buttons == [dst], f"Expected only [{dst}] active, got {active_buttons}"

    def test_hovering_inactive_item_does_not_mutate_persistent_selection(self, main_window, qapp):
        """Hovering over inactive buttons must illuminate hover state without altering persistent selection."""
        win = main_window
        win.sidebar.set_active_page("assembly_view")
        qapp.processEvents()

        active_btn = win.sidebar._buttons["assembly_view"]
        inactive_btn = win.sidebar._buttons["bom_audit"]

        assert active_btn._is_active is True
        assert inactive_btn._is_active is False

        # Simulate mouse enter on inactive button
        enter_ev = QEnterEvent(QPointF(10.0, 10.0), QPointF(10.0, 10.0), QPointF(10.0, 10.0))
        inactive_btn.enterEvent(enter_ev)
        qapp.processEvents()

        # Selection must remain firmly on assembly_view
        assert win.sidebar.active_page() == "assembly_view"
        assert active_btn._is_active is True
        assert inactive_btn._is_active is False
        assert "border-left: 2px solid #38bdf8" in active_btn.styleSheet()
        assert "border-left: 2px solid transparent" in inactive_btn.styleSheet()

        # Simulate mouse leave
        leave_ev = QEvent(QEvent.Type.Leave)
        inactive_btn.leaveEvent(leave_ev)
        qapp.processEvents()

        assert win.sidebar.active_page() == "assembly_view"
        assert active_btn._is_active is True
        assert inactive_btn._is_active is False

    def test_focus_does_not_paint_active_border_on_inactive_button(self, main_window, qapp):
        """Keyboard focus on an inactive button must not display the active cyan left border."""
        win = main_window
        win.sidebar.set_active_page("settings")
        qapp.processEvents()

        inactive_btn = win.sidebar._buttons["assembly_view"]
        inactive_btn.setFocus()
        qapp.processEvents()

        # Inactive button's stylesheet must not contain active border-left: 2px solid #38bdf8
        sheet = inactive_btn.styleSheet()
        assert "border-left: 2px solid #38bdf8" not in sheet
        assert "border-left: 2px solid transparent" in sheet

    def test_collapse_and_expand_preserves_selection(self, main_window, qapp):
        """Toggling between collapsed and expanded rail must preserve active selection and tooltips."""
        win = main_window
        for page_id in ["component_inventory", "assembly_view", "settings"]:
            win.sidebar._on_button_clicked(page_id)
            qapp.processEvents()

            # Collapse
            win.sidebar.set_collapsed(True)
            qapp.processEvents()
            assert win.sidebar.is_collapsed() is True
            assert win.sidebar.active_page() == page_id
            assert win.sidebar._buttons[page_id]._is_active is True

            # Expand
            win.sidebar.set_collapsed(False)
            qapp.processEvents()
            assert win.sidebar.is_collapsed() is False
            assert win.sidebar.active_page() == page_id
            assert win.sidebar._buttons[page_id]._is_active is True

    def test_subtab_switch_synchronizes_sidebar(self, main_window, qapp):
        """Switching inventory subtabs directly synchronizes sidebar active state."""
        win = main_window
        win.content_stack.setCurrentWidget(win.tabs)
        win.tabs.setCurrentIndex(0)
        qapp.processEvents()

        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()
        assert win.sidebar.active_page() == "component_inventory"
        assert win.sidebar._buttons["component_inventory"]._is_active is True

        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.sidebar.active_page() == "assembly_view"
        assert win.sidebar._buttons["assembly_view"]._is_active is True

    def test_settings_unified_tabs_and_selection(self, main_window, qapp):
        """Settings entry in sidebar opens unified interface with General, Vendors, and About tabs."""
        win = main_window
        sb = win.sidebar

        # 1. Clicking Settings opens the unified Settings view
        win.sidebar._on_button_clicked("settings")
        qapp.processEvents()
        assert sb.active_page() == "settings"
        assert win.content_stack.currentWidget() == win.settings_page
        assert hasattr(win, "settings_tabs")
        assert win.settings_tabs.count() == 3
        assert win.settings_tabs.tabText(0) == "General"
        assert win.settings_tabs.tabText(1) == "Vendors"
        assert win.settings_tabs.tabText(2) == "About"

        # 2. Accessing Vendors section routes to Tab 1
        win._open_settings("vendors")
        qapp.processEvents()
        assert sb.active_page() == "settings"
        assert win.settings_tabs.currentIndex() == 1

        # 3. Accessing About section routes to Tab 2
        win._open_settings("about")
        qapp.processEvents()
        assert sb.active_page() == "settings"
        assert win.settings_tabs.currentIndex() == 2

        # 4. Accessing General section routes to Tab 0
        win._open_settings("general")
        qapp.processEvents()
        assert sb.active_page() == "settings"
        assert win.settings_tabs.currentIndex() == 0

        # 5. Transitioning back to Workspace clears Settings selection
        win._on_sidebar_page_changed("component_inventory")
        qapp.processEvents()
        assert sb._buttons["settings"]._is_active is False
        assert sb._buttons["component_inventory"]._is_active is True
