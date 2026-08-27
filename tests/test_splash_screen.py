import pytest
from PyQt6.QtCore import Qt
from ui.splash_screen import SplashScreen


class TestSplashScreen:
    """Test suite for Omnix startup splash screen."""

    def test_splash_screen_initialization(self, qapp):
        splash = SplashScreen(total_duration_ms=1000)
        assert splash is not None
        assert splash.windowFlags() & Qt.WindowType.SplashScreen
        assert splash.windowFlags() & Qt.WindowType.FramelessWindowHint

        # Check card contains Omnix title
        title_found = False
        dev_credit_found = False
        lightning_found = False

        for child in splash.findChildren(object):
            text = getattr(child, "text", lambda: "")()
            if "Omnix" in text:
                title_found = True
            if "AminDenizer" in text and "DOT" in text:
                dev_credit_found = True
            if "⚡" in text:
                lightning_found = True

        assert title_found is True, "Omnix title not found in splash screen"
        assert dev_credit_found is True, "Developer credit not found in splash screen"
        assert lightning_found is False, "Lightning bolt icon should not be present in splash screen"

    def test_splash_progress_update_stages(self, qapp):
        splash = SplashScreen(total_duration_ms=1000)
        
        # Test progress at 10%
        splash.current_progress = 10
        splash._update_progress()
        assert "پایگاه داده" in splash.status_lbl.text()

        # Test progress at 50%
        splash.current_progress = 50
        splash._update_progress()
        assert "دسته‌بندی‌ها" in splash.status_lbl.text()

        # Test progress at 80%
        splash.current_progress = 80
        splash._update_progress()
        assert "رابط کاربری" in splash.status_lbl.text()

        # Test progress at 100%
        splash.current_progress = 100
        splash._update_progress()
        assert "راه‌اندازی کامل" in splash.status_lbl.text()
        splash.close()
