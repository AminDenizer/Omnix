"""
Tests for Fail-Closed Supplier Availability Gates (Lion Electronic + Javan Electronic).

Validates:
1. Lion product-status gate:
   - Explicitly available -> ALLOW
   - به‌زودی (ZWNJ, spaced, compact) -> BLOCK
   - اتمام موجودی -> BLOCK
   - Status cannot be reliably identified -> BLOCK
   - Inquiry-only / productCanOrder=false -> BLOCK
2. Javan product-status gate:
   - Explicitly open/available (موجود در انبار) -> ALLOW
   - تأمین -> BLOCK
   - اتمام -> BLOCK
   - ناموجود-سفارش دهید (even with lead time / delivery estimate) -> BLOCK
   - Visible order button / lead time does not override prohibited status -> BLOCK
   - Status cannot be reliably identified -> BLOCK
3. Dual-Path Integration:
   - Path A (Stock Shortages) with eligible vs blocked links
   - Path B (Altium BOM) with eligible vs blocked links
   - Multi-vendor selection of blocked supplier fails closed without silent fallback
   - Transport / network error fails closed before add_to_cart
"""

import pytest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from core.models import (
    ProductReference,
    ProductDetails,
    StockStatus,
    CartMutationResult,
    SessionStatus,
)
from core.procurement.models import (
    ProcurementMode,
    ProcurementRequest,
)
from core.procurement.registry import VendorRegistry
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.bridge import ProcurementBridge
from core.errors import OutOfStockError, TransportNetworkError
from vendors.lion.adapter import LionVendorAdapter
from vendors.javan.adapter import JavanVendorAdapter


# ============================================================================
# 1. LION ELECTRONIC STOREFRONT AVAILABILITY GATE TESTS
# ============================================================================

class TestLionAvailabilityGate:
    """Verifies fail-closed product-status rules for Lion Electronic."""

    def _create_mock_lion_adapter(self, html: str, can_order_js=None):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.title = "Lion Electronic Product"
        mock_driver.page_source = html
        mock_driver.current_url = "https://lionelectronic.ir/products/2070-NE555P"

        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.execute_script = MagicMock(return_value=can_order_js)
        adapter.session.wait_for_settle = MagicMock()
        return adapter

    def test_lion_explicitly_available_is_allowed(self):
        """Positive stock, no prohibited markers, can_order_js is True/None -> ALLOW."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> 2,450 </span>
                <input id="quantity-cell" value="10" />
                <button class="btn-buy">خرید آنلاین</button>
                <div class="product-price"> 85,000 ریال </div>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html, can_order_js=True)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is True
        assert details.stock_quantity == 2450
        assert details.is_inquiry_only is False

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is True
        assert stock.can_order is True
        assert stock.is_restock_pipeline is False

    @pytest.mark.parametrize("coming_soon_text", [
        "به‌زودی",           # ZWNJ (\u200c)
        "به زودی",           # Standard space
        "بهزودی",            # Compact
        "وضعیت: به‌زودی",    # With prefix
    ])
    def test_lion_coming_soon_is_blocked(self, coming_soon_text):
        """'به‌زودی' in status must BLOCK and set is_restock_pipeline=True."""
        html = f"""
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> {coming_soon_text} </span>
                <button class="btn-buy">خرید آنلاین</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "به‌زودی" in details.raw_status_text or "به زودی" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False
        assert stock.is_restock_pipeline is True

    @pytest.mark.parametrize("oos_text", [
        "اتمام موجودی",
        "ناموجود",
        "عدم موجودی",
        "تمام شد",
    ])
    def test_lion_out_of_stock_is_blocked(self, oos_text):
        """'اتمام موجودی' must BLOCK."""
        html = f"""
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> {oos_text} </span>
                <button class="btn-buy">خرید آنلاین</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert details.stock_quantity == 0

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False
        assert stock.is_restock_pipeline is False

    def test_lion_unidentified_status_is_blocked_fail_closed(self):
        """Missing or ambiguous status markers must BLOCK (Fail-Closed)."""
        html = """
        <html><body>
            <div class="product-detail">
                <p>توضیحات کلی محصول بدون هیچ بخش موجودی</p>
                <button class="btn-buy">خرید</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "Fail-Closed" in details.raw_status_text or "وضعیت نامشخص" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False

    def test_lion_inquiry_only_is_blocked(self):
        """Inquiry button present must BLOCK purchase."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> استعلام قیمت </span>
                <button class="add-inquiry">استعلام</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert details.is_inquiry_only is True

    def test_lion_js_can_order_false_is_blocked(self):
        """window.productCanOrder == False must BLOCK even if digits present."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> 50 </span>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html, can_order_js=False)
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        details = adapter.inspect_product(ref)
        assert details.can_order is False

    def test_lion_add_to_cart_raises_on_blocked_product(self):
        """Calling add_to_cart on a blocked Lion product must raise OutOfStockError."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="stock-amount"> به‌زودی </span>
            </div>
        </body></html>
        """
        adapter = self._create_mock_lion_adapter(html)
        adapter.validate_session = MagicMock(return_value=SessionStatus(vendor_id="vendor_lion", is_authenticated=True))
        ref = ProductReference(vendor_id="vendor_lion", vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")

        with pytest.raises(OutOfStockError) as exc_info:
            adapter.add_to_cart(ref, 10)
        assert "cannot be ordered" in str(exc_info.value) or "Lion product" in str(exc_info.value)


# ============================================================================
# 2. JAVAN ELECTRONIC STOREFRONT AVAILABILITY GATE TESTS
# ============================================================================

class TestJavanAvailabilityGate:
    """Verifies fail-closed product-status rules for Javan Electronic."""

    def _create_mock_javan_adapter(self, html: str):
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.title = "Javan Electronic Product"
        mock_driver.page_source = html
        mock_driver.current_url = "https://www.javanelec.com/shop/product/17930/ti/ne555p"

        adapter.session.get_driver = MagicMock(return_value=mock_driver)
        adapter.session.execute_script = MagicMock(return_value=None)
        adapter.session.wait_for_settle = MagicMock()
        return adapter

    def test_javan_explicitly_available_is_allowed(self):
        """Explicit 'موجود در انبار' badge with add-to-cart button -> ALLOW."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="badge badge-success product-status"> موجود در انبار </span>
                <form action="/shoppingcarts/createindex" method="post">
                    <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
                </form>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is True
        assert details.stock_quantity > 0
        assert "موجود در انبار" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is True
        assert stock.can_order is True

    @pytest.mark.parametrize("status_html", [
        '<span class="badge badge-warning product-status">تأمین</span>',
        '<span class="badge badge-warning product-status">تامین</span>',
        '<div class="stock-status">وضعیت: تأمین</div>',
        '<p class="status">تأمین - درخواست از تامین کننده خارجی</p>',
    ])
    def test_javan_tamim_is_blocked(self, status_html):
        """'تأمین' status must BLOCK."""
        html = f"""
        <html><body>
            <div class="product-detail">
                {status_html}
                <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "تأمین" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False

    @pytest.mark.parametrize("status_html", [
        '<span class="badge badge-danger product-status">اتمام</span>',
        '<div class="stock-status">وضعیت: اتمام</div>',
        '<span class="badge badge-danger product-status">اتمام موجودی</span>',
    ])
    def test_javan_etmam_is_blocked(self, status_html):
        """'اتمام' status must BLOCK."""
        html = f"""
        <html><body>
            <div class="product-detail">
                {status_html}
                <button type="submit" class="btn btn-success-outline">ثبت سفارش</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "اتمام" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False

    @pytest.mark.parametrize("order_later_text", [
        "ناموجود-سفارش دهید",
        "ناموجود - سفارش دهید",
        "ناموجود سفارش دهید",
        "ناموجود-سفارش دهید (زمان تحویل: ۲ تا ۳ هفته)",
        "ناموجود - زمان تحویل: ۱۰ روز کاری",
    ])
    def test_javan_order_later_with_lead_time_is_blocked(self, order_later_text):
        """'ناموجود-سفارش دهید' with lead times or delivery estimates must BLOCK."""
        html = f"""
        <html><body>
            <div class="product-detail">
                <span class="badge badge-danger product-status">{order_later_text}</span>
                <span class="lead-time">مدت زمان تحویل: ۲ هفته کاری</span>
                <button type="submit" class="btn btn-success-outline">ثبت سفارش کالا</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "ناموجود" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False

    def test_javan_button_and_lead_time_do_not_override_prohibited_status(self):
        """A visible order button or delivery estimate MUST NOT override a prohibited status."""
        html = """
        <html><body>
            <div class="product-detail">
                <div class="status-badge">تأمین</div>
                <div class="lead-time">تحویل ۳ تا ۴ هفته</div>
                <button type="submit" class="btn btn-success-outline">سفارش دهید</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "تأمین" in details.raw_status_text

    def test_javan_supplier_name_containing_tamim_not_falsely_blocked(self):
        """Page text containing 'تأمین کننده' (supplier) must not falsely trigger 'تأمین' status block."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="badge badge-success product-status">موجود در انبار</span>
                <div class="specs">تأمین کننده: شرکت البرز الکترونیک</div>
                <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is True
        assert "موجود در انبار" in details.raw_status_text

    def test_javan_unidentified_status_is_blocked_fail_closed(self):
        """If Javan storefront status cannot be reliably identified, fail closed -> BLOCK."""
        html = """
        <html><body>
            <div class="product-detail">
                <h1>NE555P</h1>
                <p>توضیحات کلی محصول بدون هیچ نشانگر موجودی یا انبار</p>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        details = adapter.inspect_product(ref)
        assert details.can_order is False
        assert "Status Unidentified" in details.raw_status_text or "وضعیت نامشخص" in details.raw_status_text

        stock = adapter.inspect_stock(ref)
        assert stock.in_stock is False
        assert stock.can_order is False

    def test_javan_add_to_cart_raises_on_blocked_product(self):
        """Calling add_to_cart on a blocked Javan product must raise OutOfStockError."""
        html = """
        <html><body>
            <div class="product-detail">
                <span class="product-status">تأمین</span>
            </div>
        </body></html>
        """
        adapter = self._create_mock_javan_adapter(html)
        adapter.validate_session = MagicMock(return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=True))
        ref = ProductReference(vendor_id="vendor_javan", vendor_sku="17930", pdp_url="https://www.javanelec.com/shop/product/17930/ti/ne555p")

        with pytest.raises(OutOfStockError) as exc_info:
            adapter.add_to_cart(ref, 50)
        assert "cannot be ordered" in str(exc_info.value) or "Javan product" in str(exc_info.value)


# ============================================================================
# 3. DUAL-PATH INTEGRATION TESTS (PATH A & PATH B)
# ============================================================================

class TestDualPathSupplierAvailabilityGate:
    """Verifies that blocked products never reach add_to_cart across Path A and Path B."""

    def _setup_mock_registry(self, lion_html: str, javan_html: str):
        class ConfiguredLionAdapter(LionVendorAdapter):
            mock_cart = MagicMock()

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                mock_driver = MagicMock()
                mock_driver.title = "Lion PDP"
                mock_driver.page_source = lion_html
                mock_driver.current_url = "https://lionelectronic.ir/products/2070-NE555P"
                mock_driver.execute_script = MagicMock(return_value=None)
                self.session.get_driver = MagicMock(return_value=mock_driver)
                self.session.execute_script = MagicMock(return_value=None)
                self.session.wait_for_settle = MagicMock()

            def add_to_cart(self, product_ref, quantity):
                ConfiguredLionAdapter.mock_cart(product_ref, quantity)
                return super().add_to_cart(product_ref, quantity)

        class ConfiguredJavanAdapter(JavanVendorAdapter):
            mock_cart = MagicMock()

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                mock_driver = MagicMock()
                mock_driver.title = "Javan PDP"
                mock_driver.page_source = javan_html
                mock_driver.current_url = "https://www.javanelec.com/shop/product/17930/ti/ne555p"
                mock_driver.execute_script = MagicMock(return_value=None)
                self.session.get_driver = MagicMock(return_value=mock_driver)
                self.session.execute_script = MagicMock(return_value=None)
                self.session.wait_for_settle = MagicMock()

            def add_to_cart(self, product_ref, quantity):
                ConfiguredJavanAdapter.mock_cart(product_ref, quantity)
                return super().add_to_cart(product_ref, quantity)

        ConfiguredLionAdapter.mock_cart.reset_mock()
        ConfiguredJavanAdapter.mock_cart.reset_mock()

        reg = VendorRegistry()
        reg.register_adapter(
            vendor_id="vendor_lion",
            adapter_class=ConfiguredLionAdapter,
            domains=["lionelectronic.ir"],
            display_name="Lion Electronic",
            enabled=True,
            activate=True,
        )
        reg.register_adapter(
            vendor_id="vendor_javan",
            adapter_class=ConfiguredJavanAdapter,
            domains=["javanelec.com"],
            display_name="Javan Electronic",
            enabled=True,
            activate=True,
        )
        return reg, ConfiguredLionAdapter, ConfiguredJavanAdapter

    # ------------------------------------------------------------------------
    # Path A: Stock Shortages / Replenishment
    # ------------------------------------------------------------------------

    def test_path_a_eligible_lion_link_proceeds(self):
        """Path A: Eligible Lion link allows procurement staging."""
        lion_html = """
        <html><body>
            <span class="stock-amount"> 500 </span>
            <input id="quantity-cell" value="10" />
            <div class="product-price"> 50,000 ریال </div>
        </body></html>
        """
        javan_html = "<html><body></body></html>"
        reg, lion_cls, _ = self._setup_mock_registry(lion_html, javan_html)

        with patch.object(lion_cls, "add_to_cart", return_value=CartMutationResult(
            vendor_id="vendor_lion",
            vendor_sku="2070-NE555P",
            requested_quantity=10,
            actual_quantity_staged=10,
            success=True,
            raw_vendor_message="Added to cart",
        )) as mock_cart:
            item = {
                "part_number": "NE555P",
                "needed_qty": 10,
                "link": "https://lionelectronic.ir/products/2070-NE555P",
                "mode": ProcurementMode.DATABASE_AWARE,
            }

            res = ProcurementBridge.execute_staged_procurement_batch([item], registry=reg)
            assert res["success"] is True
            assert res["successful_count"] == 1
            assert res["failed_count"] == 0
            mock_cart.assert_called_once()

    def test_path_a_blocked_lion_link_fails_closed_before_cart(self):
        """Path A: Lion 'به‌زودی' link blocks candidate evaluation; add_to_cart is NEVER called."""
        lion_html = """
        <html><body>
            <span class="stock-amount"> به‌زودی </span>
        </body></html>
        """
        javan_html = "<html><body></body></html>"
        reg, lion_cls, _ = self._setup_mock_registry(lion_html, javan_html)

        item = {
            "part_number": "NE555P",
            "needed_qty": 10,
            "link": "https://lionelectronic.ir/products/2070-NE555P",
            "mode": ProcurementMode.DATABASE_AWARE,
        }

        res = ProcurementBridge.execute_staged_procurement_batch([item], registry=reg)
        assert res["success"] is False
        assert res["failed_count"] == 1
        assert res["successful_count"] == 0
        # CRITICAL: add_to_cart must never be touched
        lion_cls.mock_cart.assert_not_called()
        assert "out of stock" in item["order_message"].lower() or "unorderable" in item["order_message"].lower()

    def test_path_a_blocked_javan_link_fails_closed_before_cart(self):
        """Path A: Javan 'تأمین' link blocks candidate evaluation; add_to_cart is NEVER called."""
        lion_html = "<html><body></body></html>"
        javan_html = """
        <html><body>
            <span class="badge product-status">تأمین</span>
            <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
        </body></html>
        """
        reg, _, javan_cls = self._setup_mock_registry(lion_html, javan_html)

        item = {
            "part_number": "NE555P",
            "needed_qty": 50,
            "link": "https://www.javanelec.com/shop/product/17930/ti/ne555p",
            "mode": ProcurementMode.DATABASE_AWARE,
        }

        res = ProcurementBridge.execute_staged_procurement_batch([item], registry=reg)
        assert res["success"] is False
        assert res["failed_count"] == 1
        assert res["successful_count"] == 0
        javan_cls.mock_cart.assert_not_called()

    # ------------------------------------------------------------------------
    # Path B: Altium BOM Procurement
    # ------------------------------------------------------------------------

    def test_path_b_eligible_javan_bom_item_proceeds(self):
        """Path B: BOM item with eligible Javan link allows procurement staging."""
        lion_html = "<html><body></body></html>"
        javan_html = """
        <html><body>
            <h1 class="font-weight-bold">NE555P | Texas Instruments</h1>
            <span class="badge badge-success product-status">موجود در انبار</span>
            <form action="/shoppingcarts/createindex" method="post">
                <button type="submit" class="btn btn-success-outline">اضافه به سبد خرید</button>
            </form>
            <table>
                <tr><td>10 عدد</td><td>18,000 ریال</td></tr>
            </table>
        </body></html>
        """
        reg, _, javan_cls = self._setup_mock_registry(lion_html, javan_html)

        with patch.object(javan_cls, "add_to_cart", return_value=CartMutationResult(
            vendor_id="vendor_javan",
            vendor_sku="17930",
            requested_quantity=20,
            actual_quantity_staged=20,
            success=True,
            raw_vendor_message="Item added to cart",
        )) as mock_cart:
            bom_item = {
                "part_number": "NE555P",
                "needed_qty": 20,
                "link": "https://www.javanelec.com/shop/product/17930/ti/ne555p",
                "selected_vendor_id": "vendor_javan",
                "mode": ProcurementMode.DATABASE_AWARE,
            }

            res = ProcurementBridge.execute_staged_procurement_batch([bom_item], registry=reg)
            assert res["success"] is True
            assert res["successful_count"] == 1
            mock_cart.assert_called_once()

    def test_path_b_blocked_javan_order_later_fails_closed_before_cart(self):
        """Path B: BOM item with 'ناموجود-سفارش دهید' blocks; add_to_cart is NEVER called."""
        lion_html = "<html><body></body></html>"
        javan_html = """
        <html><body>
            <span class="badge product-status">ناموجود-سفارش دهید</span>
            <span class="lead-time">تحویل ۳ هفته</span>
            <button type="submit" class="btn btn-success-outline">ثبت سفارش</button>
        </body></html>
        """
        reg, _, javan_cls = self._setup_mock_registry(lion_html, javan_html)

        bom_item = {
            "part_number": "NE555P",
            "needed_qty": 20,
            "link": "https://www.javanelec.com/shop/product/17930/ti/ne555p",
            "selected_vendor_id": "vendor_javan",
            "mode": ProcurementMode.DATABASE_AWARE,
        }

        res = ProcurementBridge.execute_staged_procurement_batch([bom_item], registry=reg)
        assert res["success"] is False
        assert res["failed_count"] == 1
        javan_cls.mock_cart.assert_not_called()

    # ------------------------------------------------------------------------
    # Multi-Vendor Selection & No Silent Fallback
    # ------------------------------------------------------------------------

    def test_multi_vendor_selection_of_blocked_vendor_fails_without_silent_fallback(self):
        """
        When user explicitly selects Lion from a multi-link item, but Lion is 'به‌زودی',
        procurement MUST FAIL CLOSED. It must NOT silently fall back to Javan.
        """
        lion_html = """
        <html><body>
            <span class="stock-amount"> به‌زودی </span>
        </body></html>
        """
        javan_html = """
        <html><body>
            <span class="badge product-status">موجود در انبار</span>
            <button type="submit" class="btn btn-success-outline">خرید</button>
        </body></html>
        """
        reg, lion_cls, javan_cls = self._setup_mock_registry(lion_html, javan_html)

        # Item has both links, but user selected Lion
        item = {
            "part_number": "NE555P",
            "needed_qty": 10,
            "selected_vendor_id": "vendor_lion",
            "selected_url": "https://lionelectronic.ir/products/2070-NE555P",
            "link": "https://lionelectronic.ir/products/2070-NE555P",
            "vendor_links": {
                "vendor_lion": "https://lionelectronic.ir/products/2070-NE555P",
                "vendor_javan": "https://www.javanelec.com/shop/product/17930/ti/ne555p",
            },
            "mode": ProcurementMode.DATABASE_AWARE,
        }

        res = ProcurementBridge.execute_staged_procurement_batch([item], registry=reg)
        assert res["success"] is False
        assert res["failed_count"] == 1
        # Neither adapter was called for cart mutation!
        lion_cls.mock_cart.assert_not_called()
        javan_cls.mock_cart.assert_not_called()

    def test_transport_network_error_fails_closed_before_cart(self):
        """TransportNetworkError during inspection fails closed and never calls add_to_cart."""
        lion_html = "<html><body></body></html>"
        javan_html = "<html><body></body></html>"
        reg, lion_cls, _ = self._setup_mock_registry(lion_html, javan_html)

        with patch.object(lion_cls, "inspect_product", side_effect=TransportNetworkError("Connection timed out")):
            item = {
                "part_number": "NE555P",
                "needed_qty": 10,
                "link": "https://lionelectronic.ir/products/2070-NE555P",
                "mode": ProcurementMode.DATABASE_AWARE,
            }

            res = ProcurementBridge.execute_staged_procurement_batch([item], registry=reg)
            assert res["success"] is False
            assert res["failed_count"] == 1
            lion_cls.mock_cart.assert_not_called()

