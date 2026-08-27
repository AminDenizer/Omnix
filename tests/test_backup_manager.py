import os
import json
import gc
import tempfile
import pytest
from database import Database
from models import Component
from backup_manager import BackupManager


class TestBackupManager:
    """Test suite for digitally-signed backups, integrity checking, tampering detection, and restoration."""

    def test_standard_backup_creation_and_verification(self, sample_db_with_data):
        temp_dir = tempfile.mkdtemp()
        bak_file = os.path.join(temp_dir, "test_backup.omnixbak")

        success, msg = BackupManager.create_backup(sample_db_with_data, bak_file, is_advanced=False)
        assert success is True
        assert os.path.exists(bak_file)

        is_valid, reason, info = BackupManager.verify_backup_file(bak_file)
        assert is_valid is True
        assert info is not None
        assert info["total_components"] == 3
        assert info["backup_type"] == "عادی"

        # Cleanup
        try:
            os.remove(bak_file)
            os.rmdir(temp_dir)
        except Exception:
            pass

    def test_advanced_backup_creation(self, sample_db_with_data):
        sample_db_with_data.add_custom_category("Sensors")
        sample_db_with_data.add_custom_package("DIP-40")

        temp_dir = tempfile.mkdtemp()
        bak_file = os.path.join(temp_dir, "test_advanced_backup.omnixbak")

        success, _ = BackupManager.create_backup(sample_db_with_data, bak_file, is_advanced=True)
        assert success is True

        is_valid, _, info = BackupManager.verify_backup_file(bak_file)
        assert is_valid is True
        assert info["backup_type"] == "پیشرفته (جامع)"
        assert info["has_custom_categories"] is True
        assert info["has_custom_packages"] is True

        # Cleanup
        try:
            os.remove(bak_file)
            os.rmdir(temp_dir)
        except Exception:
            pass

    def test_tampered_backup_rejection(self, sample_db_with_data):
        temp_dir = tempfile.mkdtemp()
        bak_file = os.path.join(temp_dir, "tampered_backup.omnixbak")

        BackupManager.create_backup(sample_db_with_data, bak_file, is_advanced=False)

        # Manually tamper with the payload data without updating signature
        with open(bak_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Modify component quantity maliciously
        data["payload"]["components"][0]["quantity"] = 999999

        with open(bak_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Verification must detect the tampering and fail
        is_valid, reason, _ = BackupManager.verify_backup_file(bak_file)
        assert is_valid is False
        assert "امضای دیجیتال" in reason

        # Cleanup
        try:
            os.remove(bak_file)
            os.rmdir(temp_dir)
        except Exception:
            pass

    def test_restore_database_from_backup(self, sample_db_with_data):
        temp_dir = tempfile.mkdtemp()
        bak_file = os.path.join(temp_dir, "restore_test.omnixbak")
        BackupManager.create_backup(sample_db_with_data, bak_file, is_advanced=True)

        # Create a fresh empty database
        empty_db_path = os.path.join(temp_dir, "empty_restore.db")
        empty_db = Database(empty_db_path)
        assert len(empty_db.get_all_components()) == 0

        # Restore from backup
        success, msg = BackupManager.restore_backup(empty_db, bak_file)
        assert success is True

        restored_comps = empty_db.get_all_components()
        assert len(restored_comps) == 3
        
        # Safe cleanup for Windows file locks
        gc.collect()
        try:
            os.remove(bak_file)
            os.remove(empty_db_path)
            os.rmdir(temp_dir)
        except Exception:
            pass
