"""
Omnix Automated Tests for Database Backup & Restore
Governing Document: Section 6 Specification
"""

import os
import sqlite3
import pytest
from PyQt6.QtWidgets import QApplication

from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.database import CURRENT_SCHEMA_VERSION, DatabaseManager
from core.inventory.backup import DatabaseBackupService
from ui.widgets.backup_restore_widget import DatabaseBackupRestoreWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_repo(tmp_path):
    db_file = str(tmp_path / "authoritative_test.db")
    repo = SqliteInventoryRepository(db_file)

    # Seed reference data
    repo.add_category("Resistor")
    repo.add_type(1, "Thick Film")
    repo.add_manufacturer("Yageo")

    # Add components and supplier links
    comp = repo.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R_0603",
            value="10k",
            quantity_in_stock=500,
        )
    )
    repo.set_supplier_links(
        comp.id,
        [
            SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lionelectronic.ir/p/101"),
            SupplierLink(vendor_id="vendor_javan", vendor_label="JAVAN", url="https://javanelec.com/p/202"),
        ]
    )

    # Configure stock policy
    repo.set_policy(
        group_key=comp.group_key,
        min_stock=100,
        target_stock=1000,
        description="Standard 10k 0603 resistor",
    )

    yield repo
    repo.close()


class TestDatabaseBackupAndRestore:
    """Tests backup creation, validation, round-trip restoration, and safety rollback."""

    def test_backup_creation_and_integrity(self, test_repo, tmp_path):
        backup_file = str(tmp_path / "omnix_backup_test.db")

        success, msg, meta = DatabaseBackupService.export_backup(
            test_repo.db_manager,
            backup_file,
            overwrite=True,
        )

        assert success is True
        assert os.path.exists(backup_file)
        assert meta["components"] == 1
        assert meta["supplier_links"] == 2
        assert meta["stock_policies"] == 1
        assert meta["ref_providers"] >= 3

        # Validate with static validator
        is_valid, val_msg, val_meta = DatabaseBackupService.validate_backup_file(backup_file)
        assert is_valid is True
        assert val_meta["components"] == 1
        assert val_meta["supplier_links"] == 2

    def test_roundtrip_restore_preserves_data_and_relationships(self, test_repo, tmp_path):
        backup_file = str(tmp_path / "roundtrip_backup.db")

        # 1. Export initial state
        success, _, _ = DatabaseBackupService.export_backup(test_repo.db_manager, backup_file)
        assert success is True

        # 2. Mutate active database (add a new component, delete old)
        comp2 = test_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="R_0805",
                value="10k",
                quantity_in_stock=200,
            )
        )
        assert len(test_repo.get_all_products()) == 2

        # 3. Restore backup
        safety_dir = str(tmp_path / "safety")
        restore_success, restore_msg, res_meta = DatabaseBackupService.restore_backup(
            test_repo,
            backup_file,
            safety_dir=safety_dir,
        )

        assert restore_success is True
        assert res_meta["components"] == 1

        # 4. Verify original records and relationships are fully restored
        restored_products = test_repo.get_all_products()
        assert len(restored_products) == 1
        p = restored_products[0]
        assert p.mpn == "RC0603FR-0710KL"
        assert p.quantity_in_stock == 500

        # Verify supplier links restored
        links = test_repo.get_supplier_links(p.id)
        assert len(links) == 2
        labels = {l.vendor_label for l in links}
        assert "LION" in labels
        assert "JAVAN" in labels

        # Verify stock policies restored
        policies = test_repo.get_all_policies()
        assert len(policies) == 1
        assert policies[0].min_stock == 100
        assert policies[0].target_stock == 1000

    def test_validation_rejects_corrupted_file(self, tmp_path):
        corrupt_file = str(tmp_path / "corrupt.db")
        with open(corrupt_file, "wb") as f:
            f.write(b"SQLite format 3\x00" + b"\xff" * 500)

        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(corrupt_file)
        assert is_valid is False
        assert "corruption" in msg.lower() or "error" in msg.lower() or "failed" in msg.lower()

    def test_validation_rejects_non_sqlite_file(self, tmp_path):
        txt_file = str(tmp_path / "not_sqlite.db")
        with open(txt_file, "w") as f:
            f.write("A" * 200)

        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(txt_file)
        assert is_valid is False
        assert "invalid file header" in msg.lower() or "not a valid sqlite" in msg.lower()

    def test_validation_rejects_unsupported_newer_schema(self, test_repo, tmp_path):
        backup_file = str(tmp_path / "future_schema.db")
        DatabaseBackupService.export_backup(test_repo.db_manager, backup_file)

        # Tamper user_version and schema_version to a future version 99
        conn = sqlite3.connect(backup_file)
        conn.execute("PRAGMA user_version = 99;")
        conn.execute("INSERT INTO schema_version (version, description) VALUES (99, 'Future version');")
        conn.commit()
        conn.close()

        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(backup_file)
        assert is_valid is False
        assert "unsupported schema version" in msg.lower()

    def test_restore_rejects_corrupted_backup_without_damaging_active_database(self, test_repo, tmp_path):
        initial_products = test_repo.get_all_products()
        assert len(initial_products) == 1

        corrupt_backup = str(tmp_path / "bad_backup.db")
        with open(corrupt_backup, "wb") as f:
            f.write(b"GARBAGE CONTENT NOT SQLITE")

        success, msg, _ = DatabaseBackupService.restore_backup(test_repo, corrupt_backup)
        assert success is False
        assert "cannot restore invalid backup" in msg.lower()

        # Active database remains intact
        assert len(test_repo.get_all_products()) == 1

    def test_backup_restore_widget_ui(self, qapp, test_repo):
        widget = DatabaseBackupRestoreWidget(repository=test_repo)
        widget.show()
        qapp.processEvents()

        assert widget.export_btn.isEnabled() is True
        assert widget.restore_btn.isEnabled() is True
        assert "Components" in widget.db_stats_lbl.text()

        widget.close()
