"""
Omnix Automated Tests for Section 4 — Backup & Restore Implementation
Governing Requirement: Section 4 Roadmap & Master Project Specification

Verifies:
1. Full backup creation with all supported persistent entities (.obk archive).
2. Backup/restore round-trip preserving records, identifiers, relationships, and relevant settings.
3. Supplier/vendor links and reference data surviving a round-trip.
4. Category hierarchy, manufacturers, and component types surviving a round-trip.
5. Persistent BOM/assembly data (stock policies per group key) surviving a round-trip.
6. Inventory Excel export remaining strictly independent of full backup.
7. Malformed or corrupted archive rejection before data mutation.
8. Unsupported backup format/schema version rejection.
9. Invalid relationships or missing required tables rejection.
10. Restore failure leaving the original data intact (safety rollback).
11. Explicit confirmation before destructive restore in UI.
12. Starter Backup validation and fresh-install initialization.
13. Starter Backup not overwriting existing user data during merge.
14. Starter Backup not being reapplied on every launch.
15. Deterministic behavior when baseline reference records already exist (idempotent merge).
16. Logging of successful and failed operations without exposing secrets.
"""

import os
import json
import sqlite3
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.database import CURRENT_SCHEMA_VERSION, DatabaseManager
from core.inventory.backup import (
    DatabaseBackupService,
    BACKUP_FORMAT_VERSION,
    BACKUP_TYPE_FULL,
    BACKUP_TYPE_STARTER,
    sanitize_settings_for_backup,
    merge_sanitized_settings,
    get_default_starter_backup_path,
)
from core.inventory.exporter import InventoryExcelExporter
from core.logger import get_event_buffer
from settings_manager import SettingsManager
from ui.widgets.backup_restore_widget import DatabaseBackupRestoreWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def populated_repo(tmp_path):
    """Creates a populated SQLite repository with all persistent entities."""
    db_file = str(tmp_path / "populated_omnix.db")
    repo = SqliteInventoryRepository(db_file)
    repo.load()

    # 1. Reference Data
    cat_id = repo.add_category("Resistor")
    repo.add_type(cat_id, "Thick Film")
    repo.add_type(cat_id, "Thin Film")
    repo.add_manufacturer("Yageo")
    repo.add_manufacturer("Vishay")

    # 2. Components
    p1 = repo.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R_0603",
            value="10k",
            quantity_in_stock=1500,
            description="10k 0603 1%",
        )
    )

    # 3. Supplier Links
    repo.set_supplier_links(
        p1.id,
        [
            SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lionelectronic.ir/p/101"),
            SupplierLink(vendor_id="vendor_javan", vendor_label="JAVAN", url="https://javanelec.com/p/202"),
        ],
    )

    # 4. Stock Policy (BOM/Assembly group-level policy)
    repo.set_policy(
        group_key=p1.group_key,
        min_stock=200,
        target_stock=2000,
        description="Standard 10k resistor stock policy",
    )

    yield repo
    repo.close()


@pytest.fixture
def mock_settings(tmp_path):
    """Creates a temporary SettingsManager instance with user preferences and credentials."""
    cfg_file = str(tmp_path / "test_settings.json")
    mgr = SettingsManager(file_path=cfg_file)
    mgr.settings["stock_policy_enabled"] = True
    mgr.settings["default_min_stock"] = 50
    mgr.settings["default_target_stock"] = 500
    mgr.set("lion_username", "test_user")
    mgr.set("lion_password", "super_secret_password_123")
    return mgr


class TestSection4BackupAndRestore:
    """Comprehensive test suite for Section 4 requirements."""

    # 1. Full backup creation with all supported persistent entities
    def test_full_backup_creation_contains_all_entities_and_manifest(self, populated_repo, mock_settings, tmp_path):
        backup_file = str(tmp_path / "full_backup.obk")

        success, msg, meta = DatabaseBackupService.export_full_backup(
            repo=populated_repo,
            target_path=backup_file,
            settings_mgr=mock_settings,
            overwrite=True,
            description="Production Test Full Backup",
        )

        assert success is True
        assert os.path.exists(backup_file)
        assert meta["backup_type"] == BACKUP_TYPE_FULL
        assert meta["format_version"] == BACKUP_FORMAT_VERSION
        assert meta["components"] == 1
        assert meta["supplier_links"] == 2
        assert meta["stock_policies"] == 1
        assert meta["ref_manufacturers"] >= 2
        assert meta["ref_categories"] >= 1
        assert meta["has_settings"] is False

        # Inspect ZIP archive structure
        with zipfile.ZipFile(backup_file, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "database.db" in namelist
            # MPS §16.3: Settings are strictly independent and must not be in backup archives
            assert "settings.json" not in namelist

            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["app_name"] == "Omnix"
            assert manifest["backup_type"] == "full"
            assert manifest["has_settings"] is False
            assert manifest["entity_counts"]["components"] == 1

    # 2. Backup/restore round-trip preserving records, identifiers, relationships, and settings
    def test_backup_restore_roundtrip_preserves_environment(self, populated_repo, mock_settings, tmp_path):
        backup_file = str(tmp_path / "roundtrip.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file, settings_mgr=mock_settings)

        # Mutate database state (delete component, add new, change settings)
        old_products = populated_repo.get_all_products()
        orig_id = old_products[0].id
        populated_repo.delete_component(orig_id)
        assert len(populated_repo.get_all_products()) == 0

        mock_settings.settings["stock_policy_enabled"] = False
        mock_settings.save()

        # Restore from archive
        success, msg, res_meta = DatabaseBackupService.restore_backup(
            repo=populated_repo,
            backup_path=backup_file,
            settings_mgr=mock_settings,
            restore_settings=True,
        )

        assert success is True
        # Verify component restored with identical attributes
        restored = populated_repo.get_all_products()
        assert len(restored) == 1
        p = restored[0]
        assert p.mpn == "RC0603FR-0710KL"
        assert p.quantity_in_stock == 1500

        # MPS §16.3: Active local user settings and credentials remain intact and are not overwritten by restore
        mock_settings.load()
        assert mock_settings.settings["stock_policy_enabled"] is False
        assert mock_settings.settings["lion_password"] == "super_secret_password_123"

    # 3. Supplier/vendor names and reference data surviving round-trip
    def test_supplier_links_survive_roundtrip(self, populated_repo, mock_settings, tmp_path):
        backup_file = str(tmp_path / "supplier_backup.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file)

        p = populated_repo.get_all_products()[0]
        links = populated_repo.get_supplier_links(p.id)
        assert len(links) == 2

        # Restore
        DatabaseBackupService.restore_backup(populated_repo, backup_file)
        restored_p = populated_repo.get_all_products()[0]
        restored_links = populated_repo.get_supplier_links(restored_p.id)
        assert len(restored_links) == 2
        labels = {l.vendor_label for l in restored_links}
        assert "LION" in labels
        assert "JAVAN" in labels

    # 4. Category hierarchy, manufacturers, and component types surviving round-trip
    def test_reference_data_hierarchy_survives_roundtrip(self, populated_repo, tmp_path):
        backup_file = str(tmp_path / "ref_backup.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file)

        # Mutate reference data
        populated_repo.add_category("Inductor")
        assert populated_repo.get_category_by_name("Inductor") is not None

        # Restore
        DatabaseBackupService.restore_backup(populated_repo, backup_file)

        # Verify restored categories and types
        cat = populated_repo.get_category_by_name("Resistor")
        assert cat is not None
        types = populated_repo.get_types_for_category(cat.id)
        type_names = {t.name for t in types}
        assert "Thick Film" in type_names
        assert "Thin Film" in type_names

        # Verify Inductor is gone (restored to backup state)
        assert populated_repo.get_category_by_name("Inductor") is None

    # 5. Persistent BOM/assembly data (stock policies per group key) surviving round-trip
    def test_stock_policies_survive_roundtrip(self, populated_repo, tmp_path):
        backup_file = str(tmp_path / "policy_backup.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file)

        policies = populated_repo.get_all_policies()
        assert len(policies) == 1
        pol = policies[0]
        assert pol.min_stock == 200
        assert pol.target_stock == 2000

        # Clear policies
        populated_repo.delete_policy(pol.group_key)
        assert len(populated_repo.get_all_policies()) == 0

        # Restore
        DatabaseBackupService.restore_backup(populated_repo, backup_file)
        restored_policies = populated_repo.get_all_policies()
        assert len(restored_policies) == 1
        assert restored_policies[0].min_stock == 200
        assert restored_policies[0].target_stock == 2000

    # 6. Inventory Excel export remaining strictly independent of full backup
    def test_excel_export_independent_of_backup(self, populated_repo, tmp_path):
        excel_path = str(tmp_path / "test_inventory_export.xlsx")
        res_path = InventoryExcelExporter.export(populated_repo, excel_path)
        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 1000

        # Excel export must NOT be recognized as an Omnix backup archive
        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(res_path)
        assert is_valid is False

    # 7. Malformed or corrupted archive rejection before data mutation
    def test_malformed_archive_rejection_prevents_data_mutation(self, populated_repo, tmp_path):
        bad_archive = str(tmp_path / "corrupted.obk")
        with zipfile.ZipFile(bad_archive, "w") as zf:
            zf.writestr("manifest.json", "NOT JSON")
            zf.writestr("database.db", b"GARBAGE")

        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(bad_archive)
        assert is_valid is False
        assert "malformed" in msg.lower() or "invalid" in msg.lower()

        # Attempt restore must fail and leave active data untouched
        success, r_msg, _ = DatabaseBackupService.restore_backup(populated_repo, bad_archive)
        assert success is False
        assert len(populated_repo.get_all_products()) == 1

    # 8. Unsupported backup version rejection
    def test_unsupported_backup_version_rejection(self, populated_repo, tmp_path):
        future_backup = str(tmp_path / "future_v99.obk")
        # Export valid, then tamper manifest format version
        DatabaseBackupService.export_full_backup(populated_repo, future_backup)

        temp_dir = str(tmp_path / "tamper")
        os.makedirs(temp_dir, exist_ok=True)
        with zipfile.ZipFile(future_backup, "r") as zf:
            zf.extractall(temp_dir)

        manifest_file = os.path.join(temp_dir, "manifest.json")
        with open(manifest_file, "r") as mf:
            m_data = json.load(mf)
        m_data["format_version"] = "99.0.0"
        with open(manifest_file, "w") as mf:
            json.dump(m_data, mf)

        tampered_archive = str(tmp_path / "tampered_v99.obk")
        with zipfile.ZipFile(tampered_archive, "w") as zf:
            for fname in os.listdir(temp_dir):
                zf.write(os.path.join(temp_dir, fname), fname)

        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(tampered_archive)
        assert is_valid is False
        assert "unsupported backup format version" in msg.lower()

    # 9. Invalid relationships or missing required data rejection
    def test_missing_required_tables_rejected(self, tmp_path):
        incomplete_db = str(tmp_path / "incomplete.db")
        conn = sqlite3.connect(incomplete_db)
        conn.execute("CREATE TABLE schema_version (version INTEGER);")
        conn.execute("INSERT INTO schema_version VALUES (1);")
        conn.commit()
        conn.close()

        is_valid, msg, meta = DatabaseBackupService.validate_sqlite_database(incomplete_db)
        assert is_valid is False
        assert "missing required application tables" in msg.lower()

    # 10. Restore failure leaving the original data intact (safety snapshot rollback)
    def test_restore_rollback_preserves_original_state_on_failure(self, populated_repo, tmp_path):
        orig_count = len(populated_repo.get_all_products())
        assert orig_count == 1

        # Simulate a corrupted source database during restore
        corrupt_src = str(tmp_path / "corrupted_source.db")
        with open(corrupt_src, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE")

        safety_dir = str(tmp_path / "safety")
        success, msg, meta = DatabaseBackupService.restore_backup(
            populated_repo,
            corrupt_src,
            safety_dir=safety_dir,
        )

        assert success is False
        assert len(populated_repo.get_all_products()) == 1

    # 11. Explicit confirmation before destructive restore
    def test_ui_restore_requires_explicit_confirmation(self, qapp, populated_repo, tmp_path):
        backup_file = str(tmp_path / "test_ui_backup.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file)

        widget = DatabaseBackupRestoreWidget(repository=populated_repo)
        widget.show()
        qapp.processEvents()

        # Mock QFileDialog to return our backup file, and QMessageBox to answer No
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(backup_file, "")), \
             patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No) as mock_q:
            widget._handle_restore_backup()
            assert mock_q.called
            # When user answers No, no restore must occur
            assert len(populated_repo.get_all_products()) == 1

        widget.close()

    # 12. Starter Backup validation and fresh-install initialization
    def test_starter_backup_validation_and_clean_reset(self, populated_repo, tmp_path):
        starter_file = str(tmp_path / "starter_test.obk")
        s, m, meta = DatabaseBackupService.export_starter_backup(populated_repo, starter_file)
        assert s is True
        assert meta["backup_type"] == BACKUP_TYPE_STARTER
        assert meta["components"] == 0
        assert meta["stock_policies"] == 0
        assert meta["ref_categories"] >= 1
        assert meta["ref_manufacturers"] >= 2

        # Validate starter archive
        is_valid, msg, val_meta = DatabaseBackupService.validate_backup_file(starter_file)
        assert is_valid is True
        assert val_meta["backup_type"] == "starter"

        # Apply clean_reset strategy on a new database
        fresh_db = str(tmp_path / "fresh_installed.db")
        fresh_repo = SqliteInventoryRepository(fresh_db)
        fresh_repo.load()

        succ, r_msg, r_meta = DatabaseBackupService.apply_starter_backup(
            fresh_repo,
            starter_path=starter_file,
            strategy="clean_reset",
        )
        assert succ is True
        assert len(fresh_repo.get_all_products()) == 0
        assert fresh_repo.get_category_by_name("Resistor") is not None
        assert fresh_repo.get_manufacturer_by_name("Yageo") is not None
        fresh_repo.close()

    # 13. Starter Backup not overwriting existing user data during safe merge
    def test_starter_backup_merge_preserves_existing_user_inventory(self, populated_repo, tmp_path):
        starter_file = str(tmp_path / "starter_for_merge.obk")
        DatabaseBackupService.export_starter_backup(populated_repo, starter_file)

        # Existing inventory: 1 component
        assert len(populated_repo.get_all_products()) == 1
        initial_mpn = populated_repo.get_all_products()[0].mpn

        # Apply starter backup in default 'merge_reference' mode
        succ, msg, res_meta = DatabaseBackupService.apply_starter_backup(
            populated_repo,
            starter_path=starter_file,
            strategy="merge_reference",
        )

        assert succ is True
        # Existing component must remain intact
        products = populated_repo.get_all_products()
        assert len(products) == 1
        assert products[0].mpn == initial_mpn
        assert products[0].quantity_in_stock == 1500

    # 14. Starter Backup not being reapplied on every launch
    def test_starter_backup_not_applied_automatically_on_launch(self, tmp_path):
        empty_db = str(tmp_path / "empty_launch.db")
        repo = SqliteInventoryRepository(empty_db)
        repo.load()

        # Loading repository initializes schema, but does NOT seed categories unless explicit
        cats = repo.get_all_categories()
        assert len(cats) == 0
        repo.close()

    # 15. Deterministic behavior when baseline reference records already exist (idempotency)
    def test_starter_backup_repeated_merge_is_idempotent(self, populated_repo, tmp_path):
        starter_file = str(tmp_path / "starter_idempotent.obk")
        DatabaseBackupService.export_starter_backup(populated_repo, starter_file)

        # Run merge once
        DatabaseBackupService.apply_starter_backup(populated_repo, starter_file, strategy="merge_reference")
        count_mfr_1 = len(populated_repo.get_all_manufacturers(include_inactive=True))
        count_cat_1 = len(populated_repo.get_all_categories(include_inactive=True))

        # Run merge second time
        s2, m2, meta2 = DatabaseBackupService.apply_starter_backup(populated_repo, starter_file, strategy="merge_reference")
        assert s2 is True
        assert meta2["added_manufacturers"] == 0
        assert meta2["added_categories"] == 0

        count_mfr_2 = len(populated_repo.get_all_manufacturers(include_inactive=True))
        count_cat_2 = len(populated_repo.get_all_categories(include_inactive=True))
        assert count_mfr_1 == count_mfr_2
        assert count_cat_1 == count_cat_2

    # 16. Logging of successful and failed operations without exposing secrets
    def test_logging_tracks_lifecycle_and_redacts_secrets(self, populated_repo, mock_settings, tmp_path):
        buffer = get_event_buffer()
        buffer.clear()

        backup_file = str(tmp_path / "logged_backup.obk")
        DatabaseBackupService.export_full_backup(populated_repo, backup_file, settings_mgr=mock_settings)

        events = buffer.get_all()
        backup_events = [e for e in events if e.domain == "BackupRestore"]
        assert len(backup_events) >= 2  # START and COMPLETION

        # Verify password secret is never in any log event
        for ev in backup_events:
            assert "super_secret_password_123" not in ev.message
            if ev.details:
                details_str = json.dumps(ev.details)
                assert "super_secret_password_123" not in details_str

    # 17. Malicious path-traversal entries (Zip Slip) rejection before extraction
    def test_malicious_path_traversal_archive_rejected_before_extraction(self, populated_repo, tmp_path):
        """
        Verifies that an archive with path traversal entries ('../../evil.txt' or '..\\evil.txt')
        is strictly rejected during validation and restore cannot write files outside the intended paths.
        """
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        target_outside = tmp_path / "evil.txt"
        assert not target_outside.exists()

        # Create valid components for archive
        valid_db = str(sandbox / "valid.db")
        populated_repo.backup(valid_db)
        manifest_data = json.dumps({
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_type": BACKUP_TYPE_FULL,
            "app_name": "Omnix",
            "created_at": "2026-10-23T00:00:00",
        })

        for traversal_entry in ["../../evil.txt", "..\\evil.txt", "sub/../../evil.txt"]:
            bad_archive = str(sandbox / f"traversal_{abs(hash(traversal_entry))}.obk")
            with zipfile.ZipFile(bad_archive, "w") as zf:
                zf.writestr("manifest.json", manifest_data)
                zf.write(valid_db, "database.db")
                zf.writestr(traversal_entry, "MALICIOUS PAYLOAD")

            # 1. Validation must immediately reject archive
            is_valid, msg, _ = DatabaseBackupService.validate_backup_file(bad_archive)
            assert is_valid is False
            assert "unsafe path traversal" in msg.lower() or "traversal" in msg.lower()

            # 2. Restore must fail and not extract the malicious file
            success, r_msg, _ = DatabaseBackupService.restore_backup(populated_repo, bad_archive)
            assert success is False
            assert not target_outside.exists(), f"Path traversal breached sandbox for entry '{traversal_entry}'!"

    # 18. Invalid settings.json rejection before modifying active database or settings
    def test_malformed_settings_json_rejected_before_data_mutation(self, populated_repo, mock_settings, tmp_path):
        """
        Verifies that an archive with a valid manifest and database but malformed or truncated
        settings.json is rejected before mutating active database or settings.
        """
        valid_db = str(tmp_path / "valid.db")
        populated_repo.backup(valid_db)
        manifest_data = json.dumps({
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_type": BACKUP_TYPE_FULL,
            "app_name": "Omnix",
            "created_at": "2026-10-23T00:00:00",
        })

        # Archive with truncated/malformed settings.json
        bad_settings_archive = str(tmp_path / "bad_settings.obk")
        with zipfile.ZipFile(bad_settings_archive, "w") as zf:
            zf.writestr("manifest.json", manifest_data)
            zf.write(valid_db, "database.db")
            zf.writestr("settings.json", b'{"theme": "dark", "general": {')  # Truncated JSON

        # Initial state before restore attempt
        initial_products = populated_repo.get_all_products()
        assert len(initial_products) == 1
        initial_theme = mock_settings.get("theme", "system")
        mock_settings.set("theme", "light")
        mock_settings.save()

        # 1. Validation must fail due to malformed settings.json
        is_valid, msg, _ = DatabaseBackupService.validate_backup_file(bad_settings_archive)
        assert is_valid is False
        assert "settings.json" in msg.lower()

        # 2. Restore must be rejected before touching database or settings
        success, r_msg, _ = DatabaseBackupService.restore_backup(
            repo=populated_repo,
            backup_path=bad_settings_archive,
            settings_mgr=mock_settings,
            restore_settings=True,
        )
        assert success is False

        # Verify active database was untouched
        assert len(populated_repo.get_all_products()) == 1
        assert populated_repo.get_all_products()[0].mpn == initial_products[0].mpn

        # Verify active settings were untouched
        mock_settings.load()
        assert mock_settings.get("theme") == "light"

    # 19. Failure and recovery: Post-restore validation failure rolls back both database and settings
    def test_post_restore_validation_failure_rolls_back_database_and_settings(self, populated_repo, mock_settings, tmp_path):
        """
        Verifies that when a failure occurs during post-restore validation (or database replacement),
        the system rolls back both active database and active settings to their pre-restore state.
        """
        # Create a second distinct repository to be restored
        other_db = str(tmp_path / "other.db")
        other_repo = SqliteInventoryRepository(other_db)
        other_repo.load()
        cat_id = other_repo.add_category("IC")
        other_repo.add_type(cat_id, "Timer")
        other_repo.add_manufacturer("TI")
        other_repo.create_component(
            InventoryProduct(
                manufacturer="TI",
                mpn="NE555P",
                category="IC",
                type_technology="Timer",
                package="DIP-8",
                footprint="DIP8",
                value="555",
                quantity_in_stock=42,
            )
        )
        other_settings = SettingsManager(file_path=str(tmp_path / "other_settings.json"))
        other_settings.set("theme", "other_custom_theme")
        other_settings.save()

        archive_to_restore = str(tmp_path / "other_package.obk")
        DatabaseBackupService.export_full_backup(
            repo=other_repo,
            target_path=archive_to_restore,
            settings_mgr=other_settings,
        )
        other_repo.close()

        # Populate current repo and current settings with distinct initial state
        initial_mpn = populated_repo.get_all_products()[0].mpn
        mock_settings.set("theme", "initial_active_theme")
        mock_settings.save()

        # Simulate post-restore validation failure
        real_validate_sqlite = DatabaseBackupService.validate_sqlite_database
        def mock_validate_sqlite(db_path):
            # Allow validation during initial backup_file check, but fail post-restore check on active db
            if os.path.abspath(db_path) == os.path.abspath(populated_repo.file_path):
                return False, "Simulated post-restore integrity failure", {}
            return real_validate_sqlite(db_path)

        with patch.object(DatabaseBackupService, "validate_sqlite_database", side_effect=mock_validate_sqlite):
            success, msg, meta = DatabaseBackupService.restore_backup(
                repo=populated_repo,
                backup_path=archive_to_restore,
                settings_mgr=mock_settings,
                restore_settings=True,
            )

        assert success is False
        assert "integrity check" in msg.lower() or "rolled back" in msg.lower()

        # Verify active database was rolled back to initial state
        products = populated_repo.get_all_products()
        assert len(products) == 1
        assert products[0].mpn == initial_mpn
        all_mpns = [p.mpn for p in products]
        assert "NE555P" not in all_mpns

        # Verify active settings were preserved/rolled back to initial state
        mock_settings.load()
        assert mock_settings.get("theme") == "initial_active_theme"

    # 20. Failure during database replacement rolls back cleanly
    def test_failure_during_database_replacement_rolls_back_cleanly(self, populated_repo, mock_settings, tmp_path):
        """
        Verifies that if an unexpected exception occurs while applying the backup into the active DB,
        the rollback handler restores the database and settings cleanly.
        """
        # Create a valid backup
        valid_backup = str(tmp_path / "valid_test.obk")
        DatabaseBackupService.export_full_backup(populated_repo, valid_backup, settings_mgr=mock_settings)

        initial_mpn = populated_repo.get_all_products()[0].mpn
        mock_settings.set("theme", "replacement_test_theme")
        mock_settings.save()

        real_connect = sqlite3.connect

        def selective_connect(path, *args, **kwargs):
            if os.path.basename(str(path)) == "database.db":
                mock_conn = MagicMock()
                mock_conn.backup.side_effect = sqlite3.OperationalError("Simulated disk error during replacement")
                return mock_conn
            return real_connect(path, *args, **kwargs)

        with patch("core.inventory.backup.sqlite3.connect", side_effect=selective_connect):
            success, msg, _ = DatabaseBackupService.restore_backup(
                repo=populated_repo,
                backup_path=valid_backup,
                settings_mgr=mock_settings,
                restore_settings=True,
            )

        assert success is False
        assert "error during database restore" in msg.lower()
        assert "restored to previous state" in msg.lower()

        # Database and settings must be intact
        assert len(populated_repo.get_all_products()) == 1
        assert populated_repo.get_all_products()[0].mpn == initial_mpn
        mock_settings.load()
        assert mock_settings.get("theme") == "replacement_test_theme"

    # 21. Failure during database replacement followed by rollback failure reports both outcomes
    def test_restore_failure_with_rollback_failure_reports_both_accurately(self, populated_repo, mock_settings, tmp_path):
        """
        Verifies that if an unexpected exception occurs while applying the backup and the rollback
        also fails, the service reports failure, surfaces both errors, and does NOT claim the
        previous state was restored.
        """
        valid_backup = str(tmp_path / "valid_test.obk")
        DatabaseBackupService.export_full_backup(populated_repo, valid_backup, settings_mgr=mock_settings)

        real_connect = sqlite3.connect
        rollback_armed = [False]

        def failing_connect(path, *args, **kwargs):
            base = os.path.basename(str(path))
            if base == "database.db":
                rollback_armed[0] = True
                raise sqlite3.OperationalError("Simulated primary restore disk fault")
            elif rollback_armed[0] and "pre_restore_safety_" in base:
                raise sqlite3.OperationalError("Simulated secondary rollback disk fault")
            return real_connect(path, *args, **kwargs)

        with patch("core.inventory.backup.sqlite3.connect", side_effect=failing_connect):
            success, msg, _ = DatabaseBackupService.restore_backup(
                repo=populated_repo,
                backup_path=valid_backup,
                settings_mgr=mock_settings,
                restore_settings=True,
            )

        assert success is False
        assert "error during database restore" in msg.lower()
        assert "primary restore disk fault" in msg.lower()
        assert "rollback to previous state also failed" in msg.lower()
        assert "secondary rollback disk fault" in msg.lower()
        # Must NEVER claim previous state was restored
        assert "restored to previous state." not in msg.lower()

    # 22. Post-restore integrity failure with rollback failure reports both outcomes
    def test_post_restore_integrity_failure_with_rollback_failure_reports_both(self, populated_repo, mock_settings, tmp_path):
        """
        Verifies that if post-restore validation fails and safety rollback also fails,
        the service reports failure, surfaces both errors, and does not claim rollback succeeded.
        """
        valid_backup = str(tmp_path / "valid_test.obk")
        DatabaseBackupService.export_full_backup(populated_repo, valid_backup, settings_mgr=mock_settings)

        real_connect = sqlite3.connect
        real_validate_sqlite = DatabaseBackupService.validate_sqlite_database
        rollback_armed = [False]

        def failing_connect(path, *args, **kwargs):
            base = os.path.basename(str(path))
            if rollback_armed[0] and "pre_restore_safety_" in base:
                raise sqlite3.OperationalError("Simulated rollback I/O crash")
            return real_connect(path, *args, **kwargs)

        def mock_validate(db_path):
            if os.path.abspath(db_path) == os.path.abspath(populated_repo.file_path):
                rollback_armed[0] = True
                return False, "Simulated database corruption post-restore", {}
            return real_validate_sqlite(db_path)

        with patch("core.inventory.backup.sqlite3.connect", side_effect=failing_connect), \
             patch.object(DatabaseBackupService, "validate_sqlite_database", side_effect=mock_validate):
            success, msg, _ = DatabaseBackupService.restore_backup(
                repo=populated_repo,
                backup_path=valid_backup,
                settings_mgr=mock_settings,
                restore_settings=True,
            )

        assert success is False
        assert "failed integrity check" in msg.lower()
        assert "rollback to previous state also failed" in msg.lower()
        assert "rollback i/o crash" in msg.lower()
        assert "rolled back to safety snapshot" not in msg.lower()

    # 23. Bundled Starter Baseline Archive Verification
    def test_bundled_starter_archive_canonical_integrity(self):
        """
        Validates the physical checked-in starter archive on disk: 'data/starter_backup.obk'.
        Guarantees that the distributed asset strictly matches the canonical reference taxonomy:
        - Exactly 22 categories
        - Exactly 205 category-scoped types
        - Exactly 399 canonical manufacturers
        - Exactly 4 link providers
        - Zero inventory components, zero stock policies, and zero supplier links
        - Zero obsolete top-level categories ('BJT', 'MOSFET', 'JFET', 'IGBT')
        - Transistor technologies correctly consolidated under 'Transistor'
        - Zero orphaned types
        """
        import os
        import zipfile
        import sqlite3
        import tempfile
        from core.inventory.backup import get_default_starter_backup_path, DatabaseBackupService

        starter_path = get_default_starter_backup_path()
        assert starter_path is not None, "Starter backup archive path could not be resolved"
        assert os.path.exists(starter_path), f"Starter archive not found at: {starter_path}"

        # 1. Structural and integrity validation using existing service API
        is_valid, msg, meta = DatabaseBackupService.validate_backup_file(starter_path)
        assert is_valid is True, f"Bundled starter archive failed validation: {msg}"
        assert meta["backup_type"] == "starter"
        assert meta["format_version"] == "1.0.0"

        # 2. Assert canonical entity counts reported in metadata / manifest
        assert meta["ref_categories"] == 22, f"Expected 22 categories, got {meta.get('ref_categories')}"
        assert meta["ref_types"] == 205, f"Expected 205 types, got {meta.get('ref_types')}"
        assert meta["ref_manufacturers"] == 399, f"Expected 399 manufacturers, got {meta.get('ref_manufacturers')}"
        assert meta["ref_providers"] == 4, f"Expected 4 providers, got {meta.get('ref_providers')}"
        assert meta["components"] == 0, "Starter archive must contain zero components"
        assert meta["stock_policies"] == 0, "Starter archive must contain zero stock policies"
        assert meta["supplier_links"] == 0, "Starter archive must contain zero supplier links"
        assert meta.get("has_settings") is False, "Starter archive must not contain settings"

        # 3. Direct inspection of embedded SQLite database
        with zipfile.ZipFile(starter_path, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "database.db" in zf.namelist()
            assert "settings.json" not in zf.namelist()

            with tempfile.TemporaryDirectory() as tmp_dir:
                extracted_db = os.path.join(tmp_dir, "starter_extracted.db")
                with open(extracted_db, "wb") as f_out:
                    f_out.write(zf.read("database.db"))

                conn = sqlite3.connect(f"file:{os.path.abspath(extracted_db)}?mode=ro", uri=True)
                cur = conn.cursor()

                # Zero components, policies, links
                cur.execute("SELECT COUNT(*) FROM components;")
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT COUNT(*) FROM stock_policies;")
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT COUNT(*) FROM supplier_links;")
                assert cur.fetchone()[0] == 0

                # Categories verification
                cur.execute("SELECT id, name FROM ref_categories ORDER BY id;")
                categories = cur.fetchall()
                assert len(categories) == 22
                cat_names = [c[1] for c in categories]
                assert "Transistor" in cat_names

                # No obsolete top-level categories
                for obsolete in ["BJT", "MOSFET", "JFET", "IGBT"]:
                    assert obsolete not in cat_names, f"Obsolete category '{obsolete}' found in starter archive"

                # Transistor scoped technologies
                cur.execute(
                    "SELECT t.name FROM ref_types t JOIN ref_categories c ON c.id=t.category_id WHERE c.name='Transistor' ORDER BY t.id;"
                )
                trans_types = [r[0] for r in cur.fetchall()]
                assert len(trans_types) == 9
                for expected_tech in ["BJT", "MOSFET", "JFET", "IGBT", "Darlington", "Digital Transistor", "RF Transistor", "Power Transistor", "Other / Special-Purpose"]:
                    assert expected_tech in trans_types, f"Expected technology '{expected_tech}' missing from Transistor category"

                # Zero orphaned types
                cur.execute("SELECT COUNT(*) FROM ref_types WHERE category_id NOT IN (SELECT id FROM ref_categories);")
                assert cur.fetchone()[0] == 0, "Orphaned types detected in starter database"

                # Zero duplicate normalized names
                cur.execute("SELECT norm_name, COUNT(*) FROM ref_categories GROUP BY norm_name HAVING COUNT(*) > 1;")
                assert len(cur.fetchall()) == 0
                cur.execute("SELECT norm_name, COUNT(*) FROM ref_manufacturers GROUP BY norm_name HAVING COUNT(*) > 1;")
                assert len(cur.fetchall()) == 0
                cur.execute("SELECT category_id, norm_name, COUNT(*) FROM ref_types GROUP BY category_id, norm_name HAVING COUNT(*) > 1;")
                assert len(cur.fetchall()) == 0

                conn.close()
