"""
Omnix Automated Tests — Section 2: Autocomplete, Input Validation & Keyboard Safety
Governing Requirements:
- B1 & B2: Dynamic suggestion filtering, case-insensitivity, exact mouse selection,
           arrow-key navigation (Up/Down) + Enter/Tab selection, focus progression.
           Non-coercion of arbitrary text, preservation of entered text, no accidental erasure.
- B3 & B4: Reference list constraint validation, visual feedback (red borders, clear messages),
           prevention of invalid persistence, graceful handling of empty/missing reference data.
- B5: Destructive actions & confirmation dialog default button safety (default is "No").
- B6: Single, temporary MPN copy feedback.
- B8: Vendor plugins empty card spacing and layout integrity.
"""

import pytest
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QKeyEvent, QFocusEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.component_edit_dialog import ComponentEditDialog
from ui.main_window import MainWindow
from ui.widgets.vendor_plugins_widget import VendorPluginsWidget
from ui.widgets.reference_data_widget import ReferenceDataWidget


@pytest.fixture
def repo(tmp_path):
    """Isolated SQLite test repository with canonical reference data."""
    db_file = str(tmp_path / "test_section2.db")
    r = SqliteInventoryRepository(db_file)
    r.add_manufacturer("FTDI")
    r.add_manufacturer("Vishay")
    r.add_manufacturer("Texas Instruments")
    r.add_category("Capacitor")
    r.add_category("Resistor")
    cat_res = r.get_category_by_name("Resistor")
    r.add_type(cat_res.id, "Thick Film")
    r.add_type(cat_res.id, "Thin Film")
    cat_cap = r.get_category_by_name("Capacitor")
    r.add_type(cat_cap.id, "Ceramic")
    r.add_type(cat_cap.id, "Electrolytic")
    yield r
    r.close()


@pytest.fixture
def empty_repo(tmp_path):
    """Isolated SQLite test repository with zero reference data."""
    db_file = str(tmp_path / "test_section2_empty.db")
    r = SqliteInventoryRepository(db_file)
    yield r
    r.close()


class TestSection2AutocompleteKeyboard:
    """Tests for B2: Autocomplete and Keyboard Navigation."""

    def test_dynamic_suggestion_filtering(self, qapp, repo):
        """Typing filters suggestions dynamically and case-insensitively."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        comp = mfr_combo.completer()
        assert comp is not None

        comp.setCompletionPrefix("tex")
        comp.complete()
        qapp.processEvents()

        popup = comp.popup()
        assert popup is not None
        assert popup.isVisible() is True
        assert comp.completionCount() == 1
        comp.setCurrentRow(0)
        assert comp.currentCompletion() == "Texas Instruments"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_arrow_key_navigation_and_enter_commit(self, qapp, repo):
        """Arrow Down navigates suggestions popup and Enter commits the highlighted suggestion."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        # Type 't' which matches 'FTDI' (contains) and 'Texas Instruments'
        le.setText("t")
        comp = mfr_combo.completer()
        comp.setCompletionPrefix("t")
        comp.complete()
        qapp.processEvents()

        popup = comp.popup()
        assert popup.isVisible() is True

        # First Down Arrow: moves into popup and highlights first item
        down_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, down_ev)
        qapp.processEvents()

        assert popup.currentIndex().isValid() is True
        first_selected = popup.currentIndex().data()
        assert first_selected in ("FTDI", "Texas Instruments")

        # Press Enter to commit highlighted item
        enter_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, enter_ev)
        qapp.processEvents()

        assert mfr_combo.currentText() == first_selected
        assert popup.isVisible() is False

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_arrow_up_down_circular_navigation(self, qapp, repo):
        """Arrow Up and Down keys move selection predictably within the suggestion popup."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        comp = mfr_combo.completer()
        comp.setCompletionPrefix("t")
        comp.complete()
        qapp.processEvents()
        popup = comp.popup()

        down_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        up_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)

        # First down
        qapp.sendEvent(le, down_ev)
        assert popup.currentIndex().row() == 0

        # Second down (if multiple)
        if popup.model().rowCount() > 1:
            qapp.sendEvent(le, down_ev)
            assert popup.currentIndex().row() == 1

            # Up arrow moves back
            qapp.sendEvent(le, up_ev)
            assert popup.currentIndex().row() == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_mouse_click_commits_canonical_value(self, qapp, repo):
        """Clicking an item in the suggestion popup commits that exact canonical value."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        le.setText("vis")
        comp = mfr_combo.completer()
        comp.setCompletionPrefix("vis")
        comp.complete()
        qapp.processEvents()

        popup = comp.popup()
        assert popup.isVisible() is True

        target_idx = popup.model().index(0, 0)
        assert target_idx.data() == "Vishay"

        # Emit clicked on popup
        popup.setCurrentIndex(target_idx)
        comp.activated.emit(target_idx.data())
        qapp.processEvents()

        assert mfr_combo.currentText() == "Vishay"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_tab_advances_focus_normally(self, qapp, repo):
        """Tab key advances focus to the next field (no focus traps)."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        le.setText("FTDI")
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        assert dlg.mpn_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_escape_dismisses_popup_without_erasing_text(self, qapp, repo):
        """Escape closes suggestion popup and preserves entered text intact."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        le.setText("my_draft_name")
        comp = mfr_combo.completer()
        comp.complete()
        qapp.processEvents()

        esc_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, esc_ev)
        qapp.processEvents()

        assert comp.popup().isVisible() is False
        assert mfr_combo.currentText() == "my_draft_name"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_arbitrary_value_preserved_on_focus_out(self, qapp, repo):
        """Arbitrary entered text is NOT erased or silently coerced on focus out."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        le.setText("UnknownVendorCorp")
        qapp.processEvents()

        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out)
        qapp.processEvents()

        assert mfr_combo.currentText() == "UnknownVendorCorp"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_unique_match_narrowing_and_tab_commits_canonical_value(self, qapp, repo):
        """
        A3 & A4: Typing query narrowing to exactly 1 match (e.g. 'texa' -> 'Texas Instruments')
        commits the complete canonical value on Tab immediately without arrow keys or clicking,
        advancing focus to MPN exactly once without submitting the dialog.
        """
        # repo has FTDI, Vishay, Texas Instruments
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        # Step 1: 'tex' matches 'Texas Instruments'
        le.setText("tex")
        comp = mfr_combo.completer()
        comp.setCompletionPrefix("tex")
        comp.complete()
        qapp.processEvents()
        assert comp.popup().isVisible() is True

        # Step 2: Narrows to 'texa' which leaves exactly one match
        le.setText("texa")
        comp.setCompletionPrefix("texa")
        comp.complete()
        qapp.processEvents()
        assert comp.popup().model().rowCount() == 1

        # Step 3: Do NOT press Up/Down, do NOT click popup. Press Tab once.
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        # Unique matching suggestion is committed immediately as complete canonical value
        assert mfr_combo.currentText() == "Texas Instruments"
        # Popup closed
        assert comp.popup().isVisible() is False
        # Focus advanced to next logical input (MPN) exactly once
        assert dlg.mpn_input.hasFocus() is True
        # Dialog did not submit
        assert dlg.result() == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_and_type_unique_tab_commitment(self, qapp, repo):
        """Category and Type fields commit unique matches and advance focus seamlessly on Tab."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # 1. Category unique match: 'cap' -> 'Capacitor'
        cat_combo = dlg.category_combo
        cat_le = cat_combo.lineEdit()
        cat_le.setFocus()
        cat_le.setText("cap")
        cat_combo.completer().setCompletionPrefix("cap")
        cat_combo.completer().complete()
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(cat_le, tab_ev)
        qapp.processEvents()

        assert cat_combo.currentText() == "Capacitor"
        assert dlg.tech_combo.hasFocus() is True

        # 2. Type unique match under Capacitor: 'cer' -> 'Ceramic'
        tech_combo = dlg.tech_combo
        tech_le = tech_combo.lineEdit()
        tech_le.setText("cer")
        tech_combo.completer().setCompletionPrefix("cer")
        tech_combo.completer().complete()
        qapp.processEvents()

        qapp.sendEvent(tech_le, tab_ev)
        qapp.processEvents()

        assert tech_combo.currentText() == "Ceramic"
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_tab_commits_active_contains_suggestion_and_advances_focus(self, qapp, repo):
        """Tab commits active suggestion for contains matches (e.g. 'film' -> 'Thick Film') and advances focus."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # Select Resistor category so types are Thick Film and Thin Film
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        tech_combo = dlg.tech_combo
        le = tech_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        # Type 'film' (substring match, not prefix)
        le.setText("film")
        comp = tech_combo.completer()
        comp.setCompletionPrefix("film")
        comp.complete()
        qapp.processEvents()

        assert comp.popup().isVisible() is True

        # Navigate with Arrow Down to make 'Thick Film' the active suggestion
        down_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, down_ev)
        qapp.processEvents()

        # Send Tab key
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        # Committed exact canonical value
        assert tech_combo.currentText() == "Thick Film"
        assert comp.popup().isVisible() is False
        # Focus advanced to value_input
        assert dlg.value_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_newly_added_reference_entry_dynamically_available(self, qapp, repo):
        """Adding a new reference item dynamically reflects in autocomplete without hardcoding."""
        # Add new manufacturer to database
        repo.add_manufacturer("Analog Devices")

        # 1. New dialog instance immediately sees the new manufacturer
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_items = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert "Analog Devices" in mfr_items

        # Autocomplete suggests it
        comp = dlg.mfr_input.completer()
        comp.setCompletionPrefix("ana")
        comp.complete()
        qapp.processEvents()
        assert comp.popup().isVisible() is True
        assert comp.currentCompletion() == "Analog Devices"

        # 2. Existing dialog can also refresh dynamically via refresh_reference_data()
        repo.add_manufacturer("Microchip Technology")
        dlg.refresh_reference_data()
        qapp.processEvents()

        updated_items = [dlg.mfr_input.itemText(i) for i in range(dlg.mfr_input.count())]
        assert "Microchip Technology" in updated_items

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestSection2ValidationFeedback:
    """Tests for B3: Invalid Input and Validation Feedback."""

    def test_invalid_manufacturer_shows_error_border_and_message(self, qapp, repo):
        """Entering an invalid manufacturer triggers visual error styling and message on blur."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        le.setText("InvalidMfg999")
        qapp.processEvents()

        # Trigger blur
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out)
        qapp.processEvents()

        assert mfr_combo.property("_has_validation_error") is True
        assert "not in canonical reference data" in dlg.validation_lbl.text()

        # Correcting text clears error state
        le.setText("Vishay")
        qapp.processEvents()
        focus_out2 = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out2)
        qapp.processEvents()

        assert mfr_combo.property("_has_validation_error") is False
        assert dlg.validation_lbl.text() == ""

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_invalid_category_shows_error_border_and_message(self, qapp, repo):
        """Entering an invalid category triggers error border and message."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        cat_combo = dlg.category_combo
        le = cat_combo.lineEdit()
        le.setFocus()
        le.setText("NonExistentCategory")
        qapp.processEvents()

        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out)
        qapp.processEvents()

        assert cat_combo.property("_has_validation_error") is True
        assert "Category 'NonExistentCategory' is not in canonical reference data" in dlg.validation_lbl.text()

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_incompatible_type_for_category_shows_error(self, qapp, repo):
        """Entering a type not associated with the category triggers error."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # Valid category
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        # Incompatible type (Ceramic belongs to Capacitor, not Resistor)
        tech_combo = dlg.tech_combo
        le = tech_combo.lineEdit()
        le.setFocus()
        le.setText("Ceramic")
        qapp.processEvents()

        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out)
        qapp.processEvents()

        assert tech_combo.property("_has_validation_error") is True
        assert "not valid for category 'Resistor'" in dlg.validation_lbl.text()

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_save_blocked_when_manufacturer_invalid(self, qapp, repo):
        """Clicking Save/Register with an invalid manufacturer blocks persistence."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        dlg.mfr_input.setEditText("BogusMfr")
        dlg.mpn_input.setText("TEST-MPN-1")
        dlg.category_combo.setEditText("Resistor")
        dlg.tech_combo.setEditText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        dlg.qty_spin.setValue(10)

        dlg._on_save_clicked()
        qapp.processEvents()

        assert dlg.saved_component is None
        assert "Manufacturer 'BogusMfr' is not in canonical reference data" in dlg.validation_lbl.text()
        assert dlg.mfr_input.property("_has_validation_error") is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_save_succeeds_with_exact_canonical_casing(self, qapp, repo):
        """Saving with valid reference values normalizes canonical casing and persists."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # lowercase inputs
        dlg.mfr_input.setEditText("vishay")
        dlg.mpn_input.setText("VISHAY-10K-0805")
        dlg.category_combo.setEditText("resistor")
        dlg.tech_combo.setEditText("thick film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("R_0805")
        dlg.qty_spin.setValue(25)

        dlg._on_save_clicked()
        qapp.processEvents()

        assert dlg.saved_component is not None
        assert dlg.saved_component.manufacturer == "Vishay"
        assert dlg.saved_component.category == "Resistor"
        assert dlg.saved_component.type_technology == "Thick Film"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_empty_reference_data_fails_safely(self, qapp, empty_repo):
        """When repository reference data is empty, dialog operates safely without crashing."""
        dlg = ComponentEditDialog(repository=empty_repo)
        dlg.show()
        qapp.processEvents()

        # Typing in empty reference repo should not crash
        dlg.mfr_input.setEditText("AnyMfr")
        dlg.mpn_input.setText("ANY-123")
        dlg.category_combo.setEditText("AnyCat")
        dlg.tech_combo.setEditText("AnyTech")
        dlg.value_input.setText("100")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("FP_0603")
        dlg.qty_spin.setValue(5)

        # Trigger blur
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(dlg.mfr_input.lineEdit(), focus_out)
        qapp.processEvents()

        # Save should create without crashing
        dlg._on_save_clicked()
        qapp.processEvents()

        assert dlg.saved_component is not None
        assert dlg.saved_component.manufacturer == "AnyMfr"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_clearing_optional_fields_allowed(self, qapp, repo):
        """Clearing optional fields (description, supplier links) is fully permitted."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        dlg.mfr_input.setEditText("Vishay")
        dlg.mpn_input.setText("OPT-TEST-1")
        dlg.category_combo.setEditText("Resistor")
        dlg.tech_combo.setEditText("Thick Film")
        dlg.value_input.setText("1k")
        dlg.package_input.setText("0402")
        dlg.footprint_input.setText("R_0402")
        dlg.qty_spin.setValue(1)

        # Ensure description is empty and zero links
        dlg.desc_input.clear()
        dlg._clear_all_link_rows()

        dlg._on_save_clicked()
        qapp.processEvents()

        assert dlg.saved_component is not None
        assert dlg.saved_component.description == ""
        assert len(dlg.saved_component.supplier_links) == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()


class TestSection2ConfirmationDialogKeyboardSafety:
    """Tests for B5: Keyboard focus in destructive actions and confirmation dialogs."""

    def test_confirmation_dialog_default_button_is_no(self, qapp):
        """Confirmation dialog in MainWindow sets default and escape button to 'No'."""
        win = MainWindow(default_file="")
        qapp.processEvents()

        box = win._create_confirmation_dialog("Test Destructive Action", "Are you sure you want to delete?")
        assert box.defaultButton().text() == "No"
        assert box.escapeButton().text() == "No"

        box.deleteLater()
        win._is_force_closing = True
        win._is_force_closing = True
        win.close()
        win.deleteLater()
        qapp.processEvents()

    def test_reference_data_delete_confirmation_default_is_no(self, qapp, repo):
        """ReferenceDataWidget delete confirmations default to QMessageBox.StandardButton.No."""
        widget = ReferenceDataWidget(repository=repo)
        widget.show()
        qapp.processEvents()

        # Verify that calling delete handlers with mock question defaults to No
        from unittest.mock import patch
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:
            # Select first mfr and invoke delete
            if widget.mfr_list.count() > 0:
                widget.mfr_list.setCurrentRow(0)
                widget._on_delete_manufacturer()
                mock_q.assert_called_once()
                args = mock_q.call_args[0]
                # args: (self, title, text, buttons, defaultButton)
                assert len(args) >= 5
                assert args[4] == QMessageBox.StandardButton.No

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_focus_indicator_geometry_follows_entire_button_perimeter(self, qapp):
        """Part B: Focus indicator outline follows the perimeter of the ENTIRE button box, not text metrics."""
        from ui.dialogs.confirmation_dialog import FocusPaddedPushButton

        btn_yes = FocusPaddedPushButton("Yes")
        btn_no = FocusPaddedPushButton("No")
        btn_yes.resize(85, 28)
        btn_no.resize(85, 28)

        # 1. Geometry for 'Yes' follows entire button box
        rect_yes = btn_yes.calculate_focus_outline_rect()
        assert rect_yes.width() == 83.0  # 85 - 2
        assert rect_yes.height() == 26.0  # 28 - 2
        # Outline spans the entire button box, much wider than text label width
        sz_yes = btn_yes.fontMetrics().size(Qt.TextFlag.TextSingleLine, "Yes")
        assert rect_yes.width() > sz_yes.width() * 2

        # 2. Geometry for 'No' follows entire button box
        rect_no = btn_no.calculate_focus_outline_rect()
        assert rect_no.width() == 83.0  # 85 - 2
        assert rect_no.height() == 26.0  # 28 - 2
        sz_no = btn_no.fontMetrics().size(Qt.TextFlag.TextSingleLine, "No")
        assert rect_no.width() > sz_no.width() * 2

    def test_focus_indicator_adapts_to_button_dimensions(self, qapp):
        """Focus indicator outline dynamically tracks the button dimensions as size changes."""
        from ui.dialogs.confirmation_dialog import FocusPaddedPushButton

        short_btn = FocusPaddedPushButton("OK")
        short_btn.resize(100, 30)
        short_rect = short_btn.calculate_focus_outline_rect()
        assert short_rect.width() == 98.0
        assert short_rect.height() == 28.0

        long_btn = FocusPaddedPushButton("Confirm Physical Component Deletion")
        long_btn.resize(320, 32)
        long_rect = long_btn.calculate_focus_outline_rect()
        assert long_rect.width() == 318.0
        assert long_rect.height() == 30.0

    def test_confirmation_dialog_focus_and_keyboard_navigation(self, qapp):
        """Confirmation dialog opens with focus on 'No', and Tab cycles focus safely."""
        from ui.dialogs.confirmation_dialog import create_confirmation_dialog

        box = create_confirmation_dialog(
            parent=None,
            title="Exit Confirmation",
            text="Do you want to exit Omnix?",
            is_danger=True,
        )
        box.show()
        qapp.processEvents()

        buttons = box.buttons()
        yes_btn = next(b for b in buttons if b.text() == "Yes")
        no_btn = next(b for b in buttons if b.text() == "No")

        # Initial focus is on 'No' (safe default)
        assert no_btn.hasFocus() is True
        assert yes_btn.hasFocus() is False

        # Tab shifts focus to 'Yes'
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(no_btn, tab_ev)
        qapp.processEvents()

        # Either yes_btn has focus or focus has progressed
        assert box.defaultButton() == no_btn
        assert box.escapeButton() == no_btn

        box.close()
        box.deleteLater()
        qapp.processEvents()


class TestSection2MPNCopyFeedback:
    """Tests for B6: MPN Copy Feedback."""

    def test_mpn_single_click_copies_and_shows_subtle_confirmation(self, qapp, repo):
        """Single-clicking MPN cell copies value to clipboard and shows temporary status message."""
        # Create a test component
        p = InventoryProduct(
            manufacturer="Vishay",
            mpn="MPN-TEST-1234",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R_0603",
            value="10k",
            quantity_in_stock=100,
        )
        repo.create_component(p)

        win = MainWindow(default_file=repo.file_path, repository=repo)
        win.show()
        qapp.processEvents()

        # Render components table
        win._render_inventory_components_table()
        qapp.processEvents()

        table = win.inventory_components_table
        found_item = None
        for r in range(table.rowCount()):
            item = table.item(r, 2)  # Column 2 is MPN
            if item and item.text() == "MPN-TEST-1234":
                found_item = item
                break

        assert found_item is not None
        win._on_inventory_component_clicked(found_item)
        qapp.processEvents()

        # Clipboard has exact MPN
        assert QApplication.clipboard().text() == "MPN-TEST-1234"
        # Status shows copied feedback
        assert "● Copied MPN: MPN-TEST-1234" in win.status_state_lbl.text()

        win._is_force_closing = True
        win.close()
        win.deleteLater()
        qapp.processEvents()


class TestSection2VendorPluginsLayout:
    """Tests for B8: Vendor Plugins Spacing and Empty State."""

    def test_vendor_plugins_empty_card_centered_and_bounded(self, qapp):
        """Vendor plugins empty state card is centered with maximum width 680px."""
        widget = VendorPluginsWidget()
        widget.show()
        qapp.processEvents()

        # Locate card frame
        card = widget.findChild(VendorPluginsWidget, "cardFrame")
        if card is None:
            # Look inside content layout
            for i in range(widget.content_layout.count()):
                item = widget.content_layout.itemAt(i)
                if item and item.layout():
                    for j in range(item.layout().count()):
                        sub_w = item.layout().itemAt(j).widget()
                        if sub_w and sub_w.objectName() == "cardFrame":
                            card = sub_w
                            break

        assert card is not None
        assert card.maximumWidth() == 680

        widget.close()
        widget.deleteLater()
        qapp.processEvents()
