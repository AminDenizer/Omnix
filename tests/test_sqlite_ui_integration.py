"""
Omnix Automated Tests for Phase 2.1: SQLite Repository Integration & UI Preservation
Governing Document: Phase 2.1 Implementation Specification

Tests:
1. MainWindow initializes with SqliteInventoryRepository as authoritative repository.
2. Tab 1 two-table layout, vertical splitter, search bar, and statistics ribbon function with SQLite.
3. Policy editing persists to SQLite and reactively updates group aggregates and products table.
4. Safe Excel bootstrap imports reference data, components, supplier links, and policies
   without modifying the source workbook.
5. In-memory and temporary database isolation protects user data.
"""

import os
import hashlib
import tempfile
import pytest
import openpyxl
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.dialogs.policy_edit_dialog import PolicyEditDialog
from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.bootstrap import bootstrap_sqlite_from_workbook, ExcelDatabaseMigrator


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_workbook(tmp_path):
    """Creates a temporary valid Excel workbook with Stock Policy and Inventory sheets."""
    wb_path = str(tmp_path / "BootstrapInventory.xlsm")
    wb = openpyxl.Workbook()

    ws_policy = wb.active
    ws_policy.title = "Stock Policy"
    ws_policy.append([
        "Category", "Type/Technology", "Value", "Package", "Footprint",
        "Total Quantity in Stock", "Min Stock", "Target Stock", "Description", "Group Key (System)"
    ])
    ws_policy.append([
        "Resistor", "Thick Film", "10k", "0603", "SMD_0603",
        150, 100, 300, "10k 1% 0603 Resistor", "Resistor|Thick Film|10k|0603|SMD_0603"
    ])
    ws_policy.append([
        "Capacitor", "X7R", "100nF", "0603", "SMD_0603",
        50, 100, 200, "100nF 50V MLCC", "Capacitor|X7R|100nF|0603|SMD_0603"
    ])

    ws_inv = wb.create_sheet(title="Inventory")
    ws_inv.append([
        "Manufacturer", "MPN", "Category", "Type/Technology", "Package",
        "Footprint", "Value", "Description", "Quantity in Stock", "Purchase Link"
    ])
    ws_inv.append([
        "Yageo", "RC0603FR-0710KL", "Resistor", "Thick Film", 603,
        "SMD_0603", "10k", "10k Resistor", 100, "LION=https://lionelectronic.ir/p/101"
    ])
    ws_inv.append([
        "Vishay", "CRCW060310K0FKEA", "Resistor", "Thick Film", "0603",
        "SMD_0603", "10k", "Vishay Resistor", 50, "JAVAN=https://javanelec.com/p/202"
    ])
    ws_inv.append([
        "Murata", "GRM188R71H104KA93D", "Capacitor", "X7R", 603,
        "SMD_0603", "100nF", "100nF Cap", 50, "LION=https://lionelectronic.ir/p/303 || JAVAN=https://javanelec.com/p/404"
    ])

    wb.save(wb_path)
    wb.close()
    return wb_path


@pytest.fixture
def sqlite_repo_with_data(temp_workbook, tmp_path):
    """Creates a temporary SQLite repository populated via bootstrap."""
    db_path = str(tmp_path / "test_inventory.db")
    repo = SqliteInventoryRepository(db_path)
    res = bootstrap_sqlite_from_workbook(temp_workbook, repo)
    assert res.success is True
    # Under Option B, physical components hold the stock thresholds
    prods = repo.get_all_products()
    yageo = next(p for p in prods if p.mpn == "RC0603FR-0710KL")
    repo.update_component_thresholds(yageo.id, min_stock=100, target_stock=300)
    return repo


class TestPhase21SqliteUIIntegration:
    """Tests for Phase 2.1: SQLite desktop integration and UI preservation."""

    def test_main_window_boots_with_sqlite_repository(self, qapp, sqlite_repo_with_data):
        repo = sqlite_repo_with_data
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            assert isinstance(win.inventory_repo, SqliteInventoryRepository)
            assert win.inventory_repo.is_loaded is True

            # Two policy groups: Resistor 10k 0603 and Capacitor 100nF 0603
            groups = win.inventory_repo.get_all_groups()
            assert len(groups) == 2

            # Top table: Stock Policy Groups (7 columns)
            assert win.table.rowCount() == 2
            assert win.table.columnCount() == 7
            assert win.inventory_components_table.columnCount() == 14

            # Headers match Section 5 specification
            expected_headers = [
                "Category", "Type / Technology", "Value", "Package", "Footprint",
                "Total In Stock", "Matched Products"
            ]
            actual_headers = [win.table.horizontalHeaderItem(c).text() for c in range(win.table.columnCount())]
            assert actual_headers == expected_headers

            win._is_force_closing = True
            win.close()

    def test_group_selection_updates_associated_products_table(self, qapp, sqlite_repo_with_data):
        repo = sqlite_repo_with_data
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # Resistor group has 2 products (Yageo, Vishay)
            resistor_idx = None
            for idx, g in enumerate(win.current_filtered_groups):
                if g.category == "Resistor":
                    resistor_idx = idx
                    break

            assert resistor_idx is not None
            win.table.selectRow(resistor_idx)
            qapp.processEvents()

            assert win.products_table.rowCount() == 2
            assert "Yageo" in win.products_table.item(0, 1).text() or "Yageo" in win.products_table.item(1, 1).text()

            # Capacitor group has 1 product (Murata)
            cap_idx = 1 - resistor_idx
            win.table.selectRow(cap_idx)
            qapp.processEvents()

            assert win.products_table.rowCount() == 1
            assert win.products_table.item(0, 1).text() == "Murata"

            win._is_force_closing = True
            win.close()

    def test_search_filtering_with_sqlite_data(self, qapp, sqlite_repo_with_data):
        repo = sqlite_repo_with_data
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            # Search by component value
            win._on_search_changed("100nF")
            assert len(win.current_filtered_groups) == 1
            assert win.current_filtered_groups[0].value == "100nF"
            assert win.table.rowCount() == 1

            # Search by manufacturer (present in child products)
            win._on_search_changed("Yageo")
            assert len(win.current_filtered_groups) == 1
            assert win.current_filtered_groups[0].category == "Resistor"

            # Clear search restores full list
            win._on_search_changed("")
            assert len(win.current_filtered_groups) == 2
            assert win.table.rowCount() == 2

            win._is_force_closing = True
            win.close()

    def test_policy_edit_persists_to_sqlite_and_updates_ui(self, qapp, sqlite_repo_with_data):
        repo = sqlite_repo_with_data
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            win.show()
            qapp.processEvents()

            resistor_group = next(g for g in win.current_filtered_groups if g.category == "Resistor")
            assert resistor_group.min_stock == 100
            assert resistor_group.target_stock == 300

            # Mock ComponentThresholdDialog execution with updated thresholds (120, 350)
            yageo = next(p for p in repo.get_all_products() if p.mpn == "RC0603FR-0710KL")
            with patch("ui.main_window.ComponentThresholdDialog") as MockDialog:
                mock_dlg_instance = MockDialog.return_value
                mock_dlg_instance.exec.return_value = 1  # Accepted
                saved_mock = InventoryProduct(
                    manufacturer="Yageo",
                    mpn="RC0603FR-0710KL",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                    description="10k Resistor",
                    quantity_in_stock=100,
                    purchase_link="LION=https://lionelectronic.ir/p/101",
                    group_key=resistor_group.group_key,
                    raw_package="603",
                    id=yageo.id,
                    min_stock=120,
                    target_stock=350,
                )
                mock_dlg_instance.saved_component = saved_mock

                def apply_mock_save():
                    repo.update_component_thresholds(
                        yageo.id,
                        min_stock=120,
                        target_stock=350,
                    )
                mock_dlg_instance.exec.side_effect = lambda: (apply_mock_save(), 1)[1]

                win._open_component_threshold_dialog(yageo)
                qapp.processEvents()

            # Verify SQLite persisted the new thresholds on the component
            updated_comp = repo.get_component_by_identity("Yageo", "RC0603FR-0710KL")
            assert updated_comp.min_stock == 120
            assert updated_comp.target_stock == 350

            # Verify UI table reflects updated group aggregate values
            updated_group = next(g for g in win.current_filtered_groups if g.category == "Resistor")
            assert updated_group.min_stock == 120
            assert updated_group.target_stock == 350

            win._is_force_closing = True
            win.close()

    def test_policy_edit_dialog_direct_sqlite_save(self, qapp, sqlite_repo_with_data):
        repo = sqlite_repo_with_data
        group = repo.get_all_groups()[0]

        # Verify Option B read-only aggregate behavior when products exist
        read_only_dlg = PolicyEditDialog(
            group=group,
            inventory_path=repo.file_path,
            repository=repo,
        )
        assert read_only_dlg.is_read_only is True
        read_only_dlg.close()

        # Direct editing enabled via read_only=False (or for policy-only groups)
        dlg = PolicyEditDialog(
            group=group,
            inventory_path=repo.file_path,
            repository=repo,
            read_only=False,
        )
        assert dlg.is_read_only is False
        dlg.min_spin.setValue(175)
        dlg.target_spin.setValue(450)

        # Trigger save directly
        dlg._on_save_clicked()
        assert dlg.result() == 1  # Accepted

        # Verify SQLite has updated policy
        saved = repo.get_policy(group.group_key)
        assert saved.min_stock == 175
        assert saved.target_stock == 450


class TestSafeBootstrapMigration:
    """Tests verifying non-destructive Excel to SQLite migration invariants."""

    def test_source_workbook_never_modified_during_bootstrap(self, temp_workbook, tmp_path):
        # Calculate source workbook hash before migration
        with open(temp_workbook, "rb") as f:
            before_hash = hashlib.sha256(f.read()).hexdigest()
        before_mtime = os.path.getmtime(temp_workbook)

        # Execute bootstrap
        db_path = str(tmp_path / "migrated.db")
        repo = SqliteInventoryRepository(db_path)
        res = bootstrap_sqlite_from_workbook(temp_workbook, repo)

        assert res.success is True
        assert res.components_imported == 3
        assert res.policies_imported == 2
        assert res.manufacturers_imported == 3
        assert res.categories_imported == 2
        assert res.types_imported == 2

        # Verify source workbook is strictly untouched
        with open(temp_workbook, "rb") as f:
            after_hash = hashlib.sha256(f.read()).hexdigest()
        after_mtime = os.path.getmtime(temp_workbook)

        assert before_hash == after_hash
        assert before_mtime == after_mtime

    def test_bootstrap_dry_run_does_not_mutate_sqlite(self, temp_workbook, tmp_path):
        db_path = str(tmp_path / "dry_run.db")
        repo = SqliteInventoryRepository(db_path)

        res = bootstrap_sqlite_from_workbook(temp_workbook, repo, dry_run=True)
        assert res.success is True
        assert res.components_imported == 3
        assert res.policies_imported == 2

        # Verify repo remains empty
        assert len(repo.get_all_products()) == 0
        assert len(repo.get_all_groups()) == 0
        assert len(repo.get_all_manufacturers(include_inactive=True)) == 0

    def test_bootstrap_preserves_package_leading_zeros(self, temp_workbook, tmp_path):
        db_path = str(tmp_path / "packages.db")
        repo = SqliteInventoryRepository(db_path)
        res = bootstrap_sqlite_from_workbook(temp_workbook, repo)
        assert res.success is True

        products = repo.get_all_products()
        for p in products:
            assert p.package == "0603", f"Expected package '0603', got '{p.package}'"

    def test_bootstrap_parses_multi_supplier_links(self, temp_workbook, tmp_path):
        db_path = str(tmp_path / "links.db")
        repo = SqliteInventoryRepository(db_path)
        res = bootstrap_sqlite_from_workbook(temp_workbook, repo)
        assert res.success is True

        murata = repo.get_component_by_identity("Murata", "GRM188R71H104KA93D")
        assert murata is not None
        assert len(murata.supplier_links) == 2
        vendor_ids = {link.vendor_id for link in murata.supplier_links}
        assert vendor_ids == {"vendor_lion", "vendor_javan"}
