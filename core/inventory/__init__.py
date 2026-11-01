"""
Omnix Core - Inventory Package
"""

from core.inventory.models import (
    InventoryProduct,
    StockPolicyGroup,
    SupplierLink,
    StockPolicyRecord,
    ManufacturerRecord,
    CategoryRecord,
    TypeRecord,
    normalize_package,
    build_group_key,
    normalize_identity_part,
    clean_display_string,
    format_supplier_links_as_string,
    InventoryDatabaseError,
    ComponentConflictError,
    ComponentNotFoundError,
    ReferenceDataInUseError,
    ReferenceDataNotFoundError,
    DuplicateReferenceError,
    ValidationError,
)
from core.inventory.database import (
    DatabaseManager,
    resolve_database_path,
)
from core.inventory.loader import (
    InventoryDatabaseLoader,
    resolve_inventory_database_path,
    InventoryError,
    MissingWorksheetError,
    WorkbookAccessError,
)
from core.inventory.repository import (
    IInventoryRepository,
    ExcelInventoryRepository,
    SqliteInventoryRepository,
)
from core.inventory.updater import (
    StockPolicyWriter,
    StockPolicyUpdateError,
    WorkbookLockedError,
)
from core.inventory.bootstrap import (
    BootstrapResult,
    ExcelDatabaseMigrator,
    bootstrap_sqlite_from_workbook,
)
from core.inventory.exporter import InventoryExcelExporter
from core.inventory.merge import DatabaseMergeService, MergeAnalysis

__all__ = [
    "InventoryProduct",
    "StockPolicyGroup",
    "SupplierLink",
    "StockPolicyRecord",
    "ManufacturerRecord",
    "CategoryRecord",
    "TypeRecord",
    "normalize_package",
    "build_group_key",
    "normalize_identity_part",
    "clean_display_string",
    "format_supplier_links_as_string",
    "InventoryDatabaseError",
    "ComponentConflictError",
    "ComponentNotFoundError",
    "ReferenceDataInUseError",
    "ReferenceDataNotFoundError",
    "DuplicateReferenceError",
    "ValidationError",
    "DatabaseManager",
    "resolve_database_path",
    "InventoryDatabaseLoader",
    "resolve_inventory_database_path",
    "InventoryError",
    "MissingWorksheetError",
    "WorkbookAccessError",
    "IInventoryRepository",
    "ExcelInventoryRepository",
    "SqliteInventoryRepository",
    "StockPolicyWriter",
    "StockPolicyUpdateError",
    "WorkbookLockedError",
    "BootstrapResult",
    "ExcelDatabaseMigrator",
    "bootstrap_sqlite_from_workbook",
    "InventoryExcelExporter",
    "DatabaseMergeService",
    "MergeAnalysis",
]

