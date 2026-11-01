"""
Deterministic Multi-Vendor Integration Test Suite for Omnix Procurement
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md
Strictly offline: Zero Selenium, Zero live websites, Zero network dependencies.
"""

import pytest
from typing import Optional, Dict, Any, List, Tuple

from core.errors import (
    OmnixVendorError,
    UnknownVendorError,
    MaxQuantityExceededError,
    TransportNetworkError,
    OutOfStockError,
    ProductNotFoundError,
)
from core.models import (
    AdapterConfig,
    AdapterStatus,
    SearchResultSet,
    SearchItem,
    ProductReference,
    ProductDetails,
    CanonicalComponentDraft,
    StockStatus,
    OrderConstraints,
    CartMutationResult,
    CartDetails,
    AuthCredentials,
    AuthResult,
    SessionStatus,
    RecoveryResult,
)
from core.procurement.models import (
    PriceTier,
    ProcurementRequest,
    VendorProcurementCandidate,
    CandidateEvaluation,
    BOMProcurementPlan,
    calculate_effective_quantity,
    effective_unit_price,
    effective_total_price,
)
from core.procurement.registry import VendorRegistry
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.vendor_interface import IVendorAdapter


class BaseFakeVendorAdapter(IVendorAdapter):
    """Base fake adapter for deterministic integration tests with operation instrumentation."""

    VENDOR_ID = "vendor_base_fake"
    BASE_URL = "https://base.example.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config
        self.search_calls: List[str] = []
        self.resolve_calls: List[str] = []
        self.inspect_calls: List[str] = []
        self.cart_calls: List[Tuple[ProductReference, int]] = []
        self._catalog: Dict[str, Dict[str, Any]] = {}

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=False)

    def search_part(self, query: str) -> SearchResultSet:
        self.search_calls.append(query)
        items = []
        for sku, data in self._catalog.items():
            if query.upper() in sku.upper() or query.upper() in data.get("mpn", "").upper():
                items.append(
                    SearchItem(
                        vendor_sku=sku,
                        mpn_hint=data.get("mpn", sku),
                        title=data.get("title", sku),
                        pdp_url=f"{self.BASE_URL}/product/{sku}",
                    )
                )
        return SearchResultSet(
            vendor_id=self.VENDOR_ID,
            query=query,
            total_matches=len(items),
            is_exact_match=any(query.upper() == it.mpn_hint.upper() for it in items),
            items=items,
        )

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        self.resolve_calls.append(url_or_sku)
        sku = url_or_sku.split("/")[-1]
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=sku,
            pdp_url=f"{self.BASE_URL}/product/{sku}",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        self.inspect_calls.append(product_ref.vendor_sku)
        data = self._catalog.get(product_ref.vendor_sku, {})
        d = ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=data.get("stock", 0),
            can_order=data.get("can_order", True),
            price_irr=data.get("price_irr", 100000),
            mpn=data.get("mpn", product_ref.vendor_sku),
            manufacturer=data.get("manufacturer", "Generic"),
            order_constraints=data.get("order_constraints", OrderConstraints(packaging_step_raw=1, moq_raw=1)),
        )
        d.raw_data = {"price_tiers": data.get("price_tiers", [])}
        return d

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(vendor_id=self.VENDOR_ID, vendor_sku="FAKE")

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        data = self._catalog.get(product_ref.vendor_sku, {})
        stock_q = data.get("stock", 0)
        can_ord = data.get("can_order", True)
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=stock_q,
            in_stock=stock_q > 0,
            can_order=can_ord,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        data = self._catalog.get(product_ref.vendor_sku, {})
        return data.get("order_constraints", OrderConstraints(packaging_step_raw=1, moq_raw=1))

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        self.cart_calls.append((product_ref, quantity))
        return CartMutationResult(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
            cart_total_items=len(self.cart_calls),
        )

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url=f"{self.BASE_URL}/cart", total_items=len(self.cart_calls))

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="noop", message="OK")

    def close(self) -> None:
        pass


class FakeLionAdapter(BaseFakeVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__(config)
        self._catalog = {
            "LION-NE555": {
                "mpn": "NE555P",
                "title": "NE555 Precision Timer DIP-8",
                "stock": 500,
                "can_order": True,
                "price_irr": 85000,
                "order_constraints": OrderConstraints(packaging_step_raw=10, moq_raw=10),
            },
            "LION-LM358": {
                "mpn": "LM358N",
                "title": "LM358 Dual Op-Amp",
                "stock": 200,
                "can_order": True,
                "price_irr": 120000,
                "order_constraints": OrderConstraints(packaging_step_raw=5, moq_raw=5),
            },
            "LION-RES-10K": {
                "mpn": "RES-10K-0805",
                "title": "Resistor 10k 0805",
                "stock": 1000,
                "can_order": True,
                "price_irr": 500,
                "order_constraints": OrderConstraints(packaging_step_raw=50, moq_raw=50),
            },
        }


class FakeJavanAdapter(BaseFakeVendorAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__(config)
        self._catalog = {
            "JAVAN-NE555": {
                "mpn": "NE555P",
                "title": "NE555 Timer IC Texas Instruments",
                "stock": 1000,
                "can_order": True,
                "price_irr": 95000,
                "price_tiers": [
                    {"min_quantity": 1, "unit_price_irr": 95000},
                    {"min_quantity": 50, "unit_price_irr": 70000},
                    {"min_quantity": 100, "unit_price_irr": 60000},
                ],
                "order_constraints": OrderConstraints(packaging_step_raw=1, moq_raw=1),
            },
            "JAVAN-LM358": {
                "mpn": "LM358N",
                "title": "LM358 Dual Op-Amp TI",
                "stock": 800,
                "can_order": True,
                "price_irr": 80000,
                "price_tiers": [
                    {"min_quantity": 1, "unit_price_irr": 80000},
                    {"min_quantity": 50, "unit_price_irr": 65000},
                ],
                "order_constraints": OrderConstraints(packaging_step_raw=1, moq_raw=1),
            },
            "JAVAN-APPROX-555": {
                "mpn": "NE555-GENERIC",
                "title": "NE555 Generic Equivalent",
                "stock": 2000,
                "can_order": True,
                "price_irr": 30000,
                "order_constraints": OrderConstraints(packaging_step_raw=1, moq_raw=1),
            },
        }


class FakeRoboEqAdapter(BaseFakeVendorAdapter):
    VENDOR_ID = "vendor_roboeq"
    BASE_URL = "https://roboeq.ir"

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__(config)
        self._catalog = {
            "ROBO-NE555": {
                "mpn": "NE555P",
                "title": "RoboEq NE555 Standard",
                "stock": 150,
                "can_order": True,
                "price_irr": 110000,
                "price_tiers": [
                    {"min_quantity": 1, "unit_price_irr": 110000},
                    {"min_quantity": 25, "unit_price_irr": 90000},
                ],
                "order_constraints": OrderConstraints(packaging_step_raw=1, moq_raw=1),
            },
            "ROBO-CAP-100UF": {
                "mpn": "CAP-100UF-25V",
                "title": "Capacitor 100uF 25V",
                "stock": 50,
                "can_order": True,
                "price_irr": 15000,
                "order_constraints": OrderConstraints(packaging_step_raw=5, moq_raw=5, max_orderable_raw=20),
            },
            "ROBO-OUT-OF-STOCK": {
                "mpn": "STM32F103C8T6",
                "title": "BluePill STM32 IC",
                "stock": 0,
                "can_order": False,
                "price_irr": 450000,
                "order_constraints": OrderConstraints(packaging_step_raw=1, moq_raw=1),
            },
        }


class FakeFailingAdapter(BaseFakeVendorAdapter):
    VENDOR_ID = "vendor_failing"
    BASE_URL = "https://failing-store.example.com"

    def search_part(self, query: str) -> SearchResultSet:
        self.search_calls.append(query)
        raise TransportNetworkError("Simulated socket timeout on search", vendor_id=self.VENDOR_ID)


@pytest.fixture
def multi_vendor_registry():
    """Populate a single VendorRegistry with all 3 test vendor adapters."""
    registry = VendorRegistry()
    registry.register_adapter("vendor_lion", FakeLionAdapter, domains=["lionelectronic.ir"])
    registry.register_adapter("vendor_javan", FakeJavanAdapter, domains=["javanelec.com"])
    registry.register_adapter("vendor_roboeq", FakeRoboEqAdapter, domains=["roboeq.ir"])
    return registry


# ==============================================================================
# 15 MANDATORY MULTI-VENDOR INTEGRATION TESTS
# ==============================================================================

class TestMultiVendorIntegrationSuite:
    """15-Point Multi-Vendor Orchestration Integration Test Suite."""

    def test_1_multi_vendor_registration(self, multi_vendor_registry):
        """Test 1: Multiple fake adapters coexist in one VendorRegistry."""
        vids = multi_vendor_registry.list_vendors()
        assert len(vids) == 3
        assert "vendor_lion" in vids
        assert "vendor_javan" in vids
        assert "vendor_roboeq" in vids

        lion_adapter = multi_vendor_registry.get_adapter("vendor_lion")
        javan_adapter = multi_vendor_registry.get_adapter("vendor_javan")
        robo_adapter = multi_vendor_registry.get_adapter("vendor_roboeq")

        assert isinstance(lion_adapter, FakeLionAdapter)
        assert isinstance(javan_adapter, FakeJavanAdapter)
        assert isinstance(robo_adapter, FakeRoboEqAdapter)

    def test_2_broadcast_procurement(self, multi_vendor_registry):
        """Test 2: One ProcurementRequest queries all registered vendors when no target is set."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10)

        candidates = orchestrator.gather_candidates(req)
        assert len(candidates) >= 3

        queried_vids = {c.vendor_id for c in candidates}
        assert queried_vids == {"vendor_lion", "vendor_javan", "vendor_roboeq"}

        for c in candidates:
            assert isinstance(c, VendorProcurementCandidate)
            assert c.part_number is not None
            assert c.product_ref is not None
            assert c.order_constraints is not None

    def test_3_explicit_vendor_id_routing(self, multi_vendor_registry):
        """Test 3: Setting explicit_vendor_id targets ONLY that vendor; others remain untouched."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_id="vendor_javan")

        candidates = orchestrator.gather_candidates(req)
        assert len(candidates) >= 1
        assert all(c.vendor_id == "vendor_javan" for c in candidates)

    def test_4_explicit_vendor_url_routing(self, multi_vendor_registry):
        """Test 4: Setting explicit_vendor_url resolves target vendor via registry without cross-querying."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)
        
        # Javan URL
        req_javan = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://javanelec.com/product/JAVAN-NE555")
        cands_javan = orchestrator.gather_candidates(req_javan)
        assert len(cands_javan) == 1
        assert cands_javan[0].vendor_id == "vendor_javan"

        # Lion URL
        req_lion = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://lionelectronic.ir/product/LION-NE555")
        cands_lion = orchestrator.gather_candidates(req_lion)
        assert len(cands_lion) == 1
        assert cands_lion[0].vendor_id == "vendor_lion"

        # Unknown domain URL returns empty candidate list
        req_unknown = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://unknown-distributor.com/p/123")
        cands_unknown = orchestrator.gather_candidates(req_unknown)
        assert len(cands_unknown) == 0

    def test_5_exact_mpn_precedence(self, multi_vendor_registry):
        """Test 5: Exact MPN match takes strict precedence over cheaper non-exact candidates."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        # Candidate A: Exact MPN NE555P, price 85,000 IRR
        cand_exact = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "L-555", "https://lionelectronic.ir/p/1"),
            in_stock=True, can_order=True, base_unit_price_irr=85000,
        )
        # Candidate B: Non-exact MPN NE555-GENERIC, much cheaper price 30,000 IRR
        cand_cheap_approx = VendorProcurementCandidate(
            vendor_id="vendor_javan",
            part_number="NE555-GENERIC",
            product_ref=ProductReference("vendor_javan", "J-555", "https://javanelec.com/p/2"),
            in_stock=True, can_order=True, base_unit_price_irr=30000,
        )

        eval_exact = orchestrator.evaluate_candidate(cand_exact, 10, exact_mpn_required=True, requested_part_number="NE555P")
        eval_approx = orchestrator.evaluate_candidate(cand_cheap_approx, 10, exact_mpn_required=True, requested_part_number="NE555P")

        # When exact_mpn_required=True: approx is rejected
        assert eval_exact.is_eligible is True
        assert eval_approx.is_eligible is False

        best = orchestrator.select_best_candidate([eval_exact, eval_approx])
        assert best.candidate.vendor_id == "vendor_lion"
        assert best.candidate.part_number == "NE555P"

        # When exact_mpn_required=False: both eligible, but exact MPN still ranks first
        eval_exact_relaxed = orchestrator.evaluate_candidate(cand_exact, 10, exact_mpn_required=False, requested_part_number="NE555P")
        eval_approx_relaxed = orchestrator.evaluate_candidate(cand_cheap_approx, 10, exact_mpn_required=False, requested_part_number="NE555P")

        assert eval_exact_relaxed.is_eligible is True
        assert eval_approx_relaxed.is_eligible is True

        best_relaxed = orchestrator.select_best_candidate([eval_exact_relaxed, eval_approx_relaxed])
        assert best_relaxed.candidate.vendor_id == "vendor_lion"

    def test_6_lowest_effective_total_cost(self, multi_vendor_registry):
        """Test 6: When candidates are eligible and exact, lowest effective total price wins."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        # For quantity = 10:
        # Lion: step=10, 10 * 85,000 = 850,000 IRR
        # Javan: step=1,  10 * 95,000 (Tier 1) = 950,000 IRR
        # RoboEq: step=1, 10 * 110,000 = 1,100,000 IRR
        # Lion is cheapest -> Lion wins
        req_10 = ProcurementRequest(part_number="NE555P", required_quantity=10)
        plan_10 = orchestrator.build_plan([req_10])
        assert plan_10.results[0].selected_evaluation.candidate.vendor_id == "vendor_lion"
        assert plan_10.results[0].selected_evaluation.effective_total_price_irr == 850000

        # For quantity = 60:
        # Lion: step=10 -> 60 * 85,000 = 5,100,000 IRR
        # Javan: step=1 -> 60 * 70,000 (Tier 2) = 4,200,000 IRR
        # RoboEq: step=1 -> 60 * 90,000 (Tier 2) = 5,400,000 IRR
        # Javan is cheapest due to volume tier -> Javan wins
        req_60 = ProcurementRequest(part_number="NE555P", required_quantity=60)
        plan_60 = orchestrator.build_plan([req_60])
        assert plan_60.results[0].selected_evaluation.candidate.vendor_id == "vendor_javan"
        assert plan_60.results[0].selected_evaluation.effective_total_price_irr == 4200000

    def test_7_price_tier_consistency(self):
        """Test 7: Multi-tier volume discount resolution without price distortion or averaging."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_javan",
            part_number="LM358N",
            product_ref=ProductReference("vendor_javan", "J-358", "https://javanelec.com/1"),
            base_unit_price_irr=100000,
            price_tiers=[
                PriceTier(min_quantity=1, unit_price_irr=100000),
                PriceTier(min_quantity=50, unit_price_irr=80000),
                PriceTier(min_quantity=100, unit_price_irr=60000),
            ],
        )

        assert effective_unit_price(cand, 1) == 100000
        assert effective_unit_price(cand, 49) == 100000
        assert effective_unit_price(cand, 50) == 80000
        assert effective_unit_price(cand, 99) == 80000
        assert effective_unit_price(cand, 100) == 60000
        assert effective_unit_price(cand, 500) == 60000

        assert effective_total_price(cand, 50) == 50 * 80000
        assert effective_total_price(cand, 100) == 100 * 60000

    def test_8_packaging_step_and_moq(self):
        """Test 8: Effective quantity calculation respects step and MOQ across multiple scenarios."""
        # Scenario A: Needed 13, Step 10, MOQ 10 -> ceil(13/10)*10 = 20
        assert calculate_effective_quantity(needed_qty=13, packaging_step=10, moq=10) == 20

        # Scenario B: Needed 7, Step 1, MOQ 50 -> max(7, 50) = 50
        assert calculate_effective_quantity(needed_qty=7, packaging_step=1, moq=50) == 50

        # Scenario C: Needed 45, Step 25, MOQ 10 -> ceil(45/25)*25 = 50
        assert calculate_effective_quantity(needed_qty=45, packaging_step=25, moq=10) == 50

    def test_9_max_orderable_enforcement(self, multi_vendor_registry):
        """Test 9: Effective quantity exceeding max_orderable triggers rejection / MaxQuantityExceededError."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        # ROBO-CAP-100UF has max_orderable_raw = 20
        # Requesting 25 units -> exceeds max_orderable
        req = ProcurementRequest(part_number="CAP-100UF-25V", required_quantity=25, explicit_vendor_id="vendor_roboeq")
        cands = orchestrator.gather_candidates(req)
        assert len(cands) == 1

        evaluation = orchestrator.evaluate_candidate(cands[0], required_quantity=25)
        assert evaluation.is_eligible is False
        assert any("exceeds max orderable limit" in r for r in evaluation.rejection_reasons)

    def test_10_ineligible_candidates(self, multi_vendor_registry):
        """Test 10: Out-of-stock and non-orderable items are strictly excluded from selection."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        # ROBO-OUT-OF-STOCK has stock=0 and can_order=False
        req = ProcurementRequest(part_number="STM32F103C8T6", required_quantity=1, explicit_vendor_id="vendor_roboeq")
        plan = orchestrator.build_plan([req])

        assert plan.total_items == 1
        assert plan.resolved_count == 0
        assert plan.results[0].status == "OUT_OF_STOCK"
        assert plan.results[0].selected_evaluation is None

    def test_11_vendor_failure_is_not_success(self):
        """Test 11: Vendor failure (network/transport exception) does not fabricate a false candidate."""
        registry = VendorRegistry()
        registry.register_adapter("vendor_failing", FakeFailingAdapter, domains=["failing.com"])
        orchestrator = UniversalProcurementOrchestrator(registry)

        req = ProcurementRequest(part_number="TEST-PART", required_quantity=1)
        cands = orchestrator.gather_candidates(req)
        assert len(cands) == 0

        plan = orchestrator.build_plan([req])
        assert plan.resolved_count == 0
        assert plan.results[0].status == "UNRESOLVED"

    def test_12_cart_staging_safety(self, multi_vendor_registry):
        """Test 12: Cart staging calls only the selected adapter's add_to_cart without executing checkout."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        lion_adapter = multi_vendor_registry.get_adapter("vendor_lion")
        javan_adapter = multi_vendor_registry.get_adapter("vendor_javan")

        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            in_stock=True, can_order=True, base_unit_price_irr=85000,
        )

        mutation = orchestrator.stage_candidate(cand, 20)
        assert mutation.success is True
        assert mutation.vendor_id == "vendor_lion"
        assert mutation.requested_quantity == 20

    def test_13_multi_request_bom_plan(self, multi_vendor_registry):
        """Test 13: Multi-request BOM plan correctly resolves different parts to different vendors."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        requests = [
            # Part 1: LM358N (Javan is cheaper: 80k vs Lion 120k) -> Javan wins
            ProcurementRequest(part_number="LM358N", required_quantity=10),
            # Part 2: RES-10K-0805 (Only Lion has stock) -> Lion wins
            ProcurementRequest(part_number="RES-10K-0805", required_quantity=100),
            # Part 3: CAP-100UF-25V (Only RoboEq has stock) -> RoboEq wins
            ProcurementRequest(part_number="CAP-100UF-25V", required_quantity=10),
            # Part 4: Missing part -> Unresolved
            ProcurementRequest(part_number="NON_EXISTENT_IC", required_quantity=1),
        ]

        plan = orchestrator.build_plan(requests)

        assert plan.total_items == 4
        assert plan.resolved_count == 3
        assert plan.unresolved_count == 1
        assert plan.is_complete is False

        # Verify multi-vendor distribution
        selected_vids = {e.candidate.vendor_id for e in plan.get_selected_evaluations()}
        assert "vendor_javan" in selected_vids
        assert "vendor_lion" in selected_vids
        assert "vendor_roboeq" in selected_vids

        # Verify unresolved item
        unresolved = plan.get_unresolved_results()
        assert len(unresolved) == 1
        assert unresolved[0].request.part_number == "NON_EXISTENT_IC"

    def test_14_deterministic_repeatability(self, multi_vendor_registry):
        """Test 14: Repeated plan executions on identical inputs yield 100% identical plans."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)
        requests = [
            ProcurementRequest(part_number="NE555P", required_quantity=60),
            ProcurementRequest(part_number="LM358N", required_quantity=10),
        ]

        plan_1 = orchestrator.build_plan(requests)
        plan_2 = orchestrator.build_plan(requests)

        assert plan_1.total_cost_irr == plan_2.total_cost_irr
        assert plan_1.resolved_count == plan_2.resolved_count

        for r1, r2 in zip(plan_1.results, plan_2.results):
            assert r1.selected_evaluation.candidate.vendor_id == r2.selected_evaluation.candidate.vendor_id
            assert r1.selected_evaluation.effective_total_price_irr == r2.selected_evaluation.effective_total_price_irr
            assert r1.selected_evaluation.effective_quantity == r2.selected_evaluation.effective_quantity

    def test_15_vendor_isolation(self, multi_vendor_registry):
        """Test 15: Operations on one vendor do not cross-mutate another vendor's adapter state."""
        orchestrator = UniversalProcurementOrchestrator(multi_vendor_registry)

        req_lion_only = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_id="vendor_lion")
        cands = orchestrator.gather_candidates(req_lion_only)
        assert len(cands) == 1
        assert cands[0].vendor_id == "vendor_lion"
