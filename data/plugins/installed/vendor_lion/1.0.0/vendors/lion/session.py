"""
Lion Electronic Browser & Session Manager
Encapsulates Chrome WebDriver lifecycle, options, headers, cookies, and DOM execution helpers.
Governing GAP: GAP-09, GAP-17.
"""

import time
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.models import AdapterConfig
from core.models import SessionContinuityMode, SessionPromotionResult
try:
    from .selectors import LionSelectors
except ImportError:
    from vendors.lion.selectors import LionSelectors


class LionSessionManager:
    """
    Manages active Chrome session, options, and JavaScript evaluation for Lion Electronic.
    Supports session promotion (headless <-> headful) with explicit continuity tracking.
    """

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig(
            vendor_id="vendor_lion",
            base_url=LionSelectors.BASE_URL,
            headless=True,
            timeout_seconds=10.0,
            settle_seconds=2.2,
        )
        self.driver: Optional[webdriver.Chrome] = None

    def create_driver(self) -> Any:
        """Create and configure WebDriver according to global settings and adapter configuration."""
        from core.browser_detection import BrowserFactory
        eff_headless = self.config.headless
        if eff_headless is True:
            eff_headless = BrowserFactory.resolve_headless(None)

        driver = BrowserFactory.create_driver(
            browser_type=getattr(self.config, "browser_type", None),
            headless=eff_headless,
            timeout_seconds=self.config.timeout_seconds,
            user_agent=self.config.user_agent,
        )
        self.driver = driver
        return driver

    def get_driver(self) -> webdriver.Chrome:
        """Get or initialize active driver with automatic liveness verification and recovery."""
        if self.driver is not None:
            try:
                _ = self.driver.current_window_handle
                return self.driver
            except Exception:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
        return self.create_driver()

    def promote_to_headful(self) -> SessionPromotionResult:
        """
        Transition session from headless to visible/headful mode for interactive user resolution.
        Governing Invariant: GAP-09 Session Continuity.
        """
        if self.driver is not None and self.config.headless is False:
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

        # Extract state from active headless session
        cookies = []
        cur_url = None
        try:
            cookies = self.driver.get_cookies()
            cur_url = self.driver.current_url
        except Exception:
            pass

        # Terminate headless driver
        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None

        # Recreate headful driver
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

    def wait_for_presence(self, selector: str, by: By = By.CSS_SELECTOR, timeout: Optional[float] = None):
        """Wait for element presence in DOM."""
        driver = self.get_driver()
        t = timeout if timeout is not None else self.config.timeout_seconds
        return WebDriverWait(driver, t).until(EC.presence_of_element_located((by, selector)))

    def wait_for_settle(self, custom_settle: Optional[float] = None) -> None:
        """Enforce standard AJAX settle time (2.0 - 2.5s)."""
        duration = custom_settle if custom_settle is not None else self.config.settle_seconds
        time.sleep(duration)

    def execute_script(self, script: str, *args) -> Any:
        """Execute JavaScript in active browser context."""
        driver = self.get_driver()
        return driver.execute_script(script, *args)

    def trigger_jquery_input_and_change(self, selector: str, value: str) -> None:
        """
        Set input value and trigger jQuery input and change events.
        """
        js = """
        var sel = arguments[0];
        var val = arguments[1];
        var el = document.querySelector(sel);
        if (el) {
            el.value = val;
            el.setAttribute('value', val);
        }
        if (window.jQuery) {
            window.jQuery(sel).val(val).trigger('input').trigger('change');
        }
        """
        self.execute_script(js, selector, str(value))

    def dismiss_active_modal(self) -> bool:
        """Click SweetAlert confirm button if present to dismiss error modal."""
        try:
            driver = self.get_driver()
            confirm_btns = driver.find_elements(By.CSS_SELECTOR, LionSelectors.SWAL_CONFIRM_BTN)
            if confirm_btns:
                driver.execute_script("arguments[0].click();", confirm_btns[0])
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def close(self) -> None:
        """Close driver and clean up resources."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
