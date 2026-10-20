"""
Omnix Core - Inventory Domain Models
Governing Document: Phase 1 Master Architecture Specification
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Any, Sequence, Dict, List


def normalize_identity_part(val: Any) -> str:
    """
    Deterministically normalize an identity component (e.g. Manufacturer or MPN) or classification part.
    Strips leading and trailing whitespace, collapses internal whitespace, and converts to uppercase for case-insensitive matching.
    """
    if val is None:
        return ""
    return " ".join(str(val).split()).upper()


def clean_display_string(val: Any) -> str:
    """
    Strip leading and trailing whitespace while preserving original casing and internal spacing.
    """
    if val is None:
        return ""
    return str(val).strip()


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
class SupplierLink:
    """
    Represents a supplier purchase link associated with a component.
    """
    vendor_id: str
    vendor_label: str
    url: str
    id: Optional[int] = None
    component_id: Optional[int] = None
    display_name: str = ""


def format_supplier_links_as_string(links: Sequence[SupplierLink]) -> str:
    """Format a sequence of SupplierLink instances into the canonical multi-link string."""
    if not links:
        return ""
    if len(links) == 1:
        l = links[0]
        if l.vendor_label:
            return f"{l.vendor_label}={l.url}"
        return l.url
    return " || ".join(f"{l.vendor_label}={l.url}" for l in links)


@dataclass(frozen=True)
class InventoryProduct:
    """
    Individual physical product record from the 'Inventory' sheet or SQLite database.
    Preserves exact manufacturer, MPN, description, physical on-hand quantity,
    and supports both legacy single Purchase Link and normalized supplier links.
    """
    manufacturer: str
    mpn: str
    category: str
    type_technology: str
    package: str  # Normalized package code
    footprint: str
    value: str
    description: str = ""
    quantity_in_stock: int = 0
    purchase_link: Optional[str] = None
    group_key: str = ""
    raw_package: str = ""
    id: Optional[int] = None
    supplier_links: Tuple[SupplierLink, ...] = ()
    norm_manufacturer: str = ""
    norm_mpn: str = ""

    def __post_init__(self):
        if not self.norm_manufacturer:
            object.__setattr__(self, "norm_manufacturer", normalize_identity_part(self.manufacturer))
        if not self.norm_mpn:
            object.__setattr__(self, "norm_mpn", normalize_identity_part(self.mpn))
        if not self.group_key:
            pkg = normalize_package(self.package)
            object.__setattr__(
                self,
                "group_key",
                build_group_key(self.category, self.type_technology, self.value, pkg, self.footprint),
            )

    @property
    def quantity(self) -> int:
        return self.quantity_in_stock

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "manufacturer": self.manufacturer,
            "mpn": self.mpn,
            "norm_manufacturer": self.norm_manufacturer,
            "norm_mpn": self.norm_mpn,
            "category": self.category,
            "type_technology": self.type_technology,
            "package": self.package,
            "raw_package": self.raw_package,
            "footprint": self.footprint,
            "value": self.value,
            "description": self.description,
            "quantity_in_stock": self.quantity_in_stock,
            "purchase_link": self.purchase_link,
            "group_key": self.group_key,
            "supplier_links": [
                {
                    "id": l.id,
                    "vendor_id": l.vendor_id,
                    "vendor_label": l.vendor_label,
                    "url": l.url,
                    "display_name": l.display_name,
                }
                for l in self.supplier_links
            ],
        }


@dataclass(frozen=True)
class StockPolicyRecord:
    """
    Explicit stock policy thresholds and attributes for a 5-dimension group key.
    """
    group_key: str
    category: str
    type_technology: str
    value: str
    package: str
    footprint: str
    min_stock: Optional[int] = None
    target_stock: Optional[int] = None
    description: str = ""


@dataclass(frozen=True)
class ManufacturerRecord:
    """Canonical manufacturer / brand reference record."""
    id: int
    name: str
    norm_name: str
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class CategoryRecord:
    """Canonical category reference record."""
    id: int
    name: str
    norm_name: str
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class TypeRecord:
    """Canonical type / technology reference record associated with a category."""
    id: int
    category_id: int
    name: str
    norm_name: str
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    category_name: Optional[str] = None


@dataclass(frozen=True)
class ProviderRecord:
    """Canonical vendor / link provider reference record."""
    id: int
    provider_id: str
    name: str
    norm_name: str
    label: str
    base_url: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ReferenceDataPayload:
    """Canonical reference entities parsed from the Reference Data sheet."""
    manufacturers: Tuple[str, ...] = ()
    categories: Tuple[str, ...] = ()
    category_types: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StockPolicyGroup:
    """
    Canonical stock-policy group from the 'Stock Policy' sheet or SQLite database.
    Stock Policy is the authoritative source for group identity, aggregated current stock,
    Min Stock, and Target Stock.
    """
    category: str
    type_technology: str
    value: str
    package: str  # Normalized package code
    footprint: str
    current_stock: Optional[int]  # Total Quantity in Stock
    min_stock: Optional[int]      # Min Stock threshold
    target_stock: Optional[int]   # Target Stock threshold
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

    @property
    def is_under_stocked(self) -> bool:
        """Alias for is_low_stock."""
        return self.is_low_stock

    @property
    def shortage_to_min(self) -> int:
        """Number of units needed to bring stock up to min_stock."""
        if self.min_stock is None or self.current_stock is None:
            return 0
        if self.current_stock < self.min_stock:
            return self.min_stock - self.current_stock
        return 0

    @property
    def shortage_to_target(self) -> int:
        """Number of units needed to bring stock up to target_stock."""
        if self.target_stock is None or self.current_stock is None:
            return 0
        if self.current_stock < self.target_stock:
            return self.target_stock - self.current_stock
        return 0


# Database Exceptions
class InventoryDatabaseError(Exception):
    """Base exception for inventory database operations."""
    pass


class ComponentConflictError(InventoryDatabaseError):
    """Raised when a component with identical normalized Manufacturer+MPN already exists."""
    def __init__(
        self,
        message: str,
        existing_component: Optional[Any] = None,
        conflicting_data: Optional[dict] = None,
    ):
        super().__init__(message)
        self.existing_component = existing_component
        self.conflicting_data = conflicting_data


class ComponentNotFoundError(InventoryDatabaseError):
    """Raised when a requested component cannot be found."""
    pass


class ReferenceDataInUseError(InventoryDatabaseError):
    """Raised when attempting to delete a reference entity that is still referenced by components."""
    pass


class ReferenceDataNotFoundError(InventoryDatabaseError):
    """Raised when a referenced manufacturer, category, or type does not exist."""
    pass


class DuplicateReferenceError(InventoryDatabaseError):
    """Raised when creating a reference entity with a duplicate normalized name."""
    pass


class ValidationError(InventoryDatabaseError):
    """Raised when component, threshold, or reference attributes violate business rules."""
    pass

