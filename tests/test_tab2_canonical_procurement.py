"""
Tests for Tab 2 (Altium BOM Project Auditor) Canonical Procurement Semantics:
- Mode A (Database-Aware / Inventory-Driven):
  * Direct purchasing strictly targeting the Inventory.xlsx link.
  * Validation of MPN, Package, Footprint, Specs, Dimensions.
  * Brand double-check only if BOM specified an explicit brand; passes if ANY.
  * Strict typed failures on mismatch (INCOMPATIBLE_MPN, INCOMPATIBLE_PACKAGE, etc.).
  * No multi-vendor fallback or silent vendor substitution.
- Mode B (BOM-Direct / Turnkey):
  * Multi-vendor discovery across all enabled registered vendors.
  * Brand Rule handling (ANY, single brand, approved list).
  * Canonical quantity calculation (if req < moq: moq; else: ceil(req/step)*step).
  * Deterministic price & quantity ranking.
- 7 Historical Safeguards:
  * Strict live site stock (NO-PARTIAL-STOCK).
  * Out of stock & unorderable detection.
"""

import os
import openpyxl
import pytest
from tempfile import NamedTemporaryFile
from typing import List, Dict, Any, Optional

from bom_auditor import BOMAuditor, BOMItem, BOMAuditResult
from core.models import (
    AdapterStatus,
    OrderConstraints,
    ProductDetails,
    ProductReference,
    SearchResultSet,
    SearchItem,
    StockStatus,
)
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    ManufacturerRule,
    ManufacturerDataState,
    ProcurementMode,
    ProcurementRequest,
    VendorProcurementCandidate,
    calculate_effective_quantity,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter
from excel_loader import ExcelDataLoader


class MockLionTab2Adapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"
    
    def __init__(self, config=None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config=None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        sku = url_or_sku.rstrip("/").split("/")[-1]
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=sku,
            pdp_url=url_or_sku if url_or_sku.startswith("http") else f"{self.BASE_URL}/product/{sku}",
        )

    def search_part(self, query: str) -> SearchResultSet:
        if "NE555" in query.upper():
            return SearchResultSet(
                vendor_id=self.VENDOR_ID,
                query=query,
                total_matches=1,
                is_exact_match=True,
                items=[
                    SearchItem(
                        vendor_sku="LION-555",
                        mpn_hint="NE555P",
                        title="NE555P Timer TI",
                        pdp_url="https://lionelectronic.ir/product/lion-555",
                    )
                ],
            )
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False, items=[])

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        if "lion-555" in product_ref.vendor_sku.lower() or "101" in product_ref.vendor_sku:
            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=product_ref.pdp_url,
                stock_quantity=100,
                can_order=True,
                price_irr=5000,
                mpn="NE555P",
                manufacturer="Texas Instruments",
                package_raw="DIP-8",
                order_constraints=OrderConstraints(moq_raw=10, packaging_step_raw=10),
            )
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=50,
            can_order=True,
            price_irr=10000,
            mpn=product_ref.vendor_sku,
            package_raw="DIP-8",
        )

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        details = self.inspect_product(product_ref)
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.stock_quantity > 0,
            can_order=details.can_order,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        details = self.inspect_product(product_ref)
        return details.order_constraints or OrderConstraints()

    def extract_product_data(self, dom_context=None):
        return None

    def add_to_cart(self, product_ref, quantity):
        return None

    def inspect_cart(self):
        return None

    def authenticate(self, credentials=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context=None):
        return None

    def close(self):
        pass


class MockJavanTab2Adapter(IVendorAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"

    def __init__(self, config=None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config=None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        sku = url_or_sku.rstrip("/").split("/")[-1]
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=sku,
            pdp_url=url_or_sku if url_or_sku.startswith("http") else f"{self.BASE_URL}/item/{sku}",
        )

    def search_part(self, query: str) -> SearchResultSet:
        if "NE555" in query.upper():
            return SearchResultSet(
                vendor_id=self.VENDOR_ID,
                query=query,
                total_matches=1,
                is_exact_match=True,
                items=[
                    SearchItem(
                        vendor_sku="JAV-555",
                        mpn_hint="NE555P",
                        title="NE555P Timer ST",
                        pdp_url="https://javanelec.com/item/jav-555",
                    )
                ],
            )
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False, items=[])

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        if "jav-555" in product_ref.vendor_sku.lower() or "202" in product_ref.vendor_sku:
            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=product_ref.pdp_url,
                stock_quantity=200,
                can_order=True,
                price_irr=4500,
                mpn="NE555P",
                manufacturer="STMicroelectronics",
                package_raw="DIP-8",
                order_constraints=OrderConstraints(moq_raw=5, packaging_step_raw=5),
            )
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=10,
            can_order=True,
            price_irr=20000,
            mpn=product_ref.vendor_sku,
            package_raw="DIP-8",
        )

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        details = self.inspect_product(product_ref)
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=details.stock_quantity,
            in_stock=details.stock_quantity > 0,
            can_order=details.can_order,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        details = self.inspect_product(product_ref)
        return details.order_constraints

    def extract_product_data(self, dom_context=None):
        return None

    def add_to_cart(self, product_ref, quantity):
        return None

    def inspect_cart(self):
        return None

    def authenticate(self, credentials=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context=None):
        return None

    def close(self):
        pass


@pytest.fixture
def tab2_registry():
    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionTab2Adapter,
        display_name="Lion Electronic",
        domains=["lionelectronic.ir"],
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=MockJavanTab2Adapter,
        display_name="Javan Electronic",
        domains=["javanelec.com"],
    )
    return reg


class TestModeAValidationAndSafeguards:
    """Mode A tests: Database-aware direct purchasing strictly using Inventory.xlsx LINK."""

    def test_mode_a_direct_purchasing_validates_mpn_and_brand_any(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mode A item with link from Inventory.xlsx to Lion and Brand = ANY
        req = ProcurementRequest(
            part_number="NE555P",
            required_quantity=7,
            explicit_vendor_id="vendor_lion",
            explicit_vendor_url="https://lionelectronic.ir/product/101",
            is_manufacturer_any=True,
            package="DIP-8",
            footprint="DIP-8",
            mode=ProcurementMode.DATABASE_AWARE,
        )

        plan = orchestrator.build_plan([req])
        assert plan.is_complete is True
        res = plan.results[0]
        assert res.status == "RESOLVED"
        assert res.selected_evaluation is not None
        assert res.selected_evaluation.is_eligible is True
        assert res.selected_evaluation.candidate.vendor_id == "vendor_lion"
        # Canonical quantity rule: req=7 < MOQ=10 -> effective_quantity = 10
        assert res.selected_evaluation.effective_quantity == 10
        assert res.selected_evaluation.effective_unit_price_irr == 5000
        assert res.selected_evaluation.effective_total_price_irr == 50000

    def test_mode_a_direct_purchasing_brand_mismatch_fails_without_substitution(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mode A item with link to Javan (STMicroelectronics), but BOM specifies Texas Instruments
        req = ProcurementRequest(
            part_number="NE555P",
            required_quantity=5,
            explicit_vendor_id="vendor_javan",
            explicit_vendor_url="https://javanelec.com/item/202",
            manufacturer="Texas Instruments",
            is_manufacturer_any=False,
            mode=ProcurementMode.DATABASE_AWARE,
        )

        plan = orchestrator.build_plan([req])
        assert plan.is_complete is False
        res = plan.results[0]
        assert res.status == "UNRESOLVED"
        assert res.selected_evaluation is None
        assert len(res.evaluations) == 1
        ev = res.evaluations[0]
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_MANUFACTURER
        # Must NOT silently switch to Lion even though Lion sells TI!
        assert len(res.candidates) == 1
        assert res.candidates[0].vendor_id == "vendor_javan"

    def test_mode_a_direct_purchasing_package_mismatch_fails(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mode A item linked to DIP-8 product, but BOM requires SOP-8
        req = ProcurementRequest(
            part_number="NE555P",
            required_quantity=5,
            explicit_vendor_id="vendor_lion",
            explicit_vendor_url="https://lionelectronic.ir/product/101",
            is_manufacturer_any=True,
            package="SOP-8",
            mode=ProcurementMode.DATABASE_AWARE,
        )

        plan = orchestrator.build_plan([req])
        assert plan.is_complete is False
        res = plan.results[0]
        assert res.status == "UNRESOLVED"
        assert res.selected_evaluation is None
        assert res.evaluations[0].state == EvaluationState.INCOMPATIBLE_PACKAGE

    def test_mode_a_insufficient_site_stock_fails_safeguard(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mock candidate with site stock = 5, but needed = 10
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="L101", pdp_url="https://lionelectronic.ir/product/101"),
            in_stock=True,
            stock_quantity=5,
            can_order=True,
            base_unit_price_irr=5000,
            order_constraints=OrderConstraints(moq_raw=10, packaging_step_raw=10),
        )
        ev = orchestrator.evaluate_candidate(cand, required_quantity=7)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.OUT_OF_STOCK
        assert any("Insufficient stock" in r for r in ev.rejection_reasons)


class TestModeBTurnkeySourcing:
    """Mode B tests: Pure CAD BOM turnkey sourcing across all enabled vendors."""

    def test_mode_b_multi_vendor_discovery_and_cost_ranking(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mode B request for NE555P (ANY brand, needed=10)
        # Lion: 5000 IRR, MOQ 10 -> total = 50,000 IRR
        # Javan: 4500 IRR, MOQ 5, step 5 -> needed 10 -> total = 45,000 IRR (Javan is cheaper)
        req = ProcurementRequest(
            part_number="NE555P",
            required_quantity=10,
            is_manufacturer_any=True,
            mode=ProcurementMode.DIRECT_BOM,
        )

        plan = orchestrator.build_plan([req])
        assert plan.is_complete is True
        res = plan.results[0]
        assert len(res.candidates) == 2
        # Javan should be selected because total cost (45,000 IRR) is lower than Lion (50,000 IRR)
        assert res.selected_evaluation is not None
        assert res.selected_evaluation.candidate.vendor_id == "vendor_javan"
        assert res.selected_evaluation.effective_total_price_irr == 45000

    def test_mode_b_brand_rule_filtering(self, tab2_registry):
        reg = tab2_registry
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        # Mode B request with Brand = "Texas Instruments"
        # Javan (ST) is disqualified; Lion (TI) is selected
        req = ProcurementRequest(
            part_number="NE555P",
            required_quantity=10,
            manufacturer="Texas Instruments",
            is_manufacturer_any=False,
            mode=ProcurementMode.DIRECT_BOM,
        )

        plan = orchestrator.build_plan([req])
        assert plan.is_complete is True
        res = plan.results[0]
        assert len(res.candidates) == 2
        assert res.selected_evaluation is not None
        assert res.selected_evaluation.candidate.vendor_id == "vendor_lion"
        assert res.selected_evaluation.candidate.manufacturer == "Texas Instruments"


class TestCanonicalQuantityCalculation:
    """Verifies Layer 5 Canonical Quantity Rule."""

    def test_canonical_moq_and_step_formula(self):
        # Case 1: needed < moq -> final = moq
        assert calculate_effective_quantity(needed_qty=3, moq=10, packaging_step=5) == 10
        assert calculate_effective_quantity(needed_qty=1, moq=100, packaging_step=10) == 100

        # Case 2: needed >= moq -> final = ceil(needed / step) * step
        assert calculate_effective_quantity(needed_qty=12, moq=10, packaging_step=5) == 15
        assert calculate_effective_quantity(needed_qty=20, moq=10, packaging_step=10) == 20
        assert calculate_effective_quantity(needed_qty=21, moq=10, packaging_step=10) == 30
