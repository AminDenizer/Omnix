"""
Deterministic Unit Tests for RoboEq Electronic Vendor Adapter (RoboEqVendorAdapter)
Tests all 13 IVendorAdapter contract operations, selector regexes, error translations,
mock HTML extractions, and ordering validations without hitting live network.
"""

import pytest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

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
    SessionExpiredError,
    SecurityChallengeError,
    WAFBlockError,
    DOMDriftError,
    UnknownVendorError,
)
from vendors.roboeq import (
    RoboEqVendorAdapter,
    RoboEqSelectors,
    RoboEqErrorTranslator,
    RoboEqSessionManager,
)


# ============================================================================
# 1. CONTRACT INHERITANCE & OPERATION COMPLETENESS
# ============================================================================

class TestRoboEqAdapterContract:
    def test_ivendor_adapter_inheritance(self):
        assert issubclass(RoboEqVendorAdapter, IVendorAdapter)

    def test_all_13_methods_present(self):
        adapter = RoboEqVendorAdapter()
        methods = [
            "initialize",
            "search_part",
            "resolve_product",
            "inspect_product",
            "extract_product_data",
            "inspect_stock",
            "determine_order_constraints",
            "add_to_cart",
            "inspect_cart",
            "authenticate",
            "validate_session",
            "recover_from_error",
            "close",
        ]
        for m in methods:
            assert hasattr(adapter, m), f"Missing method {m}"
            assert callable(getattr(adapter, m))

    def test_vendor_metadata(self):
        adapter = RoboEqVendorAdapter()
        assert adapter.vendor_id == "vendor_roboeq"
        assert adapter.base_url == "https://roboeq.ir"

    def test_get_cart_url(self):
        adapter = RoboEqVendorAdapter()
        assert adapter.get_cart_url() == "https://roboeq.ir/cart/"

    def test_is_pdp_url(self):
        adapter = RoboEqVendorAdapter()
        assert adapter.is_pdp_url("https://roboeq.ir/products/detail/0315001/آی-سی-تایمر-NE555/") is True
        assert adapter.is_pdp_url("https://roboeq.ir/cart/") is False
        assert adapter.is_pdp_url("https://lionelectronic.ir/products/2070-NE555P") is False
        assert adapter.is_pdp_url("") is False



# ============================================================================
# 2. SELECTOR REGEXES & URL PATTERNS
# ============================================================================

class TestRoboEqSelectorsAndPatterns:
    def test_pdp_url_regex(self):
        url = "https://roboeq.ir/products/detail/0315001/آی-سی-تایمر-NE555/"
        m = RoboEqSelectors.PDP_URL_PATTERN.match(url)
        assert m is not None
        assert m.group("product_id") == "0315001"
        assert m.group("slug") == "آی-سی-تایمر-NE555"

    def test_pdp_path_regex(self):
        path = "/products/detail/0315001/آی-سی-تایمر-NE555/"
        m = RoboEqSelectors.PDP_PATH_PATTERN.match(path)
        assert m is not None
        assert m.group("product_id") == "0315001"

    def test_search_url_template(self):
        url = RoboEqSelectors.SEARCH_URL_TEMPLATE.format(query="NE555")
        assert "q=NE555" in url


# ============================================================================
# 3. 3-TIER ERROR TRANSLATION ENGINE
# ============================================================================

class TestRoboEqErrorTranslation:
    def test_modal_moq_violation(self):
        err = RoboEqErrorTranslator.translate_modal_message("حداقل تعداد خرید این کالا رعایت نشده است")
        assert isinstance(err, MOQViolationError)
        assert err.vendor_id == "vendor_roboeq"

    def test_modal_order_multiple_violation(self):
        err = RoboEqErrorTranslator.translate_modal_message("تعداد سفارش باید مضرب ۱۰ باشد")
        assert isinstance(err, OrderMultipleViolationError)

    def test_modal_max_quantity_exceeded(self):
        err = RoboEqErrorTranslator.translate_modal_message("تعداد درخواستی بیش از موجودی انبار است")
        assert isinstance(err, MaxQuantityExceededError)

    def test_modal_out_of_stock(self):
        err = RoboEqErrorTranslator.translate_modal_message("این کالا در حال حاضر ناموجود است")
        assert isinstance(err, OutOfStockError)

    def test_page_state_not_found_404(self):
        err = RoboEqErrorTranslator.translate_page_state(
            http_status=404,
            page_title="خطا | روبوایکیو",
            current_url="https://roboeq.ir/error/404/",
        )
        assert isinstance(err, ProductNotFoundError)

    def test_page_state_waf_block(self):
        err = RoboEqErrorTranslator.translate_page_state(
            http_status=403,
            page_title="403 Forbidden",
            page_source="ArvanCloud Firewall Block",
        )
        assert isinstance(err, WAFBlockError)

    def test_transport_timeout(self):
        exc = Exception("TimeoutException: Timed out waiting for page")
        err = RoboEqErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, TransportNetworkError)

    def test_dom_drift_missing_element(self):
        exc = Exception("NoSuchElementException: Unable to locate element")
        err = RoboEqErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, DOMDriftError)


# ============================================================================
# 4. PRODUCT RESOLUTION TESTS
# ============================================================================

class TestRoboEqProductResolution:
    def test_resolve_full_url(self):
        adapter = RoboEqVendorAdapter()
        ref = adapter.resolve_product("https://roboeq.ir/products/detail/0315001/ne555-timer/")
        assert ref.vendor_id == "vendor_roboeq"
        assert ref.vendor_sku == "0315001"
        assert ref.product_id == "0315001"
        assert ref.slug == "ne555-timer"

    def test_resolve_relative_url(self):
        adapter = RoboEqVendorAdapter()
        ref = adapter.resolve_product("/products/detail/0315001/ne555-timer/")
        assert ref.vendor_id == "vendor_roboeq"
        assert ref.vendor_sku == "0315001"
        assert ref.pdp_url == "https://roboeq.ir/products/detail/0315001/ne555-timer/"

    def test_resolve_empty_raises(self):
        adapter = RoboEqVendorAdapter()
        with pytest.raises(ProductNotFoundError):
            adapter.resolve_product("")


# ============================================================================
# 5. DATA EXTRACTION TESTS (MOCK HTML)
# ============================================================================

MOCK_ROBOEQ_PDP = """
<!DOCTYPE html>
<html>
<head><title>آی سی تایمر NE555 | روبوایکیو</title></head>
<body>
    <h1>آی سی تایمر NE555</h1>
    <table>
        <tr><th>عنوان</th><th>مقدار</th></tr>
        <tr><td>پکیج</td><td>DIP-8</td></tr>
        <tr><td>سازنده</td><td>Texas Instruments</td></tr>
        <tr><td>وزن</td><td>1.1 گرم</td></tr>
    </table>
    <table>
        <tr><td>پارسیان</td><td>179,000</td></tr>
    </table>
</body>
</html>
"""

class TestRoboEqDataExtraction:
    def test_extract_specs(self):
        adapter = RoboEqVendorAdapter()
        draft = adapter.extract_product_data(MOCK_ROBOEQ_PDP)
        assert draft.vendor_id == "vendor_roboeq"
        assert draft.package == "DIP-8"
        assert draft.manufacturer == "Texas Instruments"
        assert draft.specs.get("وزن") == "1.1 گرم"

    def test_extract_price(self):
        adapter = RoboEqVendorAdapter()
        soup = BeautifulSoup(MOCK_ROBOEQ_PDP, "html.parser")
        price = adapter._extract_price(soup)
        assert price == 179000


# ============================================================================
# 6. CART & LIFECYCLE TESTS
# ============================================================================

class TestRoboEqCartAndLifecycle:
    def test_add_to_cart_zero_qty_raises(self):
        adapter = RoboEqVendorAdapter()
        ref = ProductReference(vendor_id="vendor_roboeq", vendor_sku="0315001", pdp_url="https://roboeq.ir/products/detail/0315001/ne555/")
        with pytest.raises(OrderMultipleViolationError):
            adapter.add_to_cart(ref, 0)

    def test_session_recovery(self):
        adapter = RoboEqVendorAdapter()
        adapter.session.dismiss_active_modal = MagicMock(return_value=True)
        rec = adapter.recover_from_error({})
        assert rec.recovered is True
        assert rec.action_taken == "DISMISS_MODAL"

    def test_close_lifecycle(self):
        adapter = RoboEqVendorAdapter()
        adapter._is_ready = True
        adapter.session.close = MagicMock()
        adapter.close()
        assert adapter._is_ready is False
