"""
Omnix Automated Tests — Comprehensive Reference Autocomplete Data Integrity Audit
Governing Document: Omnix Reference Autocomplete Data Integrity Specification

Guarantees:
- Typing, editing, deleting characters, pressing Enter or Tab, changing focus, and saving a component
  cannot silently create new autocomplete options or invalid reference records.
- Applies independently to all three fields:
  1. Manufacturer (mfr_input, ref_manufacturers)
  2. Category (category_combo, ref_categories)
  3. Type / Technology (tech_combo, ref_types)
- QComboBox.InsertPolicy.NoInsert is strictly enforced on all three fields.
- Tab unique-match completion and single focus traversal remain intact.
- Enter on partial or unrecognized text never inserts new dropdown options or database records.
- Invalid reference values are strictly rejected on Save.
- Models and SQLite reference tables are verified before and after each interaction.
"""

import os
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QFocusEvent
from PyQt6.QtWidgets import QApplication, QComboBox
from PyQt6.QtTest import QTest

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.component_edit_dialog import ComponentEditDialog


@pytest.fixture
def isolated_db(tmp_path):
    """Creates an isolated test database with dynamic reference fixtures."""
    db_file = str(tmp_path / "test_ref_integrity.db")
    repo = SqliteInventoryRepository(db_file)

    # 1. Seed Manufacturers
    repo.add_manufacturer("Texas Instruments")
    repo.add_manufacturer("TDK")
    repo.add_manufacturer("Vishay Intertechnology")
    repo.add_manufacturer("STMicroelectronics")

    # 2. Seed Categories
    repo.add_category("Capacitor")
    repo.add_category("Connector")
    repo.add_category("Resistor")

    # 3. Seed Types for Resistor
    cat_res = repo.get_category_by_name("Resistor")
    repo.add_type(cat_res.id, "Thick Film")
    repo.add_type(cat_res.id, "Thin Film")
    repo.add_type(cat_res.id, "Wirewound")

    # 4. Seed Types for Capacitor
    cat_cap = repo.get_category_by_name("Capacitor")
    repo.add_type(cat_cap.id, "Ceramic")
    repo.add_type(cat_cap.id, "Electrolytic")
    repo.add_type(cat_cap.id, "Film")

    yield repo
    repo.close()


class TestManufacturerDataIntegrity:
    """Group A: Independent audit for Manufacturer field (mfr_input, ref_manufacturers)."""

    def test_mfr_no_insert_policy_enforced(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        assert dlg.mfr_input.insertPolicy() == QComboBox.InsertPolicy.NoInsert
        dlg.close()

    def test_mfr_existing_valid_appears_as_suggestion(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        items = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert "STMicroelectronics" in items
        assert "Texas Instruments" in items
        dlg.close()

    def test_mfr_typing_filters_without_adding_options(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        count_before = dlg.mfr_input.count()
        db_count_before = len(isolated_db.get_all_manufacturers())

        dlg.mfr_input.setFocus()
        qapp.processEvents()
        for ch in "stm":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        assert dlg.mfr_input.count() == count_before
        assert len(isolated_db.get_all_manufacturers()) == db_count_before
        dlg.close()

    def test_mfr_select_stmicroelectronics_and_edit_to_stmicroel_enter_does_not_mutate_model_or_db(self, qapp, isolated_db):
        """Reproduction scenario: select STMicroelectronics, edit to STMicroel, press Enter."""
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        db_before = [m.name for m in isolated_db.get_all_manufacturers()]
        combo_before = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]

        # Select STMicroelectronics
        idx = dlg.mfr_input.findText("STMicroelectronics")
        dlg.mfr_input.setCurrentIndex(idx)
        qapp.processEvents()

        # Edit text to STMicroel
        dlg.mfr_input.lineEdit().setText("STMicroel")
        qapp.processEvents()

        # Press Enter
        QTest.keyClick(app_focus := qapp.focusWidget(), Qt.Key.Key_Return)
        qapp.processEvents()

        db_after = [m.name for m in isolated_db.get_all_manufacturers()]
        combo_after = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        comp = dlg.mfr_input.completer()
        comp_items = [comp.model().index(r, 0).data() for r in range(comp.model().rowCount())]

        # PROVE: 'STMicroel' is NOT in dropdown, NOT in completer model, NOT in database
        assert "STMicroel" not in combo_after
        assert "STMicroel" not in comp_items
        assert isolated_db.get_manufacturer_by_name("STMicroel") is None
        assert len(combo_after) == len(combo_before)
        assert len(db_after) == len(db_before)

        # Reopen dropdown and verify
        comp.setCompletionPrefix("STMicroel")
        comp.complete()
        qapp.processEvents()
        popup = comp.popup()
        if popup and popup.model():
            popup_items = [popup.model().index(r, 0).data() for r in range(popup.model().rowCount())]
            assert "STMicroel" not in popup_items
            assert "STMicroelectronics" in popup_items

        dlg.close()

    def test_mfr_unmatched_enter_preserves_text_without_creating_record(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        db_count_before = len(isolated_db.get_all_manufacturers())
        combo_count_before = dlg.mfr_input.count()

        dlg.mfr_input.lineEdit().setText("CustomUnknownMfr")
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Return)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "CustomUnknownMfr"
        assert "CustomUnknownMfr" not in [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert dlg.mfr_input.count() == combo_count_before
        assert isolated_db.get_manufacturer_by_name("CustomUnknownMfr") is None
        assert len(isolated_db.get_all_manufacturers()) == db_count_before
        dlg.close()

    def test_mfr_tab_commits_canonical_and_advances_focus_once(self, qapp, isolated_db):
        """Verifies stm -> Tab commits STMicroelectronics and moves focus to MPN."""
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        for ch in "stm":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "STMicroelectronics"
        assert qapp.focusWidget() == dlg.mpn_input
        dlg.close()

    def test_mfr_ambiguous_tab_does_not_commit_arbitrarily(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), "t")
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "t"
        assert qapp.focusWidget() == dlg.mpn_input
        dlg.close()

    def test_mfr_save_rejects_invalid_manufacturer(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setEditText("BogusManufacturer")
        dlg.mpn_input.setText("TEST-MPN-1")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        qapp.processEvents()

        db_count_before = len(isolated_db.get_all_manufacturers())
        dlg.save_btn.click()
        qapp.processEvents()

        assert dlg.result() == 0  # Blocked
        assert "not in canonical reference data" in dlg.validation_lbl.text()
        assert len(isolated_db.get_all_manufacturers()) == db_count_before
        dlg.close()


class TestCategoryDataIntegrity:
    """Group B: Independent audit for Category field (category_combo, ref_categories)."""

    def test_cat_no_insert_policy_enforced(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        assert dlg.category_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert
        dlg.close()

    def test_cat_existing_suggestions_loaded_from_db(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        items = [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]
        assert "Capacitor" in items
        assert "Resistor" in items
        assert "Connector" in items
        dlg.close()

    def test_cat_select_and_edit_enter_does_not_mutate_model_or_db(self, qapp, isolated_db):
        """Reproduction: Select Capacitor, backspace/edit to Capaci, press Enter."""
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.category_combo.setFocus()
        qapp.processEvents()

        db_before = [c.name for c in isolated_db.get_all_categories()]
        combo_before = [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]

        idx = dlg.category_combo.findText("Capacitor")
        dlg.category_combo.setCurrentIndex(idx)
        qapp.processEvents()

        dlg.category_combo.lineEdit().setText("Capaci")
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Return)
        qapp.processEvents()

        db_after = [c.name for c in isolated_db.get_all_categories()]
        combo_after = [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]

        assert "Capaci" not in combo_after
        assert isolated_db.get_category_by_name("Capaci") is None
        assert len(combo_after) == len(combo_before)
        assert len(db_after) == len(db_before)
        dlg.close()

    def test_cat_tab_commits_unique_and_advances_to_tech(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.category_combo.setFocus()
        qapp.processEvents()

        for ch in "cap":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.category_combo.currentText() == "Capacitor"
        assert qapp.focusWidget() in (dlg.tech_combo, dlg.tech_combo.lineEdit())
        dlg.close()

    def test_cat_save_rejects_invalid_category(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setCurrentText("Texas Instruments")
        dlg.mpn_input.setText("TEST-MPN-2")
        dlg.category_combo.setEditText("InvalidCategory99")
        dlg.tech_combo.setEditText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        qapp.processEvents()

        db_count_before = len(isolated_db.get_all_categories())
        dlg.save_btn.click()
        qapp.processEvents()

        assert dlg.result() == 0
        assert "Category 'InvalidCategory99' is not in canonical reference data" in dlg.validation_lbl.text()
        assert len(isolated_db.get_all_categories()) == db_count_before
        dlg.close()


class TestTypeTechnologyDataIntegrity:
    """Group C: Independent audit for Type / Technology field (tech_combo, ref_types)."""

    def test_tech_no_insert_policy_enforced(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        assert dlg.tech_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert
        dlg.close()

    def test_tech_select_and_edit_enter_does_not_mutate_model_or_db(self, qapp, isolated_db):
        """Reproduction: Select Category Capacitor, select Film, edit to Fil, press Enter."""
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        cap_rec = isolated_db.get_category_by_name("Capacitor")
        db_before = [t.name for t in isolated_db.get_types_for_category(cap_rec.id)]
        combo_before = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]

        dlg.tech_combo.setFocus()
        idx = dlg.tech_combo.findText("Film")
        dlg.tech_combo.setCurrentIndex(idx)
        qapp.processEvents()

        dlg.tech_combo.lineEdit().setText("Fil")
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Return)
        qapp.processEvents()

        db_after = [t.name for t in isolated_db.get_types_for_category(cap_rec.id)]
        combo_after = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]

        assert "Fil" not in combo_after
        assert isolated_db.get_type_by_name(cap_rec.id, "Fil") is None
        assert len(combo_after) == len(combo_before)
        assert len(db_after) == len(db_before)
        dlg.close()

    def test_tech_category_change_refreshes_without_retaining_invalid_entries(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        cap_items = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Ceramic" in cap_items
        assert "Film" in cap_items

        # Change to Resistor
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        res_items = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Thick Film" in res_items
        assert "Thin Film" in res_items
        assert "Wirewound" in res_items
        assert "Ceramic" not in res_items
        assert "Film" not in res_items
        dlg.close()

    def test_tech_save_rejects_incompatible_or_invalid_type(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        dlg.mfr_input.setCurrentText("Texas Instruments")
        dlg.mpn_input.setText("TEST-MPN-3")
        dlg.category_combo.setCurrentText("Resistor")
        # Try to use Ceramic under Resistor
        dlg.tech_combo.setEditText("Ceramic")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        qapp.processEvents()

        res_rec = isolated_db.get_category_by_name("Resistor")
        db_count_before = len(isolated_db.get_types_for_category(res_rec.id))
        dlg.save_btn.click()
        qapp.processEvents()

        assert dlg.result() == 0
        assert "not valid for category 'Resistor'" in dlg.validation_lbl.text()
        assert len(isolated_db.get_types_for_category(res_rec.id)) == db_count_before
        dlg.close()


class TestCrossFieldDataIntegrity:
    """Group D: Comprehensive cross-field lifecycle and interaction tests."""

    def test_deleting_characters_and_blur_does_not_mutate_models(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        qapp.processEvents()

        # 1. Manufacturer
        mfr_count_init = dlg.mfr_input.count()
        dlg.mfr_input.setCurrentText("Vishay Intertechnology")
        dlg.mfr_input.lineEdit().setText("Vish")
        qapp.processEvents()
        dlg.mpn_input.setFocus()
        qapp.processEvents()
        assert dlg.mfr_input.count() == mfr_count_init
        assert "Vish" not in [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]

        # 2. Category
        cat_count_init = dlg.category_combo.count()
        dlg.category_combo.setCurrentText("Connector")
        dlg.category_combo.lineEdit().setText("Conn")
        qapp.processEvents()
        dlg.tech_combo.setFocus()
        qapp.processEvents()
        assert dlg.category_combo.count() == cat_count_init
        assert "Conn" not in [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]

        # 3. Type
        tech_count_init = dlg.tech_combo.count()
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()
        dlg.tech_combo.setCurrentText("Wirewound")
        dlg.tech_combo.lineEdit().setText("Wire")
        qapp.processEvents()
        dlg.value_input.setFocus()
        qapp.processEvents()
        assert "Wire" not in [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]

        dlg.close()

    def test_full_save_with_valid_data_persists_component_without_reference_table_mutations(self, qapp, isolated_db):
        dlg = ComponentEditDialog(repository=isolated_db)
        dlg.show()
        qapp.processEvents()

        mfr_count_before = len(isolated_db.get_all_manufacturers())
        cat_count_before = len(isolated_db.get_all_categories())
        res_rec = isolated_db.get_category_by_name("Resistor")
        type_count_before = len(isolated_db.get_types_for_category(res_rec.id))

        dlg.mfr_input.setCurrentText("Texas Instruments")
        dlg.mpn_input.setText("SN74HC00N")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        dlg.qty_spin.setValue(10)
        qapp.processEvents()

        dlg.save_btn.click()
        qapp.processEvents()

        assert dlg.result() == 1
        assert dlg.saved_component is not None

        # Verify component persisted
        comp = isolated_db.get_component_by_id(dlg.saved_component.id)
        assert comp.manufacturer == "Texas Instruments"
        assert comp.category == "Resistor"
        assert comp.type_technology == "Thick Film"

        # Verify reference tables are 100% UNCHANGED
        assert len(isolated_db.get_all_manufacturers()) == mfr_count_before
        assert len(isolated_db.get_all_categories()) == cat_count_before
        assert len(isolated_db.get_types_for_category(res_rec.id)) == type_count_before

        dlg.close()
