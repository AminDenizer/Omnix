import time
import re
import math
from typing import List, Dict, Any, Optional, Callable, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from settings_manager import settings


class LionAutomator:
    """
    Automates authentication and product purchasing operations on lionelectronic.ir
    using a visible interactive Chrome browser session.
    """

    BASE_URL = "https://lionelectronic.ir"
    LOGIN_URL = "https://lionelectronic.ir/login"
    CART_URL = "https://lionelectronic.ir/orders/cart"

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.is_logged_in = False

    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome WebDriver (Headless by default or visible based on settings)."""
        show_browser = settings.get("show_browser", False)
        options = Options()

        if show_browser:
            # Visible window mode
            options.add_experimental_option("detach", True)
            options.add_argument("--start-maximized")
        else:
            # Silent background Headless mode
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(4)
        return driver

    def login_browser(
        self,
        driver: webdriver.Chrome,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Navigate to login page and authenticate using provided or stored credentials.
        """
        user = username or settings.get("lion_username", "").strip()
        pwd = password or settings.get("lion_password", "").strip()

        if not user or not pwd:
            return False, "Lion Electronic credentials are not configured in Settings."

        try:
            driver.get(self.LOGIN_URL)
            wait = WebDriverWait(driver, 10)

            # Find username and password inputs
            user_input = wait.until(EC.presence_of_element_located((By.ID, "loginform-username")))
            pass_input = driver.find_element(By.ID, "loginform-password")

            # Clear and enter credentials
            user_input.click()
            user_input.send_keys(Keys.CONTROL + "a")
            user_input.send_keys(Keys.BACKSPACE)
            user_input.send_keys(user)

            pass_input.click()
            pass_input.send_keys(Keys.CONTROL + "a")
            pass_input.send_keys(Keys.BACKSPACE)
            pass_input.send_keys(pwd)

            # Submit form
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[name='signup-button'], #login-form button[type='submit'], button.blue-btn")
            driver.execute_script("arguments[0].click();", submit_btn)

            # Wait for redirect or error message
            time.sleep(2.5)

            # Check if redirected away from /login
            cur_url = driver.current_url.lower()
            if "/login" not in cur_url or "orders" in cur_url or "products" in cur_url:
                self.is_logged_in = True
                return True, "Login successful."

            # Check for specific error message on page
            err_els = driver.find_elements(By.CSS_SELECTOR, ".help-block-error, .alert-danger, .has-error")
            for el in err_els:
                txt = el.text.strip()
                if txt:
                    return False, f"Login failed: {txt}"

            # If still on login page without obvious error, check page source
            if "خروج" in driver.page_source or "حساب کاربری" in driver.page_source:
                self.is_logged_in = True
                return True, "Login successful."

            return False, "Login could not be verified. Please check your credentials in Settings."

        except Exception as e:
            return False, f"Login error: {str(e)}"

    def add_product_to_cart(
        self,
        driver: webdriver.Chrome,
        product_url: str,
        needed_qty: int
    ) -> Tuple[bool, int, str]:
        """
        Navigate to a product page in Chrome, inspect site stock limits,
        adjust quantity respecting MOQ and available stock, and add to cart.
        Returns (success, actual_ordered_qty, message).
        """
        if not product_url or not product_url.strip():
            return False, 0, "No store link configured"

        if "lionelectronic.ir" not in product_url:
            domain = product_url.split('/')[2] if '://' in product_url else product_url
            return False, 0, f"External store link ({domain}) — Manual order required"

        try:
            driver.get(product_url)
            wait = WebDriverWait(driver, 10)

            # Layer 1: Check if page is 404 or product not found
            if "صفحه‌ای یافت نشد" in driver.page_source or "404" in driver.title:
                return False, 0, "Product page not found (HTTP 404)"

            # Layer 2: Check if direct purchase is disabled or inquiry-only via Lion JS
            can_order = driver.execute_script("return (typeof window.productCanOrder !== 'undefined') ? window.productCanOrder : null;")
            if can_order is False:
                src = driver.page_source
                if "به زودی" in src:
                    return False, 0, "Coming Soon on Lion (0 available)"
                if any(kw in src for kw in ["اتمام موجودی", "ناموجود", "تمام شد", "اتمام"]):
                    return False, 0, "Out of Stock on Lion (0 available)"
                return False, 0, "Inquiry Only / Direct Sale Closed on Lion"

            # Layer 3: Explicit Stock Element Text Inspection
            site_stock: Optional[int] = None
            stock_els = driver.find_elements(By.CSS_SELECTOR, "span.stock-amount, .product-stock, .stock-status")
            for el in stock_els:
                txt = el.text.strip()
                if "به زودی" in txt:
                    return False, 0, "Coming Soon on Lion (0 available)"
                if any(kw in txt for kw in ["ناموجود", "اتمام", "تمام شد", "تمام"]):
                    return False, 0, "Out of Stock on Lion (0 available)"
                clean_t = txt.replace(',', '').replace(' ', '')
                m = re.search(r'(\d+)', clean_t)
                if m:
                    try:
                        site_stock = int(m.group(1))
                        break
                    except ValueError:
                        pass

            if site_stock == 0:
                return False, 0, "Out of Stock on Lion (0 available)"

            # Layer 4: Check Buy Button & Inquiry Button State
            buy_btns = driver.find_elements(By.CSS_SELECTOR, "button.btn-buy, button.add-btn, .btn-buy")
            if not buy_btns:
                # Check if inquiry button exists
                inquiry_btns = driver.find_elements(By.CSS_SELECTOR, "button.add-inquiry, .add-inquiry, button.save-btn")
                if inquiry_btns:
                    return False, 0, "Inquiry Only / Direct Sale Closed on Lion"
                return False, 0, "Product unavailable for direct purchase (No buy button)"

            buy_btn = buy_btns[0]
            btn_class = buy_btn.get_attribute("class") or ""
            if "disabled" in btn_class or not buy_btn.is_enabled():
                if "به زودی" in driver.page_source:
                    return False, 0, "Coming Soon on Lion (0 available)"
                return False, 0, "Inquiry Only / Direct Sale Closed on Lion"

            # Layer 5: Quantity Input & Packaging Step / Multiple (ضریب سفارش / بسته بندی)
            qty_inputs = driver.find_elements(By.CSS_SELECTOR, "#quantity-cell, input.quantity-cell")
            if not qty_inputs:
                return False, 0, "Quantity input not found (Product may be inquiry-only)"

            qty_input = qty_inputs[0]
            initial_val = qty_input.get_attribute("value") or "1"
            
            if "به زودی" in initial_val:
                return False, 0, "Coming Soon on Lion (0 available)"

            try:
                site_step = max(int(float(initial_val)), 1)
            except ValueError:
                site_step = 1

            # Determine effective packaging step:
            # - If site_step in [2, 5, 10]: use 10 as base multiple (divisible by 2, 5, and 10 to eliminate odd-number rejection like 45 -> 50)
            # - If site_step > 10 (e.g. 25, 50, 100): use site_step
            # - If site_step == 1 (single-piece item): use 1
            if site_step > 10:
                effective_step = site_step
            elif site_step in [2, 5, 10]:
                effective_step = 10
            else:
                effective_step = 1

            # Round up needed quantity to the next valid multiple of effective_step (e.g. 45 -> 50 for step=2/5/10)
            multiples = math.ceil(needed_qty / effective_step)
            target_qty = max(multiples * effective_step, site_step)

            # Layer 6: Check Site Stock vs Target Quantity
            if site_stock is not None and site_stock < target_qty:
                return False, 0, f"Insufficient site stock ({site_stock} available, Needed: {target_qty})"

            final_qty = target_qty
            pack_warning = f" (Pack multiple: rounded from {needed_qty} to {final_qty})" if final_qty > needed_qty else ""

            # Atomically set quantity and click Add to Cart
            driver.execute_script("""
                var qty = arguments[0];
                var el = document.getElementById('quantity-cell') || document.querySelector('.quantity-cell');
                if (el) {
                    el.value = qty;
                    el.setAttribute('value', qty);
                }
                if (window.jQuery) {
                    $('#quantity-cell, .quantity-cell').val(qty).trigger('input').trigger('change');
                }
                var btn = document.querySelector('button.btn-buy, button.add-btn, .btn-buy');
                if (btn && !btn.classList.contains('disabled')) {
                    btn.click();
                }
            """, str(final_qty))

            # Wait for cart update animation / AJAX request
            time.sleep(2.2)

            # Layer 7: Check for SweetAlert / error modals / flash error popups on Lion
            err_popups = driver.find_elements(By.CSS_SELECTOR, ".swal2-html-container, .swal2-title, .alert-danger, .toast-message, .error-summary, .help-block-error")
            for ep in err_popups:
                ep_txt = ep.text.strip()
                if ep_txt and any(kw in ep_txt for kw in ["ضریب", "موجودی", "خطا", "امکان", "ناموفق", "مضرب", "بسته"]):
                    return False, 0, f"Lion Store Notice: {ep_txt}"

            msg = f"Added {final_qty} units (Pack of {site_step}){pack_warning}"
            return True, final_qty, msg

        except Exception as e:
            return False, 0, f"Error adding to cart: {str(e)}"

    def order_items_batch(
        self,
        items: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Interactive batch ordering runner:
        1. Launches Chrome browser.
        2. Logs in to lionelectronic.ir.
        3. Visits each product page and adds the required quantity to cart.
        4. Navigates to the shopping cart page (/orders/cart) and leaves the browser open.
        """
        total = len(items)
        successful_count = 0
        failed_count = 0
        results_log = []

        try:
            if progress_callback:
                progress_callback(0, total, "System", 0, "Launching Chrome browser...")

            driver = self._create_driver()
            self.driver = driver
        except Exception as e:
            err_msg = f"Failed to launch Chrome browser: {str(e)}"
            return {
                "success": False,
                "message": err_msg,
                "successful_count": 0,
                "failed_count": total,
                "results": [],
                "cart_url": self.CART_URL
            }

        # Step 1: Log in
        user = settings.get("lion_username", "").strip()
        pwd = settings.get("lion_password", "").strip()

        if user and pwd:
            if progress_callback:
                progress_callback(0, total, "Authentication", 0, "Logging into lionelectronic.ir...")
            login_ok, login_msg = self.login_browser(driver, user, pwd)
            if not login_ok:
                if progress_callback:
                    progress_callback(0, total, "Authentication", 0, f"Warning: {login_msg}")
        else:
            if progress_callback:
                progress_callback(0, total, "Authentication", 0, "No credentials configured — continuing as guest session.")

        # Step 2: Iterate through shortage items
        for idx, item in enumerate(items, start=1):
            p_name = item.get("part_name") or item.get("part_number") or f"Item {idx}"
            link = item.get("link", "").strip()
            needed = item.get("needed_qty", 1)

            if not link or "lionelectronic.ir" not in link:
                failed_count += 1
                res_entry = {"part": p_name, "status": "FAILED", "msg": "No Lion Electronic link"}
                results_log.append(res_entry)
                if progress_callback:
                    progress_callback(idx, total, p_name, 0, "Skipped (No link)")
                continue

            if progress_callback:
                progress_callback(idx, total, p_name, needed, "Opening product page...")

            ok, final_qty, msg = self.add_product_to_cart(driver, link, needed)
            item["order_success"] = bool(ok)
            item["order_message"] = msg
            if ok:
                successful_count += 1
                item["actual_ordered_qty"] = final_qty
                item["qty_ordered"] = final_qty
                results_log.append({"part": p_name, "status": "SUCCESS", "qty": final_qty, "msg": msg, "item": item})
                if progress_callback:
                    progress_callback(idx, total, p_name, final_qty, f"Added {final_qty} pcs ({msg})")
            else:
                failed_count += 1
                item["actual_ordered_qty"] = 0
                item["qty_ordered"] = 0
                results_log.append({"part": p_name, "status": "FAILED", "qty": 0, "msg": msg, "item": item})
                if progress_callback:
                    progress_callback(idx, total, p_name, 0, f"Error: {msg}")

            time.sleep(0.5)

        # Step 3: Handle completion & cart finalization
        show_browser = settings.get("show_browser", False)
        if show_browser:
            if progress_callback:
                progress_callback(total, total, "Complete", successful_count, "Opening shopping cart...")
            try:
                driver.get(self.CART_URL)
                time.sleep(2.0)
            except Exception:
                pass
        else:
            # In headless mode, close the background browser cleanly
            try:
                driver.quit()
            except Exception:
                pass

        return {
            "success": successful_count > 0,
            "message": f"Processed {total} items: {successful_count} added to cart, {failed_count} skipped/failed.",
            "successful_count": successful_count,
            "failed_count": failed_count,
            "results": results_log,
            "cart_url": self.CART_URL
        }

