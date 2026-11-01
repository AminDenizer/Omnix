"""
Comprehensive Unit and Integration Tests for Lion & Javan Vendor Plugins
Validates BOM Products, Availability Classifications, Registry Integration, and Fail-Closed Safeguards.
"""

import json
import pytest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

from core.models import (
    ProductReference,
    ProductDetails,
    CanonicalComponentDraft,
    StockStatus,
)
from core.errors import (
    ProductNotFoundError,
    TransportNetworkError,
)
from core.procurement.registry import VendorRegistry
from vendors.lion.adapter import LionVendorAdapter
from vendors.lion.selectors import LionSelectors
from vendors.javan.adapter import JavanVendorAdapter
from vendors.javan.selectors import JavanSelectors


# ============================================================================
# MOCK HTML FIXTURES
# ============================================================================

LION_AVAILABLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>STM32F103VET6 - Lion Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">STM32F103VET6</h1>
    <span class="stock-amount">100 عدد موجود است</span>
    <input id="quantity-cell" class="quantity-cell" value="1" />
    <button class="btn-buy">افزودن به سبد خرید</button>
    <div class="product-price">
        <span class="price-value">19,909,502 ریال</span>
    </div>
    <table class="table table-bordered table-striped">
        <tr><td>پارت نامبر</td><td>STM32F103VET6</td></tr>
        <tr><td>تولید کننده</td><td>STMicroelectronics</td></tr>
        <tr><td>پکیج</td><td>LQFP-100</td></tr>
    </table>
</div>
</body>
</html>
"""

LION_OOS_HTML = """
<!DOCTYPE html>
<html>
<head><title>MOCK_LION_OOS - Lion Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">MOCK_LION_OOS</h1>
    <div class="stock-status">
        <span class="badge badge-danger">ناموجود</span>
        <span class="stock-amount">0</span>
    </div>
    <table class="table table-bordered table-striped">
        <tr><td>پارت نامبر</td><td>MOCK_LION_OOS</td></tr>
        <tr><td>تولید کننده</td><td>Generic</td></tr>
    </table>
</div>
</body>
</html>
"""

LION_COMING_SOON_HTML = """
<!DOCTYPE html>
<html>
<head><title>MOCK_LION_COMING_SOON - Lion Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">MOCK_LION_COMING_SOON</h1>
    <div class="stock-status">
        <span class="badge badge-warning">به زودی</span>
    </div>
    <table class="table table-bordered table-striped">
        <tr><td>پارت نامبر</td><td>MOCK_LION_COMING_SOON</td></tr>
    </table>
</div>
</body>
</html>
"""

JAVAN_AVAILABLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>STM32F103VET6 - Javan Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">STM32F103VET6</h1>
    <span class="product-status badge-success">موجود در انبار</span>
    <button type="submit" class="btn-success-outline">افزودن به سبد خرید</button>
    <span class="price">4,256,000 ریال</span>
    <table>
        <tr><td>پارت نامبر</td><td>STM32F103VET6</td></tr>
        <tr><td>سازنده</td><td>STMicroelectronics</td></tr>
        <tr><td>پکیج</td><td>LQFP-100</td></tr>
    </table>
</div>
</body>
</html>
"""

JAVAN_OOS_HTML = """
<!DOCTYPE html>
<html>
<head><title>SMAJ5.0A - Javan Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">SMAJ5.0A</h1>
    <span class="product-status badge-danger">اتمام موجودی</span>
    <button class="btn-contact">تماس بگیرید</button>
    <table>
        <tr><td>پارت نامبر</td><td>SMAJ5.0A</td></tr>
        <tr><td>سازنده</td><td>Vishay</td></tr>
    </table>
</div>
</body>
</html>
"""

JAVAN_PREORDER_HTML = """
<!DOCTYPE html>
<html>
<head><title>MOCK_JAVAN_PREORDER - Javan Electronic</title></head>
<body>
<div class="product-detail">
    <h1 class="font-weight-bold">MOCK_JAVAN_PREORDER</h1>
    <span class="product-status badge-warning">تامین</span>
    <button class="btn-preorder">پیش خرید</button>
    <table>
        <tr><td>پارت نامبر</td><td>MOCK_JAVAN_PREORDER</td></tr>
        <tr><td>سازنده</td><td>Generic</td></tr>
    </table>
</div>
</body>
</html>
"""


def _setup_mock_session(adapter, html: str, title: str, current_url: str):
    """Configures a mock driver and session manager for deterministic, instant execution."""
    mock_driver = MagicMock()
    mock_driver.page_source = html
    mock_driver.title = title
    mock_driver.current_url = current_url
    mock_driver.execute_script.return_value = None

    adapter.session.driver = mock_driver
    adapter.session.get_driver = MagicMock(return_value=mock_driver)
    adapter.session.wait_for_settle = MagicMock(return_value=None)
    adapter.session.execute_script = MagicMock(return_value=None)
    return mock_driver


# ============================================================================
# 1. REGISTRY INTEGRATION & ROUTING TESTS
# ============================================================================

class TestLionJavanRegistryIntegration:
    """Tests dynamic manifest registration, capability detection, and route dispatching."""

    def test_manifest_files_and_registration(self):
        reg = VendorRegistry()
        with open("vendors/lion/manifest.json", encoding="utf-8") as f:
            lion_manifest = json.load(f)
        with open("vendors/javan/manifest.json", encoding="utf-8") as f:
            javan_manifest = json.load(f)

        reg_lion = reg.register_plugin_manifest(lion_manifest, LionVendorAdapter)
        reg_javan = reg.register_plugin_manifest(javan_manifest, JavanVendorAdapter)

        assert reg_lion.vendor_id == "vendor_lion"
        assert reg_javan.vendor_id == "vendor_javan"
        assert reg.has_vendor("vendor_lion")
        assert reg.has_vendor("vendor_javan")

    def test_domain_routing_resolution(self):
        reg = VendorRegistry()
        with open("vendors/lion/manifest.json", encoding="utf-8") as f:
            reg.register_plugin_manifest(json.load(f), LionVendorAdapter)
        with open("vendors/javan/manifest.json", encoding="utf-8") as f:
            reg.register_plugin_manifest(json.load(f), JavanVendorAdapter)

        # Lion domains
        assert reg.get_vendor_for_url("https://lionelectronic.ir/products/271-STM32F103VET6") == "vendor_lion"
        assert reg.get_vendor_for_url("https://www.lionelectronic.ir/products/2189-AMS1117-5.0") == "vendor_lion"

        # Javan domains
        assert reg.get_vendor_for_url("https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6") == "vendor_javan"
        assert reg.get_vendor_for_url("https://javanelec.com/shop/product/21714/advanced-monolithic-systems/ams1117-5-0") == "vendor_javan"

        # Unknown domain
        assert reg.get_vendor_for_url("https://unknown-distributor.com/item/123") is None

    def test_adapter_instantiation_from_registry(self):
        reg = VendorRegistry()
        with open("vendors/lion/manifest.json", encoding="utf-8") as f:
            reg.register_plugin_manifest(json.load(f), LionVendorAdapter)
        with open("vendors/javan/manifest.json", encoding="utf-8") as f:
            reg.register_plugin_manifest(json.load(f), JavanVendorAdapter)

        lion_adapter = reg.get_adapter("vendor_lion")
        javan_adapter = reg.get_adapter("vendor_javan")

        assert isinstance(lion_adapter, LionVendorAdapter)
        assert isinstance(javan_adapter, JavanVendorAdapter)
        assert lion_adapter.vendor_id == "vendor_lion"
        assert javan_adapter.vendor_id == "vendor_javan"


# ============================================================================
# 2. LION ADAPTER EXTRACTION & AVAILABILITY TESTS
# ============================================================================

class TestLionAdapterExtraction:
    """Verifies Lion extraction, pricing, and stock status rules."""

    def test_lion_available_product_extraction(self):
        adapter = LionVendorAdapter()
        _setup_mock_session(adapter, LION_AVAILABLE_HTML, "STM32F103VET6 - Lion Electronic", "https://lionelectronic.ir/products/271-STM32F103VET6")

        pref = ProductReference(
            vendor_id="vendor_lion",
            vendor_sku="271",
            pdp_url="https://lionelectronic.ir/products/271-STM32F103VET6",
        )

        details = adapter.inspect_product(pref)
        assert details.mpn == "STM32F103VET6"
        assert details.stock_quantity == 100
        assert details.can_order is True
        assert details.price_irr == 19909502
        assert details.manufacturer == "STMicroelectronics"

        stock = adapter.inspect_stock(pref)
        assert stock.in_stock is True
        assert stock.stock_quantity == 100
        assert stock.can_order is True

    def test_lion_out_of_stock_extraction(self):
        adapter = LionVendorAdapter()
        _setup_mock_session(adapter, LION_OOS_HTML, "MOCK_LION_OOS - Lion Electronic", "https://lionelectronic.ir/products/9999-MOCK_LION_OOS")

        pref = ProductReference(
            vendor_id="vendor_lion",
            vendor_sku="9999",
            pdp_url="https://lionelectronic.ir/products/9999-MOCK_LION_OOS",
        )

        details = adapter.inspect_product(pref)
        assert details.can_order is False
        assert details.stock_quantity == 0

        stock = adapter.inspect_stock(pref)
        assert stock.in_stock is False
        assert stock.can_order is False

    def test_lion_coming_soon_extraction(self):
        adapter = LionVendorAdapter()
        _setup_mock_session(adapter, LION_COMING_SOON_HTML, "MOCK_LION_COMING_SOON - Lion Electronic", "https://lionelectronic.ir/products/9998-MOCK_LION_COMING_SOON")

        pref = ProductReference(
            vendor_id="vendor_lion",
            vendor_sku="9998",
            pdp_url="https://lionelectronic.ir/products/9998-MOCK_LION_COMING_SOON",
        )

        details = adapter.inspect_product(pref)
        assert details.can_order is False
        assert "به‌زودی" in details.raw_status_text or "به زودی" in details.raw_status_text

        stock = adapter.inspect_stock(pref)
        assert stock.can_order is False

    def test_lion_canonical_component_draft(self):
        adapter = LionVendorAdapter()
        soup = BeautifulSoup(LION_AVAILABLE_HTML, "html.parser")
        draft = adapter.extract_product_data(soup)

        assert isinstance(draft, CanonicalComponentDraft)
        assert draft.mpn == "STM32F103VET6"
        assert draft.manufacturer == "STMicroelectronics"
        assert draft.package == "LQFP-100"


# ============================================================================
# 3. JAVAN ADAPTER EXTRACTION & AVAILABILITY TESTS
# ============================================================================

class TestJavanAdapterExtraction:
    """Verifies Javan extraction, pricing, and fail-closed availability rules."""

    def test_javan_available_product_extraction(self):
        adapter = JavanVendorAdapter()
        _setup_mock_session(adapter, JAVAN_AVAILABLE_HTML, "STM32F103VET6 - Javan Electronic", "https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6")

        pref = ProductReference(
            vendor_id="vendor_javan",
            vendor_sku="53852",
            pdp_url="https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6",
        )

        details = adapter.inspect_product(pref)
        assert details.mpn == "STM32F103VET6"
        assert details.can_order is True
        assert details.price_irr == 4256000
        assert details.manufacturer == "STMicroelectronics"

        stock = adapter.inspect_stock(pref)
        assert stock.in_stock is True
        assert stock.can_order is True

    def test_javan_out_of_stock_extraction(self):
        adapter = JavanVendorAdapter()
        _setup_mock_session(adapter, JAVAN_OOS_HTML, "SMAJ5.0A - Javan Electronic", "https://www.javanelec.com/shop/product/40465/vishay/smaj5-0a")

        pref = ProductReference(
            vendor_id="vendor_javan",
            vendor_sku="40465",
            pdp_url="https://www.javanelec.com/shop/product/40465/vishay/smaj5-0a",
        )

        details = adapter.inspect_product(pref)
        assert details.can_order is False
        assert details.stock_quantity == 0
        assert "اتمام" in details.raw_status_text or "ناموجود" in details.raw_status_text

        stock = adapter.inspect_stock(pref)
        assert stock.in_stock is False
        assert stock.can_order is False

    def test_javan_preorder_prohibited_fail_closed(self):
        adapter = JavanVendorAdapter()
        _setup_mock_session(adapter, JAVAN_PREORDER_HTML, "MOCK_JAVAN_PREORDER - Javan Electronic", "https://www.javanelec.com/shop/product/99999/generic/mock-javan-preorder")

        pref = ProductReference(
            vendor_id="vendor_javan",
            vendor_sku="99999",
            pdp_url="https://www.javanelec.com/shop/product/99999/generic/mock-javan-preorder",
        )

        details = adapter.inspect_product(pref)
        # Fail-closed policy blocks ordering of items in تامین / preorder status
        assert details.can_order is False
        assert "تأمین" in details.raw_status_text or "تامین" in details.raw_status_text

        stock = adapter.inspect_stock(pref)
        assert stock.can_order is False

    def test_javan_canonical_component_draft(self):
        adapter = JavanVendorAdapter()
        soup = BeautifulSoup(JAVAN_AVAILABLE_HTML, "html.parser")
        draft = adapter.extract_product_data(soup)

        assert isinstance(draft, CanonicalComponentDraft)
        assert draft.mpn == "STM32F103VET6"
        assert draft.manufacturer == "STMicroelectronics"
        assert draft.package == "LQFP-100"


# ============================================================================
# 4. NETWORK TIMEOUTS & ERROR TRANSLATIONS
# ============================================================================

class TestNetworkAndErrorTranslations:
    """Verifies deterministic error translation for transport, 404, and WAF blocks."""

    def test_lion_network_timeout_translation(self):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.get.side_effect = Exception("Connection timed out after 30000ms")
        adapter.session.driver = mock_driver
        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="123", pdp_url="https://lionelectronic.ir/products/123-TEST")
        with pytest.raises(TransportNetworkError) as exc_info:
            adapter.inspect_product(pref)
        assert "timed out" in exc_info.value.message.lower() or "transport" in exc_info.value.message.lower()

    def test_javan_network_timeout_translation(self):
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.get.side_effect = Exception("net::ERR_CONNECTION_TIMED_OUT")
        adapter.session.driver = mock_driver
        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://www.javanelec.com/shop/product/123/mfr/slug")
        with pytest.raises(TransportNetworkError) as exc_info:
            adapter.inspect_product(pref)
        assert "timed out" in exc_info.value.message.lower() or "transport" in exc_info.value.message.lower()

    def test_lion_404_product_not_found(self):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.page_source = "<html><head><title>404 Not Found</title></head><body>Product not found</body></html>"
        mock_driver.title = "404 Not Found"
        mock_driver.current_url = "https://lionelectronic.ir/products/0000-NONEXISTENT"
        adapter.session.driver = mock_driver
        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="0000", pdp_url="https://lionelectronic.ir/products/0000-NONEXISTENT")
        with pytest.raises(ProductNotFoundError):
            adapter.inspect_product(pref)

    def test_javan_404_product_not_found(self):
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.page_source = "<html><head><title>Not Found</title></head><body>صفحه مورد نظر شما یافت نشد</body></html>"
        mock_driver.title = "Not Found"
        mock_driver.current_url = "https://www.javanelec.com/home/notfound"
        adapter.session.driver = mock_driver
        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="0000", pdp_url="https://www.javanelec.com/shop/product/0000/none/not-found")
        with pytest.raises(ProductNotFoundError):
            adapter.inspect_product(pref)


# ============================================================================
# 5. USER-SUPPLIED LION & JAVAN VALIDATION CASES
# ============================================================================

from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.models import (
    ProcurementRequest,
    VendorProcurementCandidate,
    EvaluationState,
)
from core.models import OrderConstraints


class TestUserSuppliedValidationCases:
    """Deterministic tests for user-reported storefront edge cases."""

    def test_lion_coming_soon_frc0805(self):
        """Verifies Lion coming soon detection on FRC0805J102TS with 'به زودی' in quantity cell."""
        html = """
        <html><body>
        <div class="product-detail">
            <h1>FRC0805J102TS</h1>
            <span class="stock-amount">به زودیموجودی محصول</span>
            <input id="quantity-cell" value="به زودی" />
            <div class="product-price">1005,344 ریال</div>
        </div>
        </body></html>
        """
        adapter = LionVendorAdapter()
        _setup_mock_session(adapter, html, "FRC0805J102TS - Lion", "https://lionelectronic.ir/products/1573-FRC0805J102TS")
        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="1573", pdp_url="https://lionelectronic.ir/products/1573-FRC0805J102TS")
        details = adapter.inspect_product(pref)

        assert details.can_order is False
        assert "به‌زودی" in details.raw_status_text or "به زودی" in details.raw_status_text

    def test_lion_out_of_stock_0805w8j(self):
        """Verifies Lion out-of-stock detection on 0805W8J0272T5E with 'اتمام موجودی'."""
        html = """
        <html><body>
        <div class="product-detail">
            <h1>0805W8J0272T5E</h1>
            <span class="stock-amount">اتمام موجودیموجودی محصول</span>
            <input id="quantity-cell" value="اتمام موجودی" />
        </div>
        </body></html>
        """
        adapter = LionVendorAdapter()
        _setup_mock_session(adapter, html, "0805W8J0272T5E - Lion", "https://lionelectronic.ir/products/1578-0805W8J0272T5E")
        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="1578", pdp_url="https://lionelectronic.ir/products/1578-0805W8J0272T5E")
        details = adapter.inspect_product(pref)

        assert details.can_order is False
        assert details.stock_quantity == 0
        assert "اتمام موجودی" in details.raw_status_text or "ناموجود" in details.raw_status_text

    def test_lion_moq_vs_stock_edge_case(self):
        """
        Verifies residual stock scenario: MOQ=100, Stock=99 on Lion (0603WAJ0562T5E).
        When required_quantity (45) <= available stock (99) < MOQ/step (100),
        the store allows purchasing all remaining stock (99). Orchestrator clamps
        effective_quantity to 99 and marks the candidate ELIGIBLE.
        """
        orchestrator = UniversalProcurementOrchestrator()
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="0603WAJ0562T5E",
            product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="1314", pdp_url="https://lionelectronic.ir/products/1314-0603WAJ0562T5E"),
            base_unit_price_irr=3564,
            stock_quantity=99,
            can_order=True,
            in_stock=True,
            raw_status_text="99 عدد موجود است",
            order_constraints=OrderConstraints(packaging_step_raw=100, moq_raw=100)
        )
        req = ProcurementRequest(
            part_number="0603WAJ0562T5E",
            required_quantity=45,
            explicit_vendor_url="https://lionelectronic.ir/products/1314-0603WAJ0562T5E"
        )
        eval_result = orchestrator.evaluate_candidate(cand, req)

        assert eval_result.effective_quantity == 99
        assert eval_result.state == EvaluationState.ELIGIBLE
        assert eval_result.is_eligible is True
        assert len(eval_result.rejection_reasons) == 0

    def test_lion_low_stock_shortage(self):
        """Verifies low-stock handling on 3296W-1-201 (Stock=11 vs Needed=23)."""
        orchestrator = UniversalProcurementOrchestrator()
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="3296W-1-201",
            product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="3236", pdp_url="https://lionelectronic.ir/products/3236-3296W-1-201"),
            base_unit_price_irr=1482668,
            stock_quantity=11,
            can_order=True,
            in_stock=True,
            raw_status_text="11 عدد موجود است",
            order_constraints=OrderConstraints(packaging_step_raw=1, moq_raw=1)
        )
        req = ProcurementRequest(
            part_number="3296W-1-201",
            required_quantity=23,
            explicit_vendor_url="https://lionelectronic.ir/products/3236-3296W-1-201"
        )
        eval_result = orchestrator.evaluate_candidate(cand, req)

        assert eval_result.effective_quantity == 23
        assert eval_result.state == EvaluationState.INSUFFICIENT_STOCK
        assert any("11 available < 23" in r for r in eval_result.rejection_reasons)

    def test_lion_product_without_conventional_mpn(self):
        """Verifies local PCB product (6207-eMMC-WFBGA153-to-microSD-PCB) uses exact title without inventing MPN."""
        html = """
        <html><body>
        <div class="product-detail">
            <h1>eMMC WFBGA153 to microSD PCB</h1>
            <span class="stock-amount">93 عدد موجود است</span>
            <input id="quantity-cell" value="1" />
            <div class="product-price">12,444,486 ریال</div>
        </div>
        </body></html>
        """
        adapter = LionVendorAdapter()
        soup = BeautifulSoup(html, "html.parser")
        draft = adapter.extract_product_data(soup)

        assert draft.mpn == "eMMC WFBGA153 to microSD PCB"
        assert draft.manufacturer is None

    def test_lion_three_similar_100nf_distinctness(self):
        """Verifies three 100nF products have distinct packages, voltages, and part numbers."""
        adapter = LionVendorAdapter()
        html_0805 = "<html><body><div class='product-detail'><h1>CL21B104KBCNNNC</h1><table><tr><td>پکیج</td><td>0805</td></tr><tr><td>ولتاژ</td><td>50V</td></tr></table></div></body></html>"
        html_0603_100v = "<html><body><div class='product-detail'><h1>CL10B104KC8NNNC</h1><table><tr><td>پکیج</td><td>0603</td></tr><tr><td>ولتاژ</td><td>100V</td></tr></table></div></body></html>"
        html_0603_50v = "<html><body><div class='product-detail'><h1>CL10B104KB8NNNC</h1><table><tr><td>پکیج</td><td>0603</td></tr><tr><td>ولتاژ</td><td>50V</td></tr></table></div></body></html>"

        d1 = adapter.extract_product_data(BeautifulSoup(html_0805, "html.parser"))
        d2 = adapter.extract_product_data(BeautifulSoup(html_0603_100v, "html.parser"))
        d3 = adapter.extract_product_data(BeautifulSoup(html_0603_50v, "html.parser"))

        assert d1.mpn == "CL21B104KBCNNNC"
        assert d1.package == "0805"

        assert d2.mpn == "CL10B104KC8NNNC"
        assert d2.package == "0603"

        assert d3.mpn == "CL10B104KB8NNNC"
        assert d3.package == "0603"

        # Assert no two are identical
        assert d1.mpn != d2.mpn != d3.mpn

    def test_javan_order_on_request_35_days_fail_closed(self):
        """Verifies Javan 'ناموجود-سفارش دهید' with 35-day delivery triggers fail-closed block."""
        html = """
        <html><body>
        <div class="product-detail">
            <h1>100NF (1210) 50V 10% X7R</h1>
            <span class="product-status">ناموجود-سفارش دهید</span>
            <button class="btn-order">اضافه به سبد سفارش</button>
            <div class="delivery-time">زمان تحویل 35 روزه</div>
        </div>
        </body></html>
        """
        adapter = JavanVendorAdapter()
        _setup_mock_session(adapter, html, "100nF - Javan", "https://www.javanelec.com/shop/product/21063")
        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="21063", pdp_url="https://www.javanelec.com/shop/product/21063")
        details = adapter.inspect_product(pref)

        assert details.can_order is False
        assert "ناموجود-سفارش دهید" in details.raw_status_text

    def test_javan_short_url_and_long_url_parity(self):
        """Verifies both short URL (/shop/product/53852) and long URL resolve correctly."""
        adapter = JavanVendorAdapter()
        short_url = "https://www.javanelec.com/shop/product/53852"
        long_url = "https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6"

        ref_short = adapter.resolve_product(short_url)
        ref_long = adapter.resolve_product(long_url)

        assert ref_short.product_id == "53852"
        assert ref_long.product_id == "53852"
        assert ref_short.vendor_id == "vendor_javan"
        assert ref_long.vendor_id == "vendor_javan"
        assert adapter.is_pdp_url(short_url) is True
        assert adapter.is_pdp_url(long_url) is True

    def test_javan_url_with_parentheses_and_percent(self):
        """Verifies URL with parentheses and percent-encoding matches PDP regex."""
        adapter = JavanVendorAdapter()
        url = "https://www.javanelec.com/shop/product/21063/chaozhou-three-circle-(group)-co/100nf-(1210)-50v-10%25-x7r"

        assert adapter.is_pdp_url(url) is True
        ref = adapter.resolve_product(url)
        assert ref.product_id == "21063"
        assert ref.vendor_sku == "21063"

