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

from ui.main_window import MainWindow
from core.inventory import resolve_inventory_database_path


@pytest.fixture
def main_window(qapp):
    """Fixture providing a managed MainWindow instance for navigation tests."""
    db_path = resolve_inventory_database_path()
    win = MainWindow(default_file=db_path)
    win.show()
    qapp.processEvents()
    yield win
    win._is_force_closing = True
    win.close()


class TestSidebarSelectionStability:
    """Verifies that sidebar selection state is robust across all transitions, hover, and focus."""

    DESTINATIONS = [
        "assembly_view",
        "component_inventory",
        "bom_audit",
        "assembly_prep",
        "vendor_plugins",
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
        for page_id in ["component_inventory", "vendor_plugins", "assembly_view"]:
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

    def test_settings_hierarchical_parent_and_child_selection(self, main_window, qapp):
        """Settings parent remains visibly selected whenever any settings child is active."""
        win = main_window
        sb = win.sidebar

        for child_id, label, _ in sb.SETTINGS_CHILDREN:
            win._on_sidebar_page_changed(child_id)
            qapp.processEvents()

            # Parent Settings button must communicate active section
            assert sb.settings_parent_btn._is_active is True, f"Parent Settings not active on {child_id}"
            # Selected child must communicate active destination
            assert sb._submenu_buttons[child_id]._is_active is True, f"Child {child_id} not active"

            # All other children must be inactive
            for other_id, other_btn in sb._submenu_buttons.items():
                if other_id != child_id:
                    assert other_btn._is_active is False, f"Child {other_id} must be inactive when {child_id} is active"

            # Primary section buttons (Workspace/Tools) must be inactive
            for pid, btn in sb._buttons.items():
                if pid != "settings" and pid not in sb._submenu_buttons:
                    assert btn._is_active is False, f"Primary button {pid} must be inactive when in Settings section"

        # Transitioning back to Workspace clears Settings parent and child selection
        win._on_sidebar_page_changed("assembly_view")
        qapp.processEvents()
        assert sb.settings_parent_btn._is_active is False
        for btn in sb._submenu_buttons.values():
            assert btn._is_active is False
        assert sb._buttons["assembly_view"]._is_active is True

    def test_settings_submenu_toggle_cycles(self, main_window, qapp):
        """Clicking Settings repeatedly reliably opens and closes the submenu without desync."""
        win = main_window
        sb = win.sidebar

        # Ensure collapsed initially
        sb.set_submenu_expanded(False)
        qapp.processEvents()
        assert sb.is_submenu_expanded() is False

        for cycle in range(3):
            # Click 1: expands
            sb.settings_parent_btn.click()
            qapp.processEvents()
            assert sb.is_submenu_expanded() is True, f"Failed expand on cycle {cycle}"
            for btn in sb._submenu_buttons.values():
                assert btn.isVisible() is True

            # Click 2: collapses
            sb.settings_parent_btn.click()
            qapp.processEvents()
            assert sb.is_submenu_expanded() is False, f"Failed collapse on cycle {cycle}"
            for btn in sb._submenu_buttons.values():
                assert btn.isVisible() is False
