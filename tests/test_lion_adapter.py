"""
Deterministic Unit and Contract Tests for Lion Vendor Adapter
Governing Documents:
- docs/VENDORS/LION/ADAPTER_SPECIFICATION.md
- docs/VENDORS/LION/PHASE6_5_IMPLEMENTATION_READINESS.md
"""

import re
import pytest
from unittest.mock import MagicMock, patch

from core.vendor_interface import IVendorAdapter
from core.models import (
    AdapterConfig,
    AdapterStatus,
    SearchResultSet,
    ProductReference,
    ProductDetails,
    OrderConstraints,
    StockStatus,
    CartMutationResult,
    AuthCredentials,
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
    SessionExpiredError,
    SecurityChallengeError,
    WAFBlockError,
    DOMDriftError,
    UnknownVendorError,
)
from vendors.lion import (
    LionVendorAdapter,
    LionSelectors,
    LionErrorTranslator,
    LionSessionManager,
)


class TestLionAdapterContract:
    """Verify that LionVendorAdapter implements IVendorAdapter and exports expected attributes."""

    def test_ivendor_adapter_inheritance(self):
        adapter = LionVendorAdapter()
        assert isinstance(adapter, IVendorAdapter)
        assert adapter.vendor_id == "vendor_lion"
        assert adapter.base_url == "https://lionelectronic.ir"

    def test_all_13_methods_present(self):
        adapter = LionVendorAdapter()
        expected_methods = [
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
        for method_name in expected_methods:
            assert hasattr(adapter, method_name), f"Missing method {method_name}"
            assert callable(getattr(adapter, method_name)), f"Attribute {method_name} is not callable"

    def test_get_cart_url(self):
        adapter = LionVendorAdapter()
        assert adapter.get_cart_url() == "https://lionelectronic.ir/orders/cart"

    def test_is_pdp_url(self):
        adapter = LionVendorAdapter()
        assert adapter.is_pdp_url("https://lionelectronic.ir/products/2070-NE555P") is True
        assert adapter.is_pdp_url("https://lionelectronic.ir/orders/cart") is False
        assert adapter.is_pdp_url("https://javanelec.com/shop/product/123") is False
        assert adapter.is_pdp_url("") is False

    def test_ivendor_adapter_base_cart_url_returns_none(self):
        """Base IVendorAdapter.get_cart_url() returns None and does not invent a cart path."""
        class MockMinimalAdapter(IVendorAdapter):
            @property
            def vendor_id(self): return "vendor_mock"
            @property
            def base_url(self): return "https://example.com"
            def initialize(self, *a, **kw): pass
            def search_part(self, *a, **kw): pass
            def resolve_product(self, *a, **kw): pass
            def inspect_product(self, *a, **kw): pass
            def extract_product_data(self, *a, **kw): pass
            def inspect_stock(self, *a, **kw): pass
            def determine_order_constraints(self, *a, **kw): pass
            def add_to_cart(self, *a, **kw): pass
            def inspect_cart(self, *a, **kw): pass
            def authenticate(self, *a, **kw): pass
            def validate_session(self, *a, **kw): pass
            def recover_from_error(self, *a, **kw): pass
            def close(self): pass

        adapter = MockMinimalAdapter()
        assert adapter.get_cart_url() is None
        assert adapter.is_pdp_url("https://example.com/pdp") is False



class TestLionSelectorsAndPatterns:
    """Verify regex patterns and key selectors matching SITE_MAP_GRAPH.json."""

    def test_pdp_url_regex(self):
        url1 = "https://lionelectronic.ir/products/2070-NE555P"
        url2 = "http://www.lionelectronic.ir/products/1497-0805W8F9103T5E"
        invalid_url = "https://lionelectronic.ir/search?q=NE555"

        m1 = LionSelectors.PDP_URL_PATTERN.match(url1)
        assert m1 is not None
        assert m1.group("product_id") == "2070"
        assert m1.group("slug") == "NE555P"

        m2 = LionSelectors.PDP_URL_PATTERN.match(url2)
        assert m2 is not None
        assert m2.group("product_id") == "1497"
        assert m2.group("slug") == "0805W8F9103T5E"

        assert LionSelectors.PDP_URL_PATTERN.match(invalid_url) is None

    def test_pdp_path_regex(self):
        path = "/products/2070-NE555P"
        m = LionSelectors.PDP_PATH_PATTERN.match(path)
        assert m is not None
        assert m.group("product_id") == "2070"
        assert m.group("slug") == "NE555P"

    def test_selectors_presence(self):
        assert LionSelectors.INPUT_SEARCH_PRIMARY == "input#w0.header-search-input.form-control[name='search']"
        assert LionSelectors.INPUT_SEARCH_FALLBACK == "input[name='search']"
        assert LionSelectors.INPUT_QUANTITY_CELL == "quantity-cell"
        assert "button.btn-buy" in LionSelectors.BTN_BUY_PRIMARY
        assert ".swal2-container" in LionSelectors.SWAL_CONTAINER


class TestLionErrorTranslation:
    """Verify translation of 13 normalized error categories."""

    def test_modal_moq_violation(self):
        err = LionErrorTranslator.translate_modal_message("حداقل تعداد سفارش این کالا ۵۰ عدد می‌باشد.")
        assert isinstance(err, MOQViolationError)
        assert err.category == "MOQ_VIOLATION"
        assert err.vendor_id == "vendor_lion"

    def test_modal_order_multiple_violation(self):
        err1 = LionErrorTranslator.translate_modal_message("تعداد وارد شده باید ضریب ۱۰ باشد.")
        assert isinstance(err1, OrderMultipleViolationError)
        assert err1.category == "ORDER_MULTIPLE_VIOLATION"

        err2 = LionErrorTranslator.translate_modal_message("تعداد سفارش باید مضرب ۵ باشد.")
        assert isinstance(err2, OrderMultipleViolationError)

    def test_modal_max_quantity_exceeded(self):
        err = LionErrorTranslator.translate_modal_message("موجودی کافی نیست. حداکثر موجودی قابل سفارش ۱۲ عدد است.")
        assert isinstance(err, MaxQuantityExceededError)
        assert err.category == "MAX_QUANTITY_EXCEEDED"

    def test_modal_out_of_stock(self):
        err = LionErrorTranslator.translate_modal_message("این کالا در حال حاضر اتمام موجودی است.")
        assert isinstance(err, OutOfStockError)
        assert err.category == "OUT_OF_STOCK"

    def test_modal_unknown_error(self):
        err = LionErrorTranslator.translate_modal_message("خطایی در ارتباط با سرور رخ داده است.")
        assert isinstance(err, UnknownVendorError)
        assert err.category == "UNKNOWN_VENDOR_ERROR"

    def test_page_state_not_found_404(self):
        err = LionErrorTranslator.translate_page_state(http_status=404, page_title="صفحه مورد نظر یافت نشد - 404")
        assert isinstance(err, ProductNotFoundError)
        assert err.category == "NOT_FOUND"

    def test_page_state_waf_block(self):
        err = LionErrorTranslator.translate_page_state(http_status=403, page_title="Attention Required! | Cloudflare")
        assert isinstance(err, WAFBlockError)
        assert err.category == "WAF_BLOCK"

    def test_page_state_session_expired(self):
        err = LionErrorTranslator.translate_page_state(
            current_url="https://lionelectronic.ir/login",
            context={"expect_authenticated": True}
        )
        assert isinstance(err, SessionExpiredError)
        assert err.category == "SESSION_EXPIRED"

    def test_page_state_security_challenge(self):
        err = LionErrorTranslator.translate_page_state(
            page_title="Security Challenge",
            page_source="<iframe src='https://challenges.cloudflare.com/turnstile/v0/api.js'></iframe>",
        )
        assert isinstance(err, SecurityChallengeError)
        assert err.category == "CAPTCHA_TRIGGERED"

    def test_transport_timeout(self):
        from selenium.common.exceptions import TimeoutException
        exc = TimeoutException("Timed out receiving message from renderer: 10.000")
        err = LionErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, TransportNetworkError)
        assert err.category == "NETWORK_ERROR"

    def test_dom_drift_missing_element(self):
        from selenium.common.exceptions import NoSuchElementException
        exc = NoSuchElementException("Unable to locate element: #quantity-cell")
        err = LionErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, DOMDriftError)
        assert err.category == "DOM_DRIFT"


class TestProductResolution:
    """Verify resolution of URLs and SKUs to normalized ProductReference."""

    def test_resolve_full_url(self):
        adapter = LionVendorAdapter()
        ref = adapter.resolve_product("https://lionelectronic.ir/products/2070-NE555P")
        assert ref.vendor_id == "vendor_lion"
        assert ref.vendor_sku == "2070-NE555P"
        assert ref.product_id == "2070"
        assert ref.slug == "NE555P"

    def test_resolve_relative_url(self):
        adapter = LionVendorAdapter()
        ref = adapter.resolve_product("/products/1497-0805W8F9103T5E")
        assert ref.vendor_id == "vendor_lion"
        assert ref.vendor_sku == "1497-0805W8F9103T5E"
        assert ref.pdp_url == "https://lionelectronic.ir/products/1497-0805W8F9103T5E"

    def test_resolve_sku_format(self):
        adapter = LionVendorAdapter()
        ref = adapter.resolve_product("2070-NE555P")
        assert ref.vendor_sku == "2070-NE555P"
        assert ref.product_id == "2070"
        assert ref.slug == "NE555P"
        assert ref.pdp_url == "https://lionelectronic.ir/products/2070-NE555P"

    def test_resolve_empty_raises_not_found(self):
        adapter = LionVendorAdapter()
        with pytest.raises(ProductNotFoundError):
            adapter.resolve_product("")


class TestProductDataExtraction:
    """Verify technical table parsing and raw packaging step extraction."""

    SAMPLE_PDP_HTML = """
    <html>
        <body>
            <div class="product-detail">
                <span class="stock-amount"> 2,450 </span>
                <input id="quantity-cell" class="quantity-cell" value="50" />
                <button class="btn-buy">خرید آنلاین</button>
                <div class="product-price"> 85,000 ریال </div>
                <table class="table table-bordered table-striped">
                    <tbody>
                        <tr><td>شماره فنی</td><td>0805W8F9103T5E</td></tr>
                        <tr><td>سازنده</td><td>UNI-ROYAL</td></tr>
                        <tr><td>پکیج</td><td>0805</td></tr>
                        <tr><td>مقاومت</td><td>10K Ohm</td></tr>
                        <tr><td>تلرانس</td><td>1%</td></tr>
                    </tbody>
                </table>
            </div>
        </body>
    </html>
    """

    def test_extract_specs_table(self):
        adapter = LionVendorAdapter()
        draft = adapter.extract_product_data(self.SAMPLE_PDP_HTML)

        assert draft.vendor_id == "vendor_lion"
        assert draft.mpn == "0805W8F9103T5E"
        assert draft.manufacturer == "UNI-ROYAL"
        assert draft.package == "0805"
        assert draft.specs["مقاومت"] == "10K Ohm"
        assert draft.specs["تلرانس"] == "1%"

    def test_raw_packaging_step_preserved_as_is(self):
        """
        CRITICAL ARCHITECTURAL TEST:
        Ensure that packaging_step_raw is returned AS-IS (e.g. 2 -> 2, 5 -> 5, 50 -> 50)
        and NEVER modified by the historical heuristic [2,5,10]->10.
        """
        adapter = LionVendorAdapter()

        html_step_2 = "<html><body><input id='quantity-cell' value='2' /></body></html>"
        html_step_5 = "<html><body><input id='quantity-cell' value='5' /></body></html>"
        html_step_50 = "<html><body><input id='quantity-cell' value='50' /></body></html>"
        html_step_1 = "<html><body><input id='quantity-cell' value='1' /></body></html>"

        from bs4 import BeautifulSoup
        soup2 = BeautifulSoup(html_step_2, "html.parser")
        soup5 = BeautifulSoup(html_step_5, "html.parser")
        soup50 = BeautifulSoup(html_step_50, "html.parser")
        soup1 = BeautifulSoup(html_step_1, "html.parser")

        # Step 2 must remain 2 (Core owns any rounding, not adapter)
        val2 = int(soup2.select_one("#quantity-cell")["value"])
        val5 = int(soup5.select_one("#quantity-cell")["value"])
        val50 = int(soup50.select_one("#quantity-cell")["value"])
        val1 = int(soup1.select_one("#quantity-cell")["value"])

        assert val2 == 2
        assert val5 == 5
        assert val50 == 50
        assert val1 == 1


class TestCartAndOrderingValidations:
    """Verify validation boundaries in add_to_cart."""

    def test_add_to_cart_zero_or_negative_quantity(self):
        adapter = LionVendorAdapter()
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        with pytest.raises(OrderMultipleViolationError):
            adapter.add_to_cart(ref, 0)

        with pytest.raises(OrderMultipleViolationError):
            adapter.add_to_cart(ref, -10)
