"""
Omnix Core - Normalized Data Models for Vendor Adapters
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md
"""

from dataclasses import dataclass, field
import datetime
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
    browser_type: Optional[str] = None
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
    raw_data: Dict[str, Any] = field(default_factory=dict)


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


class SessionContinuityMode(str, Enum):
    """
    Formal qualification of browser session continuity across headless and headful transitions.
    Governing Invariant: GAP-09 Session Continuity.
    """
    SAME_CONTEXT_PRESERVED = "SAME_CONTEXT_PRESERVED"
    STATE_TRANSFERRED = "STATE_TRANSFERRED"
    BROWSER_RECREATED_UNAUTHENTICATED = "BROWSER_RECREATED_UNAUTHENTICATED"
    CONTINUITY_UNAVAILABLE = "CONTINUITY_UNAVAILABLE"


@dataclass
class SessionPromotionResult:
    """Outcome of promoting/demoting browser between headless and headful modes."""
    success: bool
    continuity_mode: SessionContinuityMode
    message: str = ""
    cookies_transferred: int = 0
    active_url: Optional[str] = None


@dataclass
class RecoveryResult:
    vendor_id: str
    recovered: bool
    action_taken: str
    message: str


class PluginCapability(str, Enum):
    """
    Canonical fine-grained functional capabilities for Omnix vendor plugins.
    Reconciled with OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 7.1
    and manifest.schema.json.
    """
    # Layer A/B Capabilities (Deterministic offline contracts & mock test harness)
    PRODUCT_URL_RECOGNITION = "PRODUCT_URL_RECOGNITION"
    PRODUCT_INSPECTION = "PRODUCT_INSPECTION"
    CART_URL_RESOLUTION = "CART_URL_RESOLUTION"
    MPN_SEARCH = "MPN_SEARCH"
    LIVE_STOCK_PROBE = "LIVE_STOCK_PROBE"
    TIERED_PRICING = "TIERED_PRICING"
    MODE_A_STAGING = "MODE_A_STAGING"

    # Layer C Capabilities (Live vendor integration, anti-bot, and interactive verification)
    LIVE_CONNECTIVITY_TEST = "LIVE_CONNECTIVITY_TEST"
    LIVE_STRUCTURE_TEST = "LIVE_STRUCTURE_TEST"
    LOGIN_TEST = "LOGIN_TEST"
    CAPTCHA_DETECTION = "CAPTCHA_DETECTION"
    CAPTCHA_HUMAN_ASSIST = "CAPTCHA_HUMAN_ASSIST"
    LIVE_PRODUCT_DISCOVERY = "LIVE_PRODUCT_DISCOVERY"
    LIVE_QUANTITY_VALIDATION = "LIVE_QUANTITY_VALIDATION"
    LIVE_ADD_TO_CART = "LIVE_ADD_TO_CART"


class CapabilityStatus(str, Enum):
    """
    Operational verification status for a plugin capability.
    Mutually exclusive operational states.
    """
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    BLOCKED = "BLOCKED"


class CapabilityBlockingReason(str, Enum):
    """
    Structured reasons explaining why a capability evaluation is BLOCKED.
    Reconciled with OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 7.2.
    """
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    UNVERIFIED_DOMAIN = "UNVERIFIED_DOMAIN"
    PREREQUISITE_GATE_FAILED = "PREREQUISITE_GATE_FAILED"
    REVOCATION_BLACKLISTED = "REVOCATION_BLACKLISTED"
    SECURITY_POLICY_RESTRICTION = "SECURITY_POLICY_RESTRICTION"
    VENDOR_ACCESS_BLOCKED = "VENDOR_ACCESS_BLOCKED"
    OPERATOR_OPT_IN_REQUIRED = "OPERATOR_OPT_IN_REQUIRED"


class PluginProcurementMode(str, Enum):
    """
    Procurement execution modes supported by vendor plugins.
    """
    MODE_A = "MODE_A"


@dataclass
class CapabilityEvaluationRecord:
    """
    Structured record of an individual capability evaluation result.
    Enforces strict consistency between BLOCKED status and blocking_reason,
    and protects against recording sensitive credentials in diagnostic details.
    """
    capability: PluginCapability
    status: CapabilityStatus
    blocking_reason: Optional[CapabilityBlockingReason] = None
    evaluated_at: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.capability, PluginCapability):
            try:
                self.capability = PluginCapability(self.capability)
            except Exception as e:
                raise ValueError(f"Invalid capability: {self.capability}") from e

        if not isinstance(self.status, CapabilityStatus):
            try:
                self.status = CapabilityStatus(self.status)
            except Exception as e:
                raise ValueError(f"Invalid capability status: {self.status}") from e

        if self.blocking_reason is not None and not isinstance(self.blocking_reason, CapabilityBlockingReason):
            try:
                self.blocking_reason = CapabilityBlockingReason(self.blocking_reason)
            except Exception as e:
                raise ValueError(f"Invalid capability blocking reason: {self.blocking_reason}") from e

        if self.status == CapabilityStatus.BLOCKED:
            if self.blocking_reason is None:
                raise ValueError("A BLOCKED capability evaluation record must specify an explicit blocking_reason.")
        else:
            if self.blocking_reason is not None:
                raise ValueError(
                    f"A capability evaluation record with status '{self.status.value}' must not specify a blocking_reason."
                )

        if not self.evaluated_at:
            self.evaluated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Sanitize diagnostic details: forbid keys matching sensitive credential patterns
        sensitive_patterns = ("password", "passwd", "secret", "token", "cookie", "credential")
        if self.details:
            for k in self.details:
                k_lower = str(k).lower()
                if any(p in k_lower for p in sensitive_patterns):
                    raise ValueError(f"Diagnostic details must not contain sensitive credential key '{k}'.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.value,
            "status": self.status.value,
            "blocking_reason": self.blocking_reason.value if self.blocking_reason else None,
            "evaluated_at": self.evaluated_at,
            "details": dict(self.details),
        }
