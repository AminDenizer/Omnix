"""
Omnix Section 5 — BOM, Procurement & Order Reporting Verification Tests
Validates:
- Fix A: BOM auditing directly against SqliteInventoryRepository using BOM Part Number -> MPN.
         No non-MPN fallback to Comment/Description; unmatched items return NOT_IN_DB.
- Fix B: 'Deduct internal stock' checkbox behavior (True = net shortage; False = gross BOM demand).
- Fix C: ProcurementBridge zero-quantity handling (no falsy fallback, ValueError on non-positive,
         orderable gate returns False).
- Fix D: Removal of automatic LinkValidationDialog pre-scan in _open_order_dialog, preserving manual button.
- Fix E: Mode A locked as sole supported procurement workflow.
- Strict Inventory Quantity Immutability: Omnix never mutates inventory quantities in any workflow.
"""

import os
import pytest
import openpyxl
from PyQt6.QtWidgets import QApplication

from bom_auditor import BOMAuditor
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import ProcurementMode
from core.procurement.registry import VendorRegistry
from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from ui.widgets.bom_audit_widget import BOMAuditWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_repo(tmp_path):
    """Creates a temporary, isolated SQLite repository seeded with test components."""
    db_path = str(tmp_path / "test_sec5.db")
    repo = SqliteInventoryRepository(db_path)

    cat_id = repo.add_category("Integrated Circuits")
    repo.add_type(cat_id, "Standard IC")
    repo.add_manufacturer("Texas Instruments")
    repo.add_manufacturer("STMicroelectronics")

    # Component 1: In stock with supplier link
    p1 = InventoryProduct(
        manufacturer="Texas Instruments",
        mpn="NE555P",
        category="Integrated Circuits",
        type_technology="Standard IC",
        package="DIP-8",
        footprint="DIP-8",
        value="Timer",
        quantity_in_stock=15,
    )
    link1 = SupplierLink(
        vendor_id="vendor_lion",
        vendor_label="LION",
        url="https://lionelectronic.ir/products/ne555p",
    )
    repo.create_component(p1, supplier_links=[link1])

    # Component 2: Low stock with supplier link
    p2 = InventoryProduct(
        manufacturer="Texas Instruments",
        mpn="LM358N",
        category="Integrated Circuits",
        type_technology="Standard IC",
        package="DIP-8",
        footprint="DIP-8",
        value="Dual OpAmp",
        quantity_in_stock=6,
    )
    link2 = SupplierLink(
        vendor_id="vendor_lion",
        vendor_label="LION",
        url="https://lionelectronic.ir/products/lm358n",
    )
    repo.create_component(p2, supplier_links=[link2])

    # Component 3: Component with Comment matching a different part's description
    p3 = InventoryProduct(
        manufacturer="STMicroelectronics",
        mpn="STM32F401RET6",
        category="Integrated Circuits",
        type_technology="Standard IC",
        package="LQFP-64",
        footprint="LQFP-64",
        value="MCU",
        description="Precision MCU Device",
        quantity_in_stock=50,
    )
    repo.create_component(p3)

    yield repo
    repo.close()


@pytest.fixture
def sample_bom(tmp_path):
    """Creates a temporary Altium BOM Excel workbook."""
    bom_file = str(tmp_path / "Altium_Project_BOM.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"
    ws.append(["Designator", "Quantity", "Comment", "Footprint", "Description", "Part Number"])
    # Item 1: NE555P (1 per board)
    ws.append(["U1", 1, "Precision Timer", "DIP-8", "Timer IC", "NE555P"])
    # Item 2: LM358N (2 per board)
    ws.append(["U2, U3", 2, "Dual Op-Amp", "DIP-8", "OpAmp IC", "LM358N"])
    # Item 3: Part not in DB by MPN, but Comment equals STM32 description
    ws.append(["U4", 1, "Precision MCU Device", "LQFP-64", "MCU", "UNLISTED-PART-999"])
    wb.save(bom_file)
    wb.close()
    return bom_file


class TestSection5BOMProcurement:

    @pytest.fixture(autouse=True)
    def register_adapters(self):
        reg = VendorRegistry.get_default_registry()
        reg.register_default_adapters()
        yield
        reg.clear()

    # --- Fix A: SQLite MPN Direct Match & Non-MPN Fallback Elimination ---

    def test_bom_audit_matches_sqlite_by_mpn(self, clean_repo, sample_bom):
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom,
            inventory=clean_repo,
            board_multiplier=5,
            deduct_stock=True
        )
        assert ok is True
        assert res is not None
        assert res.total_items_count == 3

        # Item 1: NE555P -> 1 * 5 = 5 needed; stock is 15 -> Fully Available (IN_STOCK), shortage = 0
        ne555 = next(it for it in res.items if it.part_number == "NE555P")
        assert ne555.total_needed_qty == 5
        assert ne555.db_stock_qty == 15
        assert ne555.shortage_qty == 0
        assert ne555.status == "IN_STOCK"
        assert "https://lionelectronic.ir/products/ne555p" in ne555.link
        assert ne555.is_orderable is True

        # Item 2: LM358N -> 2 * 5 = 10 needed; stock is 6 -> Shortage = 4
        lm358 = next(it for it in res.items if it.part_number == "LM358N")
        assert lm358.total_needed_qty == 10
        assert lm358.db_stock_qty == 6
        assert lm358.shortage_qty == 4
        assert lm358.status == "SHORTAGE"
        assert lm358.is_orderable is True
        assert "https://lionelectronic.ir/products/lm358n" in lm358.link

    def test_bom_audit_unmatched_mpn_reports_not_in_db_no_comment_fallback(self, clean_repo, sample_bom):
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom,
            inventory=clean_repo,
            board_multiplier=1
        )
        assert ok is True
        # Item 3: UNLISTED-PART-999 has Comment 'Precision MCU Device' which matches STM32 description,
        # but because MPN does not match, it MUST be reported as NOT_IN_DB!
        unlisted = next(it for it in res.items if it.part_number == "UNLISTED-PART-999")
        assert unlisted.status == "NOT_IN_DB"
        assert unlisted.db_stock_qty == 0
        assert unlisted.shortage_qty == 1
        assert unlisted.is_orderable is False

    # --- Fix B: Deduct Internal Stock Checkbox Behavior ---

    def test_deduct_internal_stock_true(self, clean_repo, sample_bom):
        # 5 boards: LM358N requires 10 pcs, stock is 6 -> net shortage is 4
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom,
            inventory=clean_repo,
            board_multiplier=5,
            deduct_stock=True
        )
        lm358 = next(it for it in res.items if it.part_number == "LM358N")
        assert lm358.shortage_qty == 4
        assert lm358.status == "SHORTAGE"

    def test_deduct_internal_stock_false(self, clean_repo, sample_bom):
        # 5 boards: LM358N requires 10 pcs, stock is 6.
        # With deduct_stock=False, shortage must equal full gross BOM requirement (10)
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom,
            inventory=clean_repo,
            board_multiplier=5,
            deduct_stock=False
        )
        lm358 = next(it for it in res.items if it.part_number == "LM358N")
        assert lm358.total_needed_qty == 10
        assert lm358.db_stock_qty == 6
        assert lm358.shortage_qty == 10  # Full gross requirement
        assert lm358.status == "SHORTAGE"
        assert lm358.is_orderable is True
        assert "https://lionelectronic.ir/products/lm358n" in lm358.link

        # NE555P requires 5 pcs, stock is 15.
        # With deduct_stock=False, shortage must equal 5 pcs even though in stock!
        ne555 = next(it for it in res.items if it.part_number == "NE555P")
        assert ne555.total_needed_qty == 5
        assert ne555.db_stock_qty == 15
        assert ne555.shortage_qty == 5
        assert ne555.status == "SHORTAGE"
        assert ne555.is_orderable is True

    # --- Fix C: Zero-Quantity & ProcurementBridge Defect Fixes ---

    def test_procurement_bridge_zero_quantity_item_to_request_raises(self):
        in_stock_item = {
            "part_number": "NE555P",
            "needed_qty": 0,
            "shortage_qty": 0,
            "total_needed_qty": 10,
            "link": "https://lionelectronic.ir/products/ne555p",
            "is_orderable": False,
        }
        with pytest.raises(ValueError, match="zero or negative purchase requirement"):
            ProcurementBridge.item_to_request(in_stock_item)

    def test_procurement_bridge_is_item_orderable_zero_quantity(self):
        in_stock_item = {
            "part_number": "NE555P",
            "needed_qty": 0,
            "shortage_qty": 0,
            "link": "https://lionelectronic.ir/products/ne555p",
        }
        orderable, vendor_id = ProcurementBridge.is_item_orderable(in_stock_item)
        assert orderable is False
        assert vendor_id is None

    def test_procurement_bridge_staged_batch_skips_zero_requirement(self):
        zero_item = {
            "part_number": "NE555P",
            "needed_qty": 0,
            "shortage_qty": 0,
            "total_needed_qty": 10,
            "link": "https://lionelectronic.ir/products/ne555p",
            "is_orderable": False,
        }
        res = ProcurementBridge.execute_staged_procurement_batch([zero_item])
        assert res["successful_count"] == 0
        assert res["failed_count"] == 1
        assert len(res["results"]) == 1
        assert res["results"][0]["status"] == "FAILED"
        assert "fully covered by stock" in res["results"][0]["msg"]

    # --- Fix D: Removal of Automatic LinkValidationDialog Pre-Scan ---

    def test_open_order_dialog_no_automatic_link_validation(self, qapp, clean_repo, sample_bom, monkeypatch):
        widget = BOMAuditWidget(clean_repo)
        widget.load_bom_file(sample_bom)

        validation_opened = []
        order_preview_opened = []

        # Verify LinkValidationDialog module is deleted and not imported
        import sys
        assert "ui.dialogs.link_validation_dialog" not in sys.modules

        # Monkeypatch OrderPreviewDialog
        from ui.dialogs.order_preview_dialog import OrderPreviewDialog
        def mock_preview_exec(self):
            order_preview_opened.append(True)
            return 0
        monkeypatch.setattr(OrderPreviewDialog, "exec", mock_preview_exec)

        # Trigger order dialog
        widget._open_order_dialog()

        # Link validation must NOT have executed automatically
        assert len(validation_opened) == 0
        # OrderPreviewDialog must have executed
        assert len(order_preview_opened) == 1

        # Manual validate button was removed per Phase 4 removal
        assert not hasattr(widget, "validate_links_btn")

    # --- Fix E: Mode A Sole Workflow ---

    def test_mode_a_locked_as_sole_mode_in_ui(self, qapp, clean_repo):
        """Verify Mode A is the sole supported mode in BOMAuditWidget."""
        widget = BOMAuditWidget(clean_repo)
        assert not hasattr(widget, "mode_combo")
        assert widget.current_mode == ProcurementMode.DATABASE_AWARE

    # --- Strict Inventory Quantity Immutability Verification ---

    def test_strict_inventory_immutability_repository_and_loader(self, clean_repo):
        """Verify that neither SqliteInventoryRepository nor ExcelDataLoader have stock-increment/mutation methods."""
        from excel_loader import ExcelDataLoader

        # Repository level immutability
        assert not hasattr(clean_repo, "batch_increment_stock")
        assert not hasattr(clean_repo, "increment_stock")
        assert not hasattr(clean_repo, "deduct_stock")
        assert not hasattr(SqliteInventoryRepository, "batch_increment_stock")

        # Excel loader level immutability
        assert not hasattr(ExcelDataLoader, "batch_increment_stock")
        assert not hasattr(ExcelDataLoader, "save_cell_value")

    def test_bom_audit_leaves_inventory_quantities_unaltered(self, clean_repo, sample_bom):
        """BOM auditing with deduct_stock=True or False must NEVER mutate inventory stock in the database."""
        # Initial quantities
        p1_before = clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock
        p2_before = clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock

        # Audit with deduct_stock=True
        ok, msg, res_deduct = BOMAuditor.audit_bom(sample_bom, clean_repo, board_multiplier=5, deduct_stock=True)
        assert ok is True
        p1_after_deduct = clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock
        p2_after_deduct = clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock
        assert p1_after_deduct == p1_before == 15
        assert p2_after_deduct == p2_before == 6

        # Audit with deduct_stock=False
        ok, msg, res_gross = BOMAuditor.audit_bom(sample_bom, clean_repo, board_multiplier=5, deduct_stock=False)
        assert ok is True
        p1_after_gross = clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock
        p2_after_gross = clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock
        assert p1_after_gross == p1_before == 15
        assert p2_after_gross == p2_before == 6

    def test_order_preview_dialog_has_no_stock_mutation_controls(self, qapp, clean_repo):
        """OrderPreviewDialog must NOT have 'Confirm Payment & Add Stock' button or any handler to alter stock."""
        from ui.dialogs.order_preview_dialog import OrderPreviewDialog
        from core.procurement.models import (
            BOMProcurementPlan,
            CandidateEvaluation,
            EvaluationState,
            ProcurementRequest,
            ProductReference,
            RequestProcurementResult,
            VendorProcurementCandidate,
        )

        req = ProcurementRequest(part_number="NE555P", required_quantity=10)
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="2070", pdp_url="https://lionelectronic.ir/products/2070-NE555P"),
            in_stock=True,
            can_order=True,
            base_unit_price_irr=15000,
        )
        ev = CandidateEvaluation(
            candidate=cand,
            required_quantity=10,
            effective_quantity=10,
            effective_unit_price_irr=15000,
            effective_total_price_irr=150000,
            is_eligible=True,
            state=EvaluationState.ELIGIBLE,
        )
        res = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=[cand],
            evaluations=[ev],
            selected_evaluation=ev,
        )
        plan = BOMProcurementPlan(results=[res])

        dlg = OrderPreviewDialog(plan=plan, inventory_loader=clean_repo)

        assert not hasattr(dlg, "confirm_payment_btn")
        assert not hasattr(dlg, "_confirm_payment_and_add_stock")
        assert not hasattr(dlg, "_has_updated_inventory")

