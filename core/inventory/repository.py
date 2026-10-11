"""
Omnix Core - Inventory Repository Interface & Excel Implementation
Governing Document: Phase 1 Master Architecture Specification
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Tuple

from core.inventory.models import StockPolicyGroup, InventoryProduct
from core.inventory.loader import (
    InventoryDatabaseLoader,
    resolve_inventory_database_path,
    MissingWorksheetError,
    WorkbookAccessError,
)


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
