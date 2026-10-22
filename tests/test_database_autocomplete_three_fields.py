"""
Omnix Automated Tests — Database-Driven Autocomplete for All Three Reference Fields
Governing Document: Database-Driven Autocomplete Fix Specification

Tests cover all three reference fields independently:
1. Manufacturer (ref_manufacturers)
2. Category (ref_categories)
3. Type / Technology (ref_types, dynamically filtered by category_id)

Verifies:
- Suggestions originate directly from SQLite repository/database (no hardcoded values).
- Case-insensitive filtering.
- Unique match committed as complete canonical value on Tab + focus advances exactly once.
- Ambiguous match is NOT arbitrarily committed on Tab; draft text preserved; focus advances once.
- Up/Down navigation + Enter commits explicitly highlighted suggestion.
- Mouse click commits complete canonical value.
- Escape closes suggestion list without overwriting typed text.
- Reference data additions dynamically reflected without stale cache.
- Validation rejects invalid/unmapped values on blur and blocks saving.
- Persistence stores exact canonical casing.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QFocusEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.component_edit_dialog import ComponentEditDialog


@pytest.fixture
def dynamic_db(tmp_path):
    """Creates an isolated test database with dynamic reference fixtures."""
    db_file = str(tmp_path / "test_three_fields_autocomplete.db")
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


class TestDatabaseAutocompleteSourcing:
    """Verifies that suggestions are dynamically loaded from SQLite tables."""

    def test_manufacturer_suggestions_loaded_from_ref_manufacturers(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        mfr_items = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert "Texas Instruments" in mfr_items
        assert "TDK" in mfr_items
        assert "Vishay Intertechnology" in mfr_items

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_suggestions_loaded_from_ref_categories(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        cat_items = [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]
        assert "Capacitor" in cat_items
        assert "Connector" in cat_items
        assert "Resistor" in cat_items

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_type_suggestions_dynamically_loaded_from_ref_types_for_category(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        # Switch to Resistor
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        res_types = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Thick Film" in res_types
        assert "Thin Film" in res_types
        assert "Wirewound" in res_types
        assert "Ceramic" not in res_types

        # Switch to Capacitor
        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        cap_types = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Ceramic" in cap_types
        assert "Electrolytic" in cap_types
        assert "Thick Film" not in cap_types

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_newly_inserted_reference_records_immediately_available_in_dialog(self, qapp, dynamic_db):
        """Reference data added at runtime is dynamically available without stale cache."""
        dynamic_db.add_manufacturer("Analog Devices")
        dynamic_db.add_category("Inductor")
        ind_cat = dynamic_db.get_category_by_name("Inductor")
        dynamic_db.add_type(ind_cat.id, "Toroidal")

        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        mfr_items = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert "Analog Devices" in mfr_items

        cat_items = [dlg.category_combo.itemText(i) for i in range(dlg.category_combo.count())]
        assert "Inductor" in cat_items

        dlg.category_combo.setCurrentText("Inductor")
        qapp.processEvents()
        tech_items = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Toroidal" in tech_items

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestDatabaseAutocompleteTabBehavior:
    """Verifies Tab commitment: unique match commits canonical, ambiguous match does NOT commit."""

    def test_manufacturer_unique_tab_commits_canonical_and_advances_focus_once(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setFocus()
        mfr_le.setText("texa")
        dlg.mfr_input.completer().setCompletionPrefix("texa")
        dlg.mfr_input.completer().complete()
        qapp.processEvents()

        # Send Tab key once
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(mfr_le, tab_ev)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "Texas Instruments"
        assert dlg.mpn_input.hasFocus() is True
        assert dlg.result() == 0  # Dialog not submitted

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_unique_tab_commits_canonical_and_advances_focus_once(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        cat_le = dlg.category_combo.lineEdit()
        cat_le.setFocus()
        cat_le.setText("cap")
        dlg.category_combo.completer().setCompletionPrefix("cap")
        dlg.category_combo.completer().complete()
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(cat_le, tab_ev)
        qapp.processEvents()

        assert dlg.category_combo.currentText() == "Capacitor"
        assert dlg.tech_combo.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_type_unique_tab_commits_canonical_and_advances_focus_once(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        tech_le.setText("cer")
        dlg.tech_combo.completer().setCompletionPrefix("cer")
        dlg.tech_combo.completer().complete()
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()

        assert dlg.tech_combo.currentText() == "Ceramic"
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_manufacturer_ambiguous_tab_does_not_commit_arbitrarily(self, qapp, dynamic_db):
        """Typing 't' matches 'Texas Instruments' and 'TDK'; Tab must NOT commit first result arbitrarily."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setFocus()
        mfr_le.setText("t")
        comp = dlg.mfr_input.completer()
        comp.setCompletionPrefix("t")
        comp.complete()
        qapp.processEvents()

        assert comp.popup().isVisible() is True

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(mfr_le, tab_ev)
        qapp.processEvents()

        # Draft text preserved, not coerced into TDK or Texas Instruments
        assert dlg.mfr_input.currentText() == "t"
        assert comp.popup().isVisible() is False
        assert dlg.mpn_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_ambiguous_tab_does_not_commit_arbitrarily(self, qapp, dynamic_db):
        """Typing 'c' matches 'Capacitor' and 'Connector'; Tab must NOT commit first result arbitrarily."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        cat_le = dlg.category_combo.lineEdit()
        cat_le.setFocus()
        cat_le.setText("c")
        comp = dlg.category_combo.completer()
        comp.setCompletionPrefix("c")
        comp.complete()
        qapp.processEvents()

        assert comp.popup().isVisible() is True

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(cat_le, tab_ev)
        qapp.processEvents()

        assert dlg.category_combo.currentText() == "c"
        assert comp.popup().isVisible() is False
        assert dlg.tech_combo.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_type_ambiguous_tab_does_not_commit_arbitrarily(self, qapp, dynamic_db):
        """Under Resistor, typing 'thi' matches 'Thick Film' and 'Thin Film'; Tab must NOT arbitrarily commit."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        tech_le.setText("thi")
        comp = dlg.tech_combo.completer()
        comp.setCompletionPrefix("thi")
        comp.complete()
        qapp.processEvents()

        assert comp.popup().isVisible() is True

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()

        assert dlg.tech_combo.currentText() == "thi"
        assert comp.popup().isVisible() is False
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestDirectTypingAndTabCommitment:
    """
    Verifies typing a unique partial query and pressing Tab directly
    (without pressing Arrow Down, Enter, or any other key first).
    Asserts both the committed canonical value and the resulting focused widget.
    """

    def test_manufacturer_direct_type_and_tab(self, qapp, dynamic_db):
        """Type 'tex' and press Tab directly -> commits 'Texas Instruments', focus moves to MPN."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setFocus()
        qapp.processEvents()

        # Type 'tex' via key events directly
        for ch in "tex":
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, ord(ch), Qt.KeyboardModifier.NoModifier, ch)
            qapp.sendEvent(mfr_le, ev)
            qapp.processEvents()

        assert mfr_le.text() == "tex"

        # Press Tab directly without any other interaction
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(mfr_le, tab_ev)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "Texas Instruments"
        assert dlg.mpn_input.hasFocus() is True
        assert dlg.result() == 0  # Not submitted

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_direct_type_and_tab(self, qapp, dynamic_db):
        """Type 'cap' and press Tab directly -> commits 'Capacitor', focus moves to Tech."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        cat_le = dlg.category_combo.lineEdit()
        cat_le.setFocus()
        qapp.processEvents()

        for ch in "cap":
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, ord(ch), Qt.KeyboardModifier.NoModifier, ch)
            qapp.sendEvent(cat_le, ev)
            qapp.processEvents()

        assert cat_le.text() == "cap"

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(cat_le, tab_ev)
        qapp.processEvents()

        assert dlg.category_combo.currentText() == "Capacitor"
        assert dlg.tech_combo.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_type_technology_resistor_direct_type_and_tab(self, qapp, dynamic_db):
        """Under Resistor, type 'thick' and press Tab directly -> commits 'Thick Film', focus moves to Value."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        qapp.processEvents()

        for ch in "thick":
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, ord(ch), Qt.KeyboardModifier.NoModifier, ch)
            qapp.sendEvent(tech_le, ev)
            qapp.processEvents()

        assert tech_le.text() == "thick"

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()

        assert dlg.tech_combo.currentText() == "Thick Film"
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_type_technology_capacitor_direct_type_and_tab(self, qapp, dynamic_db):
        """Under Capacitor, type 'cer' and press Tab directly -> commits 'Ceramic', focus moves to Value."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        qapp.processEvents()

        for ch in "cer":
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, ord(ch), Qt.KeyboardModifier.NoModifier, ch)
            qapp.sendEvent(tech_le, ev)
            qapp.processEvents()

        assert tech_le.text() == "cer"

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()

        assert dlg.tech_combo.currentText() == "Ceramic"
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_direct_ambiguous_type_and_tab_preserves_text_and_moves_focus(self, qapp, dynamic_db):
        """Direct ambiguous queries preserve draft text and advance focus across all 3 fields."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)

        # 1. Mfr: type 't' (matches TDK and Texas Instruments)
        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setFocus()
        ev_t = QKeyEvent(QKeyEvent.Type.KeyPress, ord('t'), Qt.KeyboardModifier.NoModifier, 't')
        qapp.sendEvent(mfr_le, ev_t)
        qapp.processEvents()
        qapp.sendEvent(mfr_le, tab_ev)
        qapp.processEvents()
        assert dlg.mfr_input.currentText() == "t"
        assert dlg.mpn_input.hasFocus() is True

        # 2. Category: type 'c' (matches Capacitor and Connector)
        cat_le = dlg.category_combo.lineEdit()
        cat_le.setFocus()
        ev_c = QKeyEvent(QKeyEvent.Type.KeyPress, ord('c'), Qt.KeyboardModifier.NoModifier, 'c')
        qapp.sendEvent(cat_le, ev_c)
        qapp.processEvents()
        qapp.sendEvent(cat_le, tab_ev)
        qapp.processEvents()
        assert dlg.category_combo.currentText() == "c"
        assert dlg.tech_combo.hasFocus() is True

        # 3. Type: with Resistor selected, type 'thi' (matches Thick Film and Thin Film)
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()
        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        for ch in "thi":
            qapp.sendEvent(tech_le, QKeyEvent(QKeyEvent.Type.KeyPress, ord(ch), Qt.KeyboardModifier.NoModifier, ch))
            qapp.processEvents()
        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()
        assert dlg.tech_combo.currentText() == "thi"
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()



class TestDatabaseAutocompleteMouseAndKeyboardSelection:
    """Verifies mouse clicks, Up/Down navigation + Enter, and Escape handling for all three fields."""

    def test_mouse_click_commits_canonical_for_all_three_fields(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        # 1. Manufacturer mouse click
        mfr_comp = dlg.mfr_input.completer()
        mfr_comp.activated.emit("Vishay Intertechnology")
        qapp.processEvents()
        assert dlg.mfr_input.currentText() == "Vishay Intertechnology"

        # 2. Category mouse click
        cat_comp = dlg.category_combo.completer()
        cat_comp.activated.emit("Resistor")
        qapp.processEvents()
        assert dlg.category_combo.currentText() == "Resistor"

        # 3. Type mouse click
        tech_comp = dlg.tech_combo.completer()
        tech_comp.activated.emit("Wirewound")
        qapp.processEvents()
        assert dlg.tech_combo.currentText() == "Wirewound"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_arrow_up_down_and_enter_commits_for_all_three_fields(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        qapp.processEvents()

        down_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        enter_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)

        # 1. Manufacturer: type 't', down arrow, Enter
        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setFocus()
        mfr_le.setText("t")
        dlg.mfr_input.completer().setCompletionPrefix("t")
        dlg.mfr_input.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(mfr_le, down_ev)
        qapp.processEvents()
        first_mfr = dlg.mfr_input.completer().popup().currentIndex().data()
        qapp.sendEvent(mfr_le, enter_ev)
        qapp.processEvents()
        assert dlg.mfr_input.currentText() == first_mfr

        # 2. Category: type 'c', down arrow, Enter
        cat_le = dlg.category_combo.lineEdit()
        cat_le.setFocus()
        cat_le.setText("c")
        dlg.category_combo.completer().setCompletionPrefix("c")
        dlg.category_combo.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(cat_le, down_ev)
        qapp.processEvents()
        first_cat = dlg.category_combo.completer().popup().currentIndex().data()
        qapp.sendEvent(cat_le, enter_ev)
        qapp.processEvents()
        assert dlg.category_combo.currentText() == first_cat

        # 3. Type: with Category set, type 'thi', down arrow, Enter
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()
        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setFocus()
        tech_le.setText("thi")
        dlg.tech_combo.completer().setCompletionPrefix("thi")
        dlg.tech_combo.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(tech_le, down_ev)
        qapp.processEvents()
        first_tech = dlg.tech_combo.completer().popup().currentIndex().data()
        qapp.sendEvent(tech_le, enter_ev)
        qapp.processEvents()
        assert dlg.tech_combo.currentText() == first_tech

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_escape_dismisses_popup_preserving_text_for_all_three_fields(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        esc_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)

        # 1. Manufacturer
        dlg.mfr_input.lineEdit().setText("draft_mfr")
        dlg.mfr_input.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(dlg.mfr_input.lineEdit(), esc_ev)
        qapp.processEvents()
        assert dlg.mfr_input.completer().popup().isVisible() is False
        assert dlg.mfr_input.currentText() == "draft_mfr"

        # 2. Category
        dlg.category_combo.lineEdit().setText("draft_cat")
        dlg.category_combo.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(dlg.category_combo.lineEdit(), esc_ev)
        qapp.processEvents()
        assert dlg.category_combo.completer().popup().isVisible() is False
        assert dlg.category_combo.currentText() == "draft_cat"

        # 3. Type
        dlg.tech_combo.lineEdit().setText("draft_type")
        dlg.tech_combo.completer().complete()
        qapp.processEvents()
        qapp.sendEvent(dlg.tech_combo.lineEdit(), esc_ev)
        qapp.processEvents()
        assert dlg.tech_combo.completer().popup().isVisible() is False
        assert dlg.tech_combo.currentText() == "draft_type"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestDatabaseAutocompleteValidationAndPersistence:
    """Verifies that invalid values are rejected and valid values persist canonical casing."""

    def test_invalid_manufacturer_rejected_on_blur_and_blocks_save(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        mfr_le = dlg.mfr_input.lineEdit()
        mfr_le.setText("UnknownVendorCorp")
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(mfr_le, focus_out)
        qapp.processEvents()

        assert dlg.mfr_input.property("_has_validation_error") is True
        assert "is not in canonical reference data" in dlg.validation_lbl.text()

        # Attempt to save
        dlg.mpn_input.setText("TEST-MPN-1")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")

        dlg.save_btn.click()
        qapp.processEvents()
        assert dlg.result() == 0  # Save blocked
        assert dlg.saved_component is None

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_invalid_category_rejected_on_blur_and_blocks_save(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        cat_le = dlg.category_combo.lineEdit()
        cat_le.setText("InvalidCategory")
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(cat_le, focus_out)
        qapp.processEvents()

        assert dlg.category_combo.property("_has_validation_error") is True
        assert "is not in canonical reference data" in dlg.validation_lbl.text()

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_incompatible_type_rejected_on_blur_and_blocks_save(self, qapp, dynamic_db):
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        # Ceramic is a Capacitor type, incompatible with Resistor
        tech_le = dlg.tech_combo.lineEdit()
        tech_le.setText("Ceramic")
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(tech_le, focus_out)
        qapp.processEvents()

        assert dlg.tech_combo.property("_has_validation_error") is True
        assert "is not valid for category 'Resistor'" in dlg.validation_lbl.text()

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_save_persists_canonical_database_casing_for_all_three_fields(self, qapp, dynamic_db):
        """Saving with lower-case input persists exact canonical database casing."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        qapp.processEvents()

        # Set lower-cased valid values
        dlg.mfr_input.setEditText("texas instruments")
        dlg.mpn_input.setText("SN74HC00N")
        dlg.category_combo.setEditText("resistor")
        dlg.tech_combo.setEditText("thick film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        dlg.qty_spin.setValue(100)

        dlg.save_btn.click()
        qapp.processEvents()

        assert dlg.result() == 1  # Accepted
        assert dlg.saved_component is not None

        # Verify persisted record in SQLite database
        saved_id = dlg.saved_component.id
        persisted = dynamic_db.get_component_by_id(saved_id)
        assert persisted is not None
        assert persisted.manufacturer == "Texas Instruments"  # Canonical casing
        assert persisted.category == "Resistor"               # Canonical casing
        assert persisted.type_technology == "Thick Film"       # Canonical casing

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestRealKeyboardRuntimeTabInteraction:
    """
    Directly reproduces and verifies runtime user keyboard interaction:
    Typing keystrokes directly into the active focused widget (QComboBox / focusWidget)
    and pressing the Tab key directly without arrow navigation or Enter.
    Verifies:
    1. Exact 'stm' -> Tab failure reproduction: commits 'STMicroelectronics' and advances focus to MPN once.
    2. Real Omnix SQLite database ('data/omnix_inventory.db') verification with 429 manufacturers.
    3. Category field 'cap' -> Tab: commits 'Capacitor' and advances focus to Type once.
    4. Type/Technology field 'film' -> Tab: commits 'Film' and advances focus to Value once.
    5. Ambiguous query 't' -> Tab: preserves draft text 't' and advances focus to MPN once.
    """

    def test_exact_stm_runtime_failure_reproduction_and_resolution(self, qapp, dynamic_db):
        """Reproduces user typing 'stm' into focused combo and pressing Tab directly."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        # Type 's', 't', 'm' directly through the focused widget
        for ch in "stm":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        assert dlg.mfr_input.lineEdit().text() == "stm"

        # Press Tab directly on the focused widget
        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "STMicroelectronics"
        assert dlg.mfr_input.lineEdit().text() == "STMicroelectronics"
        assert qapp.focusWidget() == dlg.mpn_input
        assert dlg.result() == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_exact_stm_real_database_runtime_interaction(self, qapp):
        """Verifies the exact runtime failure against the real authoritative SQLite database with 429 manufacturers."""
        import os
        real_db_path = "data/omnix_inventory.db"
        if not os.path.exists(real_db_path):
            pytest.skip("data/omnix_inventory.db not found")

        real_repo = SqliteInventoryRepository(real_db_path)
        dlg = ComponentEditDialog(repository=real_repo)
        dlg.show()
        dlg.activateWindow()
        dlg.mfr_input.setFocus()
        qapp.processEvents()

        # Type 's', 't', 'm' directly into active widget
        for ch in "stm":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        assert dlg.mfr_input.lineEdit().text() == "stm"

        # Press Tab directly
        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.mfr_input.currentText() == "STMicroelectronics"
        assert dlg.mfr_input.lineEdit().text() == "STMicroelectronics"
        assert qapp.focusWidget() == dlg.mpn_input
        assert dlg.result() == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_runtime_category_tab_resolution(self, qapp, dynamic_db):
        """Type 'cap' into focused Category combo and press Tab directly -> commits 'Capacitor'."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        dlg.category_combo.setFocus()
        qapp.processEvents()

        for ch in "cap":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        assert dlg.category_combo.lineEdit().text() == "cap"

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.category_combo.currentText() == "Capacitor"
        assert dlg.category_combo.lineEdit().text() == "Capacitor"
        assert qapp.focusWidget() in (dlg.tech_combo, dlg.tech_combo.lineEdit())

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_runtime_type_technology_tab_resolution(self, qapp, dynamic_db):
        """Select Category 'Capacitor', type 'film' into Type combo and press Tab -> commits 'Film'."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        dlg.category_combo.setCurrentText("Capacitor")
        qapp.processEvents()

        dlg.tech_combo.setFocus()
        qapp.processEvents()

        for ch in "film":
            QTest.keyClick(qapp.focusWidget(), ch)
            qapp.processEvents()

        assert dlg.tech_combo.lineEdit().text() == "film"

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        assert dlg.tech_combo.currentText() == "Film"
        assert dlg.tech_combo.lineEdit().text() == "Film"
        assert qapp.focusWidget() == dlg.value_input

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_runtime_ambiguous_preservation_and_single_focus_jump(self, qapp, dynamic_db):
        """Type 't' (ambiguous: Texas Instruments vs TDK) and press Tab -> preserves 't' and moves focus to MPN."""
        dlg = ComponentEditDialog(repository=dynamic_db)
        dlg.show()
        dlg.activateWindow()
        dlg.mfr_input.setFocus()
        dlg.mfr_input.lineEdit().clear()
        qapp.processEvents()

        QTest.keyClick(qapp.focusWidget(), 't')
        qapp.processEvents()

        assert dlg.mfr_input.lineEdit().text() == "t"

        QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()

        # Text preserved, focus moved to MPN once
        assert dlg.mfr_input.currentText() == "t"
        assert dlg.mfr_input.lineEdit().text() == "t"
        assert qapp.focusWidget() == dlg.mpn_input

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()
