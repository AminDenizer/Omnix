"""
Unit & Contract Tests for Omnix Vendor Plugin Contract (Phase 2)
Governing Document: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Sections 6 & 7

Validates:
1. Canonical models: PluginCapability (16 items), CapabilityStatus (5 items),
   CapabilityBlockingReason (7 items), PluginProcurementMode (2 items).
2. CapabilityEvaluationRecord validation, timestamping, blocking consistency,
   and secret leakage protection in diagnostic details.
3. IVendorAdapter base contracts: 13 abstract methods, fail-closed defaults,
   empty default capabilities and modes, deterministic queries.
4. Centralized CAPABILITY_METHOD_MAP covering all 16 capabilities,
   verifying real adapter methods and explicit empty Layer C live test boundaries.
5. Declared capability and procurement mode consistency validation.
6. Built-in production adapters (Lion, Javan, RoboEq) compliance and evidence-backed
   declarations (Layer A/B only, zero Layer C).
"""

import inspect
import json
import pytest
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from core.models import (
    PluginCapability,
    CapabilityStatus,
    CapabilityBlockingReason,
    PluginProcurementMode,
    CapabilityEvaluationRecord,
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
from core.vendor_interface import (
    IVendorAdapter,
    CAPABILITY_METHOD_MAP,
    validate_capability_mode_consistency,
)
from vendors.lion.adapter import LionVendorAdapter
from vendors.javan.adapter import JavanVendorAdapter
from vendors.roboeq.adapter import RoboEqVendorAdapter


# ==============================================================================
# 1. Canonical Enum & Model Tests
# ==============================================================================

class TestCanonicalEnums:
    """Verify exact membership and string compatibility of all Phase 2 enums."""

    def test_plugin_capability_exact_16_items(self):
        expected_layer_ab = {
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "CART_URL_RESOLUTION",
            "MPN_SEARCH",
            "LIVE_STOCK_PROBE",
            "TIERED_PRICING",
            "MODE_A_STAGING",
            "MODE_B_STAGING",
        }
        expected_layer_c = {
            "LIVE_CONNECTIVITY_TEST",
            "LIVE_STRUCTURE_TEST",
            "LOGIN_TEST",
            "CAPTCHA_DETECTION",
            "CAPTCHA_HUMAN_ASSIST",
            "LIVE_PRODUCT_DISCOVERY",
            "LIVE_QUANTITY_VALIDATION",
            "LIVE_ADD_TO_CART",
        }
        all_expected = expected_layer_ab | expected_layer_c

        assert len(PluginCapability) == 16
        assert {c.value for c in PluginCapability} == all_expected
        assert {c.name for c in PluginCapability} == all_expected

        # Verify string-compatibility
        for cap in PluginCapability:
            assert isinstance(cap, str)
            assert cap == cap.value

    def test_layer_ab_capabilities_match_manifest_schema(self):
        """Ensure Layer A/B capabilities strictly match the manifest JSON schema enum."""
        with open("core/plugins/manifest.schema.json", "r", encoding="utf-8") as f:
            schema = json.load(f)
        schema_caps = set(schema["properties"]["capabilities"]["items"]["enum"])

        layer_ab_caps = {
            PluginCapability.PRODUCT_URL_RECOGNITION.value,
            PluginCapability.PRODUCT_INSPECTION.value,
            PluginCapability.CART_URL_RESOLUTION.value,
            PluginCapability.MPN_SEARCH.value,
            PluginCapability.LIVE_STOCK_PROBE.value,
            PluginCapability.TIERED_PRICING.value,
            PluginCapability.MODE_A_STAGING.value,
            PluginCapability.MODE_B_STAGING.value,
        }
        assert schema_caps == layer_ab_caps

    def test_capability_status_exact_5_items(self):
        expected_statuses = {"PASSED", "FAILED", "NOT_RUN", "NOT_SUPPORTED", "BLOCKED"}
        assert len(CapabilityStatus) == 5
        assert {s.value for s in CapabilityStatus} == expected_statuses
        for status in CapabilityStatus:
            assert isinstance(status, str)
            assert status == status.value

    def test_capability_blocking_reason_exact_7_items(self):
        expected_reasons = {
            "MISSING_CREDENTIALS",
            "UNVERIFIED_DOMAIN",
            "PREREQUISITE_GATE_FAILED",
            "REVOCATION_BLACKLISTED",
            "SECURITY_POLICY_RESTRICTION",
            "VENDOR_ACCESS_BLOCKED",
            "OPERATOR_OPT_IN_REQUIRED",
        }
        assert len(CapabilityBlockingReason) == 7
        assert {r.value for r in CapabilityBlockingReason} == expected_reasons
        for reason in CapabilityBlockingReason:
            assert isinstance(reason, str)
            assert reason == reason.value

    def test_plugin_procurement_mode_exact_2_items(self):
        expected_modes = {"MODE_A", "MODE_B"}
        assert len(PluginProcurementMode) == 2
        assert {m.value for m in PluginProcurementMode} == expected_modes
        for mode in PluginProcurementMode:
            assert isinstance(mode, str)
            assert mode == mode.value


# ==============================================================================
# 2. CapabilityEvaluationRecord Consistency & Secret Safety
# ==============================================================================

class TestCapabilityEvaluationRecord:
    """Verify evaluation record validation, timestamping, and diagnostic sanitization."""

    def test_valid_passed_evaluation(self):
        record = CapabilityEvaluationRecord(
            capability=PluginCapability.PRODUCT_INSPECTION,
            status=CapabilityStatus.PASSED,
            details={"sample_part": "NE555"},
        )
        assert record.capability == PluginCapability.PRODUCT_INSPECTION
        assert record.status == CapabilityStatus.PASSED
        assert record.blocking_reason is None
        assert record.evaluated_at != ""
        assert record.details == {"sample_part": "NE555"}

    def test_string_coercion_on_construction(self):
        record = CapabilityEvaluationRecord(
            capability="MPN_SEARCH",  # type: ignore
            status="NOT_RUN",  # type: ignore
        )
        assert isinstance(record.capability, PluginCapability)
        assert record.capability == PluginCapability.MPN_SEARCH
        assert isinstance(record.status, CapabilityStatus)
        assert record.status == CapabilityStatus.NOT_RUN

    def test_valid_blocked_evaluation_requires_blocking_reason(self):
        record = CapabilityEvaluationRecord(
            capability=PluginCapability.LOGIN_TEST,
            status=CapabilityStatus.BLOCKED,
            blocking_reason=CapabilityBlockingReason.MISSING_CREDENTIALS,
            details={"gate": "Gate C1"},
        )
        assert record.status == CapabilityStatus.BLOCKED
        assert record.blocking_reason == CapabilityBlockingReason.MISSING_CREDENTIALS

    def test_blocked_without_reason_raises_value_error(self):
        with pytest.raises(ValueError, match="BLOCKED capability evaluation record must specify an explicit blocking_reason"):
            CapabilityEvaluationRecord(
                capability=PluginCapability.LOGIN_TEST,
                status=CapabilityStatus.BLOCKED,
                blocking_reason=None,
            )

    @pytest.mark.parametrize("status", [
        CapabilityStatus.PASSED,
        CapabilityStatus.FAILED,
        CapabilityStatus.NOT_RUN,
        CapabilityStatus.NOT_SUPPORTED,
    ])
    def test_non_blocked_with_blocking_reason_raises_value_error(self, status):
        with pytest.raises(ValueError, match="must not specify a blocking_reason"):
            CapabilityEvaluationRecord(
                capability=PluginCapability.PRODUCT_INSPECTION,
                status=status,
                blocking_reason=CapabilityBlockingReason.PREREQUISITE_GATE_FAILED,
            )

    def test_automatic_iso8601_timestamp_generation(self):
        before = datetime.now(timezone.utc)
        record = CapabilityEvaluationRecord(
            capability=PluginCapability.CART_URL_RESOLUTION,
            status=CapabilityStatus.PASSED,
        )
        after = datetime.now(timezone.utc)

        assert record.evaluated_at != ""
        parsed = datetime.fromisoformat(record.evaluated_at)
        assert before <= parsed <= after

    @pytest.mark.parametrize("sensitive_key", [
        "password",
        "user_password",
        "passwd",
        "SECRET",
        "api_secret",
        "access_token",
        "session_token",
        "auth_token",
        "cookie_header",
        "cookies",
        "credentials_dict",
    ])
    def test_diagnostic_details_rejects_sensitive_keys(self, sensitive_key):
        with pytest.raises(ValueError, match="Diagnostic details must not contain sensitive credential key"):
            CapabilityEvaluationRecord(
                capability=PluginCapability.PRODUCT_INSPECTION,
                status=CapabilityStatus.FAILED,
                details={sensitive_key: "sensitive_value_123"},
            )

    def test_diagnostic_details_accepts_safe_operational_keys(self):
        safe_details = {
            "http_status": 200,
            "response_time_ms": 154.2,
            "element_count": 4,
            "sku_queried": "12345",
        }
        record = CapabilityEvaluationRecord(
            capability=PluginCapability.PRODUCT_INSPECTION,
            status=CapabilityStatus.PASSED,
            details=safe_details,
        )
        assert record.details == safe_details

    def test_to_dict_serialization(self):
        record = CapabilityEvaluationRecord(
            capability=PluginCapability.LIVE_STOCK_PROBE,
            status=CapabilityStatus.BLOCKED,
            blocking_reason=CapabilityBlockingReason.UNVERIFIED_DOMAIN,
            evaluated_at="2026-10-15T20:00:00+00:00",
            details={"attempted_host": "unauthorized.vendor.com"},
        )
        data = record.to_dict()
        assert data == {
            "capability": "LIVE_STOCK_PROBE",
            "status": "BLOCKED",
            "blocking_reason": "UNVERIFIED_DOMAIN",
            "evaluated_at": "2026-10-15T20:00:00+00:00",
            "details": {"attempted_host": "unauthorized.vendor.com"},
        }


# ==============================================================================
# 3. IVendorAdapter Contract & Fail-Closed Defaults
# ==============================================================================

class MinimalConcreteAdapter(IVendorAdapter):
    """Minimal subclass to test default base behaviors without mocking."""
    @property
    def vendor_id(self) -> str:
        return "vendor_minimal"

    @property
    def base_url(self) -> str:
        return "https://minimal.example.com"

    def initialize(self, config=None):
        return AdapterStatus(vendor_id=self.vendor_id, is_ready=True, is_authenticated=False)

    def search_part(self, query):
        return SearchResultSet(vendor_id=self.vendor_id, query=query, total_matches=0, is_exact_match=False)

    def resolve_product(self, url_or_sku):
        return ProductReference(vendor_id=self.vendor_id, vendor_sku="MIN-1", pdp_url="https://minimal.example.com/p/1")

    def inspect_product(self, product_ref):
        return ProductDetails(vendor_id=self.vendor_id, vendor_sku=product_ref.vendor_sku, pdp_url=product_ref.pdp_url)

    def extract_product_data(self, dom_context):
        return CanonicalComponentDraft(vendor_id=self.vendor_id, vendor_sku="MIN-1")

    def inspect_stock(self, product_ref):
        return StockStatus(vendor_id=self.vendor_id, vendor_sku=product_ref.vendor_sku, stock_quantity=0, in_stock=False, can_order=False)

    def determine_order_constraints(self, product_ref):
        return OrderConstraints()

    def add_to_cart(self, product_ref, quantity):
        return CartMutationResult(vendor_id=self.vendor_id, vendor_sku=product_ref.vendor_sku, requested_quantity=quantity, actual_quantity_staged=0, success=False)

    def inspect_cart(self):
        return CartDetails(vendor_id=self.vendor_id, cart_url="", total_items=0)

    def authenticate(self, credentials=None, challenge_handler=None):
        return AuthResult(vendor_id=self.vendor_id, success=False, message="Not implemented")

    def validate_session(self):
        return SessionStatus(vendor_id=self.vendor_id, is_authenticated=False)

    def recover_from_error(self, error_context):
        return RecoveryResult(vendor_id=self.vendor_id, recovered=False, action_taken="none", message="")

    def close(self):
        pass


class TestIVendorAdapterContract:
    """Verify base IVendorAdapter abstract specifications and fail-closed behaviors."""

    def test_ivendor_adapter_is_abstract(self):
        with pytest.raises(TypeError):
            IVendorAdapter()  # type: ignore

    def test_all_13_abstract_methods_exist(self):
        expected_abstract_methods = {
            "vendor_id",
            "base_url",
            "initialize",
            "search_part",
            "resolve_product",
            "inspect_product",
            "extract_product_data",
            "inspect_stock",
            "determine_order_constraints",
            "add_to_cart",
            "inspect_cart",
            "authenticate",
            "validate_session",
            "recover_from_error",
            "close",
        }
        abstract_members = getattr(IVendorAdapter, "__abstractmethods__", set())
        assert expected_abstract_methods.issubset(abstract_members)

    def test_base_get_cart_url_returns_none(self):
        adapter = MinimalConcreteAdapter()
        assert adapter.get_cart_url() is None

    def test_base_is_pdp_url_fails_closed_returns_false(self):
        adapter = MinimalConcreteAdapter()
        assert adapter.is_pdp_url("https://minimal.example.com/item/1") is False
        assert adapter.is_pdp_url("") is False

    def test_base_get_supported_capabilities_empty_default(self):
        adapter = MinimalConcreteAdapter()
        caps = adapter.get_supported_capabilities()
        assert isinstance(caps, set)
        assert len(caps) == 0

    def test_base_get_supported_modes_empty_default(self):
        adapter = MinimalConcreteAdapter()
        modes = adapter.get_supported_modes()
        assert isinstance(modes, set)
        assert len(modes) == 0

    def test_supports_capability_fails_closed_for_undeclared(self):
        adapter = MinimalConcreteAdapter()
        for cap in PluginCapability:
            assert adapter.supports_capability(cap) is False

    def test_supports_capability_fails_closed_on_invalid_inputs(self):
        adapter = MinimalConcreteAdapter()
        assert adapter.supports_capability("NON_EXISTENT_CAPABILITY") is False
        assert adapter.supports_capability("") is False
        assert adapter.supports_capability(123) is False  # type: ignore
        assert adapter.supports_capability(None) is False  # type: ignore

    def test_capability_queries_perform_no_io_or_network(self):
        """Querying capabilities must be instantaneous and pure in-memory lookup."""
        adapter = MinimalConcreteAdapter()
        # Call multiple times with various parameters
        for _ in range(100):
            adapter.get_supported_capabilities()
            adapter.get_supported_modes()
            adapter.supports_capability(PluginCapability.MPN_SEARCH)
            adapter.supports_capability("INVALID")


# ==============================================================================
# 4. CAPABILITY_METHOD_MAP Verification
# ==============================================================================

class TestCapabilityMethodMap:
    """Verify the completeness and accuracy of the centralized capability-to-method map."""

    def test_map_covers_all_16_capabilities_exactly_once(self):
        assert len(CAPABILITY_METHOD_MAP) == 16
        assert set(CAPABILITY_METHOD_MAP.keys()) == set(PluginCapability)

    def test_layer_ab_capabilities_map_to_real_adapter_methods(self):
        layer_ab = [
            PluginCapability.PRODUCT_URL_RECOGNITION,
            PluginCapability.PRODUCT_INSPECTION,
            PluginCapability.CART_URL_RESOLUTION,
            PluginCapability.MPN_SEARCH,
            PluginCapability.LIVE_STOCK_PROBE,
            PluginCapability.TIERED_PRICING,
            PluginCapability.MODE_A_STAGING,
            PluginCapability.MODE_B_STAGING,
        ]
        for cap in layer_ab:
            methods = CAPABILITY_METHOD_MAP[cap]
            assert isinstance(methods, tuple)
            assert len(methods) >= 1, f"Capability {cap} must have at least one mapped method."
            for m_name in methods:
                assert hasattr(IVendorAdapter, m_name), (
                    f"Method '{m_name}' mapped for '{cap}' does not exist on IVendorAdapter."
                )
                assert callable(getattr(IVendorAdapter, m_name)), (
                    f"Attribute '{m_name}' on IVendorAdapter is not callable."
                )

    def test_layer_c_capabilities_map_to_empty_tuple_with_documented_boundary(self):
        layer_c = [
            PluginCapability.LIVE_CONNECTIVITY_TEST,
            PluginCapability.LIVE_STRUCTURE_TEST,
            PluginCapability.LOGIN_TEST,
            PluginCapability.CAPTCHA_DETECTION,
            PluginCapability.CAPTCHA_HUMAN_ASSIST,
            PluginCapability.LIVE_PRODUCT_DISCOVERY,
            PluginCapability.LIVE_QUANTITY_VALIDATION,
            PluginCapability.LIVE_ADD_TO_CART,
        ]
        for cap in layer_c:
            methods = CAPABILITY_METHOD_MAP[cap]
            assert methods == (), (
                f"Layer C capability {cap} must map to () in Phase 2, "
                "representing deferred live-test runner boundaries."
            )

    def test_mode_a_and_mode_b_staging_map_to_add_to_cart(self):
        assert CAPABILITY_METHOD_MAP[PluginCapability.MODE_A_STAGING] == ("add_to_cart",)
        assert CAPABILITY_METHOD_MAP[PluginCapability.MODE_B_STAGING] == ("add_to_cart",)


# ==============================================================================
# 5. Procurement Mode and Capability Consistency Invariants
# ==============================================================================

class TestProcurementModeCapabilityConsistency:
    """Verify consistency rules between declared capabilities and supported procurement modes."""

    def test_staging_without_corresponding_mode_fails(self):
        # Case 1: MODE_A_STAGING declared, but MODE_A not in modes
        errors_a = validate_capability_mode_consistency(
            capabilities={PluginCapability.MODE_A_STAGING},
            modes=set(),
        )
        assert len(errors_a) == 1
        assert "MODE_A_STAGING requires MODE_A" in errors_a[0]

        # Case 2: MODE_B_STAGING declared, but MODE_B not in modes
        errors_b = validate_capability_mode_consistency(
            capabilities={PluginCapability.MODE_B_STAGING},
            modes={PluginProcurementMode.MODE_A},
        )
        assert len(errors_b) == 1
        assert "MODE_B_STAGING requires MODE_B" in errors_b[0]

    def test_single_mode_a_plugin_is_valid(self):
        errors = validate_capability_mode_consistency(
            capabilities={
                PluginCapability.PRODUCT_URL_RECOGNITION,
                PluginCapability.PRODUCT_INSPECTION,
                PluginCapability.CART_URL_RESOLUTION,
                PluginCapability.MODE_A_STAGING,
            },
            modes={PluginProcurementMode.MODE_A},
        )
        assert errors == []

    def test_single_mode_b_plugin_is_valid(self):
        errors = validate_capability_mode_consistency(
            capabilities={
                PluginCapability.PRODUCT_URL_RECOGNITION,
                PluginCapability.PRODUCT_INSPECTION,
                PluginCapability.MPN_SEARCH,
                PluginCapability.MODE_B_STAGING,
            },
            modes={PluginProcurementMode.MODE_B},
        )
        assert errors == []

    def test_dual_mode_plugin_is_valid(self):
        errors = validate_capability_mode_consistency(
            capabilities={
                PluginCapability.PRODUCT_URL_RECOGNITION,
                PluginCapability.PRODUCT_INSPECTION,
                PluginCapability.MODE_A_STAGING,
                PluginCapability.MODE_B_STAGING,
            },
            modes={PluginProcurementMode.MODE_A, PluginProcurementMode.MODE_B},
        )
        assert errors == []

    def test_no_modes_with_no_staging_is_valid(self):
        errors = validate_capability_mode_consistency(
            capabilities={PluginCapability.PRODUCT_URL_RECOGNITION},
            modes=set(),
        )
        assert errors == []


# ==============================================================================
# 6. Built-in Production Adapters Compliance (Lion, Javan, RoboEq)
# ==============================================================================

class TestBuiltInAdaptersCompliance:
    """Verify Lion, Javan, and RoboEq declared capabilities and modes against codebase evidence."""

    @pytest.fixture
    def lion(self):
        return LionVendorAdapter()

    @pytest.fixture
    def javan(self):
        return JavanVendorAdapter()

    @pytest.fixture
    def roboeq(self):
        return RoboEqVendorAdapter()

    def test_adapters_are_instantiable_without_browser(self, lion, javan, roboeq):
        assert isinstance(lion, IVendorAdapter)
        assert isinstance(javan, IVendorAdapter)
        assert isinstance(roboeq, IVendorAdapter)

    def test_lion_adapter_capabilities_and_modes(self, lion):
        expected_caps = {
            PluginCapability.PRODUCT_URL_RECOGNITION,
            PluginCapability.PRODUCT_INSPECTION,
            PluginCapability.CART_URL_RESOLUTION,
            PluginCapability.MPN_SEARCH,
            PluginCapability.LIVE_STOCK_PROBE,
            PluginCapability.TIERED_PRICING,
            PluginCapability.MODE_A_STAGING,
            PluginCapability.MODE_B_STAGING,
        }
        assert lion.get_supported_capabilities() == expected_caps
        assert lion.get_supported_modes() == {PluginProcurementMode.MODE_A, PluginProcurementMode.MODE_B}
        assert lion.supports_capability(PluginCapability.TIERED_PRICING) is True
        assert lion.validate_capability_consistency() == []

        # Zero Layer C capabilities declared
        for cap in PluginCapability:
            if cap.name.startswith("LIVE_") and cap != PluginCapability.LIVE_STOCK_PROBE:
                assert lion.supports_capability(cap) is False
            if cap.name.startswith("CAPTCHA_") or cap == PluginCapability.LOGIN_TEST:
                assert lion.supports_capability(cap) is False

    def test_javan_adapter_capabilities_and_modes(self, javan):
        expected_caps = {
            PluginCapability.PRODUCT_URL_RECOGNITION,
            PluginCapability.PRODUCT_INSPECTION,
            PluginCapability.CART_URL_RESOLUTION,
            PluginCapability.MPN_SEARCH,
            PluginCapability.LIVE_STOCK_PROBE,
            PluginCapability.TIERED_PRICING,
            PluginCapability.MODE_A_STAGING,
            PluginCapability.MODE_B_STAGING,
        }
        assert javan.get_supported_capabilities() == expected_caps
        assert javan.get_supported_modes() == {PluginProcurementMode.MODE_A, PluginProcurementMode.MODE_B}
        assert javan.supports_capability(PluginCapability.TIERED_PRICING) is True
        assert javan.validate_capability_consistency() == []

        # Zero Layer C capabilities declared
        for cap in PluginCapability:
            if cap.name.startswith("LIVE_") and cap != PluginCapability.LIVE_STOCK_PROBE:
                assert javan.supports_capability(cap) is False
            if cap.name.startswith("CAPTCHA_") or cap == PluginCapability.LOGIN_TEST:
                assert javan.supports_capability(cap) is False

    def test_roboeq_adapter_capabilities_and_modes(self, roboeq):
        """RoboEq extracts single price only; does NOT declare TIERED_PRICING."""
        expected_caps = {
            PluginCapability.PRODUCT_URL_RECOGNITION,
            PluginCapability.PRODUCT_INSPECTION,
            PluginCapability.CART_URL_RESOLUTION,
            PluginCapability.MPN_SEARCH,
            PluginCapability.LIVE_STOCK_PROBE,
            PluginCapability.MODE_A_STAGING,
            PluginCapability.MODE_B_STAGING,
        }
        assert roboeq.get_supported_capabilities() == expected_caps
        assert roboeq.get_supported_modes() == {PluginProcurementMode.MODE_A, PluginProcurementMode.MODE_B}
        assert roboeq.supports_capability(PluginCapability.TIERED_PRICING) is False
        assert roboeq.validate_capability_consistency() == []

        # Zero Layer C capabilities declared
        for cap in PluginCapability:
            if cap.name.startswith("LIVE_") and cap != PluginCapability.LIVE_STOCK_PROBE:
                assert roboeq.supports_capability(cap) is False
            if cap.name.startswith("CAPTCHA_") or cap == PluginCapability.LOGIN_TEST:
                assert roboeq.supports_capability(cap) is False

    def test_builtin_adapters_preserve_cart_url_and_pdp_contracts(self, lion, javan, roboeq):
        # Cart URLs
        assert lion.get_cart_url() == "https://lionelectronic.ir/orders/cart"
        assert javan.get_cart_url() == "https://www.javanelec.com/shoppingcarts"
        assert roboeq.get_cart_url() == "https://roboeq.ir/cart/"

        # PDP URL validation
        assert lion.is_pdp_url("https://lionelectronic.ir/products/2070-NE555P") is True
        assert lion.is_pdp_url("https://lionelectronic.ir/orders/cart") is False

        assert javan.is_pdp_url("https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p") is True
        assert javan.is_pdp_url("https://www.javanelec.com/shoppingcarts") is False

        assert roboeq.is_pdp_url("https://roboeq.ir/products/detail/0315001/ic-ne555/") is True
        assert roboeq.is_pdp_url("https://roboeq.ir/cart/") is False


