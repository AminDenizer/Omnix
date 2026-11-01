"""
Omnix Core — Browser Automation Detection and Configuration
Governing Specification: Phase 9 Browser Automation Settings

Detects supported desktop browsers (Chrome, Edge, Firefox), checks driver compatibility,
and provides unified configuration for headless and headed automation sessions.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class BrowserInfo:
    browser_id: str
    display_name: str
    is_installed: bool
    executable_path: Optional[str] = None
    version: Optional[str] = None
    driver_supported: bool = True
    status_message: str = ""


class BrowserDetectionService:
    """Service detecting installed web browsers and driver compatibility."""

    WINDOWS_SEARCH_PATHS = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ],
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        ],
    }

    CLI_NAMES = {
        "chrome": ["chrome", "google-chrome", "google-chrome-stable"],
        "edge": ["msedge", "microsoft-edge"],
        "firefox": ["firefox"],
    }

    @classmethod
    def detect_browser(cls, browser_id: str) -> BrowserInfo:
        """Detect whether a specific browser is installed on the local system."""
        b_id = browser_id.lower().strip()
        names = {
            "chrome": "Google Chrome",
            "edge": "Microsoft Edge",
            "firefox": "Mozilla Firefox",
        }
        disp_name = names.get(b_id, b_id.title())

        # Check explicit paths
        exe_path = None
        if sys.platform == "win32":
            candidate_paths = cls.WINDOWS_SEARCH_PATHS.get(b_id, [])
            for p in candidate_paths:
                if p and os.path.isfile(p):
                    exe_path = p
                    break

        # Check PATH
        if not exe_path:
            for cli_cmd in cls.CLI_NAMES.get(b_id, []):
                found = shutil.which(cli_cmd)
                if found and os.path.isfile(found):
                    exe_path = found
                    break

        if not exe_path:
            return BrowserInfo(
                browser_id=b_id,
                display_name=disp_name,
                is_installed=False,
                status_message="Not detected on host system",
            )

        # Attempt to read version safely without launching UI
        version = None
        try:
            if sys.platform == "win32":
                import winreg
                reg_keys = {
                    "chrome": r"Software\Google\Chrome\BLBeacon",
                    "edge": r"Software\Microsoft\Edge\BLBeacon",
                }
                if b_id in reg_keys:
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_keys[b_id]) as key:
                            version, _ = winreg.QueryValueEx(key, "version")
                    except Exception:
                        pass
        except Exception:
            pass

        ver_str = f" (v{version})" if version else ""
        return BrowserInfo(
            browser_id=b_id,
            display_name=disp_name,
            is_installed=True,
            executable_path=exe_path,
            version=version,
            status_message=f"Installed{ver_str}",
        )

    @classmethod
    def detect_all(cls) -> Dict[str, BrowserInfo]:
        """Detects all supported browser types."""
        return {
            "chrome": cls.detect_browser("chrome"),
            "edge": cls.detect_browser("edge"),
            "firefox": cls.detect_browser("firefox"),
        }

    @classmethod
    def get_preferred_browser(cls, settings_dict: Optional[Dict] = None) -> str:
        """Determines the active preferred browser from settings or installed fallback."""
        if settings_dict:
            configured = settings_dict.get("browser_type")
            if configured and str(configured).lower() in ("chrome", "edge", "firefox"):
                return str(configured).lower()

        # Check installed in priority order: chrome -> edge -> firefox
        all_b = cls.detect_all()
        for b_id in ["chrome", "edge", "firefox"]:
            if all_b[b_id].is_installed:
                return b_id
        return "chrome"


class BrowserFactory:
    """
    Unified factory creating Selenium WebDrivers according to settings and adapter configuration.
    Governing Specification: Phase 9 Browser Automation Settings (Chrome, Edge, Firefox).
    """

    @classmethod
    def resolve_browser_type(cls, explicit_type: Optional[str] = None) -> str:
        """Resolve the effective browser engine in priority: explicit argument -> settings.json -> fallback."""
        if explicit_type and str(explicit_type).lower().strip() in ("chrome", "edge", "firefox"):
            return str(explicit_type).lower().strip()

        try:
            from settings_manager import settings
            configured = settings.get("browser_type")
            if configured and str(configured).lower().strip() in ("chrome", "edge", "firefox"):
                return str(configured).lower().strip()
        except Exception:
            pass

        return BrowserDetectionService.get_preferred_browser()

    @classmethod
    def resolve_headless(cls, explicit_headless: Optional[bool] = None) -> bool:
        """Resolve whether browser should run headless in priority: explicit argument -> settings.json -> default True."""
        if explicit_headless is not None:
            return bool(explicit_headless)

        try:
            from settings_manager import settings
            configured = settings.get("browser_headless")
            if configured is not None:
                return bool(configured)
            if settings.get("show_browser") is True:
                return False
        except Exception:
            pass

        return True

    @classmethod
    def create_driver(
        cls,
        browser_type: Optional[str] = None,
        headless: Optional[bool] = None,
        timeout_seconds: float = 10.0,
        user_agent: Optional[str] = None,
    ):
        """
        Create, configure, and return a Selenium WebDriver for the resolved browser engine.
        Applies headless options, standard user-agent, automation masks, and implicit timeouts.
        Raises RuntimeError with actionable error message if the browser is uninstalled or initialization fails.
        """
        b_type = cls.resolve_browser_type(browser_type)
        is_headless = cls.resolve_headless(headless)

        info = BrowserDetectionService.detect_browser(b_type)
        if not info.is_installed:
            raise RuntimeError(
                f"Browser '{info.display_name}' ({b_type}) is not installed on this system. "
                f"Please install it or select an available browser in General Settings."
            )

        ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        try:
            if b_type == "chrome":
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options as ChromeOptions

                options = ChromeOptions()
                if is_headless:
                    options.add_argument("--headless=new")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--window-size=1920,1080")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                else:
                    options.add_experimental_option("detach", True)
                    options.add_argument("--start-maximized")

                options.add_argument(f"user-agent={ua}")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)

                driver = webdriver.Chrome(options=options)

            elif b_type == "edge":
                from selenium import webdriver
                from selenium.webdriver.edge.options import Options as EdgeOptions

                options = EdgeOptions()
                if is_headless:
                    options.add_argument("--headless=new")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--window-size=1920,1080")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                else:
                    options.add_argument("--start-maximized")

                options.add_argument(f"user-agent={ua}")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)

                driver = webdriver.Edge(options=options)

            elif b_type == "firefox":
                from selenium import webdriver
                from selenium.webdriver.firefox.options import Options as FirefoxOptions

                options = FirefoxOptions()
                if is_headless:
                    options.add_argument("-headless")
                    options.add_argument("--window-size=1920,1080")

                if ua:
                    options.set_preference("general.useragent.override", ua)

                driver = webdriver.Firefox(options=options)

            else:
                raise ValueError(f"Unsupported browser type: {b_type}")

            driver.implicitly_wait(max(timeout_seconds / 2.0, 1.0))
            return driver

        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"Failed to launch {info.display_name} automation session: {e}") from e

