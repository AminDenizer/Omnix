"""
Javan Electronic Vendor Adapter Implementation (JavanVendorAdapter)
Conforms strictly to IVendorAdapter and docs/VENDORS/JAVAN/ADAPTER_SPECIFICATION.md.
Vendor ID: vendor_javan
"""

import re
import urllib.parse
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
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
from vendors.javan.selectors import JavanSelectors
from vendors.javan.errors import JavanErrorTranslator
from vendors.javan.session import JavanSessionManager


class JavanVendorAdapter(IVendorAdapter):
    """
    Formal Vendor Adapter for Javan Electronic (https://www.javanelec.com).
    Implements all 13 IVendorAdapter operations without Core procurement math.
    """

    VENDOR_ID = "vendor_javan"
    BASE_URL = JavanSelectors.BASE_URL

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config or AdapterConfig(
            vendor_id=self.VENDOR_ID,
            base_url=self.BASE_URL,
            headless=True,
            timeout_seconds=10.0,
            settle_seconds=2.2,
        )
        self.session = JavanSessionManager(self._config)
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
            self.session = JavanSessionManager(self._config)

        try:
            self.session.get_driver()
            self._is_ready = True
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=True,
                is_authenticated=self._is_authenticated,
                message="Javan Vendor Adapter initialized successfully.",
            )
        except Exception as e:
            self._is_ready = False
            err = JavanErrorTranslator.translate_transport_exception(e, {"operation": "initialize"})
            return AdapterStatus(
                vendor_id=self.VENDOR_ID,
                is_ready=False,
                is_authenticated=False,
                message=f"Initialization failed: {err.message}",
            )

    def search_part(self, query: str) -> SearchResultSet:
        """
        Execute search on Javan Electronic via GET /shop?searchfilter={query}#filter_items_-1.
        Extracts candidate cards and originality badges.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return SearchResultSet(vendor_id=self.VENDOR_ID, query="", total_matches=0, is_exact_match=False, items=[])

        search_url = JavanSelectors.SEARCH_URL_TEMPLATE.format(query=urllib.parse.quote(clean_q))
        driver = self.session.get_driver()

        try:
            driver.get(search_url)
            self.session.wait_for_settle(1.5)

            # Check for page level errors (404, WAF, etc.)
            err = JavanErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"query": clean_q, "operation": "search_part"},
            )
            if err:
                raise err

            page_text = driver.page_source

            # Check for zero results marker "0 محصول"
            if JavanSelectors.ZERO_RESULTS_MARKER in page_text:
                return SearchResultSet(
                    vendor_id=self.VENDOR_ID,
                    query=clean_q,
                    total_matches=0,
                    is_exact_match=False,
                    items=[],
                )

            items: List[SearchItem] = []
            soup = BeautifulSoup(page_text, "html.parser")

            # Extract product links matching canonical regex /shop/product/{id}/{brand}/{part}
            product_links = soup.select(JavanSelectors.RESULTS_PRODUCT_LINKS)
            seen_urls = set()

            for a_tag in product_links:
                href = a_tag.get("href", "")
                full_url = urllib.parse.urljoin(self.BASE_URL, href)
                m = JavanSelectors.PDP_PATH_PATTERN.match(href) or JavanSelectors.PDP_URL_PATTERN.match(full_url)
                if m and full_url not in seen_urls:
                    seen_urls.add(full_url)
                    p_id = m.group("product_id")
                    mfr = m.group("manufacturer")
                    slug = m.group("slug")
                    sku = p_id

                    # Extract title / text
                    title = a_tag.get_text(strip=True) or f"{slug} | {mfr}"

                    # Try to find thumbnail
                    img_tag = a_tag.find("img") or (a_tag.parent.find("img") if a_tag.parent else None)
                    thumb_url = img_tag.get("src") if img_tag else None
                    if thumb_url:
                        thumb_url = urllib.parse.urljoin(self.BASE_URL, thumb_url)

                    # Check originality badge in container
                    container = a_tag.parent or a_tag
                    is_orig = True
                    badge = container.find("span", attrs={"data-prdtype": True}) if container else None
                    if badge and badge.get("data-prdtype", "").lower() == "copy":
                        is_orig = False

                    item = SearchItem(
                        vendor_sku=sku,
                        mpn_hint=slug,
                        title=title,
                        pdp_url=full_url,
                        thumbnail_url=thumb_url,
                        raw_data={
                            "product_id": p_id,
                            "manufacturer": mfr,
                            "slug": slug,
                            "is_original": is_orig,
                        },
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
            raise JavanErrorTranslator.translate_transport_exception(e, {"query": clean_q, "operation": "search_part"})

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        """
        Resolve a URL or SKU to a normalized ProductReference.
        """
        raw = (url_or_sku or "").strip()
        if not raw:
            raise ProductNotFoundError("Empty product identifier provided", vendor_id=self.VENDOR_ID)

        # Case 1: Full URL
        m = JavanSelectors.PDP_URL_PATTERN.match(raw)
        if m:
            p_id = m.group("product_id")
            mfr = m.group("manufacturer")
            slug = m.group("slug")
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=raw,
                product_id=p_id,
                slug=slug,
            )

        # Case 2: Relative URL
        m_rel = JavanSelectors.PDP_PATH_PATTERN.match(raw)
        if m_rel:
            p_id = m_rel.group("product_id")
            mfr = m_rel.group("manufacturer")
            slug = m_rel.group("slug")
            full_url = urllib.parse.urljoin(self.BASE_URL, raw)
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=full_url,
                product_id=p_id,
                slug=slug,
            )

        # Case 3: SKU format '17930' or '17930/texas-instruments/ne555p'
        sku_m = re.match(r"^(?P<product_id>\d+)(?:/(?P<manufacturer>[a-zA-Z0-9_.-]+)/(?P<slug>[a-zA-Z0-9_.-]+))?$", raw)
        if sku_m:
            p_id = sku_m.group("product_id")
            mfr = sku_m.group("manufacturer") or "generic"
            slug = sku_m.group("slug") or f"product-{p_id}"
            pdp_url = f"{self.BASE_URL}/shop/product/{p_id}/{mfr}/{slug}"
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=pdp_url,
                product_id=p_id,
                slug=slug,
            )

        # Fallback: Assume SKU or ID
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=raw,
            pdp_url=f"{self.BASE_URL}/shop/product/{raw}/unknown/part",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        """
        Navigate to PDP and extract complete technical specs, tiered pricing, stock, and constraints.
        """
        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            driver.get(target_url)
            self.session.wait_for_settle(1.5)

            # Check 404 and page errors
            err = JavanErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"url": target_url, "operation": "inspect_product"},
            )
            if err:
                raise err

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Extract Title & MPN from H1
            title_el = soup.select_one(JavanSelectors.PDP_TITLE)
            raw_title = title_el.get_text(strip=True) if title_el else ""

            # Check add to cart button presence
            add_btn = soup.select_one(JavanSelectors.BTN_ADD_TO_CART)
            can_order = add_btn is not None

            # Extract technical specifications table
            draft = self.extract_product_data(soup)

            # Extract pricing tiers table
            price_tiers = self._extract_price_tiers(soup)
            price_irr = price_tiers[0]["unit_price_irr"] if price_tiers else None
            packaging_step = price_tiers[0]["min_quantity"] if price_tiers else 1
            moq = packaging_step

            # Fallback for MPN if not in specs table
            mpn = draft.mpn
            if not mpn:
                if "|" in raw_title:
                    mpn = raw_title.split("|")[0].strip()
                elif raw_title:
                    mpn = raw_title.split()[0].strip()
                else:
                    mpn = product_ref.slug

            # Fallback for Manufacturer if not in specs table
            mfr = draft.manufacturer
            if not mfr and "|" in raw_title:
                mfr = raw_title.split("|")[1].strip()

            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=target_url,
                stock_quantity=0,
                can_order=can_order,
                is_inquiry_only=False,
                raw_status_text="موجود" if can_order else "ناموجود",
                price_irr=price_irr,
                mpn=mpn,
                manufacturer=mfr,
                package_raw=draft.package,
                order_constraints=OrderConstraints(
                    packaging_step_raw=packaging_step,
                    moq_raw=moq,
                ),
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise JavanErrorTranslator.translate_transport_exception(e, {"url": target_url, "operation": "inspect_product"})

    def _extract_price_tiers(self, soup: BeautifulSoup) -> List[Dict[str, int]]:
        """
        Extract tiered pricing brackets from Javan PDP tables.
        Rows match patterns like: '50 عدد' -> '78,100 ریال'
        """
        tiers: List[Dict[str, int]] = []
        rows = soup.select("table tr")

        for row in rows:
            text = row.get_text(" ", strip=True)
            # Look for quantity pattern and price pattern
            # Example: "50 عدد 78,100 ریال" or cells [50 عدد, 78,100 ریال]
            tds = row.find_all(["td", "th"])
            if len(tds) >= 2:
                col1 = tds[0].get_text(strip=True)
                col2 = tds[1].get_text(strip=True)
                
                # Check if col1 contains quantity (e.g. '50 عدد')
                qm = re.search(r"([\d,]+)\s*عدد", col1)
                pm = re.search(r"([\d,]+)", col2)
                if qm and pm:
                    qty = int(qm.group(1).replace(",", ""))
                    price = int(pm.group(1).replace(",", ""))
                    tiers.append({"min_quantity": qty, "unit_price_irr": price})
            else:
                # Single row text search
                qm = re.search(r"([\d,]+)\s*عدد", text)
                pm = re.search(r"([\d,]+)\s*(?:ریال|تومان|IRR)", text)
                if qm and pm:
                    qty = int(qm.group(1).replace(",", ""))
                    price = int(pm.group(1).replace(",", ""))
                    tiers.append({"min_quantity": qty, "unit_price_irr": price})

        # Sort tiers by min_quantity ascending
        tiers.sort(key=lambda t: t["min_quantity"])
        return tiers

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        """
        Extract technical specs ('Brand', 'Package', 'Mounting Style', etc.) from BeautifulSoup or HTML string.
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

        rows = soup.select(JavanSelectors.SPEC_TABLE_ROWS)
        for row in rows:
            tds = row.find_all(["td", "th"])
            if len(tds) >= 2:
                key = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                if key and val and key != "Features" and key != "انتخاب ویژگی":
                    specs[key] = val
                    k_lower = key.lower()
                    if "brand" in k_lower or "سازنده" in key or "manufacturer" in k_lower:
                        manufacturer = val
                    elif "package" in k_lower or "پکیج" in key or "case" in k_lower:
                        package = val
                    elif "mpn" in k_lower or "part number" in k_lower or "شماره فنی" in key:
                        mpn = val

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
        Inspect live stock availability on Javan Electronic.
        """
        details = self.inspect_product(product_ref)
        raw_text = details.raw_status_text

        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.can_order,
            can_order=details.can_order,
            is_inquiry_only=details.is_inquiry_only,
            is_restock_pipeline=False,
            raw_text=raw_text,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        """
        Extract raw packaging step and MOQ from Javan pricing tiers without client-side modifications.
        """
        details = self.inspect_product(product_ref)
        return details.order_constraints

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        """
        Internal Browser AJAX / Form cart mutation:
        1. Click 'button.btn-success-outline[type="submit"]'.
        2. Wait 2.0-2.5s settle window.
        3. Intercept and translate any validation error alert.
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
                raise OutOfStockError(f"Javan product cannot be ordered (Status: {details.raw_status_text})", vendor_id=self.VENDOR_ID)

            # Submit Add to Cart form via button click
            js_mutation = """
                var btn = document.querySelector('button.btn-success-outline[type="submit"], button[type="submit"]');
                if (btn && !btn.classList.contains('disabled')) {
                    btn.click();
                    return true;
                }
                var form = document.querySelector('form[action*="shoppingcarts"], form.form-horizontal');
                if (form) {
                    form.submit();
                    return true;
                }
                return false;
            """
            clicked = self.session.execute_script(js_mutation)
            if not clicked:
                raise DOMDriftError("Add to cart button not found or disabled on Javan PDP", vendor_id=self.VENDOR_ID)

            # Enforce 2.0-2.5s asynchronous settle window
            self.session.wait_for_settle(2.2)

            # Check for error alerts
            err_popups = driver.find_elements(By.CSS_SELECTOR, ".alert-danger, .validation-summary-errors, .toast-error")
            for ep in err_popups:
                ep_text = ep.text.strip()
                if ep_text and any(kw in ep_text for kw in ["ضریب", "موجودی", "خطا", "امکان", "ناموفق", "مضرب", "بسته", "حداقل"]):
                    self.session.dismiss_active_modal()
                    err = JavanErrorTranslator.translate_modal_message(ep_text, {"requested_qty": quantity, "product_sku": product_ref.vendor_sku})
                    raise err

            return CartMutationResult(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=quantity,
                success=True,
                error_category=None,
                raw_vendor_message=f"Added {quantity} units to Javan shopping cart",
                cart_total_items=1,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise JavanErrorTranslator.translate_transport_exception(e, {"sku": product_ref.vendor_sku, "qty": quantity, "operation": "add_to_cart"})

    def inspect_cart(self) -> CartDetails:
        """
        Navigate to /shoppingcarts and extract staged line items.
        """
        driver = self.session.get_driver()

        try:
            driver.get(JavanSelectors.CART_URL)
            self.session.wait_for_settle(2.0)

            err = JavanErrorTranslator.translate_page_state(
                page_title=driver.title,
                page_source=driver.page_source,
                current_url=driver.current_url,
                context={"operation": "inspect_cart"},
            )
            if err:
                raise err

            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select(JavanSelectors.CART_ITEM_ROWS)

            cart_items: List[CartItem] = []
            for r in rows:
                tds = r.find_all("td")
                if len(tds) >= 2:
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
                cart_url=JavanSelectors.CART_URL,
                total_items=len(cart_items),
                items=cart_items,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise JavanErrorTranslator.translate_transport_exception(e, {"operation": "inspect_cart"})

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        """
        Authenticate browser session using provided credentials.
        """
        if not credentials or not credentials.username or not credentials.password:
            return AuthResult(
                vendor_id=self.VENDOR_ID,
                success=False,
                message="Javan authentication credentials not provided.",
            )

        driver = self.session.get_driver()

        try:
            driver.get(JavanSelectors.LOGIN_URL)
            self.session.wait_for_settle(1.5)

            # Enter username
            user_input = driver.find_element(By.ID, JavanSelectors.LOGIN_USERNAME_ID)
            user_input.click()
            user_input.send_keys(Keys.CONTROL + "a")
            user_input.send_keys(Keys.BACKSPACE)
            user_input.send_keys(credentials.username)

            # Enter password
            pass_input = driver.find_element(By.ID, JavanSelectors.LOGIN_PASSWORD_ID)
            pass_input.click()
            pass_input.send_keys(Keys.CONTROL + "a")
            pass_input.send_keys(Keys.BACKSPACE)
            pass_input.send_keys(credentials.password)

            # Submit
            submit_btn = driver.find_element(By.CSS_SELECTOR, JavanSelectors.LOGIN_SUBMIT_BTN)
            driver.execute_script("arguments[0].click();", submit_btn)

            self.session.wait_for_settle(2.5)

            # Verify session state
            status = self.validate_session()
            if status.is_authenticated:
                self._is_authenticated = True
                self._current_user = credentials.username
                return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Login successful.")

            # Check error message on page
            err_els = driver.find_elements(By.CSS_SELECTOR, ".validation-summary-errors, .alert-danger, .field-validation-error")
            for el in err_els:
                txt = el.text.strip()
                if txt:
                    return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login failed: {txt}")

            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Login verification failed.")

        except Exception as e:
            err = JavanErrorTranslator.translate_transport_exception(e, {"operation": "authenticate"})
            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login error: {err.message}")

    def validate_session(self) -> SessionStatus:
        """
        Verify whether the active browser session contains logged-in state indicators.
        """
        driver = self.session.get_driver()
        try:
            src = driver.page_source
            cur_url = driver.current_url.lower()

            if JavanSelectors.AUTH_LOGOUT_TEXT in src or JavanSelectors.AUTH_PROFILE_TEXT in src:
                self._is_authenticated = True
                return SessionStatus(
                    vendor_id=self.VENDOR_ID,
                    is_authenticated=True,
                    username=self._current_user,
                    session_valid=True,
                    message="Session authenticated.",
                )

            if "/account/login" not in cur_url and self._is_authenticated:
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
        Dismiss any active modal and return to clean state.
        """
        dismissed = self.session.dismiss_active_modal()
        action = "DISMISS_MODAL" if dismissed else "NOOP"
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
