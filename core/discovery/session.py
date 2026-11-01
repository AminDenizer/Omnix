"""
Omnix Universal Discovery - Browser Observation Session
Harness for Chrome-based empirical discovery, DOM extraction, and screenshot capture.
Vendor-neutral: contains ZERO vendor-specific selectors or assumptions.
"""

import time
import os
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.discovery.models import VendorTarget


class DiscoverySession:
    """
    Universal Chrome observation harness for empirical website discovery.
    Provides non-destructive DOM querying, screenshot recording, and session observation.
    """

    def __init__(
        self,
        target: Optional[VendorTarget] = None,
        headless: bool = True,
        timeout_seconds: float = 12.0,
        settle_delay: float = 1.5,
    ):
        self.target = target
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.settle_delay = settle_delay
        self.driver: Optional[webdriver.Chrome] = None

    def start(self) -> webdriver.Chrome:
        """Launch configured Chrome WebDriver instance."""
        if self.driver is not None:
            return self.driver

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        else:
            options.add_experimental_option("detach", True)
            options.add_argument("--start-maximized")

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(self.timeout_seconds / 3.0)
        self.driver = driver
        return driver

    def navigate(self, url: str) -> str:
        """Navigate to a URL and wait for standard settle time."""
        driver = self.start()
        driver.get(url)
        self.wait_settle()
        return driver.current_url

    def wait_settle(self, delay: Optional[float] = None) -> None:
        """Wait for JavaScript / AJAX settle window."""
        t = delay if delay is not None else self.settle_delay
        time.sleep(t)

    def capture_dom(self) -> str:
        """Capture complete current HTML page source."""
        driver = self.start()
        return driver.page_source

    def capture_screenshot(self, filepath: str) -> str:
        """Capture full-page screenshot to disk."""
        driver = self.start()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        driver.save_screenshot(filepath)
        return filepath

    def get_current_url(self) -> str:
        """Return current URL in browser."""
        driver = self.start()
        return driver.current_url

    def get_page_title(self) -> str:
        """Return current page title."""
        driver = self.start()
        return driver.title

    def execute_script(self, script: str, *args) -> Any:
        """Execute arbitrary JavaScript in the browser context."""
        driver = self.start()
        return driver.execute_script(script, *args)

    def find_elements_by_css(self, css_selector: str) -> List[Any]:
        """Find matching DOM elements."""
        driver = self.start()
        try:
            return driver.find_elements(By.CSS_SELECTOR, css_selector)
        except Exception:
            return []

    def get_cookies(self) -> List[Dict[str, Any]]:
        """Return active browser cookies."""
        driver = self.start()
        return driver.get_cookies()

    def close(self) -> None:
        """Cleanly close browser and release resources."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def __enter__(self) -> "DiscoverySession":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
