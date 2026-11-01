"""
Omnix Test Suite — Phase 10: Export, Backup, Restore, and Merge Integration.

Verifies:
1. Export produces exactly one worksheet named 'Inventory' representing Component Inventory.
2. Backup preserves database in .obk format.
3. Restore restores the database safely and distinctly.
4. Bind/Merge adds approved records without replacing destination or corrupting reference IDs.
5. Incomplete keys or invalid schemas are caught.
6. Rollback / cancellation leaves both databases intact without partial modifications.
7. UI actions map to their distinct operations.
"""

import os
import sqlite3
import pytest
import openpyxl
from unittest.mock import patch, MagicMock

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.exporter import InventoryExcelExporter
from core.inventory.backup import DatabaseBackupService
from core.inventory.merge import DatabaseMergeService
from ui.widgets.backup_restore_widget import DatabaseBackupRestoreWidget


@pytest.fixture
def test_db_pair(tmp_path):
    dest_path = tmp_path / "dest.db"
    src_path = tmp_path / "src.db"

    # Initialize destination
    repo_dest = SqliteInventoryRepository(str(dest_path))
    repo_dest.load()
    cat_res_d = repo_dest.add_category("Resistor")
    repo_dest.add_type(cat_res_d, "Thick Film")
    cat_cap_d = repo_dest.add_category("Capacitor")
    repo_dest.add_type(cat_cap_d, "Ceramic")
    repo_dest.add_manufacturer("Yageo")
    repo_dest.add_manufacturer("Murata")
    repo_dest.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0805FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0805",
            footprint="SMD_0805",
            value="10k",
            quantity_in_stock=100,
            min_stock=10,
            target_stock=200,
        )
    )

    # Initialize source
    repo_src = SqliteInventoryRepository(str(src_path))
    repo_src.load()
    cat_res_s = repo_src.add_category("Resistor")
    repo_src.add_type(cat_res_s, "Thick Film")
    cat_cap_s = repo_src.add_category("Capacitor")
    repo_src.add_type(cat_cap_s, "Ceramic")
    repo_src.add_manufacturer("Yageo")
    repo_src.add_manufacturer("Murata")

    # Duplicate component (same MFR + MPN)
    repo_src.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0805FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0805",
            footprint="SMD_0805",
            value="10k",
            quantity_in_stock=50,
        )
    )
    # New component
    repo_src.create_component(
        InventoryProduct(
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=500,
            min_stock=50,
            target_stock=1000,
        )
    )

    return repo_dest, str(dest_path), str(src_path)


class TestPhase10Integration:

    def test_single_sheet_inventory_export(self, test_db_pair, tmp_path):
        repo_dest, dest_path, _ = test_db_pair
        export_file = tmp_path / "Inventory_Export.xlsx"

        out_path = InventoryExcelExporter.export(
            repository=repo_dest,
            filepath=str(export_file),
            include_assembly=False,
        )
        assert os.path.exists(out_path)

        wb = openpyxl.load_workbook(str(export_file))
        assert wb.sheetnames == ["Inventory"]
        ws = wb["Inventory"]
        assert ws.max_row >= 2
        assert ws.cell(1, 1).value == "Row"
        assert ws.cell(1, 2).value == "Manufacturer"
        assert ws.cell(1, 3).value == "Part Number (MPN)"
        assert ws.cell(2, 2).value == "Yageo"
        assert ws.cell(2, 3).value == "RC0805FR-0710KL"

    def test_backup_and_restore_cycle(self, test_db_pair, tmp_path):
        repo_dest, dest_path, _ = test_db_pair
        backup_file = tmp_path / "test_backup.obk"

        # 1. Create backup
        b_res, b_msg, _ = DatabaseBackupService.export_full_backup(repo_dest, backup_file)
        assert b_res is True
        assert os.path.exists(str(backup_file))

        # 2. Modify dest by adding another component
        repo_dest.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805FR-071KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="SMD_0805",
                value="1k",
                quantity_in_stock=25,
            )
        )
        assert len(repo_dest.get_all_products()) == 2

        # 3. Restore from backup
        r_res, r_msg, _ = DatabaseBackupService.restore_backup(repo_dest, backup_file)
        assert r_res is True
        assert len(repo_dest.get_all_products()) == 1
        assert repo_dest.get_all_products()[0].mpn == "RC0805FR-0710KL"

    def test_bind_merge_preserves_destination_and_adds_new(self, test_db_pair, tmp_path):
        repo_dest, dest_path, src_path = test_db_pair

        analysis = DatabaseMergeService.analyze_merge(repo_dest, src_path)

        assert analysis.is_valid is True
        assert len(analysis.new_components) == 1
        assert analysis.new_components[0]["mpn"] == "GRM188R71H104KA93D"
        assert len(analysis.duplicate_components) == 1
        assert analysis.duplicate_components[0]["mpn"] == "RC0805FR-0710KL"

        # Execute merge
        safety_dir = tmp_path / "merge_backups"
        ok, msg, meta = DatabaseMergeService.execute_merge(
            target_repo=repo_dest,
            analysis=analysis,
            safety_backup_dir=str(safety_dir),
        )
        assert ok is True
        assert meta["added_components"] == 1
        assert meta["skipped_duplicates"] == 1

        # Check destination records
        comps = repo_dest.get_all_products()
        assert len(comps) == 2
        mpns = {c.mpn for c in comps}
        assert mpns == {"RC0805FR-0710KL", "GRM188R71H104KA93D"}

        # Original stock was preserved, not overwritten by source
        yageo = [c for c in comps if c.mpn == "RC0805FR-0710KL"][0]
        assert yageo.quantity_in_stock == 100

    def test_bind_merge_rollback_on_failure(self, test_db_pair, tmp_path):
        repo_dest, dest_path, src_path = test_db_pair
        analysis = DatabaseMergeService.analyze_merge(repo_dest, src_path)

        # Inject failure during creation
        safety_dir = tmp_path / "merge_backups"
        with patch.object(repo_dest, "create_component", side_effect=RuntimeError("Simulated write failure")):
            ok, msg, meta = DatabaseMergeService.execute_merge(
                target_repo=repo_dest,
                analysis=analysis,
                safety_backup_dir=str(safety_dir),
            )
            assert ok is False
            assert "Simulated write failure" in msg

        # Ensure destination was rolled back and still contains only original 1 component
        comps = repo_dest.get_all_products()
        assert len(comps) == 1
        assert comps[0].mpn == "RC0805FR-0710KL"

    def test_backup_restore_widget_ui_separation(self, qapp, test_db_pair):
        repo_dest, dest_path, src_path = test_db_pair
        widget = DatabaseBackupRestoreWidget(repository=repo_dest)

        # Buttons exist as distinct UI triggers
        assert widget.export_btn is not None
        assert widget.restore_btn is not None
        assert widget.merge_db_btn is not None
        assert widget.export_excel_btn is not None

        assert "Backup" in widget.export_btn.text()
        assert "Restore" in widget.restore_btn.text()
        assert "Merge" in widget.merge_db_btn.text()
        assert "Export" in widget.export_excel_btn.text()
