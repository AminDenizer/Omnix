"""
Omnix Core - Normalized Data Models for Vendor Adapters
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class IdentityMatchTier(Enum):
    """
    Deterministic confidence tiers for cart item matching (GAP-13).
    """
    EXACT_VENDOR_SKU = "EXACT_VENDOR_SKU"
    CANONICAL_PDP_URL = "CANONICAL_PDP_URL"
    MPN_AND_MANUFACTURER = "MPN_AND_MANUFACTURER"
    MPN_ONLY_FALLBACK = "MPN_ONLY_FALLBACK"
    NO_MATCH = "NO_MATCH"



@dataclass
class AdapterConfig:
    vendor_id: str
    base_url: str
    headless: bool = True
    timeout_seconds: float = 10.0
    settle_seconds: float = 2.2
    user_agent: Optional[str] = None
    extra_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VendorSettings:
    """
    Structured configuration settings for an individual vendor adapter.
    Governing GAP: GAP-11.
    """
    vendor_id: str
    enabled: bool = True
    username: str = ""
    password: str = ""
    timeout_seconds: float = 10.0
    headless: bool = True
    extra_options: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        masked_pwd = "***" if self.password else ""
        return (
            f"VendorSettings(vendor_id='{self.vendor_id}', enabled={self.enabled}, "
            f"username='{self.username}', password='{masked_pwd}', "
            f"timeout_seconds={self.timeout_seconds}, headless={self.headless})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "enabled": self.enabled,
            "username": self.username,
            "password": self.password,
            "timeout_seconds": self.timeout_seconds,
            "headless": self.headless,
            "extra_options": dict(self.extra_options),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VendorSettings":
        return cls(
            vendor_id=data.get("vendor_id", ""),
            enabled=data.get("enabled", True),
            username=data.get("username", ""),
            password=data.get("password", ""),
            timeout_seconds=float(data.get("timeout_seconds", 10.0)),
            headless=data.get("headless", True),
            extra_options=data.get("extra_options", {}),
        )


@dataclass
class AdapterStatus:
    vendor_id: str
    is_ready: bool
    is_authenticated: bool
    message: str = ""


@dataclass
class SearchItem:
    vendor_sku: str
    mpn_hint: str
    title: str
    pdp_url: str
    thumbnail_url: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResultSet:
    vendor_id: str
    query: str
    total_matches: int
    is_exact_match: bool
    items: List[SearchItem] = field(default_factory=list)


@dataclass
class ProductReference:
    vendor_id: str
    vendor_sku: str
    pdp_url: str
    product_id: Optional[str] = None
    slug: Optional[str] = None


@dataclass
class OrderConstraints:
    packaging_step_raw: int = 1
    moq_raw: int = 1
    max_orderable_raw: Optional[int] = None


@dataclass
class ProductDetails:
    vendor_id: str
    vendor_sku: str
    pdp_url: str
    stock_quantity: int = 0
    can_order: bool = False
    is_inquiry_only: bool = False
    raw_status_text: str = ""
    price_irr: Optional[int] = None
    mpn: Optional[str] = None
    manufacturer: Optional[str] = None
    package_raw: Optional[str] = None
    order_constraints: OrderConstraints = field(default_factory=OrderConstraints)


@dataclass
class CanonicalComponentDraft:
    vendor_id: str
    vendor_sku: str
    mpn: Optional[str] = None
    manufacturer: Optional[str] = None
    package: Optional[str] = None
    description: Optional[str] = None
    specs: Dict[str, str] = field(default_factory=dict)


@dataclass
class StockStatus:
    vendor_id: str
    vendor_sku: str
    stock_quantity: int
    in_stock: bool
    can_order: bool
    is_inquiry_only: bool = False
    is_restock_pipeline: bool = False
    raw_text: str = ""


@dataclass
class CartItem:
    vendor_sku: str
    product_name: str
    quantity: int
    unit_price_irr: Optional[int] = None
    total_price_irr: Optional[int] = None
    pdp_url: Optional[str] = None
    mpn: Optional[str] = None
    manufacturer: Optional[str] = None


@dataclass
class CartDetails:
    vendor_id: str
    cart_url: str
    total_items: int
    total_amount_irr: Optional[int] = None
    items: List[CartItem] = field(default_factory=list)

    def find_items_by_sku(self, sku: str) -> List[CartItem]:
        norm = (sku or "").strip().upper()
        return [item for item in self.items if (item.vendor_sku or "").strip().upper() == norm]

    def get_total_quantity_for_sku(self, sku: str) -> int:
        return sum(item.quantity for item in self.find_items_by_sku(sku))


@dataclass
class CartMutationResult:
    vendor_id: str
    vendor_sku: str
    requested_quantity: int
    actual_quantity_staged: int
    success: bool
    error_category: Optional[str] = None
    raw_vendor_message: str = ""
    cart_total_items: int = 0
    initial_cart_qty: int = 0
    target_qty: int = 0
    delta_qty: int = 0
    is_noop: bool = False
    match_tier: Optional[IdentityMatchTier] = None
    match_confidence: str = "NONE"



@dataclass
class AuthCredentials:
    username: str
    password: str
    extra_fields: Dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        masked_pwd = "***" if self.password else ""
        return f"AuthCredentials(username='{self.username}', password='{masked_pwd}', extra_fields={self.extra_fields})"


@dataclass
class AuthResult:
    vendor_id: str
    success: bool
    message: str
    session_token: Optional[str] = None
    requires_interactive: bool = False
    challenge_context: Optional[Any] = None


@dataclass
class SessionStatus:
    vendor_id: str
    is_authenticated: bool
    username: Optional[str] = None
    session_valid: bool = False
    message: str = ""
    requires_interactive: bool = False


@dataclass
class RecoveryResult:
    vendor_id: str
    recovered: bool
    action_taken: str
    message: str
