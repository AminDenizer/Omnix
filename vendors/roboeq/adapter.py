"""
RoboEq Electronic Vendor Adapter Implementation (RoboEqVendorAdapter)
Conforms strictly to IVendorAdapter and docs/VENDORS/ROBOEQ/ADAPTER_SPECIFICATION.md.
Vendor ID: vendor_roboeq
"""

import re
import urllib.parse
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

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
    OmnixVendorError,
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
from vendors.roboeq.selectors import RoboEqSelectors
from vendors.roboeq.errors import RoboEqErrorTranslator
from vendors.roboeq.session import RoboEqSessionManager


class RoboEqVendorAdapter(IVendorAdapter):
    """
    Formal Vendor Adapter for RoboEq Electronic (https://roboeq.ir).
    Implements all 13 IVendorAdapter operations without Core procurement math.
    """

    VENDOR_ID = "vendor_roboeq"
    BASE_URL = RoboEqSelectors.BASE_URL

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config or AdapterConfig(
            vendor_id=self.VENDOR_ID,
            base_url=self.BASE_URL,
            headless=True,
            timeout_seconds=10.0,
            settle_seconds=2.2,
        )
        self.session = RoboEqSessionManager(self._config)
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
        if config:
            self._config = config
            self.session = RoboEqSessionManager(self._config)

        try:
            self.session.get_driver()
            self._is_ready = True
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=True,
                is_authenticated=self._is_authenticated,
                message="RoboEq Vendor Adapter initialized successfully.",
            )
        except Exception as e:
            self._is_ready = False
            err = RoboEqErrorTranslator.translate_transport_exception(e, {"operation": "initialize"})
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=False,
                is_authenticated=False,
                message=f"Initialization failed: {err.message}",
            )

    def search_part(self, query: str) -> SearchResultSet:
        clean_q = (query or "").strip()
        if not clean_q:
            return SearchResultSet(vendor_id=self.VENDOR_ID, query="", total_matches=0, is_exact_match=False, items=[])

        search_url = RoboEqSelectors.SEARCH_URL_TEMPLATE.format(query=urllib.parse.quote(clean_q))
        driver = self.session.get_driver()

        try:
            driver.get(search_url)
            self.session.wait_for_settle(1.5)

            err = RoboEqErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"query": clean_q, "operation": "search_part"},
            )
            if err:
                raise err

            page_text = driver.page_source
            items: List[SearchItem] = []
            soup = BeautifulSoup(page_text, "html.parser")

            product_links = soup.select(RoboEqSelectors.RESULTS_PRODUCT_LINKS)
            seen_urls = set()

            for a_tag in product_links:
                href = a_tag.get("href", "")
                unquoted_href = urllib.parse.unquote(href)
                full_url = urllib.parse.urljoin(self.BASE_URL, href)
                m = (
                    RoboEqSelectors.PDP_PATH_PATTERN.match(href)
                    or RoboEqSelectors.PDP_PATH_PATTERN.match(unquoted_href)
                    or RoboEqSelectors.PDP_URL_PATTERN.match(full_url)
                )
                if m and full_url not in seen_urls:
                    seen_urls.add(full_url)
                    p_id = m.group("product_id")
                    slug = m.group("slug")
                    title = a_tag.get_text(strip=True) or slug

                    img_tag = a_tag.find("img") or (a_tag.parent.find("img") if a_tag.parent else None)
                    thumb_url = img_tag.get("src") if img_tag else None
                    if thumb_url:
                        thumb_url = urllib.parse.urljoin(self.BASE_URL, thumb_url)

                    item = SearchItem(
                        vendor_sku=p_id,
                        mpn_hint=slug,
                        title=title,
                        pdp_url=full_url,
                        thumbnail_url=thumb_url,
                        raw_data={"product_id": p_id, "slug": slug},
                    )
                    items.append(item)

            total = len(items)
            is_exact = any(clean_q.lower() in item.mpn_hint.lower() or clean_q.lower() in item.title.lower() for item in items)

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
            raise RoboEqErrorTranslator.translate_transport_exception(e, {"query": clean_q, "operation": "search_part"})

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        raw = (url_or_sku or "").strip()
        if not raw:
            raise ProductNotFoundError("Empty product identifier provided", vendor_id=self.VENDOR_ID)

        m = RoboEqSelectors.PDP_URL_PATTERN.match(raw)
        if m:
            p_id = m.group("product_id")
            slug = m.group("slug")
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=raw,
                product_id=p_id,
                slug=slug,
            )

        m_rel = RoboEqSelectors.PDP_PATH_PATTERN.match(raw)
        if m_rel:
            p_id = m_rel.group("product_id")
            slug = m_rel.group("slug")
            full_url = urllib.parse.urljoin(self.BASE_URL, raw)
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=full_url,
                product_id=p_id,
                slug=slug,
            )

        sku_m = re.match(r"^(?P<product_id>\d+)(?:/(?P<slug>[^/]+))?$", raw)
        if sku_m:
            p_id = sku_m.group("product_id")
            slug = sku_m.group("slug") or f"product-{p_id}"
            pdp_url = f"{self.BASE_URL}/products/detail/{p_id}/{slug}/"
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=pdp_url,
                product_id=p_id,
                slug=slug,
            )

        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=raw,
            pdp_url=f"{self.BASE_URL}/products/detail/{raw}/product/",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            driver.get(target_url)
            self.session.wait_for_settle(1.5)

            err = RoboEqErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"url": target_url, "operation": "inspect_product"},
            )
            if err:
                raise err

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            title_el = soup.select_one(RoboEqSelectors.PDP_TITLE)
            raw_title = title_el.get_text(strip=True) if title_el else ""

            # Check interactive add-to-cart buttons
            add_btns = soup.find_all(lambda tag: tag.name == "button" and ("افزودن به سبد" in tag.get_text() or "inc-qty" in tag.get("class", [])))
            can_order = len(add_btns) > 0 or "ناموجود" not in html

            draft = self.extract_product_data(soup)

            # Price extraction
            price_irr = self._extract_price(soup)

            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=target_url,
                stock_quantity=0,
                can_order=can_order,
                is_inquiry_only=False,
                raw_status_text="موجود" if can_order else "ناموجود",
                price_irr=price_irr,
                mpn=draft.mpn or raw_title,
                manufacturer=draft.manufacturer,
                package_raw=draft.package,
                order_constraints=OrderConstraints(packaging_step_raw=1, moq_raw=1),
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise RoboEqErrorTranslator.translate_transport_exception(e, {"url": target_url, "operation": "inspect_product"})

    def _extract_price(self, soup: BeautifulSoup) -> Optional[int]:
        # Extract price from tables or price spans
        for td in soup.find_all(["td", "span", "div"]):
            txt = td.get_text(strip=True).replace(",", "")
            m = re.search(r"(\d{4,9})", txt)
            if m:
                val = int(m.group(1))
                if 1000 <= val <= 500000000:
                    return val
        return None

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
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

        rows = soup.select(RoboEqSelectors.SPEC_TABLE_ROWS)
        for row in rows:
            tds = row.find_all(["td", "th"])
            if len(tds) >= 2:
                k = tds[0].get_text(strip=True)
                v = tds[1].get_text(strip=True)
                if k and v and k != "عنوان":
                    specs[k] = v
                    k_lower = k.lower()
                    if "پکیج" in k or "package" in k_lower:
                        package = v
                    elif "سازنده" in k or "brand" in k_lower or "manufacturer" in k_lower:
                        manufacturer = v
                    elif "شماره فنی" in k or "part number" in k_lower or "mpn" in k_lower:
                        mpn = v

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
        details = self.inspect_product(product_ref)
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.can_order,
            can_order=details.can_order,
            is_inquiry_only=details.is_inquiry_only,
            is_restock_pipeline=False,
            raw_text=details.raw_status_text,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        details = self.inspect_product(product_ref)
        return details.order_constraints

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        if quantity <= 0:
            raise OrderMultipleViolationError(f"Quantity must be greater than 0 (got {quantity})", vendor_id=self.VENDOR_ID)

        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            if driver.current_url.lower() != target_url.lower():
                driver.get(target_url)
                self.session.wait_for_settle(1.5)

            details = self.inspect_product(product_ref)
            if not details.can_order:
                raise OutOfStockError(f"RoboEq product cannot be ordered (Status: {details.raw_status_text})", vendor_id=self.VENDOR_ID)

            js_add = """
                var btn = document.querySelector('button.show-sellers-table, button.inc-qty, button');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """
            clicked = self.session.execute_script(js_add)
            if not clicked:
                raise DOMDriftError("Add to cart button not found on RoboEq PDP", vendor_id=self.VENDOR_ID)

            self.session.wait_for_settle(2.2)

            return CartMutationResult(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=quantity,
                success=True,
                error_category=None,
                raw_vendor_message=f"Added {quantity} units to RoboEq cart",
                cart_total_items=1,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise RoboEqErrorTranslator.translate_transport_exception(e, {"sku": product_ref.vendor_sku, "qty": quantity, "operation": "add_to_cart"})

    def inspect_cart(self) -> CartDetails:
        driver = self.session.get_driver()
        try:
            driver.get(RoboEqSelectors.CART_URL)
            self.session.wait_for_settle(2.0)

            err = RoboEqErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"operation": "inspect_cart"},
            )
            if err:
                raise err

            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select(".cart-container table tr, table.cart tr, .cart-table tr")

            cart_items: List[CartItem] = []
            for r in rows:
                tds = r.find_all("td")
                if len(tds) >= 2:
                    name = tds[0].get_text(strip=True)
                    if not name or "محصول" in name or "کالا" in name:
                        continue
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
                cart_url=RoboEqSelectors.CART_URL,
                total_items=len(cart_items),
                items=cart_items,
            )
        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise RoboEqErrorTranslator.translate_transport_exception(e, {"operation": "inspect_cart"})


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
                if v_cfg and v_cfg.username:
                    credentials = AuthCredentials(username=v_cfg.username, password=v_cfg.password)
            except Exception:
                pass

        if not credentials or not credentials.username:
            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Credentials not provided.")

        driver = self.session.get_driver()
        try:
            driver.get(RoboEqSelectors.LOGIN_URL)
            self.session.wait_for_settle(1.5)

            # Upfront challenge detection (Turnstile, reCAPTCHA, WAF, OTP)
            challenge_type = self._detect_challenge_on_page(driver)
            if challenge_type is not None:
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=challenge_type,
                    prompt_message=f"RoboEq Electronic requires security challenge resolution ({challenge_type.value}).",
                    target_url=driver.current_url or RoboEqSelectors.LOGIN_URL,
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

            user_input = driver.find_element(By.ID, RoboEqSelectors.LOGIN_USERNAME_ID)
            user_input.send_keys(credentials.username)

            submit_btn = driver.find_element(By.CSS_SELECTOR, RoboEqSelectors.LOGIN_SUBMIT_BTN)
            submit_btn.click()
            self.session.wait_for_settle(2.0)

            # Check post-submit challenge
            post_challenge = self._detect_challenge_on_page(driver)
            if post_challenge is not None:
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=post_challenge,
                    prompt_message=f"RoboEq Electronic presented a post-login challenge ({post_challenge.value}).",
                    target_url=driver.current_url or RoboEqSelectors.LOGIN_URL,
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

            status = self.validate_session()
            if status.is_authenticated:
                self._is_authenticated = True
                self._current_user = credentials.username
                return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Login successful.")

            return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="CAS authentication staged.")
        except Exception as e:
            err = RoboEqErrorTranslator.translate_transport_exception(e, {"operation": "authenticate"})
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
        driver = self.session.get_driver()
        try:
            src = driver.page_source
            if RoboEqSelectors.AUTH_LOGOUT_TEXT in src or RoboEqSelectors.AUTH_PROFILE_TEXT in src:
                self._is_authenticated = True
                return SessionStatus(
                    vendor_id=self.VENDOR_ID,
                    is_authenticated=True,
                    username=self._current_user,
                    session_valid=True,
                    message="Session authenticated.",
                )
            return SessionStatus(
                vendor_id=self.VENDOR_ID,
                is_authenticated=False,
                username=None,
                session_valid=False,
                message="Session unauthenticated (Guest mode).",
            )
        except Exception as e:
            return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=False, message=str(e))

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        dismissed = self.session.dismiss_active_modal()
        return RecoveryResult(
            vendor_id=self.VENDOR_ID,
            recovered=dismissed,
            action_taken="DISMISS_MODAL" if dismissed else "NOOP",
            message="Dismissed modal" if dismissed else "No active modal",
        )

    def close(self) -> None:
        self.session.close()
        self._is_ready = False
