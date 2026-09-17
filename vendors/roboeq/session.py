"""
RoboEq Electronic Browser & Session Manager
Encapsulates Chrome WebDriver lifecycle, options, headers, cookies, and DOM execution helpers.
Governing GAP: GAP-09, GAP-17.
"""

import time
from typing import Optional, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.models import AdapterConfig
from core.procurement.challenge_handler import SessionContinuityMode, SessionPromotionResult
from vendors.roboeq.selectors import RoboEqSelectors


class RoboEqSessionManager:
    """
    Manages active Chrome session, options, and JavaScript evaluation for RoboEq Electronic.
    Supports session promotion (headless <-> headful) with explicit continuity tracking.
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

    def promote_to_headful(self) -> SessionPromotionResult:
        """
        Transition session from headless to visible/headful mode for interactive user resolution.
        Governing Invariant: GAP-09 Session Continuity.
        """
        if self.driver is not None and not self.config.headless:
            return SessionPromotionResult(
                success=True,
                continuity_mode=SessionContinuityMode.SAME_CONTEXT_PRESERVED,
                message="Browser is already in visible/headful mode.",
                active_url=getattr(self.driver, "current_url", None),
            )

        if self.driver is None:
            self.config.headless = False
            self.create_driver()
            return SessionPromotionResult(
                success=True,
                continuity_mode=SessionContinuityMode.BROWSER_RECREATED_UNAUTHENTICATED,
                message="Created new visible headful browser driver.",
            )

        cookies = []
        cur_url = None
        try:
            cookies = self.driver.get_cookies()
            cur_url = self.driver.current_url
        except Exception:
            pass

        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None

        self.config.headless = False
        driver = self.create_driver()

        transferred_count = 0
        if cur_url and not cur_url.startswith("data:") and not cur_url.startswith("about:"):
            try:
                driver.get(cur_url)
                for c in cookies:
                    try:
                        driver.add_cookie(c)
                        transferred_count += 1
                    except Exception:
                        pass
                driver.refresh()
                time.sleep(0.8)
            except Exception:
                pass

            return SessionPromotionResult(
                success=True,
                continuity_mode=SessionContinuityMode.STATE_TRANSFERRED if transferred_count > 0 else SessionContinuityMode.BROWSER_RECREATED_UNAUTHENTICATED,
                message=f"Promoted to headful mode with {transferred_count} cookies transferred.",
                cookies_transferred=transferred_count,
                active_url=cur_url,
            )

        return SessionPromotionResult(
            success=True,
            continuity_mode=SessionContinuityMode.BROWSER_RECREATED_UNAUTHENTICATED,
            message="Promoted to headful mode (no active URL/cookies to transfer).",
            cookies_transferred=0,
        )

    def demote_to_headless(self) -> SessionPromotionResult:
        """
        Transition session back to headless mode after interactive resolution.
        """
        if self.driver is not None and self.config.headless:
            return SessionPromotionResult(
                success=True,
                continuity_mode=SessionContinuityMode.SAME_CONTEXT_PRESERVED,
                message="Browser is already in headless mode.",
                active_url=getattr(self.driver, "current_url", None),
            )

        cookies = []
        cur_url = None
        if self.driver is not None:
            try:
                cookies = self.driver.get_cookies()
                cur_url = self.driver.current_url
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        self.config.headless = True
        driver = self.create_driver()

        transferred_count = 0
        if cur_url and not cur_url.startswith("data:") and not cur_url.startswith("about:"):
            try:
                driver.get(cur_url)
                for c in cookies:
                    try:
                        driver.add_cookie(c)
                        transferred_count += 1
                    except Exception:
                        pass
                driver.refresh()
                time.sleep(0.5)
            except Exception:
                pass

        return SessionPromotionResult(
            success=True,
            continuity_mode=SessionContinuityMode.STATE_TRANSFERRED if transferred_count > 0 else SessionContinuityMode.BROWSER_RECREATED_UNAUTHENTICATED,
            message=f"Demoted to headless mode with {transferred_count} cookies transferred.",
            cookies_transferred=transferred_count,
            active_url=cur_url,
        )

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
