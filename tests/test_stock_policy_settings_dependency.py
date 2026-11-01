"""
Focused test suite for OMNIX Stock Policy Settings, Dependency, Layout & Low-Stock Action.

Test coverage (Task D):
1. With validation enabled, the startup-check checkbox is available when permitted by the master toggle.
2. With validation disabled, the startup-check checkbox is disabled.
3. Disabling validation preserves the saved startup-check preference.
4. Re-enabling validation restores the checkbox's previous saved value.
5. The master-toggle behavior remains correct.
6. Show Matched Products in Assembly View retains its existing independent behavior.
7. If validation is disabled, automatic startup shortage checking is skipped even when its saved preference is true.
8. If validation is enabled and the saved startup preference is true, existing startup-check behavior remains intact.
9. The Order Low Stock (N) button is visible when validation is enabled and existing visibility conditions permit it.
10. The button is hidden when validation is disabled.
11. The button's visibility updates immediately after toggling validation.
12. Re-enabling validation restores the appropriate visibility without creating a duplicate button.
13. The master-toggle dependency is respected.
14. Settings control order and grouping in the general settings view.
"""

import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QPushButton, QCheckBox, QFrame

from settings_manager import settings
from ui.main_window import MainWindow
from ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def managed_window(qapp):
    """Provides a managed MainWindow instance with clean setting states restored on teardown."""
    orig_master = settings.get("stock_policy_enabled", True)
    orig_validation = settings.get("stock_policy_validation_enabled", True)
    orig_columns = settings.get("stock_policy_show_columns", True)
    orig_startup = settings.get("auto_check_startup_shortage", True)
    orig_match = settings.get("match_products_enabled", True)

    with patch.object(MainWindow, "_check_startup_shortages"), patch("PyQt6.QtCore.QTimer.singleShot"):
        win = MainWindow()
        win.show()
        qapp.processEvents()
    yield win
    win._is_force_closing = True
    win.close()

    # Restore settings
    settings.set("stock_policy_enabled", orig_master)
    settings.set("stock_policy_validation_enabled", orig_validation)
    settings.set("stock_policy_show_columns", orig_columns)
    settings.set("auto_check_startup_shortage", orig_startup)
    settings.set("match_products_enabled", orig_match)


class TestStockPolicySettingsDependency:
    """Task D1-D6: Settings dependencies and preference preservation."""

    def test_case_01_validation_enabled_allows_startup_check(self, managed_window):
        win = managed_window
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(True)

        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_startup_chk.isEnabled() is True

        dlg = SettingsDialog(win)
        dlg.stock_policy_enabled_chk.setChecked(True)
        dlg.stock_policy_validation_chk.setChecked(True)
        assert dlg.startup_chk.isEnabled() is True
        dlg.close()

    def test_case_02_validation_disabled_disables_startup_check(self, managed_window):
        win = managed_window
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(False)

        assert win.side_startup_chk.isEnabled() is False
        assert win.side_startup_chk.isChecked() is False

        dlg = SettingsDialog(win)
        dlg.stock_policy_enabled_chk.setChecked(True)
        dlg.stock_policy_validation_chk.setChecked(False)
        assert dlg.startup_chk.isEnabled() is False
        assert dlg.startup_chk.isChecked() is False
        dlg.close()

    def test_case_03_disabling_validation_preserves_saved_startup_check_preference(self, managed_window):
        win = managed_window
        # Explicitly configure startup check to True and validation to True
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", True)
        settings.set("auto_check_startup_shortage", True)
        win._sync_general_settings_page()

        assert win.side_startup_chk.isChecked() is True
        assert settings.get("auto_check_startup_shortage") is True

        # Disable validation
        win.side_stock_policy_validation_chk.setChecked(False)

        # Startup checkbox is now disabled, but saved preference MUST remain True
        assert win.side_startup_chk.isEnabled() is False
        assert settings.get("auto_check_startup_shortage") is True

        # Also verify in SettingsDialog: saving while validation is disabled preserves preference
        dlg = SettingsDialog(win)
        dlg.stock_policy_validation_chk.setChecked(False)
        assert dlg.startup_chk.isEnabled() is False
        dlg._save_and_close()

        assert settings.get("auto_check_startup_shortage") is True

    def test_case_04_reenabling_validation_restores_checkbox_value(self, managed_window):
        win = managed_window
        # Case A: Saved preference was True
        settings.set("auto_check_startup_shortage", True)
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(False)
        assert win.side_startup_chk.isEnabled() is False

        # Re-enable validation
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.side_startup_chk.isEnabled() is True
        assert win.side_startup_chk.isChecked() is True

        # Case B: Saved preference was False
        win.side_startup_chk.setChecked(False)
        assert settings.get("auto_check_startup_shortage") is False

        win.side_stock_policy_validation_chk.setChecked(False)
        assert win.side_startup_chk.isEnabled() is False

        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.side_startup_chk.isEnabled() is True
        assert win.side_startup_chk.isChecked() is False

    def test_case_05_master_toggle_authority_over_subordinate_controls(self, managed_window):
        win = managed_window
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_stock_policy_show_columns_chk.isEnabled() is True
        assert win.side_startup_chk.isEnabled() is True
        assert win.side_stock_policy_validation_chk.isChecked() is True
        assert win.side_startup_chk.isChecked() is True

        # Disabling master toggle disables all subordinates and visibly unchecks validation and startup
        win.side_stock_policy_enabled_chk.setChecked(False)
        assert win.side_stock_policy_validation_chk.isEnabled() is False
        assert win.side_stock_policy_show_columns_chk.isEnabled() is False
        assert win.side_startup_chk.isEnabled() is False
        assert win.side_stock_policy_validation_chk.isChecked() is False
        assert win.side_startup_chk.isChecked() is False

        # Re-enabling master restores validation & columns, and startup check if validation is checked
        win.side_stock_policy_enabled_chk.setChecked(True)
        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_stock_policy_show_columns_chk.isEnabled() is True
        assert win.side_startup_chk.isEnabled() is True
        assert win.side_stock_policy_validation_chk.isChecked() is True
        assert win.side_startup_chk.isChecked() is True

        # If validation was unchecked when master is re-enabled, startup check remains disabled and unchecked
        win.side_stock_policy_validation_chk.setChecked(False)
        win.side_stock_policy_enabled_chk.setChecked(False)
        assert win.side_stock_policy_validation_chk.isChecked() is False
        assert win.side_startup_chk.isChecked() is False
        win.side_stock_policy_enabled_chk.setChecked(True)
        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_stock_policy_validation_chk.isChecked() is False
        assert win.side_startup_chk.isEnabled() is False
        assert win.side_startup_chk.isChecked() is False

        # Test identical behavior in SettingsDialog
        dlg = SettingsDialog(win)
        dlg.stock_policy_enabled_chk.setChecked(True)
        dlg.stock_policy_validation_chk.setChecked(True)
        assert dlg.stock_policy_validation_chk.isEnabled() is True
        assert dlg.startup_chk.isEnabled() is True
        assert dlg.stock_policy_validation_chk.isChecked() is True
        assert dlg.startup_chk.isChecked() is True

        dlg.stock_policy_enabled_chk.setChecked(False)
        assert dlg.stock_policy_validation_chk.isEnabled() is False
        assert dlg.stock_policy_validation_chk.isChecked() is False
        assert dlg.startup_chk.isEnabled() is False
        assert dlg.startup_chk.isChecked() is False

        dlg.stock_policy_enabled_chk.setChecked(True)
        assert dlg.stock_policy_validation_chk.isEnabled() is True
        assert dlg.stock_policy_validation_chk.isChecked() is True
        assert dlg.startup_chk.isEnabled() is True
        assert dlg.startup_chk.isChecked() is True
        dlg.close()

    def test_case_06_matched_products_independent_behavior(self, managed_window):
        win = managed_window
        # Master and validation both disabled
        win.side_stock_policy_enabled_chk.setChecked(False)
        win.side_stock_policy_validation_chk.setChecked(False)

        # Match products must remain enabled and togglable
        assert win.side_match_products_chk.isEnabled() is True

        win.side_match_products_chk.setChecked(False)
        assert settings.get("match_products_enabled") is False

        win.side_match_products_chk.setChecked(True)
        assert settings.get("match_products_enabled") is True

    def test_case_06b_dependent_checkbox_visual_and_interactive_lifecycle(self, managed_window):
        win = managed_window
        # Start in fully-enabled state
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", True)
        settings.set("auto_check_startup_shortage", True)
        settings.set("match_products_enabled", True)
        win._sync_general_settings_page()

        assert win.side_stock_policy_enabled_chk.isChecked() is True
        assert win.side_stock_policy_validation_chk.isChecked() is True
        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_startup_chk.isChecked() is True
        assert win.side_startup_chk.isEnabled() is True
        assert win.side_match_products_chk.isChecked() is True

        # 1. Uncheck master -> both validation and startup visibly appear unchecked and disabled
        win.side_stock_policy_enabled_chk.setChecked(False)
        assert win.side_stock_policy_validation_chk.isChecked() is False
        assert win.side_stock_policy_validation_chk.isEnabled() is False
        assert win.side_startup_chk.isChecked() is False
        assert win.side_startup_chk.isEnabled() is False
        # Match products unaffected
        assert win.side_match_products_chk.isChecked() is True
        assert win.side_match_products_chk.isEnabled() is True
        # Saved preferences remain True
        assert settings.get("stock_policy_validation_enabled") is True
        assert settings.get("auto_check_startup_shortage") is True

        # 2. Re-enable master -> restores both
        win.side_stock_policy_enabled_chk.setChecked(True)
        assert win.side_stock_policy_validation_chk.isChecked() is True
        assert win.side_stock_policy_validation_chk.isEnabled() is True
        assert win.side_startup_chk.isChecked() is True
        assert win.side_startup_chk.isEnabled() is True

        # 3. Explicitly uncheck startup check (user preference = False)
        win.side_startup_chk.setChecked(False)
        assert settings.get("auto_check_startup_shortage") is False

        # 4. Uncheck validation -> startup appears unchecked and disabled
        win.side_stock_policy_validation_chk.setChecked(False)
        assert win.side_stock_policy_validation_chk.isChecked() is False
        assert win.side_startup_chk.isChecked() is False
        assert win.side_startup_chk.isEnabled() is False

        # 5. Re-enable validation -> startup restores its saved preference (False) and enabled
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.side_stock_policy_validation_chk.isChecked() is True
        assert win.side_startup_chk.isChecked() is False
        assert win.side_startup_chk.isEnabled() is True

        # Verify lifecycle across SettingsDialog
        dlg = SettingsDialog(win)
        dlg.stock_policy_enabled_chk.setChecked(False)
        assert dlg.stock_policy_validation_chk.isChecked() is False
        assert dlg.stock_policy_validation_chk.isEnabled() is False
        assert dlg.startup_chk.isChecked() is False
        assert dlg.startup_chk.isEnabled() is False
        assert dlg.match_products_chk.isEnabled() is True
        dlg.stock_policy_enabled_chk.setChecked(True)
        assert dlg.stock_policy_validation_chk.isChecked() is True
        assert dlg.stock_policy_validation_chk.isEnabled() is True
        # Startup restores previous preference of False
        assert dlg.startup_chk.isChecked() is False
        assert dlg.startup_chk.isEnabled() is True
        dlg.close()


class TestStartupExecutionDependency:
    """Task D7-D8: Actual startup execution check enforcement."""

    def test_case_07_startup_shortage_check_skipped_when_validation_disabled(self, managed_window):
        win = managed_window
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", False)
        settings.set("auto_check_startup_shortage", True)

        with patch("ui.main_window.OrderPreviewDialog") as mock_preview_dlg:
            win._check_startup_shortages()
            assert not mock_preview_dlg.called

        # Also when master toggle is disabled
        settings.set("stock_policy_enabled", False)
        settings.set("stock_policy_validation_enabled", True)
        settings.set("auto_check_startup_shortage", True)

        with patch("ui.main_window.OrderPreviewDialog") as mock_preview_dlg:
            win._check_startup_shortages()
            assert not mock_preview_dlg.called

    def test_case_08_startup_shortage_check_runs_when_validation_enabled(self, managed_window):
        win = managed_window
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", True)
        settings.set("auto_check_startup_shortage", True)

        # Provide simulated shortages
        mock_items = [{"Category": "Capacitor", "Part Number": "TEST-100NF"}]
        with patch.object(win, "_get_stock_policy_replenishment_items", return_value=mock_items), \
             patch("ui.main_window.OrderPreviewDialog") as mock_preview_dlg:
            win._check_startup_shortages()
            assert mock_preview_dlg.called


class TestHeaderActionLowStockVisibility:
    """Task D9-D13: Order Low Stock action visibility rules and reactivity."""

    def test_case_09_button_visible_when_validation_enabled(self, managed_window):
        win = managed_window
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", True)
        win._update_stats_ribbon()

        assert win.stats_ribbon.order_shortages_btn.isVisible() is True

    def test_case_10_button_hidden_when_validation_disabled(self, managed_window):
        win = managed_window
        settings.set("stock_policy_enabled", True)
        settings.set("stock_policy_validation_enabled", False)
        win._update_stats_ribbon()

        assert win.stats_ribbon.order_shortages_btn.isVisible() is False

    def test_case_11_button_visibility_updates_immediately_on_toggle(self, managed_window):
        win = managed_window
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is True

        # Toggle validation checkbox OFF
        win.side_stock_policy_validation_chk.setChecked(False)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is False

        # Toggle validation checkbox ON
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is True

    def test_case_12_reenabling_validation_restores_button_without_duplicate(self, managed_window):
        win = managed_window
        initial_btn = win.stats_ribbon.order_shortages_btn
        initial_buttons_count = len(win.stats_ribbon.findChildren(QPushButton))

        # Toggle off and on repeatedly
        for _ in range(3):
            win.side_stock_policy_validation_chk.setChecked(False)
            assert win.stats_ribbon.order_shortages_btn.isVisible() is False
            win.side_stock_policy_validation_chk.setChecked(True)
            assert win.stats_ribbon.order_shortages_btn.isVisible() is True

        # Exactly the same widget instance retained, no duplicate buttons
        assert win.stats_ribbon.order_shortages_btn is initial_btn
        assert len(win.stats_ribbon.findChildren(QPushButton)) == initial_buttons_count

    def test_case_13_master_toggle_dependency_respected_for_shortages_button(self, managed_window):
        win = managed_window
        win.side_stock_policy_enabled_chk.setChecked(True)
        win.side_stock_policy_validation_chk.setChecked(True)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is True

        # Unchecking master toggle hides the button even if validation checkbox is True
        win.side_stock_policy_enabled_chk.setChecked(False)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is False

        # Re-enabling master restores button visibility
        win.side_stock_policy_enabled_chk.setChecked(True)
        assert win.stats_ribbon.order_shortages_btn.isVisible() is True


class TestSettingsLayoutHierarchy:
    """Task D14: Layout order and grouping of General Settings controls."""

    def test_case_14_settings_control_order_and_grouping(self, managed_window):
        win = managed_window

        # Verify all required controls exist on the page
        assert isinstance(win.side_stock_policy_enabled_chk, QCheckBox)
        assert isinstance(win.side_stock_policy_validation_chk, QCheckBox)
        assert isinstance(win.side_stock_policy_show_columns_chk, QCheckBox)
        assert isinstance(win.side_stock_policy_divider, QFrame)
        assert isinstance(win.side_startup_chk, QCheckBox)
        assert isinstance(win.side_match_products_chk, QCheckBox)

        # Verify exact labels
        assert win.side_stock_policy_enabled_chk.text() == "Enable stock-policy features"
        assert win.side_stock_policy_validation_chk.text() == "Enable stock-policy validation / shortage checking"
        assert win.side_stock_policy_show_columns_chk.text() == "Show Min Stock and Target Stock columns in Component Inventory"
        assert win.side_startup_chk.text() == "Automatically check inventory shortages on application startup"
        assert win.side_match_products_chk.text() == "Show Matched Products in Assembly View"

        # Verify hierarchical layout order within general_settings_page
        card = win.general_settings_page.findChild(QFrame, "cardFrame")
        assert card is not None
        card_layout = card.layout()

        # Item 0 in card layout is the Master Checkbox (1. Enable stock-policy features)
        assert card_layout.itemAt(0).widget() is win.side_stock_policy_enabled_chk

        # Sub-layout contains stock policy sub-controls
        sub_layout = card_layout.itemAt(1).layout()
        assert sub_layout is not None
        sub_widgets = [sub_layout.itemAt(i).widget() for i in range(sub_layout.count()) if sub_layout.itemAt(i).widget()]
        assert win.side_stock_policy_validation_chk in sub_widgets
        assert win.side_startup_chk in sub_widgets
        assert win.side_stock_policy_show_columns_chk in sub_widgets

        # Divider follows immediately after the stock-policy group
        outer_widgets = [card_layout.itemAt(i).widget() for i in range(card_layout.count()) if card_layout.itemAt(i).widget()]
        assert win.side_stock_policy_divider in outer_widgets
