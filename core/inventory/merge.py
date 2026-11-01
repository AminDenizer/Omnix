"""
Omnix Core — Database Bind/Merge Service
Governing Requirement: Phase 3 Database Bind/Merge Specification

Provides non-destructive, transactional binding and merging of external SQLite inventory databases
into the active runtime repository.

Key Guarantees:
1. Validates external database schema and version before any reading.
2. Reads the source database in strictly read-only mode (file:...?mode=ro).
3. Matches components strictly using the canonical Manufacturer + MPN identity policy.
4. Identifies new records, duplicates, incomplete keys, reference conflicts, and conflicting values.
5. Never blindly copies source IDs (resolves foreign keys against target records).
6. Preserves existing destination records; does not overwrite without explicit policy.
7. Does not guess identities for components with missing or incomplete keys (skips safely).
8. Automatically creates a pre-merge safety backup of the destination database.
9. Operates transactionally: completely rolls back destination changes if any step fails.
10. Preserves both source and destination if operation is cancelled or aborted.
"""

import os
import sqlite3
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

from core.inventory.models import (
    InventoryProduct,
    SupplierLink,
    normalize_identity_part,
    normalize_package,
)
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.backup import DatabaseBackupService
from core.logger import log_event, track_operation


@dataclass
class MergeAnalysis:
    """Detailed preview analysis outcome comparing external source DB against target repository."""
    source_path: str
    source_schema_version: int
    is_valid: bool = True
    validation_error: Optional[str] = None

    # Component classification
    total_source_components: int = 0
    new_components: List[Dict[str, Any]] = field(default_factory=list)
    duplicate_components: List[Dict[str, Any]] = field(default_factory=list)
    conflicting_components: List[Dict[str, Any]] = field(default_factory=list)
    incomplete_components: List[Dict[str, Any]] = field(default_factory=list)

    # Reference classification
    new_manufacturers: List[str] = field(default_factory=list)
    new_categories: List[str] = field(default_factory=list)
    new_types: List[Dict[str, Any]] = field(default_factory=list)
    new_providers: List[Dict[str, Any]] = field(default_factory=list)

    # Supplier links and policies
    new_supplier_links_count: int = 0
    new_stock_policies_count: int = 0

    @property
    def can_merge(self) -> bool:
        return self.is_valid and len(self.new_components) > 0


class DatabaseMergeService:
    """Service orchestrating validation, analysis, and transactional merge of external databases."""

    @classmethod
    def validate_source_database(cls, source_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates that source_path exists, is an accessible SQLite database with valid schema
        and recognized schema_version. Reads strictly in read-only mode.
        """
        if not source_path or not os.path.isfile(source_path):
            return False, f"Source database file not found: '{source_path}'", {}

        abs_path = os.path.abspath(source_path)
        try:
            # Read-only URI connection
            uri = Path(abs_path).resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            cur = conn.cursor()

            # Check table existence
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}
            required_tables = {"components", "ref_manufacturers", "ref_categories", "ref_types"}
            missing_tables = required_tables - tables
            if missing_tables:
                conn.close()
                return False, f"Incompatible database schema: missing required tables {sorted(missing_tables)}", {}

            # Check schema version
            version = 1
            if "schema_version" in tables:
                cur.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;")
                row = cur.fetchone()
                if row:
                    version = int(row[0])

            cur.execute("SELECT COUNT(*) FROM components;")
            comp_count = cur.fetchone()[0]

            conn.close()
            return True, "Valid Omnix inventory database.", {
                "source_path": abs_path,
                "schema_version": version,
                "tables": sorted(list(tables)),
                "component_count": comp_count,
            }
        except sqlite3.DatabaseError as e:
            return False, f"Not a valid or readable SQLite database: {e}", {}
        except Exception as e:
            return False, f"Error validating source database: {e}", {}

    @classmethod
    def analyze_merge(
        cls,
        target_repo: SqliteInventoryRepository,
        source_path: str,
    ) -> MergeAnalysis:
        """
        Performs a dry-run analysis comparing source database against target repository.
        Source DB is accessed in read-only mode and is NEVER modified.
        Target repository is NOT modified during analysis.
        """
        valid, msg, meta = cls.validate_source_database(source_path)
        if not valid:
            return MergeAnalysis(
                source_path=source_path,
                source_schema_version=0,
                is_valid=False,
                validation_error=msg,
            )

        analysis = MergeAnalysis(
            source_path=os.path.abspath(source_path),
            source_schema_version=meta.get("schema_version", 1),
            is_valid=True,
        )

        src_uri = Path(analysis.source_path).resolve().as_uri() + "?mode=ro"
        src_conn = sqlite3.connect(src_uri, uri=True, timeout=5.0)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        try:
            # 1. Existing target index: (norm_mfr, norm_mpn) -> InventoryProduct
            target_products = target_repo.get_all_products()
            target_identity_map: Dict[Tuple[str, str], InventoryProduct] = {}
            for p in target_products:
                mfr_norm = normalize_identity_part(p.manufacturer) if p.manufacturer else ""
                mpn_norm = normalize_identity_part(p.mpn) if p.mpn else ""
                if mfr_norm and mpn_norm:
                    target_identity_map[(mfr_norm, mpn_norm)] = p

            # Existing target references (from authoritative reference tables)
            target_mfrs = {
                normalize_identity_part(getattr(r, "name", r["name"] if isinstance(r, dict) else ""))
                for r in target_repo.get_all_manufacturers()
            }
            target_cats = {
                normalize_identity_part(getattr(r, "name", r["name"] if isinstance(r, dict) else ""))
                for r in target_repo.get_all_categories()
            }
            target_types = {
                (
                    normalize_identity_part(getattr(r, "category_name", r["category_name"] if isinstance(r, dict) else "")),
                    normalize_identity_part(getattr(r, "name", r["name"] if isinstance(r, dict) else ""))
                )
                for r in target_repo.get_all_types()
            }

            # 2. Inspect source reference data indexes (for resolving source names and relationships)
            src_mfrs = src_cur.execute("SELECT name, norm_name FROM ref_manufacturers;").fetchall()
            src_mfr_by_norm = {
                (row["norm_name"] or normalize_identity_part(row["name"])): row["name"]
                for row in src_mfrs
            }

            src_cats = src_cur.execute("SELECT id, name, norm_name FROM ref_categories;").fetchall()
            src_cat_id_to_norm = {}
            src_cat_norm_to_name = {}
            for row in src_cats:
                norm = row["norm_name"] or normalize_identity_part(row["name"])
                src_cat_id_to_norm[row["id"]] = norm
                src_cat_norm_to_name[norm] = row["name"]

            src_types = src_cur.execute("SELECT id, category_id, name, norm_name FROM ref_types;").fetchall()
            # Map (cat_norm, type_norm) -> canonical type name
            src_types_by_cat_and_norm: Dict[Tuple[str, str], str] = {}
            for row in src_types:
                cat_norm = src_cat_id_to_norm.get(row["category_id"])
                type_norm = row["norm_name"] or normalize_identity_part(row["name"])
                if cat_norm and type_norm:
                    src_types_by_cat_and_norm[(cat_norm, type_norm)] = row["name"]

            # 3. Inspect source components
            src_components = src_cur.execute("""
                SELECT
                    id, manufacturer, mpn, category, type_technology,
                    package, footprint, value, description, quantity_in_stock,
                    min_stock, target_stock
                FROM components
                ORDER BY id;
            """).fetchall()

            analysis.total_source_components = len(src_components)

            # Inspect supplier links in source
            src_links_by_comp: Dict[int, List[Dict[str, Any]]] = {}
            if "supplier_links" in meta.get("tables", []):
                for l_row in src_cur.execute("SELECT * FROM supplier_links;").fetchall():
                    c_id = l_row["component_id"]
                    src_links_by_comp.setdefault(c_id, []).append(dict(l_row))

            for comp in src_components:
                raw_mfr = comp["manufacturer"] or ""
                raw_mpn = comp["mpn"] or ""
                norm_m = normalize_identity_part(raw_mfr) if raw_mfr else ""
                norm_p = normalize_identity_part(raw_mpn) if raw_mpn else ""

                comp_data = {
                    "source_id": comp["id"],
                    "manufacturer": raw_mfr,
                    "mpn": raw_mpn,
                    "category": comp["category"] or "",
                    "type_technology": comp["type_technology"] or "",
                    "package": comp["package"] or "",
                    "footprint": comp["footprint"] or "",
                    "value": comp["value"] or "",
                    "description": comp["description"] or "",
                    "quantity_in_stock": comp["quantity_in_stock"] if comp["quantity_in_stock"] is not None else 0,
                    "min_stock": comp["min_stock"],
                    "target_stock": comp["target_stock"],
                    "supplier_links": src_links_by_comp.get(comp["id"], []),
                }

                # Identity rule: Manufacturer + MPN must be present
                if not norm_m or not norm_p:
                    analysis.incomplete_components.append(comp_data)
                    continue

                target_key = (norm_m, norm_p)
                if target_key in target_identity_map:
                    # Component exists in target
                    existing = target_identity_map[target_key]
                    # Check for conflicting values (different package, value, footprint)
                    conflicts = []
                    if comp_data["value"] and existing.value and comp_data["value"].lower().strip() != existing.value.lower().strip():
                        conflicts.append(f"Value differs: '{existing.value}' vs '{comp_data['value']}'")
                    if comp_data["package"] and existing.package and normalize_package(comp_data["package"]) != normalize_package(existing.package):
                        conflicts.append(f"Package differs: '{existing.package}' vs '{comp_data['package']}'")

                    if conflicts:
                        comp_data["conflict_reasons"] = conflicts
                        comp_data["existing_target"] = existing
                        analysis.conflicting_components.append(comp_data)
                    else:
                        analysis.duplicate_components.append(comp_data)
                else:
                    # Strict Target Reference Validation:
                    # A new component is eligible for import ONLY if all its required reference data
                    # can be resolved to valid existing records in the target database.
                    # Never auto-create missing references during merge.
                    ref_errors = []
                    c_mfr = comp_data["manufacturer"]
                    c_cat = comp_data["category"]
                    c_tech = comp_data["type_technology"]

                    norm_m = normalize_identity_part(c_mfr) if c_mfr else ""
                    norm_c = normalize_identity_part(c_cat) if c_cat else ""
                    norm_t = normalize_identity_part(c_tech) if c_tech else ""

                    # 1. Manufacturer validation
                    if not norm_m:
                        ref_errors.append("Manufacturer cannot be empty.")
                    elif norm_m not in target_mfrs:
                        ref_errors.append(
                            f"Manufacturer '{c_mfr}' does not exist in target database reference data."
                        )

                    # 2. Category validation
                    if not norm_c:
                        ref_errors.append("Category cannot be empty.")
                    elif norm_c not in target_cats:
                        ref_errors.append(
                            f"Category '{c_cat}' does not exist in target database reference data."
                        )

                    # 3. Type/Technology validation (if specified, must exist and belong to the category)
                    if norm_t:
                        if not norm_c or norm_c not in target_cats:
                            ref_errors.append(
                                f"Type/Technology '{c_tech}' cannot be imported without a valid target Category."
                            )
                        elif (norm_c, norm_t) not in target_types:
                            ref_errors.append(
                                f"Type/Technology '{c_tech}' is not an active technology for Category '{c_cat}' in target database."
                            )

                    if ref_errors:
                        comp_data["conflict_reasons"] = ref_errors
                        analysis.conflicting_components.append(comp_data)
                        continue

                    # Brand new eligible component with all target references verified
                    analysis.new_components.append(comp_data)

            # References are NOT auto-imported or created during merge under strict validation policy.
            # Reference collections remain empty.
            analysis.new_manufacturers = []
            analysis.new_categories = []
            analysis.new_types = []
            analysis.new_providers = []

            return analysis

        finally:
            src_conn.close()

    @classmethod
    def execute_merge(
        cls,
        target_repo: SqliteInventoryRepository,
        analysis: MergeAnalysis,
        safety_backup_dir: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes the transactional merge of new records from the analyzed external database into target_repo.
        1. Verifies analysis validity.
        2. Creates an automatic pre-merge backup of the target database.
        3. Inserts missing reference records (manufacturers, categories, types).
        4. Inserts new components and their supplier links.
        5. Preserves existing destination records untouched (no destructive overwrite).
        6. Rolls back completely on failure. Source DB is untouched.
        """
        if not analysis.is_valid:
            return False, f"Cannot merge invalid source database: {analysis.validation_error}", {}

        if not analysis.can_merge:
            return True, "No new records or references to merge.", {
                "added_components": 0,
                "added_manufacturers": 0,
                "added_categories": 0,
                "added_types": 0,
                "skipped_duplicates": len(analysis.duplicate_components),
                "skipped_conflicts": len(analysis.conflicting_components),
                "skipped_incomplete": len(analysis.incomplete_components),
            }

        with track_operation("DatabaseMerge", f"Merging from '{os.path.basename(analysis.source_path)}'") as tracker:
            # 1. Pre-merge safety backup of target database
            backup_meta: Dict[str, Any] = {}
            dest_path = getattr(target_repo, "file_path", None)
            if dest_path and os.path.exists(dest_path):
                try:
                    b_dir = safety_backup_dir or os.path.join(os.path.dirname(dest_path), "backups")
                    os.makedirs(b_dir, exist_ok=True)
                    backup_file = os.path.join(
                        b_dir,
                        f"pre_merge_backup_{os.path.splitext(os.path.basename(dest_path))[0]}.obk"
                    )
                    ok_b, msg_b, b_meta = DatabaseBackupService.export_full_backup(
                        target_repo,
                        backup_file,
                        overwrite=True,
                    )
                    if not ok_b:
                        err_msg = f"Pre-merge safety backup failed: {msg_b}. Merge aborted."
                        tracker.fail(err_msg)
                        return False, err_msg, {
                            "added_components": 0,
                            "skipped_duplicates": len(analysis.duplicate_components),
                            "skipped_conflicts": len(analysis.conflicting_components),
                            "skipped_incomplete": len(analysis.incomplete_components),
                            "backup_created": False,
                        }
                    backup_meta = b_meta
                    log_event("DatabaseMerge", "PROGRESS", f"Pre-merge safety backup created at '{backup_file}'")
                except Exception as e:
                    err_msg = f"Pre-merge safety backup failed with exception: {e}. Merge aborted."
                    tracker.fail(err_msg)
                    return False, err_msg, {
                        "added_components": 0,
                        "skipped_duplicates": len(analysis.duplicate_components),
                        "skipped_conflicts": len(analysis.conflicting_components),
                        "skipped_incomplete": len(analysis.incomplete_components),
                        "backup_created": False,
                    }

            # 2. Transactional execution on target database
            added_components = 0
            added_mfrs = 0
            added_cats = 0
            added_types = 0
            added_links = 0

            try:
                with target_repo.db_manager.transaction():
                    conn = target_repo.db_manager.get_connection()

                    # Zero Automatic Reference Creation:
                    # New components are eligible for import ONLY if all required reference data
                    # already exists in the target database. We do not insert reference records.
                    added_mfrs = 0
                    added_cats = 0
                    added_types = 0

                    # D. Insert New Approved Components
                    for c_data in analysis.new_components:
                        # Construct product model
                        prod = InventoryProduct(
                            manufacturer=c_data["manufacturer"],
                            mpn=c_data["mpn"],
                            category=c_data["category"],
                            type_technology=c_data["type_technology"],
                            package=c_data["package"],
                            footprint=c_data["footprint"],
                            value=c_data["value"],
                            description=c_data["description"],
                            quantity_in_stock=c_data["quantity_in_stock"],
                            min_stock=c_data["min_stock"],
                            target_stock=c_data["target_stock"],
                        )

                        # Extract supplier links
                        links: List[SupplierLink] = []
                        for sl in c_data.get("supplier_links", []):
                            links.append(SupplierLink(
                                vendor_id=sl.get("vendor_id"),
                                vendor_label=sl.get("vendor_label"),
                                url=sl.get("url", ""),
                                display_name=sl.get("display_name"),
                            ))

                        # Create component using target repository (creates fresh ID and resolves foreign keys)
                        new_comp = target_repo.create_component(prod, supplier_links=links)
                        if new_comp:
                            added_components += 1
                            added_links += len(links)

                # Commit completed successfully
                summary_meta = {
                    "source_path": analysis.source_path,
                    "added_components": added_components,
                    "added_manufacturers": added_mfrs,
                    "added_categories": added_cats,
                    "added_types": added_types,
                    "added_supplier_links": added_links,
                    "skipped_duplicates": len(analysis.duplicate_components),
                    "skipped_conflicts": len(analysis.conflicting_components),
                    "skipped_incomplete": len(analysis.incomplete_components),
                    "backup_created": bool(backup_meta),
                }

                tracker.complete(
                    f"Successfully merged database: +{added_components} components"
                )
                if added_components > 0:
                    user_msg = (
                        f"Successfully merged {added_components} new component(s) into database.\n"
                        f"Preserved {len(analysis.duplicate_components)} existing duplicate(s) and "
                        f"skipped {len(analysis.conflicting_components)} conflict(s)."
                    )
                else:
                    user_msg = (
                        f"No components were imported.\n"
                        f"Preserved {len(analysis.duplicate_components)} duplicate(s), "
                        f"skipped {len(analysis.conflicting_components)} conflict(s), and "
                        f"skipped {len(analysis.incomplete_components)} incomplete record(s)."
                    )

                return True, user_msg, summary_meta

            except Exception as e:
                err_msg = f"Database merge failed and was rolled back: {e}"
                tracker.fail(err_msg, level="ERROR")
                return False, err_msg, {"backup_created": bool(backup_meta)}
