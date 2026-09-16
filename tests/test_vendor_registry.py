"""
Deterministic Unit Tests for VendorRegistry
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 15
"""

import threading
import pytest
from typing import Optional, Dict, Any

from core.errors import UnknownVendorError
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
from core.procurement.registry import VendorRegistry, VendorRegistration
from core.vendor_interface import IVendorAdapter


class MockVendorAdapterA(IVendorAdapter):
    VENDOR_ID = "vendor_mock_a"
    BASE_URL = "https://mocka.example.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config
        self._initialized = False

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        self._initialized = True
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=False)

    def search_part(self, query: str) -> SearchResultSet:
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False)

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="SKU1", pdp_url="https://mocka.example.com/p/1")

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(vendor_id=self.VENDOR_ID, vendor_sku="SKU1", pdp_url="https://mocka.example.com/p/1")

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(vendor_id=self.VENDOR_ID, vendor_sku="SKU1")

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        return StockStatus(vendor_id=self.VENDOR_ID, vendor_sku="SKU1", stock_quantity=10, in_stock=True, can_order=True)

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=1, moq_raw=1)

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        return CartMutationResult(vendor_id=self.VENDOR_ID, vendor_sku="SKU1", requested_quantity=quantity, actual_quantity_staged=quantity, success=True)

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url="https://mocka.example.com/cart", total_items=0)

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="noop", message="OK")

    def close(self) -> None:
        self._initialized = False


class MockVendorAdapterB(MockVendorAdapterA):
    VENDOR_ID = "vendor_mock_b"
    BASE_URL = "https://store.mockb.org"


class TestVendorRegistryRegistration:
    """Verify adapter registration, duplicate rejection, and type safety."""

    def test_register_vendor_successfully(self):
        registry = VendorRegistry()
        registry.register_adapter(
            vendor_id="vendor_mock_a",
            adapter_class=MockVendorAdapterA,
            domains=["mocka.example.com"],
            display_name="Mock Vendor A",
        )

        assert registry.has_vendor("vendor_mock_a") is True
        assert registry.list_vendors() == ["vendor_mock_a"]

        reg = registry.get_registration("vendor_mock_a")
        assert reg.vendor_id == "vendor_mock_a"
        assert reg.display_name == "Mock Vendor A"
        assert "mocka.example.com" in reg.domains

    def test_duplicate_vendor_registration_raises_value_error(self):
        registry = VendorRegistry()
        registry.register_adapter("vendor_mock_a", MockVendorAdapterA, domains=["mocka.example.com"])

        with pytest.raises(ValueError, match="already registered"):
            registry.register_adapter("vendor_mock_a", MockVendorAdapterA, domains=["mocka.example.com"])

    def test_invalid_vendor_id_raises_value_error(self):
        registry = VendorRegistry()
        with pytest.raises(ValueError, match="non-empty string"):
            registry.register_adapter("", MockVendorAdapterA)
        with pytest.raises(ValueError, match="non-empty string"):
            registry.register_adapter(None, MockVendorAdapterA)

    def test_invalid_adapter_class_raises_value_error(self):
        registry = VendorRegistry()
        class NotAnAdapter:
            pass

        with pytest.raises(ValueError, match="subclass of IVendorAdapter"):
            registry.register_adapter("vendor_invalid", NotAnAdapter)


class TestVendorRegistryLookupAndFactory:
    """Verify deterministic instantiation, config propagation, and error handling."""

    def test_get_adapter_instantiates_correct_class(self):
        registry = VendorRegistry()
        registry.register_adapter("vendor_mock_a", MockVendorAdapterA)

        adapter = registry.get_adapter("vendor_mock_a")
        assert isinstance(adapter, MockVendorAdapterA)
        assert adapter.vendor_id == "vendor_mock_a"
        assert adapter.base_url == "https://mocka.example.com"

    def test_get_adapter_passes_custom_config(self):
        registry = VendorRegistry()
        default_cfg = AdapterConfig(vendor_id="vendor_mock_a", base_url="https://mocka.example.com", timeout_seconds=5.0)
        registry.register_adapter("vendor_mock_a", MockVendorAdapterA, config=default_cfg)

        # 1. With default config
        a1 = registry.get_adapter("vendor_mock_a")
        assert a1._config.timeout_seconds == 5.0

        # 2. With override config
        override_cfg = AdapterConfig(vendor_id="vendor_mock_a", base_url="https://mocka.example.com", timeout_seconds=12.0)
        a2 = registry.get_adapter("vendor_mock_a", config=override_cfg)
        assert a2._config.timeout_seconds == 12.0

    def test_unknown_vendor_raises_unknown_vendor_error(self):
        registry = VendorRegistry()
        with pytest.raises(UnknownVendorError) as exc_info:
            registry.get_adapter("vendor_nonexistent")
        assert exc_info.value.vendor_id == "vendor_nonexistent"

    def test_get_registration_unknown_vendor_raises(self):
        registry = VendorRegistry()
        with pytest.raises(UnknownVendorError):
            registry.get_registration("vendor_ghost")


class TestVendorRegistryURLRouting:
    """Verify deterministic URL-based vendor identification and edge cases."""

    @pytest.fixture
    def populated_registry(self):
        registry = VendorRegistry()
        registry.register_adapter("vendor_mock_a", MockVendorAdapterA, domains=["mocka.example.com"])
        registry.register_adapter("vendor_mock_b", MockVendorAdapterB, domains=["mockb.org"])
        return registry

    def test_url_routing_exact_domain(self, populated_registry):
        assert populated_registry.get_vendor_for_url("https://mocka.example.com/products/123") == "vendor_mock_a"
        assert populated_registry.get_vendor_for_url("https://mockb.org/item/456") == "vendor_mock_b"

    def test_url_routing_subdomain_support(self, populated_registry):
        assert populated_registry.get_vendor_for_url("https://shop.mocka.example.com/p/1") == "vendor_mock_a"
        assert populated_registry.get_vendor_for_url("https://auth.mockb.org/login") == "vendor_mock_b"

    def test_url_routing_normalizes_case_and_protocol(self, populated_registry):
        assert populated_registry.get_vendor_for_url("HTTP://WWW.MOCKA.EXAMPLE.COM/part") == "vendor_mock_a"
        assert populated_registry.get_vendor_for_url("http://mockb.org/") == "vendor_mock_b"
        assert populated_registry.get_vendor_for_url("www.mocka.example.com") == "vendor_mock_a"

    def test_unknown_domain_returns_none(self, populated_registry):
        assert populated_registry.get_vendor_for_url("https://example.com/item") is None
        assert populated_registry.get_vendor_for_url("https://google.com") is None
        assert populated_registry.get_vendor_for_url("") is None
        assert populated_registry.get_vendor_for_url(None) is None

    def test_similar_domain_does_not_false_positive(self, populated_registry):
        # Must not match mocka.example.com when target is fake-mocka.example.com
        assert populated_registry.get_vendor_for_url("https://fake-mocka.example.com/p") is None
        assert populated_registry.get_vendor_for_url("https://mocka.example.com.attacker.com/p") is None
        assert populated_registry.get_vendor_for_url("https://notmockb.org") is None


class TestVendorRegistryProductionAdapters:
    """Verify registration and routing of the three production adapters: Lion, Javan, RoboEq."""

    def test_register_default_production_adapters(self):
        registry = VendorRegistry()
        registry.register_default_adapters()

        registered = registry.list_vendors()
        assert "vendor_lion" in registered
        assert "vendor_javan" in registered
        assert "vendor_roboeq" in registered
        assert len(registered) == 3

    def test_production_adapters_url_routing(self):
        registry = VendorRegistry()
        registry.register_default_adapters()

        # Lion Electronic
        assert registry.get_vendor_for_url("https://lionelectronic.ir/products/detail/0201016") == "vendor_lion"
        assert registry.get_vendor_for_url("http://www.lionelectronic.ir/orders/cart") == "vendor_lion"

        # Javan Electronic
        assert registry.get_vendor_for_url("https://javanelec.com/shop/product/17930/ti/ne555p") == "vendor_javan"
        assert registry.get_vendor_for_url("https://www.javanelec.com/search?q=LM358") == "vendor_javan"

        # RoboEq Electronic
        assert registry.get_vendor_for_url("https://roboeq.ir/products/detail/0201016/") == "vendor_roboeq"
        assert registry.get_vendor_for_url("https://auth.roboeq.ir/cas/login") == "vendor_roboeq"

    def test_production_adapter_instantiation_contract(self):
        registry = VendorRegistry()
        registry.register_default_adapters()

        lion = registry.get_adapter("vendor_lion")
        javan = registry.get_adapter("vendor_javan")
        roboeq = registry.get_adapter("vendor_roboeq")

        assert isinstance(lion, IVendorAdapter)
        assert isinstance(javan, IVendorAdapter)
        assert isinstance(roboeq, IVendorAdapter)

        assert lion.vendor_id == "vendor_lion"
        assert javan.vendor_id == "vendor_javan"
        assert roboeq.vendor_id == "vendor_roboeq"


class TestVendorRegistryThreadSafety:
    """Verify concurrent registration and lookup safety."""

    def test_concurrent_registration_and_lookups(self):
        registry = VendorRegistry()
        errors = []

        def worker_register(idx):
            try:
                vid = f"vendor_thread_{idx}"
                # Subclass dynamically
                mock_cls = type(f"DynamicAdapter{idx}", (MockVendorAdapterA,), {"VENDOR_ID": vid})
                registry.register_adapter(vid, mock_cls, domains=[f"thread{idx}.com"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_register, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(registry.list_vendors()) == 20

        # Concurrent reads
        def worker_read(idx):
            try:
                vid = f"vendor_thread_{idx}"
                a = registry.get_adapter(vid)
                assert a.vendor_id == vid
                assert registry.get_vendor_for_url(f"https://thread{idx}.com/p/1") == vid
            except Exception as e:
                errors.append(e)

        read_threads = [threading.Thread(target=worker_read, args=(i,)) for i in range(20)]
        for t in read_threads:
            t.start()
        for t in read_threads:
            t.join()

        assert len(errors) == 0
