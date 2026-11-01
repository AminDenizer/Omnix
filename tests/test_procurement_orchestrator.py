"""
Deterministic Unit Tests for UniversalProcurementOrchestrator
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
"""

import pytest
from typing import Optional, Dict, Any, List

from core.errors import UnknownVendorError
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
    BOMProcurementPlan,
)
from core.procurement.registry import VendorRegistry
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.vendor_interface import IVendorAdapter


class MockLionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config

    @property
    def vendor_id(self) -> str: return self.VENDOR_ID
    @property
    def base_url(self) -> str: return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=False)

    def search_part(self, query: str) -> SearchResultSet:
        if "NE555" in query.upper():
            return SearchResultSet(
                vendor_id=self.VENDOR_ID, query=query, total_matches=1, is_exact_match=True,
                items=[SearchItem(vendor_sku="LION-555", mpn_hint="NE555P", title="NE555 Timer IC", pdp_url="https://lionelectronic.ir/p/555")]
            )
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False)

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="LION-555", pdp_url="https://lionelectronic.ir/p/555")

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID, vendor_sku="LION-555", pdp_url="https://lionelectronic.ir/p/555",
            stock_quantity=100, can_order=True, price_irr=85000, mpn="NE555P", manufacturer="TI",
            order_constraints=OrderConstraints(packaging_step_raw=10, moq_raw=10)
        )

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(vendor_id=self.VENDOR_ID, vendor_sku="LION-555")

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        return StockStatus(vendor_id=self.VENDOR_ID, vendor_sku="LION-555", stock_quantity=100, in_stock=True, can_order=True)

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=10, moq_raw=10)

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        return CartMutationResult(vendor_id=self.VENDOR_ID, vendor_sku="LION-555", requested_quantity=quantity, actual_quantity_staged=quantity, success=True)

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url="https://lionelectronic.ir/cart", total_items=1)

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="noop", message="OK")

    def close(self) -> None: pass


class MockJavanAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config

    @property
    def vendor_id(self) -> str: return self.VENDOR_ID
    @property
    def base_url(self) -> str: return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=False)

    def search_part(self, query: str) -> SearchResultSet:
        if "NE555" in query.upper():
            return SearchResultSet(
                vendor_id=self.VENDOR_ID, query=query, total_matches=1, is_exact_match=True,
                items=[SearchItem(vendor_sku="JAVAN-555", mpn_hint="NE555P", title="NE555 Timer", pdp_url="https://javanelec.com/p/555")]
            )
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False)

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-555", pdp_url="https://javanelec.com/p/555")

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        d = ProductDetails(
            vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-555", pdp_url="https://javanelec.com/p/555",
            stock_quantity=500, can_order=True, price_irr=90000, mpn="NE555P", manufacturer="TI",
            order_constraints=OrderConstraints(packaging_step_raw=1, moq_raw=1)
        )
        # Attach raw price tiers
        d.raw_data = {
            "price_tiers": [
                {"min_quantity": 1, "unit_price_irr": 90000},
                {"min_quantity": 50, "unit_price_irr": 70000},
            ]
        }
        return d

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-555")

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        return StockStatus(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-555", stock_quantity=500, in_stock=True, can_order=True)

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=1, moq_raw=1)

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        return CartMutationResult(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-555", requested_quantity=quantity, actual_quantity_staged=quantity, success=True)

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url="https://javanelec.com/cart", total_items=1)

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="noop", message="OK")

    def close(self) -> None: pass


@pytest.fixture
def mock_registry():
    registry = VendorRegistry()
    registry.register_adapter("vendor_lion", MockLionAdapter, domains=["lionelectronic.ir"])
    registry.register_adapter("vendor_javan", MockJavanAdapter, domains=["javanelec.com"])
    return registry


class TestUniversalProcurementOrchestratorRouting:
    """Verify deterministic vendor routing according to explicit IDs, URLs, or all vendors."""

    def test_route_explicit_vendor_id(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_id="vendor_lion")

        cands = orchestrator.gather_candidates(req)
        assert len(cands) == 1
        assert cands[0].vendor_id == "vendor_lion"

    def test_route_explicit_vendor_url(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://javanelec.com/p/555")

        cands = orchestrator.gather_candidates(req)
        assert len(cands) == 1
        assert cands[0].vendor_id == "vendor_javan"

    def test_route_unknown_explicit_vendor_raises(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_id="vendor_nonexistent")

        with pytest.raises(UnknownVendorError):
            orchestrator.gather_candidates(req)

    def test_route_all_vendors_when_no_explicit_target(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10)

        cands = orchestrator.gather_candidates(req)
        vids = {c.vendor_id for c in cands}
        assert "vendor_lion" in vids
        assert "vendor_javan" in vids
        assert len(cands) == 2


class TestUniversalProcurementOrchestratorEvaluationAndSelection:
    """Verify deterministic candidate evaluation and price/MPN precedence."""

    def test_selection_prefers_lower_effective_total_price(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        # Quantity 60:
        # Lion: step=10 -> effective_qty=60 * 85,000 = 5,100,000 IRR
        # Javan: step=1 -> effective_qty=60 * 70,000 (Tier 2) = 4,200,000 IRR
        req = ProcurementRequest(part_number="NE555P", required_quantity=60)
        plan = orchestrator.build_plan([req])

        assert plan.total_items == 1
        assert plan.resolved_count == 1
        res = plan.results[0]
        assert res.status == "RESOLVED"
        assert res.selected_evaluation.candidate.vendor_id == "vendor_javan"
        assert res.selected_evaluation.effective_total_price_irr == 4200000

    def test_selection_prefers_exact_mpn(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        # Lion candidate has exact MPN NE555P, mock custom candidate has generic NE555
        cand_exact = VendorProcurementCandidate(
            vendor_id="vendor_lion", part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "L1", "https://lionelectronic.ir/1"),
            in_stock=True, can_order=True, base_unit_price_irr=100000
        )
        cand_approx = VendorProcurementCandidate(
            vendor_id="vendor_javan", part_number="NE555-GENERIC",
            product_ref=ProductReference("vendor_javan", "J1", "https://javanelec.com/1"),
            in_stock=True, can_order=True, base_unit_price_irr=50000
        )
        eval_exact = orchestrator.evaluate_candidate(cand_exact, 10, exact_mpn_required=True, requested_part_number="NE555P")
        eval_approx = orchestrator.evaluate_candidate(cand_approx, 10, exact_mpn_required=True, requested_part_number="NE555P")

        # When exact MPN is required, approx is ineligible
        assert eval_exact.is_eligible is True
        assert eval_approx.is_eligible is False

        best = orchestrator.select_best_candidate([eval_exact, eval_approx])
        assert best.candidate.vendor_id == "vendor_lion"

    def test_unresolved_plan_when_no_candidates_found(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        req = ProcurementRequest(part_number="MISSING_PART_XYZ", required_quantity=5)
        plan = orchestrator.build_plan([req])

        assert plan.total_items == 1
        assert plan.resolved_count == 0
        assert plan.unresolved_count == 1
        assert plan.is_complete is False
        assert plan.results[0].status == "UNRESOLVED"


class TestUniversalProcurementOrchestratorCartStaging:
    """Verify non-destructive cart staging through adapter contract."""

    def test_stage_candidate_delegates_to_adapter(self, mock_registry):
        orchestrator = UniversalProcurementOrchestrator(mock_registry)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion", part_number="NE555P",
            product_ref=ProductReference("vendor_lion", "LION-555", "https://lionelectronic.ir/p/555"),
            in_stock=True, can_order=True, base_unit_price_irr=85000
        )
        mutation = orchestrator.stage_candidate(cand, 20)
        assert mutation.success is True
        assert mutation.requested_quantity == 20
        assert mutation.actual_quantity_staged == 20
        assert mutation.vendor_id == "vendor_lion"
