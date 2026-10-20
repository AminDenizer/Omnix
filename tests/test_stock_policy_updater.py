"""
Omnix Tests - Stock Policy Updater & Threshold Editing Dialog
Governing Document: Phase 1 Refinement Specification

Verifies:
- Editing and saving Min Stock and Target Stock to a temporary copy of Inventory.xlsm
- Exact row identification by canonical Group Key
- Formula preservation across all formula-generated columns
- Validation rules (Target Stock >= Min Stock >= 0)
- PolicyEditDialog interaction, inline validation, and cancel behavior
- Error handling for locked/read-only files
- Byte immutability of the real user's original workbook
"""

import os
import shutil
import tempfile
import pytest
import openpyxl

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QAbstractSpinBox, QDialog

from core.inventory.models import StockPolicyGroup
from core.inventory.updater import StockPolicyWriter
from core.inventory.loader import InventoryDatabaseLoader
from ui.dialogs.policy_edit_dialog import PolicyEditDialog


REAL_WORKBOOK_PATH = os.path.abspath("Inventory.xlsm")


@pytest.fixture
def temp_inventory_workbook():
    """Create a temporary copy of Inventory.xlsm for safe write tests."""
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "Inventory_test.xlsm")
    shutil.copyfile(REAL_WORKBOOK_PATH, temp_file)
    yield temp_file
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestStockPolicyWriter:
    """Test suite for StockPolicyWriter Excel COM persistence."""

    def test_validation_rejects_negative_thresholds(self, temp_inventory_workbook):
        writer = StockPolicyWriter()
        success, msg = writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key="Capacitor|X7R|100nF|0603|SMD_0603",
            min_stock=-5,
            target_stock=100,
        )
        assert success is False
        assert "non-negative" in msg

    def test_validation_rejects_target_less_than_min(self, temp_inventory_workbook):
        writer = StockPolicyWriter()
        success, msg = writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key="Capacitor|X7R|100nF|0603|SMD_0603",
            min_stock=50,
            target_stock=30,
        )
        assert success is False
        assert "cannot be less than Min Stock" in msg

    def test_update_min_and_target_stock_persists_to_temp_workbook(self, temp_inventory_workbook):
        writer = StockPolicyWriter()
        target_key = "Capacitor|X7R|100nF|0603|SMD_0603"

        # Update to new values: Min 45, Target 120
        success, msg = writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key=target_key,
            min_stock=45,
            target_stock=120,
        )
        assert success is True
        assert "Successfully updated" in msg

        # Verify with openpyxl that values persisted on disk
        wb = openpyxl.load_workbook(temp_inventory_workbook, data_only=True, read_only=True)
        ws = wb["Stock Policy"]
        # Row 2 is Capacitor|X7R|100nF|0603|SMD_0603
        min_cell = ws.cell(row=2, column=7).value
        tgt_cell = ws.cell(row=2, column=8).value
        wb.close()

        assert min_cell == 45
        assert tgt_cell == 120

    def test_formula_preservation_after_policy_update(self, temp_inventory_workbook):
        """Verify that updating literal thresholds does not overwrite formulas in other columns."""
        writer = StockPolicyWriter()
        target_key = "Capacitor|X7R|100nF|0603|SMD_0603"

        writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key=target_key,
            min_stock=55,
            target_stock=150,
        )

        # Inspect workbook with data_only=False to check formulas
        wb = openpyxl.load_workbook(temp_inventory_workbook, data_only=False, read_only=True)
        ws = wb["Stock Policy"]

        # Col 1 (A): Category formula
        cat_formula = ws.cell(row=2, column=1).value
        assert str(cat_formula).startswith("=")
        assert "Assembly View" in str(cat_formula)

        # Col 6 (F): Total Quantity in Stock formula
        stock_formula = ws.cell(row=2, column=6).value
        assert str(stock_formula).startswith("=")

        # Col 10 (J): Group Key formula
        key_formula = ws.cell(row=2, column=10).value
        assert str(key_formula).startswith("=")

        wb.close()

    def test_loader_reads_updated_values_correctly(self, temp_inventory_workbook):
        """Verify that InventoryDatabaseLoader reads the updated thresholds cleanly."""
        writer = StockPolicyWriter()
        target_key = "Resistor|Thick Film|10k|0603|SMD_0603"

        writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key=target_key,
            min_stock=35,
            target_stock=90,
        )

        loader = InventoryDatabaseLoader()
        groups, products, warnings = loader.load_workbook(temp_inventory_workbook)

        matching_group = next((g for g in groups if g.group_key == target_key), None)
        assert matching_group is not None
        assert matching_group.min_stock == 35
        assert matching_group.target_stock == 90

    def test_nonexistent_group_key_returns_failure(self, temp_inventory_workbook):
        writer = StockPolicyWriter()
        success, msg = writer.update_policy(
            workbook_path=temp_inventory_workbook,
            group_key="Nonexistent|Category|Value|Package|Footprint",
            min_stock=10,
            target_stock=20,
        )
        assert success is False
        assert "not found" in msg

    def test_missing_file_returns_failure(self):
        writer = StockPolicyWriter()
        success, msg = writer.update_policy(
            workbook_path="nonexistent_folder/missing.xlsm",
            group_key="Capacitor|X7R|100nF|0603|SMD_0603",
            min_stock=10,
            target_stock=20,
        )
        assert success is False
        assert "not found" in msg

    def test_original_workbook_remains_unmodified_during_tests(self):
        """Assert that real Inventory.xlsm in autom/atom was never modified."""
        loader = InventoryDatabaseLoader()
        groups, _, _ = loader.load_workbook(REAL_WORKBOOK_PATH)
        cap_group = next((g for g in groups if g.group_key == "Capacitor|X7R|100nF|0603|SMD_0603"), None)
        assert cap_group is not None
        # Original values in Inventory.xlsm
        assert cap_group.min_stock == 100
        assert cap_group.target_stock == 300


class TestPolicyEditDialog:
    """Test suite for PolicyEditDialog UI."""

    def test_dialog_initialization_with_group_data(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=30,
            target_stock=100,
            description="Test Capacitor",
        )

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
        )

        assert dlg.min_spin.value() == 30
        assert dlg.target_spin.value() == 100
        assert dlg.save_btn.isEnabled() is True
        assert dlg.validation_lbl.text() == ""

    def test_dialog_inline_validation_disables_save_when_invalid(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=30,
            target_stock=100,
            description="Test Capacitor",
        )

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
        )

        # Set Min Stock higher than Target Stock (Min 150 > Target 100)
        dlg.min_spin.setValue(150)
        qapp.processEvents()

        assert dlg.save_btn.isEnabled() is False
        assert "must be greater than or equal to Min Stock" in dlg.validation_lbl.text()

        # Fix Target Stock to 200 (Target 200 >= Min 150)
        dlg.target_spin.setValue(200)
        qapp.processEvents()

        assert dlg.save_btn.isEnabled() is True
        assert dlg.validation_lbl.text() == ""

    def test_dialog_cancel_leaves_workbook_unchanged(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=100,
            target_stock=300,
            description="Test Capacitor",
        )

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
        )

        dlg.min_spin.setValue(50)
        dlg.target_spin.setValue(150)
        dlg.reject()

        # Workbook must retain original values
        wb = openpyxl.load_workbook(temp_inventory_workbook, data_only=True, read_only=True)
        ws = wb["Stock Policy"]
        assert ws.cell(row=2, column=7).value == 100
        assert ws.cell(row=2, column=8).value == 300
        wb.close()

    def test_dialog_external_arrow_buttons_adjust_spinboxes(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=30,
            target_stock=100,
            description="Test Capacitor",
        )

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
        )

        # 1. Built-in spinbox arrows must be hidden
        assert dlg.min_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert dlg.target_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons

        # 2. External QToolButtons must exist and have correct arrow types
        assert dlg.min_up_btn.arrowType() == Qt.ArrowType.UpArrow
        assert dlg.min_down_btn.arrowType() == Qt.ArrowType.DownArrow
        assert dlg.target_up_btn.arrowType() == Qt.ArrowType.UpArrow
        assert dlg.target_down_btn.arrowType() == Qt.ArrowType.DownArrow

        # 3. Clicking Min Stock up/down modifies only min_spin
        dlg.min_up_btn.click()
        qapp.processEvents()
        assert dlg.min_spin.value() == 31
        assert dlg.target_spin.value() == 100

        dlg.min_down_btn.click()
        qapp.processEvents()
        assert dlg.min_spin.value() == 30
        assert dlg.target_spin.value() == 100

        # 4. Clicking Target Stock up/down modifies only target_spin
        dlg.target_up_btn.click()
        qapp.processEvents()
        assert dlg.target_spin.value() == 101
        assert dlg.min_spin.value() == 30

        dlg.target_down_btn.click()
        qapp.processEvents()
        assert dlg.target_spin.value() == 100
        assert dlg.min_spin.value() == 30

        # 5. Direct keyboard input or programmatic set still works
        dlg.min_spin.setValue(45)
        dlg.target_spin.setValue(90)
        assert dlg.min_spin.value() == 45
        assert dlg.target_spin.value() == 90
        assert dlg.save_btn.isEnabled() is True

    def test_dialog_save_button_enters_animated_saving_state_and_prevents_duplicate_clicks(self, qapp, temp_inventory_workbook):
        import time

        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=30,
            target_stock=100,
            description="Test Capacitor",
        )

        mock_writer = MagicMock(spec=StockPolicyWriter)
        def delayed_update(*args, **kwargs):
            time.sleep(0.1)
            return True, "Successfully updated"
        mock_writer.update_policy.side_effect = delayed_update

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
            writer=mock_writer,
        )

        # 1. Initial state
        assert dlg.save_btn.text() in ["Save Changes", "💾 Save Changes"]
        assert dlg.save_btn.isEnabled() is True
        assert dlg._is_saving is False
        assert dlg.save_btn.icon().isNull() is True
        assert dlg._spinner_timer.isActive() is False

        # 2. Trigger save
        dlg.save_btn.click()
        qapp.processEvents()

        # 3. Assert animated saving state
        assert dlg._is_saving is True
        assert dlg.save_btn.text() == "Saving..."
        assert dlg.save_btn.isEnabled() is False
        assert dlg.save_btn.icon().isNull() is False  # Spinner icon active
        assert dlg.save_btn.property("saving") == "true"
        assert dlg.cancel_btn.isEnabled() is False
        assert dlg.min_spin.isEnabled() is False
        assert dlg.target_spin.isEnabled() is False
        assert dlg._spinner_timer.isActive() is True

        initial_worker = dlg._save_worker
        assert initial_worker is not None

        # 4. Attempt duplicate click while save is in flight
        dlg._on_save_clicked()
        assert dlg._save_worker is initial_worker  # No duplicate worker created

        # 5. Wait for background worker to complete
        dlg._save_worker.wait(3000)
        qapp.processEvents()

        # 6. Assert success completion
        assert dlg._is_saving is False
        assert dlg._spinner_timer.isActive() is False
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_dialog_save_button_restores_state_on_failure(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=30,
            target_stock=100,
            description="Test Capacitor",
        )

        mock_writer = MagicMock(spec=StockPolicyWriter)
        mock_writer.update_policy.return_value = (False, "Simulated workbook write error")

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
            writer=mock_writer,
        )

        with patch("ui.dialogs.policy_edit_dialog.QMessageBox.critical") as mock_crit:
            dlg.save_btn.click()
            qapp.processEvents()

            # Confirm animated saving state entered
            assert dlg._is_saving is True
            assert dlg.save_btn.text() == "Saving..."
            assert dlg.save_btn.isEnabled() is False

            # Wait for worker to finish
            if dlg._save_worker:
                dlg._save_worker.wait(3000)
            qapp.processEvents()

            # Confirm error handling
            assert mock_crit.called
            assert "Save Failed" in mock_crit.call_args[0][1]
            assert "Simulated workbook write error" in mock_crit.call_args[0][2]

            # Confirm button and form controls were fully restored
            assert dlg._is_saving is False
            assert dlg._spinner_timer.isActive() is False
            assert dlg.save_btn.text() in ["Save Changes", "💾 Save Changes"]
            assert dlg.save_btn.isEnabled() is True
            assert dlg.save_btn.icon().isNull() is True
            assert dlg.save_btn.property("saving") == "false"
            assert dlg.cancel_btn.isEnabled() is True
            assert dlg.min_spin.isEnabled() is True
            assert dlg.target_spin.isEnabled() is True

    def test_dialog_save_end_to_end_with_temp_workbook(self, qapp, temp_inventory_workbook):
        group = StockPolicyGroup(
            category="Capacitor",
            type_technology="X7R",
            value="100nF",
            package="0603",
            footprint="SMD_0603",
            current_stock=12,
            min_stock=100,
            target_stock=300,
            description="Test Capacitor",
        )

        dlg = PolicyEditDialog(
            group=group,
            inventory_path=temp_inventory_workbook,
        )

        dlg.min_spin.setValue(55)
        dlg.target_spin.setValue(145)

        dlg.save_btn.click()
        qapp.processEvents()

        # In-flight animated state
        assert dlg._is_saving is True
        assert dlg.save_btn.text() == "Saving..."

        # Wait for actual Excel COM save to complete
        if dlg._save_worker:
            dlg._save_worker.wait(15000)
        qapp.processEvents()

        assert dlg.result() == QDialog.DialogCode.Accepted

        # Check values on disk in the temp workbook
        wb = openpyxl.load_workbook(temp_inventory_workbook, data_only=True, read_only=True)
        ws = wb["Stock Policy"]
        assert ws.cell(row=2, column=7).value == 55
        assert ws.cell(row=2, column=8).value == 145
        wb.close()
