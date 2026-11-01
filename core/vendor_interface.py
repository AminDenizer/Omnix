"""
Omnix Core - Vendor Adapter Interface Contract (IVendorAdapter)
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md Section 2
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Set, FrozenSet, Tuple, Union, List

from core.models import (
    AdapterConfig,
    AdapterStatus,
    SearchResultSet,
    ProductReference,
    ProductDetails,
    CanonicalComponentDraft,
    StockStatus,
    OrderConstraints,
    CartMutationResult,
    CartDetails,
    AuthCredentials,
    AuthResult,
    SessionStatus,
    RecoveryResult,
    PluginCapability,
    CapabilityStatus,
    CapabilityBlockingReason,
    PluginProcurementMode,
    CapabilityEvaluationRecord,
)


class IVendorAdapter(ABC):
    """
    Abstract Base Class for all Omnix Vendor Adapters.
    Defines the 13 conceptual operations required for vendor interactions.
    """

    _SUPPORTED_CAPABILITIES: FrozenSet[PluginCapability] = frozenset()
    _SUPPORTED_MODES: FrozenSet[PluginProcurementMode] = frozenset()

    @property
    @abstractmethod
    def vendor_id(self) -> str:
        """Unique identifier for the vendor (e.g., 'vendor_lion')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base storefront URL for the vendor."""
        pass

    @abstractmethod
    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        """
        Initialize the adapter, configure browser session or driver context.
        """
        pass

    @abstractmethod
    def search_part(self, query: str) -> SearchResultSet:
        """
        Execute catalog search on vendor platform and return normalized candidate matches.
        """
        pass

    @abstractmethod
    def resolve_product(self, url_or_sku: str) -> ProductReference:
        """
        Resolve a URL or vendor SKU to a standardized ProductReference.
        """
        pass

    @abstractmethod
    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        """
        Navigate to and extract complete product details, specifications, and constraints.
        """
        pass

    @abstractmethod
    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        """
        Extract canonical component draft data from a loaded PDP DOM tree or HTML string.
        """
        pass

    @abstractmethod
    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        """
        Inspect live stock availability, ordering capability, and inquiry status.
        """
        pass

    @abstractmethod
    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        """
        Extract raw packaging step, MOQ, and maximum orderable limits.
        """
        pass

    @abstractmethod
    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        """
        Mutate browser cart by adding requested quantity of the specified product.
        """
        pass

    @abstractmethod
    def inspect_cart(self) -> CartDetails:
        """
        Inspect current shopping cart items, staged quantities, and total amount.
        """
        pass

    @abstractmethod
    def authenticate(
        self,
        credentials: Optional[AuthCredentials] = None,
        challenge_handler: Optional[Any] = None,
    ) -> AuthResult:
        """
        Authenticate browser session using provided or configured credentials,
        with optional interactive challenge handler for CAPTCHA/OTP resolution.
        Governing GAPs: GAP-09, GAP-17.
        """
        pass

    @abstractmethod
    def validate_session(self) -> SessionStatus:
        """
        Verify whether the current browser session is actively authenticated.
        """
        pass

    @abstractmethod
    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        """
        Attempt recovery from modal popups, dialogs, or transient errors.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Cleanly terminate driver, release browser resources, and close session.
        """
        pass

    def get_cart_url(self) -> Optional[str]:
        """
        Return the storefront cart URL for browser navigation and user review.
        Base implementation returns None. Every adapter must explicitly provide its correct cart URL.
        """
        return None

    def is_pdp_url(self, url: str) -> bool:
        """
        Check whether the given storefront URL matches a canonical Product Detail Page (PDP).
        Default implementation returns False (strict non-permissive rejection).
        """
        return False

    def get_supported_capabilities(self) -> Set[PluginCapability]:
        """
        Return the set of fine-grained functional capabilities explicitly declared
        and supported by this adapter.
        Base implementation returns an empty set (fail-closed).
        """
        return set(self._SUPPORTED_CAPABILITIES)

    def supports_capability(self, capability: Union[PluginCapability, str]) -> bool:
        """
        Query whether this adapter explicitly declares and supports the given capability.
        Performs no I/O, network requests, or browser activity.
        Fails closed (returns False) for unknown, unparseable, or undeclared capabilities.
        """
        if not isinstance(capability, PluginCapability):
            try:
                capability = PluginCapability(str(capability))
            except (ValueError, TypeError):
                return False
        return capability in self.get_supported_capabilities()

    def get_supported_modes(self) -> Set[PluginProcurementMode]:
        """
        Return the set of procurement modes supported by this adapter (e.g. MODE_A).
        Base implementation returns an empty set (fail-closed).
        """
        return set(self._SUPPORTED_MODES)

    def validate_capability_consistency(self) -> List[str]:
        """
        Validate consistency between declared capabilities and supported procurement modes.
        Returns a list of error descriptions (empty if consistent).
        """
        return validate_capability_mode_consistency(
            self.get_supported_capabilities(),
            self.get_supported_modes(),
        )


def validate_capability_mode_consistency(
    capabilities: Set[PluginCapability],
    modes: Set[PluginProcurementMode],
) -> List[str]:
    """
    Enforce capability and procurement mode consistency invariants:
    - Declaring MODE_A_STAGING requires MODE_A in supported modes.
    Returns a list of violation error strings (empty list if valid).
    """
    errors: List[str] = []
    if PluginCapability.MODE_A_STAGING in capabilities and PluginProcurementMode.MODE_A not in modes:
        errors.append("Declaring MODE_A_STAGING requires MODE_A in supported procurement modes.")
    return errors


CAPABILITY_METHOD_MAP: Dict[PluginCapability, Tuple[str, ...]] = {
    # Layer A/B Capabilities (Mapped to real, concrete IVendorAdapter operations)
    PluginCapability.PRODUCT_URL_RECOGNITION: ("is_pdp_url",),
    PluginCapability.PRODUCT_INSPECTION: ("inspect_product", "extract_product_data", "determine_order_constraints"),
    PluginCapability.CART_URL_RESOLUTION: ("get_cart_url",),
    PluginCapability.MPN_SEARCH: ("search_part",),
    PluginCapability.LIVE_STOCK_PROBE: ("inspect_stock",),
    PluginCapability.TIERED_PRICING: ("inspect_product",),
    PluginCapability.MODE_A_STAGING: ("add_to_cart",),

    # Layer C Capabilities (Live verification boundaries; no direct adapter methods exist in Phase 2.
    # Verification belongs to the dedicated Layer C Live Test Runner scheduled for Phase 9+)
    PluginCapability.LIVE_CONNECTIVITY_TEST: (),
    PluginCapability.LIVE_STRUCTURE_TEST: (),
    PluginCapability.LOGIN_TEST: (),
    PluginCapability.CAPTCHA_DETECTION: (),
    PluginCapability.CAPTCHA_HUMAN_ASSIST: (),
    PluginCapability.LIVE_PRODUCT_DISCOVERY: (),
    PluginCapability.LIVE_QUANTITY_VALIDATION: (),
    PluginCapability.LIVE_ADD_TO_CART: (),
}

