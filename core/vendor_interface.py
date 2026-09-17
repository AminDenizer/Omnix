"""
Omnix Core - Vendor Adapter Interface Contract (IVendorAdapter)
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md Section 2
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

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
)


class IVendorAdapter(ABC):
    """
    Abstract Base Class for all Omnix Vendor Adapters.
    Defines the 13 conceptual operations required for vendor interactions.
    """

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
