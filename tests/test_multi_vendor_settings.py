"""
Omnix Unit & Contract Tests for GAP-11: Multi-Vendor Settings & Dynamic Enable/Disable
Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-11)
"""

import os
import json
import pytest
import tempfile
from core.models import VendorSettings, AuthCredentials, AdapterConfig
from core.procurement.registry import VendorRegistry, VendorRegistration
from core.procurement.models import ProcurementRequest
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.vendor_interface import IVendorAdapter
from settings_manager import SettingsManager


@pytest.fixture
def temp_settings_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


class DummyTestAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_test"
    BASE_URL = "https://test.example.com"

    def __init__(self, config=None):
        self.config = config

    @property
    def vendor_id(self):
        return self.VENDOR_ID

    @property
    def base_url(self):
        return self.BASE_URL

    def initialize(self, config=None):
        pass

    def search_part(self, query):
        from core.models import SearchResultSet
        return SearchResultSet(vendor_id=self.VENDOR_ID, query=query, total_matches=0, is_exact_match=False, items=[])

    def resolve_product(self, url_or_sku):
        pass

    def inspect_product(self, product_ref):
        pass

    def extract_product_data(self, dom_context):
        pass

    def inspect_stock(self, product_ref):
        pass

    def determine_order_constraints(self, product_ref):
        pass

    def add_to_cart(self, product_ref, quantity):
        pass

    def inspect_cart(self):
        pass

    def authenticate(self, credentials=None, challenge_handler=None):
        pass

    def validate_session(self):
        pass

    def recover_from_error(self, error_context):
        pass

    def close(self):
        pass


class TestMultiVendorSettingsModel:
    """Tests for VendorSettings model invariants and credential security (GAP-11)."""

    def test_vendor_settings_defaults(self):
        cfg = VendorSettings(vendor_id="vendor_lion")
        assert cfg.vendor_id == "vendor_lion"
        assert cfg.enabled is True
        assert cfg.username == ""
        assert cfg.password == ""
        assert cfg.timeout_seconds == 10.0
        assert cfg.headless is True
        assert cfg.extra_options == {}

    def test_password_masked_in_repr(self):
        cfg = VendorSettings(vendor_id="vendor_lion", username="test_user", password="secret_password_123")
        repr_str = repr(cfg)
        assert "secret_password_123" not in repr_str
        assert "***" in repr_str
        assert "test_user" in repr_str

    def test_auth_credentials_password_masked_in_repr(self):
        cred = AuthCredentials(username="my_user", password="my_secret_pass")
        repr_str = repr(cred)
        assert "my_secret_pass" not in repr_str
        assert "***" in repr_str
        assert "my_user" in repr_str

    def test_serialization_roundtrip(self):
        cfg = VendorSettings(
            vendor_id="vendor_javan",
            enabled=False,
            username="javan_user",
            password="javan_password",
            timeout_seconds=15.5,
            headless=False,
            extra_options={"region": "tehran"},
        )
        d = cfg.to_dict()
        restored = VendorSettings.from_dict(d)
        assert restored.vendor_id == "vendor_javan"
        assert restored.enabled is False
        assert restored.username == "javan_user"
        assert restored.password == "javan_password"
        assert restored.timeout_seconds == 15.5
        assert restored.headless is False
        assert restored.extra_options == {"region": "tehran"}


class TestMultiVendorSettingsManager:
    """Tests for SettingsManager multi-vendor persistence and isolation (GAP-11)."""

    def test_default_multi_vendor_settings(self, temp_settings_file):
        mgr = SettingsManager(file_path=temp_settings_file)
        all_v = mgr.get_all_vendor_settings()
        assert "vendor_lion" in all_v
        assert "vendor_javan" in all_v
        assert "vendor_roboeq" in all_v
        assert all_v["vendor_lion"].enabled is True
        assert all_v["vendor_javan"].enabled is True
        assert all_v["vendor_roboeq"].enabled is True

    def test_independent_vendor_enable_disable(self, temp_settings_file):
        mgr = SettingsManager(file_path=temp_settings_file)
        mgr.set_vendor_enabled("vendor_lion", True)
        mgr.set_vendor_enabled("vendor_javan", False)
        mgr.set_vendor_enabled("vendor_roboeq", True)

        assert mgr.is_vendor_enabled("vendor_lion") is True
        assert mgr.is_vendor_enabled("vendor_javan") is False
        assert mgr.is_vendor_enabled("vendor_roboeq") is True

        # Reload from disk
        mgr2 = SettingsManager(file_path=temp_settings_file)
        assert mgr2.is_vendor_enabled("vendor_lion") is True
        assert mgr2.is_vendor_enabled("vendor_javan") is False
        assert mgr2.is_vendor_enabled("vendor_roboeq") is True

    def test_changing_one_vendor_does_not_alter_another(self, temp_settings_file):
        mgr = SettingsManager(file_path=temp_settings_file)
        lion_cfg = VendorSettings(vendor_id="vendor_lion", username="lion_user_1", password="lion_pass_1", timeout_seconds=8.0)
        javan_cfg = VendorSettings(vendor_id="vendor_javan", username="javan_user_2", password="javan_pass_2", timeout_seconds=12.0)
        roboeq_cfg = VendorSettings(vendor_id="vendor_roboeq", username="robo_user_3", password="robo_pass_3", timeout_seconds=14.0)

        mgr.set_vendor_settings("vendor_lion", lion_cfg)
        mgr.set_vendor_settings("vendor_javan", javan_cfg)
        mgr.set_vendor_settings("vendor_roboeq", roboeq_cfg)

        # Now update only Javan
        updated_javan = VendorSettings(vendor_id="vendor_javan", username="javan_MODIFIED", password="new_pass", timeout_seconds=20.0, enabled=False)
        mgr.set_vendor_settings("vendor_javan", updated_javan)

        # Verify Lion and RoboEq were untouched
        l_read = mgr.get_vendor_settings("vendor_lion")
        assert l_read.username == "lion_user_1"
        assert l_read.password == "lion_pass_1"
        assert l_read.timeout_seconds == 8.0
        assert l_read.enabled is True

        r_read = mgr.get_vendor_settings("vendor_roboeq")
        assert r_read.username == "robo_user_3"
        assert r_read.password == "robo_pass_3"
        assert r_read.timeout_seconds == 14.0
        assert r_read.enabled is True

        j_read = mgr.get_vendor_settings("vendor_javan")
        assert j_read.username == "javan_MODIFIED"
        assert j_read.enabled is False

    def test_legacy_backward_compatibility_synchronization(self, temp_settings_file):
        # Create a legacy settings file format
        legacy_data = {
            "lion_username": "legacy_lion_user",
            "lion_password": "legacy_lion_pass",
            "show_browser": True,
            "auto_check_startup_shortage": False,
        }
        with open(temp_settings_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        mgr = SettingsManager(file_path=temp_settings_file)
        lion_cfg = mgr.get_vendor_settings("vendor_lion")
        assert lion_cfg.username == "legacy_lion_user"
        assert lion_cfg.password == "legacy_lion_pass"
        assert lion_cfg.headless is False  # show_browser == True -> headless == False


class TestVendorRegistryAndOrchestratorFiltering:
    """Tests for dynamic vendor filtering in VendorRegistry and Orchestrator (GAP-11)."""

    def test_registry_dynamic_enable_disable(self):
        reg = VendorRegistry()
        reg.register_adapter("v1", DummyTestAdapter, domains=["v1.ir"], enabled=True)
        reg.register_adapter("v2", DummyTestAdapter, domains=["v2.ir"], enabled=True)
        reg.register_adapter("v3", DummyTestAdapter, domains=["v3.ir"], enabled=False)

        assert reg.is_vendor_enabled("v1") is True
        assert reg.is_vendor_enabled("v2") is True
        assert reg.is_vendor_enabled("v3") is False
        assert reg.get_enabled_vendors() == ["v1", "v2"]

        reg.set_vendor_enabled("v3", True)
        assert reg.get_enabled_vendors() == ["v1", "v2", "v3"]

        reg.set_vendor_enabled("v1", False)
        assert reg.get_enabled_vendors() == ["v2", "v3"]

    def test_orchestrator_bypasses_disabled_vendors(self):
        reg = VendorRegistry()
        reg.register_adapter("v_enabled", DummyTestAdapter, enabled=True)
        reg.register_adapter("v_disabled", DummyTestAdapter, enabled=False)

        orch = UniversalProcurementOrchestrator(registry=reg)
        req = ProcurementRequest(part_number="NE555P", required_quantity=10)

        # Default resolution queries only enabled vendors
        target_vids = orch._resolve_target_vendors(req)
        assert target_vids == ["v_enabled"]
        assert "v_disabled" not in target_vids

        # If caller specifies vendor list, disabled vendor is filtered out
        filtered_vids = orch._resolve_target_vendors(req, vendor_ids=["v_enabled", "v_disabled"])
        assert filtered_vids == ["v_enabled"]

    def test_orchestrator_explicit_disabled_url_returns_empty(self):
        reg = VendorRegistry()
        reg.register_adapter("v_active", DummyTestAdapter, domains=["active.ir"], enabled=True)
        reg.register_adapter("v_inactive", DummyTestAdapter, domains=["inactive.ir"], enabled=False)

        orch = UniversalProcurementOrchestrator(registry=reg)

        req_active = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://active.ir/item1")
        assert orch._resolve_target_vendors(req_active) == ["v_active"]

        req_inactive = ProcurementRequest(part_number="NE555P", required_quantity=10, explicit_vendor_url="https://inactive.ir/item2")
        assert orch._resolve_target_vendors(req_inactive) == []
