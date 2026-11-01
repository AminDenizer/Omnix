"""
Omnix Test Suite — Unified Browser Automation Settings Tests
Governing Specification: Phase 9 / 11 Browser Automation Settings (Chrome, Edge, Firefox)
"""

import pytest
from unittest.mock import MagicMock, patch

from core.browser_detection import BrowserDetectionService, BrowserInfo, BrowserFactory
from core.models import AdapterConfig, SessionContinuityMode
from core.inventory.repository import SqliteInventoryRepository
from settings_manager import SettingsManager, settings
from ui.dialogs.settings_dialog import SettingsDialog
from ui.main_window import MainWindow
from vendors.lion.session import LionSessionManager
from vendors.javan.session import JavanSessionManager
from vendors.roboeq.session import RoboEqSessionManager


class TestBrowserDetectionAndConfiguration:
    """Verifies browser detection, driver compatibility checks, and settings UI."""

    def test_browser_detection_service(self):
        detected = BrowserDetectionService.detect_all()
        assert "chrome" in detected
        assert "edge" in detected
        assert "firefox" in detected

        for b_id, info in detected.items():
            assert isinstance(info, BrowserInfo)
            assert info.browser_id == b_id

    def test_get_preferred_browser_logic(self):
        pref_chrome = BrowserDetectionService.get_preferred_browser({"browser_type": "chrome"})
        assert pref_chrome == "chrome"

        pref_edge = BrowserDetectionService.get_preferred_browser({"browser_type": "edge"})
        assert pref_edge == "edge"

        pref_firefox = BrowserDetectionService.get_preferred_browser({"browser_type": "firefox"})
        assert pref_firefox == "firefox"

        # Default fallback
        pref_default = BrowserDetectionService.get_preferred_browser({})
        assert pref_default in ("chrome", "edge", "firefox")

    def test_settings_dialog_browser_controls_and_persistence(self, qapp, tmp_path):
        fake_settings_file = tmp_path / "test_settings.json"
        fake_settings = SettingsManager(str(fake_settings_file))

        with patch("ui.dialogs.settings_dialog.settings", fake_settings):
            dlg = SettingsDialog(initial_tab="general")

            assert hasattr(dlg, "browser_combo")
            assert hasattr(dlg, "browser_status_lbl")
            assert hasattr(dlg, "browser_headless_chk")

            # Select Firefox (Edge was removed from supported browsers to avoid automation conflict)
            ff_idx = dlg.browser_combo.findData("firefox")
            if ff_idx >= 0:
                dlg.browser_combo.setCurrentIndex(ff_idx)

            # Toggle headless
            dlg.browser_headless_chk.setChecked(False)

            # Save and verify settings persisted in isolated settings manager
            dlg._save_and_close()
            assert fake_settings.get("browser_type") == "firefox"
            assert fake_settings.get("browser_headless") is False

    def test_embedded_general_settings_page_controls_and_sync(self, qapp, tmp_path):
        fake_settings_file = tmp_path / "test_settings_embedded.json"
        fake_settings = SettingsManager(str(fake_settings_file))
        fake_settings.set("browser_type", "firefox")
        fake_settings.set("browser_headless", False)

        test_db = tmp_path / "embedded_inv.db"
        clean_repo = SqliteInventoryRepository(str(test_db))

        with patch("ui.main_window.settings", fake_settings), \
             patch("settings_manager.settings", fake_settings):
            win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
            win.show()
            qapp.processEvents()

            assert hasattr(win, "side_browser_combo")
            assert hasattr(win, "side_browser_status_lbl")
            assert hasattr(win, "side_browser_headless_chk")

            # Check that initial values were synced from settings
            assert win.side_browser_combo.currentData() == "firefox"
            assert win.side_browser_headless_chk.isChecked() is False

            # Switch to Chrome in UI
            chrome_idx = win.side_browser_combo.findData("chrome")
            win.side_browser_combo.setCurrentIndex(chrome_idx)
            assert fake_settings.get("browser_type") == "chrome"

            # Check headless
            win.side_browser_headless_chk.setChecked(True)
            assert fake_settings.get("browser_headless") is True

            win._is_force_closing = True
            win.close()


class TestBrowserFactoryAndVendorIntegration:
    """Verifies BrowserFactory resolution, driver instantiation, and vendor session integration."""

    def test_browser_factory_resolution_priority(self, tmp_path):
        fake_settings = SettingsManager(str(tmp_path / "s.json"))
        fake_settings.set("browser_type", "firefox")
        fake_settings.set("browser_headless", False)

        with patch("settings_manager.settings", fake_settings):
            # Explicit overrides settings
            assert BrowserFactory.resolve_browser_type("edge") == "edge"
            assert BrowserFactory.resolve_headless(True) is True
            assert BrowserFactory.resolve_headless(False) is False

            # If explicit is None, reads settings
            assert BrowserFactory.resolve_browser_type(None) == "firefox"
            assert BrowserFactory.resolve_headless(None) is False

    def test_browser_factory_chrome_creation(self):
        with patch.object(BrowserDetectionService, "detect_browser", return_value=BrowserInfo("chrome", "Chrome", True)), \
             patch("selenium.webdriver.Chrome") as mock_chrome:
            mock_inst = MagicMock()
            mock_chrome.return_value = mock_inst

            driver = BrowserFactory.create_driver(browser_type="chrome", headless=True)
            assert driver is mock_inst
            mock_chrome.assert_called_once()
            mock_inst.implicitly_wait.assert_called_once()

    def test_browser_factory_edge_creation(self):
        with patch.object(BrowserDetectionService, "detect_browser", return_value=BrowserInfo("edge", "Edge", True)), \
             patch("selenium.webdriver.Edge") as mock_edge:
            mock_inst = MagicMock()
            mock_edge.return_value = mock_inst

            driver = BrowserFactory.create_driver(browser_type="edge", headless=False)
            assert driver is mock_inst
            mock_edge.assert_called_once()
            mock_inst.implicitly_wait.assert_called_once()

    def test_browser_factory_firefox_creation(self):
        with patch.object(BrowserDetectionService, "detect_browser", return_value=BrowserInfo("firefox", "Firefox", True)), \
             patch("selenium.webdriver.Firefox") as mock_ff:
            mock_inst = MagicMock()
            mock_ff.return_value = mock_inst

            driver = BrowserFactory.create_driver(browser_type="firefox", headless=True)
            assert driver is mock_inst
            mock_ff.assert_called_once()
            mock_inst.implicitly_wait.assert_called_once()

    def test_browser_factory_uninstalled_browser_raises_runtime_error(self):
        with patch.object(BrowserDetectionService, "detect_browser", return_value=BrowserInfo("firefox", "Mozilla Firefox", False)):
            with pytest.raises(RuntimeError) as exc_info:
                BrowserFactory.create_driver(browser_type="firefox")
            assert "not installed on this system" in str(exc_info.value)

    def test_vendor_session_integration_lion(self):
        session = LionSessionManager()
        with patch.object(BrowserFactory, "create_driver") as mock_factory:
            mock_driver = MagicMock()
            mock_factory.return_value = mock_driver

            d = session.create_driver()
            assert d is mock_driver
            mock_factory.assert_called_once()

    def test_vendor_session_integration_javan(self):
        session = JavanSessionManager()
        with patch.object(BrowserFactory, "create_driver") as mock_factory:
            mock_driver = MagicMock()
            mock_factory.return_value = mock_driver

            d = session.create_driver()
            assert d is mock_driver
            mock_factory.assert_called_once()

    def test_vendor_session_integration_roboeq(self):
        session = RoboEqSessionManager()
        with patch.object(BrowserFactory, "create_driver") as mock_factory:
            mock_driver = MagicMock()
            mock_factory.return_value = mock_driver

            d = session.create_driver()
            assert d is mock_driver
            mock_factory.assert_called_once()

    def test_session_promotion_contract_uses_factory(self):
        session = LionSessionManager()
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = [{"name": "auth", "value": "123"}]
        mock_driver.current_url = "https://lionelectronic.ir/account"
        session.driver = mock_driver

        with patch.object(session, "create_driver") as mock_create:
            mock_new_driver = MagicMock()
            mock_create.return_value = mock_new_driver

            res = session.promote_to_headful()
            assert res.success is True
            assert res.continuity_mode == SessionContinuityMode.STATE_TRANSFERRED
            assert session.config.headless is False
            mock_create.assert_called_once()
