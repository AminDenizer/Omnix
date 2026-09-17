"""
Lion Electronic Vendor Adapter Implementation (LionVendorAdapter)
Conforms strictly to IVendorAdapter and docs/VENDORS/LION/ADAPTER_SPECIFICATION.md.
Vendor ID: vendor_lion
"""

import re
import urllib.parse
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from core.vendor_interface import IVendorAdapter
from core.models import (
    AdapterConfig,
    AdapterStatus,
    SearchItem,
    SearchResultSet,
    ProductReference,
    ProductDetails,
    CanonicalComponentDraft,
    OrderConstraints,
    StockStatus,
    CartItem,
    CartDetails,
    CartMutationResult,
    AuthCredentials,
    AuthResult,
    SessionStatus,
    RecoveryResult,
)
from core.errors import (
    ProductNotFoundError,
    ZeroSearchResultsError,
    OutOfStockError,
    MOQViolationError,
    OrderMultipleViolationError,
    MaxQuantityExceededError,
    TransportNetworkError,
    AuthenticationRequiredError,
    DOMDriftError,
    UnknownVendorError,
)
from vendors.lion.selectors import LionSelectors
from vendors.lion.errors import LionErrorTranslator
from vendors.lion.session import LionSessionManager


class LionVendorAdapter(IVendorAdapter):
    """
    Formal Vendor Adapter for Lion Electronic (https://lionelectronic.ir).
    Implements all 13 IVendorAdapter operations without Core procurement math.
    """

    VENDOR_ID = "vendor_lion"
    BASE_URL = LionSelectors.BASE_URL

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config or AdapterConfig(
            vendor_id=self.VENDOR_ID,
            base_url=self.BASE_URL,
            headless=True,
            timeout_seconds=10.0,
            settle_seconds=2.2,
        )
        self.session = LionSessionManager(self._config)
        self._is_ready = False
        self._is_authenticated = False
        self._current_user: Optional[str] = None

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        """Initialize browser driver context and ready state."""
        if config:
            self._config = config
            self.session = LionSessionManager(self._config)

        try:
            self.session.get_driver()
            self._is_ready = True
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=True,
                is_authenticated=self._is_authenticated,
                message="Lion Vendor Adapter initialized successfully.",
            )
        except Exception as e:
            self._is_ready = False
            err = LionErrorTranslator.translate_transport_exception(e, {"operation": "initialize"})
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=False,
                is_authenticated=False,
                message=f"Initialization failed: {err.message}",
            )

    def search_part(self, query: str) -> SearchResultSet:
        """
        Execute search on Lion Electronic via GET /products?search={query}.
        Extracts candidate cards from .products-list, .product-grid.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return SearchResultSet(vendor_id=self.VENDOR_ID, query="", total_matches=0, is_exact_match=False, items=[])

        search_url = LionSelectors.SEARCH_URL_TEMPLATE.format(query=urllib.parse.quote(clean_q))
        driver = self.session.get_driver()

        try:
            driver.get(search_url)
            self.session.wait_for_settle(1.5)

            # Check for page level errors (404, WAF, etc.)
            err = LionErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"query": clean_q, "operation": "search_part"},
            )
            if err:
                raise err

            # Check for zero results
            empty_els = driver.find_elements(By.CSS_SELECTOR, LionSelectors.RESULTS_EMPTY_CONTAINER)
            page_text = driver.page_source

            items: List[SearchItem] = []
            soup = BeautifulSoup(page_text, "html.parser")

            # Extract product links matching canonical regex /products/(\d+)-(.*)
            product_links = soup.select(LionSelectors.RESULTS_PRODUCT_LINKS)
            seen_urls = set()

            for a_tag in product_links:
                href = a_tag.get("href", "")
                full_url = urllib.parse.urljoin(self.BASE_URL, href)
                m = LionSelectors.PDP_PATH_PATTERN.match(href) or LionSelectors.PDP_URL_PATTERN.match(full_url)
                if m and full_url not in seen_urls:
                    seen_urls.add(full_url)
                    p_id = m.group("product_id")
                    slug = m.group("slug")
                    sku = f"{p_id}-{slug}"
                    title = a_tag.get_text(strip=True) or slug
                    
                    # Try to find thumbnail
                    img_tag = a_tag.find("img") or (a_tag.parent.find("img") if a_tag.parent else None)
                    thumb_url = img_tag.get("src") if img_tag else None
                    if thumb_url:
                        thumb_url = urllib.parse.urljoin(self.BASE_URL, thumb_url)

                    item = SearchItem(
                        vendor_sku=sku,
                        mpn_hint=slug,
                        title=title,
                        pdp_url=full_url,
                        thumbnail_url=thumb_url,
                        raw_data={"product_id": p_id, "slug": slug},
                    )
                    items.append(item)

            total = len(items)
            is_exact = any(item.mpn_hint.lower() == clean_q.lower() for item in items)

            return SearchResultSet(
                vendor_id=self.VENDOR_ID,
                query=clean_q,
                total_matches=total,
                is_exact_match=is_exact,
                items=items,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise LionErrorTranslator.translate_transport_exception(e, {"query": clean_q, "operation": "search_part"})

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        """
        Resolve a URL or SKU to a normalized ProductReference.
        """
        raw = (url_or_sku or "").strip()
        if not raw:
            raise ProductNotFoundError("Empty product identifier provided", vendor_id=self.VENDOR_ID)

        # Case 1: Full URL
        m = LionSelectors.PDP_URL_PATTERN.match(raw)
        if m:
            p_id = m.group("product_id")
            slug = m.group("slug")
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=f"{p_id}-{slug}",
                pdp_url=raw,
                product_id=p_id,
                slug=slug,
            )

        # Case 2: Relative URL
        m_rel = LionSelectors.PDP_PATH_PATTERN.match(raw)
        if m_rel:
            p_id = m_rel.group("product_id")
            slug = m_rel.group("slug")
            full_url = urllib.parse.urljoin(self.BASE_URL, raw)
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=f"{p_id}-{slug}",
                pdp_url=full_url,
                product_id=p_id,
                slug=slug,
            )

        # Case 3: SKU format '2070-NE555P'
        sku_m = re.match(r"^(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.-]+)$", raw)
        if sku_m:
            p_id = sku_m.group("product_id")
            slug = sku_m.group("slug")
            pdp_url = f"{self.BASE_URL}/products/{raw}"
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=raw,
                pdp_url=pdp_url,
                product_id=p_id,
                slug=slug,
            )

        # Fallback: Assume SKU or slug
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=raw,
            pdp_url=f"{self.BASE_URL}/products/{raw}",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        """
        Navigate to PDP and extract complete technical specs, stock, and constraints.
        """
        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            driver.get(target_url)
            self.session.wait_for_settle(1.5)

            # Check 404 and page errors
            err = LionErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"url": target_url, "operation": "inspect_product"},
            )
            if err:
                raise err

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Extract window.productCanOrder via JS
            can_order_js = self.session.execute_script(
                "return (typeof window.productCanOrder !== 'undefined') ? window.productCanOrder : null;"
            )

            # Extract Stock amount text
            stock_qty = 0
            stock_span = soup.select_one(LionSelectors.STOCK_AMOUNT_SPAN)
            raw_status_text = stock_span.get_text(strip=True) if stock_span else ""

            if raw_status_text:
                clean_digits = raw_status_text.replace(",", "").replace(" ", "")
                sm = re.search(r"(\d+)", clean_digits)
                if sm:
                    stock_qty = int(sm.group(1))

            # Determine can_order and inquiry state
            is_inquiry = False
            inquiry_btn = soup.select_one(LionSelectors.BTN_INQUIRY_PRIMARY)
            if inquiry_btn is not None:
                is_inquiry = True

            can_order = True
            if can_order_js is False or stock_qty == 0 or "اتمام موجودی" in raw_status_text or "به زودی" in raw_status_text:
                can_order = False

            # Extract raw packaging step from #quantity-cell attribute
            qty_input = soup.select_one(LionSelectors.INPUT_QUANTITY_CSS)
            raw_step = 1
            if qty_input:
                val = qty_input.get("value", "1")
                try:
                    raw_step = max(int(float(val)), 1)
                except ValueError:
                    raw_step = 1

            # Extract technical specifications table
            draft = self.extract_product_data(soup)

            # Extract Price (if available)
            price_irr = None
            price_el = soup.select_one(".product-price, .price-value, .price")
            if price_el:
                price_text = price_el.get_text(strip=True).replace(",", "").replace(" ", "")
                pm = re.search(r"(\d+)", price_text)
                if pm:
                    price_irr = int(pm.group(1))

            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=target_url,
                stock_quantity=stock_qty,
                can_order=can_order,
                is_inquiry_only=is_inquiry,
                raw_status_text=raw_status_text,
                price_irr=price_irr,
                mpn=draft.mpn,
                manufacturer=draft.manufacturer,
                package_raw=draft.package,
                order_constraints=OrderConstraints(
                    packaging_step_raw=raw_step,
                    moq_raw=raw_step,
                ),
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise LionErrorTranslator.translate_transport_exception(e, {"url": target_url, "operation": "inspect_product"})

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        """
        Extract technical specs ('شماره فنی', 'سازنده', 'پکیج') from BeautifulSoup or HTML string.
        """
        if isinstance(dom_context, str):
            soup = BeautifulSoup(dom_context, "html.parser")
        elif isinstance(dom_context, BeautifulSoup):
            soup = dom_context
        else:
            soup = BeautifulSoup(str(dom_context), "html.parser")

        mpn = None
        manufacturer = None
        package = None
        specs: Dict[str, str] = {}

        rows = soup.select(LionSelectors.SPEC_TABLE_ROWS)
        for row in rows:
            tds = row.find_all(["td", "th"])
            if len(tds) >= 2:
                key = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                if key and val:
                    specs[key] = val
                    if "شماره فنی" in key or "part number" in key.lower() or "mpn" in key.lower():
                        mpn = val
                    elif "سازنده" in key or "manufacturer" in key.lower() or "brand" in key.lower():
                        manufacturer = val
                    elif "پکیج" in key or "package" in key.lower() or "case" in key.lower():
                        package = val

        return CanonicalComponentDraft(
            vendor_id=self.VENDOR_ID,
            vendor_sku="",
            mpn=mpn,
            manufacturer=manufacturer,
            package=package,
            description=None,
            specs=specs,
        )

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        """
        Inspect live stock availability on Lion Electronic.
        """
        details = self.inspect_product(product_ref)
        raw_text = details.raw_status_text
        is_restock = "به زودی" in raw_text

        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.stock_quantity > 0 and details.can_order,
            can_order=details.can_order,
            is_inquiry_only=details.is_inquiry_only,
            is_restock_pipeline=is_restock,
            raw_text=raw_text,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        """
        Extract raw packaging step from Lion DOM without client-side modifications.
        """
        details = self.inspect_product(product_ref)
        return details.order_constraints

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        """
        Internal Browser AJAX cart mutation:
        1. Set quantity in #quantity-cell.
        2. Trigger jQuery 'input' and 'change'.
        3. Click 'button.btn-buy'.
        4. Wait 2.0-2.5s settle window.
        5. Intercept and translate any SweetAlert modal error.
        """
        if quantity <= 0:
            raise OrderMultipleViolationError(f"Quantity must be greater than 0 (got {quantity})", vendor_id=self.VENDOR_ID)

        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            # Ensure we are on the PDP
            if driver.current_url.lower() != target_url.lower():
                driver.get(target_url)
                self.session.wait_for_settle(1.5)

            # Check if purchasable
            details = self.inspect_product(product_ref)
            if not details.can_order:
                if details.is_inquiry_only:
                    raise OutOfStockError("Lion product is inquiry-only (direct purchase disabled)", vendor_id=self.VENDOR_ID)
                raise OutOfStockError(f"Lion product cannot be ordered (Stock: {details.stock_quantity}, Status: {details.raw_status_text})", vendor_id=self.VENDOR_ID)

            # Check stock ceiling
            if details.stock_quantity > 0 and quantity > details.stock_quantity:
                raise MaxQuantityExceededError(
                    f"Requested quantity {quantity} exceeds available stock {details.stock_quantity}",
                    vendor_id=self.VENDOR_ID,
                    context={"requested": quantity, "available": details.stock_quantity},
                )

            # Set quantity and trigger jQuery events, then click buy button
            js_mutation = """
                var targetQty = arguments[0];
                var el = document.getElementById('quantity-cell') || document.querySelector('.quantity-cell');
                if (el) {
                    el.value = targetQty;
                    el.setAttribute('value', targetQty);
                }
                if (window.jQuery) {
                    window.jQuery('#quantity-cell, .quantity-cell').val(targetQty).trigger('input').trigger('change');
                }
                var btn = document.querySelector('button.btn-buy, button.add-btn, .btn-buy');
                if (btn && !btn.classList.contains('disabled')) {
                    btn.click();
                    return true;
                }
                return false;
            """
            clicked = self.session.execute_script(js_mutation, str(quantity))
            if not clicked:
                raise DOMDriftError("Buy button (.btn-buy) not found or disabled on Lion PDP", vendor_id=self.VENDOR_ID)

            # Enforce 2.0-2.5s asynchronous settle window
            self.session.wait_for_settle(2.2)

            # Check for SweetAlert error popups
            err_popups = driver.find_elements(By.CSS_SELECTOR, LionSelectors.SWAL_HTML_CONTAINER)
            for ep in err_popups:
                ep_text = ep.text.strip()
                if ep_text and any(kw in ep_text for kw in ["ضریب", "موجودی", "خطا", "امکان", "ناموفق", "مضرب", "بسته", "حداقل"]):
                    # Dismiss modal
                    self.session.dismiss_active_modal()
                    err = LionErrorTranslator.translate_modal_message(ep_text, {"requested_qty": quantity, "product_sku": product_ref.vendor_sku})
                    raise err

            return CartMutationResult(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=quantity,
                success=True,
                error_category=None,
                raw_vendor_message=f"Added {quantity} units to Lion shopping cart",
                cart_total_items=1,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise LionErrorTranslator.translate_transport_exception(e, {"sku": product_ref.vendor_sku, "qty": quantity, "operation": "add_to_cart"})

    def inspect_cart(self) -> CartDetails:
        """
        Navigate to /orders/cart and extract staged line items.
        """
        driver = self.session.get_driver()

        try:
            driver.get(LionSelectors.CART_URL)
            self.session.wait_for_settle(2.0)

            err = LionErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"operation": "inspect_cart"},
            )
            if err:
                raise err

            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select(LionSelectors.CART_ITEM_ROWS)

            cart_items: List[CartItem] = []
            for r in rows:
                tds = r.find_all("td")
                if len(tds) >= 3:
                    name = tds[0].get_text(strip=True)
                    qty_str = tds[1].get_text(strip=True).replace(",", "")
                    qm = re.search(r"(\d+)", qty_str)
                    qty = int(qm.group(1)) if qm else 1

                    cart_items.append(
                        CartItem(
                            vendor_sku=name,
                            product_name=name,
                            quantity=qty,
                        )
                    )

            return CartDetails(
                vendor_id=self.VENDOR_ID,
                cart_url=LionSelectors.CART_URL,
                total_items=len(cart_items),
                items=cart_items,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise LionErrorTranslator.translate_transport_exception(e, {"operation": "inspect_cart"})

    def authenticate(
        self,
        credentials: Optional[AuthCredentials] = None,
        challenge_handler: Optional[Any] = None,
    ) -> AuthResult:
        """
        Authenticate browser session using provided credentials,
        with optional interactive challenge handler for CAPTCHA/OTP resolution (GAP-09, GAP-17).
        """
        from core.procurement.challenge_handler import ChallengeType, ChallengeState, ChallengeContext

        if not credentials:
            try:
                from settings_manager import settings
                v_cfg = settings.get_vendor_settings(self.VENDOR_ID)
                if v_cfg and v_cfg.username and v_cfg.password:
                    credentials = AuthCredentials(username=v_cfg.username, password=v_cfg.password)
            except Exception:
                pass

        if not credentials or not credentials.username or not credentials.password:
            return AuthResult(
                vendor_id=self.VENDOR_ID,
                success=False,
                message="Lion authentication credentials not provided.",
            )

        driver = self.session.get_driver()

        try:
            driver.get(LionSelectors.LOGIN_URL)
            self.session.wait_for_settle(1.5)

            # Upfront challenge detection (Turnstile, reCAPTCHA, WAF, OTP)
            challenge_type = self._detect_challenge_on_page(driver)
            if challenge_type is not None:
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=challenge_type,
                    prompt_message=f"Lion Electronic requires security challenge resolution ({challenge_type.value}).",
                    target_url=driver.current_url or LionSelectors.LOGIN_URL,
                )
                if challenge_handler is not None:
                    if challenge_type in (ChallengeType.TURNSTILE, ChallengeType.RECAPTCHA, ChallengeType.HCAPTCHA, ChallengeType.CUSTOM, ChallengeType.CAPTCHA):
                        self.session.promote_to_headful()

                    res = challenge_handler.handle_challenge(ctx)
                    if res.state == ChallengeState.SOLVED:
                        status = self.validate_session()
                        if status.is_authenticated:
                            self._is_authenticated = True
                            self._current_user = credentials.username
                            return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Interactive login successful.")
                    elif res.state == ChallengeState.CANCELLED:
                        return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Authentication cancelled by user.")
                    else:
                        return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Challenge resolution failed: {res.message}")
                else:
                    return AuthResult(
                        vendor_id=self.VENDOR_ID,
                        success=False,
                        message=f"Security challenge encountered ({challenge_type.value}) but no challenge handler configured.",
                        requires_interactive=True,
                        challenge_context=ctx,
                    )

            # Enter username
            user_input = driver.find_element(By.ID, LionSelectors.LOGIN_USERNAME_ID)
            user_input.click()
            user_input.send_keys(Keys.CONTROL + "a")
            user_input.send_keys(Keys.BACKSPACE)
            user_input.send_keys(credentials.username)

            # Enter password
            pass_input = driver.find_element(By.ID, LionSelectors.LOGIN_PASSWORD_ID)
            pass_input.click()
            pass_input.send_keys(Keys.CONTROL + "a")
            pass_input.send_keys(Keys.BACKSPACE)
            pass_input.send_keys(credentials.password)

            # Check for image CAPTCHA input if present on form
            captcha_input_els = driver.find_elements(By.CSS_SELECTOR, "input[name*='captcha'], input[id*='captcha'], #captcha-input")
            captcha_img_els = driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha-img, #captcha-image")
            if captcha_input_els and captcha_img_els:
                img_src = captcha_img_els[0].get_attribute("src") or ""
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=ChallengeType.IMAGE_CAPTCHA,
                    prompt_message="Please enter the characters shown in the CAPTCHA image.",
                    target_url=driver.current_url or LionSelectors.LOGIN_URL,
                    image_base64=img_src if img_src.startswith("data:") else None,
                    metadata={"src": img_src},
                )
                if challenge_handler is not None:
                    res = challenge_handler.handle_challenge(ctx)
                    if res.state == ChallengeState.SOLVED and res.solution:
                        captcha_input_els[0].send_keys(res.solution)
                    elif res.state == ChallengeState.CANCELLED:
                        return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Authentication cancelled by user.")
                    else:
                        return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"CAPTCHA solving failed: {res.message}")
                else:
                    return AuthResult(
                        vendor_id=self.VENDOR_ID,
                        success=False,
                        message="Image CAPTCHA encountered but no challenge handler configured.",
                        requires_interactive=True,
                        challenge_context=ctx,
                    )

            # Submit
            submit_btn = driver.find_element(By.CSS_SELECTOR, LionSelectors.LOGIN_SUBMIT_BTN)
            driver.execute_script("arguments[0].click();", submit_btn)

            self.session.wait_for_settle(2.5)

            # Verify session state
            status = self.validate_session()
            if status.is_authenticated:
                self._is_authenticated = True
                self._current_user = credentials.username
                return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Login successful.")

            # Post-submit challenge detection
            post_challenge = self._detect_challenge_on_page(driver)
            if post_challenge is not None:
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=post_challenge,
                    prompt_message=f"Lion Electronic presented a post-login challenge ({post_challenge.value}).",
                    target_url=driver.current_url or LionSelectors.LOGIN_URL,
                )
                if challenge_handler is not None:
                    self.session.promote_to_headful()
                    res = challenge_handler.handle_challenge(ctx)
                    if res.state == ChallengeState.SOLVED:
                        status = self.validate_session()
                        if status.is_authenticated:
                            self._is_authenticated = True
                            self._current_user = credentials.username
                            return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Interactive login successful.")
                    elif res.state == ChallengeState.CANCELLED:
                        return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Authentication cancelled by user.")
                    return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Post-login challenge not resolved: {res.state.value}")
                else:
                    return AuthResult(
                        vendor_id=self.VENDOR_ID,
                        success=False,
                        message=f"Post-login challenge encountered ({post_challenge.value}) but no challenge handler configured.",
                        requires_interactive=True,
                        challenge_context=ctx,
                    )

            # Check error message on page
            err_els = driver.find_elements(By.CSS_SELECTOR, ".help-block-error, .alert-danger, .has-error")
            for el in err_els:
                txt = el.text.strip()
                if txt:
                    return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login failed: {txt}")

            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Login verification failed.")

        except Exception as e:
            err = LionErrorTranslator.translate_transport_exception(e, {"operation": "authenticate"})
            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login error: {err.message}")

    @staticmethod
    def _detect_challenge_on_page(driver: Any) -> Optional[Any]:
        """Detect whether the current browser DOM contains known security challenges."""
        from core.procurement.challenge_handler import ChallengeType
        try:
            page_src = driver.page_source.lower()
            if "cf-turnstile" in page_src or "challenges.cloudflare.com" in page_src:
                return ChallengeType.TURNSTILE
            if "g-recaptcha" in page_src or "recaptcha" in page_src:
                return ChallengeType.RECAPTCHA
            if "h-captcha" in page_src or "hcaptcha" in page_src:
                return ChallengeType.HCAPTCHA
            if "just a moment" in page_src or "ray id:" in page_src or "cf-challenge" in page_src:
                return ChallengeType.CUSTOM
            if "کد تایید" in page_src or "one-time password" in page_src or "enter otp" in page_src:
                return ChallengeType.OTP
        except Exception:
            pass
        return None

    def validate_session(self) -> SessionStatus:
        """
        Verify whether the active browser session contains logged-in state indicators.
        """
        driver = self.session.get_driver()
        try:
            src = driver.page_source
            cur_url = driver.current_url.lower()

            if LionSelectors.AUTH_LOGOUT_TEXT in src or LionSelectors.AUTH_PROFILE_TEXT in src:
                self._is_authenticated = True
                return SessionStatus(
                    vendor_id=self.VENDOR_ID,
                    is_authenticated=True,
                    username=self._current_user,
                    session_valid=True,
                    message="Session authenticated.",
                )

            if "/login" not in cur_url and self._is_authenticated:
                return SessionStatus(
                    vendor_id=self.VENDOR_ID,
                    is_authenticated=True,
                    username=self._current_user,
                    session_valid=True,
                    message="Session active.",
                )

            return SessionStatus(
                vendor_id=self.VENDOR_ID,
                is_authenticated=False,
                username=None,
                session_valid=False,
                message="Session unauthenticated (Guest mode).",
            )
        except Exception as e:
            return SessionStatus(
                vendor_id=self.VENDOR_ID,
                is_authenticated=False,
                message=f"Session check error: {str(e)}",
            )

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        """
        Dismiss any active SweetAlert modal and return to clean PDP state.
        """
        dismissed = self.session.dismiss_active_modal()
        action = "DISMISS_SWEETALERT_MODAL" if dismissed else "NOOP"
        return RecoveryResult(
            vendor_id=self.VENDOR_ID,
            recovered=dismissed,
            action_taken=action,
            message="Dismissed active modal dialog." if dismissed else "No active modal detected.",
        )

    def close(self) -> None:
        """Cleanly terminate browser session."""
        self.session.close()
        self._is_ready = False
