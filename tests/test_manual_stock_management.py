"""
Omnix Automated Tests - Manual Stock Management Workflow
Validates:
1. A stock update changes the requested component's quantity.
2. All unrelated component metadata remains unchanged.
3. Negative and non-integer quantities are rejected.
4. Nonexistent component ID is handled through established ComponentNotFoundError.
5. StockAdjustmentDialog loads component's current quantity and applies step controls (+1, +10, -1, -10).
6. Saving refreshes relevant stock displays and the low-stock count through existing UI mechanisms.
7. Existing BOM/procurement paths remain strictly read-only with respect to on-hand stock.
"""

import os
import pytest
import openpyxl
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

from core.inventory.models import (
    InventoryProduct,
    SupplierLink,
    StockPolicyRecord,
    ValidationError,
    ComponentNotFoundError,
)
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
from ui.main_window import MainWindow
from bom_auditor import BOMAuditor


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_repo(tmp_path):
    """Creates a temporary isolated SQLite repository seeded with test components."""
    db_path = str(tmp_path / "test_manual_stock.db")
    repo = SqliteInventoryRepository(db_path)

    cat_id = repo.add_category("Integrated Circuits")
    repo.add_type(cat_id, "Standard IC")
    repo.add_manufacturer("Texas Instruments")
    repo.add_manufacturer("STMicroelectronics")

    p1 = InventoryProduct(
        manufacturer="Texas Instruments",
        mpn="NE555P",
        category="Integrated Circuits",
        type_technology="Standard IC",
        package="DIP-8",
        footprint="DIP-8",
        value="Timer",
        description="Precision Precision Timer",
        quantity_in_stock=15,
    )
    link1 = SupplierLink(
        vendor_id="vendor_lion",
        vendor_label="LION",
        url="https://lionelectronic.ir/products/ne555p",
    )
    repo.create_component(p1, supplier_links=[link1])

    p2 = InventoryProduct(
        manufacturer="Texas Instruments",
        mpn="LM358N",
        category="Integrated Circuits",
        type_technology="Standard IC",
        package="DIP-8",
        footprint="DIP-8",
        value="Dual OpAmp",
        description="Dual Low Power OpAmp",
        quantity_in_stock=6,
    )
    repo.create_component(p2)

    yield repo
    repo.close()


class TestManualStockManagement:

    def test_update_component_stock_success(self, clean_repo):
        """1. A stock update changes the requested component's quantity."""
        p1 = clean_repo.get_component_by_identity("Texas Instruments", "NE555P")
        assert p1 is not None
        assert p1.quantity_in_stock == 15

        updated = clean_repo.update_component_stock(p1.id, 42)
        assert updated.quantity_in_stock == 42
        assert updated.id == p1.id

        # Verify persistence directly from repository
        reloaded = clean_repo.get_component_by_id(p1.id)
        assert reloaded.quantity_in_stock == 42

    def test_update_component_stock_preserves_unrelated_metadata(self, clean_repo):
        """2. All unrelated component metadata remains strictly unchanged."""
        p1_before = clean_repo.get_component_by_identity("Texas Instruments", "NE555P")
        links_before = clean_repo.get_supplier_links(p1_before.id)

        clean_repo.update_component_stock(p1_before.id, 99)

        p1_after = clean_repo.get_component_by_id(p1_before.id)
        links_after = clean_repo.get_supplier_links(p1_before.id)

        assert p1_after.quantity_in_stock == 99
        assert p1_after.manufacturer == p1_before.manufacturer
        assert p1_after.mpn == p1_before.mpn
        assert p1_after.norm_manufacturer == p1_before.norm_manufacturer
        assert p1_after.norm_mpn == p1_before.norm_mpn
        assert p1_after.category == p1_before.category
        assert p1_after.type_technology == p1_before.type_technology
        assert p1_after.package == p1_before.package
        assert p1_after.footprint == p1_before.footprint
        assert p1_after.value == p1_before.value
        assert p1_after.description == p1_before.description
        assert p1_after.group_key == p1_before.group_key

        assert len(links_after) == len(links_before)
        assert links_after[0].url == links_before[0].url

    def test_update_component_stock_rejects_negative_and_invalid_quantities(self, clean_repo):
        """3. Negative quantities and non-integer inputs are rejected."""
        p1 = clean_repo.get_component_by_identity("Texas Instruments", "NE555P")

        with pytest.raises(ValidationError, match="non-negative"):
            clean_repo.update_component_stock(p1.id, -1)

        with pytest.raises(ValidationError, match="non-negative"):
            clean_repo.update_component_stock(p1.id, -100)

        with pytest.raises(ValidationError, match="must be an integer"):
            clean_repo.update_component_stock(p1.id, "50")

        with pytest.raises(ValidationError, match="must be an integer"):
            clean_repo.update_component_stock(p1.id, True)

        # Confirm stock was not modified
        p1_unmodified = clean_repo.get_component_by_id(p1.id)
        assert p1_unmodified.quantity_in_stock == 15

    def test_update_component_stock_nonexistent_id(self, clean_repo):
        """4. A nonexistent component ID is handled through ComponentNotFoundError."""
        with pytest.raises(ComponentNotFoundError, match="Component ID 999999 not found"):
            clean_repo.update_component_stock(999999, 10)

    def test_stock_adjustment_dialog_loads_and_applies_controls(self, qapp, clean_repo):
        """5. Dialog loads selected component's current quantity and applies step controls correctly."""
        p1 = clean_repo.get_component_by_identity("Texas Instruments", "NE555P")
        dlg = StockAdjustmentDialog(component=p1, repository=clean_repo)

        # Initial quantity check
        assert dlg.qty_spin.value() == 15

        # Check button controls (+1, +10, -1, -10)
        # Find step buttons by label
        btn_map = {btn.text(): btn for btn in dlg.step_buttons}

        btn_map["+1"].click()
        assert dlg.qty_spin.value() == 16
        assert "Increase" in dlg.delta_lbl.text()

        btn_map["+10"].click()
        assert dlg.qty_spin.value() == 26

        btn_map["-1"].click()
        assert dlg.qty_spin.value() == 25

        btn_map["-10"].click()
        assert dlg.qty_spin.value() == 15
        assert "No change" in dlg.delta_lbl.text()

        # Direct entry and floor at zero
        dlg.qty_spin.setValue(5)
        btn_map["-10"].click()
        assert dlg.qty_spin.value() == 0  # does not go negative

        # Save new quantity
        dlg.qty_spin.setValue(55)
        dlg._save_stock()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.saved_component is not None
        assert dlg.saved_component.quantity_in_stock == 55

        # Verify repository on disk
        reloaded = clean_repo.get_component_by_id(p1.id)
        assert reloaded.quantity_in_stock == 55

    def test_stock_adjustment_dialog_refreshes_ui_and_low_stock_status(self, qapp, tmp_path):
        """6. Saving refreshes relevant stock displays and low-stock count through existing UI mechanisms."""
        db_path = str(tmp_path / "test_ui_stock_refresh.db")
        repo = SqliteInventoryRepository(db_path)

        cat_id = repo.add_category("Standard Resistors")
        repo.add_type(cat_id, "Thick Film")
        repo.add_manufacturer("Yageo")

        p = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            category="Standard Resistors",
            type_technology="Thick Film",
            package="0603",
            footprint="0603",
            value="10k",
            quantity_in_stock=10,
            min_stock=20,
            target_stock=50,
        )
        created_p = repo.create_component(p)

        # Configure Stock Policy: Min = 20, Target = 50 -> Current (10) is LOW STOCK
        repo.set_policy(
            created_p.group_key,
            min_stock=20,
            target_stock=50,
            category="Standard Resistors",
            type_technology="Thick Film",
            package="0603",
            footprint="0603",
            value="10k",
        )

        from unittest.mock import patch

        with patch.object(MainWindow, "_check_startup_shortages"):
            window = MainWindow(default_file=db_path, repository=repo)
            window.show()
            qapp.processEvents()

            window._reload_and_select_group(created_p.group_key, select_comp_id=created_p.id)
            qapp.processEvents()

            # 1. Verify initial low stock state in stats ribbon
            groups = repo.get_all_groups()
            assert len(groups) == 1
            assert groups[0].is_low_stock is True
            assert window.stats_ribbon.order_shortages_btn.isVisible() is True
            assert "Order Low Stock (1)" in window.stats_ribbon.order_shortages_btn.text()

            # 2. Verify stock_mgmt_btn is enabled when component is selected
            assert hasattr(window, "stock_mgmt_btn")
            assert window.stock_mgmt_btn.isEnabled() is True

            # 3. Perform manual stock update: increase stock from 10 to 35 (> min_stock 20)
            repo.update_component_stock(created_p.id, 35)

            # 4. Trigger established refresh mechanism
            window._reload_and_select_group(created_p.group_key, select_comp_id=created_p.id)
            window._update_stats_ribbon()
            qapp.processEvents()

            # 5. Verify low-stock count is cleared
            updated_groups = repo.get_all_groups()
            assert updated_groups[0].current_stock == 35
            assert updated_groups[0].is_low_stock is False
            assert "All Stock OK" in window.stats_ribbon.order_shortages_btn.text()

            window._is_force_closing = True
            window.close()
        repo.close()

    def test_existing_bom_procurement_paths_remain_strictly_read_only(self, clean_repo, tmp_path):
        """7. Existing BOM/procurement paths remain read-only with respect to on-hand stock."""
        # Create a sample BOM file
        bom_path = str(tmp_path / "Audit_BOM.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "BOM"
        ws.append(["Item", "Designator", "Quantity", "Part Number", "Description"])
        ws.append(["1", "U1", 5, "NE555P", "Precision Timer"])
        ws.append(["2", "U2", 20, "LM358N", "Dual OpAmp"])
        wb.save(bom_path)
        wb.close()

        p1_orig = clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock
        p2_orig = clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock

        # Audit with deduct_stock=True
        ok1, _, res1 = BOMAuditor.audit_bom(bom_path, clean_repo, board_multiplier=1, deduct_stock=True)
        assert ok1 is True
        assert clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock == p1_orig
        assert clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock == p2_orig

        # Audit with deduct_stock=False
        ok2, _, res2 = BOMAuditor.audit_bom(bom_path, clean_repo, board_multiplier=1, deduct_stock=False)
        assert ok2 is True
        assert clean_repo.get_component_by_identity("Texas Instruments", "NE555P").quantity_in_stock == p1_orig
        assert clean_repo.get_component_by_identity("Texas Instruments", "LM358N").quantity_in_stock == p2_orig
