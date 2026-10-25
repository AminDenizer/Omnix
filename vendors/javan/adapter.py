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
    from .selectors import JavanSelectors
    from .errors import JavanErrorTranslator
    from .session import JavanSessionManager
except ImportError:
    from vendors.javan.selectors import JavanSelectors
    from vendors.javan.errors import JavanErrorTranslator
    from vendors.javan.session import JavanSessionManager


def _normalize_persian_text(text: str) -> str:
    """Normalize Persian unicode characters, ZWNJ, spaces, and character variants."""
    if not text:
        return ""
    t = text.replace("\u200c", " ").replace("\u200b", " ").replace("\xa0", " ")
    t = t.replace("ك", "ک").replace("ي", "ی").replace("ئ", "ی").replace("ة", "ه")
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ـ", "").replace("–", "-").replace("—", "-")
    return " ".join(t.split()).strip()


class JavanVendorAdapter(IVendorAdapter):

    """
    Formal Vendor Adapter for Javan Electronic (https://www.javanelec.com).
    Implements all 13 IVendorAdapter operations without Core procurement math.
    """

    VENDOR_ID = "vendor_javan"
    BASE_URL = JavanSelectors.BASE_URL

    _SUPPORTED_CAPABILITIES: frozenset = frozenset({
        PluginCapability.PRODUCT_URL_RECOGNITION,
        PluginCapability.PRODUCT_INSPECTION,
        PluginCapability.CART_URL_RESOLUTION,
        PluginCapability.MPN_SEARCH,
        PluginCapability.LIVE_STOCK_PROBE,
        PluginCapability.TIERED_PRICING,
        PluginCapability.MODE_A_STAGING,
        PluginCapability.MODE_B_STAGING,
    })
    _SUPPORTED_MODES: frozenset = frozenset({
        PluginProcurementMode.MODE_A,
        PluginProcurementMode.MODE_B,
    })

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
        if raw.startswith("http://") or raw.startswith("https://"):
            m = JavanSelectors.PDP_URL_PATTERN.match(raw)
            if m:
                p_id = m.group("product_id")
                mfr = m.group("manufacturer") or "generic"
                slug = m.group("slug") or f"product-{p_id}"
                return ProductReference(
                    vendor_id=self.VENDOR_ID,
                    vendor_sku=p_id,
                    pdp_url=raw,
                    product_id=p_id,
                    slug=slug,
                )

            # Check hash navigation (#dtl/7589)
            dtl_m = re.search(r"#dtl/(\d+)", raw)
            if dtl_m:
                p_id = dtl_m.group(1)
                return ProductReference(
                    vendor_id=self.VENDOR_ID,
                    vendor_sku=p_id,
                    pdp_url=raw,
                    product_id=p_id,
                    slug=f"product-{p_id}",
                )

            # Check /shop/product/123, /products/123, /product/123, /item/123
            prod_m = re.search(r"/(?:shop/product|products|product|item)/(\d+)(?:/([a-zA-Z0-9_.-]+))?(?:/([a-zA-Z0-9_.-]+))?", raw)
            if prod_m:
                p_id = prod_m.group(1)
                mfr = prod_m.group(2) or "generic"
                slug = prod_m.group(3) or f"product-{p_id}"
                return ProductReference(
                    vendor_id=self.VENDOR_ID,
                    vendor_sku=p_id,
                    pdp_url=raw,
                    product_id=p_id,
                    slug=slug,
                )

            # Generic Javan URL fallback - preserve exact raw URL
            dig_m = re.search(r"(\d+)", raw)
            p_id = dig_m.group(1) if dig_m else "product"
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=raw,
                product_id=p_id,
                slug="product",
            )

        # Case 2: Relative URL
        m_rel = JavanSelectors.PDP_PATH_PATTERN.match(raw)
        if m_rel:
            p_id = m_rel.group("product_id")
            mfr = m_rel.group("manufacturer") or "generic"
            slug = m_rel.group("slug") or f"product-{p_id}"
            full_url = urllib.parse.urljoin(self.BASE_URL, raw)
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=full_url,
                product_id=p_id,
                slug=slug,
            )

        if raw.startswith("/"):
            full_url = urllib.parse.urljoin(self.BASE_URL, raw)
            dig_m = re.search(r"(\d+)", raw)
            p_id = dig_m.group(1) if dig_m else "product"
            return ProductReference(
                vendor_id=self.VENDOR_ID,
                vendor_sku=p_id,
                pdp_url=full_url,
                product_id=p_id,
                slug="product",
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
            cur_url = getattr(driver, "current_url", "") or ""
            if not cur_url or (cur_url.rstrip("/").lower() != target_url.rstrip("/").lower()):
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

            # Check stock and add to cart button presence
            add_btn = soup.select_one(JavanSelectors.BTN_ADD_TO_CART)

            # Extract dedicated status badge/element if present
            status_el = soup.select_one(
                ".product-status, .stock-status, .availability, [class*='status'], .badge-success, .badge-danger, .badge-warning, .label-success, .label-danger, .label-warning"
            )
            raw_badge_text = status_el.get_text(strip=True) if status_el else ""

            page_text = soup.get_text(" ", strip=True)
            norm_badge = _normalize_persian_text(raw_badge_text)
            norm_page = _normalize_persian_text(page_text)
            badge_compact = re.sub(r"[\s\-_]+", "", norm_badge)
            page_compact = re.sub(r"[\s\-_]+", "", norm_page)

            # 1. Prohibited statuses (FAIL-CLOSED: BLOCK)
            # A lead time, an order/request button, or text suggesting later delivery
            # MUST NOT override any prohibited status.
            is_prohibited = False
            prohibited_reason = ""

            # Check تامین (excluding تامین کننده)
            if re.search(r"\bتامین(?!\s*کننده)\b", norm_badge) or norm_badge == "تامین":
                is_prohibited = True
                prohibited_reason = "تأمین"
            elif re.search(r"\bاتمام\b", norm_badge) or "اتمام موجودی" in norm_badge:
                is_prohibited = True
                prohibited_reason = "اتمام"
            elif "ناموجودسفارشدهید" in badge_compact or ("ناموجود" in norm_badge and ("سفارشدهید" in badge_compact or "سفارش" in norm_badge)):
                is_prohibited = True
                prohibited_reason = "ناموجود-سفارش دهید"
            elif "ناموجود" in norm_badge or "عدم موجودی" in norm_badge:
                is_prohibited = True
                prohibited_reason = "ناموجود"
            else:
                # Check within page / product container
                if re.search(r"\bتامین(?!\s*کننده)\b", norm_page):
                    is_prohibited = True
                    prohibited_reason = "تأمین"
                elif re.search(r"\bاتمام\b", norm_page) or "اتمام موجودی" in norm_page:
                    is_prohibited = True
                    prohibited_reason = "اتمام"
                elif "ناموجودسفارشدهید" in page_compact or ("ناموجود" in norm_page and ("سفارشدهید" in page_compact or "سفارش دهید" in norm_page)):
                    is_prohibited = True
                    prohibited_reason = "ناموجود-سفارش دهید"
                elif "ناموجود" in norm_page or "عدم موجودی" in norm_page:
                    is_prohibited = True
                    prohibited_reason = "ناموجود"

            # 2. Check for explicit permitted open/available status (ALLOW)
            # Must be explicitly open/available for purchase under agreed storefront semantics
            has_explicit_stock = False
            if "موجود در انبار" in norm_badge or norm_badge == "موجود":
                has_explicit_stock = True
            elif "موجود در انبار" in norm_page or re.search(r"\bوضعیت\s*[:\s]+\s*موجود\b", norm_page):
                has_explicit_stock = True
            elif "موجود" in norm_page and add_btn is not None and not is_prohibited:
                has_explicit_stock = True

            # Determine initial orderability
            if is_prohibited:
                can_order = False
                stock_qty = 0
                raw_status_text = prohibited_reason or raw_badge_text or "ناموجود"
            elif has_explicit_stock and add_btn is not None:
                can_order = True
                stock_qty = 1000
                raw_status_text = raw_badge_text or "موجود در انبار"
            else:
                # Status cannot be reliably identified -> BLOCK (Fail-Closed)
                can_order = False
                stock_qty = 0
                raw_status_text = raw_badge_text or "وضعیت نامشخص (Status Unidentified - Fail-Closed)"

            # Extract technical specifications table
            draft = self.extract_product_data(soup)

            # Extract pricing tiers table
            price_tiers = self._extract_price_tiers(soup)
            price_irr = price_tiers[0]["unit_price_irr"] if price_tiers else None
            
            if price_irr is None:
                # Find main price from text or elements
                main_pm = re.search(r"([\d,]{3,})\s*(?:ریال|تومان|IRR)", page_text)
                if main_pm:
                    val = int(main_pm.group(1).replace(",", ""))
                    if val > 100:
                        price_irr = val

            # Extract packaging step & MOQ from specs or tiers
            packaging_step = 1
            moq = 1
            if "ضریب" in draft.specs:
                sm = re.search(r"(\d+)", draft.specs["ضریب"])
                if sm:
                    packaging_step = max(int(sm.group(1)), 1)
            elif price_tiers and price_tiers[0]["min_quantity"] > 1:
                packaging_step = price_tiers[0]["min_quantity"]

            if "حداقل" in draft.specs:
                mm = re.search(r"(\d+)", draft.specs["حداقل"])
                if mm:
                    moq = max(int(mm.group(1)), 1)
            elif price_tiers and price_tiers[0]["min_quantity"] > 1:
                moq = price_tiers[0]["min_quantity"]
            else:
                moq = packaging_step

            # Fallback/Authoritative check: Extract exact constraints via shoppingCarts/create if product ID is present
            p_id_probe = product_ref.product_id or product_ref.vendor_sku
            if not p_id_probe or not str(p_id_probe).isdigit():
                m_dig = re.search(r"(\d+)", target_url)
                p_id_probe = m_dig.group(1) if m_dig else None

            if p_id_probe:
                try:
                    modal_data = driver.execute_script("""
                        var pid = arguments[0];
                        var res = null;
                        try {
                            $.ajax({
                                url: '/shoppingCarts/create',
                                data: { productId: pid },
                                async: false,
                                success: function(html) {
                                    var $h = $('<div>' + html + '</div>');
                                    var moq = parseFloat($h.find('#SaleMOQ, #SaleMOQExpositive').val());
                                    var ratio = parseFloat($h.find('#SaleRatio').val());
                                    var inv = parseFloat($h.find('#Inventory').val());
                                    var price = parseFloat($h.find('#Price').val());
                                    res = {
                                        moq: isNaN(moq) ? 1 : moq,
                                        ratio: isNaN(ratio) ? 1 : ratio,
                                        inventory: isNaN(inv) ? 1000 : inv,
                                        price: isNaN(price) ? null : price
                                    };
                                }
                            });
                        } catch(e) {}
                        return res;
                    """, p_id_probe)
                    if modal_data and isinstance(modal_data, dict):
                        packaging_step = int(modal_data.get("ratio") or packaging_step or 1)
                        moq = int(modal_data.get("moq") or moq or 1)
                        if modal_data.get("price"):
                            price_irr = int(modal_data["price"])
                        if modal_data.get("inventory") is not None:
                            modal_inv = int(modal_data["inventory"])
                            if modal_inv <= 0:
                                stock_qty = 0
                                can_order = False
                                raw_status_text = "اتمام موجودی (Modal Inventory: 0)"
                            elif can_order:
                                stock_qty = modal_inv
                except Exception:
                    pass

            # Resolve MPN
            mpn = draft.mpn
            if not mpn:
                if "نام قطعه" in draft.specs:
                    mpn = draft.specs["نام قطعه"]
                elif "|" in raw_title:
                    mpn = raw_title.split("|")[0].strip()
                elif product_ref.slug and product_ref.slug != "part":
                    mpn = product_ref.slug
                else:
                    mpn = product_ref.vendor_sku

            # Resolve Manufacturer
            mfr = draft.manufacturer
            if not mfr and "|" in raw_title:
                mfr = raw_title.split("|")[1].strip()

            raw_data = {"price_tiers": price_tiers}

            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=target_url,
                stock_quantity=stock_qty,
                can_order=can_order,
                is_inquiry_only=False,
                raw_status_text=raw_status_text,
                price_irr=price_irr,
                mpn=mpn,
                manufacturer=mfr,
                package_raw=draft.package,
                order_constraints=OrderConstraints(
                    packaging_step_raw=packaging_step,
                    moq_raw=moq,
                ),
                raw_data=raw_data,
            )

        except Exception as e:
            if isinstance(e, OmnixVendorError):
                raise
            raise JavanErrorTranslator.translate_transport_exception(e, {"url": target_url, "operation": "inspect_product"})

    def _extract_price_tiers(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extract tiered pricing brackets from Javan PDP tables or lists.
        Rows match patterns like: '10 عدد' -> '18,400 ریال' or '+ 400 عدد 18,000 ریال'
        """
        tiers: List[Dict[str, Any]] = []
        rows = soup.select("table tr, div[class*='price'], ul li, tr")

        for row in rows:
            text = row.get_text(" ", strip=True)
            tds = row.find_all(["td", "th", "div", "span"])
            if len(tds) >= 2:
                col1 = tds[0].get_text(strip=True)
                col2 = tds[1].get_text(strip=True)
                
                qm = re.search(r"([\d,]+)\s*عدد", col1)
                pm = re.search(r"([\d,]{3,})", col2)
                if qm and pm:
                    qty = int(qm.group(1).replace(",", ""))
                    price = int(pm.group(1).replace(",", ""))
                    if price > 100:
                        tiers.append({"min_quantity": qty, "unit_price_irr": price})
            else:
                qm = re.search(r"\+?\s*([\d,]+)\s*عدد", text)
                pm = re.search(r"([\d,]{3,})\s*(?:ریال|تومان|IRR)?", text)
                if qm and pm:
                    try:
                        qty = int(qm.group(1).replace(",", ""))
                        price = int(pm.group(1).replace(",", ""))
                        if price > 100:
                            tiers.append({"min_quantity": qty, "unit_price_irr": price})
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
        Extract technical specs ('نام کارخانه‌ای', 'نام قطعه', 'برند', 'پکیج', etc.) from BeautifulSoup or HTML.
        """
        if isinstance(dom_context, str):
            soup = BeautifulSoup(dom_context, "html.parser")
        elif hasattr(dom_context, "find_all"):
            soup = dom_context
        else:
            soup = BeautifulSoup(str(dom_context), "html.parser")

        mpn = None
        manufacturer = None
        package = None
        specs: Dict[str, str] = {}

        # 1. Check specification table rows
        rows = soup.select("table tr, .spec-row, dl dt")
        for r in rows:
            tds = r.find_all(["td", "th", "dd"])
            if len(tds) >= 2:
                key = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                if key and val and key != "Features" and key != "انتخاب ویژگی":
                    specs[key] = val
                    k_lower = key.lower()
                    if "نام کارخانه‌ای" in key or "شماره فنی" in key or "پارت نامبر" in key or "part number" in k_lower or "mpn" in k_lower:
                        mpn = val
                    elif not mpn and ("نام قطعه" in key or "part name" in k_lower):
                        mpn = val
                    elif "برند" in key or "سازنده" in key or "تولید کننده" in key or "تولیدکننده" in key or "brand" in k_lower or "manufacturer" in k_lower:
                        manufacturer = val
                    elif "پکیج" in key or "package" in k_lower or "case" in k_lower or "footprint" in k_lower:
                        package = val

        # 2. Check full text lines (e.g. نام کارخانه‌ای: 1206B104K500CT, برند: Walsin)
        full_text = soup.get_text("\n", strip=True)
        for line in full_text.splitlines():
            line_clean = line.strip(" •-\t\r")
            if not mpn:
                m_mpn = re.search(r"^(?:نام\s*کارخانه‌ای|شماره\s*فنی|پارت\s*نامبر|Part\s*Number|MPN)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\+\/]+)", line_clean, re.IGNORECASE)
                if m_mpn:
                    mpn = m_mpn.group(1).strip()
            if not manufacturer:
                m_mfg = re.search(r"^(?:برند|سازنده|تولید\s*کننده|Brand|Manufacturer)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\s]+)", line_clean, re.IGNORECASE)
                if m_mfg:
                    manufacturer = m_mfg.group(1).strip()
            if not package:
                m_pkg = re.search(r"^(?:پکیج|Package|سایز|Footprint)\s*[:\s•-]+\s*([a-zA-Z0-9_.\-\s]+)", line_clean, re.IGNORECASE)
                if m_pkg:
                    package = m_pkg.group(1).strip()
            if "حداقل" not in specs:
                m_min = re.search(r"^حداقل\s*[:\s•-]+\s*(\d+)", line_clean)
                if m_min:
                    specs["حداقل"] = m_min.group(1)
            if "ضریب" not in specs:
                m_step = re.search(r"^ضریب\s*[:\s•-]+\s*(\d+)", line_clean)
                if m_step:
                    specs["ضریب"] = m_step.group(1)

        # 3. Fallback to PDP title / H1 if MPN is not in specs table or text
        if not mpn:
            title_el = soup.select_one(JavanSelectors.PDP_TITLE)
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
        Inspect live stock availability on Javan Electronic.
        """
        details = self.inspect_product(product_ref)
        raw_text = details.raw_status_text

        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.can_order and details.stock_quantity > 0,
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
        Internal Browser AJAX / Modal cart mutation on Javan Electronic:
        1. Auto-authenticate if not already logged in.
        2. Resolve effective quantity respecting MOQ and packaging step.
        3. Trigger Javan addToCart modal dialog.
        4. Populate quantity and instant quantity, confirm modal form.
        5. Intercept and translate any validation error alert.
        """
        if quantity <= 0:
            raise OrderMultipleViolationError(f"Quantity must be greater than 0 (got {quantity})", vendor_id=self.VENDOR_ID)

        driver = self.session.get_driver()
        target_url = product_ref.pdp_url

        try:
            # 1. Ensure session is authenticated (reuse valid session when available)
            try:
                status = self.validate_session()
            except Exception:
                status = SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=False)

            if not status.is_authenticated:
                # User-initiated cart addition authorizes login with configured credentials
                from settings_manager import settings
                v_cfg = settings.get_vendor_settings(self.VENDOR_ID) if hasattr(settings, "get_vendor_settings") else None
                u = (v_cfg.username if v_cfg else "") or settings.get("javan_username", "").strip()
                p = (v_cfg.password if v_cfg else "") or settings.get("javan_password", "").strip()

                if not u or not p:
                    raise AuthenticationRequiredError(
                        "Javan Electronic credentials (Username & Password) are not configured.",
                        vendor_id=self.VENDOR_ID,
                    )

                auth_res = self.authenticate(credentials=AuthCredentials(username=u, password=p))
                if not auth_res or not auth_res.success:
                    err_msg = auth_res.message if auth_res else "Authentication failed"
                    if auth_res and getattr(auth_res, "requires_interactive", False):
                        from core.errors import SecurityChallengeError
                        raise SecurityChallengeError(
                            f"Javan Electronic security challenge encountered: {err_msg}",
                            vendor_id=self.VENDOR_ID,
                        )
                    raise AuthenticationRequiredError(
                        f"Javan Electronic authentication failed: {err_msg}",
                        vendor_id=self.VENDOR_ID,
                    )

            # 2. Ensure we are on the PDP or base page
            cur_url = getattr(driver, "current_url", "") or ""
            if not cur_url or ("javanelec.com" not in cur_url):
                driver.get(target_url)
                self.session.wait_for_settle(2.0)

            # 3. Check if purchasable and resolve constraints
            details = self.inspect_product(product_ref)
            if not details.can_order:
                raise OutOfStockError(f"Javan product cannot be ordered (Status: {details.raw_status_text})", vendor_id=self.VENDOR_ID)

            # 4. Resolve effective quantity based on constraints
            step = details.order_constraints.packaging_step_raw or 1
            moq = details.order_constraints.moq_raw or 1
            eff_qty = max(quantity, moq)
            if step > 1:
                rem = (eff_qty - moq) % step
                if rem != 0:
                    eff_qty += (step - rem)

            # 5. Extract numeric product ID
            p_id = product_ref.product_id or product_ref.vendor_sku
            if not p_id or not str(p_id).isdigit():
                m_dig = re.search(r"(\d+)", target_url)
                p_id = m_dig.group(1) if m_dig else "0"

            # 6. Execute modal trigger and quantity confirmation via JS
            js_mutation = f"""
                var reqQty = parseInt("{quantity}");
                var pid = parseInt("{p_id}");
                window._javanLastStagedQty = reqQty;
                
                // Trigger addToCart
                if (typeof addToCart === 'function' && !isNaN(pid) && pid > 0) {{
                    addToCart(null, pid);
                }} else {{
                    var btn = document.querySelector('.prd_dtl_add_cart_btn button, button.btn-success-outline, button[onclick*="addToCart"]');
                    if (btn) btn.click();
                }}
                
                // Poll for modal and submit quantity
                var start = Date.now();
                var timer = setInterval(function() {{
                    var form = document.querySelector('#CreateShoppingCarts, .bootbox.modal form');
                    if (form) {{
                        clearInterval(timer);

                        var moqEl = form.querySelector('#SaleMOQ, #SaleMOQExpositive');
                        var ratioEl = form.querySelector('#SaleRatio');
                        var moq = moqEl ? parseFloat(moqEl.value) : 1;
                        var ratio = ratioEl ? parseFloat(ratioEl.value) : 1;
                        if (isNaN(moq) || moq < 1) moq = 1;
                        if (isNaN(ratio) || ratio < 1) ratio = 1;

                        var eff = Math.max(reqQty, moq);
                        if (ratio > 1) {{
                            var rem = (eff - moq) % ratio;
                            if (rem !== 0) {{
                                eff += (ratio - rem);
                            }}
                        }}

                        window._javanLastStagedQty = eff;

                        var qInp = form.querySelector('#Quantity');
                        if (qInp) {{
                            qInp.value = eff.toString();
                            if (typeof addShpCart === 'function') {{
                                addShpCart();
                            }} else if (window.jQuery) {{
                                $(qInp).val(eff.toString()).trigger('input').trigger('change').trigger('keyup');
                            }}
                        }}

                        setTimeout(function() {{
                            var modal = form.closest('.modal, .bootbox');
                            var cBtn = modal ? modal.querySelector('button[data-bb-handler="confirm"], button.btn-success') : null;
                            if (cBtn) {{
                                cBtn.click();
                            }} else if (window.jQuery) {{
                                $(form).submit();
                            }}
                        }}, 250);
                    }}
                    if (Date.now() - start > 5000) {{
                        clearInterval(timer);
                    }}
                }}, 200);
                return true;
            """
            self.session.execute_script(js_mutation)

            # Enforce settle window
            self.session.wait_for_settle(3.0)

            # Get final staged quantity computed by modal
            actual_staged_qty = self.session.execute_script("return window._javanLastStagedQty || arguments[0];", eff_qty)

            # Fallback direct modal confirm from Python side if modal is still open
            try:
                modals = driver.find_elements(By.CSS_SELECTOR, "#CreateShoppingCarts, .bootbox.modal, #adcrt")
                for m in modals:
                    if m.is_displayed():
                        q_inp = m.find_element(By.CSS_SELECTOR, "#Quantity")
                        driver.execute_script("arguments[0].value = arguments[1]; if (typeof addShpCart === 'function') addShpCart();", q_inp, str(actual_staged_qty))
                        time.sleep(0.3)
                        c_btns = m.find_elements(By.CSS_SELECTOR, "button[data-bb-handler='confirm'], button.btn-success")
                        for cb in c_btns:
                            if cb.is_displayed():
                                driver.execute_script("arguments[0].click();", cb)
                                self.session.wait_for_settle(2.0)
            except Exception:
                pass

            # Check for error alerts
            err_popups = driver.find_elements(By.CSS_SELECTOR, ".alert-danger, .validation-summary-errors, .toast-error, .bootbox-alert")
            for ep in err_popups:
                ep_text = ep.text.strip()
                if ep_text and any(kw in ep_text for kw in ["ضریب", "موجودی", "خطا", "امکان", "ناموفق", "مضرب", "بسته", "حداقل"]):
                    self.session.dismiss_active_modal()
                    err = JavanErrorTranslator.translate_modal_message(ep_text, {"requested_qty": eff_qty, "product_sku": product_ref.vendor_sku})
                    raise err

            try:
                final_qty = int(actual_staged_qty)
            except (ValueError, TypeError):
                final_qty = eff_qty

            if final_qty <= 0:
                raise OmnixVendorError("Javan cart staging did not confirm any quantity.", vendor_id=self.VENDOR_ID)

            return CartMutationResult(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=final_qty,
                success=True,
                error_category=None,
                raw_vendor_message=f"Added {final_qty} units to Javan shopping cart",
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
            
            cart_items: List[CartItem] = []
            
            # 1. Parse .basket-item / .cart-item containers
            basket_items = soup.select(".basket-item, .cart-item, [class*='basket-item']")
            for b in basket_items:
                title_el = b.select_one(".product-title, h4, h5, .title, strong") or b
                name = title_el.get_text(" ", strip=True) if title_el else ""
                
                # Qty input
                qty = 1
                qty_inp = b.select_one("input.card-dtl-qty-input, input[name*='Quantity'], input[id*='Quantity']")
                if qty_inp and qty_inp.get("value"):
                    qm = re.search(r"(\d+)", qty_inp.get("value", "1").replace(",", ""))
                    if qm:
                        qty = int(qm.group(1))

                # Unit price
                u_price = None
                p_text = b.get_text(" ", strip=True)
                pm = re.search(r"([\d,]{3,})\s*\|\s*قیمت واحد", p_text)
                if pm:
                    u_price = int(pm.group(1).replace(",", ""))

                if name:
                    cart_items.append(
                        CartItem(
                            vendor_sku=name,
                            product_name=name,
                            quantity=qty,
                            unit_price_irr=u_price,
                        )
                    )

            # 2. Fallback to table rows if no basket items found
            if not cart_items:
                rows = soup.select(JavanSelectors.CART_ITEM_ROWS)
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
                message="Javan authentication credentials not provided.",
            )

        driver = self.session.get_driver()

        try:
            driver.get(JavanSelectors.LOGIN_URL)
            self.session.wait_for_settle(1.5)

            # Upfront challenge detection (Turnstile, reCAPTCHA, WAF, OTP)
            challenge_type = self._detect_challenge_on_page(driver)
            if challenge_type is not None:
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=challenge_type,
                    prompt_message=f"Javan Electronic requires security challenge resolution ({challenge_type.value}).",
                    target_url=driver.current_url or JavanSelectors.LOGIN_URL,
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

            # Check for image CAPTCHA input if present on form
            captcha_input_els = driver.find_elements(By.CSS_SELECTOR, "input[name*='captcha'], input[id*='captcha'], #captcha-input")
            captcha_img_els = driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha-img, #captcha-image")
            if captcha_input_els and captcha_img_els:
                img_src = captcha_img_els[0].get_attribute("src") or ""
                ctx = ChallengeContext(
                    vendor_id=self.VENDOR_ID,
                    challenge_type=ChallengeType.IMAGE_CAPTCHA,
                    prompt_message="Please enter the characters shown in the CAPTCHA image.",
                    target_url=driver.current_url or JavanSelectors.LOGIN_URL,
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
            submit_btn = driver.find_element(By.CSS_SELECTOR, JavanSelectors.LOGIN_SUBMIT_BTN)
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
                    prompt_message=f"Javan Electronic presented a post-login challenge ({post_challenge.value}).",
                    target_url=driver.current_url or JavanSelectors.LOGIN_URL,
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
            err_els = driver.find_elements(By.CSS_SELECTOR, ".validation-summary-errors, .alert-danger, .field-validation-error")
            for el in err_els:
                txt = el.text.strip()
                if txt:
                    return AuthResult(vendor_id=self.VENDOR_ID, success=False, message=f"Login failed: {txt}")

            return AuthResult(vendor_id=self.VENDOR_ID, success=False, message="Login verification failed.")

        except Exception as e:
            err = JavanErrorTranslator.translate_transport_exception(e, {"operation": "authenticate"})
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

    def get_cart_url(self) -> Optional[str]:
        """Return the storefront cart URL for Javan Electronic."""
        return JavanSelectors.CART_URL

    def is_pdp_url(self, url: str) -> bool:
        """Check whether the given URL matches a Javan Electronic Product Detail Page (PDP)."""
        clean = (url or "").strip()
        if not clean:
            return False
        return bool(JavanSelectors.PDP_URL_PATTERN.match(clean) or JavanSelectors.PDP_PATH_PATTERN.match(clean))

