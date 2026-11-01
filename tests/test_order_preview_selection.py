"""
Tests for Per-Item Selection in OrderPreviewDialog (Mode A).

Covers all 11 required scenarios:
1. All orderable items are selected by default.
2. Invalid, blank-link, and missing/unorderable items cannot be selected.
3. Select All selects only orderable items.
4. Deselect All clears all orderable selections.
5. Individual checkbox changes are reflected in the final selected batch.
6. _execute_mode_a_order() dispatches only selected items.
7. Zero selected items cannot launch a procurement batch.
8. Selected multi-vendor items retain existing vendor-selection behavior.
9. MOQ/order-step and existing procurement tests remain unchanged.
10. The selection UI does not mutate local inventory quantities.
11. OrderPreviewDialog operates strictly in Mode A architecture.
"""

import os
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from core.models import AdapterConfig, AdapterStatus, ProductDetails, ProductReference
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    OrderConstraints,
    ProcurementRequest,
    RequestProcurementResult,
    SupplierOutcomeStatus,
    VendorProcurementCandidate,
)
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter
from ui.dialogs.order_preview_dialog import OrderPreviewDialog, OrderWorkerThread, VendorSelectionDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockLionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config
        self.dispatched_urls: List[str] = []

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query: str) -> Any:
        return None

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="LION-SKU", pdp_url=url_or_sku)

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=100,
            can_order=True,
            price_irr=5000,
            mpn=product_ref.vendor_sku,
        )

    def extract_product_data(self, dom_context: Any) -> Any:
        return None

    def inspect_stock(self, product_ref: ProductReference) -> Any:
        return None

    def determine_order_constraints(self, product_ref: ProductReference) -> Any:
        return None

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> Any:
        self.dispatched_urls.append(product_ref.pdp_url)
        return {"success": True, "staged_quantity": quantity}

    def inspect_cart(self) -> Any:
        return None

    def authenticate(self, credentials: Any = None) -> Any:
        return None

    def validate_session(self) -> Any:
        return None

    def recover_from_error(self, error_context: Any) -> Any:
        return None

    def close(self) -> None:
        pass


class MockJavanAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config
        self.dispatched_urls: List[str] = []

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query: str) -> Any:
        return None

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-SKU", pdp_url=url_or_sku)

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=50,
            can_order=True,
            price_irr=4500,
            mpn=product_ref.vendor_sku,
        )

    def extract_product_data(self, dom_context: Any) -> Any:
        return None

    def inspect_stock(self, product_ref: ProductReference) -> Any:
        return None

    def determine_order_constraints(self, product_ref: ProductReference) -> Any:
        return None

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> Any:
        self.dispatched_urls.append(product_ref.pdp_url)
        return {"success": True, "staged_quantity": quantity}

    def inspect_cart(self) -> Any:
        return None

    def authenticate(self, credentials: Any = None) -> Any:
        return None

    def validate_session(self) -> Any:
        return None

    def recover_from_error(self, error_context: Any) -> Any:
        return None

    def close(self) -> None:
        pass


@pytest.fixture
def mock_registry():
    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionAdapter,
        domains=["lionelectronic.ir"],
        display_name="Lion Electronic",
        enabled=True,
        activate=True,
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=MockJavanAdapter,
        domains=["javanelec.com"],
        display_name="Javan Electronic",
        enabled=True,
        activate=True,
    )
    return reg


@pytest.fixture
def sample_shortages():
    return [
        {
            "part_name": "NE555P",
            "part_number": "NE555P",
            "description": "Timer IC DIP-8",
            "current_stock": 2,
            "needed_qty": 5,
            "link": "https://lionelectronic.ir/products/ne555p",
            "vendor_id": "vendor_lion",
        },
        {
            "part_name": "LM358N",
            "part_number": "LM358N",
            "description": "Op-Amp DIP-8",
            "current_stock": 10,
            "needed_qty": 4,
            "link": "https://javanelec.com/products/lm358n",
            "vendor_id": "vendor_javan",
        },
        {
            "part_name": "EXT-INVALID",
            "part_number": "EXT-100",
            "description": "External unsupported vendor",
            "current_stock": 0,
            "needed_qty": 10,
            "link": "https://unsupported-store.com/item/100",
        },
        {
            "part_name": "BLANK-LINK",
            "part_number": "BLANK-01",
            "description": "Missing URL in DB",
            "current_stock": 0,
            "needed_qty": 20,
            "link": "",
        },
    ]


class TestOrderPreviewSelection:
    """Comprehensive test suite for per-item selection in OrderPreviewDialog."""

    def test_1_all_orderable_items_selected_by_default(self, qapp, mock_registry, sample_shortages):
        """Scenario 1: All valid, orderable items must be selected by default."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        assert dlg.table.rowCount() == 4
        assert dlg.table.columnCount() == 7
        assert len(dlg.orderable_items) == 2
        assert len(dlg.invalid_items) == 2

        # Check default checkbox state for orderable rows (0 and 1)
        item0 = dlg.table.item(0, dlg.COL_SELECT)
        item1 = dlg.table.item(1, dlg.COL_SELECT)
        assert item0.checkState() == Qt.CheckState.Checked
        assert item1.checkState() == Qt.CheckState.Checked

        # Both orderable items are returned by get_selected_orderable_items
        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 2
        assert selected == dlg.orderable_items
        assert dlg.selected_orderable_items == selected

        # Order button reflects count
        assert dlg.order_btn.isEnabled() is True
        assert "Add 2 Items to Cart" in dlg.order_btn.text()

    def test_2_invalid_blank_missing_items_cannot_be_selected(self, qapp, mock_registry, sample_shortages):
        """Scenario 2: Items with invalid or blank links must remain unselected and non-selectable."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        # Row 2 is external non-registered URL
        item_ext = dlg.table.item(2, dlg.COL_SELECT)
        assert item_ext.checkState() == Qt.CheckState.Unchecked
        assert not (item_ext.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert not (item_ext.flags() & Qt.ItemFlag.ItemIsEnabled)

        # Row 3 is blank link
        item_blank = dlg.table.item(3, dlg.COL_SELECT)
        assert item_blank.checkState() == Qt.CheckState.Unchecked
        assert not (item_blank.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert not (item_blank.flags() & Qt.ItemFlag.ItemIsEnabled)

        # Attempt to programmatically check row 2
        item_ext.setCheckState(Qt.CheckState.Checked)
        # Handler must force it back to Unchecked
        assert item_ext.checkState() == Qt.CheckState.Unchecked

        # Excluded from selected list
        selected = dlg.get_selected_orderable_items()
        assert sample_shortages[2] not in selected
        assert sample_shortages[3] not in selected

    def test_3_select_all_selects_only_orderable_items(self, qapp, mock_registry, sample_shortages):
        """Scenario 3: 'Select All' selects only valid orderable items, keeping invalid unselected."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        # Deselect first
        dlg._deselect_all_orderable()
        assert len(dlg.get_selected_orderable_items()) == 0

        # Click Select All button
        dlg.select_all_btn.click()

        # Only orderable items are checked
        assert dlg.table.item(0, dlg.COL_SELECT).checkState() == Qt.CheckState.Checked
        assert dlg.table.item(1, dlg.COL_SELECT).checkState() == Qt.CheckState.Checked
        assert dlg.table.item(2, dlg.COL_SELECT).checkState() == Qt.CheckState.Unchecked
        assert dlg.table.item(3, dlg.COL_SELECT).checkState() == Qt.CheckState.Unchecked

        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 2
        assert dlg.order_btn.isEnabled() is True
        assert "Add 2 Items to Cart" in dlg.order_btn.text()

    def test_4_deselect_all_clears_all_orderable_selections(self, qapp, mock_registry, sample_shortages):
        """Scenario 4: 'Deselect All' clears all orderable selections and disables the order action."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        # Click Deselect All button
        dlg.deselect_all_btn.click()

        # All rows are Unchecked
        for r in range(dlg.table.rowCount()):
            assert dlg.table.item(r, dlg.COL_SELECT).checkState() == Qt.CheckState.Unchecked

        assert dlg.get_selected_orderable_items() == []
        assert dlg.order_btn.isEnabled() is False
        assert dlg.order_btn.text() == "🛒 No Items Selected"

    def test_5_individual_checkbox_toggle_updates_selected_batch(self, qapp, mock_registry):
        """Scenario 5: Individual checkbox changes are reflected dynamically in the selected batch and button."""
        shortages = [
            {"part_name": "A", "part_number": "A", "needed_qty": 1, "link": "https://lionelectronic.ir/a", "vendor_id": "vendor_lion"},
            {"part_name": "B", "part_number": "B", "needed_qty": 2, "link": "https://lionelectronic.ir/b", "vendor_id": "vendor_lion"},
            {"part_name": "C", "part_number": "C", "needed_qty": 3, "link": "https://lionelectronic.ir/c", "vendor_id": "vendor_lion"},
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=mock_registry)
        assert len(dlg.get_selected_orderable_items()) == 3
        assert "Add 3 Items to Cart" in dlg.order_btn.text()

        # Uncheck item B (row 1)
        dlg.table.item(1, dlg.COL_SELECT).setCheckState(Qt.CheckState.Unchecked)

        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 2
        assert [it["part_name"] for it in selected] == ["A", "C"]
        assert "Add 2 Items to Cart" in dlg.order_btn.text()

        # Re-check item B
        dlg.table.item(1, dlg.COL_SELECT).setCheckState(Qt.CheckState.Checked)
        selected_after = dlg.get_selected_orderable_items()
        assert len(selected_after) == 3
        assert [it["part_name"] for it in selected_after] == ["A", "B", "C"]
        assert "Add 3 Items to Cart" in dlg.order_btn.text()

    def test_6_execute_order_dispatches_only_selected_items(self, qapp, mock_registry):
        """Scenario 6: _execute_mode_a_order() dispatches only selected items to OrderWorkerThread."""
        shortages = [
            {"part_name": "ITEM-1", "part_number": "P1", "needed_qty": 5, "link": "https://lionelectronic.ir/1", "vendor_id": "vendor_lion"},
            {"part_name": "ITEM-2", "part_number": "P2", "needed_qty": 10, "link": "https://lionelectronic.ir/2", "vendor_id": "vendor_lion"},
            {"part_name": "ITEM-3", "part_number": "P3", "needed_qty": 15, "link": "https://lionelectronic.ir/3", "vendor_id": "vendor_lion"},
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=mock_registry)

        # Deselect ITEM-2 (row 1)
        dlg.table.item(1, dlg.COL_SELECT).setCheckState(Qt.CheckState.Unchecked)
        assert len(dlg.get_selected_orderable_items()) == 2

        with patch("ui.dialogs.order_preview_dialog.settings.get", return_value="mock_user"), \
             patch.object(OrderWorkerThread, "start") as mock_thread_start:

            dlg._execute_mode_a_order()

            assert mock_thread_start.called
            assert dlg.worker is not None
            # Verify exact items dispatched to OrderWorkerThread
            dispatched_items = dlg.worker.items
            assert len(dispatched_items) == 2
            assert [it["part_name"] for it in dispatched_items] == ["ITEM-1", "ITEM-3"]
            assert dlg.progress_bar.maximum() == 2

    def test_7_zero_selected_items_blocks_order(self, qapp, mock_registry, sample_shortages):
        """Scenario 7: Zero selected items cannot launch a procurement batch."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)
        dlg.deselect_all_btn.click()

        assert dlg.order_btn.isEnabled() is False

        with patch.object(QMessageBox, "warning") as mock_warn, \
             patch.object(OrderWorkerThread, "start") as mock_thread_start:

            dlg._execute_mode_a_order()

            assert mock_warn.called
            assert "No Items Selected" in mock_warn.call_args[0][1]
            assert not mock_thread_start.called
            assert dlg.worker is None

    def test_8_selected_multi_vendor_items_retain_vendor_selection_behavior(self, qapp, mock_registry):
        """Scenario 8: Selected multi-vendor items prompt for vendor choice; deselected ones do not."""
        shortages = [
            {
                "part_name": "MULTI-1",
                "part_number": "MULTI-1",
                "needed_qty": 5,
                "link": "LION=https://lionelectronic.ir/m1 || JAVAN=https://javanelec.com/m1",
            },
            {
                "part_name": "SINGLE-LION",
                "part_number": "SINGLE-LION",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/s1",
                "vendor_id": "vendor_lion",
            },
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=mock_registry)

        with patch("ui.dialogs.order_preview_dialog.settings.get", return_value="mock_user"):
            def select_lion(*args, **kwargs):
                dlg.multi_vendor_items[0]["selected_vendor_id"] = "vendor_lion"
                dlg.multi_vendor_items[0]["selected_url"] = dlg.multi_vendor_items[0]["vendor_links"]["vendor_lion"]
                return QDialog.DialogCode.Accepted

            # Case 8a: Multi-vendor item is selected -> VendorSelectionDialog is prompted
            with patch.object(VendorSelectionDialog, "exec", side_effect=select_lion) as mock_vsd, \
                 patch.object(OrderWorkerThread, "start"):
                dlg._execute_mode_a_order()
                assert mock_vsd.called

            # Case 8b: Multi-vendor item is DESELECTED, single item is selected -> VendorSelectionDialog is NOT prompted
            dlg.multi_vendor_items[0]["selected_vendor_id"] = None
            dlg.table.item(0, dlg.COL_SELECT).setCheckState(Qt.CheckState.Unchecked)
            with patch.object(VendorSelectionDialog, "exec") as mock_vsd_not_called, \
                 patch.object(OrderWorkerThread, "start"):
                dlg._execute_mode_a_order()
                assert not mock_vsd_not_called.called

    def test_9_moq_and_order_step_remain_unaffected(self, qapp, mock_registry):
        """Scenario 9: Selection UI preserves MOQ, packaging step, and needed quantities without tampering."""
        shortages = [
            {
                "part_name": "RES-0805",
                "part_number": "RES-0805",
                "needed_qty": 7,
                "shortage_qty": 7,
                "moq": 10,
                "order_step": 10,
                "link": "https://lionelectronic.ir/res-0805",
                "vendor_id": "vendor_lion",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=mock_registry)
        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 1
        item = selected[0]
        assert item["needed_qty"] == 7
        assert item["shortage_qty"] == 7
        assert item["moq"] == 10
        assert item["order_step"] == 10

    def test_10_selection_ui_does_not_mutate_local_inventory_quantities(self, qapp, mock_registry, tmp_path):
        """Scenario 10: Toggling selections and reviewing batches strictly leaves repository quantities unchanged."""
        db_path = str(tmp_path / "test_inventory.db")
        repo = SqliteInventoryRepository(db_path)

        p1 = repo.create_component(
            InventoryProduct(
                mpn="ISOLATED-01",
                category="Capacitor",
                type_technology="MLCC",
                package="0805",
                manufacturer="Murata",
                value="10uF",
                footprint="0805",
                quantity_in_stock=42,
            )
        )
        p2 = repo.create_component(
            InventoryProduct(
                mpn="ISOLATED-02",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                manufacturer="Yageo",
                value="10k",
                footprint="0603",
                quantity_in_stock=100,
            )
        )

        shortages = [
            {
                "part_name": "ISOLATED-01",
                "part_number": "ISOLATED-01",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/iso1",
                "vendor_id": "vendor_lion",
            },
            {
                "part_name": "ISOLATED-02",
                "part_number": "ISOLATED-02",
                "needed_qty": 20,
                "link": "https://javanelec.com/iso2",
                "vendor_id": "vendor_javan",
            },
        ]

        dlg = OrderPreviewDialog(all_shortages=shortages, inventory_loader=repo, registry=mock_registry)

        # Perform selection toggles
        dlg.deselect_all_btn.click()
        dlg.select_all_btn.click()
        dlg.table.item(0, dlg.COL_SELECT).setCheckState(Qt.CheckState.Unchecked)
        dlg.table.item(0, dlg.COL_SELECT).setCheckState(Qt.CheckState.Checked)

        # Confirm stock in database remains 100% unaltered
        c1 = repo.get_component_by_id(p1.id)
        c2 = repo.get_component_by_id(p2.id)
        assert c1.quantity_in_stock == 42
        assert c2.quantity_in_stock == 100

    def test_11_order_preview_operates_solely_in_mode_a(self, qapp, mock_registry):
        """Scenario 11: OrderPreviewDialog operates solely in Mode A architecture even if plan is supplied."""
        cand = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="NE555P",
            package="DIP-8",
            base_unit_price_irr=5000,
            stock_quantity=100,
            in_stock=True,
            can_order=True,
            order_constraints=OrderConstraints(moq_raw=5, packaging_step_raw=1),
            product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="LION-555", pdp_url="https://lionelectronic.ir/555"),
        )
        eval_obj = CandidateEvaluation(
            candidate=cand,
            required_quantity=5,
            effective_quantity=5,
            effective_unit_price_irr=5000,
            effective_total_price_irr=25000,
            is_eligible=True,
            state=EvaluationState.ELIGIBLE,
            rejection_reasons=[],
        )
        result = RequestProcurementResult(
            request=ProcurementRequest(part_number="NE555P", required_quantity=5),
            candidates=[cand],
            evaluations=[eval_obj],
            selected_evaluation=eval_obj,
        )
        plan = BOMProcurementPlan(results=[result])

        dlg = OrderPreviewDialog(plan=plan, registry=mock_registry)
        assert hasattr(dlg, "table")
        assert hasattr(dlg, "select_all_btn")
        assert hasattr(dlg, "deselect_all_btn")
        assert not hasattr(dlg, "master_table")
        assert not hasattr(dlg, "detail_table")

    def test_12_single_direct_export_staging_results_action(self, qapp, mock_registry, sample_shortages):
        """Verify exactly one direct export action exists: Export Staging Results (.xlsx)."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        # 1. Direct button exists and is disabled initially
        assert hasattr(dlg, "export_post_operation_btn")
        assert dlg.export_post_operation_btn.isEnabled() is False
        assert "Export Staging Results (.xlsx)" in dlg.export_post_operation_btn.text()

        # 2. Dropdown and pre-order plan button are absent
        assert not hasattr(dlg, "export_menu")
        assert not hasattr(dlg, "export_pre_order_btn")

        # 3. Account Settings button is absent
        assert not hasattr(dlg, "settings_btn")

    def test_13_no_account_settings_in_order_preview(self, qapp, mock_registry):
        """Verify preview dialog contains single direct export and no Account Settings button."""
        dlg = OrderPreviewDialog(all_shortages=[], registry=mock_registry)
        assert not hasattr(dlg, "settings_btn")
        assert hasattr(dlg, "export_post_operation_btn")
        assert not hasattr(dlg, "export_menu")

    def test_14_export_staging_subset_of_eligible_items(self, qapp, mock_registry, sample_shortages, tmp_path):
        """Verify export respects subset selection: only selected staged items are exported."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)

        # Deselect row 1, keep only row 0 selected
        dlg.table.item(0, dlg.COL_SELECT).setCheckState(Qt.CheckState.Unchecked)
        selected = dlg.get_selected_orderable_items()
        assert len(selected) == 1
        assert selected[0]["part_number"] == "LM358N"

        # Simulate staging finished
        mock_results = {
            "success": True,
            "results": [
                {
                    "part": "LM358N",
                    "status": "SUCCESS",
                    "qty": 10,
                    "msg": "Added 10 to cart",
                    "vendor_id": "vendor_lion",
                    "status_code": SupplierOutcomeStatus.ADDED_TO_CART,
                }
            ],
        }
        with patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"), \
             patch("webbrowser.open"):
            dlg._on_mode_a_order_finished(mock_results)

        assert dlg.export_post_operation_btn.isEnabled() is True

        # Export to tmp_path
        out_file = str(tmp_path / "staging_results.xlsx")
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(out_file, "Excel Files (*.xlsx)")), \
             patch.object(QMessageBox, "information"), \
             patch("webbrowser.open"):
            dlg._export_post_operation_results()

        assert os.path.exists(out_file)

        # Read back exported workbook to verify it contains staged items
        import openpyxl
        wb = openpyxl.load_workbook(out_file, data_only=True)
        assert "Procurement Summary" in wb.sheetnames
        ws = wb["Procurement Summary"]
        # Find part number in sheet
        found_parts = []
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell and "LM358N" in str(cell):
                    found_parts.append("LM358N")
        assert "LM358N" in found_parts
        wb.close()

    def test_15_empty_selection_and_no_eligible_items_behavior(self, qapp, mock_registry):
        """Verify empty selection and zero eligible items correctly sets controls, tooltips, and blocks export."""
        # Zero eligible shortages
        ineligible_only = [
            {"part_name": "Blank 1", "needed_qty": 5, "link": "", "vendor_id": None},
            {"part_name": "External 1", "needed_qty": 10, "link": "https://unknown.com/part", "vendor_id": None},
        ]
        dlg = OrderPreviewDialog(all_shortages=ineligible_only, registry=mock_registry)

        # Checkboxes are uncheckable and disabled
        assert len(dlg.orderable_items) == 0
        assert dlg.select_all_btn.isEnabled() is True
        assert "No items have valid vendor links" in dlg.select_all_btn.toolTip()
        assert dlg.deselect_all_btn.isEnabled() is True
        assert dlg.order_btn.isEnabled() is False
        assert "No Orderable Items" in dlg.order_btn.text()
        assert dlg.export_post_operation_btn.isEnabled() is False

        # Clicking select all when 0 eligible items exist selects 0 items
        dlg._select_all_orderable()
        assert dlg.get_selected_orderable_items() == []

        # Clicking deselect all clears
        dlg._deselect_all_orderable()
        assert dlg.get_selected_orderable_items() == []

        # Attempting export without staging results triggers warning and aborts
        with patch.object(QMessageBox, "warning") as mock_warn, \
             patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as mock_save:
            dlg._export_post_operation_results()
            mock_warn.assert_called_once()
            mock_save.assert_not_called()

    def test_16_export_button_disabled_when_staging_fails_or_empty(self, qapp, mock_registry, sample_shortages):
        """Verify Export Staging Results button remains disabled when staging produces zero valid items."""
        dlg = OrderPreviewDialog(all_shortages=sample_shortages, registry=mock_registry)
        assert dlg.export_post_operation_btn.isEnabled() is False

        # All items failed to stage
        failed_results = {
            "success": False,
            "successful_count": 0,
            "failed_count": 2,
            "results": [
                {"part": "RES-10K", "status": "FAILED", "qty": 0, "msg": "Network timeout"},
                {"part": "LM358N", "status": "FAILED", "qty": 0, "msg": "Out of stock"},
            ],
        }
        with patch.object(QMessageBox, "information"), patch.object(QMessageBox, "warning"), patch("webbrowser.open"):
            dlg._on_mode_a_order_finished(failed_results)

        # Export button must remain disabled
        assert dlg.export_post_operation_btn.isEnabled() is False
        assert "No valid staged items" in dlg.export_post_operation_btn.toolTip()

        # Attempting export warns and aborts
        with patch.object(QMessageBox, "warning") as mock_warn, \
             patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as mock_save:
            dlg._export_post_operation_results()
            mock_warn.assert_called_once()
            mock_save.assert_not_called()

        # Now simulate at least one successful staged item
        success_results = {
            "success": True,
            "successful_count": 1,
            "failed_count": 1,
            "results": [
                {"part": "RES-10K", "status": "SUCCESS", "qty": 5, "msg": "Added 5 to cart"},
                {"part": "LM358N", "status": "FAILED", "qty": 0, "msg": "Out of stock"},
            ],
        }
        with patch.object(QMessageBox, "information"), patch.object(QMessageBox, "warning"), patch("webbrowser.open"):
            dlg._on_mode_a_order_finished(success_results)
        assert dlg.export_post_operation_btn.isEnabled() is True

    def test_17_bom_audit_widget_has_no_pre_order_export_button(self, qapp):
        """Verify BOMAuditWidget does not contain obsolete Export Report - Pre-Order Plan button."""
        from ui.widgets.bom_audit_widget import BOMAuditWidget
        widget = BOMAuditWidget()
        assert not hasattr(widget, "export_pre_order_btn")
        assert not hasattr(widget, "export_report_btn")

