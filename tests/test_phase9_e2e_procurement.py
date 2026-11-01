"""
End-to-End Multi-Vendor Procurement Integration Test Suite
Phase 9 — Step 8 Gate Certification
Governing Documents:
- docs/MASTER_PROJECT_SPECIFICATION.md
- docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md
- docs/PROCUREMENT/PHASE9_STEP8_SCOPE_AUDIT.md

Strictly offline: Zero Selenium, Zero live websites, Zero network dependencies.
Validates Mode A (Inventory Shortages and Altium BOM Assembly) lifecycles,
error handling, MOQ stepping, partial failure tolerance, and post-order inventory updates.
"""

import os
from typing import Any, Dict, List, Optional, Tuple
import openpyxl
import pytest

from bom_auditor import BOMAuditor
from excel_loader import ExcelDataLoader
from core.errors import (
    OmnixVendorError,
    OutOfStockError,
    ProductNotFoundError,
    TransportNetworkError,
    UnknownVendorError,
)
from core.models import (
    AdapterConfig,
    AdapterStatus,
    AuthCredentials,
    AuthResult,
    CanonicalComponentDraft,
    CartDetails,
    CartMutationResult,
    OrderConstraints,
    ProductDetails,
    ProductReference,
    RecoveryResult,
    SearchResultSet,
    SearchItem,
    SessionStatus,
    StockStatus,
)
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    PriceTier,
    ProcurementRequest,
    VendorProcurementCandidate,
    calculate_effective_quantity,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter


# ============================================================================
# Deterministic Mock Adapters for Multi-Vendor E2E Testing
# ============================================================================

class BaseE2EFakeAdapter(IVendorAdapter):
    """Base fake adapter for E2E tests implementing all 13 contract methods."""

    VENDOR_ID = "vendor_base"
    BASE_URL = "https://base.example.com"
    CATALOG: Dict[str, Dict[str, Any]] = {}
    FAIL_ON_STAGE = False
    FAIL_ERROR_TYPE: Optional[str] = None
    STAGED_CALLS: List[Tuple[ProductReference, int]] = []

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query: str) -> SearchResultSet:
        items: List[SearchItem] = []
        clean_q = query.strip().upper()
        for sku, info in self.CATALOG.items():
            mpn = info.get("mpn", sku).upper()
            if clean_q in mpn or clean_q in sku.upper() or clean_q in info.get("title", "").upper():
                items.append(
                    SearchItem(
                        vendor_sku=sku,
                        mpn_hint=info.get("mpn", sku),
                        title=info.get("title", sku),
                        pdp_url=info.get("url", f"{self.BASE_URL}/product/{sku}"),
                    )
                )
        return SearchResultSet(
            vendor_id=self.VENDOR_ID,
            query=query,
            total_matches=len(items),
            is_exact_match=any(clean_q == it.mpn_hint.upper() for it in items),
            items=items,
        )

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        sku = url_or_sku.rstrip("/").split("/")[-1]
        for s, info in self.CATALOG.items():
            if info.get("url") == url_or_sku or s == sku:
                sku = s
                break
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=sku,
            pdp_url=url_or_sku if url_or_sku.startswith("http") else f"{self.BASE_URL}/product/{sku}",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        info = self.CATALOG.get(product_ref.vendor_sku)
        if not info:
            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=product_ref.pdp_url,
                stock_quantity=1000,
                can_order=True,
                price_irr=50000,
                mpn=product_ref.vendor_sku,
            )
        if not info.get("in_stock", True):
            return ProductDetails(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                pdp_url=product_ref.pdp_url,
                stock_quantity=0,
                can_order=False,
                price_irr=0,
                mpn=info.get("mpn", product_ref.vendor_sku),
            )
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=info.get("stock_qty", 500),
            can_order=True,
            price_irr=info.get("price_irr", 10000),
            mpn=info.get("mpn", product_ref.vendor_sku),
            package_raw=info.get("package", "DIP-8"),
            order_constraints=OrderConstraints(
                packaging_step_raw=info.get("step", 1),
                moq_raw=info.get("moq", 1),
                max_orderable_raw=info.get("max_qty", None),
            ),
        )

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(
            vendor_id=self.VENDOR_ID,
            vendor_sku="E2E-SKU",
        )

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        info = self.CATALOG.get(product_ref.vendor_sku)
        if not info or not info.get("in_stock", True):
            return StockStatus(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                stock_quantity=0,
                in_stock=False,
                can_order=False,
            )
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=info.get("stock_qty", 500),
            in_stock=True,
            can_order=True,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        info = self.CATALOG.get(product_ref.vendor_sku, {})
        return OrderConstraints(
            packaging_step_raw=info.get("step", 1),
            moq_raw=info.get("moq", 1),
            max_orderable_raw=info.get("max_qty", None),
        )

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        if self.FAIL_ON_STAGE:
            if self.FAIL_ERROR_TYPE == "network":
                raise TransportNetworkError(f"Simulated network timeout for {self.VENDOR_ID}")
            elif self.FAIL_ERROR_TYPE == "out_of_stock":
                raise OutOfStockError(f"Simulated out of stock for {product_ref.vendor_sku}")
            else:
                raise OmnixVendorError(f"Simulated generic failure for {self.VENDOR_ID}")

        info = self.CATALOG.get(product_ref.vendor_sku, {})
        if not info.get("in_stock", True) and product_ref.vendor_sku in self.CATALOG:
            raise OutOfStockError(f"Item {product_ref.vendor_sku} is out of stock at {self.VENDOR_ID}")

        self.STAGED_CALLS.append((product_ref, quantity))
        return CartMutationResult(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
            raw_vendor_message="Staged successfully in cart",
            cart_total_items=len(self.STAGED_CALLS),
        )

    def inspect_cart(self) -> CartDetails:
        total = sum(q * 10000 for _, q in self.STAGED_CALLS)
        return CartDetails(
            vendor_id=self.VENDOR_ID,
            cart_url=f"{self.BASE_URL}/cart",
            total_items=len(self.STAGED_CALLS),
            total_amount_irr=total,
        )

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="noop", message="OK")

    def close(self) -> None:
        pass


class FakeLionE2EAdapter(BaseE2EFakeAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"
    CATALOG = {
        "2070-NE555P": {
            "mpn": "NE555P",
            "title": "NE555P Timer DIP-8",
            "url": "https://lionelectronic.ir/products/2070-NE555P",
            "in_stock": True,
            "stock_qty": 200,
            "price_irr": 25000,
            "moq": 1,
            "step": 1,
        },
        "1932-LM358N": {
            "mpn": "LM358N",
            "title": "LM358N Dual OpAmp",
            "url": "https://lionelectronic.ir/products/1932-LM358N",
            "in_stock": True,
            "stock_qty": 150,
            "price_irr": 30000,
            "moq": 1,
            "step": 1,
        },
        "1001-OOS": {
            "mpn": "OOS-CHIP",
            "title": "Out of Stock Chip",
            "url": "https://lionelectronic.ir/products/1001-OOS",
            "in_stock": False,
            "stock_qty": 0,
            "price_irr": 0,
            "moq": 1,
            "step": 1,
        },
    }
    FAIL_ON_STAGE = False
    FAIL_ERROR_TYPE = None
    STAGED_CALLS = []


class FakeJavanE2EAdapter(BaseE2EFakeAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"
    CATALOG = {
        "101-STM32F103": {
            "mpn": "STM32F103C8T6",
            "title": "STM32F103C8T6 ARM MCU",
            "url": "https://javanelec.com/product/101/STM32F103",
            "package": "LQFP-48",
            "in_stock": True,
            "stock_qty": 50,
            "price_irr": 180000,
            "moq": 1,
            "step": 1,
        },
        "102-AMS1117-3.3": {
            "mpn": "AMS1117-3.3",
            "title": "AMS1117 3.3V LDO SOT-223",
            "url": "https://javanelec.com/product/102/AMS1117",
            "package": "SOT-223",
            "in_stock": True,
            "stock_qty": 1000,
            "price_irr": 8000,
            "moq": 5,
            "step": 5,
        },
    }
    FAIL_ON_STAGE = False
    FAIL_ERROR_TYPE = None
    STAGED_CALLS = []


class FakeRoboEqE2EAdapter(BaseE2EFakeAdapter):
    VENDOR_ID = "vendor_roboeq"
    BASE_URL = "https://roboeq.ir"
    CATALOG = {
        "0101001": {
            "mpn": "ATMEGA328P-PU",
            "title": "ATmega328P DIP-28 AVR MCU",
            "url": "https://roboeq.ir/products/detail/0101001/",
            "package": "DIP-28",
            "in_stock": True,
            "stock_qty": 80,
            "price_irr": 220000,
            "moq": 1,
            "step": 1,
        },
        "0202002": {
            "mpn": "100UF-25V-SMD",
            "title": "100uF 25V SMD Electrolytic Capacitor",
            "url": "https://roboeq.ir/products/detail/0202002/",
            "package": "SMD",
            "in_stock": True,
            "stock_qty": 500,
            "price_irr": 12000,
            "moq": 10,
            "step": 10,
        },
    }
    FAIL_ON_STAGE = False
    FAIL_ERROR_TYPE = None
    STAGED_CALLS = []


# ============================================================================
# Test Fixtures & Registry Setup
# ============================================================================

@pytest.fixture
def clean_registry():
    """Provides an isolated registry populated with mock adapter classes for all 3 vendors."""
    FakeLionE2EAdapter.STAGED_CALLS = []
    FakeLionE2EAdapter.FAIL_ON_STAGE = False
    FakeLionE2EAdapter.FAIL_ERROR_TYPE = None

    FakeJavanE2EAdapter.STAGED_CALLS = []
    FakeJavanE2EAdapter.FAIL_ON_STAGE = False
    FakeJavanE2EAdapter.FAIL_ERROR_TYPE = None

    FakeRoboEqE2EAdapter.STAGED_CALLS = []
    FakeRoboEqE2EAdapter.FAIL_ON_STAGE = False
    FakeRoboEqE2EAdapter.FAIL_ERROR_TYPE = None

    reg = VendorRegistry.get_default_registry()
    reg.clear()

    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=FakeLionE2EAdapter,
        display_name="Lion Electronic",
        domains=["lionelectronic.ir", "www.lionelectronic.ir"],
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=FakeJavanE2EAdapter,
        display_name="Javan Electronic",
        domains=["javanelec.com", "www.javanelec.com"],
    )
    reg.register_adapter(
        vendor_id="vendor_roboeq",
        adapter_class=FakeRoboEqE2EAdapter,
        display_name="RoboEq Electronic",
        domains=["roboeq.ir", "www.roboeq.ir"],
    )

    yield {
        "registry": reg,
        "lion_cls": FakeLionE2EAdapter,
        "javan_cls": FakeJavanE2EAdapter,
        "roboeq_cls": FakeRoboEqE2EAdapter,
    }
    reg.clear()


# ============================================================================
# Test Suite 1: Mode A — Inventory Shortages End-to-End Lifecycle
# ============================================================================

class TestModeAInventoryShortagesEndToEnd:
    """Validates Mode A: Inventory.xlsx -> Shortage Extraction -> Orchestrator -> Cart Staging -> Stock Update."""

    def test_mode_a_full_procurement_lifecycle(self, clean_registry, tmp_path):
        reg = clean_registry["registry"]
        lion_cls = clean_registry["lion_cls"]
        javan_cls = clean_registry["javan_cls"]
        roboeq_cls = clean_registry["roboeq_cls"]

        # 1. Create an Inventory.xlsx with known shortages across 3 vendors + unorderable links
        inv_path = os.path.join(str(tmp_path), "Inventory.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventory"
        ws.append([
            "Row", "ECODE", "PART NAME", "DISCRIPTION", "Quantity in Stock",
            "Min Stock", "Target Stock", "FOOTPRINT", "PART NUMBER", "LINK"
        ])
        # Row 2: Lion shortage (Stock: 2, Min: 10, Target: 20 -> Needed: 18)
        ws.append([1, None, "NE555P", "Timer IC", 2, 10, 20, "DIP-8", "NE555P", "https://lionelectronic.ir/products/2070-NE555P"])
        # Row 3: Javan shortage with MOQ/step=5 (Stock: 1, Min: 20, Target: 50 -> Needed: 49 -> Effective: 50)
        ws.append([2, None, "AMS1117-3.3", "LDO 3.3V", 1, 20, 50, "SOT-223", "AMS1117-3.3", "https://javanelec.com/product/102/AMS1117"])
        # Row 4: RoboEq shortage with MOQ/step=10 (Stock: 0, Min: 5, Target: 15 -> Needed: 15 -> Effective: 20)
        ws.append([3, None, "100uF 25V", "SMD Cap", 0, 5, 15, "SMD", "100UF-25V-SMD", "https://roboeq.ir/products/detail/0202002/"])
        # Row 5: Digikey unsupported link (Stock: 0, Min: 10, Target: 20 -> Needed: 20 -> Unorderable)
        ws.append([4, None, "OPA2134", "Audio OpAmp", 0, 10, 20, "SOIC-8", "OPA2134", "https://www.digikey.com/en/products/OPA2134"])
        # Row 6: Blank link (Stock: 1, Min: 10, Target: 10 -> Needed: 9 -> Unorderable)
        ws.append([5, None, "Resistor 1k", "1% Resistor", 1, 10, 10, "0805", "RC0805-1K", None])
        # Row 7: Sufficient stock (Stock: 100, Min: 10, Target: 20 -> Needed: 0 -> Not a shortage)
        ws.append([6, None, "LED Green", "Green LED", 100, 10, 20, "0805", "LED-0805-G", "https://lionelectronic.ir/products/2070-NE555P"])

        wb.save(inv_path)
        wb.close()

        # 2. Load inventory data via ExcelDataLoader
        loader = ExcelDataLoader()
        loader.load_file(inv_path)
        shortages = loader.get_shortage_items(registry=reg)

        # Assert mathematical shortage detection
        assert len(shortages) == 5
        shortage_map = {s["part_name"]: s for s in shortages}

        assert shortage_map["NE555P"]["needed_qty"] == 18
        assert shortage_map["NE555P"]["vendor_id"] == "vendor_lion"
        assert shortage_map["NE555P"]["is_orderable"] is True

        assert shortage_map["AMS1117-3.3"]["needed_qty"] == 49
        assert shortage_map["AMS1117-3.3"]["vendor_id"] == "vendor_javan"
        assert shortage_map["AMS1117-3.3"]["is_orderable"] is True

        assert shortage_map["100uF 25V"]["needed_qty"] == 15
        assert shortage_map["100uF 25V"]["vendor_id"] == "vendor_roboeq"
        assert shortage_map["100uF 25V"]["is_orderable"] is True

        assert shortage_map["OPA2134"]["is_orderable"] is False
        assert shortage_map["Resistor 1k"]["is_orderable"] is False

        # 3. Filter orderable items and convert to ProcurementRequests
        orderable_items = [s for s in shortages if s.get("is_orderable")]
        assert len(orderable_items) == 3

        requests = [ProcurementBridge.item_to_request(s, registry=reg) for s in orderable_items]
        assert len(requests) == 3

        # 4. Plan and stage procurement via Universal Procurement Orchestrator
        orchestrator = UniversalProcurementOrchestrator(registry=reg)
        plan = orchestrator.build_plan(requests)

        assert plan.is_complete is True
        assert len(plan.results) == 3

        stage_results = []
        for r in plan.results:
            assert r.status == "RESOLVED"
            assert r.selected_evaluation is not None
            sr = orchestrator.stage_candidate(
                r.selected_evaluation.candidate,
                r.selected_evaluation.effective_quantity,
            )
            stage_results.append(sr)

        assert len(stage_results) == 3
        assert all(sr.success for sr in stage_results)

        # 5. Verify vendor-specific cart staging
        assert len(lion_cls.STAGED_CALLS) == 1
        assert lion_cls.STAGED_CALLS[0][0].vendor_sku == "2070-NE555P"
        assert lion_cls.STAGED_CALLS[0][1] == 18

        assert len(javan_cls.STAGED_CALLS) == 1
        assert javan_cls.STAGED_CALLS[0][0].vendor_sku == "102-AMS1117-3.3"
        assert javan_cls.STAGED_CALLS[0][1] == 50  # 49 stepped to 50 due to step=5

        assert len(roboeq_cls.STAGED_CALLS) == 1
        assert roboeq_cls.STAGED_CALLS[0][0].vendor_sku == "0202002"
        assert roboeq_cls.STAGED_CALLS[0][1] == 20  # 15 stepped to 20 due to step=10

        # 6. Verify strict inventory immutability: procurement staging does not alter stock
        assert not hasattr(loader, "batch_increment_stock")
        assert not hasattr(loader, "save_cell_value")

        # 7. Reload file from disk and assert inventory stock levels remain strictly untouched
        reloaded_loader = ExcelDataLoader()
        reloaded_loader.load_file(inv_path)
        persisted_shortages = reloaded_loader.get_shortage_items()
        persisted_names = {s["part_name"] for s in persisted_shortages}
        assert "NE555P" in persisted_names
        assert "AMS1117-3.3" in persisted_names
        assert "100uF 25V" in persisted_names
        assert "OPA2134" in persisted_names
        assert "Resistor 1k" in persisted_names


# ============================================================================
# Test Suite 2: Mode A — Altium BOM Assembly End-to-End Lifecycle
# ============================================================================

class TestModeAAltiumBOMAssemblyEndToEnd:
    """Validates Mode A: Altium BOM -> Multiplier Calculation -> Audit -> Multi-Vendor Staging -> Stock Update."""

    def test_mode_a_full_assembly_procurement_lifecycle(self, clean_registry, tmp_path):
        reg = clean_registry["registry"]
        lion_cls = clean_registry["lion_cls"]
        javan_cls = clean_registry["javan_cls"]
        roboeq_cls = clean_registry["roboeq_cls"]

        # 1. Create Inventory.xlsx
        inv_path = os.path.join(str(tmp_path), "Inventory.xlsx")
        inv_wb = openpyxl.Workbook()
        ws_inv = inv_wb.active
        ws_inv.title = "Inventory"
        ws_inv.append(["ECODE", "PART NAME", "DISCRIPTION", "Quantity in Stock", "FOOTPRINT", "PART NUMBER", "LINK"])
        ws_inv.append([None, "NE555P", "Timer IC", 10, "DIP-8", "NE555P", "https://lionelectronic.ir/products/2070-NE555P"])
        ws_inv.append([None, "STM32F103C8T6", "MCU", 2, "LQFP-48", "STM32F103C8T6", "https://javanelec.com/product/101/STM32F103"])
        ws_inv.append([None, "ATMEGA328P-PU", "AVR MCU", 5, "DIP-28", "ATMEGA328P-PU", "https://roboeq.ir/products/detail/0101001/"])
        ws_inv.append([None, "100uF 25V", "Capacitor", 100, "SMD", "100UF-25V-SMD", "https://roboeq.ir/products/detail/0202002/"])
        inv_wb.save(inv_path)
        inv_wb.close()

        # 2. Create Sample_BOM.xlsx
        bom_path = os.path.join(str(tmp_path), "Sample_BOM.xlsx")
        bom_wb = openpyxl.Workbook()
        ws_bom = bom_wb.active
        ws_bom.append(["Designator", "Quantity", "Comment", "Footprint", "Description", "Part Number"])
        ws_bom.append(["U1", 1, "NE555P", "DIP-8", "Timer", "NE555P"])
        ws_bom.append(["U2", 1, "STM32F103C8T6", "LQFP-48", "ARM MCU", "STM32F103C8T6"])
        ws_bom.append(["U3", 2, "ATMEGA328P-PU", "DIP-28", "AVR MCU", "ATMEGA328P-PU"])
        ws_bom.append(["C1, C2", 2, "100uF 25V", "SMD", "Capacitor", "100UF-25V-SMD"])
        bom_wb.save(bom_path)
        bom_wb.close()

        # 3. Run BOM Auditor with board multiplier = 10
        inv_loader = ExcelDataLoader()
        inv_loader.load_file(inv_path)

        ok, msg, audit_res = BOMAuditor.audit_bom(bom_path, inv_loader, board_multiplier=10)
        assert ok is True
        assert audit_res is not None
        assert audit_res.board_multiplier == 10

        # Mathematical verification:
        # - NE555P: 1 * 10 = 10 needed, in stock = 10 -> Shortage = 0 (IN_STOCK)
        # - STM32F103: 1 * 10 = 10 needed, in stock = 2 -> Shortage = 8 (SHORTAGE) -> Javan
        # - ATmega328P: 2 * 10 = 20 needed, in stock = 5 -> Shortage = 15 (SHORTAGE) -> RoboEq
        # - 100uF: 2 * 10 = 20 needed, in stock = 100 -> Shortage = 0 (IN_STOCK)
        orderable = audit_res.get_orderable_shortages()
        assert len(orderable) == 2

        orderable_map = {it["part_number"]: it for it in orderable}
        assert orderable_map["STM32F103C8T6"]["needed_qty"] == 8
        assert orderable_map["STM32F103C8T6"]["vendor_id"] == "vendor_javan"

        assert orderable_map["ATMEGA328P-PU"]["needed_qty"] == 15
        assert orderable_map["ATMEGA328P-PU"]["vendor_id"] == "vendor_roboeq"

        # 4. Convert to ProcurementRequests and stage via orchestrator
        requests = [ProcurementBridge.item_to_request(it, registry=reg) for it in orderable]
        orchestrator = UniversalProcurementOrchestrator(registry=reg)
        plan = orchestrator.build_plan(requests)

        assert plan.is_complete is True
        stage_results = []
        for r in plan.results:
            assert r.status == "RESOLVED"
            assert r.selected_evaluation is not None
            sr = orchestrator.stage_candidate(
                r.selected_evaluation.candidate,
                r.selected_evaluation.effective_quantity,
            )
            stage_results.append(sr)

        assert len(stage_results) == 2
        assert all(sr.success for sr in stage_results)

        # Assert staging dispatch
        assert len(lion_cls.STAGED_CALLS) == 0
        assert len(javan_cls.STAGED_CALLS) == 1
        assert javan_cls.STAGED_CALLS[0][1] == 8
        assert len(roboeq_cls.STAGED_CALLS) == 1
        assert roboeq_cls.STAGED_CALLS[0][1] == 15

        # 5. Verify strict inventory immutability: BOM fulfillment does not alter stock
        assert not hasattr(inv_loader, "batch_increment_stock")
        assert not hasattr(inv_loader, "save_cell_value")

        # 6. Verify inventory stock on disk remains strictly untouched
        inv_loader_reloaded = ExcelDataLoader()
        inv_loader_reloaded.load_file(inv_path)
        stock_col = inv_loader_reloaded.get_column_index(["quantity in stock"])
        stm_row_cells = next(r for idx, r in inv_loader_reloaded.rows if "STM32F103" in " ".join(r))
        mcu_row_cells = next(r for idx, r in inv_loader_reloaded.rows if "ATMEGA328P" in " ".join(r))
        assert stm_row_cells[stock_col] == "2"   # untouched original stock
        assert mcu_row_cells[stock_col] == "5"   # untouched original stock


# ============================================================================
# Test Suite 3: Multi-Vendor Edge Cases & Fault Tolerance
# ============================================================================

class TestMultiVendorProcurementEdgeCases:
    """Validates edge cases: 100% stock, OOS items, network failure resilience, direct URL routing."""

    def test_zero_shortage_batch_handling(self, clean_registry):
        reg = clean_registry["registry"]
        orchestrator = UniversalProcurementOrchestrator(registry=reg)

        plan = orchestrator.build_plan([])
        assert plan.total_items == 0
        assert len(plan.results) == 0

    def test_out_of_stock_item_handling(self, clean_registry):
        reg = clean_registry["registry"]
        lion_cls = clean_registry["lion_cls"]

        # Item 1001-OOS is marked out of stock in Lion catalog
        req = ProcurementRequest(
            part_number="OOS-CHIP",
            required_quantity=5,
            explicit_vendor_id="vendor_lion",
            explicit_vendor_url="https://lionelectronic.ir/products/1001-OOS",
            exact_mpn_required=False,
        )
        orchestrator = UniversalProcurementOrchestrator(registry=reg)
        plan = orchestrator.build_plan([req])

        # Plan evaluation should be unresolved / out of stock
        assert plan.is_complete is False
        res_item = plan.results[0]
        assert res_item.status in ("OUT_OF_STOCK", "UNRESOLVED")
        assert res_item.selected_evaluation is None
        assert len(lion_cls.STAGED_CALLS) == 0

    def test_partial_vendor_failure_tolerance(self, clean_registry):
        """If one vendor encounters a network error, other vendor staging operations still succeed."""
        reg = clean_registry["registry"]
        lion_cls = clean_registry["lion_cls"]
        javan_cls = clean_registry["javan_cls"]
        roboeq_cls = clean_registry["roboeq_cls"]

        # Javan adapter simulates transport network error
        javan_cls.FAIL_ON_STAGE = True
        javan_cls.FAIL_ERROR_TYPE = "network"

        batch_items = [
            {
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 10,
                "link": "https://lionelectronic.ir/products/2070-NE555P",
                "is_orderable": True,
                "vendor_id": "vendor_lion",
                "orig_row_idx": 2,
            },
            {
                "part_name": "STM32F103",
                "part_number": "STM32F103C8T6",
                "needed_qty": 5,
                "link": "https://javanelec.com/product/101/STM32F103",
                "is_orderable": True,
                "vendor_id": "vendor_javan",
                "orig_row_idx": 3,
            },
            {
                "part_name": "ATmega328P",
                "part_number": "ATMEGA328P-PU",
                "needed_qty": 4,
                "link": "https://roboeq.ir/products/detail/0101001/",
                "is_orderable": True,
                "vendor_id": "vendor_roboeq",
                "orig_row_idx": 4,
            },
        ]

        batch_res = ProcurementBridge.execute_staged_procurement_batch(batch_items, registry=reg)

        assert batch_res["successful_count"] == 2
        assert batch_res["failed_count"] == 1
        assert len(batch_res["results"]) == 3

        # Lion and RoboEq succeeded
        assert len(lion_cls.STAGED_CALLS) == 1
        assert lion_cls.STAGED_CALLS[0][1] == 10

        assert len(roboeq_cls.STAGED_CALLS) == 1
        assert roboeq_cls.STAGED_CALLS[0][1] == 4

        # Javan recorded as failure with error detail
        javan_failure = next(r for r in batch_res["results"] if "javan" in r.get("msg", "").lower() or r.get("part") == "STM32F103")
        assert javan_failure["status"] == "FAILED"

    def test_direct_url_vs_catalog_search_selection(self, clean_registry):
        """Explicit URL bypasses catalog search; missing URL searches all registered adapters."""
        reg = clean_registry["registry"]
        lion_cls = clean_registry["lion_cls"]

        # Item with direct URL
        item_direct = {
            "part_name": "NE555P",
            "needed_qty": 10,
            "link": "https://lionelectronic.ir/products/2070-NE555P",
        }
        req_direct = ProcurementBridge.item_to_request(item_direct, registry=reg)
        assert req_direct.explicit_vendor_id == "vendor_lion"
        assert req_direct.explicit_vendor_url == "https://lionelectronic.ir/products/2070-NE555P"
        assert req_direct.exact_mpn_required is True

        # Item without direct URL (generic catalog search)
        item_generic = {
            "part_name": "NE555P",
            "part_number": "NE555P",
            "needed_qty": 10,
            "link": None,
        }
        req_generic = ProcurementBridge.item_to_request(item_generic, registry=reg)
        assert req_generic.explicit_vendor_id is None
        assert req_generic.explicit_vendor_url is None
        assert req_generic.exact_mpn_required is True

        # Orchestrator should find candidate via catalog search across all vendors
        orchestrator = UniversalProcurementOrchestrator(registry=reg)
        plan = orchestrator.build_plan([req_generic])

        assert plan.is_complete is True
        res_item = plan.results[0]
        assert res_item.selected_evaluation is not None
        assert res_item.selected_evaluation.candidate.vendor_id == "vendor_lion"
        assert res_item.selected_evaluation.candidate.part_number == "NE555P"
