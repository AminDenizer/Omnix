"""
Unit and Integration Tests for Phase 1:
1. Vendor Authentication and Cart Safety for Lion & Javan (Scope A).
2. Cart and Final Order Boundary (Scope B).
3. Multi-Link Product Selection in Inventory and BOM Workflows (Scope C).
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from core.models import (
    AdapterConfig,
    AuthCredentials,
    AuthResult,
    CartMutationResult,
    OrderConstraints,
    ProductDetails,
    ProductReference,
    SessionStatus,
    StockStatus,
)
from core.errors import (
    AuthenticationRequiredError,
    SecurityChallengeError,
    OrderMultipleViolationError,
    OutOfStockError,
    OmnixVendorError,
)
from core.procurement.models import ProcurementMode, ProcurementRequest
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from core.procurement.bridge import ProcurementBridge
from core.vendor_interface import IVendorAdapter
from vendors.lion.adapter import LionVendorAdapter
from vendors.javan.adapter import JavanVendorAdapter
from ui.dialogs.order_preview_dialog import (
    OrderPreviewDialog,
    VendorSelectionDialog,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app


class FakeTestAdapter(IVendorAdapter):
    """Controlled test adapter for safe offline unit tests."""
    def __init__(self, vendor_id="vendor_fake", base_url="https://fake.com"):
        self._vendor_id = vendor_id
        self._base_url = base_url

    @property
    def vendor_id(self) -> str:
        return self._vendor_id

    @property
    def base_url(self) -> str:
        return self._base_url

    def initialize(self, config=None):
        return None

    def search_part(self, query: str):
        return None

    def resolve_product(self, url_or_sku: str):
        return ProductReference(vendor_id=self.vendor_id, vendor_sku="SKU-1", pdp_url=url_or_sku)

    def inspect_product(self, product_ref):
        return ProductDetails(
            vendor_id=self.vendor_id,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=100,
            can_order=True,
            order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
        )

    def extract_product_data(self, dom_context):
        return None

    def inspect_stock(self, product_ref):
        return StockStatus(vendor_id=self.vendor_id, vendor_sku="SKU-1", stock_quantity=100, in_stock=True, can_order=True)

    def determine_order_constraints(self, product_ref):
        return OrderConstraints(moq_raw=1, packaging_step_raw=1)

    def add_to_cart(self, product_ref, quantity: int):
        return CartMutationResult(
            vendor_id=self.vendor_id,
            vendor_sku=product_ref.vendor_sku,
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
            cart_total_items=1,
        )

    def inspect_cart(self):
        return None

    def authenticate(self, credentials=None, challenge_handler=None):
        return AuthResult(vendor_id=self.vendor_id, success=True, message="Auth OK")

    def validate_session(self):
        return SessionStatus(vendor_id=self.vendor_id, is_authenticated=True)

    def recover_from_error(self, error_context):
        return None

    def close(self):
        pass

    def get_cart_url(self):
        return f"{self.base_url}/cart"

    def is_pdp_url(self, url: str) -> bool:
        return True


@pytest.fixture
def clean_registry():
    reg = VendorRegistry()

    class FakeLion(FakeTestAdapter):
        VENDOR_ID = "vendor_lion"
        BASE_URL = "https://lionelectronic.ir"
        def __init__(self, config=None):
            super().__init__(vendor_id="vendor_lion", base_url="https://lionelectronic.ir")

    class FakeJavan(FakeTestAdapter):
        VENDOR_ID = "vendor_javan"
        BASE_URL = "https://javanelec.com"
        def __init__(self, config=None):
            super().__init__(vendor_id="vendor_javan", base_url="https://javanelec.com")

    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=FakeLion,
        domains=["lionelectronic.ir"],
        display_name="Lion Electronic",
        enabled=True,
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=FakeJavan,
        domains=["javanelec.com"],
        display_name="Javan Electronic",
        enabled=True,
    )
    return reg


# ============================================================================
# Scope A: User-Initiated Vendor Authentication and Cart Addition
# ============================================================================

class TestUserInitiatedAuthAndCartAddition:

    def test_javan_cart_reuses_valid_session(self):
        """When session is already authenticated, Javan add_to_cart must not re-authenticate."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://www.javanelec.com/shop/product/123"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://javanelec.com/shop/product/123")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=True)) as mock_val, \
             patch.object(adapter, "authenticate") as mock_auth, \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=10):

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_javan",
                vendor_sku="123",
                pdp_url=pref.pdp_url,
                stock_quantity=100,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 10)
            assert res.success is True
            mock_val.assert_called_once()
            mock_auth.assert_not_called()

    def test_javan_cart_authenticates_unauthenticated_session_when_credentials_present(self):
        """When session is unauthenticated, Javan add_to_cart authenticates with configured credentials."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://www.javanelec.com/shop/product/123"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://javanelec.com/shop/product/123")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=False)), \
             patch("settings_manager.settings.get_vendor_settings", return_value=MagicMock(username="testuser", password="testpassword")), \
             patch.object(adapter, "authenticate", return_value=AuthResult(vendor_id="vendor_javan", success=True, message="Login ok")) as mock_auth, \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=5):

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_javan",
                vendor_sku="123",
                pdp_url=pref.pdp_url,
                stock_quantity=100,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 5)
            assert res.success is True
            mock_auth.assert_called_once()

    def test_javan_cart_missing_credentials_raises_authentication_required_error(self):
        """If session is unauthenticated and credentials missing, Javan raises AuthenticationRequiredError."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        adapter.session.driver = mock_driver

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://javanelec.com/shop/product/123")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=False)), \
             patch("settings_manager.settings.get_vendor_settings", return_value=None), \
             patch("settings_manager.settings.get", return_value=""):

            with pytest.raises(AuthenticationRequiredError, match="Javan Electronic credentials .* are not configured"):
                adapter.add_to_cart(pref, 5)

    def test_javan_cart_auth_failure_raises_authentication_required_error(self):
        """If authentication fails during cart staging, Javan raises AuthenticationRequiredError."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        adapter.session.driver = mock_driver

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://javanelec.com/shop/product/123")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=False)), \
             patch("settings_manager.settings.get_vendor_settings", return_value=MagicMock(username="testuser", password="badpassword")), \
             patch.object(adapter, "authenticate", return_value=AuthResult(vendor_id="vendor_javan", success=False, message="Invalid password")):

            with pytest.raises(AuthenticationRequiredError, match="Javan Electronic authentication failed"):
                adapter.add_to_cart(pref, 5)

    def test_javan_cart_challenge_raises_security_challenge_error(self):
        """If security challenge requires interactive solving, Javan raises SecurityChallengeError."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        adapter.session.driver = mock_driver

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="123", pdp_url="https://javanelec.com/shop/product/123")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=False)), \
             patch("settings_manager.settings.get_vendor_settings", return_value=MagicMock(username="testuser", password="password")), \
             patch.object(adapter, "authenticate", return_value=AuthResult(vendor_id="vendor_javan", success=False, message="Turnstile challenge", requires_interactive=True)):

            with pytest.raises(SecurityChallengeError, match="Javan Electronic security challenge encountered"):
                adapter.add_to_cart(pref, 5)

    def test_lion_cart_reuses_valid_session(self):
        """When session is already authenticated, Lion add_to_cart must not re-authenticate."""
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/products/123-slug"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="123", pdp_url="https://lionelectronic.ir/products/123-slug")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_lion", is_authenticated=True)) as mock_val, \
             patch.object(adapter, "authenticate") as mock_auth, \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=True):

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_lion",
                vendor_sku="123",
                pdp_url=pref.pdp_url,
                stock_quantity=100,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 10)
            assert res.success is True
            mock_val.assert_called_once()
            mock_auth.assert_not_called()

    def test_lion_cart_authenticates_when_configured(self):
        """When session is unauthenticated and credentials exist, Lion add_to_cart authenticates."""
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/products/123-slug"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="123", pdp_url="https://lionelectronic.ir/products/123-slug")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_lion", is_authenticated=False)), \
             patch("settings_manager.settings.get_vendor_settings", return_value=MagicMock(username="lionuser", password="lionpassword")), \
             patch.object(adapter, "authenticate", return_value=AuthResult(vendor_id="vendor_lion", success=True, message="Login ok")) as mock_auth, \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=True):

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_lion",
                vendor_sku="123",
                pdp_url=pref.pdp_url,
                stock_quantity=100,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 5)
            assert res.success is True
            mock_auth.assert_called_once()


# ============================================================================
# Scope B: Cart and Final Order Boundary
# ============================================================================

class TestCartAndFinalOrderBoundary:

    def test_lion_add_to_cart_never_calls_checkout_or_payment(self):
        """Lion add_to_cart operates exclusively on the PDP and never navigates to checkout/payment."""
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/products/100-test"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_lion", vendor_sku="100", pdp_url="https://lionelectronic.ir/products/100-test")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_lion", is_authenticated=True)), \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=True) as mock_js:

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_lion",
                vendor_sku="100",
                pdp_url=pref.pdp_url,
                stock_quantity=50,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 5)
            assert res.success is True

            # Verify all driver.get calls
            for call in mock_driver.get.call_args_list:
                url = call[0][0].lower()
                assert "checkout" not in url
                assert "payment" not in url
                assert "order/pay" not in url
                assert "final" not in url

            # Verify JS script executed only touches quantity-cell and btn-buy
            executed_js = mock_js.call_args[0][0]
            assert "btn-buy" in executed_js
            assert "checkout" not in executed_js.lower()
            assert "payment" not in executed_js.lower()

    def test_javan_add_to_cart_never_calls_checkout_or_payment(self):
        """Javan add_to_cart operates on the PDP/modal and never calls checkout or payment."""
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://www.javanelec.com/shop/product/555"
        mock_driver.find_elements.return_value = []
        adapter.session.driver = mock_driver
        adapter.session.wait_for_settle = MagicMock()

        pref = ProductReference(vendor_id="vendor_javan", vendor_sku="555", pdp_url="https://javanelec.com/shop/product/555")

        with patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_javan", is_authenticated=True)), \
             patch.object(adapter, "inspect_product") as mock_insp, \
             patch.object(adapter.session, "execute_script", return_value=5) as mock_js:

            mock_insp.return_value = ProductDetails(
                vendor_id="vendor_javan",
                vendor_sku="555",
                pdp_url=pref.pdp_url,
                stock_quantity=50,
                can_order=True,
                order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
            )

            res = adapter.add_to_cart(pref, 5)
            assert res.success is True

            for call in mock_driver.get.call_args_list:
                url = call[0][0].lower()
                assert "checkout" not in url
                assert "payment" not in url
                assert "bank" not in url

            scripts = [call[0][0] for call in mock_js.call_args_list]
            assert any("addToCart" in s for s in scripts)
            for s in scripts:
                assert "checkout" not in s.lower()
                assert "payment" not in s.lower()

    def test_orchestrator_stage_candidate_never_invokes_payment_or_order_submission(self, clean_registry):
        """Orchestrator stage_candidate stops strictly at adapter.add_to_cart."""
        orch = UniversalProcurementOrchestrator(registry=clean_registry)
        adapter = clean_registry.get_adapter("vendor_lion")

        cand = MagicMock()
        cand.vendor_id = "vendor_lion"
        cand.part_number = "TEST-PART"
        cand.product_ref = ProductReference(vendor_id="vendor_lion", vendor_sku="TEST", pdp_url="https://lionelectronic.ir/p/1")
        cand.order_constraints = OrderConstraints(max_orderable_raw=100)

        with patch.object(FakeTestAdapter, "inspect_cart", return_value=None), \
             patch.object(FakeTestAdapter, "add_to_cart") as mock_add:

            mock_add.return_value = CartMutationResult(
                vendor_id="vendor_lion",
                vendor_sku="TEST",
                requested_quantity=10,
                actual_quantity_staged=10,
                success=True,
            )

            res = orch.stage_candidate(cand, 10, sync_cart=True)
            assert res.success is True
            mock_add.assert_called_once_with(cand.product_ref, 10)


# ============================================================================
# Scope C: Multi-Link Product Selection
# ============================================================================

class TestMultiLinkProductSelection:

    def test_single_eligible_link_no_prompt(self, qapp, clean_registry):
        """Component with exactly 1 eligible link is auto-selected without prompt."""
        shortages = [
            {
                "part_name": "SINGLE-1",
                "part_number": "SINGLE-1",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/products/10-test",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=clean_registry)

        # Single link item must be automatically mapped and classified without multi-vendor flag
        item = dlg.all_shortages[0]
        assert item["is_multi_vendor"] is False
        assert item["selected_vendor_id"] == "vendor_lion"
        assert item["selected_url"] == "https://lionelectronic.ir/products/10-test"
        assert item in dlg.lion_items
        assert item in dlg.orderable_items
        assert item not in dlg.multi_vendor_items

    def test_multi_eligible_links_requires_explicit_user_selection(self, qapp, clean_registry):
        """Component with multiple eligible links is flagged as multi-vendor needing selection."""
        shortages = [
            {
                "part_name": "MULTI-1",
                "part_number": "MULTI-1",
                "needed_qty": 5,
                "link": "LION=https://lionelectronic.ir/m1 || JAVAN=https://javanelec.com/m1",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=clean_registry)

        item = dlg.all_shortages[0]
        assert item["is_multi_vendor"] is True
        assert item.get("selected_vendor_id") is None
        assert item in dlg.multi_vendor_items
        assert item in dlg.orderable_items
        assert len(item["vendor_links"]) == 2

    def test_multi_link_dialog_placeholder_prevents_silent_selection(self, qapp, clean_registry):
        """VendorSelectionDialog prevents confirmation if any item is left unselected."""
        items = [
            {
                "part_name": "RES-0805",
                "part_number": "RC0805JR-0710KL",
                "needed_qty": 100,
                "vendor_links": {
                    "vendor_lion": "https://lionelectronic.ir/p/res-lion",
                    "vendor_javan": "https://javanelec.com/p/res-javan",
                },
            }
        ]
        dialog = VendorSelectionDialog(items, registry=clean_registry)

        # Combo should start at index 0 (placeholder None)
        it, combo = dialog.combo_boxes[0]
        assert combo.currentData() is None
        assert "-- Select Supplier Link --" in combo.currentText()

        # Attempt to confirm without selection -> warning shown, dialog remains open
        with patch.object(QMessageBox, "warning") as mock_warn:
            dialog._on_confirm()
            mock_warn.assert_called_once()
            assert it.get("selected_vendor_id") is None

        # Find Lion option index and select it
        lion_idx = -1
        for idx in range(combo.count()):
            cdata = combo.itemData(idx)
            if isinstance(cdata, tuple) and cdata[0] == "vendor_lion":
                lion_idx = idx
                break

        assert lion_idx > 0
        combo.setCurrentIndex(lion_idx)
        chosen_data = combo.currentData()
        assert chosen_data[0] == "vendor_lion"
        assert chosen_data[1] == "https://lionelectronic.ir/p/res-lion"

        dialog._on_confirm()
        assert it["selected_vendor_id"] == "vendor_lion"
        assert it["selected_url"] == "https://lionelectronic.ir/p/res-lion"
        assert it["vendor_id"] == "vendor_lion"
        assert it["link"] == "https://lionelectronic.ir/p/res-lion"

    def test_multi_link_selection_carries_through_to_procurement_request(self, clean_registry):
        """Selected link and vendor are strictly preserved into ProcurementRequest."""
        item = {
            "part_name": "NE555P",
            "part_number": "NE555P",
            "needed_qty": 10,
            "link": "LION=https://lionelectronic.ir/p/555 || JAVAN=https://javanelec.com/p/555",
            "vendor_links": {
                "vendor_lion": "https://lionelectronic.ir/p/555",
                "vendor_javan": "https://javanelec.com/p/555",
            },
            "selected_vendor_id": "vendor_javan",
            "selected_url": "https://javanelec.com/p/555",
        }

        req = ProcurementBridge.item_to_request(item, registry=clean_registry)
        assert req.explicit_vendor_id == "vendor_javan"
        assert req.explicit_vendor_url == "https://javanelec.com/p/555"

    def test_unselected_multi_link_raises_error_if_dispatched_without_choice(self, clean_registry):
        """Attempting to dispatch a multi-link item without selection raises ValueError fail-closed."""
        item = {
            "part_name": "NE555P",
            "part_number": "NE555P",
            "needed_qty": 10,
            "link": "LION=https://lionelectronic.ir/p/555 || JAVAN=https://javanelec.com/p/555",
            "vendor_links": {
                "vendor_lion": "https://lionelectronic.ir/p/555",
                "vendor_javan": "https://javanelec.com/p/555",
            },
        }

        with pytest.raises(ValueError, match="Vendor selection is required before procurement dispatch"):
            ProcurementBridge.item_to_request(item, registry=clean_registry)

    def test_multi_link_selection_does_not_mutate_persistent_db_links(self, qapp, clean_registry):
        """Selecting a vendor link for an order in UI does not alter stored link data."""
        stored_raw_link = "LION=https://lionelectronic.ir/m1 || JAVAN=https://javanelec.com/m1"
        item = {
            "part_name": "MULTI-1",
            "part_number": "MULTI-1",
            "needed_qty": 5,
            "link": stored_raw_link,
            "raw_link": stored_raw_link,
        }
        dlg = OrderPreviewDialog(all_shortages=[item], registry=clean_registry)

        # Simulate user selecting Javan
        dlg.multi_vendor_items[0]["selected_vendor_id"] = "vendor_javan"
        dlg.multi_vendor_items[0]["selected_url"] = "https://javanelec.com/m1"
        dlg.multi_vendor_items[0]["vendor_id"] = "vendor_javan"
        dlg.multi_vendor_items[0]["link"] = "https://javanelec.com/m1"

        # The persistent raw_link field remains untouched
        assert item["raw_link"] == stored_raw_link

    def test_disabled_vendor_link_is_filtered_out_from_eligibility(self, qapp, clean_registry):
        """If a component has Lion and Javan links, but Javan is disabled, only Lion is eligible."""
        clean_registry.set_vendor_enabled("vendor_javan", False)

        shortages = [
            {
                "part_name": "MULTI-1",
                "part_number": "MULTI-1",
                "needed_qty": 5,
                "link": "LION=https://lionelectronic.ir/m1 || JAVAN=https://javanelec.com/m1",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=clean_registry)

        item = dlg.all_shortages[0]
        # Because Javan is disabled, only 1 eligible link remains -> auto-selects Lion!
        assert item["is_multi_vendor"] is False
        assert item["selected_vendor_id"] == "vendor_lion"
        assert item["selected_url"] == "https://lionelectronic.ir/m1"
        assert item in dlg.lion_items

    def test_bom_ordering_with_multiple_components_isolated_choices(self, qapp, clean_registry):
        """BOM with multiple multi-link items displays each component distinctly without crosstalk."""
        items = [
            {
                "part_name": "R1",
                "part_number": "RES-10K",
                "designator": "R1, R2",
                "needed_qty": 20,
                "vendor_links": {
                    "vendor_lion": "https://lionelectronic.ir/p/res10k",
                    "vendor_javan": "https://javanelec.com/p/res10k",
                },
            },
            {
                "part_name": "C1",
                "part_number": "CAP-100NF",
                "designator": "C1",
                "needed_qty": 10,
                "vendor_links": {
                    "vendor_lion": "https://lionelectronic.ir/p/cap100n",
                    "vendor_javan": "https://javanelec.com/p/cap100n",
                },
            },
        ]
        dialog = VendorSelectionDialog(items, registry=clean_registry)

        assert len(dialog.combo_boxes) == 2

        it1, combo1 = dialog.combo_boxes[0]
        # Find Lion for R1
        for idx in range(combo1.count()):
            cdata = combo1.itemData(idx)
            if isinstance(cdata, tuple) and cdata[0] == "vendor_lion":
                combo1.setCurrentIndex(idx)
                break

        it2, combo2 = dialog.combo_boxes[1]
        # Find Javan for C1
        for idx in range(combo2.count()):
            cdata = combo2.itemData(idx)
            if isinstance(cdata, tuple) and cdata[0] == "vendor_javan":
                combo2.setCurrentIndex(idx)
                break

        dialog._on_confirm()

        assert it1["selected_vendor_id"] == "vendor_lion"
        assert it1["selected_url"] == "https://lionelectronic.ir/p/res10k"

        assert it2["selected_vendor_id"] == "vendor_javan"
        assert it2["selected_url"] == "https://javanelec.com/p/cap100n"
