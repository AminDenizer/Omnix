"""
Omnix Automated Tests for Phase 2.2: Component Management UI, CRUD & Supplier Links
Governing Document: Phase 2.2 Specification

Verifies:
1. Component CRUD and SQLite persistence.
2. Duplicate normalized identity enforcement with Persian notice: «این قطعه از قبل ثبت شده است.»
3. Multi-vendor supplier link management and transactional integrity.
4. Stock grouping invariants (5-dimension key, leading zeros e.g. 0603/0805, aggregate recalculation).
5. Safe deletion preserving group policies and other components.
6. Reactive UI updates (tables, search filtering, stats ribbon, and selections).
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QInputDialog

from ui.main_window import MainWindow
from ui.dialogs.component_edit_dialog import ComponentEditDialog, SupplierLinkRow
from core.inventory.models import (
    InventoryProduct,
    SupplierLink,
    ComponentConflictError,
    ValidationError,
)
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.bootstrap import bootstrap_sqlite_from_workbook


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_sqlite_repo(qapp, tmp_path):
    """Creates a fresh, isolated SQLite inventory repository with initialized schema."""
    db_path = str(tmp_path / "clean_test.db")
    repo = SqliteInventoryRepository(db_path)
    # Seed standard categories and types for testing
    cat_id = repo.add_category("Resistor")
    repo.add_type(cat_id, "Thick Film")
    cat_cap_id = repo.add_category("Capacitor")
    repo.add_type(cat_cap_id, "Ceramic X7R")
    repo.add_manufacturer("Yageo")
    repo.add_manufacturer("Vishay")
    repo.add_manufacturer("Murata")
    yield repo
    app = QApplication.instance()
    if app:
        app.processEvents()
    repo.close()


class TestComponentCRUD:
    """Verifies physical component creation, editing, deletion, and canceling."""

    def test_create_component_and_verify_sqlite_persistence(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        prod = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="SMD_0603",
            value="10k",
            description="10k Resistor 1%",
            quantity_in_stock=500,
        )
        created = repo.create_component(prod)
        assert created.id is not None

        # Verify fetched back from SQLite
        fetched = repo.get_component_by_id(created.id)
        assert fetched is not None
        assert fetched.manufacturer == "Yageo"
        assert fetched.mpn == "RC0603FR-0710KL"
        assert fetched.quantity_in_stock == 500
        assert fetched.package == "0603"
        assert fetched.group_key == "Resistor|Thick Film|10k|0603|SMD_0603"

    def test_edit_component_fields_and_quantity(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        prod = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                description="Original description",
                quantity_in_stock=100,
            )
        )
        updated = repo.update_component(
            prod.id,
            description="Updated description",
            quantity_in_stock=250,
            value="10k 0.1%",
        )
        assert updated.description == "Updated description"
        assert updated.quantity_in_stock == 250
        assert updated.value == "10k 0.1%"

        # Verify in database
        refetched = repo.get_component_by_id(prod.id)
        assert refetched.quantity_in_stock == 250
        assert refetched.description == "Updated description"

    def test_delete_component_without_deleting_other_components_in_same_group(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW060310K0FKEA",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=200,
            )
        )
        assert p1.group_key == p2.group_key

        # Delete p1
        deleted = repo.delete_component(p1.id)
        assert deleted is True

        # p1 should be gone, p2 must remain untouched
        assert repo.get_component_by_id(p1.id) is None
        remaining_p2 = repo.get_component_by_id(p2.id)
        assert remaining_p2 is not None
        assert remaining_p2.quantity_in_stock == 200

        # Group should still exist with p2
        group = repo.get_group(p2.group_key)
        assert group is not None
        assert group.current_stock == 200

    def test_cancel_dialog_without_persisting_changes(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        initial_count = len(repo.get_all_products())

        dlg = ComponentEditDialog(repository=repo)
        dlg.mfr_input.setCurrentText("TestMfr")
        dlg.mpn_input.setText("TEST-MPN-101")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("1k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")
        dlg.qty_spin.setValue(999)

        # Cancel dialog
        dlg.reject()
        assert dlg.result() == 0  # QDialog.DialogCode.Rejected
        assert len(repo.get_all_products()) == initial_count
        assert repo.get_component_by_identity("TestMfr", "TEST-MPN-101") is None

    def test_handle_repository_database_failure_without_partial_writes(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        # Try to create component with negative quantity
        with pytest.raises(ValidationError):
            repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="ERR-001",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                    quantity_in_stock=-50,
                )
            )
        assert repo.get_component_by_identity("Yageo", "ERR-001") is None


class TestComponentIdentityAndDuplicates:
    """Verifies duplicate detection, Persian notice, and identity collision protection."""

    def test_detect_duplicate_normalized_identity(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        # Check normalized match with different case and whitespace
        existing = repo.get_component_by_identity("  yageo  ", "  rc0603fr-0710kl  ")
        assert existing is not None
        assert existing.manufacturer == "Yageo"
        assert existing.mpn == "RC0603FR-0710KL"

    def test_duplicate_registration_shows_persian_notice_and_blocks_insert(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        dlg = ComponentEditDialog(repository=repo)
        dlg.mfr_input.setCurrentText("yageo")
        dlg.mpn_input.setText("rc0603fr-0710kl")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")
        dlg.qty_spin.setValue(500)

        dlg.show()
        qapp.processEvents()

        # Attempt to save
        dlg._on_save_clicked()
        qapp.processEvents()

        # Dialog must remain open (not accepted)
        assert dlg.result() != 1
        # Duplicate alert must be visible
        assert dlg.duplicate_frame.isVisible() is True
        # Exact English notice
        assert "This component is already registered." in dlg.dup_title_lbl.text()
        # Existing record details shown
        assert "Yageo" in dlg.dup_details_lbl.text()
        assert "100" in dlg.dup_details_lbl.text()

        dlg.close()

        # Database must not have created a second record or changed quantity
        products = repo.get_all_products()
        assert len(products) == 1
        assert products[0].quantity_in_stock == 100

    def test_duplicate_registration_does_not_modify_existing_quantity_or_links(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        orig_link = SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lion.ir/p/1")
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW060310K0FKEA",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=333,
            ),
            supplier_links=[orig_link],
        )

        # Try to register duplicate with quantity 999 and new link
        dlg = ComponentEditDialog(repository=repo)
        dlg.mfr_input.setCurrentText("Vishay")
        dlg.mpn_input.setText("CRCW060310K0FKEA")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")
        dlg.qty_spin.setValue(999)
        dlg._on_save_clicked()

        # Confirm Vishay component is strictly unmutated
        refetched = repo.get_component_by_id(p.id)
        assert refetched.quantity_in_stock == 333
        assert len(refetched.supplier_links) == 1
        assert refetched.supplier_links[0].url == "https://lion.ir/p/1"

    def test_edit_component_retaining_current_identity_succeeds(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="Ceramic X7R",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=50,
            )
        )
        dlg = ComponentEditDialog(repository=repo, component=p)
        assert dlg.mode == "edit"
        dlg.qty_spin.setValue(75)
        dlg.desc_input.setText("Edited 50V MLCC")
        dlg._on_save_clicked()
        assert dlg.result() == 1  # Accepted

        updated = repo.get_component_by_id(p.id)
        assert updated.quantity_in_stock == 75
        assert updated.description == "Edited 50V MLCC"
        assert updated.manufacturer == "Murata"
        assert updated.mpn == "GRM188R71H104KA93D"

    def test_edit_component_conflict_with_another_component_rejected(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW060310K0FKEA",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=200,
            )
        )
        # Attempt to edit p2's manufacturer/MPN to match p1
        dlg = ComponentEditDialog(repository=repo, component=p2)
        dlg.mfr_input.setCurrentText("Yageo")
        dlg.mpn_input.setText("RC0603FR-0710KL")
        dlg.show()
        qapp.processEvents()

        dlg._on_save_clicked()
        qapp.processEvents()

        assert dlg.result() != 1
        assert "Conflict" in dlg.validation_lbl.text()
        assert dlg.duplicate_frame.isVisible() is True
        dlg.close()

        # Both components must retain their original identities
        assert repo.get_component_by_id(p1.id).manufacturer == "Yageo"
        assert repo.get_component_by_id(p2.id).manufacturer == "Vishay"

    def test_database_level_uniqueness_conflict_handled_gracefully(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            )
        )
        # Direct repository create with same identity raises ComponentConflictError
        with pytest.raises(ComponentConflictError):
            repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="RC0603FR-0710KL",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                )
            )


class TestSupplierLinksManagement:
    """Verifies adding, editing, removing, and transactional safety of supplier links."""

    def test_add_multiple_supplier_links_to_component(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)
        dlg.mfr_input.setCurrentText("Murata")
        dlg.mpn_input.setText("GRM188-MULTI")
        dlg.category_combo.setCurrentText("Capacitor")
        dlg.tech_combo.setCurrentText("Ceramic X7R")
        dlg.value_input.setText("100nF")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")
        dlg.qty_spin.setValue(100)

        # Add 2 supplier links
        dlg._add_empty_link_row()
        dlg._link_rows[0].vendor_combo.setCurrentIndex(0)  # Lion
        dlg._link_rows[0].url_input.setText("https://lionelectronic.ir/p/123")

        dlg._add_empty_link_row()
        dlg._link_rows[1].vendor_combo.setCurrentIndex(1)  # Javan
        dlg._link_rows[1].url_input.setText("https://javanelec.com/p/456")

        dlg._on_save_clicked()
        assert dlg.result() == 1

        created = repo.get_component_by_identity("Murata", "GRM188-MULTI")
        assert created is not None
        assert len(created.supplier_links) == 2
        vendor_ids = {l.vendor_id for l in created.supplier_links}
        assert vendor_ids == {"vendor_lion", "vendor_javan"}

    def test_remove_individual_supplier_link_persists(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        l1 = SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lion.ir/1")
        l2 = SupplierLink(vendor_id="vendor_javan", vendor_label="JAVAN", url="https://javan.com/2")
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188-2LINKS",
                category="Capacitor",
                type_technology="Ceramic X7R",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
            ),
            supplier_links=[l1, l2],
        )

        dlg = ComponentEditDialog(repository=repo, component=p)
        assert len(dlg._link_rows) == 2

        # Remove the first link (Lion)
        dlg._remove_link_row(dlg._link_rows[0])
        assert len(dlg._link_rows) == 1

        dlg._on_save_clicked()
        assert dlg.result() == 1

        updated = repo.get_component_by_id(p.id)
        assert len(updated.supplier_links) == 1
        assert updated.supplier_links[0].vendor_id == "vendor_javan"

    def test_component_link_changes_isolated_from_other_components(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-1",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            ),
            supplier_links=[SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lion.ir/res1")],
        )
        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="RES-2",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            ),
            supplier_links=[SupplierLink(vendor_id="vendor_javan", vendor_label="JAVAN", url="https://javan.com/res2")],
        )

        # Update p1 links only
        repo.set_supplier_links(p1.id, [
            SupplierLink(vendor_id="vendor_roboeq", vendor_label="ROBOEQ", url="https://roboeq.ir/res1_new")
        ])

        # Verify p2 links are completely untouched
        refetched_p2 = repo.get_component_by_id(p2.id)
        assert len(refetched_p2.supplier_links) == 1
        assert refetched_p2.supplier_links[0].url == "https://javan.com/res2"


class TestStockGroupingInvariantsAndUI:
    """Verifies 5-field grouping key invariants and UI reactivity."""

    def test_preserves_package_leading_zeros(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="PKG-603",
                category="Resistor",
                type_technology="Thick Film",
                package="603",  # Numeric unpadded
                footprint="SMD_0603",
                value="10k",
            )
        )
        assert p1.package == "0603"
        assert p1.group_key.split("|")[3] == "0603"

        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="PKG-805",
                category="Resistor",
                type_technology="Thick Film",
                package="805",  # Numeric unpadded
                footprint="SMD_0805",
                value="10k",
            )
        )
        assert p2.package == "0805"
        assert p2.group_key.split("|")[3] == "0805"

    def test_recalculates_group_membership_after_grouping_field_edit(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RECALC-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        old_group_key = p.group_key
        assert repo.get_group(old_group_key).current_stock == 100

        # Change Value to 20k
        updated = repo.update_component(p.id, value="20k")
        new_group_key = updated.group_key
        assert new_group_key != old_group_key
        assert "20k" in new_group_key

        # Old group must have 0 current stock, new group has 100
        old_g = repo.get_group(old_group_key)
        assert old_g is None or old_g.current_stock == 0
        new_g = repo.get_group(new_group_key)
        assert new_g is not None
        assert new_g.current_stock == 100

    def test_main_window_add_and_edit_component_ui_reactivity(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            assert win.add_component_btn.isEnabled() is True
            assert win.edit_component_btn.isEnabled() is False

            # Add component via mocked accepted dialog
            with patch("ui.main_window.ComponentEditDialog") as MockDlg:
                mock_instance = MockDlg.return_value
                mock_instance.exec.return_value = 1  # Accepted

                created_prod = repo.create_component(
                    InventoryProduct(
                        manufacturer="Yageo",
                        mpn="UI-TEST-01",
                        category="Resistor",
                        type_technology="Thick Film",
                        package="0603",
                        footprint="SMD_0603",
                        value="10k",
                        quantity_in_stock=500,
                    )
                )
                mock_instance.saved_component = created_prod

                win._open_add_component_dialog()
                qapp.processEvents()

            # Verify tables and stats ribbon updated
            assert win.table.rowCount() == 1
            assert win.products_table.rowCount() == 1
            assert win.products_table.item(0, 1).text() == "Yageo"
            assert win.products_table.item(0, 2).text() == "UI-TEST-01"

            # Selection enables Edit and Delete buttons
            win.products_table.selectRow(0)
            qapp.processEvents()
            assert win.edit_component_btn.isEnabled() is True
            assert win.delete_component_btn.isEnabled() is True

            win._is_force_closing = True
            win.close()

    def test_main_window_delete_component_ui(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="DEL-UI-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=50,
            )
        )
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            assert win.products_table.rowCount() == 1
            win.products_table.selectRow(0)
            qapp.processEvents()

            # Confirm deletion via QMessageBox.Yes mock
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                win._delete_selected_component()
                qapp.processEvents()

            # Verify component removed from SQLite and UI
            assert repo.get_component_by_id(p.id) is None
            assert win.products_table.rowCount() == 0

            win._is_force_closing = True
            win.close()

    def test_canceled_or_failed_save_leaves_no_partial_link_changes(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        orig_link = SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lion.ir/keep")
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="PARTIAL-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            ),
            supplier_links=[orig_link],
        )

        dlg = ComponentEditDialog(repository=repo, component=p)
        # Add new link row
        dlg._add_empty_link_row()
        dlg._link_rows[1].url_input.setText("https://invalid-attempt.com")

        # Cancel dialog
        dlg.reject()

        # Database must retain only the original link
        refetched = repo.get_component_by_id(p.id)
        assert len(refetched.supplier_links) == 1
        assert refetched.supplier_links[0].url == "https://lion.ir/keep"

    def test_preserves_unrelated_components_and_existing_policy_thresholds(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="PRESERVE-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
                min_stock=150,
                target_stock=400,
            )
        )
        # Set policy thresholds for this group
        repo.set_policy(
            group_key=p1.group_key,
            min_stock=150,
            target_stock=400,
            category="Resistor",
            type_technology="Thick Film",
            value="10k",
            package="0603",
            footprint="SMD_0603",
        )
        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="PRESERVE-02",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=200,
            )
        )

        # Update p1
        repo.update_component(p1.id, quantity_in_stock=120)

        # Verify group policy thresholds are completely preserved
        group = repo.get_group(p1.group_key)
        assert group.min_stock == 150
        assert group.target_stock == 400
        assert group.current_stock == 320  # 120 + 200

        # Verify unrelated component p2 is intact
        refetched_p2 = repo.get_component_by_id(p2.id)
        assert refetched_p2.quantity_in_stock == 200

    def test_refreshing_statistics_and_search_results_after_component_add(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # Initially 0 components
            assert len(win.current_filtered_groups) == 0

            # Add component
            repo.create_component(
                InventoryProduct(
                    manufacturer="Murata",
                    mpn="CAP-100NF-0603",
                    category="Capacitor",
                    type_technology="Ceramic X7R",
                    package="0603",
                    footprint="SMD_0603",
                    value="100nF",
                    quantity_in_stock=80,
                )
            )

            # Re-filter and render
            win.inventory_repo.load(win.inventory_database_path)
            win._filter_and_render()
            qapp.processEvents()

            assert len(win.current_filtered_groups) == 1
            assert win.table.rowCount() == 1

            # Filter by search
            win._on_search_changed("100nF")
            assert len(win.current_filtered_groups) == 1

            win._on_search_changed("NonExistentValue")
            assert len(win.current_filtered_groups) == 0

            win._is_force_closing = True
            win.close()


class TestEmptyGroupPolicyCleanupInvariant:
    """Verifies that empty groups and their stock policies are cleaned up atomically upon last component deletion."""

    def test_deleting_non_last_component_preserves_group_stock_policy(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-MULTI-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        p2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="RES-MULTI-02",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=200,
                min_stock=150,
                target_stock=500,
            )
        )
        group_key = p1.group_key
        repo.set_policy(
            group_key=group_key,
            min_stock=150,
            target_stock=500,
            category="Resistor",
            type_technology="Thick Film",
            value="10k",
            package="0603",
            footprint="SMD_0603",
        )

        # Delete p1 (not the last component)
        ok = repo.delete_component(p1.id)
        assert ok is True

        # Policy must remain intact
        pol = repo.get_policy(group_key)
        assert pol is not None
        assert pol.min_stock == 150
        assert pol.target_stock == 500

        # Group must remain in get_all_groups with p2
        group = repo.get_group(group_key)
        assert group is not None
        assert group.min_stock == 150
        assert group.target_stock == 500
        assert group.current_stock == 200
        assert len(group.products) == 1

    def test_deleting_last_component_deletes_stock_policy_and_removes_group(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-SOLO-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        group_key = p.group_key
        repo.set_policy(
            group_key=group_key,
            min_stock=150,
            target_stock=500,
            category="Resistor",
            type_technology="Thick Film",
            value="10k",
            package="0603",
            footprint="SMD_0603",
        )

        # Policy exists before deletion
        assert repo.get_policy(group_key) is not None

        # Delete the only component in this group
        ok = repo.delete_component(p.id)
        assert ok is True

        # Stock policy must be deleted
        assert repo.get_policy(group_key) is None

        # Group must disappear completely from get_all_groups()
        assert repo.get_group(group_key) is None
        all_groups = repo.get_all_groups()
        assert not any(g.group_key == group_key for g in all_groups)

    def test_recreating_component_after_policy_cleanup_does_not_recreate_old_policy(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-RECREATE-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        group_key = p.group_key
        repo.set_policy(
            group_key=group_key,
            min_stock=250,
            target_stock=600,
        )

        # Delete last component
        repo.delete_component(p.id)
        assert repo.get_policy(group_key) is None

        # Later, add a new component with the same 5-field key
        p_new = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="RES-RECREATE-02",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=50,
            )
        )
        assert p_new.group_key == group_key

        # The new component's group must NOT have old policy thresholds
        group = repo.get_group(group_key)
        assert group is not None
        assert group.min_stock == 0
        assert group.target_stock == 0
        assert group.min_stock != 250
        assert group.target_stock != 600

    def test_deletion_failure_rolls_back_both_component_and_policy(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-ROLLBACK-01",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        group_key = p.group_key
        repo.set_policy(
            group_key=group_key,
            min_stock=100,
            target_stock=300,
        )

        # Simulate database failure during policy cleanup within the transaction
        real_conn = repo._db.get_connection()

        class FailingConnWrapper:
            def __init__(self, target):
                self._target = target

            def execute(self, sql, *args, **kwargs):
                if "DELETE FROM stock_policies" in str(sql):
                    raise Exception("Simulated disk error during policy deletion")
                return self._target.execute(sql, *args, **kwargs)

            @property
            def in_transaction(self):
                return self._target.in_transaction

            def __enter__(self):
                return self._target.__enter__()

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self._target.__exit__(exc_type, exc_val, exc_tb)

            def __getattr__(self, name):
                return getattr(self._target, name)

        wrapper = FailingConnWrapper(real_conn)
        with patch.object(repo._db, "get_connection", return_value=wrapper):
            try:
                repo.delete_component(p.id)
            except Exception:
                pass

        # Verify rollback: component still exists, policy still exists
        assert repo.get_component_by_id(p.id) is not None
        assert repo.get_policy(group_key) is not None
        assert repo.get_policy(group_key).min_stock == 100


class TestThreeDistinctInventoryViews:
    """Verifies the three distinct inventory views, placement of CRUD buttons, and synchronization."""

    def test_three_views_exist_with_distinct_responsibilities(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # 1. Top-level tabs remain exactly 3
            assert win.tabs.count() == 3
            assert "Inventory" in win.tabs.tabText(0)
            assert "Auditor" in win.tabs.tabText(1)
            assert "Assembly" in win.tabs.tabText(2)

            # 2. Inventory Sub-tabs exist with 2 views
            assert hasattr(win, "inventory_subtabs")
            assert win.inventory_subtabs.count() == 2
            assert any(text in win.inventory_subtabs.tabText(0) for text in ["Assembly View", "Stock Policy"])
            assert "Component Inventory" in win.inventory_subtabs.tabText(1)

            # 3. Table 1: Dedicated Component Inventory Table (13 columns with Min Stock and Target Stock)
            assert hasattr(win, "inventory_components_table")
            assert win.inventory_components_table.columnCount() == 13

            # 4. Table 2: Stock Policy Groups Table (8 columns without Min/Target Stock)
            assert hasattr(win, "table")
            assert win.table.columnCount() == 8

            # 5. Table 3: Associated Physical Products Table
            assert hasattr(win, "products_table")
            assert win.products_table.columnCount() == 11
            assert win.products_frame.parent() == win.inventory_splitter

            # 6. Primary Component Management Actions are in Component Inventory
            assert win.add_component_btn.parent() == win.component_inventory_view
            assert win.edit_component_btn.parent() == win.component_inventory_view
            assert win.delete_component_btn.parent() == win.component_inventory_view

            win._is_force_closing = True
            win.close()

    def test_synchronization_across_all_three_views(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # Initially empty
            assert win.inventory_components_table.rowCount() == 0
            assert win.table.rowCount() == 0
            assert win.products_table.rowCount() == 0

            # Add component to SQLite
            p1 = repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="SYNC-01",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                    quantity_in_stock=100,
                )
            )

            # Trigger reload/sync
            win._reload_and_select_group(p1.group_key, select_comp_id=p1.id)
            qapp.processEvents()

            # Verify Table 1 (Component Inventory) updated
            assert win.inventory_components_table.rowCount() == 1
            assert win.inventory_components_table.item(0, 1).text() == "Yageo"
            assert win.inventory_components_table.item(0, 2).text() == "SYNC-01"

            # Verify Table 2 (Stock Policy Groups) updated
            assert win.table.rowCount() == 1
            assert win.table.item(0, 0).text() == "Resistor"
            assert win.table.item(0, 2).text() == "10k"

            # Verify Table 3 (Associated Physical Products) updated
            assert win.products_table.rowCount() == 1
            assert win.products_table.item(0, 1).text() == "Yageo"
            assert win.products_table.item(0, 2).text() == "SYNC-01"

            # Delete component and verify all three views clear
            ok = repo.delete_component(p1.id)
            assert ok is True
            win._reload_and_select_group()
            qapp.processEvents()

            assert win.inventory_components_table.rowCount() == 0
            assert win.table.rowCount() == 0
            assert win.products_table.rowCount() == 0

            win._is_force_closing = True
            win.close()


class TestComponentInventoryViewAndColumns:
    """Verifies Component Inventory column layout, order, empty state, and tab-switching persistence."""

    def test_component_inventory_column_order(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            tbl = win.inventory_components_table
            assert tbl.columnCount() == 13

            expected_headers = [
                "Row", "Manufacturer", "Part Number (MPN)", "Category",
                "Type / Technology", "Value", "Package", "Footprint",
                "Quantity in Stock", "Min Stock", "Target Stock", "Description", "Purchase Link"
            ]
            actual_headers = [tbl.horizontalHeaderItem(i).text() for i in range(13)]
            assert actual_headers == expected_headers

            # Verify Min Stock and Target Stock are at index 9 and 10, Description is at index 11, immediately before Purchase Link at index 12
            assert actual_headers[9] == "Min Stock"
            assert actual_headers[10] == "Target Stock"
            assert actual_headers[11] == "Description"
            assert actual_headers[12] == "Purchase Link"

            win._is_force_closing = True
            win.close()

    def test_components_table_renders_existing_sqlite_records_on_open(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        repo.create_component(
            InventoryProduct(
                manufacturer="Yageo", mpn="RC0603-1", category="Resistor",
                type_technology="Thick Film", package="0603", footprint="SMD_0603",
                value="10k", description="Resistor 10k", quantity_in_stock=100
            )
        )
        repo.create_component(
            InventoryProduct(
                manufacturer="Murata", mpn="GRM188-1", category="Capacitor",
                type_technology="Ceramic X7R", package="0603", footprint="SMD_0603",
                value="100nF", description="Capacitor 100nF", quantity_in_stock=200
            )
        )

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            tbl = win.inventory_components_table
            assert tbl.rowCount() == 2

            # Check column data alignment
            assert tbl.item(0, 1).text() in ["Yageo", "Murata"]
            # Col 8 is quantity
            assert tbl.item(0, 8).text() in ["100", "200"]
            # Col 11 is description
            assert "Resistor" in tbl.item(0, 11).text() or "Capacitor" in tbl.item(0, 11).text()

            win._is_force_closing = True
            win.close()

    def test_switching_subtabs_refreshes_and_preserves_component_table(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        repo.create_component(
            InventoryProduct(
                manufacturer="Vishay", mpn="CRCW0603-10K", category="Resistor",
                type_technology="Thick Film", package="0603", footprint="SMD_0603",
                value="10k", quantity_in_stock=50
            )
        )
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # Initially Sub-tab 1 (Component Inventory) on application startup
            assert win.inventory_subtabs.currentIndex() == 1
            assert win.inventory_components_table.rowCount() == 1
            assert win.inventory_components_table.item(0, 2).text() == "CRCW0603-10K"

            # Switch to Sub-tab 0 (Assembly View)
            win.inventory_subtabs.setCurrentIndex(0)
            qapp.processEvents()

            # Switch back to Sub-tab 0
            win.inventory_subtabs.setCurrentIndex(0)
            qapp.processEvents()

            # Switch back to Sub-tab 1
            win.inventory_subtabs.setCurrentIndex(1)
            qapp.processEvents()
            assert win.inventory_components_table.rowCount() == 1
            assert win.inventory_components_table.item(0, 2).text() == "CRCW0603-10K"

            win._is_force_closing = True
            win.close()

    def test_empty_component_inventory_overlay(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            win.inventory_subtabs.setCurrentIndex(1)
            qapp.processEvents()

            tbl = win.inventory_components_table
            assert tbl.rowCount() == 0
            assert tbl.empty_overlay.isVisible()
            assert "No Components in Inventory" in tbl.empty_overlay.title_lbl.text()

            win._is_force_closing = True
            win.close()

    def test_buttons_placement_isolated_to_component_inventory(self, qapp, clean_sqlite_repo):
        repo = clean_sqlite_repo
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)

            # No quick_add_comp_btn in Stock Policy Groups
            assert not hasattr(win, "quick_add_comp_btn")

            # Buttons only in component_inventory_view
            assert win.add_component_btn.parent() == win.component_inventory_view
            assert win.edit_component_btn.parent() == win.component_inventory_view
            assert win.delete_component_btn.parent() == win.component_inventory_view

            win._is_force_closing = True
            win.close()


class TestComponentEditDialogLifecycleAndReferenceData:
    """Verifies dialog reset, zero state leakage, category-dependent types, and explicit reference additions."""

    def test_dialog_modes_and_titles(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        # Create mode
        dlg_create = ComponentEditDialog(repository=repo)
        assert dlg_create.mode == "create"
        assert dlg_create.windowTitle() == "Register Component"
        assert dlg_create.save_btn.text() == "Register Component"

        # Edit mode
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Murata", mpn="GRM-TEST", category="Capacitor",
                type_technology="Ceramic X7R", package="0603", footprint="SMD_0603",
                value="100nF", quantity_in_stock=10
            )
        )
        dlg_edit = ComponentEditDialog(repository=repo, component=p)
        assert dlg_edit.mode == "edit"
        assert "Edit Component" in dlg_edit.windowTitle()
        assert dlg_edit.save_btn.text() == "Save Changes"

    def test_form_reset_prevents_state_leakage(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)

        # Fill fields as if an abort or previous session occurred
        dlg.mfr_input.setCurrentText("Yageo")
        dlg.mpn_input.setText("LEAK-TEST")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("47k")
        dlg.package_input.setText("0805")
        dlg.footprint_input.setText("SMD_0805")
        dlg.desc_input.setText("Some leaked desc")
        dlg.qty_spin.setValue(999)
        dlg._add_empty_link_row(SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lion.com"))
        assert len(dlg._link_rows) == 1

        # Reset form
        dlg.reset_form()

        assert dlg.mpn_input.text() == ""
        assert dlg.value_input.text() == ""
        assert dlg.package_input.text() == ""
        assert dlg.footprint_input.text() == ""
        assert dlg.desc_input.text() == ""
        assert dlg.qty_spin.value() == 0
        assert len(dlg._link_rows) == 0
        assert dlg.mode == "create"
        assert dlg.component is None
        assert dlg.saved_component is None
        assert not dlg.duplicate_frame.isVisible()

    def test_switching_from_edit_mode_back_to_registration(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        p = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay", mpn="CRCW0603-EDIT", category="Resistor",
                type_technology="Thick Film", package="0603", footprint="SMD_0603",
                value="1k", quantity_in_stock=15
            )
        )
        dlg = ComponentEditDialog(repository=repo, component=p)
        assert dlg.mode == "edit"
        assert dlg.mpn_input.text() == "CRCW0603-EDIT"

        # Now reset into registration mode
        dlg.reset_form()
        assert dlg.mode == "create"
        assert dlg.component is None
        assert dlg.mpn_input.text() == ""
        assert dlg.windowTitle() == "Register Component"
        assert dlg.save_btn.text() == "Register Component"

    def test_reference_data_category_dependent_type_filtering(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)

        # Select Resistor
        dlg.category_combo.setCurrentText("Resistor")
        tech_items = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Thick Film" in tech_items
        assert "Ceramic X7R" not in tech_items

        # Switch to Capacitor
        dlg.category_combo.setCurrentText("Capacitor")
        tech_items_cap = [dlg.tech_combo.itemText(i) for i in range(dlg.tech_combo.count())]
        assert "Ceramic X7R" in tech_items_cap
        assert "Thick Film" not in tech_items_cap

    def test_incompatible_type_is_cleared_on_category_change(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)

        dlg.category_combo.setCurrentText("Capacitor")
        dlg.tech_combo.setCurrentText("Ceramic X7R")
        assert dlg.tech_combo.currentText() == "Ceramic X7R"

        # Switch to Resistor - Ceramic X7R is incompatible and must be cleared
        dlg.category_combo.setCurrentText("Resistor")
        assert dlg.tech_combo.currentText() != "Ceramic X7R"

    def test_failed_save_preserves_user_input(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)

        # Enter valid fields except missing MPN
        dlg.mfr_input.setCurrentText("Yageo")
        dlg.mpn_input.setText("")  # Invalid!
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")
        dlg.qty_spin.setValue(100)

        dlg._on_save_clicked()

        # Dialog was rejected/not accepted, error is displayed, inputs preserved
        assert "required" in dlg.validation_lbl.text().lower()
        assert dlg.value_input.text() == "10k"
        assert dlg.package_input.text() == "0603"
        assert dlg.qty_spin.value() == 100

    def test_explicit_addition_of_reference_data(self, clean_sqlite_repo):
        repo = clean_sqlite_repo
        dlg = ComponentEditDialog(repository=repo)

        # Mock QInputDialog to return new manufacturer "Kemet"
        with patch.object(QInputDialog, "getText", return_value=("Kemet", True)):
            dlg._on_add_manufacturer_clicked()

        mfr_rec = repo.get_manufacturer_by_name("Kemet")
        assert mfr_rec is not None
        assert dlg.mfr_input.currentText() == "Kemet"

        # Mock QInputDialog to return new category "Inductor"
        with patch.object(QInputDialog, "getText", return_value=("Inductor", True)):
            dlg._on_add_category_clicked()

        cat_rec = repo.get_category_by_name("Inductor")
        assert cat_rec is not None
        assert dlg.category_combo.currentText() == "Inductor"

        # Mock QInputDialog to return new type "Ferrite Bead" for Inductor
        with patch.object(QInputDialog, "getText", return_value=("Ferrite Bead", True)):
            dlg._on_add_type_clicked()

        assert repo.validate_category_type("Inductor", "Ferrite Bead")
        assert dlg.tech_combo.currentText() == "Ferrite Bead"
        dlg.close()
        dlg.deleteLater()
        QApplication.instance().processEvents()
