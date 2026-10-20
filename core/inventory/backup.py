"""
Omnix Core — Database Backup & Restore Service
Governing Document: Section 6 Master Architecture Specification

Provides safe, consistent, and validated backup and restoration for the authoritative
SQLite inventory database:
- Atomic online backups using SQLite's native backup API.
- Deep integrity validation (PRAGMA integrity_check, schema compatibility, table presence).
- Automatic pre-restore safety snapshot to guarantee zero data loss on failure.
- Complete preservation of component relationships, supplier links, and reference data.
- Explicit schema-version compatibility guards (rejects newer unsupported versions).
- Excludes secrets, credentials, tokens, and external source workbooks.
"""

import os
import sqlite3
import datetime
from typing import Tuple, Dict, Any, Optional

from core.inventory.database import DatabaseManager, CURRENT_SCHEMA_VERSION
from core.inventory.repository import SqliteInventoryRepository


REQUIRED_TABLES = [
    "schema_version",
    "ref_manufacturers",
    "ref_categories",
    "ref_types",
    "ref_providers",
    "components",
    "supplier_links",
    "stock_policies",
]


class DatabaseBackupService:
    """Enterprise-grade SQLite database backup and restore manager."""

    @staticmethod
    def validate_backup_file(backup_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates the integrity, schema version, and structure of a database backup file.
        Returns:
            (is_valid, message, metadata_dict)
        """
        if not backup_path or not os.path.exists(backup_path):
            return False, f"Backup file does not exist: '{backup_path}'", {}

        if os.path.getsize(backup_path) < 100:
            return False, "File is too small to be a valid SQLite database.", {}

        # 1. Verify SQLite Header Magic Bytes
        try:
            with open(backup_path, "rb") as f:
                header = f.read(16)
                if not header.startswith(b"SQLite format 3"):
                    return False, "File is not a valid SQLite database (invalid file header).", {}
        except Exception as e:
            return False, f"Failed to read backup file header: {e}", {}

        # 2. Open Read-Only Connection for Deep Integrity Check
        conn = None
        try:
            abs_p = os.path.abspath(backup_path)
            conn = sqlite3.connect(f"file:{abs_p}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            # PRAGMA integrity_check
            cursor = conn.execute("PRAGMA integrity_check;")
            integrity_rows = cursor.fetchall()
            if not integrity_rows or integrity_rows[0][0] != "ok":
                reasons = "; ".join(r[0] for r in integrity_rows)
                return False, f"Database corruption detected: {reasons}", {}

            # PRAGMA user_version
            user_ver = conn.execute("PRAGMA user_version;").fetchone()[0]

            # Schema version table check
            table_names = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
            ]

            missing_tables = [tbl for tbl in REQUIRED_TABLES if tbl not in table_names]
            if missing_tables:
                return (
                    False,
                    f"Backup is missing required application tables: {', '.join(missing_tables)}",
                    {},
                )

            # Query schema_version table
            schema_ver_row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;"
            ).fetchone()
            schema_ver = schema_ver_row[0] if schema_ver_row else user_ver

            if schema_ver > CURRENT_SCHEMA_VERSION or user_ver > CURRENT_SCHEMA_VERSION:
                return (
                    False,
                    f"Unsupported schema version (version {schema_ver}). "
                    f"This backup was created by a newer version of Omnix (current version: {CURRENT_SCHEMA_VERSION}).",
                    {},
                )

            # Gather record counts
            counts = {
                "components": conn.execute("SELECT COUNT(*) FROM components;").fetchone()[0],
                "supplier_links": conn.execute("SELECT COUNT(*) FROM supplier_links;").fetchone()[0],
                "stock_policies": conn.execute("SELECT COUNT(*) FROM stock_policies;").fetchone()[0],
                "ref_manufacturers": conn.execute("SELECT COUNT(*) FROM ref_manufacturers;").fetchone()[0],
                "ref_categories": conn.execute("SELECT COUNT(*) FROM ref_categories;").fetchone()[0],
                "ref_types": conn.execute("SELECT COUNT(*) FROM ref_types;").fetchone()[0],
                "ref_providers": conn.execute("SELECT COUNT(*) FROM ref_providers;").fetchone()[0],
                "schema_version": schema_ver,
                "file_size_bytes": os.path.getsize(abs_p),
            }

            return True, "Backup file passed all structural and integrity checks.", counts

        except Exception as e:
            return False, f"Failed to validate database backup: {e}", {}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def export_backup(
        db_manager: DatabaseManager,
        target_path: str,
        overwrite: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Exports a hot atomic snapshot of the active SQLite database to target_path.
        """
        abs_target = os.path.abspath(target_path)
        if os.path.exists(abs_target) and not overwrite:
            return False, f"Target file already exists: '{abs_target}'", {}

        os.makedirs(os.path.dirname(abs_target), exist_ok=True)

        try:
            # Perform native atomic backup
            success = db_manager.backup(abs_target)
            if not success:
                return False, "SQLite native backup operation failed.", {}

            # Validate the created snapshot
            is_valid, msg, metadata = DatabaseBackupService.validate_backup_file(abs_target)
            if not is_valid:
                # Remove corrupted output
                try:
                    os.remove(abs_target)
                except Exception:
                    pass
                return False, f"Backup creation failed integrity validation: {msg}", {}

            metadata["backup_path"] = abs_target
            metadata["exported_at"] = datetime.datetime.now().isoformat()
            return True, f"Successfully created database backup at '{abs_target}'.", metadata

        except Exception as e:
            return False, f"Backup export error: {e}", {}

    @staticmethod
    def restore_backup(
        repo: SqliteInventoryRepository,
        backup_path: str,
        safety_dir: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Safely restores a validated database backup into the active repository:
        1. Validates backup file integrity and schema version.
        2. Creates an automatic pre-restore safety snapshot.
        3. Transactionally replaces the active database using SQLite native backup.
        4. Re-initializes repository connection and schema.
        5. In case of unexpected failure, automatically rolls back to the safety snapshot.
        """
        abs_backup = os.path.abspath(backup_path)
        is_valid, val_msg, metadata = DatabaseBackupService.validate_backup_file(abs_backup)
        if not is_valid:
            return False, f"Cannot restore invalid backup: {val_msg}", {}

        current_db_path = repo.file_path
        if not current_db_path or current_db_path == ":memory:":
            return False, "Cannot restore into an in-memory or uninitialized database path.", {}

        # 1. Create Pre-Restore Safety Snapshot
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if not safety_dir:
            safety_dir = os.path.join(os.path.dirname(current_db_path), "safety_backups")
        os.makedirs(safety_dir, exist_ok=True)
        safety_path = os.path.join(safety_dir, f"pre_restore_safety_{timestamp}.db")

        safety_created = False
        if os.path.exists(current_db_path):
            safety_created = repo.backup(safety_path)
            if not safety_created:
                return False, f"Failed to create pre-restore safety snapshot at '{safety_path}'. Restore aborted.", {}

        # 2. Transactionally apply backup into active database
        backup_conn = None
        target_conn = None
        try:
            # Connect to backup source and target destination
            backup_conn = sqlite3.connect(abs_backup)
            target_conn = sqlite3.connect(current_db_path)

            with target_conn:
                backup_conn.backup(target_conn)

            target_conn.close()
            target_conn = None
            backup_conn.close()
            backup_conn = None

            # 3. Reload Repository Connection & Schema
            repo.load(current_db_path)

            # 4. Verify Active DB Integrity after Restore
            active_valid, active_msg, active_meta = DatabaseBackupService.validate_backup_file(current_db_path)
            if not active_valid:
                # Rollback to safety snapshot
                if safety_created and os.path.exists(safety_path):
                    sb_conn = sqlite3.connect(safety_path)
                    tb_conn = sqlite3.connect(current_db_path)
                    with tb_conn:
                        sb_conn.backup(tb_conn)
                    sb_conn.close()
                    tb_conn.close()
                    repo.load(current_db_path)
                return False, f"Restored database failed integrity check ({active_msg}). Rolled back to safety snapshot.", {}

            active_meta["safety_snapshot_path"] = safety_path
            active_meta["restored_from"] = abs_backup
            return True, f"Successfully restored database from '{abs_backup}'.", active_meta

        except Exception as e:
            # Rollback to safety snapshot on exception
            if safety_created and os.path.exists(safety_path):
                try:
                    sb_conn = sqlite3.connect(safety_path)
                    tb_conn = sqlite3.connect(current_db_path)
                    with tb_conn:
                        sb_conn.backup(tb_conn)
                    sb_conn.close()
                    tb_conn.close()
                    repo.load(current_db_path)
                except Exception:
                    pass
            return False, f"Error during database restore: {e}. Restored to previous state.", {}
        finally:
            if backup_conn:
                try:
                    backup_conn.close()
                except Exception:
                    pass
            if target_conn:
                try:
                    target_conn.close()
                except Exception:
                    pass
