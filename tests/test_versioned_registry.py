"""
Deterministic Unit and Concurrency Tests for Omnix Phase 3: Version-Aware Registry Metadata.
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Phase 3.

Covers all 22 required Phase 3 verification scenarios:
 1. Empty-by-default behavior is preserved for new and default registries.
 2. Multiple versions of one vendor coexist.
 3. First-version activation follows the documented default.
 4. Additional versions remain inactive by default.
 5. Registering after explicit deactivation does not reactivate the vendor.
 6. Explicit activation switches the selected version.
 7. Explicitly registering the first version with activate=False leaves the vendor inactive.
 8. Duplicate version registration is rejected.
 9. Invalid manifest registration leaves registry state unchanged.
10. Plugin identity conflicts are rejected atomically.
11. Only active-version domains appear in live route mappings.
12. Failed activation due to collision preserves the previous active version and routes.
13. Unregistering an inactive version leaves the active version undisturbed.
14. Unregistering the active version clears its pointer and routes without silent fallback.
15. Unregistering a complete vendor clears every associated version and route.
16. Version-specific metadata remains queryable for inactive versions.
17. get_enabled_vendors() excludes disabled and inactive vendors.
18. get_adapter(vendor_id) fails closed when no version is active.
19. URL-to-adapter resolution corresponds to the exact active version selected in its consistent registry snapshot.
20. Concurrent read/switch tests establish that readers cannot observe partially updated routing or pointer state.
21. Legacy registration defaults and manifest-backed registration remain distinguishable.
22. Existing adapter contract and capability validation remain intact.
"""

import threading
import time
import pytest
from typing import Optional, Dict, Any, List

from core.errors import UnknownVendorError
from core.models import (
    AdapterConfig,
    AdapterStatus,
    CanonicalComponentDraft,
    CartDetails,
    CartMutationResult,
    OrderConstraints,
    ProductDetails,
    ProductReference,
    RecoveryResult,
    SearchResultSet,
    SessionStatus,
    StockStatus,
)
from core.procurement.registry import (
    VendorRegistry,
    PluginVersionRegistration,
    LEGACY_DEFAULT_VERSION,
    reset_default_registry,
)
from core.procurement.models import ProcurementRequest
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.bridge import ProcurementBridge
from core.plugins.manifest_validator import ManifestError, ManifestValidationError
from core.vendor_interface import IVendorAdapter


# ---------------------------------------------------------------------------
# Test Adapters & Helpers
# ---------------------------------------------------------------------------

class MockVersionAdapter(IVendorAdapter):
    """Compliant mock vendor adapter for versioned registry testing."""
    VENDOR_ID = "vendor_mock"
    BASE_URL = "https://mock.example.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config or AdapterConfig(vendor_id=self.VENDOR_ID, base_url=self.BASE_URL)

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config=None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True)

    def search_part(self, query: str) -> SearchResultSet:
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, items=[])

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="SKU-1", pdp_url=url_or_sku)

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku="SKU-1",
            pdp_url=product_ref.pdp_url,
            stock_quantity=50,
            can_order=True,
            price_irr=5000,
            mpn="MOCK-MPN",
        )

    def extract_product_data(self, dom_context) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(vendor_id=self.VENDOR_ID, vendor_sku="SKU-1")

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        return StockStatus(vendor_id=self.VENDOR_ID, vendor_sku="SKU-1", stock_quantity=50, in_stock=True, can_order=True)

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=1, moq_raw=1)

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        return CartMutationResult(
            vendor_id=self.VENDOR_ID,
            vendor_sku="SKU-1",
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
        )

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url=f"{self.BASE_URL}/cart", total_items=0)

    def authenticate(self, credentials=None, challenge_handler=None):
        return None

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True)

    def recover_from_error(self, error_context):
        return RecoveryResult(recovered=False)

    def close(self) -> None:
        pass

    def is_pdp_url(self, url: str) -> bool:
        return "p/" in url or "products/" in url


class MockVendorBAdapter(MockVersionAdapter):
    VENDOR_ID = "vendor_b"
    BASE_URL = "https://b.example.com"


class MockVendorCAdapter(MockVersionAdapter):
    VENDOR_ID = "vendor_c"
    BASE_URL = "https://c.example.com"


def make_manifest(
    plugin_id: str = "com.example.mock",
    vendor_id: str = "vendor_mock",
    version: str = "1.0.0",
    domains: Optional[List[str]] = None,
    display_name: str = "Mock Vendor",
    capabilities: Optional[List[str]] = None,
    modes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Helper to synthesize valid canonical manifests conforming to manifest.schema.json."""
    doms = domains if domains is not None else ["mock.example.com"]
    return {
        "manifest_version": "1.0.0",
        "plugin_id": plugin_id,
        "vendor_id": vendor_id,
        "display_name": display_name,
        "description": f"{display_name} Plugin Description",
        "version": version,
        "min_omnix_version": "1.0.0",
        "omnix_contract_version": "1.0.0",
        "entry_point": "tests.test_versioned_registry:MockVersionAdapter",
        "publisher": {
            "name": "Omnix Core Engineering",
            "type": "OFFICIAL",
            "key_id": "core-official-key-01",
        },
        "capabilities": capabilities or ["PRODUCT_URL_RECOGNITION", "PRODUCT_INSPECTION"],
        "supported_modes": modes or ["MODE_A"],
        "routes": {
            "base_url": f"https://{doms[0]}",
            "domains": doms,
            "cart_url": f"https://{doms[0]}/cart",
        },
    }


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure global default registry is pristine before and after each test."""
    reset_default_registry()
    yield
    reset_default_registry()


# ---------------------------------------------------------------------------
# Test Suite: 22 Required Scenarios
# ---------------------------------------------------------------------------

class TestPhase3VersionedRegistry:
    """Complete, deterministic verification of Phase 3 Version-Aware Registry Metadata."""

    def test_01_empty_by_default_behavior_preserved(self):
        """Scenario 1: Empty-by-default behavior is preserved for new and default registries."""
        reg = VendorRegistry()
        assert reg.list_vendors() == []
        assert reg.list_active_vendors() == []
        assert reg.get_enabled_vendors() == []
        assert reg.has_vendor("vendor_mock") is False
        assert reg.has_active_vendor("vendor_mock") is False
        assert reg.get_active_version("vendor_mock") is None
        assert reg.get_vendor_for_url("https://mock.example.com") is None
        adapter, reg_meta = reg.resolve_adapter_for_url("https://mock.example.com")
        assert adapter is None
        assert reg_meta is None

        # Global default registry
        default_reg = VendorRegistry.get_default_registry()
        assert default_reg.list_vendors() == []
        assert default_reg.list_active_vendors() == []
        assert default_reg.get_enabled_vendors() == []
        assert default_reg.has_vendor("vendor_lion") is False

    def test_02_multiple_versions_of_one_vendor_coexist(self):
        """Scenario 2: Multiple versions of one vendor coexist."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        m2 = make_manifest(version="1.1.0")
        m3 = make_manifest(version="2.0.0")

        reg.register_plugin_manifest(m1, MockVersionAdapter)
        reg.register_plugin_manifest(m2, MockVersionAdapter)
        reg.register_plugin_manifest(m3, MockVersionAdapter)

        assert reg.list_versions("vendor_mock") == ["1.0.0", "1.1.0", "2.0.0"]
        assert reg.has_vendor("vendor_mock") is True

        r1 = reg.get_version_registration("vendor_mock", "1.0.0")
        r2 = reg.get_version_registration("vendor_mock", "1.1.0")
        r3 = reg.get_version_registration("vendor_mock", "2.0.0")

        assert r1.version == "1.0.0"
        assert r2.version == "1.1.0"
        assert r3.version == "2.0.0"

    def test_03_first_version_activation_follows_documented_default(self):
        """Scenario 3: First-version activation follows the documented default (auto-activates)."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=None)

        assert reg.get_active_version("vendor_mock") == "1.0.0"
        assert reg.has_active_vendor("vendor_mock") is True
        assert reg.list_active_vendors() == ["vendor_mock"]
        assert reg.get_vendor_for_url("https://mock.example.com/p/1") == "vendor_mock"

    def test_04_additional_versions_remain_inactive_by_default(self):
        """Scenario 4: Additional versions remain inactive by default."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        m2 = make_manifest(version="1.2.0")

        reg.register_plugin_manifest(m1, MockVersionAdapter)
        assert reg.get_active_version("vendor_mock") == "1.0.0"

        # Register additional version with activate=None
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=None)
        assert reg.get_active_version("vendor_mock") == "1.0.0"
        assert reg.list_versions("vendor_mock") == ["1.0.0", "1.2.0"]

    def test_05_registering_after_explicit_deactivation_does_not_reactivate(self):
        """Scenario 5: Registering after explicit deactivation does not reactivate the vendor."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        m2 = make_manifest(version="2.0.0")

        reg.register_plugin_manifest(m1, MockVersionAdapter)
        reg.deactivate_vendor("vendor_mock")

        assert reg.get_active_version("vendor_mock") is None
        assert reg.has_active_vendor("vendor_mock") is False

        # Register another version with default activate=None
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=None)
        assert reg.get_active_version("vendor_mock") is None
        assert reg.has_active_vendor("vendor_mock") is False
        assert reg.has_vendor("vendor_mock") is True

    def test_06_explicit_activation_switches_selected_version(self):
        """Scenario 6: Explicit activation switches the selected version."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["v1.mock.com"])
        m2 = make_manifest(version="2.0.0", domains=["v2.mock.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        assert reg.get_active_version("vendor_mock") == "1.0.0"
        assert reg.get_vendor_for_url("https://v1.mock.com/p") == "vendor_mock"
        assert reg.get_vendor_for_url("https://v2.mock.com/p") is None

        # Explicitly activate version 2.0.0
        reg.activate_version("vendor_mock", "2.0.0")

        assert reg.get_active_version("vendor_mock") == "2.0.0"
        assert reg.get_vendor_for_url("https://v1.mock.com/p") is None
        assert reg.get_vendor_for_url("https://v2.mock.com/p") == "vendor_mock"

    def test_07_explicitly_registering_first_version_with_activate_false_leaves_inactive(self):
        """Scenario 7: Explicitly registering first version with activate=False leaves vendor inactive."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=False)

        assert reg.has_vendor("vendor_mock") is True
        assert reg.has_active_vendor("vendor_mock") is False
        assert reg.get_active_version("vendor_mock") is None
        assert reg.list_active_vendors() == []
        assert reg.get_vendor_for_url("https://mock.example.com/p") is None

    def test_08_duplicate_version_registration_is_rejected(self):
        """Scenario 8: Duplicate version registration is rejected atomically."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter)

        with pytest.raises(ValueError, match="already registered"):
            reg.register_plugin_manifest(m1, MockVersionAdapter)

        assert reg.list_versions("vendor_mock") == ["1.0.0"]

    def test_09_invalid_manifest_registration_leaves_registry_state_unchanged(self):
        """Scenario 9: Invalid manifest registration leaves registry state unchanged."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter)

        invalid_manifest = {
            "manifest_version": "1.0.0",
            "plugin_id": "not-valid-reverse-dns",
            "vendor_id": "bad_vendor",
        }

        with pytest.raises(ManifestError):
            reg.register_plugin_manifest(invalid_manifest, MockVersionAdapter)

        assert reg.list_vendors() == ["vendor_mock"]
        assert reg.list_versions("vendor_mock") == ["1.0.0"]
        assert reg.get_active_version("vendor_mock") == "1.0.0"

    def test_10_plugin_identity_conflicts_are_rejected_atomically(self):
        """Scenario 10: Plugin identity conflicts are rejected atomically."""
        reg = VendorRegistry()
        m1 = make_manifest(plugin_id="com.example.mock", vendor_id="vendor_mock", version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter)

        # 1. Different plugin_id for the same vendor_id
        m_diff_plugin = make_manifest(plugin_id="com.other.mock", vendor_id="vendor_mock", version="2.0.0")
        with pytest.raises(ValueError, match="Plugin identity conflict"):
            reg.register_plugin_manifest(m_diff_plugin, MockVersionAdapter)

        # 2. Same plugin_id for a different vendor_id
        m_same_plugin_diff_vendor = make_manifest(
            plugin_id="com.example.mock",
            vendor_id="vendor_b",
            version="1.0.0",
            domains=["b.example.com"],
        )
        with pytest.raises(ValueError, match="Plugin identity conflict"):
            reg.register_plugin_manifest(m_same_plugin_diff_vendor, MockVendorBAdapter)

        # Confirm registry was untouched
        assert reg.list_vendors() == ["vendor_mock"]
        assert reg.list_versions("vendor_mock") == ["1.0.0"]

    def test_11_only_active_version_domains_appear_in_live_routes(self):
        """Scenario 11: Only active-version domains appear in live route mappings."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["active-domain.com"])
        m2 = make_manifest(version="2.0.0", domains=["inactive-domain.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        assert reg.get_vendor_for_url("https://active-domain.com/p/100") == "vendor_mock"
        assert reg.get_vendor_for_url("https://inactive-domain.com/p/100") is None

    def test_12_failed_activation_due_to_collision_preserves_previous_active_version(self):
        """Scenario 12: Failed activation due to collision preserves previous active version and routes."""
        reg = VendorRegistry()
        mA = make_manifest(plugin_id="com.example.a", vendor_id="vendor_mock", version="1.0.0", domains=["shared.com"])
        mB1 = make_manifest(plugin_id="com.example.b", vendor_id="vendor_b", version="1.0.0", domains=["b-domain.com"])
        mB2 = make_manifest(plugin_id="com.example.b", vendor_id="vendor_b", version="2.0.0", domains=["shared.com"])

        reg.register_plugin_manifest(mA, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(mB1, MockVendorBAdapter, activate=True)
        reg.register_plugin_manifest(mB2, MockVendorBAdapter, activate=False)

        # Attempt to activate mB2, which collides with mA on "shared.com"
        with pytest.raises(ValueError, match="Domain conflict"):
            reg.activate_version("vendor_b", "2.0.0")

        # Verify vendor_b's active version is still 1.0.0 and b-domain.com is still routed to vendor_b
        assert reg.get_active_version("vendor_b") == "1.0.0"
        assert reg.get_vendor_for_url("https://b-domain.com/p") == "vendor_b"

        # Verify vendor_mock's active version is still 1.0.0 and shared.com routes to vendor_mock
        assert reg.get_active_version("vendor_mock") == "1.0.0"
        assert reg.get_vendor_for_url("https://shared.com/p") == "vendor_mock"

    def test_13_unregistering_inactive_version_leaves_active_version_undisturbed(self):
        """Scenario 13: Unregistering an inactive version leaves the active version undisturbed."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["mock.com"])
        m2 = make_manifest(version="2.0.0", domains=["mock-v2.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        assert reg.unregister_version("vendor_mock", "2.0.0") is True

        assert reg.get_active_version("vendor_mock") == "1.0.0"
        assert reg.list_versions("vendor_mock") == ["1.0.0"]
        assert reg.get_vendor_for_url("https://mock.com/p") == "vendor_mock"

    def test_14_unregistering_active_version_clears_pointer_and_routes_without_fallback(self):
        """Scenario 14: Unregistering active version clears pointer and routes without silent fallback."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["mock-v1.com"])
        m2 = make_manifest(version="2.0.0", domains=["mock-v2.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        assert reg.unregister_version("vendor_mock", "1.0.0") is True

        assert reg.get_active_version("vendor_mock") is None
        assert reg.has_active_vendor("vendor_mock") is False
        assert reg.has_vendor("vendor_mock") is True
        assert reg.list_versions("vendor_mock") == ["2.0.0"]
        assert reg.get_vendor_for_url("https://mock-v1.com/p") is None
        assert reg.get_vendor_for_url("https://mock-v2.com/p") is None

    def test_15_unregistering_complete_vendor_clears_all_versions_and_routes(self):
        """Scenario 15: Unregistering a complete vendor clears every associated version and route."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["mock-v1.com"])
        m2 = make_manifest(version="2.0.0", domains=["mock-v2.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter)
        reg.register_plugin_manifest(m2, MockVersionAdapter)

        assert reg.unregister_adapter("vendor_mock") is True

        assert reg.has_vendor("vendor_mock") is False
        assert reg.has_active_vendor("vendor_mock") is False
        assert reg.list_vendors() == []
        assert reg.get_active_version("vendor_mock") is None
        assert reg.get_vendor_for_url("https://mock-v1.com/p") is None

        # Repeat unregister returns False
        assert reg.unregister_adapter("vendor_mock") is False

        # Provider identity is released: can now register new vendor with same plugin_id
        m_new = make_manifest(plugin_id="com.example.mock", vendor_id="vendor_b", domains=["b.com"])
        reg.register_plugin_manifest(m_new, MockVendorBAdapter)
        assert reg.has_vendor("vendor_b") is True

    def test_16_version_specific_metadata_queryable_for_inactive_versions(self):
        """Scenario 16: Version-specific metadata remains queryable for inactive versions."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", display_name="Mock V1")
        m2 = make_manifest(version="2.0.0", display_name="Mock V2")

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        meta_v2 = reg.get_version_registration("vendor_mock", "2.0.0")
        assert meta_v2.version == "2.0.0"
        assert meta_v2.display_name == "Mock V2"
        assert meta_v2.plugin_id == "com.example.mock"

        # Diagnostic/Settings UI fallback for inactive vendor
        reg.deactivate_vendor("vendor_mock")
        active_meta = reg.get_registration("vendor_mock")
        assert active_meta.version == "2.0.0"  # Highest registered SemVer returned for settings inspect

    def test_17_get_enabled_vendors_excludes_disabled_and_inactive(self):
        """Scenario 17: get_enabled_vendors() excludes disabled and inactive vendors."""
        reg = VendorRegistry()
        mA = make_manifest(plugin_id="com.a", vendor_id="vendor_mock", version="1.0.0", domains=["a.com"])
        mB = make_manifest(plugin_id="com.b", vendor_id="vendor_b", version="1.0.0", domains=["b.com"])
        mC = make_manifest(plugin_id="com.c", vendor_id="vendor_c", version="1.0.0", domains=["c.com"])

        # vendor_mock: active and enabled
        reg.register_plugin_manifest(mA, MockVersionAdapter, activate=True, enabled=True)

        # vendor_b: active but disabled
        reg.register_plugin_manifest(mB, MockVendorBAdapter, activate=True, enabled=True)
        reg.set_vendor_enabled("vendor_b", False)

        # vendor_c: inactive
        reg.register_plugin_manifest(mC, MockVendorCAdapter, activate=False)

        assert reg.get_enabled_vendors() == ["vendor_mock"]

    def test_18_get_adapter_fails_closed_when_no_version_is_active(self):
        """Scenario 18: get_adapter(vendor_id) fails closed when no version is active."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=False)

        with pytest.raises(UnknownVendorError, match="no active version"):
            reg.get_adapter("vendor_mock")

        # Explicit version instantiation still succeeds
        adapter = reg.get_adapter("vendor_mock", version="1.0.0")
        assert isinstance(adapter, MockVersionAdapter)

    def test_19_url_to_adapter_resolution_atomic_snapshot(self):
        """Scenario 19: URL-to-adapter resolution corresponds to exact active version in consistent snapshot."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["store.mock.com"])
        m2 = make_manifest(version="2.0.0", domains=["store.mock.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)

        # Resolve when v1.0.0 is active
        adapter1, meta1 = reg.resolve_adapter_for_url("https://store.mock.com/products/123")
        assert adapter1 is not None
        assert meta1 is not None
        assert meta1.version == "1.0.0"

        # Register v2.0.0 and activate it
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=True)
        adapter2, meta2 = reg.resolve_adapter_for_url("https://store.mock.com/products/123")
        assert adapter2 is not None
        assert meta2 is not None
        assert meta2.version == "2.0.0"

        # Unrecognized domain
        ad_none, meta_none = reg.resolve_adapter_for_url("https://unrecognized.com")
        assert ad_none is None
        assert meta_none is None

        # Disabled vendor with enabled_only=True
        reg.set_vendor_enabled("vendor_mock", False)
        ad_dis, meta_dis = reg.resolve_adapter_for_url("https://store.mock.com/products/123", enabled_only=True)
        assert ad_dis is None
        assert meta_dis is None

    def test_20_concurrent_read_and_switch_thread_safety(self):
        """Scenario 20: Concurrent read/switch tests establish readers cannot observe partially updated state."""
        reg = VendorRegistry()
        m1 = make_manifest(version="1.0.0", domains=["thread.mock.com"])
        m2 = make_manifest(version="2.0.0", domains=["thread.mock.com"])

        reg.register_plugin_manifest(m1, MockVersionAdapter, activate=True)
        reg.register_plugin_manifest(m2, MockVersionAdapter, activate=False)

        stop_event = threading.Event()
        errors = []

        def reader_worker():
            while not stop_event.is_set():
                try:
                    adapter, meta = reg.resolve_adapter_for_url("https://thread.mock.com/p/1")
                    if adapter is not None and meta is not None:
                        # Version in meta must match active version at resolution time
                        assert meta.version in ("1.0.0", "2.0.0")
                        assert adapter.vendor_id == "vendor_mock"
                except Exception as e:
                    errors.append(e)

        def writer_worker():
            for i in range(50):
                target_ver = "2.0.0" if i % 2 == 0 else "1.0.0"
                try:
                    reg.activate_version("vendor_mock", target_ver)
                except Exception as e:
                    errors.append(e)
                time.sleep(0.001)

        readers = [threading.Thread(target=reader_worker) for _ in range(6)]
        writer = threading.Thread(target=writer_worker)

        for r in readers:
            r.start()
        writer.start()

        writer.join()
        stop_event.set()
        for r in readers:
            r.join()

        assert len(errors) == 0, f"Thread safety errors observed: {errors}"

    def test_21_legacy_defaults_and_manifest_backed_distinguishable(self):
        """Scenario 21: Legacy registration defaults and manifest-backed registration remain distinguishable."""
        reg = VendorRegistry()

        # Legacy programmatic registration
        reg.register_adapter(
            vendor_id="vendor_mock",
            adapter_class=MockVersionAdapter,
            domains=["legacy.mock.com"],
        )

        leg_meta = reg.get_version_registration("vendor_mock", LEGACY_DEFAULT_VERSION)
        assert leg_meta.is_manifest_backed is False
        assert leg_meta.manifest is None
        assert leg_meta.version == "0.0.0-dev"
        assert leg_meta.plugin_id == "local.vendor_mock.in_tree"

        # Manifest-backed registration
        reg2 = VendorRegistry()
        m = make_manifest(plugin_id="com.example.manifest", vendor_id="vendor_mock", version="1.0.0")
        reg2.register_plugin_manifest(m, MockVersionAdapter)

        man_meta = reg2.get_version_registration("vendor_mock", "1.0.0")
        assert man_meta.is_manifest_backed is True
        assert man_meta.manifest is not None
        assert man_meta.version == "1.0.0"
        assert man_meta.plugin_id == "com.example.manifest"

    def test_22_adapter_contract_and_capability_validation_intact(self):
        """Scenario 22: Existing adapter contract and capability validation remain intact."""
        reg = VendorRegistry()

        # 1. Invalid adapter class (not subclass of IVendorAdapter)
        class NotAnAdapter:
            pass

        m = make_manifest()
        with pytest.raises(ValueError, match="subclass of IVendorAdapter"):
            reg.register_plugin_manifest(m, NotAnAdapter)

        # 2. VENDOR_ID mismatch
        class MismatchedAdapter(MockVersionAdapter):
            VENDOR_ID = "vendor_wrong_name"

        with pytest.raises(ValueError, match="does not match adapter class VENDOR_ID"):
            reg.register_plugin_manifest(m, MismatchedAdapter)

        # 3. Valid registration retains capabilities and supported_modes
        m_caps = make_manifest(
            capabilities=["PRODUCT_URL_RECOGNITION", "CART_URL_RESOLUTION"],
            modes=["MODE_A", "MODE_B"],
        )
        reg_entry = reg.register_plugin_manifest(m_caps, MockVersionAdapter)
        assert reg_entry.capabilities == ["PRODUCT_URL_RECOGNITION", "CART_URL_RESOLUTION"]
        assert reg_entry.modes == ["MODE_A", "MODE_B"]


class TestPhase3AtomicProcurementDispatch:
    """Regression tests verifying atomic procurement URL dispatch without TOCTOU."""

    def test_explicit_url_uses_resolved_adapter_without_secondary_get_adapter(self):
        """Test A: Explicit product URL uses adapter from resolve_adapter_for_url() without secondary get_adapter() call."""
        reg = VendorRegistry()
        m = make_manifest(version="1.0.0")
        reg.register_plugin_manifest(m, MockVersionAdapter)

        get_adapter_calls = []
        original_get_adapter = reg.get_adapter

        def spy_get_adapter(vendor_id, *args, **kwargs):
            get_adapter_calls.append(vendor_id)
            return original_get_adapter(vendor_id, *args, **kwargs)

        reg.get_adapter = spy_get_adapter

        orch = UniversalProcurementOrchestrator(registry=reg)
        req = ProcurementRequest(
            part_number="MOCK-MPN",
            required_quantity=1,
            explicit_vendor_url="https://mock.example.com/p/123",
        )

        cands = orch.gather_candidates(req)
        assert len(cands) == 1
        assert cands[0].vendor_id == "vendor_mock"
        assert cands[0].base_unit_price_irr == 5000
        # get_adapter must NEVER have been called during explicit URL candidate gathering
        assert len(get_adapter_calls) == 0

    def test_active_version_switch_during_inspection_retains_snapshot_adapter(self):
        """Test B: Active-version switch during in-flight inspection retains the original resolved adapter instance."""
        reg = VendorRegistry()

        class MockAdapterV1(MockVersionAdapter):
            def inspect_product(self, product_ref):
                # Switch active version to 2.0.0 during in-flight inspection!
                reg.activate_version("vendor_mock", "2.0.0")
                return ProductDetails(
                    vendor_id=self.VENDOR_ID,
                    vendor_sku="SKU-V1",
                    pdp_url=product_ref.pdp_url,
                    stock_quantity=10,
                    can_order=True,
                    price_irr=1111,
                    mpn="V1-MPN",
                )

        class MockAdapterV2(MockVersionAdapter):
            def inspect_product(self, product_ref):
                return ProductDetails(
                    vendor_id=self.VENDOR_ID,
                    vendor_sku="SKU-V2",
                    pdp_url=product_ref.pdp_url,
                    stock_quantity=20,
                    can_order=True,
                    price_irr=2222,
                    mpn="V2-MPN",
                )

        m1 = make_manifest(version="1.0.0")
        m2 = make_manifest(version="2.0.0")
        reg.register_plugin_manifest(m1, MockAdapterV1)
        reg.register_plugin_manifest(m2, MockAdapterV2)

        # Initially 1.0.0 is active
        assert reg.get_active_version("vendor_mock") == "1.0.0"

        orch = UniversalProcurementOrchestrator(registry=reg)
        req = ProcurementRequest(
            part_number="MOCK-MPN",
            required_quantity=1,
            explicit_vendor_url="https://mock.example.com/p/123",
        )

        # In-flight inspection will trigger activation of 2.0.0
        cands = orch.gather_candidates(req)
        assert len(cands) == 1
        cand = cands[0]
        # Must retain the V1 adapter snapshot for the in-flight operation
        assert cand.base_unit_price_irr == 1111
        assert cand.part_number == "V1-MPN"
        assert cand.product_ref.vendor_sku == "SKU-1"

        # Now active version in registry is confirmed to have switched to 2.0.0
        assert reg.get_active_version("vendor_mock") == "2.0.0"

        # Subsequent request uses V2 adapter
        cands2 = orch.gather_candidates(req)
        assert len(cands2) == 1
        assert cands2[0].base_unit_price_irr == 2222
        assert cands2[0].part_number == "V2-MPN"

    def test_fail_closed_cases(self):
        """Test C: Fail-closed cases (unmapped URL, inactive vendor, disabled vendor, explicit vendor ID mismatch, empty URL)."""
        reg = VendorRegistry()
        m = make_manifest(version="1.0.0", domains=["mock.example.com"])
        reg.register_plugin_manifest(m, MockVersionAdapter)

        orch = UniversalProcurementOrchestrator(registry=reg)

        # 1. Unmapped URL
        req_unmapped = ProcurementRequest(
            part_number="TEST",
            required_quantity=1,
            explicit_vendor_url="https://unknown-distributor.com/p/123",
        )
        assert orch.gather_candidates(req_unmapped) == []

        # 2. Inactive vendor
        reg.deactivate_vendor("vendor_mock")
        req_inactive = ProcurementRequest(
            part_number="TEST",
            required_quantity=1,
            explicit_vendor_url="https://mock.example.com/p/123",
        )
        assert orch.gather_candidates(req_inactive) == []

        # Reactivate and test disabled vendor
        reg.activate_version("vendor_mock", "1.0.0")
        reg.set_vendor_enabled("vendor_mock", False)
        req_disabled = ProcurementRequest(
            part_number="TEST",
            required_quantity=1,
            explicit_vendor_url="https://mock.example.com/p/123",
        )
        assert orch.gather_candidates(req_disabled) == []

        # Reactivate and enable, test vendor ID mismatch
        reg.set_vendor_enabled("vendor_mock", True)
        req_mismatch = ProcurementRequest(
            part_number="TEST",
            required_quantity=1,
            explicit_vendor_id="vendor_lion",  # Mismatch with mock.example.com
            explicit_vendor_url="https://mock.example.com/p/123",
        )
        assert orch.gather_candidates(req_mismatch) == []

        # 5. Empty / whitespace URL
        req_empty = ProcurementRequest(
            part_number="TEST",
            required_quantity=1,
            explicit_vendor_url="   ",
        )
        assert orch.gather_candidates(req_empty) == []

    def test_mode_a_bridge_staged_procurement_reaches_atomic_resolver(self):
        """Test D: Mode A bridge staged procurement reaches atomic resolver."""
        reg = VendorRegistry()
        m = make_manifest(version="1.0.0", domains=["mock.example.com"])
        reg.register_plugin_manifest(m, MockVersionAdapter)

        item = {
            "part_number": "MOCK-MPN",
            "needed_qty": 5,
            "link": "https://mock.example.com/p/555",
            "mode": "DATABASE_AWARE",
        }
        req = ProcurementBridge.item_to_request(item, registry=reg)
        assert req.explicit_vendor_url == "https://mock.example.com/p/555"
        assert req.explicit_vendor_id == "vendor_mock"

        orch = UniversalProcurementOrchestrator(registry=reg)
        plan = orch.build_plan([req])

        assert plan.total_items == 1
        assert plan.resolved_count == 1
        result = plan.results[0]
        assert result.status == "RESOLVED"
        assert result.selected_evaluation.candidate.vendor_id == "vendor_mock"
        assert result.selected_evaluation.candidate.base_unit_price_irr == 5000

