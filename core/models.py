"""
Omnix Core - Normalized Data Models for Vendor Adapters
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


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


@dataclass
class CartDetails:
    vendor_id: str
    cart_url: str
    total_items: int
    total_amount_irr: Optional[int] = None
    items: List[CartItem] = field(default_factory=list)


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


@dataclass
class AuthCredentials:
    username: str
    password: str
    extra_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class AuthResult:
    vendor_id: str
    success: bool
    message: str
    session_token: Optional[str] = None


@dataclass
class SessionStatus:
    vendor_id: str
    is_authenticated: bool
    username: Optional[str] = None
    session_valid: bool = False
    message: str = ""


@dataclass
class RecoveryResult:
    vendor_id: str
    recovered: bool
    action_taken: str
    message: str
