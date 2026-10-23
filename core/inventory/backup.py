"""
Omnix Core — Database Backup & Restore Service
Governing Document: Section 4 — Backup & Restore Implementation (DOC-OMNIX-MPS-001)

Provides safe, consistent, versioned, and validated backup and restoration for the
authoritative SQLite inventory database and application environment:
- Portable, versioned Omnix Backup Archive (.obk / .zip) bundling database and sanitized settings.
- Backward-compatible support for legacy SQLite database backups (.db / .sqlite).
- Atomic online backups using SQLite's native backup API.
- Deep integrity validation (PRAGMA integrity_check, schema compatibility, table presence).
- Automatic pre-restore safety snapshots guaranteeing zero data loss on failure.
- Complete preservation of component relationships, supplier links, and reference data.
- Explicit schema-version and backup-format compatibility guards.
- Automatic redaction of credentials, passwords, session tokens, and secrets from backups.
- Standalone Starter Backup baseline mechanism for fresh installations without fabricated data.
"""

import os
import json
import shutil
import sqlite3
import zipfile
import tempfile
import datetime
from typing import Tuple, Dict, Any, Optional, List

from config import get_app_dir, get_bundle_dir, APP_NAME, APP_VERSION
from core.inventory.database import DatabaseManager, CURRENT_SCHEMA_VERSION
from core.inventory.repository import SqliteInventoryRepository
from core.logger import log_event, track_operation, sanitize_text

# Format & Type Constants
BACKUP_FORMAT_VERSION = "1.0.0"
CURRENT_BACKUP_FORMAT_MAJOR = 1

BACKUP_TYPE_FULL = "full"
BACKUP_TYPE_STARTER = "starter"
BACKUP_TYPE_LEGACY_DB = "legacy_sqlite"

ARCHIVE_MANIFEST_FILENAME = "manifest.json"
ARCHIVE_DATABASE_FILENAME = "database.db"
ARCHIVE_SETTINGS_FILENAME = "settings.json"

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

SECRET_KEY_NAMES = {
    "password", "lion_password", "token", "secret", "cookie",
    "credential", "api_key", "apikey", "session_id", "private_key", "jwt"
}


def sanitize_settings_for_backup(settings_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively clones a settings dictionary, clearing or excluding all password
    and credential fields so sensitive authentication secrets are never exported.
    """
    if not isinstance(settings_dict, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for k, v in settings_dict.items():
        k_lower = str(k).lower().replace("-", "_")
        if any(secret_term in k_lower for secret_term in SECRET_KEY_NAMES):
            sanitized[k] = ""
        elif isinstance(v, dict):
            sanitized[k] = sanitize_settings_for_backup(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_settings_for_backup(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v

    return sanitized


def merge_sanitized_settings(existing_settings: Dict[str, Any], imported_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merges imported settings into existing settings, updating configuration preferences
    while preserving existing local passwords if the imported field is blank.
    """
    merged = dict(existing_settings)
    for k, v in imported_settings.items():
        k_lower = str(k).lower().replace("-", "_")
        is_secret = any(secret_term in k_lower for secret_term in SECRET_KEY_NAMES)

        if is_secret:
            # Preserve existing local secret if imported secret is empty/blank
            if v and str(v).strip():
                merged[k] = v
        elif k == "vendors" and isinstance(v, dict):
            existing_vendors = merged.setdefault("vendors", {})
            for vid, vcfg in v.items():
                if isinstance(vcfg, dict):
                    ev = existing_vendors.setdefault(vid, {})
                    for vk, vv in vcfg.items():
                        vk_lower = str(vk).lower()
                        if any(st in vk_lower for st in SECRET_KEY_NAMES):
                            if vv and str(vv).strip():
                                ev[vk] = vv
                        else:
                            ev[vk] = vv
        elif isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = merge_sanitized_settings(merged[k], v)
        else:
            merged[k] = v

    # Ensure legacy lion_password and vendor_lion password stay synchronized
    v_lion = merged.get("vendors", {}).get("vendor_lion")
    if isinstance(v_lion, dict):
        if merged.get("lion_password") and not v_lion.get("password"):
            v_lion["password"] = merged["lion_password"]
        elif v_lion.get("password") and not merged.get("lion_password"):
            merged["lion_password"] = v_lion["password"]

    return merged


def is_archive_file(file_path: str) -> bool:
    """Check if file starts with ZIP signature bytes or has archive extension."""
    if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) < 22:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
            return header.startswith(b"PK\x03\x04")
    except Exception:
        return False


def get_default_starter_backup_path() -> Optional[str]:
    """
    Resolves the default Starter Backup baseline archive path.
    Checks candidate locations in data and bundle directories.
    """
    candidates = [
        os.path.join(get_app_dir(), "data", "starter_backup.obk"),
        os.path.join(get_bundle_dir(), "data", "starter_backup.obk"),
        os.path.join(get_app_dir(), "data", "starter_backup.zip"),
        os.path.join(get_app_dir(), "data", "starter_backup.db"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 100:
            return os.path.abspath(p)
    return None


class DatabaseBackupService:
    """Enterprise-grade Omnix Backup, Restore, and Starter Baseline Manager."""

    @staticmethod
    def validate_sqlite_database(db_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates the integrity, schema version, and structure of a raw SQLite database file.
        """
        if not db_path or not os.path.exists(db_path):
            return False, f"Database file does not exist: '{db_path}'", {}

        if os.path.getsize(db_path) < 100:
            return False, "File is too small to be a valid SQLite database.", {}

        # 1. Verify SQLite Header Magic Bytes
        try:
            with open(db_path, "rb") as f:
                header = f.read(16)
                if not header.startswith(b"SQLite format 3"):
                    return False, "File is not a valid SQLite database (invalid file header).", {}
        except Exception as e:
            return False, f"Failed to read database file header: {e}", {}

        # 2. Open Read-Only Connection for Deep Integrity Check
        conn = None
        try:
            abs_p = os.path.abspath(db_path)
            conn = sqlite3.connect(f"file:{abs_p}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            # PRAGMA integrity_check
            cursor = conn.execute("PRAGMA integrity_check;")
            integrity_rows = cursor.fetchall()
            if not integrity_rows or integrity_rows[0][0] != "ok":
                reasons = "; ".join(r[0] for r in integrity_rows)
                return False, f"Database corruption detected: {reasons}", {}

            # PRAGMA foreign_key_check
            fk_cursor = conn.execute("PRAGMA foreign_key_check;")
            fk_errors = fk_cursor.fetchall()
            if fk_errors:
                return False, f"Foreign key constraint violation detected in database ({len(fk_errors)} orphaned reference(s)).", {}

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
                "backup_type": BACKUP_TYPE_LEGACY_DB,
            }

            return True, "Database file passed all structural and integrity checks.", counts

        except Exception as e:
            return False, f"Failed to validate database backup: {e}", {}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def validate_backup_file(backup_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates any supported Omnix backup format:
        1. Unified Omnix Backup Archive (.obk / .zip with manifest.json and database.db).
        2. Legacy standalone SQLite database (.db / .sqlite).
        """
        if not backup_path or not os.path.exists(backup_path):
            return False, f"Backup file does not exist: '{backup_path}'", {}

        if is_archive_file(backup_path):
            return DatabaseBackupService.validate_archive_package(backup_path)
        else:
            return DatabaseBackupService.validate_sqlite_database(backup_path)

    @staticmethod
    def validate_archive_package(archive_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates an Omnix Backup Archive (.obk / .zip):
        - Zip archive structure integrity.
        - Manifest presence, schema version, and metadata.
        - Embedded SQLite database deep integrity.
        - Embedded settings validity if present.
        """
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                # 1. Test zip CRC checksums
                corrupted = zf.testzip()
                if corrupted:
                    return False, f"Archive corruption detected in member '{corrupted}'.", {}

                namelist = zf.namelist()

                # 2. Check for suspicious path-traversal members
                for member_name in namelist:
                    norm_name = member_name.replace("\\", "/")
                    if (
                        ".." in member_name
                        or ".." in norm_name
                        or member_name.startswith("/")
                        or member_name.startswith("\\")
                        or (len(member_name) > 1 and member_name[1] == ":")
                        or os.path.isabs(member_name)
                    ):
                        return False, f"Archive contains unsafe path traversal entry: '{member_name}'.", {}

                # 3. Check required members
                if ARCHIVE_MANIFEST_FILENAME not in namelist:
                    return False, f"Invalid backup archive: missing required '{ARCHIVE_MANIFEST_FILENAME}'.", {}
                if ARCHIVE_DATABASE_FILENAME not in namelist:
                    return False, f"Invalid backup archive: missing required '{ARCHIVE_DATABASE_FILENAME}'.", {}

                # 3. Parse manifest
                try:
                    manifest_data = json.loads(zf.read(ARCHIVE_MANIFEST_FILENAME).decode("utf-8"))
                except Exception as e:
                    return False, f"Malformed manifest in backup archive: {e}", {}

                fmt_ver = manifest_data.get("format_version", "1.0.0")
                try:
                    major_ver = int(str(fmt_ver).split(".")[0])
                except Exception:
                    major_ver = 1

                if major_ver > CURRENT_BACKUP_FORMAT_MAJOR:
                    return (
                        False,
                        f"Unsupported backup format version '{fmt_ver}' (maximum supported: {BACKUP_FORMAT_VERSION}).",
                        {},
                    )

                backup_type = manifest_data.get("backup_type", BACKUP_TYPE_FULL)

                # 4. Extract database.db to temporary file and validate SQLite integrity
                with tempfile.TemporaryDirectory() as tmp_dir:
                    extracted_db = os.path.join(tmp_dir, "extracted.db")
                    with open(extracted_db, "wb") as out_f:
                        out_f.write(zf.read(ARCHIVE_DATABASE_FILENAME))

                    db_valid, db_msg, db_counts = DatabaseBackupService.validate_sqlite_database(extracted_db)
                    if not db_valid:
                        return False, f"Embedded database validation failed: {db_msg}", {}

                # 5. Check settings.json if present
                has_settings = ARCHIVE_SETTINGS_FILENAME in namelist
                if has_settings:
                    try:
                        settings_content = json.loads(zf.read(ARCHIVE_SETTINGS_FILENAME).decode("utf-8"))
                        if not isinstance(settings_content, dict):
                            return False, "Archive settings.json is not a valid JSON dictionary.", {}
                    except Exception as e:
                        return False, f"Malformed settings.json in backup archive: {e}", {}

                # Assemble unified metadata
                metadata = dict(db_counts)
                metadata.update({
                    "format_version": fmt_ver,
                    "backup_type": backup_type,
                    "app_name": manifest_data.get("app_name", APP_NAME),
                    "created_at": manifest_data.get("created_at", ""),
                    "description": manifest_data.get("description", ""),
                    "has_settings": has_settings,
                    "file_size_bytes": os.path.getsize(archive_path),
                })

                return True, "Omnix backup archive passed all structural and integrity checks.", metadata

        except zipfile.BadZipFile:
            return False, "File is not a valid zip archive or has a corrupted header.", {}
        except Exception as e:
            return False, f"Failed to validate backup archive: {e}", {}

    @staticmethod
    def export_backup(
        db_manager: DatabaseManager,
        target_path: str,
        overwrite: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Exports a hot atomic snapshot of the active SQLite database to target_path.
        Maintains complete backward compatibility with existing callers.
        """
        abs_target = os.path.abspath(target_path)
        with track_operation("BackupRestore", f"Export database backup to '{os.path.basename(abs_target)}'") as tracker:
            if os.path.exists(abs_target) and not overwrite:
                msg = f"Target file already exists: '{abs_target}'"
                tracker.fail(msg, level="WARNING")
                return False, msg, {}

            os.makedirs(os.path.dirname(abs_target), exist_ok=True)

            try:
                # Perform native atomic backup
                success = db_manager.backup(abs_target)
                if not success:
                    tracker.fail("SQLite native backup operation failed", level="ERROR")
                    return False, "SQLite native backup operation failed.", {}

                # Validate the created snapshot
                is_valid, msg, metadata = DatabaseBackupService.validate_backup_file(abs_target)
                if not is_valid:
                    try:
                        os.remove(abs_target)
                    except Exception:
                        pass
                    tracker.fail(f"Backup failed integrity validation: {msg}", level="ERROR")
                    return False, f"Backup creation failed integrity validation: {msg}", {}

                metadata["backup_path"] = abs_target
                metadata["exported_at"] = datetime.datetime.now().isoformat()
                tracker.complete(f"Database backup exported successfully to '{os.path.basename(abs_target)}'")
                return True, f"Successfully created database backup at '{abs_target}'.", metadata

            except Exception as e:
                err_msg = f"Backup export error: {e}"
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {}

    @staticmethod
    def export_full_backup(
        repo: SqliteInventoryRepository,
        target_path: str,
        settings_mgr: Optional[Any] = None,
        overwrite: bool = False,
        description: str = "",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Creates a complete, portable Omnix Backup Package (.obk / .zip) bundling:
        - Atomic SQLite database snapshot with all entities and relationships.
        - Sanitized user settings (excluding passwords and authentication tokens).
        - Format version and compatibility manifest.
        """
        abs_target = os.path.abspath(target_path)
        with track_operation("BackupRestore", f"Export full backup to '{os.path.basename(abs_target)}'") as tracker:
            if os.path.exists(abs_target) and not overwrite:
                msg = f"Target file already exists: '{abs_target}'"
                tracker.fail(msg, level="WARNING")
                return False, msg, {}

            os.makedirs(os.path.dirname(abs_target), exist_ok=True)

            # If user explicitly specified .db / .sqlite, produce standard SQLite file for compatibility
            ext = os.path.splitext(abs_target)[1].lower()
            if ext in (".db", ".sqlite"):
                return DatabaseBackupService.export_backup(repo.db_manager, abs_target, overwrite=overwrite)

            temp_dir = tempfile.mkdtemp(prefix="omnix_backup_")
            try:
                # 1. Hot snapshot of SQLite database
                temp_db = os.path.join(temp_dir, ARCHIVE_DATABASE_FILENAME)
                success = repo.backup(temp_db)
                if not success:
                    tracker.fail("Failed to create SQLite atomic snapshot", level="ERROR")
                    return False, "Failed to create SQLite database snapshot.", {}

                db_valid, val_msg, db_counts = DatabaseBackupService.validate_sqlite_database(temp_db)
                if not db_valid:
                    tracker.fail(f"Snapshot integrity check failed: {val_msg}", level="ERROR")
                    return False, f"Snapshot integrity check failed: {val_msg}", {}

                # 2. Export sanitized settings (passwords and secrets stripped)
                has_settings = False
                if settings_mgr is not None:
                    raw_settings = getattr(settings_mgr, "settings", {})
                    sanitized_settings = sanitize_settings_for_backup(raw_settings)
                    temp_settings = os.path.join(temp_dir, ARCHIVE_SETTINGS_FILENAME)
                    with open(temp_settings, "w", encoding="utf-8") as sf:
                        json.dump(sanitized_settings, sf, indent=4, ensure_ascii=False)
                    has_settings = True

                # 3. Create manifest.json
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                manifest = {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "backup_type": BACKUP_TYPE_FULL,
                    "app_name": APP_NAME,
                    "app_version": APP_VERSION,
                    "created_at": now_iso,
                    "description": description or "Omnix Full Application Environment Backup",
                    "database": {
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "tables": REQUIRED_TABLES,
                    },
                    "has_settings": has_settings,
                    "entity_counts": {
                        "components": db_counts.get("components", 0),
                        "supplier_links": db_counts.get("supplier_links", 0),
                        "stock_policies": db_counts.get("stock_policies", 0),
                        "ref_manufacturers": db_counts.get("ref_manufacturers", 0),
                        "ref_categories": db_counts.get("ref_categories", 0),
                        "ref_types": db_counts.get("ref_types", 0),
                        "ref_providers": db_counts.get("ref_providers", 0),
                    },
                }

                temp_manifest = os.path.join(temp_dir, ARCHIVE_MANIFEST_FILENAME)
                with open(temp_manifest, "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, indent=4, ensure_ascii=False)

                # 4. Pack into ZIP archive
                with zipfile.ZipFile(abs_target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(temp_manifest, ARCHIVE_MANIFEST_FILENAME)
                    zf.write(temp_db, ARCHIVE_DATABASE_FILENAME)
                    if has_settings:
                        temp_settings = os.path.join(temp_dir, ARCHIVE_SETTINGS_FILENAME)
                        zf.write(temp_settings, ARCHIVE_SETTINGS_FILENAME)

                # 5. Validate the final generated archive
                is_valid, msg, metadata = DatabaseBackupService.validate_backup_file(abs_target)
                if not is_valid:
                    try:
                        os.remove(abs_target)
                    except Exception:
                        pass
                    tracker.fail(f"Generated archive failed validation: {msg}", level="ERROR")
                    return False, f"Backup creation failed integrity validation: {msg}", {}

                metadata["backup_path"] = abs_target
                tracker.complete(f"Full backup exported successfully to '{os.path.basename(abs_target)}'")
                return True, f"Successfully created full backup archive at '{abs_target}'.", metadata

            except Exception as e:
                err_msg = f"Full backup export error: {e}"
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {}
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def export_starter_backup(
        repo: SqliteInventoryRepository,
        target_path: str,
        overwrite: bool = False,
        description: str = "Omnix Starter Baseline Reference Data",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Creates a dedicated Starter Backup archive containing approved baseline reference data:
        - Manufacturers, categories, technology types, and link providers.
        - Zero component records, zero stock policies, zero supplier links, and zero user secrets.
        """
        abs_target = os.path.abspath(target_path)
        with track_operation("BackupRestore", f"Export starter baseline to '{os.path.basename(abs_target)}'") as tracker:
            if os.path.exists(abs_target) and not overwrite:
                msg = f"Target file already exists: '{abs_target}'"
                tracker.fail(msg, level="WARNING")
                return False, msg, {}

            os.makedirs(os.path.dirname(abs_target), exist_ok=True)
            temp_dir = tempfile.mkdtemp(prefix="omnix_starter_")

            try:
                temp_db = os.path.join(temp_dir, ARCHIVE_DATABASE_FILENAME)
                # 1. Initialize clean schema in temp database
                clean_mgr = DatabaseManager(temp_db)
                clean_mgr.initialize_schema()

                # 2. Extract and copy reference records from active repo
                src_conn = repo.db_manager.get_connection()
                dst_conn = clean_mgr.get_connection()

                with dst_conn:
                    # Providers
                    providers = src_conn.execute(
                        "SELECT provider_id, name, norm_name, label, base_url, is_active FROM ref_providers;"
                    ).fetchall()
                    dst_conn.executemany(
                        "INSERT OR IGNORE INTO ref_providers (provider_id, name, norm_name, label, base_url, is_active) VALUES (?, ?, ?, ?, ?, ?);",
                        [tuple(r) for r in providers],
                    )

                    # Categories
                    categories = src_conn.execute(
                        "SELECT id, name, norm_name, is_active FROM ref_categories ORDER BY id;"
                    ).fetchall()
                    dst_conn.executemany(
                        "INSERT OR IGNORE INTO ref_categories (id, name, norm_name, is_active) VALUES (?, ?, ?, ?);",
                        [tuple(r) for r in categories],
                    )

                    # Types
                    types = src_conn.execute(
                        "SELECT id, category_id, name, norm_name, is_active FROM ref_types ORDER BY id;"
                    ).fetchall()
                    dst_conn.executemany(
                        "INSERT OR IGNORE INTO ref_types (id, category_id, name, norm_name, is_active) VALUES (?, ?, ?, ?, ?);",
                        [tuple(r) for r in types],
                    )

                    # Manufacturers
                    mfrs = src_conn.execute(
                        "SELECT name, norm_name, is_active FROM ref_manufacturers ORDER BY id;"
                    ).fetchall()
                    dst_conn.executemany(
                        "INSERT OR IGNORE INTO ref_manufacturers (name, norm_name, is_active) VALUES (?, ?, ?);",
                        [tuple(r) for r in mfrs],
                    )

                clean_mgr.close()

                # 3. Verify clean baseline counts
                db_valid, val_msg, db_counts = DatabaseBackupService.validate_sqlite_database(temp_db)
                if not db_valid:
                    tracker.fail(f"Starter database integrity check failed: {val_msg}", level="ERROR")
                    return False, f"Starter database validation failed: {val_msg}", {}

                # Confirm zero inventory records
                if db_counts.get("components", 0) > 0 or db_counts.get("stock_policies", 0) > 0:
                    tracker.fail("Starter database cannot contain inventory components or stock policies", level="ERROR")
                    return False, "Starter database contains non-baseline inventory records.", {}

                # 4. Manifest
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                manifest = {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "backup_type": BACKUP_TYPE_STARTER,
                    "app_name": APP_NAME,
                    "app_version": APP_VERSION,
                    "created_at": now_iso,
                    "description": description,
                    "database": {
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "tables": REQUIRED_TABLES,
                    },
                    "has_settings": False,
                    "entity_counts": {
                        "components": 0,
                        "supplier_links": 0,
                        "stock_policies": 0,
                        "ref_manufacturers": db_counts.get("ref_manufacturers", 0),
                        "ref_categories": db_counts.get("ref_categories", 0),
                        "ref_types": db_counts.get("ref_types", 0),
                        "ref_providers": db_counts.get("ref_providers", 0),
                    },
                }

                temp_manifest = os.path.join(temp_dir, ARCHIVE_MANIFEST_FILENAME)
                with open(temp_manifest, "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, indent=4, ensure_ascii=False)

                # 5. Pack into archive
                with zipfile.ZipFile(abs_target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(temp_manifest, ARCHIVE_MANIFEST_FILENAME)
                    zf.write(temp_db, ARCHIVE_DATABASE_FILENAME)

                is_valid, msg, metadata = DatabaseBackupService.validate_backup_file(abs_target)
                if not is_valid:
                    try:
                        os.remove(abs_target)
                    except Exception:
                        pass
                    tracker.fail(f"Starter archive failed validation: {msg}", level="ERROR")
                    return False, f"Starter backup creation failed validation: {msg}", {}

                metadata["backup_path"] = abs_target
                tracker.complete(f"Starter baseline exported successfully to '{os.path.basename(abs_target)}'")
                return True, f"Successfully created starter baseline archive at '{abs_target}'.", metadata

            except Exception as e:
                err_msg = f"Starter backup export error: {e}"
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {}
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def restore_backup(
        repo: SqliteInventoryRepository,
        backup_path: str,
        safety_dir: Optional[str] = None,
        settings_mgr: Optional[Any] = None,
        restore_settings: bool = True,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Safely restores a validated backup (.obk / .zip or legacy .db) into the active repository:
        1. Validates backup integrity, manifest, and schema version.
        2. Creates an automatic pre-restore safety snapshot of the active database and settings.
        3. Transactionally replaces the active database using SQLite native backup.
        4. Safely restores sanitized application settings if present and requested.
        5. Deep validates restored database integrity.
        6. Automatically rolls back to safety snapshot if any error occurs.
        """
        abs_backup = os.path.abspath(backup_path)
        with track_operation("BackupRestore", f"Restore backup from '{os.path.basename(abs_backup)}'") as tracker:
            is_valid, val_msg, metadata = DatabaseBackupService.validate_backup_file(abs_backup)
            if not is_valid:
                msg = f"Cannot restore invalid backup: {val_msg}"
                tracker.fail(msg, level="ERROR")
                return False, msg, {}

            current_db_path = repo.file_path
            if not current_db_path or current_db_path == ":memory:":
                msg = "Cannot restore into an in-memory or uninitialized database path."
                tracker.fail(msg, level="ERROR")
                return False, msg, {}

            # 1. Create Pre-Restore Safety Snapshot of Database
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if not safety_dir:
                safety_dir = os.path.join(os.path.dirname(current_db_path), "safety_backups")
            os.makedirs(safety_dir, exist_ok=True)
            safety_db_path = os.path.join(safety_dir, f"pre_restore_safety_{timestamp}.db")

            safety_db_created = False
            if os.path.exists(current_db_path):
                safety_db_created = repo.backup(safety_db_path)
                if not safety_db_created:
                    msg = f"Failed to create pre-restore safety snapshot at '{safety_db_path}'. Restore aborted."
                    tracker.fail(msg, level="ERROR")
                    return False, msg, {}

            # 2. Create Safety Copy of settings.json if present
            safety_settings_path = None
            if settings_mgr is not None and getattr(settings_mgr, "file_path", None) and os.path.exists(settings_mgr.file_path):
                safety_settings_path = os.path.join(safety_dir, f"pre_restore_settings_{timestamp}.json")
                try:
                    shutil.copy2(settings_mgr.file_path, safety_settings_path)
                except Exception:
                    safety_settings_path = None

            temp_dir = None
            backup_conn = None
            target_conn = None
            pending_settings_merge = None

            try:
                # 3. Extract database and stage settings from archive or use raw DB file
                if is_archive_file(abs_backup):
                    temp_dir = tempfile.mkdtemp(prefix="omnix_restore_")
                    with zipfile.ZipFile(abs_backup, "r") as zf:
                        extracted_db = os.path.join(temp_dir, ARCHIVE_DATABASE_FILENAME)
                        with open(extracted_db, "wb") as f_out:
                            f_out.write(zf.read(ARCHIVE_DATABASE_FILENAME))
                        source_db_file = extracted_db

                        # Stage settings merge in memory (applied only after database restore succeeds)
                        if restore_settings and settings_mgr is not None and ARCHIVE_SETTINGS_FILENAME in zf.namelist():
                            try:
                                imported_settings = json.loads(zf.read(ARCHIVE_SETTINGS_FILENAME).decode("utf-8"))
                                current_settings = getattr(settings_mgr, "settings", {})
                                pending_settings_merge = merge_sanitized_settings(current_settings, imported_settings)
                            except Exception as se:
                                log_event("BackupRestore", "WARNING", f"Settings restore staging skipped due to error: {se}")
                else:
                    source_db_file = abs_backup

                # 4. Explicitly close active repository connection before applying backup
                repo.close()

                # Transactionally apply backup into active database
                backup_conn = sqlite3.connect(source_db_file)
                target_conn = sqlite3.connect(current_db_path)

                with target_conn:
                    backup_conn.backup(target_conn)

                target_conn.close()
                target_conn = None
                backup_conn.close()
                backup_conn = None

                # 5. Reload Repository Connection & Schema
                repo.load(current_db_path)

                # 6. Deep Verify Active DB Integrity after Restore
                active_valid, active_msg, active_meta = DatabaseBackupService.validate_sqlite_database(current_db_path)
                if not active_valid:
                    # Rollback to safety snapshots
                    rollback_errors = []
                    if safety_db_created and os.path.exists(safety_db_path):
                        try:
                            repo.close()
                            sb_conn = sqlite3.connect(safety_db_path)
                            tb_conn = sqlite3.connect(current_db_path)
                            with tb_conn:
                                sb_conn.backup(tb_conn)
                            sb_conn.close()
                            tb_conn.close()
                            repo.load(current_db_path)
                        except Exception as r_err:
                            rollback_errors.append(f"database rollback error: {r_err}")

                    if safety_settings_path and os.path.exists(safety_settings_path) and settings_mgr:
                        try:
                            shutil.copy2(safety_settings_path, settings_mgr.file_path)
                            settings_mgr.load()
                        except Exception as s_err:
                            rollback_errors.append(f"settings rollback error: {s_err}")

                    if rollback_errors:
                        msg = (
                            f"Restored database failed integrity check ({active_msg}). "
                            f"Rollback to previous state also failed: {'; '.join(rollback_errors)}"
                        )
                    else:
                        msg = f"Restored database failed integrity check ({active_msg}). Rolled back to safety snapshot."
                    tracker.fail(msg, level="ERROR")
                    return False, msg, {}

                # 7. Apply staged settings now that database restore has succeeded
                if pending_settings_merge is not None and settings_mgr is not None:
                    try:
                        settings_mgr.settings = pending_settings_merge
                        settings_mgr.save()
                        log_event("BackupRestore", "PROGRESS", "Merged application settings from backup package")
                    except Exception as se:
                        log_event("BackupRestore", "WARNING", f"Failed to save restored settings: {se}")

                active_meta["safety_snapshot_path"] = safety_db_path
                active_meta["restored_from"] = abs_backup
                active_meta["backup_type"] = metadata.get("backup_type", BACKUP_TYPE_FULL)
                tracker.complete(f"Database restored successfully from '{os.path.basename(abs_backup)}'")
                return True, f"Successfully restored database from '{abs_backup}'.", active_meta

            except Exception as e:
                # Rollback to safety snapshot on any unexpected exception
                rollback_errors = []
                if safety_db_created and os.path.exists(safety_db_path):
                    try:
                        repo.close()
                        sb_conn = sqlite3.connect(safety_db_path)
                        tb_conn = sqlite3.connect(current_db_path)
                        with tb_conn:
                            sb_conn.backup(tb_conn)
                        sb_conn.close()
                        tb_conn.close()
                        repo.load(current_db_path)
                    except Exception as r_err:
                        rollback_errors.append(f"database rollback error: {r_err}")

                if safety_settings_path and os.path.exists(safety_settings_path) and settings_mgr:
                    try:
                        shutil.copy2(safety_settings_path, settings_mgr.file_path)
                        settings_mgr.load()
                    except Exception as s_err:
                        rollback_errors.append(f"settings rollback error: {s_err}")

                if rollback_errors:
                    err_msg = (
                        f"Error during database restore: {e}. "
                        f"Rollback to previous state also failed: {'; '.join(rollback_errors)}"
                    )
                else:
                    err_msg = f"Error during database restore: {e}. Restored to previous state."
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {}
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
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def apply_starter_backup(
        repo: SqliteInventoryRepository,
        starter_path: Optional[str] = None,
        safety_dir: Optional[str] = None,
        strategy: str = "merge_reference",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Applies approved baseline reference data from a Starter Backup archive:
        - strategy="merge_reference" (Default / Safe): Adds missing reference manufacturers,
          categories, types, and providers into the active database WITHOUT modifying or deleting
          any existing components or stock policies.
        - strategy="clean_reset" (Destructive): Replaces active database with clean starter baseline.
        """
        # Resolve path
        resolved_starter = starter_path or get_default_starter_backup_path()
        if not resolved_starter or not os.path.exists(resolved_starter):
            return False, f"Starter backup archive not found at: '{resolved_starter or 'default locations'}'.", {}

        abs_starter = os.path.abspath(resolved_starter)
        with track_operation("BackupRestore", f"Apply starter baseline ({strategy})") as tracker:
            is_valid, msg, meta = DatabaseBackupService.validate_backup_file(abs_starter)
            if not is_valid:
                tracker.fail(f"Invalid starter backup: {msg}", level="ERROR")
                return False, f"Invalid starter backup: {msg}", {}

            if strategy == "clean_reset":
                # Clean reset is a full restore of the starter baseline
                return DatabaseBackupService.restore_backup(
                    repo=repo,
                    backup_path=abs_starter,
                    safety_dir=safety_dir,
                    restore_settings=False,
                )

            # strategy == "merge_reference": Non-destructive insertion of baseline reference records
            temp_dir = None
            try:
                if is_archive_file(abs_starter):
                    temp_dir = tempfile.mkdtemp(prefix="omnix_starter_merge_")
                    with zipfile.ZipFile(abs_starter, "r") as zf:
                        extracted_db = os.path.join(temp_dir, ARCHIVE_DATABASE_FILENAME)
                        with open(extracted_db, "wb") as f_out:
                            f_out.write(zf.read(ARCHIVE_DATABASE_FILENAME))
                        source_db = extracted_db
                else:
                    source_db = abs_starter

                src_conn = sqlite3.connect(f"file:{os.path.abspath(source_db)}?mode=ro", uri=True)
                src_conn.row_factory = sqlite3.Row

                active_conn = repo.db_manager.get_connection()
                added_mfrs = 0
                added_cats = 0
                added_types = 0
                added_provs = 0

                with repo.db_manager.transaction():
                    # 1. Merge Providers
                    providers = src_conn.execute(
                        "SELECT provider_id, name, norm_name, label, base_url, is_active FROM ref_providers;"
                    ).fetchall()
                    for p in providers:
                        cursor = active_conn.execute(
                            "INSERT OR IGNORE INTO ref_providers (provider_id, name, norm_name, label, base_url, is_active) VALUES (?, ?, ?, ?, ?, ?);",
                            (p["provider_id"], p["name"], p["norm_name"], p["label"], p["base_url"], p["is_active"]),
                        )
                        if cursor.rowcount > 0:
                            added_provs += 1

                    # 2. Merge Categories
                    categories = src_conn.execute(
                        "SELECT name, norm_name, is_active FROM ref_categories ORDER BY id;"
                    ).fetchall()
                    for c in categories:
                        cursor = active_conn.execute(
                            "INSERT OR IGNORE INTO ref_categories (name, norm_name, is_active) VALUES (?, ?, ?);",
                            (c["name"], c["norm_name"], c["is_active"]),
                        )
                        if cursor.rowcount > 0:
                            added_cats += 1

                    # Map active category norm_name -> id
                    cat_map = {
                        r[1]: r[0] for r in active_conn.execute(
                            "SELECT id, norm_name FROM ref_categories;"
                        ).fetchall()
                    }

                    # 3. Merge Types (mapped to active category IDs by norm_name)
                    types = src_conn.execute("""
                        SELECT t.name, t.norm_name, t.is_active, c.norm_name as cat_norm
                        FROM ref_types t
                        JOIN ref_categories c ON c.id = t.category_id
                        ORDER BY t.id;
                    """).fetchall()

                    for t in types:
                        cat_id = cat_map.get(t["cat_norm"])
                        if cat_id:
                            cursor = active_conn.execute(
                                "INSERT OR IGNORE INTO ref_types (category_id, name, norm_name, is_active) VALUES (?, ?, ?, ?);",
                                (cat_id, t["name"], t["norm_name"], t["is_active"]),
                            )
                            if cursor.rowcount > 0:
                                added_types += 1

                    # 4. Merge Manufacturers
                    mfrs = src_conn.execute(
                        "SELECT name, norm_name, is_active FROM ref_manufacturers ORDER BY id;"
                    ).fetchall()
                    for m in mfrs:
                        cursor = active_conn.execute(
                            "INSERT OR IGNORE INTO ref_manufacturers (name, norm_name, is_active) VALUES (?, ?, ?);",
                            (m["name"], m["norm_name"], m["is_active"]),
                        )
                        if cursor.rowcount > 0:
                            added_mfrs += 1

                src_conn.close()

                result_meta = {
                    "added_manufacturers": added_mfrs,
                    "added_categories": added_cats,
                    "added_types": added_types,
                    "added_providers": added_provs,
                    "strategy": strategy,
                    "starter_source": abs_starter,
                }

                tracker.complete(
                    f"Starter baseline merged successfully: +{added_mfrs} mfrs, +{added_cats} categories, +{added_types} types, +{added_provs} providers"
                )
                return True, "Starter baseline reference data merged successfully.", result_meta

            except Exception as e:
                err_msg = f"Failed to merge starter baseline: {e}"
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {}
            finally:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
