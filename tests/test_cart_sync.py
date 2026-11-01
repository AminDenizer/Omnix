"""
Unit and Integration Tests for TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization (GAP-13)
Governing Document: docs/PRODUCT/MASTER_IMPLEMENTATION_ROADMAP.md (TASK-A4)
"""

import pytest
from typing import Optional, Dict, Any, List

from core.models import (
    CartItem,
    CartDetails,
    CartMutationResult,
    IdentityMatchTier,
    ProductReference,
    OrderConstraints,
)
from core.procurement.models import (
    calculate_effective_quantity,
    VendorProcurementCandidate,
    ProcurementRequest,
    BOMProcurementPlan,
    CandidateEvaluation,
    RequestProcurementResult,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from core.procurement.bridge import ProcurementBridge
from core.vendor_interface import IVendorAdapter
from core.errors import OmnixVendorError, TransportNetworkError


class MockCartVendorAdapter(IVendorAdapter):
    """Configurable mock adapter for cart idempotency testing."""

    def __init__(self, vendor_id: str = "vendor_lion", base_url: str = "https://lionelectronic.ir"):
        self._vendor_id = vendor_id
        self._base_url = base_url
        self.cart_items: List[CartItem] = []
        self.add_to_cart_calls: List[Dict[str, Any]] = []
        self.inspect_cart_calls: int = 0
        self.should_fail_inspection: bool = False
        self.inspection_error_msg: str = "Mock inspection failure"

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

    def resolve_product(self, raw_input: str) -> ProductReference:
        if "2070-NE555P" in raw_input or "NE555P" in raw_input:
            return ProductReference(vendor_id=self._vendor_id, vendor_sku="2070-NE555P", pdp_url="https://lionelectronic.ir/products/2070-NE555P")
        if "3080-LM358" in raw_input or "LM358" in raw_input:
            return ProductReference(vendor_id=self._vendor_id, vendor_sku="3080-LM358", pdp_url="https://lionelectronic.ir/products/3080-LM358")
        return ProductReference(vendor_id=self._vendor_id, vendor_sku="SKU-100", pdp_url=f"{self._base_url}/p/100")

    def inspect_product(self, product_ref: ProductReference):
        from core.models import ProductDetails
        return ProductDetails(
            vendor_id=self._vendor_id,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=500,
            can_order=True,
            price_irr=50000,
            mpn=product_ref.vendor_sku.split("-")[-1] if "-" in product_ref.vendor_sku else product_ref.vendor_sku,
        )

    def extract_product_data(self, dom_context: Any):
        from core.models import CanonicalComponentDraft
        return CanonicalComponentDraft(vendor_id=self._vendor_id, vendor_sku="SKU-100")

    def map_to_canonical(self, product_details):
        return None

    def inspect_stock(self, product_ref: ProductReference):
        from core.models import StockStatus
        return StockStatus(
            vendor_id=self._vendor_id,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=500,
            in_stock=True,
            can_order=True,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=10, moq_raw=5)

    def inspect_cart(self) -> CartDetails:
        self.inspect_cart_calls += 1
        if self.should_fail_inspection:
            raise TransportNetworkError(self.inspection_error_msg)
        return CartDetails(
            vendor_id=self._vendor_id,
            cart_url=f"{self._base_url}/cart",
            total_items=len(self.cart_items),
            items=list(self.cart_items),
        )

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        self.add_to_cart_calls.append({"sku": product_ref.vendor_sku, "qty": quantity})
        for item in self.cart_items:
            if item.vendor_sku == product_ref.vendor_sku:
                item.quantity += quantity
                break
        else:
            self.cart_items.append(
                CartItem(
                    vendor_sku=product_ref.vendor_sku,
                    product_name=f"Product {product_ref.vendor_sku}",
                    quantity=quantity,
                    pdp_url=product_ref.pdp_url,
                )
            )

        return CartMutationResult(
            vendor_id=self._vendor_id,
            vendor_sku=product_ref.vendor_sku,
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
            raw_vendor_message=f"Added {quantity} to cart",
            cart_total_items=len(self.cart_items),
        )

    def authenticate(self, credentials=None, challenge_handler=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context):
        return None

    def close(self):
        pass


class MockLionCartAdapter(MockCartVendorAdapter):
    INSTANCE = None
    def __init__(self, config=None):
        if MockLionCartAdapter.INSTANCE is not None:
            self.__dict__ = MockLionCartAdapter.INSTANCE.__dict__
        else:
            super().__init__(vendor_id="vendor_lion", base_url="https://lionelectronic.ir")
            MockLionCartAdapter.INSTANCE = self


class MockJavanCartAdapter(MockCartVendorAdapter):
    INSTANCE = None
    def __init__(self, config=None):
        if MockJavanCartAdapter.INSTANCE is not None:
            self.__dict__ = MockJavanCartAdapter.INSTANCE.__dict__
        else:
            super().__init__(vendor_id="vendor_javan", base_url="https://javanelec.com")
            MockJavanCartAdapter.INSTANCE = self


class MockRoboEqCartAdapter(MockCartVendorAdapter):
    INSTANCE = None
    def __init__(self, config=None):
        if MockRoboEqCartAdapter.INSTANCE is not None:
            self.__dict__ = MockRoboEqCartAdapter.INSTANCE.__dict__
        else:
            super().__init__(vendor_id="vendor_roboeq", base_url="https://roboeq.ir")
            MockRoboEqCartAdapter.INSTANCE = self


@pytest.fixture
def test_registry():
    MockLionCartAdapter.INSTANCE = None
    MockJavanCartAdapter.INSTANCE = None
    MockRoboEqCartAdapter.INSTANCE = None

    lion_mock = MockLionCartAdapter()
    javan_mock = MockJavanCartAdapter()
    roboeq_mock = MockRoboEqCartAdapter()

    reg = VendorRegistry()
    reg.register_adapter("vendor_lion", MockLionCartAdapter, domains=["lionelectronic.ir"])
    reg.register_adapter("vendor_javan", MockJavanCartAdapter, domains=["javanelec.com"])
    reg.register_adapter("vendor_roboeq", MockRoboEqCartAdapter, domains=["roboeq.ir"])

    return reg, lion_mock, javan_mock, roboeq_mock



# =========================================================================
# 1. Authoritative A3 Quantity Reconciliation (Cases A through E + Edge Cases)
# =========================================================================

class TestQuantityReconciliationA3:
    """Verify exact compliance with canonical A3 MOQ and packaging-step rules."""

    def test_case_a_raw_less_than_moq_step_greater_than_moq_empty_cart(self):
        """Case A: raw=3, MOQ=5, step=10, existing=0 => target=5, delta=5."""
        target = calculate_effective_quantity(needed_qty=3, packaging_step=10, moq=5)
        assert target == 5  # Strictly 5, NOT 10!

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="TEST-A",
            product_ref=ProductReference("vendor_lion", "SKU-A", "https://lionelectronic.ir/p/a"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )
        cart = CartDetails(vendor_id="vendor_lion", cart_url="", total_items=0, items=[])
        existing, delta, is_noop, _ = UniversalProcurementOrchestrator.calculate_cart_delta(cand, target, cart)

        assert existing == 0
        assert delta == 5
        assert is_noop is False

    def test_case_b_raw_less_than_moq_step_greater_than_moq_partial_cart(self):
        """Case B: raw=3, MOQ=5, step=10, existing=2 => target=5, delta=3."""
        target = calculate_effective_quantity(needed_qty=3, packaging_step=10, moq=5)
        assert target == 5

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="TEST-B",
            product_ref=ProductReference("vendor_lion", "SKU-B", "https://lionelectronic.ir/p/b"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )
        cart = CartDetails(
            vendor_id="vendor_lion",
            cart_url="",
            total_items=1,
            items=[CartItem(vendor_sku="SKU-B", product_name="Item B", quantity=2)],
        )
        existing, delta, is_noop, _ = UniversalProcurementOrchestrator.calculate_cart_delta(cand, target, cart)

        assert existing == 2
        assert delta == 3
        assert is_noop is False

    def test_case_c_raw_less_than_moq_step_greater_than_moq_exact_cart(self):
        """Case C: raw=3, MOQ=5, step=10, existing=5 => target=5, delta=0 (no-op)."""
        target = calculate_effective_quantity(needed_qty=3, packaging_step=10, moq=5)
        assert target == 5

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="TEST-C",
            product_ref=ProductReference("vendor_lion", "SKU-C", "https://lionelectronic.ir/p/c"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )
        cart = CartDetails(
            vendor_id="vendor_lion",
            cart_url="",
            total_items=1,
            items=[CartItem(vendor_sku="SKU-C", product_name="Item C", quantity=5)],
        )
        existing, delta, is_noop, _ = UniversalProcurementOrchestrator.calculate_cart_delta(cand, target, cart)

        assert existing == 5
        assert delta == 0
        assert is_noop is True

    def test_case_d_raw_greater_than_moq_unaligned_step_empty_cart(self):
        """Case D: raw=12, MOQ=5, step=10, existing=0 => target=20, delta=20."""
        target = calculate_effective_quantity(needed_qty=12, packaging_step=10, moq=5)
        assert target == 20

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="TEST-D",
            product_ref=ProductReference("vendor_lion", "SKU-D", "https://lionelectronic.ir/p/d"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )
        cart = CartDetails(vendor_id="vendor_lion", cart_url="", total_items=0, items=[])
        existing, delta, is_noop, _ = UniversalProcurementOrchestrator.calculate_cart_delta(cand, target, cart)

        assert existing == 0
        assert delta == 20
        assert is_noop is False

    def test_case_e_raw_greater_than_moq_unaligned_step_partial_cart(self):
        """Case E: raw=12, MOQ=5, step=10, existing=17 => target=20, delta=3, final=20."""
        target = calculate_effective_quantity(needed_qty=12, packaging_step=10, moq=5)
        assert target == 20

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="TEST-E",
            product_ref=ProductReference("vendor_lion", "SKU-E", "https://lionelectronic.ir/p/e"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )
        cart = CartDetails(
            vendor_id="vendor_lion",
            cart_url="",
            total_items=1,
            items=[CartItem(vendor_sku="SKU-E", product_name="Item E", quantity=17)],
        )
        existing, delta, is_noop, _ = UniversalProcurementOrchestrator.calculate_cart_delta(cand, target, cart)

        assert existing == 17
        assert delta == 3
        assert is_noop is False

    def test_raw_less_than_moq_step_less_than_moq(self):
        """raw=3, MOQ=10, step=2 => target=10 (MOQ enforced without step rounding)."""
        target = calculate_effective_quantity(needed_qty=3, packaging_step=2, moq=10)
        assert target == 10

    def test_raw_equals_moq(self):
        """raw=5, MOQ=5, step=10 => raw >= MOQ => ceil(5/10)*10 = 10."""
        target = calculate_effective_quantity(needed_qty=5, packaging_step=10, moq=5)
        assert target == 10

    def test_raw_greater_than_moq_aligned_step(self):
        """raw=20, MOQ=5, step=10 => ceil(20/10)*10 = 20."""
        target = calculate_effective_quantity(needed_qty=20, packaging_step=10, moq=5)
        assert target == 20


# =========================================================================
# 2. Strict 4-Priority Cart Item Identity Cascade
# =========================================================================

class TestCartItemIdentityCascade:
    """Verify strict 4-priority matching cascade and negative constraints."""

    def test_priority1_normalized_vendor_sku_exact_match(self):
        """Priority 1: matching SKU yields EXACT_VENDOR_SKU."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "2070-NE555P", "https://lionelectronic.ir/products/2070-ne555p"),
            manufacturer="TI",
        )
        item = CartItem(
            vendor_sku="2070-ne555p",  # lowercase
            product_name="Timer IC NE555P",
            quantity=10,
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is True
        assert tier == IdentityMatchTier.EXACT_VENDOR_SKU

    def test_priority1_differing_vendor_sku_strictly_no_match(self):
        """Priority 1: distinct valid SKUs yield NO_MATCH even if MPN is identical."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "SKU-A", "https://lionelectronic.ir/p/a"),
        )
        item = CartItem(
            vendor_sku="SKU-B",
            product_name="NE555P",
            quantity=10,
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is False
        assert tier == IdentityMatchTier.NO_MATCH

    def test_priority2_canonical_pdp_url_match_when_sku_missing(self):
        """Priority 2: SKU missing on one side, canonical PDP URL matches."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "", "https://www.lionelectronic.ir/products/ne555/"),
        )
        item = CartItem(
            vendor_sku="",
            product_name="NE555",
            pdp_url="http://lionelectronic.ir/products/ne555",
            quantity=5,
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is True
        assert tier == IdentityMatchTier.CANONICAL_PDP_URL

    def test_priority3_mpn_and_manufacturer_match(self):
        """Priority 3: SKU/URL missing, MPN and Manufacturer match."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="STM32F103C8T6",
            product_ref=ProductReference("vendor_lion", "", ""),
            manufacturer="STMicroelectronics",
        )
        item = CartItem(
            vendor_sku="STM32F103C8T6",
            product_name="Microcontroller",
            quantity=10,
            mpn="STM32F103C8T6",
            manufacturer="STMicroelectronics",
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is True
        assert tier == IdentityMatchTier.MPN_AND_MANUFACTURER

    def test_priority3_differing_manufacturers_strictly_no_match(self):
        """Priority 3 Negative Rule: Identical MPN but different manufacturers yields NO_MATCH."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="LM358",
            product_ref=ProductReference("vendor_lion", "", ""),
            manufacturer="Texas Instruments",
        )
        item = CartItem(
            vendor_sku="LM358",
            product_name="OpAmp LM358",
            quantity=10,
            mpn="LM358",
            manufacturer="ON Semiconductor",
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is False
        assert tier == IdentityMatchTier.NO_MATCH

    def test_priority4_mpn_only_fallback_recorded(self):
        """Priority 4: MPN match with manufacturer absent on both sides yields MPN_ONLY_FALLBACK."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="1N4148",
            product_ref=ProductReference("vendor_lion", "", ""),
            manufacturer=None,
        )
        item = CartItem(
            vendor_sku="1N4148",
            product_name="Diode 1N4148",
            quantity=100,
            mpn="1N4148",
            manufacturer=None,
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is True
        assert tier == IdentityMatchTier.MPN_ONLY_FALLBACK

    def test_product_name_is_never_used_as_identity_key(self):
        """Negative Rule: Overlapping words in Product Name never match unrelated candidate."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="RES-10K-0805",
            product_ref=ProductReference("vendor_lion", "SKU-RES10K", "https://lionelectronic.ir/p/1"),
        )
        item = CartItem(
            vendor_sku="SKU-CAP10UF",
            product_name="SMD Resistor 10K 0805 High Precision",
            quantity=50,
        )
        is_match, tier = UniversalProcurementOrchestrator.match_cart_item(cand, item)
        assert is_match is False
        assert tier == IdentityMatchTier.NO_MATCH


# =========================================================================
# 3. Cart State Synchronization & Idempotent Convergence
# =========================================================================

class TestCartSynchronizationAndIdempotency:
    """Verify deterministic delta staging, multi-line summation, and repeated execution convergence."""

    def test_stage_candidate_empty_cart_adds_full_delta(self, test_registry):
        reg, lion, _, _ = test_registry
        orch = UniversalProcurementOrchestrator(registry=reg)

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=30, sync_cart=True)

        assert res.success is True
        assert res.is_noop is False
        assert res.actual_quantity_staged == 30
        assert res.initial_cart_qty == 0
        assert res.delta_qty == 30
        assert len(lion.add_to_cart_calls) == 1
        assert lion.add_to_cart_calls[0]["qty"] == 30

    def test_stage_candidate_partial_cart_adds_shortage_only(self, test_registry):
        reg, lion, _, _ = test_registry
        lion.cart_items = [CartItem(vendor_sku="LION-555", product_name="NE555P", quantity=10)]

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=30, sync_cart=True)

        assert res.success is True
        assert res.is_noop is False
        assert res.initial_cart_qty == 10
        assert res.delta_qty == 20
        assert res.actual_quantity_staged == 20
        assert len(lion.add_to_cart_calls) == 1
        assert lion.add_to_cart_calls[0]["qty"] == 20

    def test_stage_candidate_existing_exceeds_target_is_noop(self, test_registry):
        reg, lion, _, _ = test_registry
        lion.cart_items = [CartItem(vendor_sku="LION-555", product_name="NE555P", quantity=50)]

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=30, sync_cart=True)

        assert res.success is True
        assert res.is_noop is True
        assert res.actual_quantity_staged == 0
        assert res.delta_qty == 0
        assert res.initial_cart_qty == 50
        assert "Already satisfied" in res.raw_vendor_message
        assert len(lion.add_to_cart_calls) == 0

    def test_multi_line_cart_same_sku_aggregated(self, test_registry):
        reg, lion, _, _ = test_registry
        lion.cart_items = [
            CartItem(vendor_sku="LION-555", product_name="NE555P Line 1", quantity=15),
            CartItem(vendor_sku="LION-555", product_name="NE555P Line 2", quantity=25),
        ]

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=50, sync_cart=True)

        assert res.success is True
        assert res.initial_cart_qty == 40
        assert res.delta_qty == 10
        assert res.actual_quantity_staged == 10

    def test_repeated_synchronization_convergence_idempotency(self, test_registry):
        """Run 1 stages delta; Run 2 performs no-op; cart total is stable."""
        reg, lion, _, _ = test_registry
        lion.cart_items = [CartItem(vendor_sku="LION-555", product_name="NE555P", quantity=17)]

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=5),
            in_stock=True, can_order=True,
        )

        # Execution 1: Target = 20, Existing = 17 -> stages delta = 3 -> new cart = 20
        res1 = orch.stage_candidate(cand, quantity=20, sync_cart=True)
        assert res1.success is True
        assert res1.is_noop is False
        assert res1.delta_qty == 3
        assert res1.actual_quantity_staged == 3
        assert len(lion.add_to_cart_calls) == 1

        # Execution 2: Re-run immediately on updated cart -> Target = 20, Existing = 20 -> No-op
        res2 = orch.stage_candidate(cand, quantity=20, sync_cart=True)
        assert res2.success is True
        assert res2.is_noop is True
        assert res2.delta_qty == 0
        assert res2.actual_quantity_staged == 0
        assert len(lion.add_to_cart_calls) == 1


# =========================================================================
# 4. Multi-Vendor Isolation & Error Containment
# =========================================================================

class TestMultiVendorIsolationAndErrorHandling:
    """Verify vendor isolation, disabled vendor bypass, and max_orderable enforcement."""

    def test_multi_vendor_isolation_one_fails_other_succeeds(self, test_registry):
        reg, lion, javan, _ = test_registry
        lion.should_fail_inspection = True

        orch = UniversalProcurementOrchestrator(registry=reg)

        cand_lion = VendorProcurementCandidate(
            vendor_id="vendor_lion", part_number="LION-PART",
            product_ref=ProductReference("vendor_lion", "L1", "https://lionelectronic.ir/1"),
            in_stock=True, can_order=True,
        )
        cand_javan = VendorProcurementCandidate(
            vendor_id="vendor_javan", part_number="JAVAN-PART",
            product_ref=ProductReference("vendor_javan", "J1", "https://javanelec.com/1"),
            in_stock=True, can_order=True,
        )

        plan = BOMProcurementPlan(
            plan_id="PLAN-ISO",
            results=[
                RequestProcurementResult(
                    request=ProcurementRequest(part_number="LION-PART", required_quantity=10),
                    candidates=[cand_lion],
                    evaluations=[],
                    selected_evaluation=CandidateEvaluation(candidate=cand_lion, required_quantity=10, is_eligible=True, effective_quantity=10, effective_total_price_irr=1000),
                    status="RESOLVED",
                ),
                RequestProcurementResult(
                    request=ProcurementRequest(part_number="JAVAN-PART", required_quantity=20),
                    candidates=[cand_javan],
                    evaluations=[],
                    selected_evaluation=CandidateEvaluation(candidate=cand_javan, required_quantity=20, is_eligible=True, effective_quantity=20, effective_total_price_irr=2000),
                    status="RESOLVED",
                ),
            ],
        )

        summary = orch.stage_procurement_plan(plan, sync_cart=True)

        assert summary["total_items"] == 2
        assert summary["successful_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["results"][0]["status"] == "FAILED"
        assert summary["results"][0]["vendor_id"] == "vendor_lion"
        assert summary["results"][1]["status"] == "SUCCESS"
        assert summary["results"][1]["vendor_id"] == "vendor_javan"
        assert len(javan.add_to_cart_calls) == 1

    def test_disabled_vendor_strictly_bypassed_upfront(self, test_registry):
        reg, lion, _, _ = test_registry
        reg.set_vendor_enabled("vendor_lion", False)

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=10, sync_cart=True)

        assert res.success is False
        assert res.error_category == "VENDOR_DISABLED"
        assert lion.inspect_cart_calls == 0
        assert len(lion.add_to_cart_calls) == 0

    def test_max_quantity_exceeded_enforcement(self, test_registry):
        reg, lion, _, _ = test_registry
        lion.cart_items = [CartItem(vendor_sku="LION-555", product_name="NE555P", quantity=45)]

        orch = UniversalProcurementOrchestrator(registry=reg)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10, max_orderable_raw=50),
            in_stock=True, can_order=True,
        )

        res = orch.stage_candidate(cand, quantity=60, sync_cart=True)

        assert res.success is False
        assert res.error_category == "MAX_QUANTITY_EXCEEDED"
        assert len(lion.add_to_cart_calls) == 0


# =========================================================================
# 5. Procurement Bridge Batch Staging Integration
# =========================================================================

class TestBridgeBatchDeltaStaging:
    """Verify ProcurementBridge batch execution with delta synchronization."""

    def test_bridge_batch_staging_with_delta_sync(self, test_registry):
        reg, lion, _, _ = test_registry
        lion.cart_items = [CartItem(vendor_sku="2070-NE555P", product_name="NE555P", quantity=20)]

        orch = UniversalProcurementOrchestrator(registry=reg)

        items = [
            {
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 20,
                "link": "https://lionelectronic.ir/products/2070-NE555P",
            },
            {
                "part_name": "LM358",
                "part_number": "LM358",
                "needed_qty": 10,
                "link": "https://lionelectronic.ir/products/3080-LM358",
            },
        ]

        summary = ProcurementBridge.execute_staged_procurement_batch(
            items=items,
            registry=reg,
            orchestrator=orch,
        )

        assert summary["success"] is True
        assert summary["successful_count"] == 2
        assert summary["failed_count"] == 0

        # Part 1 was already satisfied (no-op)
        assert summary["results"][0]["status"] == "SUCCESS"
        assert summary["results"][0]["qty"] == 0
        assert "Already satisfied" in summary["results"][0]["msg"]

        # Part 2 was newly staged
        assert summary["results"][1]["status"] == "SUCCESS"
        assert summary["results"][1]["qty"] == 10
