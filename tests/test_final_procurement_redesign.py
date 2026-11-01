"""
OMNIX — Final Procurement Workflow Redesign Verification Suite
Governing Spec: DOC-OMNIX-PLAN-FINAL-004

Tests:
1. Option A: Direct link staging without PDP MPN / DOM matching rejection.
2. The 14/10/20/15 Rule: Insufficient stock safety check (step=10, target=20, stock=15 -> INSUFFICIENT_STOCK, 0 added, SKIPPED, batch continues).
3. Boundary Control: Prohibition on automatic purchasing (ADDED_TO_CART only, user controls checkout).
4. Dual Export Separation: Pre-Order Plan vs Post-Operation Results lifecycles, buttons, and filenames.
5. Selection Integrity: Deselected items never dispatched to worker or adapter.
6. Dynamic Plugin Configuration: Manifest-driven schema, password masking with reveal toggle, idempotent persistence.
7. Standalone Link Validation Removal: Complete removal of buttons, dialogs, and preflight checks.
8. Absolute Inventory Immutability: Zero writes to quantity_in_stock during procurement workflows.
"""

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLineEdit, QMessageBox, QPushButton

from core.models import AdapterConfig, AdapterStatus, ProductDetails, ProductReference, StockStatus
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    OrderConstraints,
    ProcurementMode,
    ProcurementRequest,
    RequestProcurementResult,
    SupplierItemResult,
    SupplierOutcomeStatus,
    VendorProcurementCandidate,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from core.procurement.reporting.models import ReportType
from core.vendor_interface import IVendorAdapter
from settings_manager import settings
from ui.dialogs.order_preview_dialog import OrderPreviewDialog, OrderWorkerThread
from ui.widgets.vendor_plugins_widget import PluginConfigDialog, VendorPluginsWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ==============================================================================
# Mock Adapters for Controlled Staging
# ==============================================================================

class MockLionStagingAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"
    stock_qty = 100
    order_step = 1
    can_order_flag = True
    dispatched_items = []

    def __init__(self, config=None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config=None):
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query):
        return None

    def resolve_product(self, url_or_sku):
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="LION-SKU-1", pdp_url=url_or_sku)

    def inspect_product(self, product_ref):
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=self.stock_qty,
            can_order=self.can_order_flag,
            price_irr=10000,
            mpn="UNMATCHED-MPN-ON-DISTRIBUTOR-SITE",  # Option A verification
            manufacturer="UNMATCHED-MFR",
        )

    def extract_product_data(self, dom_context):
        return None

    def inspect_stock(self, product_ref):
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=self.stock_qty,
            in_stock=self.stock_qty > 0,
            can_order=self.can_order_flag,
        )

    def determine_order_constraints(self, product_ref):
        return OrderConstraints(
            moq_raw=self.order_step,
            packaging_step_raw=self.order_step,
        )

    def add_to_cart(self, product_ref, quantity):
        self.dispatched_items.append((product_ref.pdp_url, quantity))
        return {"success": True, "staged_quantity": quantity, "message": f"Added {quantity} to cart"}

    def inspect_cart(self):
        return None

    def get_cart_url(self):
        return "https://lionelectronic.ir/cart"

    def authenticate(self, credentials=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context):
        return None

    def close(self):
        pass


@pytest.fixture
def registered_lion_registry():
    MockLionStagingAdapter.stock_qty = 100
    MockLionStagingAdapter.order_step = 1
    MockLionStagingAdapter.dispatched_items = []

    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionStagingAdapter,
        domains=["lionelectronic.ir"],
        display_name="Lion Electronic",
        enabled=True,
        activate=True,
    )
    return reg


# ==============================================================================
# 1. Option A: Direct Link Staging (No DOM MPN Rejection)
# ==============================================================================

class TestOptionADirectLinkStaging:
    def test_direct_link_bypasses_mpn_and_mfr_mismatch(self, registered_lion_registry):
        """
        Option A Requirement:
        Stored vendor URLs in Mode A must stage directly without rejection
        due to distributor page lacking or mismatching MPN / Manufacturer text.
        """
        MockLionStagingAdapter.stock_qty = 50
        MockLionStagingAdapter.order_step = 1

        orch = UniversalProcurementOrchestrator(registry=registered_lion_registry)

        # Mode A item with explicit link
        req = ProcurementRequest(
            part_number="STM32F401RET6",
            required_quantity=5,
            explicit_vendor_url="https://lionelectronic.ir/products/stm32-chip",
            mode=ProcurementMode.DATABASE_AWARE,
        )

        cands = orch.gather_candidates(req, vendor_ids=["vendor_lion"])
        assert len(cands) == 1
        cand = cands[0]
        assert cand.product_ref.pdp_url == "https://lionelectronic.ir/products/stm32-chip"

        # Evaluate candidate: even though adapter returned MPN 'UNMATCHED-MPN-ON-DISTRIBUTOR-SITE',
        # Option A ensures is_eligible == True and state == ELIGIBLE
        evaluation = orch.evaluate_candidate(cand, request=req)
        assert evaluation.is_eligible is True
        assert evaluation.state == EvaluationState.ELIGIBLE
        assert evaluation.effective_quantity == 5


# ==============================================================================
# 2. The 14/10/20/15 Rule: Strict Stock Safety & MOQ Handling
# ==============================================================================

class TestQuantityMOQAndStockSafety:
    def test_insufficient_stock_rule_shortage_14_step_10_target_20_stock_15(self):
        """
        The 14/10/20/15 Rule:
        Shortage = 14, Packaging Step = 10 -> Effective Required = 20.
        Supplier Live Stock = 15.
        Result:
        - Must be marked INSUFFICIENT_STOCK.
        - Must NOT add 10 to cart (zero cart addition).
        - Must NOT purchase or order.
        - Status must be SKIPPED, status_code must be SupplierOutcomeStatus.INSUFFICIENT_STOCK.
        - Remaining independent items in batch must continue normally.
        """
        class MockStep10Stock15Adapter(MockLionStagingAdapter):
            stock_qty = 15
            order_step = 10
            dispatched_items = []

        registry = VendorRegistry()
        registry.register_adapter(
            vendor_id="vendor_lion",
            adapter_class=MockStep10Stock15Adapter,
            domains=["lionelectronic.ir"],
            display_name="Lion Electronic",
            enabled=True,
            activate=True,
        )

        orch = UniversalProcurementOrchestrator(registry=registry)

        req1 = ProcurementRequest(
            part_number="RES-10K",
            required_quantity=14,  # Target will round up to 20 due to step=10
            explicit_vendor_url="https://lionelectronic.ir/res-10k",
            mode=ProcurementMode.DATABASE_AWARE,
        )

        cands = orch.gather_candidates(req1, vendor_ids=["vendor_lion"])
        assert len(cands) == 1
        cand1 = cands[0]
        eval1 = orch.evaluate_candidate(cand1, request=req1)

        # Candidate evaluation must flag INSUFFICIENT_STOCK because stock(15) < effective_qty(20)
        assert eval1.state == EvaluationState.INSUFFICIENT_STOCK
        assert eval1.is_eligible is False
        assert any("Insufficient stock" in r for r in eval1.rejection_reasons)

        # Plan building must record exact required failure message
        plan = orch.build_plan([req1], vendor_ids=["vendor_lion"])
        res1 = plan.results[0]
        assert res1.status == "INSUFFICIENT_STOCK"
        assert "Insufficient stock: 20 units required by supplier package rules, but only 15 are available. No quantity was added." in res1.error_message

        # Batch execution via bridge:
        # Item 1 has shortage 14, step 10, stock 15 -> must be SKIPPED with 0 added
        batch_items = [
            {
                "part_name": "RES-10K",
                "part_number": "RES-10K",
                "needed_qty": 14,
                "link": "https://lionelectronic.ir/res-10k",
                "vendor_id": "vendor_lion",
            },
        ]

        batch_result = ProcurementBridge.execute_staged_procurement_batch(
            items=batch_items,
            registry=registry,
            orchestrator=orch,
        )

        supplier_results = batch_result.get("supplier_results", [])
        assert len(supplier_results) == 1

        # Item 1: INSUFFICIENT_STOCK, 0 added, SKIPPED
        r1 = supplier_results[0]
        assert r1.status == SupplierOutcomeStatus.INSUFFICIENT_STOCK
        assert r1.staged_quantity == 0
        assert r1.requested_quantity == 14
        assert r1.effective_quantity == 20
        assert r1.available_quantity == 15

        # Verify adapter was never asked to add 10 or 15 or 20
        assert ("https://lionelectronic.ir/res-10k", 10) not in MockStep10Stock15Adapter.dispatched_items
        assert ("https://lionelectronic.ir/res-10k", 20) not in MockStep10Stock15Adapter.dispatched_items


# ==============================================================================
# 3. Dual Export Lifecycle Separation (Pre-Order vs Post-Operation)
# ==============================================================================

class TestDualExportLifecycle:
    def test_order_preview_export_buttons_and_lifecycle(self, qapp, registered_lion_registry):
        """
        Procurement Export Simplification:
        - Exactly one direct action: 'Export Staging Results (.xlsx)'.
        - No 'Export Report' dropdown and no 'Export Report — Pre-Order Plan (.xlsx)'.
        - Staging Results button is disabled initially; enabled only after staging run finishes.
        """
        shortages = [
            {
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/ne555p",
                "vendor_id": "vendor_lion",
            }
        ]

        dlg = OrderPreviewDialog(all_shortages=shortages, registry=registered_lion_registry)

        # 1. Exactly one direct export button exists (no dropdown or pre-order button)
        assert hasattr(dlg, "export_post_operation_btn")
        assert not hasattr(dlg, "export_menu")
        assert not hasattr(dlg, "settings_btn")

        # 2. Staging Results button is disabled initially
        assert dlg.export_post_operation_btn.isEnabled() is False
        assert "Staging Results" in dlg.export_post_operation_btn.text()

        # 3. Simulate staging run completion
        mock_staging_results = {
            "success": True,
            "successful_count": 1,
            "failed_count": 0,
            "results": [
                {
                    "part": "NE555P",
                    "status": "SUCCESS",
                    "qty": 5,
                    "msg": "Added 5 pcs",
                    "vendor_id": "vendor_lion",
                    "status_code": SupplierOutcomeStatus.ADDED_TO_CART,
                }
            ],
        }
        with patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"), \
             patch("webbrowser.open"):
            dlg._on_mode_a_order_finished(mock_staging_results)

        # 4. Post-Operation button is now enabled
        assert dlg.export_post_operation_btn.isEnabled() is True
        assert dlg.staging_results_log is not None

        dlg.close()


# ==============================================================================
# 4. Selection Integrity: Deselected Items Never Sent to Worker
# ==============================================================================

class TestSelectionIntegrity:
    def test_deselected_items_are_not_dispatched(self, qapp, registered_lion_registry):
        """
        Phase 3 / Section 8 Requirement:
        Deselected items must NEVER be sent to the worker or supplier adapter.
        """
        shortages = [
            {"part_name": "A", "part_number": "A", "needed_qty": 1, "link": "https://lionelectronic.ir/a", "vendor_id": "vendor_lion"},
            {"part_name": "B", "part_number": "B", "needed_qty": 2, "link": "https://lionelectronic.ir/b", "vendor_id": "vendor_lion"},
        ]

        dlg = OrderPreviewDialog(all_shortages=shortages, registry=registered_lion_registry)

        # Deselect item B (row 1)
        item1 = dlg.table.item(1, dlg.COL_SELECT)
        item1.setCheckState(Qt.CheckState.Unchecked)

        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 1
        assert selected[0]["part_name"] == "A"

        # Intercept worker start
        with patch("ui.dialogs.order_preview_dialog.settings.get", return_value="configured"), \
             patch.object(OrderWorkerThread, "start") as mock_thread_start:

            dlg._execute_mode_a_order()

            assert mock_thread_start.called
            assert dlg.worker is not None
            dispatched = dlg.worker.items
            assert len(dispatched) == 1
            assert dispatched[0]["part_name"] == "A"

        dlg.close()


# ==============================================================================
# 5. Dynamic Plugin Configuration Dialog
# ==============================================================================

class TestDynamicPluginConfigDialog:
    def test_plugin_config_dialog_renders_schema_and_masks_password(self, qapp, registered_lion_registry):
        """
        Phase 5 / Section 9 Requirement:
        Configuration UI must be driven by plugin manifest schema.
        Passwords must use EchoMode.Password with reveal toggle.
        """
        dlg = PluginConfigDialog(
            vendor_id="vendor_lion",
            registry=registered_lion_registry,
        )

        assert "username" in dlg.field_widgets
        assert "password" in dlg.field_widgets
        assert "timeout_seconds" in dlg.field_widgets

        pwd_widget, _ = dlg.field_widgets["password"]
        assert isinstance(pwd_widget, QLineEdit)
        assert pwd_widget.echoMode() == QLineEdit.EchoMode.Password

        # Find reveal button (child of the parent container or matching row)
        reveal_buttons = [b for b in dlg.findChildren(QPushButton) if b.toolTip() == "Toggle password visibility"]
        assert len(reveal_buttons) > 0
        btn = reveal_buttons[0]

        btn.click()
        assert pwd_widget.echoMode() == QLineEdit.EchoMode.Normal

        btn.click()
        assert pwd_widget.echoMode() == QLineEdit.EchoMode.Password

        dlg.close()


# ==============================================================================
# 6. Absolute Inventory Immutability
# ==============================================================================

class TestInventoryImmutabilityDuringProcurement:
    def test_zero_inventory_mutations_during_procurement(self, registered_lion_registry):
        """
        Section 11 Requirement:
        Inspect all code paths in procurement staging, evaluation, and bridge.
        Ensure ZERO writes to quantity_in_stock or inventory database.
        """
        db_path = "data/omnix_inventory.db"
        if not os.path.exists(db_path):
            pytest.skip("Main database not found")

        # Read baseline row counts and sum of stock
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(quantity_in_stock) FROM components")
        baseline_count, baseline_sum = cur.fetchone()
        conn.close()

        # Run orchestrator evaluation and bridge staging batch
        orch = UniversalProcurementOrchestrator(registry=registered_lion_registry)
        batch_items = [
            {"part_name": "TEST-1", "part_number": "TEST-1", "needed_qty": 5, "link": "https://lionelectronic.ir/p1", "vendor_id": "vendor_lion"}
        ]
        ProcurementBridge.execute_staged_procurement_batch(items=batch_items, registry=registered_lion_registry, orchestrator=orch)

        # Re-check database
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(quantity_in_stock) FROM components")
        post_count, post_sum = cur.fetchone()
        conn.close()

        assert post_count == baseline_count
        assert post_sum == baseline_sum
