"""
Omnix Core - Inventory SQLite Database Bootstrap & Migration Utility
Governing Document: Phase 2.1 Implementation Specification

Provides safe, strictly read-only import of Excel inventory workbooks
(such as Inventory-test.xlsm or user workbooks) into the authoritative
SQLite inventory database.

Guarantees:
- Strictly read-only workbook access (data_only=True, read_only=True).
- NEVER writes to or mutates the source Excel workbook.
- Seeds canonical reference data (manufacturers, categories, types).
- Enforces normalized identity uniqueness while preserving original display text.
- Preserves package leading zeros (e.g. 603 -> '0603').
- Parses and preserves multi-vendor supplier links.
- Recalculates five-dimension group keys consistently.
- Preserves stock policy thresholds (Min Stock, Target Stock, Description).
- Never executes automatically unannounced on application startup.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import os

from core.inventory.models import (
    InventoryProduct,
    StockPolicyGroup,
    SupplierLink,
    clean_display_string,
    ComponentConflictError,
)
from core.inventory.loader import (
    InventoryDatabaseLoader,
    WorkbookAccessError,
    MissingWorksheetError,
)
from core.inventory.repository import SqliteInventoryRepository
from core.procurement.vendor_links import parse_vendor_links


@dataclass
class BootstrapResult:
    """Outcome and metrics of a workbook-to-SQLite bootstrap migration."""
    success: bool
    message: str
    workbook_path: str
    manufacturers_imported: int = 0
    categories_imported: int = 0
    types_imported: int = 0
    components_imported: int = 0
    policies_imported: int = 0
    warnings: List[str] = field(default_factory=list)


class ExcelDatabaseMigrator:
    """
    Non-destructive migrator that imports data from an Excel inventory workbook
    into a SqliteInventoryRepository instance.
    """

    def __init__(self, loader: Optional[InventoryDatabaseLoader] = None):
        self.loader = loader or InventoryDatabaseLoader()

    def bootstrap(
        self,
        workbook_path: str,
        sqlite_repo: SqliteInventoryRepository,
        dry_run: bool = False,
    ) -> BootstrapResult:
        """
        Executes a safe, non-destructive import of workbook data into the target SQLite repository.

        Args:
            workbook_path: Path to the .xlsm or .xlsx source workbook.
            sqlite_repo: Target SqliteInventoryRepository instance.
            dry_run: If True, parses and validates without committing changes to SQLite.

        Returns:
            BootstrapResult with counts and warning messages.
        """
        if not os.path.exists(workbook_path):
            return BootstrapResult(
                success=False,
                message=f"Workbook file not found at: {workbook_path}",
                workbook_path=workbook_path,
            )

        try:
            # 1. Strictly read-only parse of workbook
            groups, products, parse_warnings = self.loader.load_workbook(workbook_path)
            ref_data = self.loader.load_reference_data(workbook_path)
        except (WorkbookAccessError, MissingWorksheetError) as e:
            return BootstrapResult(
                success=False,
                message=f"Failed to read workbook: {e}",
                workbook_path=workbook_path,
            )
        except Exception as e:
            return BootstrapResult(
                success=False,
                message=f"Unexpected error parsing workbook: {e}",
                workbook_path=workbook_path,
            )

        all_warnings: List[str] = list(parse_warnings)

        if dry_run:
            return BootstrapResult(
                success=True,
                message=(
                    f"Dry run succeeded: found {len(products)} components, {len(groups)} policy groups, "
                    f"{len(ref_data.manufacturers)} manufacturers, {len(ref_data.categories)} categories."
                ),
                workbook_path=workbook_path,
                manufacturers_imported=len(ref_data.manufacturers),
                categories_imported=len(ref_data.categories),
                types_imported=len(ref_data.category_types),
                components_imported=len(products),
                policies_imported=len(groups),
                warnings=all_warnings,
            )

        mfr_count = 0
        cat_count = 0
        type_count = 0
        comp_count = 0
        pol_count = 0

        # Cache category name -> id to minimize database lookups
        cat_cache: Dict[str, int] = {}

        # 2a. Seed Canonical Reference Data from 'Reference Data' worksheet
        for mfr in ref_data.manufacturers:
            mfr_name = clean_display_string(mfr)
            if mfr_name and not sqlite_repo.get_manufacturer_by_name(mfr_name):
                try:
                    sqlite_repo.add_manufacturer(mfr_name)
                    mfr_count += 1
                except Exception as e:
                    all_warnings.append(f"Failed to add reference manufacturer '{mfr_name}': {e}")

        for cat in ref_data.categories:
            cat_name = clean_display_string(cat)
            if cat_name and cat_name not in cat_cache:
                cat_rec = sqlite_repo.get_category_by_name(cat_name)
                if cat_rec:
                    cat_cache[cat_name] = cat_rec.id
                else:
                    try:
                        cat_id = sqlite_repo.add_category(cat_name)
                        cat_cache[cat_name] = cat_id
                        cat_count += 1
                    except Exception as e:
                        all_warnings.append(f"Failed to add reference category '{cat_name}': {e}")

        for cat_name, tech_name in ref_data.category_types:
            clean_c = clean_display_string(cat_name)
            clean_t = clean_display_string(tech_name)
            cat_id = cat_cache.get(clean_c)
            if cat_id is None:
                cat_rec = sqlite_repo.get_category_by_name(clean_c)
                if cat_rec:
                    cat_id = cat_rec.id
                    cat_cache[clean_c] = cat_id
            if cat_id is not None and clean_t:
                if not sqlite_repo.validate_category_type(clean_c, clean_t):
                    try:
                        sqlite_repo.add_type(category_id=cat_id, name=clean_t)
                        type_count += 1
                    except Exception as e:
                        all_warnings.append(f"Failed to add reference type '{clean_t}' for category '{clean_c}': {e}")

        # 2a-ii. Ensure foundational Transistor category and verified technologies
        sqlite_repo.ensure_transistor_reference_data()

        # 2b. Seed any additional Manufacturers, Categories, and Types from products/groups
        for p in products:
            # Manufacturer
            mfr_name = clean_display_string(p.manufacturer)
            if mfr_name and not sqlite_repo.get_manufacturer_by_name(mfr_name):
                try:
                    sqlite_repo.add_manufacturer(mfr_name)
                    mfr_count += 1
                except Exception as e:
                    all_warnings.append(f"Failed to add manufacturer '{mfr_name}': {e}")

            # Category
            cat_name = clean_display_string(p.category)
            if cat_name:
                if cat_name not in cat_cache:
                    cat_rec = sqlite_repo.get_category_by_name(cat_name)
                    if cat_rec:
                        cat_cache[cat_name] = cat_rec.id
                    else:
                        try:
                            cat_id = sqlite_repo.add_category(cat_name)
                            cat_cache[cat_name] = cat_id
                            cat_count += 1
                        except Exception as e:
                            all_warnings.append(f"Failed to add category '{cat_name}': {e}")
                            continue

                # Type / Technology
                tech_name = clean_display_string(p.type_technology)
                cat_id = cat_cache.get(cat_name)
                if tech_name and cat_id is not None:
                    if not sqlite_repo.validate_category_type(cat_name, tech_name):
                        try:
                            sqlite_repo.add_type(category_id=cat_id, name=tech_name)
                            type_count += 1
                        except Exception as e:
                            all_warnings.append(f"Failed to add type '{tech_name}' for category '{cat_name}': {e}")

        # Also seed categories and types present in policy-only groups
        for g in groups:
            cat_name = clean_display_string(g.category)
            if cat_name and cat_name not in cat_cache:
                cat_rec = sqlite_repo.get_category_by_name(cat_name)
                if cat_rec:
                    cat_cache[cat_name] = cat_rec.id
                else:
                    try:
                        cat_id = sqlite_repo.add_category(cat_name)
                        cat_cache[cat_name] = cat_id
                        cat_count += 1
                    except Exception:
                        continue

            tech_name = clean_display_string(g.type_technology)
            cat_id = cat_cache.get(cat_name)
            if tech_name and cat_id is not None:
                if not sqlite_repo.validate_category_type(cat_name, tech_name):
                    try:
                        sqlite_repo.add_type(category_id=cat_id, name=tech_name)
                        type_count += 1
                    except Exception:
                        pass

        # 3. Import Physical Components & Supplier Links
        for p in products:
            supplier_links: List[SupplierLink] = []
            if p.purchase_link:
                try:
                    res = parse_vendor_links(p.purchase_link)
                    if res.is_valid and res.links:
                        for entry in res.links.values():
                            supplier_links.append(
                                SupplierLink(
                                    vendor_id=entry.vendor_id,
                                    vendor_label=entry.vendor_label,
                                    url=entry.url,
                                    display_name=entry.display_name,
                                )
                            )
                    elif not res.is_valid:
                        all_warnings.append(
                            f"Component '{p.manufacturer} {p.mpn}': Malformed purchase link '{p.purchase_link}': {res.error_message}"
                        )
                except Exception as e:
                    all_warnings.append(f"Component '{p.manufacturer} {p.mpn}': Error parsing link: {e}")

            # Check if component already exists
            existing = sqlite_repo.get_component_by_identity(p.manufacturer, p.mpn)
            if existing is not None:
                all_warnings.append(
                    f"Skipped duplicate component: Manufacturer '{p.manufacturer}', MPN '{p.mpn}' already exists."
                )
                continue

            try:
                sqlite_repo.create_component(p, supplier_links=supplier_links)
                comp_count += 1
            except ComponentConflictError as e:
                all_warnings.append(f"Component conflict for '{p.manufacturer} {p.mpn}': {e}")
            except Exception as e:
                all_warnings.append(f"Failed to create component '{p.manufacturer} {p.mpn}': {e}")

        # 4. Import Stock Policies
        for g in groups:
            # Policy-only or component groups with threshold settings
            if g.min_stock is not None or g.target_stock is not None or g.description:
                if sqlite_repo.get_policy(g.group_key) is not None:
                    all_warnings.append(
                        f"Preserved existing stock policy for group '{g.group_key}'."
                    )
                    continue
                try:
                    sqlite_repo.set_policy(
                        group_key=g.group_key,
                        min_stock=g.min_stock,
                        target_stock=g.target_stock,
                        category=g.category,
                        type_technology=g.type_technology,
                        value=g.value,
                        package=g.package,
                        footprint=g.footprint,
                        description=g.description,
                    )
                    pol_count += 1
                except Exception as e:
                    all_warnings.append(f"Failed to set policy for group '{g.group_key}': {e}")

        # 5. Reconcile existing component records with canonical reference data
        try:
            reconciled = sqlite_repo.reconcile_canonical_classifications()
            if reconciled > 0:
                all_warnings.append(f"Reconciled {reconciled} component record(s) with canonical reference data.")
        except Exception as e:
            all_warnings.append(f"Warning during classification reconciliation: {e}")

        return BootstrapResult(
            success=True,
            message=(
                f"Successfully bootstrapped SQLite database from '{os.path.basename(workbook_path)}': "
                f"{comp_count} components, {pol_count} stock policies, {mfr_count} manufacturers, "
                f"{cat_count} categories, {type_count} technologies."
            ),
            workbook_path=workbook_path,
            manufacturers_imported=mfr_count,
            categories_imported=cat_count,
            types_imported=type_count,
            components_imported=comp_count,
            policies_imported=pol_count,
            warnings=all_warnings,
        )


def bootstrap_sqlite_from_workbook(
    workbook_path: str,
    sqlite_repo: SqliteInventoryRepository,
    dry_run: bool = False,
) -> BootstrapResult:
    """Convenience helper to bootstrap an existing SQLite repository from an Excel workbook."""
    migrator = ExcelDatabaseMigrator()
    return migrator.bootstrap(workbook_path, sqlite_repo, dry_run=dry_run)
