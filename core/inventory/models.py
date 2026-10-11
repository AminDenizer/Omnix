"""
Omnix Core - Inventory Domain Models
Governing Document: Phase 1 Master Architecture Specification
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Any


def normalize_package(pkg: Any) -> str:
    """
    Deterministically normalize component package codes.
    Handles numeric packages (e.g. 603 -> '0603', 805 -> '0805')
    and ensures consistent matching with textual codes ('0603', 'D Case').
    """
    if pkg is None:
        return ""
    pkg_str = str(pkg).strip()
    if pkg_str.isdigit() and len(pkg_str) < 4:
        return pkg_str.zfill(4)
    return pkg_str


def build_group_key(
    category: str,
    type_technology: str,
    value: str,
    package: Any,
    footprint: str,
) -> str:
    """
    Construct the canonical Group Key using the exact 5 dimensions defined by the workbook:
    Category | Type/Technology | Value | Normalized Package | Footprint
    """
    cat = (category or "").strip()
    tech = (type_technology or "").strip()
    val = (value or "").strip()
    norm_pkg = normalize_package(package)
    fp = (footprint or "").strip()
    return f"{cat}|{tech}|{val}|{norm_pkg}|{fp}"


@dataclass(frozen=True)
class InventoryProduct:
    """
    Individual physical product record from the 'Inventory' sheet.
    Preserves exact manufacturer, MPN, description, physical on-hand quantity,
    and its single independent Purchase Link.
    """
    manufacturer: str
    mpn: str
    category: str
    type_technology: str
    package: str  # Normalized package code
    footprint: str
    value: str
    description: str
    quantity_in_stock: int
    purchase_link: Optional[str]
    group_key: str
    raw_package: str = ""

    @property
    def quantity(self) -> int:
        return self.quantity_in_stock


@dataclass(frozen=True)
class StockPolicyGroup:
    """
    Canonical stock-policy group from the 'Stock Policy' sheet.
    Stock Policy is the authoritative source for group identity, aggregated current stock,
    Min Stock, and Target Stock.
    """
    category: str
    type_technology: str
    value: str
    package: str  # Normalized package code
    footprint: str
    current_stock: Optional[int]  # Read directly from 'Total Quantity in Stock'
    min_stock: Optional[int]      # Read directly from 'Min Stock'
    target_stock: Optional[int]   # Read directly from 'Target Stock'
    description: str
    products: Tuple[InventoryProduct, ...] = ()
    missing_fields: Tuple[str, ...] = ()

    @property
    def group_key(self) -> str:
        return build_group_key(
            self.category,
            self.type_technology,
            self.value,
            self.package,
            self.footprint,
        )

    @property
    def is_complete(self) -> bool:
        """Indicates whether all required policy fields (current, min, target) are present and valid."""
        return len(self.missing_fields) == 0

    @property
    def is_low_stock(self) -> bool:
        """True if current_stock is strictly below min_stock."""
        if not self.is_complete:
            return False
        if self.min_stock is None or self.current_stock is None:
            return False
        return self.current_stock < self.min_stock
