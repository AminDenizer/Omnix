"""
Omnix Core - Inventory Repository Interface & Excel Implementation
Governing Document: Phase 1 Master Architecture Specification
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Tuple, Union, Sequence, Any
import sqlite3

from core.inventory.models import (
    StockPolicyGroup,
    InventoryProduct,
    SupplierLink,
    StockPolicyRecord,
    ManufacturerRecord,
    CategoryRecord,
    TypeRecord,
    ProviderRecord,
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
from core.inventory.loader import (
    InventoryDatabaseLoader,
    resolve_inventory_database_path,
    MissingWorksheetError,
    WorkbookAccessError,
)
from core.inventory.database import DatabaseManager, resolve_database_path
from core.procurement.vendor_links import parse_vendor_links


class IInventoryRepository(ABC):
    """
    Abstract interface isolating inventory data access from underlying persistence mechanisms.
    Allows UI and procurement layers to query policy groups and products without coupling to Excel.
    """

    @abstractmethod
    def load(self, file_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Load inventory database from storage.
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass

    @abstractmethod
    def get_all_groups(self) -> List[StockPolicyGroup]:
        """Return all canonical policy groups defined in Stock Policy."""
        pass

    @abstractmethod
    def get_group(self, group_key: str) -> Optional[StockPolicyGroup]:
        """Retrieve a specific policy group by its 5-dimension key."""
        pass

    @abstractmethod
    def get_all_products(self) -> List[InventoryProduct]:
        """Return all physical product records from Inventory."""
        pass

    @abstractmethod
    def get_products_for_group(self, group_key: str) -> List[InventoryProduct]:
        """Return individual physical products matching a specific policy group."""
        pass

    @abstractmethod
    def get_warnings(self) -> List[str]:
        """Return diagnostic warnings encountered during loading."""
        pass

    @abstractmethod
    def get_file_path(self) -> Optional[str]:
        """Return active file path if applicable."""
        pass

    def get_all_providers(self, include_inactive: bool = False) -> List[Any]:
        """Return all registered vendor and link providers."""
        return []


class ExcelInventoryRepository(IInventoryRepository):
    """
    Concrete implementation of IInventoryRepository backed by Inventory.xlsm.
    Read-only, preserves workbook immutability.
    """

    def __init__(self, loader: Optional[InventoryDatabaseLoader] = None):
        self._loader = loader or InventoryDatabaseLoader()
        self._groups: List[StockPolicyGroup] = []
        self._groups_by_key: Dict[str, StockPolicyGroup] = {}
        self._products: List[InventoryProduct] = []
        self._products_by_group: Dict[str, List[InventoryProduct]] = {}
        self._warnings: List[str] = []
        self._file_path: Optional[str] = None
        self._is_loaded = False

    def load(self, file_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Load the inventory workbook cleanly.
        """
        try:
            resolved_path = resolve_inventory_database_path(file_path)
            groups, products, warnings = self._loader.load_workbook(resolved_path)

            self._groups = groups
            self._groups_by_key = {g.group_key: g for g in groups}
            self._products = products
            self._products_by_group = {}
            for p in products:
                if p.group_key not in self._products_by_group:
                    self._products_by_group[p.group_key] = []
                self._products_by_group[p.group_key].append(p)

            self._warnings = warnings
            self._file_path = resolved_path
            self._is_loaded = True

            return True, f"Loaded {len(groups)} policy groups and {len(products)} physical products."
        except MissingWorksheetError as e:
            self._is_loaded = False
            return False, f"Missing required worksheet: {e}"
        except WorkbookAccessError as e:
            self._is_loaded = False
            return False, f"Workbook access error: {e}"
        except Exception as e:
            self._is_loaded = False
            return False, f"Unexpected error loading inventory database: {e}"

    def get_all_groups(self) -> List[StockPolicyGroup]:
        return list(self._groups)

    def get_group(self, group_key: str) -> Optional[StockPolicyGroup]:
        return self._groups_by_key.get(group_key)

    def get_all_products(self) -> List[InventoryProduct]:
        return list(self._products)

    def get_products_for_group(self, group_key: str) -> List[InventoryProduct]:
        return list(self._products_by_group.get(group_key, []))

    def get_warnings(self) -> List[str]:
        return list(self._warnings)

    def get_file_path(self) -> Optional[str]:
        return self._file_path

    @property
    def file_path(self) -> Optional[str]:
        return self._file_path

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded


class SqliteInventoryRepository(IInventoryRepository):
    """
    Concrete SQLite implementation of IInventoryRepository.
    Authoritative local database repository for component CRUD, identity normalization,
    supplier links, stock policy persistence, and group aggregation.
    """

    def __init__(
        self,
        db_manager_or_path: Optional[Union[DatabaseManager, str]] = None,
        auto_initialize: bool = True,
    ):
        if isinstance(db_manager_or_path, DatabaseManager):
            self._db = db_manager_or_path
        elif isinstance(db_manager_or_path, str):
            self._db = DatabaseManager(db_manager_or_path)
        else:
            self._db = DatabaseManager()

        self._warnings: List[str] = []
        self._is_loaded = False

        if auto_initialize:
            self._db.initialize_schema()
            self._is_loaded = True

    @property
    def db_manager(self) -> DatabaseManager:
        return self._db

    def load(self, file_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Load / connect to SQLite database.
        """
        try:
            if file_path is not None and file_path != self._db.db_path:
                self._db.close()
                self._db = DatabaseManager(file_path)
            self._db.initialize_schema()
            self._is_loaded = True
            return True, f"Loaded SQLite inventory database from '{self._db.db_path}'."
        except Exception as e:
            self._is_loaded = False
            return False, f"Failed to load SQLite inventory database: {e}"

    def get_file_path(self) -> Optional[str]:
        return self._db.db_path

    @property
    def file_path(self) -> Optional[str]:
        return self._db.db_path

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def get_warnings(self) -> List[str]:
        return list(self._warnings)

    def close(self):
        """Closes the underlying database connection."""
        self._db.close()
        self._is_loaded = False

    def backup(self, target_path: str) -> bool:
        """Hot backup to target file path."""
        return self._db.backup(target_path)

    # =========================================================================
    # Reference Data: Manufacturers
    # =========================================================================

    def add_manufacturer(self, name: str, is_active: bool = True) -> int:
        clean_name = clean_display_string(name)
        if not clean_name:
            raise ValidationError("Manufacturer name cannot be empty.")
        norm = normalize_identity_part(clean_name)

        conn = self._db.get_connection()
        with self._db.transaction():
            existing = conn.execute(
                "SELECT id FROM ref_manufacturers WHERE norm_name = ?;", (norm,)
            ).fetchone()
            if existing:
                raise DuplicateReferenceError(f"Manufacturer '{clean_name}' already exists.")

            cursor = conn.execute(
                """
                INSERT INTO ref_manufacturers (name, norm_name, is_active)
                VALUES (?, ?, ?);
                """,
                (clean_name, norm, 1 if is_active else 0),
            )
            return cursor.lastrowid

    def get_manufacturer(self, mfr_id: int) -> Optional[ManufacturerRecord]:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_manufacturers WHERE id = ?;",
            (mfr_id,),
        ).fetchone()
        if not row:
            return None
        return ManufacturerRecord(
            id=row["id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def get_manufacturer_by_name(self, name: str) -> Optional[ManufacturerRecord]:
        norm = normalize_identity_part(name)
        if not norm:
            return None
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_manufacturers WHERE norm_name = ?;",
            (norm,),
        ).fetchone()
        if not row:
            return None
        return ManufacturerRecord(
            id=row["id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def get_all_manufacturers(self, include_inactive: bool = False) -> List[ManufacturerRecord]:
        conn = self._db.get_connection()
        if include_inactive:
            cursor = conn.execute("SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_manufacturers ORDER BY name COLLATE NOCASE ASC;")
        else:
            cursor = conn.execute("SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_manufacturers WHERE is_active = 1 ORDER BY name COLLATE NOCASE ASC;")

        return [
            ManufacturerRecord(
                id=r["id"],
                name=r["name"],
                norm_name=r["norm_name"],
                is_active=bool(r["is_active"]),
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in cursor.fetchall()
        ]

    def update_manufacturer(
        self,
        mfr_id: int,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            current = self.get_manufacturer(mfr_id)
            if not current:
                return False

            new_name = current.name
            new_norm = current.norm_name
            if name is not None:
                cleaned = clean_display_string(name)
                if not cleaned:
                    raise ValidationError("Manufacturer name cannot be empty.")
                new_norm = normalize_identity_part(cleaned)
                if new_norm != current.norm_name:
                    dup = conn.execute(
                        "SELECT id FROM ref_manufacturers WHERE norm_name = ? AND id != ?;",
                        (new_norm, mfr_id),
                    ).fetchone()
                    if dup:
                        raise DuplicateReferenceError(f"Manufacturer name '{cleaned}' is already in use.")
                new_name = cleaned

            new_active = current.is_active if is_active is None else bool(is_active)

            conn.execute(
                """
                UPDATE ref_manufacturers
                SET name = ?, norm_name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (new_name, new_norm, 1 if new_active else 0, mfr_id),
            )

            # Propagate name change to components to preserve display integrity
            if new_name != current.name:
                if new_norm != current.norm_name:
                    collision = conn.execute(
                        """
                        SELECT c1.id, c1.mpn, c2.id as colliding_id
                        FROM components c1
                        JOIN components c2 ON c2.norm_manufacturer = ? AND c2.norm_mpn = c1.norm_mpn
                        WHERE c1.norm_manufacturer = ?;
                        """,
                        (new_norm, current.norm_name),
                    ).fetchone()
                    if collision:
                        raise ComponentConflictError(
                            f"Cannot rename manufacturer '{current.name}' to '{new_name}': "
                            f"component with MPN '{collision['mpn']}' would collide with existing component (ID {collision['colliding_id']})."
                        )

                conn.execute(
                    """
                    UPDATE components
                    SET manufacturer = ?, norm_manufacturer = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE norm_manufacturer = ?;
                    """,
                    (new_name, new_norm, current.norm_name),
                )

            return True

    def delete_manufacturer(self, mfr_id: int) -> bool:
        mfr = self.get_manufacturer(mfr_id)
        if not mfr:
            return False

        conn = self._db.get_connection()
        with self._db.transaction():
            # Check dependency in components
            in_use = conn.execute(
                "SELECT COUNT(*) FROM components WHERE norm_manufacturer = ?;",
                (mfr.norm_name,),
            ).fetchone()[0]
            if in_use > 0:
                raise ReferenceDataInUseError(
                    f"Cannot delete manufacturer '{mfr.name}' because it is in use by "
                    f"{in_use} component record(s). Deactivate it instead."
                )

            conn.execute("DELETE FROM ref_manufacturers WHERE id = ?;", (mfr_id,))
            return True

    def deactivate_manufacturer(self, mfr_id: int) -> bool:
        return self.update_manufacturer(mfr_id, is_active=False)

    # =========================================================================
    # Reference Data: Categories
    # =========================================================================

    def add_category(self, name: str, is_active: bool = True) -> int:
        clean_name = clean_display_string(name)
        if not clean_name:
            raise ValidationError("Category name cannot be empty.")
        norm = normalize_identity_part(clean_name)

        conn = self._db.get_connection()
        with self._db.transaction():
            existing = conn.execute(
                "SELECT id FROM ref_categories WHERE norm_name = ?;", (norm,)
            ).fetchone()
            if existing:
                raise DuplicateReferenceError(f"Category '{clean_name}' already exists.")

            cursor = conn.execute(
                """
                INSERT INTO ref_categories (name, norm_name, is_active)
                VALUES (?, ?, ?);
                """,
                (clean_name, norm, 1 if is_active else 0),
            )
            return cursor.lastrowid

    def get_category(self, cat_id: int) -> Optional[CategoryRecord]:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_categories WHERE id = ?;",
            (cat_id,),
        ).fetchone()
        if not row:
            return None
        return CategoryRecord(
            id=row["id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def get_category_by_name(self, name: str) -> Optional[CategoryRecord]:
        norm = normalize_identity_part(name)
        if not norm:
            return None
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_categories WHERE norm_name = ?;",
            (norm,),
        ).fetchone()
        if not row:
            return None
        return CategoryRecord(
            id=row["id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def get_all_categories(self, include_inactive: bool = False) -> List[CategoryRecord]:
        conn = self._db.get_connection()
        if include_inactive:
            cursor = conn.execute("SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_categories ORDER BY name COLLATE NOCASE ASC;")
        else:
            cursor = conn.execute("SELECT id, name, norm_name, is_active, created_at, updated_at FROM ref_categories WHERE is_active = 1 ORDER BY name COLLATE NOCASE ASC;")

        return [
            CategoryRecord(
                id=r["id"],
                name=r["name"],
                norm_name=r["norm_name"],
                is_active=bool(r["is_active"]),
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in cursor.fetchall()
        ]

    def update_category(
        self,
        cat_id: int,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            current = self.get_category(cat_id)
            if not current:
                return False

            new_name = current.name
            new_norm = current.norm_name
            if name is not None:
                cleaned = clean_display_string(name)
                if not cleaned:
                    raise ValidationError("Category name cannot be empty.")
                new_norm = normalize_identity_part(cleaned)
                if new_norm != current.norm_name:
                    dup = conn.execute(
                        "SELECT id FROM ref_categories WHERE norm_name = ? AND id != ?;",
                        (new_norm, cat_id),
                    ).fetchone()
                    if dup:
                        raise DuplicateReferenceError(f"Category name '{cleaned}' is already in use.")
                new_name = cleaned

            new_active = current.is_active if is_active is None else bool(is_active)

            conn.execute(
                """
                UPDATE ref_categories
                SET name = ?, norm_name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (new_name, new_norm, 1 if new_active else 0, cat_id),
            )

            # Propagate name change to components and synchronize group_key and stock policies
            if new_name != current.name:
                conn.execute(
                    """
                    UPDATE components
                    SET category = ?,
                        group_key = ? || '|' || type_technology || '|' || value || '|' || package || '|' || footprint,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE category = ? COLLATE NOCASE;
                    """,
                    (new_name, new_name, current.name),
                )

                policies = conn.execute(
                    "SELECT group_key, type_technology, value, package, footprint FROM stock_policies WHERE category = ? COLLATE NOCASE;",
                    (current.name,),
                ).fetchall()
                for pol_row in policies:
                    new_gk = f"{new_name}|{pol_row['type_technology']}|{pol_row['value']}|{pol_row['package']}|{pol_row['footprint']}"
                    conn.execute(
                        """
                        UPDATE stock_policies
                        SET category = ?, group_key = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE group_key = ?;
                        """,
                        (new_name, new_gk, pol_row["group_key"]),
                    )

            return True

    def delete_category(self, cat_id: int) -> bool:
        cat = self.get_category(cat_id)
        if not cat:
            return False

        conn = self._db.get_connection()
        with self._db.transaction():
            # Check 1: associated types
            type_count = conn.execute(
                "SELECT COUNT(*) FROM ref_types WHERE category_id = ?;", (cat_id,)
            ).fetchone()[0]
            if type_count > 0:
                raise ReferenceDataInUseError(
                    f"Cannot delete category '{cat.name}' because it contains "
                    f"{type_count} associated technology type(s). Delete or reassign them first."
                )

            # Check 2: associated components
            in_use = conn.execute(
                "SELECT COUNT(*) FROM components WHERE category = ? COLLATE NOCASE;", (cat.name,)
            ).fetchone()[0]
            if in_use > 0:
                raise ReferenceDataInUseError(
                    f"Cannot delete category '{cat.name}' because it is in use by "
                    f"{in_use} component record(s). Deactivate it instead."
                )

            conn.execute("DELETE FROM ref_categories WHERE id = ?;", (cat_id,))
            return True

    def deactivate_category(self, cat_id: int) -> bool:
        return self.update_category(cat_id, is_active=False)

    def ensure_transistor_reference_data(self) -> bool:
        """
        Ensures canonical Transistor category and its core verified technologies
        (BJT, MOSFET, JFET, IGBT, NPN, PNP) exist in reference tables.
        """
        cat = self.get_category_by_name("Transistor")
        if not cat:
            try:
                cat_id = self.add_category("Transistor")
            except Exception:
                cat = self.get_category_by_name("Transistor")
                cat_id = cat.id if cat else None
        else:
            cat_id = cat.id

        if not cat_id:
            return False

        core_types = ["BJT", "MOSFET", "JFET", "IGBT", "NPN", "PNP"]
        for t_name in core_types:
            if not self.validate_category_type("Transistor", t_name):
                try:
                    self.add_type(cat_id, t_name)
                except Exception:
                    pass
        return True

    # =========================================================================
    # Reference Data: Types / Technologies
    # =========================================================================

    def add_type(self, category_id: int, name: str, is_active: bool = True) -> int:
        cat = self.get_category(category_id)
        if not cat:
            raise ReferenceDataNotFoundError(f"Category ID {category_id} does not exist.")

        clean_name = clean_display_string(name)
        if not clean_name:
            raise ValidationError("Type/Technology name cannot be empty.")
        norm = normalize_identity_part(clean_name)

        conn = self._db.get_connection()
        with self._db.transaction():
            existing = conn.execute(
                "SELECT id FROM ref_types WHERE category_id = ? AND norm_name = ?;",
                (category_id, norm),
            ).fetchone()
            if existing:
                raise DuplicateReferenceError(
                    f"Type/Technology '{clean_name}' already exists in category '{cat.name}'."
                )

            cursor = conn.execute(
                """
                INSERT INTO ref_types (category_id, name, norm_name, is_active)
                VALUES (?, ?, ?, ?);
                """,
                (category_id, clean_name, norm, 1 if is_active else 0),
            )
            return cursor.lastrowid

    def get_type(self, type_id: int) -> Optional[TypeRecord]:
        conn = self._db.get_connection()
        row = conn.execute(
            """
            SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
            FROM ref_types t
            JOIN ref_categories c ON c.id = t.category_id
            WHERE t.id = ?;
            """,
            (type_id,),
        ).fetchone()
        if not row:
            return None
        return TypeRecord(
            id=row["id"],
            category_id=row["category_id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            category_name=row["category_name"],
        )

    def get_type_by_name(self, category_id: int, type_name: str) -> Optional[TypeRecord]:
        """
        Retrieves a canonical type record for a category by case-insensitive normalized name.
        """
        type_norm = normalize_identity_part(type_name)
        if not type_norm:
            return None
        conn = self._db.get_connection()
        row = conn.execute(
            """
            SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
            FROM ref_types t
            JOIN ref_categories c ON c.id = t.category_id
            WHERE t.category_id = ? AND t.norm_name = ?;
            """,
            (category_id, type_norm),
        ).fetchone()
        if not row:
            return None
        return TypeRecord(
            id=row["id"],
            category_id=row["category_id"],
            name=row["name"],
            norm_name=row["norm_name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            category_name=row["category_name"],
        )

    def get_types_for_category(
        self, category_id: int, include_inactive: bool = False
    ) -> List[TypeRecord]:
        conn = self._db.get_connection()
        if include_inactive:
            cursor = conn.execute(
                """
                SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
                FROM ref_types t
                JOIN ref_categories c ON c.id = t.category_id
                WHERE t.category_id = ?
                ORDER BY t.name COLLATE NOCASE ASC;
                """,
                (category_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
                FROM ref_types t
                JOIN ref_categories c ON c.id = t.category_id
                WHERE t.category_id = ? AND t.is_active = 1
                ORDER BY t.name COLLATE NOCASE ASC;
                """,
                (category_id,),
            )

        return [
            TypeRecord(
                id=r["id"],
                category_id=r["category_id"],
                name=r["name"],
                norm_name=r["norm_name"],
                is_active=bool(r["is_active"]),
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
                category_name=r["category_name"],
            )
            for r in cursor.fetchall()
        ]

    def get_all_types(self, include_inactive: bool = False) -> List[TypeRecord]:
        conn = self._db.get_connection()
        if include_inactive:
            cursor = conn.execute(
                """
                SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
                FROM ref_types t
                JOIN ref_categories c ON c.id = t.category_id
                ORDER BY c.name COLLATE NOCASE ASC, t.name COLLATE NOCASE ASC;
                """
            )
        else:
            cursor = conn.execute(
                """
                SELECT t.id, t.category_id, t.name, t.norm_name, t.is_active, t.created_at, t.updated_at, c.name as category_name
                FROM ref_types t
                JOIN ref_categories c ON c.id = t.category_id
                WHERE t.is_active = 1
                ORDER BY c.name COLLATE NOCASE ASC, t.name COLLATE NOCASE ASC;
                """
            )

        return [
            TypeRecord(
                id=r["id"],
                category_id=r["category_id"],
                name=r["name"],
                norm_name=r["norm_name"],
                is_active=bool(r["is_active"]),
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
                category_name=r["category_name"],
            )
            for r in cursor.fetchall()
        ]

    def update_type(
        self,
        type_id: int,
        name: Optional[str] = None,
        category_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            current = self.get_type(type_id)
            if not current:
                return False

            current_cat = self.get_category(current.category_id)
            if not current_cat:
                raise ReferenceDataNotFoundError(f"Parent category ID {current.category_id} not found.")

            new_cat_id = current.category_id if category_id is None else category_id
            # If reassigning category_id, verify that no active components use this type under current category
            if new_cat_id != current.category_id:
                in_use = conn.execute(
                    "SELECT COUNT(*) FROM components WHERE category = ? COLLATE NOCASE AND type_technology = ? COLLATE NOCASE;",
                    (current_cat.name, current.name),
                ).fetchone()[0]
                if in_use > 0:
                    target_cat = self.get_category(new_cat_id)
                    target_cat_name = target_cat.name if target_cat else str(new_cat_id)
                    raise ReferenceDataInUseError(
                        f"Cannot move technology '{current.name}' from '{current_cat.name}' to '{target_cat_name}' "
                        f"because it is in use by {in_use} component record(s). Reassign or update the components first."
                    )

            new_name = current.name
            new_norm = current.norm_name
            if name is not None:
                cleaned = clean_display_string(name)
                if not cleaned:
                    raise ValidationError("Type/Technology name cannot be empty.")
                new_norm = normalize_identity_part(cleaned)
                new_name = cleaned

            # Check uniqueness under category
            dup = conn.execute(
                "SELECT id FROM ref_types WHERE category_id = ? AND norm_name = ? AND id != ?;",
                (new_cat_id, new_norm, type_id),
            ).fetchone()
            if dup:
                raise DuplicateReferenceError(
                    f"Type '{new_name}' already exists in target category."
                )

            new_active = current.is_active if is_active is None else bool(is_active)

            conn.execute(
                """
                UPDATE ref_types
                SET category_id = ?, name = ?, norm_name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (new_cat_id, new_name, new_norm, 1 if new_active else 0, type_id),
            )

            # Propagate name change to components and synchronize group_key and stock policies
            if new_name != current.name:
                conn.execute(
                    """
                    UPDATE components
                    SET type_technology = ?,
                        group_key = category || '|' || ? || '|' || value || '|' || package || '|' || footprint,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE category = ? COLLATE NOCASE AND type_technology = ? COLLATE NOCASE;
                    """,
                    (new_name, new_name, current_cat.name, current.name),
                )

                policies = conn.execute(
                    "SELECT group_key, category, value, package, footprint FROM stock_policies WHERE category = ? COLLATE NOCASE AND type_technology = ? COLLATE NOCASE;",
                    (current_cat.name, current.name),
                ).fetchall()
                for pol_row in policies:
                    new_gk = f"{pol_row['category']}|{new_name}|{pol_row['value']}|{pol_row['package']}|{pol_row['footprint']}"
                    conn.execute(
                        """
                        UPDATE stock_policies
                        SET type_technology = ?, group_key = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE group_key = ?;
                        """,
                        (new_name, new_gk, pol_row["group_key"]),
                    )

            return True

    def delete_type(self, type_id: int) -> bool:
        t = self.get_type(type_id)
        if not t:
            return False

        conn = self._db.get_connection()
        with self._db.transaction():
            in_use = conn.execute(
                "SELECT COUNT(*) FROM components WHERE category = ? COLLATE NOCASE AND type_technology = ? COLLATE NOCASE;",
                (t.category_name, t.name),
            ).fetchone()[0]
            if in_use > 0:
                raise ReferenceDataInUseError(
                    f"Cannot delete type '{t.name}' because it is in use by "
                    f"{in_use} component record(s) under category '{t.category_name}'. Deactivate it instead."
                )


            conn.execute("DELETE FROM ref_types WHERE id = ?;", (type_id,))
            return True

    def deactivate_type(self, type_id: int) -> bool:
        return self.update_type(type_id, is_active=False)

    def validate_category_type(self, category_name: str, type_name: str) -> bool:
        """
        Validates whether type_name is an active canonical technology for category_name.
        """
        cat_norm = normalize_identity_part(category_name)
        type_norm = normalize_identity_part(type_name)
        if not cat_norm or not type_norm:
            return False

        conn = self._db.get_connection()
        row = conn.execute(
            """
            SELECT t.id
            FROM ref_types t
            JOIN ref_categories c ON c.id = t.category_id
            WHERE c.norm_name = ? AND t.norm_name = ? AND t.is_active = 1 AND c.is_active = 1;
            """,
            (cat_norm, type_norm),
        ).fetchone()
        return row is not None

    # =========================================================================
    # Vendor & Link Providers Reference Data CRUD
    # =========================================================================

    def get_all_providers(self, include_inactive: bool = False) -> List[ProviderRecord]:
        conn = self._db.get_connection()
        query = "SELECT id, provider_id, name, norm_name, label, base_url, is_active, created_at, updated_at FROM ref_providers"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY id ASC;"
        rows = conn.execute(query).fetchall()
        return [
            ProviderRecord(
                id=r["id"],
                provider_id=r["provider_id"],
                name=r["name"],
                norm_name=r["norm_name"],
                label=r["label"],
                base_url=r["base_url"] or "",
                is_active=bool(r["is_active"]),
                created_at=str(r["created_at"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]

    def get_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, provider_id, name, norm_name, label, base_url, is_active, created_at, updated_at FROM ref_providers WHERE provider_id = ? OR norm_name = ?;",
            (provider_id.strip(), normalize_identity_part(provider_id)),
        ).fetchone()
        if not row:
            return None
        return ProviderRecord(
            id=row["id"],
            provider_id=row["provider_id"],
            name=row["name"],
            norm_name=row["norm_name"],
            label=row["label"],
            base_url=row["base_url"] or "",
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def add_provider(
        self,
        provider_id: str,
        name: str,
        label: str,
        base_url: str = "",
        is_active: bool = True,
    ) -> ProviderRecord:
        clean_pid = provider_id.strip()
        clean_name = clean_display_string(name)
        clean_label = clean_display_string(label).upper()
        if not clean_pid or not clean_name or not clean_label:
            raise ValidationError("Provider ID, Name, and Label cannot be empty.")

        norm_name = normalize_identity_part(clean_name)
        conn = self._db.get_connection()
        with self._db.transaction():
            existing = conn.execute(
                "SELECT id FROM ref_providers WHERE provider_id = ? OR norm_name = ?;",
                (clean_pid, norm_name),
            ).fetchone()
            if existing:
                raise DuplicateReferenceError(f"Provider '{clean_name}' ({clean_pid}) already exists.")

            cursor = conn.execute(
                """
                INSERT INTO ref_providers (provider_id, name, norm_name, label, base_url, is_active)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (clean_pid, clean_name, norm_name, clean_label, (base_url or "").strip(), 1 if is_active else 0),
            )
            pk = cursor.lastrowid
            return ProviderRecord(
                id=pk,
                provider_id=clean_pid,
                name=clean_name,
                norm_name=norm_name,
                label=clean_label,
                base_url=(base_url or "").strip(),
                is_active=bool(is_active),
            )

    def update_provider(
        self,
        provider_pk: int,
        name: Optional[str] = None,
        label: Optional[str] = None,
        base_url: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[ProviderRecord]:
        conn = self._db.get_connection()
        with self._db.transaction():
            current = conn.execute(
                "SELECT id, provider_id, name, norm_name, label, base_url, is_active FROM ref_providers WHERE id = ?;",
                (provider_pk,),
            ).fetchone()
            if not current:
                return None

            new_name = clean_display_string(name) if name is not None else current["name"]
            new_label = clean_display_string(label).upper() if label is not None else current["label"]
            new_url = (base_url or "").strip() if base_url is not None else current["base_url"]
            new_active = bool(is_active) if is_active is not None else bool(current["is_active"])
            norm_name = normalize_identity_part(new_name)

            if norm_name != current["norm_name"]:
                dup = conn.execute(
                    "SELECT id FROM ref_providers WHERE norm_name = ? AND id != ?;",
                    (norm_name, provider_pk),
                ).fetchone()
                if dup:
                    raise DuplicateReferenceError(f"Provider name '{new_name}' already exists.")

            conn.execute(
                """
                UPDATE ref_providers
                SET name = ?, norm_name = ?, label = ?, base_url = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (new_name, norm_name, new_label, new_url, 1 if new_active else 0, provider_pk),
            )
            return ProviderRecord(
                id=provider_pk,
                provider_id=current["provider_id"],
                name=new_name,
                norm_name=norm_name,
                label=new_label,
                base_url=new_url,
                is_active=new_active,
            )

    def delete_provider(self, provider_pk: int) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            current = conn.execute(
                "SELECT provider_id, label FROM ref_providers WHERE id = ?;",
                (provider_pk,),
            ).fetchone()
            if not current:
                return False

            pid = current["provider_id"]
            lbl = current["label"]
            in_use = conn.execute(
                "SELECT COUNT(*) FROM supplier_links WHERE vendor_id = ? OR vendor_label = ?;",
                (pid, lbl),
            ).fetchone()[0]
            if in_use > 0:
                raise ReferenceDataInUseError(
                    f"Cannot delete provider '{pid}' because {in_use} supplier link(s) reference it. Deactivate it instead."
                )

            conn.execute("DELETE FROM ref_providers WHERE id = ?;", (provider_pk,))
            return True

    # =========================================================================
    # Component CRUD & Identity Enforcement
    # =========================================================================

    def _row_to_component(
        self, row: sqlite3.Row, links: Optional[List[SupplierLink]] = None
    ) -> InventoryProduct:
        comp_id = row["id"]
        if links is None:
            links = self.get_supplier_links(comp_id)

        purchase_link = format_supplier_links_as_string(links) or None

        return InventoryProduct(
            id=comp_id,
            manufacturer=row["manufacturer"],
            mpn=row["mpn"],
            norm_manufacturer=row["norm_manufacturer"],
            norm_mpn=row["norm_mpn"],
            category=row["category"],
            type_technology=row["type_technology"],
            package=row["package"],
            raw_package=row["raw_package"] or "",
            footprint=row["footprint"],
            value=row["value"],
            description=row["description"] or "",
            quantity_in_stock=row["quantity_in_stock"],
            purchase_link=purchase_link,
            group_key=row["group_key"],
            supplier_links=tuple(links),
        )

    def create_component(
        self,
        product: InventoryProduct,
        supplier_links: Optional[Sequence[SupplierLink]] = None,
    ) -> InventoryProduct:
        """
        Creates an individual physical component record with enforced identity uniqueness
        and transactionally persists any associated supplier links.
        """
        clean_mfr = clean_display_string(product.manufacturer)
        clean_mpn = clean_display_string(product.mpn)

        if not clean_mfr:
            raise ValidationError("Manufacturer cannot be empty.")
        if not clean_mpn:
            raise ValidationError("MPN cannot be empty.")

        if product.quantity_in_stock < 0:
            raise ValidationError(
                f"Quantity in stock must be non-negative (received {product.quantity_in_stock})."
            )

        norm_mfr = normalize_identity_part(clean_mfr)
        norm_mpn = normalize_identity_part(clean_mpn)

        cat = clean_display_string(product.category)
        tech = clean_display_string(product.type_technology)
        val = clean_display_string(product.value)
        raw_pkg = clean_display_string(product.raw_package or product.package)
        pkg = normalize_package(product.package)
        fp = clean_display_string(product.footprint)
        desc = clean_display_string(product.description)
        qty = int(product.quantity_in_stock)

        group_key = build_group_key(cat, tech, val, pkg, fp)

        conn = self._db.get_connection()
        with self._db.transaction():
            # Validate category and type if canonical reference data is populated in database
            has_ref_data = conn.execute("SELECT COUNT(*) FROM ref_categories;").fetchone()[0] > 0
            if has_ref_data and cat:
                cat_rec = self.get_category_by_name(cat)
                if not cat_rec:
                    raise ReferenceDataNotFoundError(f"Category '{cat}' does not exist in canonical reference data.")
                cat = cat_rec.name
                if tech:
                    if not self.validate_category_type(cat, tech):
                        raise ValidationError(
                            f"Type/Technology '{tech}' is not an active technology for category '{cat}'."
                        )
                    type_rec = self.get_type_by_name(cat_rec.id, tech)
                    if type_rec:
                        tech = type_rec.name

            if clean_mfr:
                mfr_rec = self.get_manufacturer_by_name(clean_mfr)
                if mfr_rec:
                    clean_mfr = mfr_rec.name

            # Recalculate group key with canonical names
            group_key = build_group_key(cat, tech, val, pkg, fp)

            # Identity collision check (Manufacturer + MPN)
            conflict = conn.execute(
                "SELECT id, manufacturer, mpn FROM components WHERE norm_manufacturer = ? AND norm_mpn = ?;",
                (norm_mfr, norm_mpn),
            ).fetchone()
            if conflict:
                existing = self.get_component_by_id(conflict["id"])
                raise ComponentConflictError(
                    f"Component with identity '{clean_mfr}' + '{clean_mpn}' already exists in database (ID {conflict['id']}).",
                    existing_component=existing,
                    conflicting_data=product.to_dict(),
                )

            cursor = conn.execute(
                """
                INSERT INTO components (
                    manufacturer, mpn, norm_manufacturer, norm_mpn,
                    category, type_technology, package, raw_package,
                    footprint, value, description, quantity_in_stock, group_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (clean_mfr, clean_mpn, norm_mfr, norm_mpn, cat, tech, pkg, raw_pkg, fp, val, desc, qty, group_key),
            )
            comp_id = cursor.lastrowid

            # Determine links to insert
            links_to_insert: List[SupplierLink] = []
            if supplier_links is not None:
                links_to_insert = list(supplier_links)
            elif product.supplier_links:
                links_to_insert = list(product.supplier_links)
            elif product.purchase_link and str(product.purchase_link).strip():
                parsed = parse_vendor_links(product.purchase_link)
                if parsed.links:
                    for entry in parsed.links.values():
                        links_to_insert.append(
                            SupplierLink(
                                vendor_id=entry.vendor_id,
                                vendor_label=entry.vendor_label,
                                url=entry.url,
                                display_name=entry.display_name,
                            )
                        )
                else:
                    links_to_insert.append(
                        SupplierLink(
                            vendor_id="generic",
                            vendor_label="LINK",
                            url=str(product.purchase_link).strip(),
                        )
                    )

            inserted_links = []
            for l in links_to_insert:
                if not l.url or not str(l.url).strip():
                    continue
                cur_link = conn.execute(
                    """
                    INSERT INTO supplier_links (component_id, vendor_id, vendor_label, url, display_name)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (comp_id, l.vendor_id or "generic", l.vendor_label or "LINK", str(l.url).strip(), l.display_name or ""),
                )
                inserted_links.append(
                    SupplierLink(
                        id=cur_link.lastrowid,
                        component_id=comp_id,
                        vendor_id=l.vendor_id or "generic",
                        vendor_label=l.vendor_label or "LINK",
                        url=str(l.url).strip(),
                        display_name=l.display_name or "",
                    )
                )

        return self.get_component_by_id(comp_id)

    def get_component_by_id(self, component_id: int) -> Optional[InventoryProduct]:
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT * FROM components WHERE id = ?;", (component_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_component(row)

    def get_component_by_identity(self, manufacturer: str, mpn: str) -> Optional[InventoryProduct]:
        norm_mfr = normalize_identity_part(manufacturer)
        norm_mpn = normalize_identity_part(mpn)
        if not norm_mfr or not norm_mpn:
            return None

        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT * FROM components WHERE norm_manufacturer = ? AND norm_mpn = ?;",
            (norm_mfr, norm_mpn),
        ).fetchone()
        if not row:
            return None
        return self._row_to_component(row)

    def update_component(self, component_id: int, **fields) -> InventoryProduct:
        """
        Updates an existing component record. Enforces identity uniqueness against other
        components and re-aggregates group key if grouping attributes change.
        """
        conn = self._db.get_connection()
        with self._db.transaction():
            row = conn.execute("SELECT * FROM components WHERE id = ?;", (component_id,)).fetchone()
            if not row:
                raise ComponentNotFoundError(f"Component ID {component_id} not found.")

            mfr = clean_display_string(fields.get("manufacturer", row["manufacturer"]))
            mpn = clean_display_string(fields.get("mpn", row["mpn"]))
            if not mfr or not mpn:
                raise ValidationError("Manufacturer and MPN cannot be empty.")

            norm_mfr = normalize_identity_part(mfr)
            norm_mpn = normalize_identity_part(mpn)

            # Check collision with other components
            conflict = conn.execute(
                "SELECT id FROM components WHERE norm_manufacturer = ? AND norm_mpn = ? AND id != ?;",
                (norm_mfr, norm_mpn, component_id),
            ).fetchone()
            if conflict:
                existing = self.get_component_by_id(conflict["id"])
                raise ComponentConflictError(
                    f"Cannot update component {component_id} to '{mfr}' + '{mpn}': "
                    f"identity is already in use by component ID {conflict['id']}.",
                    existing_component=existing,
                )

            cat = clean_display_string(fields.get("category", row["category"]))
            tech = clean_display_string(fields.get("type_technology", row["type_technology"]))

            # Validate category and type if canonical reference data is populated
            has_ref_data = conn.execute("SELECT COUNT(*) FROM ref_categories;").fetchone()[0] > 0
            if has_ref_data and cat:
                cat_rec = self.get_category_by_name(cat)
                if not cat_rec:
                    raise ReferenceDataNotFoundError(f"Category '{cat}' does not exist in canonical reference data.")
                cat = cat_rec.name
                if tech:
                    if not self.validate_category_type(cat, tech):
                        raise ValidationError(
                            f"Type/Technology '{tech}' is not an active technology for category '{cat}'."
                        )
                    type_rec = self.get_type_by_name(cat_rec.id, tech)
                    if type_rec:
                        tech = type_rec.name

            if mfr:
                mfr_rec = self.get_manufacturer_by_name(mfr)
                if mfr_rec:
                    mfr = mfr_rec.name

            val = clean_display_string(fields.get("value", row["value"]))
            raw_pkg = clean_display_string(fields.get("raw_package", fields.get("package", row["package"])))
            pkg = normalize_package(fields.get("package", row["package"]))
            fp = clean_display_string(fields.get("footprint", row["footprint"]))
            desc = clean_display_string(fields.get("description", row["description"]))

            qty_val = fields.get("quantity_in_stock", row["quantity_in_stock"])
            if qty_val is not None:
                if not isinstance(qty_val, (int, float)) or int(qty_val) < 0:
                    raise ValidationError(f"Quantity in stock must be non-negative (received {qty_val}).")
                qty = int(qty_val)
            else:
                qty = row["quantity_in_stock"]

            group_key = build_group_key(cat, tech, val, pkg, fp)

            conn.execute(
                """
                UPDATE components SET
                    manufacturer = ?,
                    mpn = ?,
                    norm_manufacturer = ?,
                    norm_mpn = ?,
                    category = ?,
                    type_technology = ?,
                    package = ?,
                    raw_package = ?,
                    footprint = ?,
                    value = ?,
                    description = ?,
                    quantity_in_stock = ?,
                    group_key = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (mfr, mpn, norm_mfr, norm_mpn, cat, tech, pkg, raw_pkg, fp, val, desc, qty, group_key, component_id),
            )

            if "supplier_links" in fields and fields["supplier_links"] is not None:
                self.set_supplier_links(component_id, fields["supplier_links"])

        return self.get_component_by_id(component_id)

    def delete_component(self, component_id: int) -> bool:
        """
        Deletes component. Cascade foreign keys automatically delete supplier links.

        Empty-Group Policy Cleanup Invariant:
        - If other components remain in the same five-field group, the group's Min Stock
          and Target Stock policy values remain unchanged.
        - If the deleted component was the last component in that group, delete that
          group's stock policy record in the same database transaction.
        - If any error occurs, the transaction rolls back atomically.
        """
        conn = self._db.get_connection()
        with self._db.transaction():
            # 1. Lookup group_key for component before deletion
            row = conn.execute("SELECT group_key FROM components WHERE id = ?;", (component_id,)).fetchone()
            if not row:
                return False
            group_key = row["group_key"]

            # 2. Delete the component
            cursor = conn.execute("DELETE FROM components WHERE id = ?;", (component_id,))
            if cursor.rowcount == 0:
                return False

            # 3. Check if any components remain in this group
            remaining = conn.execute(
                "SELECT COUNT(*) FROM components WHERE group_key = ?;", (group_key,)
            ).fetchone()[0]

            # 4. If no components remain, atomically clean up the orphaned stock policy
            if remaining == 0:
                conn.execute("DELETE FROM stock_policies WHERE group_key = ?;", (group_key,))

            return True

    def search_components(self, query: str) -> List[InventoryProduct]:
        """Multi-token keyword search matching component fields."""
        if not query or not query.strip():
            return self.get_all_products()

        terms = [t.strip().upper() for t in query.split() if t.strip()]
        all_prods = self.get_all_products()
        matched = []
        for p in all_prods:
            searchable = " ".join([
                p.manufacturer, p.mpn, p.category, p.type_technology,
                p.value, p.package, p.footprint, p.description,
                p.purchase_link or ""
            ]).upper()
            if all(t in searchable for t in terms):
                matched.append(p)
        return matched

    def reconcile_canonical_classifications(self) -> int:
        """
        Scans all component records and reconciles category, type_technology,
        and group_key to match active canonical reference data.
        Preserves the authoritative 5-dimension group key:
        Category + Type/Technology + Value + Package + Footprint
        Returns the number of component records updated.
        """
        conn = self._db.get_connection()
        has_ref = conn.execute("SELECT COUNT(*) FROM ref_categories;").fetchone()[0] > 0
        if not has_ref:
            return 0

        updated_count = 0
        with self._db.transaction():
            rows = conn.execute("SELECT * FROM components;").fetchall()
            for r in rows:
                comp_id = r["id"]
                cur_cat = r["category"]
                cur_tech = r["type_technology"]
                cur_key = r["group_key"]
                val = r["value"]
                pkg = r["package"]
                fp = r["footprint"]

                cat_rec = self.get_category_by_name(cur_cat)
                new_cat = cat_rec.name if cat_rec else cur_cat
                new_tech = cur_tech
                if cat_rec and cur_tech:
                    t_rec = self.get_type_by_name(cat_rec.id, cur_tech)
                    if t_rec:
                        new_tech = t_rec.name

                new_key = build_group_key(new_cat, new_tech, val, pkg, fp)
                if new_cat != cur_cat or new_tech != cur_tech or new_key != cur_key:
                    conn.execute(
                        """
                        UPDATE components SET
                            category = ?,
                            type_technology = ?,
                            group_key = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (new_cat, new_tech, new_key, comp_id),
                    )
                    updated_count += 1
        return updated_count

    # =========================================================================
    # Supplier Links (One-to-Many)
    # =========================================================================

    def add_supplier_link(
        self,
        component_id: int,
        vendor_id: str,
        vendor_label: str,
        url: str,
        display_name: str = "",
    ) -> SupplierLink:
        if not url or not url.strip():
            raise ValidationError("Supplier link URL cannot be empty.")

        conn = self._db.get_connection()
        with self._db.transaction():
            c = conn.execute("SELECT id FROM components WHERE id = ?;", (component_id,)).fetchone()
            if not c:
                raise ComponentNotFoundError(f"Component ID {component_id} not found.")

            cursor = conn.execute(
                """
                INSERT INTO supplier_links (component_id, vendor_id, vendor_label, url, display_name)
                VALUES (?, ?, ?, ?, ?);
                """,
                (component_id, vendor_id or "generic", vendor_label or "LINK", url.strip(), display_name or ""),
            )
            return SupplierLink(
                id=cursor.lastrowid,
                component_id=component_id,
                vendor_id=vendor_id or "generic",
                vendor_label=vendor_label or "LINK",
                url=url.strip(),
                display_name=display_name or "",
            )

    def get_supplier_links(self, component_id: int) -> List[SupplierLink]:
        conn = self._db.get_connection()
        cursor = conn.execute(
            """
            SELECT id, component_id, vendor_id, vendor_label, url, display_name
            FROM supplier_links
            WHERE component_id = ?
            ORDER BY id ASC;
            """,
            (component_id,),
        )
        return [
            SupplierLink(
                id=r["id"],
                component_id=r["component_id"],
                vendor_id=r["vendor_id"],
                vendor_label=r["vendor_label"],
                url=r["url"],
                display_name=r["display_name"] or "",
            )
            for r in cursor.fetchall()
        ]

    def set_supplier_links(
        self, component_id: int, links: Sequence[SupplierLink]
    ) -> List[SupplierLink]:
        """Atomically replaces all supplier links for a component."""
        conn = self._db.get_connection()
        with self._db.transaction():
            c = conn.execute("SELECT id FROM components WHERE id = ?;", (component_id,)).fetchone()
            if not c:
                raise ComponentNotFoundError(f"Component ID {component_id} not found.")

            conn.execute("DELETE FROM supplier_links WHERE component_id = ?;", (component_id,))
            inserted = []
            for l in links:
                if not l.url or not str(l.url).strip():
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO supplier_links (component_id, vendor_id, vendor_label, url, display_name)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (component_id, l.vendor_id or "generic", l.vendor_label or "LINK", str(l.url).strip(), l.display_name or ""),
                )
                inserted.append(
                    SupplierLink(
                        id=cur.lastrowid,
                        component_id=component_id,
                        vendor_id=l.vendor_id or "generic",
                        vendor_label=l.vendor_label or "LINK",
                        url=str(l.url).strip(),
                        display_name=l.display_name or "",
                    )
                )
            return inserted

    def delete_supplier_link(self, link_id: int) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            cursor = conn.execute("DELETE FROM supplier_links WHERE id = ?;", (link_id,))
            return cursor.rowcount > 0

    # =========================================================================
    # Stock Policies
    # =========================================================================

    def get_policy(self, group_key: str) -> Optional[StockPolicyRecord]:
        conn = self._db.get_connection()
        row = conn.execute(
            """
            SELECT group_key, category, type_technology, value, package, footprint, min_stock, target_stock, description
            FROM stock_policies
            WHERE group_key = ?;
            """,
            (group_key,),
        ).fetchone()
        if not row:
            return None
        return StockPolicyRecord(
            group_key=row["group_key"],
            category=row["category"],
            type_technology=row["type_technology"],
            value=row["value"],
            package=row["package"],
            footprint=row["footprint"],
            min_stock=row["min_stock"],
            target_stock=row["target_stock"],
            description=row["description"] or "",
        )

    def set_policy(
        self,
        group_key: str,
        min_stock: Optional[int] = None,
        target_stock: Optional[int] = None,
        category: str = "",
        type_technology: str = "",
        value: str = "",
        package: str = "",
        footprint: str = "",
        description: str = "",
    ) -> StockPolicyRecord:
        """
        Sets or updates min_stock and target_stock thresholds for a 5-dimension group key.
        Preserves policy even when no components currently exist in inventory.
        """
        if min_stock is not None:
            if not isinstance(min_stock, (int, float)) or int(min_stock) < 0:
                raise ValidationError(f"Min Stock must be non-negative (received {min_stock}).")
            min_stock = int(min_stock)

        if target_stock is not None:
            if not isinstance(target_stock, (int, float)) or int(target_stock) < 0:
                raise ValidationError(f"Target Stock must be non-negative (received {target_stock}).")
            target_stock = int(target_stock)

        if min_stock is not None and target_stock is not None and target_stock < min_stock:
            raise ValidationError(
                f"Target Stock ({target_stock}) cannot be less than Min Stock ({min_stock})."
            )

        parts = group_key.split("|")
        cat = category or (parts[0] if len(parts) > 0 else "")
        tech = type_technology or (parts[1] if len(parts) > 1 else "")
        val = value or (parts[2] if len(parts) > 2 else "")
        pkg = normalize_package(package or (parts[3] if len(parts) > 3 else ""))
        fp = footprint or (parts[4] if len(parts) > 4 else "")

        conn = self._db.get_connection()
        with self._db.transaction():
            conn.execute(
                """
                INSERT INTO stock_policies (
                    group_key, category, type_technology, value, package, footprint,
                    min_stock, target_stock, description, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(group_key) DO UPDATE SET
                    min_stock = excluded.min_stock,
                    target_stock = excluded.target_stock,
                    description = CASE WHEN excluded.description != '' THEN excluded.description ELSE stock_policies.description END,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (group_key, cat, tech, val, pkg, fp, min_stock, target_stock, description or ""),
            )

        return self.get_policy(group_key)

    def delete_policy(self, group_key: str) -> bool:
        conn = self._db.get_connection()
        with self._db.transaction():
            cursor = conn.execute("DELETE FROM stock_policies WHERE group_key = ?;", (group_key,))
            return cursor.rowcount > 0

    def get_all_policies(self) -> List[StockPolicyRecord]:
        conn = self._db.get_connection()
        cursor = conn.execute(
            """
            SELECT group_key, category, type_technology, value, package, footprint, min_stock, target_stock, description
            FROM stock_policies
            ORDER BY category ASC, type_technology ASC, value ASC;
            """
        )
        return [
            StockPolicyRecord(
                group_key=r["group_key"],
                category=r["category"],
                type_technology=r["type_technology"],
                value=r["value"],
                package=r["package"],
                footprint=r["footprint"],
                min_stock=r["min_stock"],
                target_stock=r["target_stock"],
                description=r["description"] or "",
            )
            for r in cursor.fetchall()
        ]

    # =========================================================================
    # Aggregation & IInventoryRepository Contract
    # =========================================================================

    def get_all_products(self) -> List[InventoryProduct]:
        """Returns all physical components in database with their supplier links."""
        conn = self._db.get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM components
            ORDER BY category ASC, manufacturer ASC, mpn ASC;
            """
        )
        links_cursor = conn.execute(
            "SELECT id, component_id, vendor_id, vendor_label, url, display_name FROM supplier_links ORDER BY id ASC;"
        )
        links_by_comp: Dict[int, List[SupplierLink]] = {}
        for lr in links_cursor.fetchall():
            links_by_comp.setdefault(lr["component_id"], []).append(
                SupplierLink(
                    id=lr["id"],
                    component_id=lr["component_id"],
                    vendor_id=lr["vendor_id"],
                    vendor_label=lr["vendor_label"],
                    url=lr["url"],
                    display_name=lr["display_name"] or "",
                )
            )

        return [
            self._row_to_component(r, links_by_comp.get(r["id"], []))
            for r in cursor.fetchall()
        ]

    def get_products_for_group(self, group_key: str) -> List[InventoryProduct]:
        """Returns individual physical products contributing to a specific policy group."""
        conn = self._db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM components WHERE group_key = ? ORDER BY manufacturer ASC, mpn ASC;",
            (group_key,),
        )
        return [self._row_to_component(r) for r in cursor.fetchall()]

    def get_all_groups(self) -> List[StockPolicyGroup]:
        """
        Returns all canonical policy groups aggregated across database components
        and saved stock policies.
        Preserves policy-only groups with zero current stock.
        """
        all_products = self.get_all_products()
        products_by_group: Dict[str, List[InventoryProduct]] = {}
        for p in all_products:
            products_by_group.setdefault(p.group_key, []).append(p)

        policies = {p.group_key: p for p in self.get_all_policies()}
        all_keys = sorted(list(set(products_by_group.keys()) | set(policies.keys())))

        groups: List[StockPolicyGroup] = []
        for key in all_keys:
            prods = products_by_group.get(key, [])
            pol = policies.get(key)

            if prods:
                current_stock = sum(p.quantity_in_stock for p in prods)
                sample_p = prods[0]
                cat = sample_p.category
                tech = sample_p.type_technology
                val = sample_p.value
                pkg = sample_p.package
                fp = sample_p.footprint
                desc = (pol.description if pol and pol.description else sample_p.description) or ""
            elif pol:
                current_stock = 0
                cat = pol.category
                tech = pol.type_technology
                val = pol.value
                pkg = pol.package
                fp = pol.footprint
                desc = pol.description or ""
            else:
                continue

            min_stock = pol.min_stock if pol else None
            target_stock = pol.target_stock if pol else None

            missing = []
            if min_stock is None:
                missing.append("min_stock")
            if target_stock is None:
                missing.append("target_stock")

            group = StockPolicyGroup(
                category=cat,
                type_technology=tech,
                value=val,
                package=pkg,
                footprint=fp,
                current_stock=current_stock,
                min_stock=min_stock,
                target_stock=target_stock,
                description=desc,
                products=tuple(prods),
                missing_fields=tuple(missing),
            )
            groups.append(group)

        return groups

    def get_group(self, group_key: str) -> Optional[StockPolicyGroup]:
        """Retrieves an individual policy group by its 5-dimension key."""
        prods = self.get_products_for_group(group_key)
        pol = self.get_policy(group_key)
        if not prods and not pol:
            return None

        if prods:
            current_stock = sum(p.quantity_in_stock for p in prods)
            sample_p = prods[0]
            cat = sample_p.category
            tech = sample_p.type_technology
            val = sample_p.value
            pkg = sample_p.package
            fp = sample_p.footprint
            desc = (pol.description if pol and pol.description else sample_p.description) or ""
        else:
            current_stock = 0
            cat = pol.category
            tech = pol.type_technology
            val = pol.value
            pkg = pol.package
            fp = pol.footprint
            desc = pol.description or ""

        min_stock = pol.min_stock if pol else None
        target_stock = pol.target_stock if pol else None

        missing = []
        if min_stock is None:
            missing.append("min_stock")
        if target_stock is None:
            missing.append("target_stock")

        return StockPolicyGroup(
            category=cat,
            type_technology=tech,
            value=val,
            package=pkg,
            footprint=fp,
            current_stock=current_stock,
            min_stock=min_stock,
            target_stock=target_stock,
            description=desc,
            products=tuple(prods),
            missing_fields=tuple(missing),
        )

