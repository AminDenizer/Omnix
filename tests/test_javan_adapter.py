"""
Deterministic Unit Tests for Javan Electronic Vendor Adapter (JavanVendorAdapter)
Tests all 13 IVendorAdapter contract operations, selector regexes, error translations,
mock HTML extractions, and ordering validations without hitting live network.
"""

import pytest
from unittest.mock import MagicMock, patch
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
from vendors.javan import (
    JavanVendorAdapter,
    JavanSelectors,
    JavanErrorTranslator,
    JavanSessionManager,
)


# ============================================================================
# 1. CONTRACT INHERITANCE & OPERATION COMPLETENESS
# ============================================================================

class TestJavanAdapterContract:
    def test_ivendor_adapter_inheritance(self):
        """Verify JavanVendorAdapter implements IVendorAdapter."""
        assert issubclass(JavanVendorAdapter, IVendorAdapter)

    def test_all_13_methods_present(self):
        """Verify all 13 conceptual operations exist on JavanVendorAdapter."""
        adapter = JavanVendorAdapter()
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
            assert hasattr(adapter, m), f"Missing method {m} on JavanVendorAdapter"
            assert callable(getattr(adapter, m)), f"Attribute {m} is not callable"

    def test_vendor_metadata(self):
        """Verify vendor_id and base_url constants."""
        adapter = JavanVendorAdapter()
        assert adapter.vendor_id == "vendor_javan"
        assert adapter.base_url == "https://www.javanelec.com"


# ============================================================================
# 2. SELECTOR REGEXES & URL PATTERNS
# ============================================================================

class TestJavanSelectorsAndPatterns:
    def test_pdp_url_regex(self):
        """Test canonical PDP URL regex parsing."""
        url = "https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p"
        m = JavanSelectors.PDP_URL_PATTERN.match(url)
        assert m is not None
        assert m.group("product_id") == "17930"
        assert m.group("manufacturer") == "texas-instruments"
        assert m.group("slug") == "ne555p"

    def test_pdp_path_regex(self):
        """Test relative PDP path regex parsing."""
        path = "/shop/product/17930/texas-instruments/ne555p"
        m = JavanSelectors.PDP_PATH_PATTERN.match(path)
        assert m is not None
        assert m.group("product_id") == "17930"
        assert m.group("manufacturer") == "texas-instruments"
        assert m.group("slug") == "ne555p"

    def test_search_url_template(self):
        """Test search URL template generation."""
        formatted = JavanSelectors.SEARCH_URL_TEMPLATE.format(query="NE555")
        assert "searchfilter=NE555" in formatted
        assert "#filter_items_-1" in formatted


# ============================================================================
# 3. 3-TIER ERROR TRANSLATION ENGINE
# ============================================================================

class TestJavanErrorTranslation:
    def test_modal_moq_violation(self):
        err = JavanErrorTranslator.translate_modal_message("حداقل تعداد خرید این کالا 50 عدد است")
        assert isinstance(err, MOQViolationError)
        assert err.vendor_id == "vendor_javan"

    def test_modal_order_multiple_violation(self):
        err = JavanErrorTranslator.translate_modal_message("تعداد سفارش باید مضرب 50 باشد")
        assert isinstance(err, OrderMultipleViolationError)
        assert err.vendor_id == "vendor_javan"

    def test_modal_max_quantity_exceeded(self):
        err = JavanErrorTranslator.translate_modal_message("تعداد درخواستی بیش از موجودی انبار است")
        assert isinstance(err, MaxQuantityExceededError)
        assert err.vendor_id == "vendor_javan"

    def test_modal_out_of_stock(self):
        err = JavanErrorTranslator.translate_modal_message("متاسفانه این کالا ناموجود است")
        assert isinstance(err, OutOfStockError)
        assert err.vendor_id == "vendor_javan"

    def test_modal_unknown_error(self):
        err = JavanErrorTranslator.translate_modal_message("خطای نامشخص در ثبت اطلاعات")
        assert isinstance(err, UnknownVendorError)
        assert err.vendor_id == "vendor_javan"

    def test_page_state_not_found_404(self):
        err = JavanErrorTranslator.translate_page_state(
            http_status=404,
            page_title="جوان الکترونیک - Not Found",
            page_source="<h1>صفحه مورد نظر شما یافت نشد</h1>",
            current_url="https://www.javanelec.com/home/notfound",
        )
        assert isinstance(err, ProductNotFoundError)

    def test_page_state_waf_block(self):
        err = JavanErrorTranslator.translate_page_state(
            http_status=403,
            page_title="403 Forbidden",
            page_source="Access Denied by ArvanCloud Firewall",
            current_url="https://www.javanelec.com/shop",
        )
        assert isinstance(err, WAFBlockError)

    def test_page_state_session_expired(self):
        err = JavanErrorTranslator.translate_page_state(
            http_status=401,
            page_title="ورود به حساب کاربری",
            page_source="ورود",
            current_url="https://www.javanelec.com/account/login",
            context={"expect_authenticated": True},
        )
        assert isinstance(err, SessionExpiredError)

    def test_page_state_security_challenge(self):
        err = JavanErrorTranslator.translate_page_state(
            page_title="Security Check",
            page_source="Please solve the captcha challenge below",
            current_url="https://www.javanelec.com/challenge",
        )
        assert isinstance(err, SecurityChallengeError)

    def test_transport_timeout(self):
        exc = Exception("TimeoutException: Timed out receiving message from renderer")
        err = JavanErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, TransportNetworkError)

    def test_dom_drift_missing_element(self):
        exc = Exception("NoSuchElementException: Unable to locate element: input#searchAll")
        err = JavanErrorTranslator.translate_transport_exception(exc)
        assert isinstance(err, DOMDriftError)


# ============================================================================
# 4. PRODUCT RESOLUTION TESTS
# ============================================================================

class TestJavanProductResolution:
    def test_resolve_full_url(self):
        adapter = JavanVendorAdapter()
        ref = adapter.resolve_product("https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p")
        assert ref.vendor_id == "vendor_javan"
        assert ref.vendor_sku == "17930"
        assert ref.product_id == "17930"
        assert ref.slug == "ne555p"

    def test_resolve_relative_url(self):
        adapter = JavanVendorAdapter()
        ref = adapter.resolve_product("/shop/product/17930/texas-instruments/ne555p")
        assert ref.vendor_id == "vendor_javan"
        assert ref.vendor_sku == "17930"
        assert ref.pdp_url == "https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p"

    def test_resolve_sku_format(self):
        adapter = JavanVendorAdapter()
        ref = adapter.resolve_product("17930/texas-instruments/ne555p")
        assert ref.vendor_id == "vendor_javan"
        assert ref.vendor_sku == "17930"
        assert ref.pdp_url == "https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p"

    def test_resolve_empty_raises_not_found(self):
        adapter = JavanVendorAdapter()
        with pytest.raises(ProductNotFoundError):
            adapter.resolve_product("")


# ============================================================================
# 5. DATA EXTRACTION & TIERED PRICING TESTS (MOCK DOM)
# ============================================================================

MOCK_JAVAN_PDP_HTML = """
<!DOCTYPE html>
<html>
<head><title>NE555P | Texas Instruments</title></head>
<body>
    <h1 class="font-weight-bold">NE555P | Texas Instruments</h1>
    <table>
        <tr><th>Features</th><th>انتخاب ویژگی</th></tr>
        <tr><td>Brand</td><td>Texas Instruments</td></tr>
        <tr><td>Package</td><td>DIP-8</td></tr>
        <tr><td>Mounting Style</td><td>Through Hole</td></tr>
        <tr><td>Supply Voltage (Min)</td><td>4.5 V</td></tr>
        <tr><td>Supply Voltage (Max)</td><td>16 V</td></tr>
        <tr><td>Minimum Operating Temperature</td><td>0 °C</td></tr>
        <tr><td>Maximum Operating Temperature</td><td>+70 °C</td></tr>
    </table>
    <table>
        <tr><th>تعداد</th><th>قیمت واحد</th></tr>
        <tr><td>50 عدد</td><td>78,100 ریال</td></tr>
        <tr><td>200 عدد</td><td>77,300 ریال</td></tr>
        <tr><td>500 عدد</td><td>76,500 ریال</td></tr>
        <tr><td>1,000 عدد</td><td>74,900 ریال</td></tr>
    </table>
    <form action="/shoppingcarts/createindex" class="form-horizontal" method="post">
        <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
    </form>
</body>
</html>
"""

class TestJavanProductDataExtraction:
    def test_extract_specs_table(self):
        adapter = JavanVendorAdapter()
        draft = adapter.extract_product_data(MOCK_JAVAN_PDP_HTML)
        assert draft.vendor_id == "vendor_javan"
        assert draft.manufacturer == "Texas Instruments"
        assert draft.package == "DIP-8"
        assert draft.specs.get("Mounting Style") == "Through Hole"
        assert draft.specs.get("Supply Voltage (Min)") == "4.5 V"
        assert "Features" not in draft.specs

    def test_extract_price_tiers(self):
        adapter = JavanVendorAdapter()
        soup = BeautifulSoup(MOCK_JAVAN_PDP_HTML, "html.parser")
        tiers = adapter._extract_price_tiers(soup)
        assert len(tiers) == 4
        assert tiers[0] == {"min_quantity": 50, "unit_price_irr": 78100}
        assert tiers[1] == {"min_quantity": 200, "unit_price_irr": 77300}
        assert tiers[2] == {"min_quantity": 500, "unit_price_irr": 76500}
        assert tiers[3] == {"min_quantity": 1000, "unit_price_irr": 74900}

    def test_raw_packaging_step_preserved_as_is(self):
        adapter = JavanVendorAdapter()
        soup = BeautifulSoup(MOCK_JAVAN_PDP_HTML, "html.parser")
        tiers = adapter._extract_price_tiers(soup)
        lowest_step = tiers[0]["min_quantity"]
        # Must preserve raw 50 without core optimization
        assert lowest_step == 50


# ============================================================================
# 6. CART & ORDERING VALIDATIONS
# ============================================================================

class TestJavanCartAndOrderingValidations:
    def test_add_to_cart_zero_or_negative_quantity(self):
        adapter = JavanVendorAdapter()
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p")
        with pytest.raises(OrderMultipleViolationError):
            adapter.add_to_cart(ref, 0)
        with pytest.raises(OrderMultipleViolationError):
            adapter.add_to_cart(ref, -5)


MOCK_LM358_PDP_HTML = """
<!DOCTYPE html>
<html>
<head><title>LM358D | STMicroelectronics</title></head>
<body>
    <h1 class="font-weight-bold">LM358D | STMicroelectronics</h1>
    <table>
        <tr><th>Features</th><th>انتخاب ویژگی</th></tr>
        <tr><td>Brand</td><td>STMicroelectronics</td></tr>
        <tr><td>Package</td><td>SOIC-8</td></tr>
        <tr><td>Mounting Style</td><td>SMD/SMT</td></tr>
    </table>
    <table>
        <tr><th>تعداد</th><th>قیمت واحد</th></tr>
        <tr><td>100 عدد</td><td>136,000 ریال</td></tr>
        <tr><td>200 عدد</td><td>135,000 ریال</td></tr>
        <tr><td>500 عدد</td><td>133,000 ریال</td></tr>
        <tr><td>1,000 عدد</td><td>131,000 ریال</td></tr>
        <tr><td>2,500 عدد</td><td>128,000 ریال</td></tr>
    </table>
    <form action="/shoppingcarts/createindex" class="form-horizontal" method="post">
        <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
    </form>
</body>
</html>
"""

class TestJavanLM358Extraction:
    def test_extract_lm358_specs_and_5_tiers(self):
        adapter = JavanVendorAdapter()
        draft = adapter.extract_product_data(MOCK_LM358_PDP_HTML)
        assert draft.manufacturer == "STMicroelectronics"
        assert draft.package == "SOIC-8"

        soup = BeautifulSoup(MOCK_LM358_PDP_HTML, "html.parser")
        tiers = adapter._extract_price_tiers(soup)
        assert len(tiers) == 5
        assert tiers[0] == {"min_quantity": 100, "unit_price_irr": 136000}
        assert tiers[4] == {"min_quantity": 2500, "unit_price_irr": 128000}


# ============================================================================
# 7. SESSION, RECOVERY & MOCK LIFECYCLE TESTS
# ============================================================================

class TestJavanSessionAndRecovery:
    def test_session_manager_init(self):
        mgr = JavanSessionManager()
        assert mgr.config.vendor_id == "vendor_javan"
        assert mgr.config.base_url == "https://www.javanelec.com"
        assert mgr.config.settle_seconds == 2.2

    def test_auth_without_credentials_fails(self):
        adapter = JavanVendorAdapter()
        res = adapter.authenticate(None)
        assert res.success is False
        assert "not provided" in res.message

    def test_recover_from_error_noop(self):
        adapter = JavanVendorAdapter()
        adapter.session.dismiss_active_modal = MagicMock(return_value=False)
        rec = adapter.recover_from_error({})
        assert rec.recovered is False
        assert rec.action_taken == "NOOP"

    def test_recover_from_error_dismissed(self):
        adapter = JavanVendorAdapter()
        adapter.session.dismiss_active_modal = MagicMock(return_value=True)
        rec = adapter.recover_from_error({})
        assert rec.recovered is True
        assert rec.action_taken == "DISMISS_MODAL"

    def test_close_resets_ready(self):
        adapter = JavanVendorAdapter()
        adapter._is_ready = True
        adapter.session.close = MagicMock()
        adapter.close()
        assert adapter._is_ready is False
        adapter.session.close.assert_called_once()

