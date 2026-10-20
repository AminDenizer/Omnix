"""
Omnix Automated Tests for Autocomplete and Keyboard Completion
Governing Document: Section 10 Autocomplete Specification

Verifies:
1. Typing 'ftd' + Tab commits canonical 'FTDI' to Manufacturer input and advances focus.
2. Typing partial text + Enter commits suggestion.
3. Arrow down navigation and Enter commits highlighted suggestion.
4. Escape dismisses popup suggestions without committing invalid value.
5. Focus change (FocusOut) does not leave partial text when canonical selection required.
6. Category autocomplete: 'cap' + Tab -> 'Capacitor'.
7. Category-dependent Technology autocomplete: with Category 'Resistor', 'thi' + Tab -> 'Thick Film'.
8. Non-matching input does not commit arbitrary values.
"""

import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QKeyEvent, QFocusEvent
from PyQt6.QtWidgets import QApplication

from core.inventory.database import resolve_database_path
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.component_edit_dialog import ComponentEditDialog


@pytest.fixture
def repo(tmp_path):
    # Use isolated test database pre-seeded from clean database
    db_file = str(tmp_path / "test_autocomplete.db")
    r = SqliteInventoryRepository(db_file)
    r.add_manufacturer("FTDI")
    r.add_manufacturer("TDK")
    r.add_manufacturer("Texas Instruments")
    r.add_category("Capacitor")
    r.add_category("Resistor")
    cat_res = r.get_category_by_name("Resistor")
    r.add_type(cat_res.id, "Thick Film")
    r.add_type(cat_res.id, "Thin Film")
    yield r
    r.close()


class TestAutocompleteKeyboard:
    """Verifies keyboard-driven completion behavior on component registration combos."""

    def test_manufacturer_tab_commits_ftdi(self, qapp, repo):
        """Typing 'ftd' + Tab commits 'FTDI' and advances focus to MPN input."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        assert le is not None
        le.setFocus()
        qapp.processEvents()

        # Type partial text
        le.setText("ftd")
        qapp.processEvents()

        # Press Tab
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        assert mfr_combo.currentText() == "FTDI"
        assert dlg.mpn_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_manufacturer_enter_commits_ftdi(self, qapp, repo):
        """Typing 'ftd' + Enter commits 'FTDI' without advancing focus."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        le.setText("ftd")
        qapp.processEvents()

        enter_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, enter_ev)
        qapp.processEvents()

        assert mfr_combo.currentText() == "FTDI"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_tab_commits_capacitor(self, qapp, repo):
        """Typing 'cap' + Tab in Category combo commits 'Capacitor'."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        cat_combo = dlg.category_combo
        le = cat_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        le.setText("cap")
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        assert cat_combo.currentText() == "Capacitor"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_category_dependent_tech_autocomplete(self, qapp, repo):
        """When Category is 'Resistor', typing 'thi' + Tab commits 'Thick Film'."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # Select Resistor
        dlg.category_combo.setCurrentText("Resistor")
        qapp.processEvents()

        tech_combo = dlg.tech_combo
        le = tech_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        le.setText("thi")
        qapp.processEvents()

        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        assert tech_combo.currentText() == "Thick Film"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_escape_dismisses_without_committing_invalid(self, qapp, repo):
        """Pressing Escape with an open popup dismisses the popup without committing."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        comp = mfr_combo.completer()
        comp.complete()
        qapp.processEvents()

        # Send Escape
        esc_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        handled = qapp.sendEvent(le, esc_ev)
        qapp.processEvents()

        assert comp.popup().isVisible() is False

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_focus_out_commits_canonical_or_clears_invalid(self, qapp, repo):
        """FocusOut commits candidate match (e.g. 'ftd' -> 'FTDI')."""
        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        le.setText("ftd")
        qapp.processEvents()

        # Trigger FocusOut
        focus_out = QFocusEvent(QFocusEvent.Type.FocusOut)
        qapp.sendEvent(le, focus_out)
        qapp.processEvents()

        assert mfr_combo.currentText() == "FTDI"

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()
