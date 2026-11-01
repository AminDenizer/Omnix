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
    PluginCapability,
    PluginProcurementMode,
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
try:
    from .selectors import LionSelectors
    from .errors import LionErrorTranslator
    from .session import LionSessionManager
except ImportError:
    from vendors.lion.selectors import LionSelectors
    from vendors.lion.errors import LionErrorTranslator
    from vendors.lion.session import LionSessionManager


def _normalize_persian_text(text: str) -> str:
    """Normalize Persian unicode characters, ZWNJ, spaces, and character variants."""
    if not text:
        return ""
    t = text.replace("\u200c", " ").replace("\u200b", " ").replace("\xa0", " ")
    t = t.replace("ك", "ک").replace("ي", "ی").replace("ئ", "ی").replace("ة", "ه")
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ـ", "").replace("–", "-").replace("—", "-")
    return " ".join(t.split()).strip()


class LionVendorAdapter(IVendorAdapter):

    """
    Formal Vendor Adapter for Lion Electronic (https://lionelectronic.ir).
    Implements all 13 IVendorAdapter operations without Core procurement math.
    """

    VENDOR_ID = "vendor_lion"
    BASE_URL = LionSelectors.BASE_URL

    _SUPPORTED_CAPABILITIES: frozenset = frozenset({
        PluginCapability.PRODUCT_URL_RECOGNITION,
        PluginCapability.PRODUCT_INSPECTION,
        PluginCapability.CART_URL_RESOLUTION,
        PluginCapability.MPN_SEARCH,
        PluginCapability.LIVE_STOCK_PROBE,
        PluginCapability.TIERED_PRICING,
        PluginCapability.MODE_A_STAGING,
    })
    _SUPPORTED_MODES: frozenset = frozenset({
        PluginProcurementMode.MODE_A,
    })

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
            can_order_js = None
            try:
                can_order_js = self.session.execute_script(
                    "return (typeof window.productCanOrder !== 'undefined') ? window.productCanOrder : null;"
                )
            except Exception:
                can_order_js = None

            # Extract Stock amount text and status indicators
            stock_qty = 0
            stock_span = soup.select_one(LionSelectors.STOCK_AMOUNT_SPAN)
            stock_container = soup.select_one(LionSelectors.STOCK_CONTAINER)

            raw_status_text = ""
            if stock_span:
                raw_status_text = stock_span.get_text(strip=True)
            elif stock_container:
                raw_status_text = stock_container.get_text(strip=True)

            if raw_status_text:
                clean_digits = raw_status_text.replace(",", "").replace(" ", "")
                sm = re.search(r"(\d+)", clean_digits)
                if sm:
                    stock_qty = int(sm.group(1))

            # Determine inquiry vs buy button
            buy_btn = soup.select_one(LionSelectors.BTN_BUY_PRIMARY)
            inquiry_btn = soup.select_one(LionSelectors.BTN_INQUIRY_PRIMARY)
            is_inquiry = bool(inquiry_btn is not None and buy_btn is None)

            # Normalize Persian status strings
            norm_status = _normalize_persian_text(raw_status_text)
            norm_compact = re.sub(r"[\s\-_]+", "", norm_status)

            page_stock_text = ""
            if stock_container:
                page_stock_text = _normalize_persian_text(stock_container.get_text(" ", strip=True))
            page_stock_compact = re.sub(r"[\s\-_]+", "", page_stock_text)

            is_coming_soon = (
                "به زودی" in norm_status
                or "بهزودی" in norm_compact
                or "به زودی" in page_stock_text
                or "بهزودی" in page_stock_compact
            )
            is_out_of_stock = (
                "اتمام موجودی" in norm_status
                or "ناموجود" in norm_status
                or "عدم موجودی" in norm_status
                or "تمام شد" in norm_status
                or "اتمام موجودی" in page_stock_text
                or "ناموجود" in page_stock_text
            )

            # Fail-closed procurement eligibility gate for Lion:
            # - Explicitly available and eligible for immediate purchase -> ALLOW
            # - به‌زودی -> BLOCK
            # - اتمام موجودی -> BLOCK
            # - Status cannot be reliably identified -> BLOCK
            if is_inquiry:
                can_order = False
                raw_status_text = raw_status_text or "استعلام (Inquiry-only)"
            elif can_order_js is False:
                can_order = False
                raw_status_text = raw_status_text or "سفارش غیرفعال (productCanOrder=false)"
            elif is_coming_soon:
                can_order = False
                raw_status_text = "به‌زودی"
            elif is_out_of_stock or (stock_span and stock_qty == 0):
                can_order = False
                raw_status_text = raw_status_text if (raw_status_text and not raw_status_text.isdigit()) else "اتمام موجودی"
            elif stock_qty > 0 and not is_coming_soon and not is_out_of_stock:
                can_order = True
            else:
                # Status cannot be reliably identified -> BLOCK (Fail-Closed)
                can_order = False
                raw_status_text = raw_status_text or "وضعیت نامشخص (Fail-Closed: Status Unidentified)"

            # Extract raw packaging step from #quantity-cell attribute
            qty_input = soup.select_one(LionSelectors.INPUT_QUANTITY_CSS)
            raw_step = 1
            if qty_input:
                val = qty_input.get("value", "1")
                try:
                    raw_step = max(int(float(val)), 1)
                except ValueError:
                    raw_step = 1

            # Extract technical specifications
            draft = self.extract_product_data(soup)

            # Extract Price and Volume Tiers
            price_tiers = self._extract_price_tiers(soup)
            price_irr = None
            if price_tiers:
                price_irr = price_tiers[0]["unit_price_irr"]
                if raw_step == 1 and price_tiers[0]["min_quantity"] > 1:
                    raw_step = price_tiers[0]["min_quantity"]
            else:
                price_el = soup.select_one(".product-price, .price-value, .price, .price-table, [class*='price']")
                if price_el:
                    price_text = price_el.get_text(strip=True).replace(",", "").replace(" ", "")
                    pm = re.search(r"(\d+)", price_text)
                    if pm:
                        price_irr = int(pm.group(1))

            if price_irr is None:
                # Page-wide regex fallback for IRR prices
                page_txt = soup.get_text(" ", strip=True)
                all_prices = re.findall(r"([\d,]{3,})\s*(?:ریال|تومان|IRR)", page_txt)
                if all_prices:
                    for p_str in all_prices:
                        val = int(p_str.replace(",", ""))
                        if val > 100:  # Reasonable price threshold
                            price_irr = val
                            break

            raw_data = {"price_tiers": price_tiers}

            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=target_url,
                stock_quantity=stock_qty,
                can_order=can_order,
                is_inquiry_only=is_inquiry,
                raw_status_text=raw_status_text or ("موجود" if can_order else "ناموجود"),
                price_irr=price_irr,
                mpn=draft.mpn or getattr(product_ref, "slug", None) or product_ref.vendor_sku,
                manufacturer=draft.manufacturer,
                package_raw=draft.package,
                order_constraints=OrderConstraints(
                    packaging_step_raw=raw_step,
                    moq_raw=raw_step,
                ),
                raw_data=raw_data,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise LionErrorTranslator.translate_transport_exception(e, {"url": target_url, "operation": "inspect_product"})

    def _extract_price_tiers(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract tiered pricing brackets from Lion PDP."""
        tiers: List[Dict[str, Any]] = []
        # Search all tables and rows
        rows = soup.select("table tr, .price-table tr, div[class*='price'] tr, tr")
        for row in rows:
            tds = row.find_all(["td", "th", "div", "span"])
            row_txt = row.get_text(" ", strip=True)
            # Check pattern: Quantity (e.g. 10, 200, 2000) and Price (e.g. 366,226 ریال)
            qm = re.search(r"^(\d+)", row_txt)
            pm = re.search(r"([\d,]{3,})\s*(?:ریال|تومان)?", row_txt)
            if qm and pm:
                try:
                    q = int(qm.group(1))
                    p = int(pm.group(1).replace(",", ""))
                    if p > 100 and q >= 1:
                        tiers.append({"min_quantity": q, "unit_price_irr": p})
                except Exception:
                    pass
        # Deduplicate and sort
        seen_q = set()
        unique_tiers = []
        for t in sorted(tiers, key=lambda x: x["min_quantity"]):
            if t["min_quantity"] not in seen_q:
                seen_q.add(t["min_quantity"])
                unique_tiers.append(t)
        return unique_tiers

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        """
        Extract technical specs ('Part Number', 'Manufacture', 'Package', 'Lion Part') from BeautifulSoup or HTML.
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

        # 1. Check table rows
        rows = soup.select(LionSelectors.SPEC_TABLE_ROWS)
        for row in rows:
            tds = row.find_all(["td", "th"])
            if len(tds) >= 2:
                key = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                if key and val:
                    specs[key] = val
                    k_lower = key.lower()
                    if "شماره فنی" in key or "پارت نامبر" in key or "part number" in k_lower or "partnumber" in k_lower or "mpn" in k_lower:
                        mpn = val
                    elif "سازنده" in key or "تولید کننده" in key or "تولیدکننده" in key or "manufacturer" in k_lower or "manufacture" in k_lower or "brand" in k_lower:
                        manufacturer = val
                    elif "پکیج" in key or "package" in k_lower or "case" in k_lower or "footprint" in k_lower:
                        package = val

        # 2. Check list items / text elements (e.g. • Part Number C3216X7R1H106K160AC)
        full_text = soup.get_text("\n", strip=True)
        for line in full_text.splitlines():
            line_clean = line.strip(" •-\t\r")
            if not mpn:
                m_mpn = re.search(r"^(?:Part\s*Number|شماره\s*فنی|پارت\s*نامبر|MPN)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\+\/]+)", line_clean, re.IGNORECASE)
                if m_mpn:
                    mpn = m_mpn.group(1).strip()
            if not manufacturer:
                m_mfg = re.search(r"^(?:Manufacture|Manufacturer|سازنده|تولید\s*کننده|Brand|برند)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\s]+)", line_clean, re.IGNORECASE)
                if m_mfg:
                    manufacturer = m_mfg.group(1).strip()
            if not package:
                m_pkg = re.search(r"^(?:Package|پکیج|سایز|Footprint)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\s]+)", line_clean, re.IGNORECASE)
                if m_pkg:
                    package = m_pkg.group(1).strip()

        # 3. Fallback to PDP title / H1 if MPN is not in specs table or text
        if not mpn:
            title_el = soup.select_one(LionSelectors.PDP_TITLE)
            if title_el:
                raw_t = title_el.get_text(strip=True)
                if raw_t:
                    mpn = raw_t

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
        norm_text = _normalize_persian_text(raw_text)
        norm_compact = re.sub(r"[\s\-_]+", "", norm_text)
        is_restock = "به زودی" in norm_text or "بهزودی" in norm_compact

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
            # Check authentication / session reuse (GAP-09)
            try:
                status = self.validate_session()
            except Exception:
                status = SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=False)

            if not status.is_authenticated:
                from settings_manager import settings
                v_cfg = settings.get_vendor_settings(self.VENDOR_ID) if hasattr(settings, "get_vendor_settings") else None
                u = (v_cfg.username if v_cfg else "") or settings.get("lion_username", "").strip()
                p = (v_cfg.password if v_cfg else "") or settings.get("lion_password", "").strip()

                if u and p:
                    auth_res = self.authenticate(credentials=AuthCredentials(username=u, password=p))
                    if not auth_res or not auth_res.success:
                        err_msg = auth_res.message if auth_res else "Authentication failed"
                        if auth_res and getattr(auth_res, "requires_interactive", False):
                            from core.errors import SecurityChallengeError
                            raise SecurityChallengeError(
                                f"Lion Electronic security challenge encountered: {err_msg}",
                                vendor_id=self.VENDOR_ID,
                            )
                        raise AuthenticationRequiredError(
                            f"Lion Electronic authentication failed: {err_msg}",
                            vendor_id=self.VENDOR_ID,
                        )

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
            rows = soup.select(".cart-item") or soup.select("table.table tbody tr, .cart-table tbody tr")

            cart_items: List[CartItem] = []
            for r in rows:
                # Check modern Lion cart structure: .cart-item / .checkout-item
                title_el = r.select_one(".product-title")
                qty_input = r.select_one("input.counter, input[name='quantity'], input[name*='quantity'], .quantity-cell")
                if title_el:
                    name = title_el.get_text(strip=True)
                    qty = 1
                    if qty_input and qty_input.get("value"):
                        try:
                            qty = int(float(qty_input.get("value").replace(",", "")))
                        except Exception:
                            qty = 1
                    cart_items.append(
                        CartItem(
                            vendor_sku=name,
                            product_name=name,
                            quantity=qty,
                        )
                    )
                    continue

                # Fallback to legacy table row format
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
        """Authenticate browser session using provided credentials."""
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

            user_input = driver.find_element(By.ID, LionSelectors.LOGIN_USERNAME_ID)
            user_input.click()
            user_input.send_keys(Keys.CONTROL + "a")
            user_input.send_keys(Keys.BACKSPACE)
            user_input.send_keys(credentials.username)

            pass_input = driver.find_element(By.ID, LionSelectors.LOGIN_PASSWORD_ID)
            pass_input.click()
            pass_input.send_keys(Keys.CONTROL + "a")
            pass_input.send_keys(Keys.BACKSPACE)
            pass_input.send_keys(credentials.password)

            submit_btn = driver.find_element(By.CSS_SELECTOR, LionSelectors.LOGIN_SUBMIT_BTN)
            driver.execute_script("arguments[0].click();", submit_btn)

            self.session.wait_for_settle(2.5)

            status = self.validate_session()
            if status.is_authenticated:
                self._is_authenticated = True
                self._current_user = credentials.username
                return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Login successful.")

            err_els = driver.find_elements(By.CSS_SELECTOR, ".help-block-error, .alert-danger, .has-error")
            for el in err_els:
                txt = el.text.strip()
                if txt:
                    return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login failed: {txt}")

            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Login verification failed.")

        except Exception as e:
            err = LionErrorTranslator.translate_transport_exception(e, {"operation": "authenticate"})
            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login error: {err.message}")


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

    def get_cart_url(self) -> Optional[str]:
        """Return the storefront cart URL for Lion Electronic."""
        return LionSelectors.CART_URL

    def is_pdp_url(self, url: str) -> bool:
        """Check whether the given URL matches a Lion Electronic Product Detail Page (PDP)."""
        clean = (url or "").strip()
        if not clean:
            return False
        return bool(LionSelectors.PDP_URL_PATTERN.match(clean) or LionSelectors.PDP_PATH_PATTERN.match(clean))

