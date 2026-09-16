"""
RoboEq Electronic Browser & Session Manager
Encapsulates Chrome WebDriver lifecycle, options, headers, cookies, and DOM execution helpers.
"""

import time
from typing import Optional, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.models import AdapterConfig
from vendors.roboeq.selectors import RoboEqSelectors


class RoboEqSessionManager:
    """
    Manages active Chrome session, options, and JavaScript evaluation for RoboEq Electronic.
    """

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig(
            vendor_id="vendor_roboeq",
            base_url=RoboEqSelectors.BASE_URL,
            headless=True,
            timeout_seconds=10.0,
            settle_seconds=2.2,
        )
        self.driver: Optional[webdriver.Chrome] = None

    def create_driver(self) -> webdriver.Chrome:
        options = Options()
        if self.config.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        else:
            options.add_experimental_option("detach", True)
            options.add_argument("--start-maximized")

        ua = self.config.user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        options.add_argument(f"user-agent={ua}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(self.config.timeout_seconds / 2.0)
        self.driver = driver
        return driver

    def get_driver(self) -> webdriver.Chrome:
        if self.driver is None:
            return self.create_driver()
        return self.driver

    def wait_for_settle(self, custom_settle: Optional[float] = None) -> None:
        duration = custom_settle if custom_settle is not None else self.config.settle_seconds
        time.sleep(duration)

    def execute_script(self, script: str, *args) -> Any:
        driver = self.get_driver()
        return driver.execute_script(script, *args)

    def dismiss_active_modal(self) -> bool:
        try:
            driver = self.get_driver()
            close_btns = driver.find_elements(By.CSS_SELECTOR, ".modal .close, button.close, .mz-button-close, .toast-close-button")
            if close_btns:
                driver.execute_script("arguments[0].click();", close_btns[0])
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
