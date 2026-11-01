"""
Omnix Vendor Plugin System — Milestone 2 Comprehensive Test Suite
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Verifies:
1. Empty-by-Default Invariant:
   - Fresh lifecycle manager and registry initialize empty (zero active vendors).
   - Attempting activation/deactivation of uninstalled vendors fails-closed with NOT_INSTALLED.
2. Dynamic Activation & Registration (Gate E):
   - Securely loads installed plugin through PluginLoader (validating authenticated digests, AST, paths).
   - Atomically registers manifest and adapter class in VendorRegistry.
   - Populates storefront domain routing and active version pointers.
   - Updates persistent store index (active_version, enabled=True).
3. Idempotent Activation & Deactivation:
   - Activating an already active plugin returns ALREADY_ACTIVE without error.
   - Deactivating removes domain routing and clears active pointer in VendorRegistry.
   - Deactivating an inactive plugin returns ALREADY_INACTIVE idempotently.
   - Re-activating a deactivated plugin restores routing seamlessly.
4. Security Integrity Gate — Tamper Resistance Before Activation:
   - Modifying any installed file causes pre-import digest verification failure (TAMPERED_FILES_DETECTED).
   - Corrupted/tampered files are NEVER imported or executed.
   - VendorRegistry remains completely pristine with zero partial state.
5. Security Integrity Gate — Missing Files Before Activation:
   - Deleting a required installed file fails activation with CORRUPTED_MISSING_FILES.
6. Contract Validation Gate — Incompatible Adapter:
   - Adapter not subclassing IVendorAdapter or missing abstract methods fails with LOAD_FAILED.
   - Registry is never mutated on contract failure.
7. Multi-Version Management & Version Switching:
   - Multiple versions installed side-by-side on disk.
   - Explicit atomic version switching swaps active pointer and domain routes in VendorRegistry.
   - Switching to a corrupted version fails-closed, preserving the currently active version.
8. Application Startup Recovery & Restoration:
   - Reconciles crash journals and unindexed directories via PluginStore.reconcile_on_startup().
   - Restores previously enabled plugins into VendorRegistry fail-closed.
   - Tampered/corrupted plugins fail safely without crashing application startup.
   - Disabled plugins remain dormant on disk.
9. Full Uninstallation Lifecycle:
   - Single version uninstall purges version files, unregisters from registry, and updates store.
   - Full vendor uninstall purges all vendor files, clears registry state, and deletes store record.
10. Status Reporting & Thread Safety:
    - get_plugin_status() provides accurate consolidated store and registry state.
    - Concurrent operations remain thread-safe under lock.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Any, Dict, Optional

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.models import AdapterConfig, AdapterStatus, ProductReference
from core.plugins.manifest_mf import generate_manifest_mf
from core.plugins.plugin_installer import PluginInstaller
from core.plugins.plugin_lifecycle_manager import (
    LifecycleResult,
    LifecycleStatus,
    PluginLifecycleManager,
    get_lifecycle_manager,
    restore_installed_plugins,
)
from core.plugins.plugin_loader import PluginLoader
from core.plugins.plugin_store import (
    InstalledPluginRecord,
    InstalledPluginStatus,
    InstalledVersionRecord,
    PluginStore,
)
from core.plugins.trust_engine import TrustEngine
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter


# ---------------------------------------------------------------------------
# Test Fixtures & Sample Code
# ---------------------------------------------------------------------------

SAMPLE_ADAPTER_CODE = """
from core.vendor_interface import IVendorAdapter
from .selectors import LION_SELECTORS

class LionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lion.ir"

    def __init__(self, config=None):
        self._config = config

    @property
    def vendor_id(self):
        return "vendor_lion"

    @property
    def base_url(self):
        return "https://lion.ir"

    def initialize(self, config=None):
        return None

    def search_part(self, query):
        return None

    def resolve_product(self, url_or_sku):
        return None

    def inspect_product(self, product_ref):
        return None

    def extract_product_data(self, dom_context):
        return None

    def inspect_stock(self, product_ref):
        return None

    def determine_order_constraints(self, product_ref):
        return None

    def add_to_cart(self, product_ref, quantity=1):
        return {"success": True, "selector": LION_SELECTORS.get("cart")}

    def inspect_cart(self):
        return None

    def authenticate(self, credentials=None, challenge_handler=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context):
        return None

    def close(self):
        pass
"""

SAMPLE_SELECTORS_CODE = """
LION_SELECTORS = {
    "cart": "#cart-btn",
    "search": "#search-input"
}
"""


def make_test_manifest(
    vendor_id: str = "vendor_lion",
    plugin_id: str = "com.omnix.vendor.lion",
    version: str = "1.0.0",
    key_id: str = "key_test_1",
    entry_point: str = "lion.adapter:LionAdapter",
    domains: Optional[list] = None,
) -> Dict[str, Any]:
    """Generate a valid schema-compliant manifest dictionary."""
    return {
        "manifest_version": "1.0.0",
        "plugin_id": plugin_id,
        "vendor_id": vendor_id,
        "display_name": "Lion Procurement Plugin",
        "version": version,
        "min_omnix_version": "2.0.0",
        "omnix_contract_version": "1.0.0",
        "entry_point": entry_point,
        "publisher": {
            "name": "Lion Electronics Inc.",
            "type": "OFFICIAL",
            "key_id": key_id,
        },
        "supported_modes": ["MODE_A"],
        "capabilities": ["MODE_A_STAGING"],
        "routes": {
            "base_url": "https://lion.ir",
            "cart_url": "https://lion.ir/cart",
            "domains": domains or ["lion.ir"],
            "pdp_patterns": [r"^https?://(?:www\.)?lion\.ir/product/.*$"],
        },
    }


@pytest.fixture
def isolated_env():
    """Create an isolated filesystem environment with store, loader, and registry."""
    import sys
    for mod in list(sys.modules.keys()):
        if mod.startswith("omnix_plugins."):
            sys.modules.pop(mod, None)

    temp_dir = Path(tempfile.mkdtemp(prefix="omnix_test_m2_"))
    plugins_root = temp_dir / "data" / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)

    store = PluginStore(plugins_root=plugins_root)
    loader = PluginLoader(store=store)
    registry = VendorRegistry()
    manager = PluginLifecycleManager(store=store, loader=loader, registry=registry)

    try:
        yield {
            "temp_dir": temp_dir,
            "plugins_root": plugins_root,
            "store": store,
            "loader": loader,
            "registry": registry,
            "manager": manager,
        }
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        for mod in list(sys.modules.keys()):
            if mod.startswith("omnix_plugins."):
                sys.modules.pop(mod, None)


def helper_create_installed_plugin(
    env: dict,
    vendor_id: str = "vendor_lion",
    plugin_id: str = "com.omnix.vendor.lion",
    version: str = "1.0.0",
    domains: Optional[list] = None,
    entry_point: str = "lion.adapter:LionAdapter",
    adapter_code: str = SAMPLE_ADAPTER_CODE,
    selectors_code: str = SAMPLE_SELECTORS_CODE,
    enabled: bool = False,
    set_active: bool = True,
) -> Path:
    """Directly lay out an installed plugin directory with authentic file digests."""
    store: PluginStore = env["store"]
    install_dir = store.installed_root / vendor_id / version
    pkg_dir = install_dir / "lion"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write package files
    manifest = make_test_manifest(
        vendor_id=vendor_id,
        plugin_id=plugin_id,
        version=version,
        entry_point=entry_point,
        domains=domains,
    )
    (install_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "selectors.py").write_text(selectors_code, encoding="utf-8")
    (pkg_dir / "adapter.py").write_text(adapter_code, encoding="utf-8")

    # 2. Compute authentic file digests
    file_digests = {}
    for root, _, files in os.walk(install_dir):
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(install_dir).as_posix()
            with open(full_p, "rb") as fh:
                file_digests[rel_p] = hashlib.sha256(fh.read()).hexdigest()

    # 3. Create version record in store
    ver_rec = InstalledVersionRecord(
        version=version,
        install_path=str(install_dir.resolve()),
        package_hash=hashlib.sha256(b"dummy_pkg_hash").hexdigest(),
        installed_at="2026-10-25T08:00:00Z",
        entry_point=entry_point,
        publisher={"name": "Lion Official", "key_id": "key_1"},
        status=InstalledPluginStatus.INSTALLED,
        manifest=manifest,
        file_digests=file_digests,
    )

    store.record_installed_version(
        vendor_id=vendor_id,
        plugin_id=plugin_id,
        display_name=manifest.get("display_name", vendor_id),
        version_record=ver_rec,
        set_active=set_active,
        enabled=enabled,
    )

    return install_dir


# ===========================================================================
# 1. Empty-by-Default Invariant Tests
# ===========================================================================

def test_empty_by_default_fresh_lifecycle(isolated_env):
    """An unconfigured lifecycle manager and registry initialize empty."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    assert reg.list_vendors() == []
    assert reg.list_active_vendors() == []
    assert reg.get_enabled_vendors() == []

    status = mgr.get_plugin_status("vendor_lion")
    assert status["is_installed"] is False
    assert status["is_registered_in_registry"] is False
    assert status["routed_domains"] == []


def test_lifecycle_operations_on_uninstalled_vendor_fail_closed(isolated_env):
    """Lifecycle actions on uninstalled plugins fail-closed without side effects."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    res_act = mgr.activate_plugin("vendor_unknown")
    assert res_act.success is False
    assert res_act.status == LifecycleStatus.NOT_INSTALLED

    res_deact = mgr.deactivate_plugin("vendor_unknown")
    assert res_deact.success is False
    assert res_deact.status == LifecycleStatus.NOT_INSTALLED

    res_switch = mgr.switch_active_version("vendor_unknown", "1.0.0")
    assert res_switch.success is False
    assert res_switch.status == LifecycleStatus.NOT_INSTALLED

    res_uninst = mgr.uninstall_plugin("vendor_unknown")
    assert res_uninst.success is False
    assert res_uninst.status == LifecycleStatus.NOT_INSTALLED

    assert reg.list_vendors() == []


# ===========================================================================
# 2. Dynamic Activation & Registration (Gate E) Tests
# ===========================================================================

def test_activation_of_valid_installed_plugin(isolated_env):
    """Installed plugin activates cleanly, registers in registry, and enables URL resolution."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    # Pre-activation: registry must be empty
    assert reg.list_vendors() == []
    assert reg.get_active_version("vendor_lion") is None
    adapter_pre, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter_pre is None

    # Execute activation
    res = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res.success is True
    assert res.status == LifecycleStatus.SUCCESS
    assert res.vendor_id == "vendor_lion"
    assert res.version == "1.0.0"
    assert res.registration is not None

    # Post-activation: registry and store state verified
    assert reg.has_vendor("vendor_lion") is True
    assert reg.has_active_vendor("vendor_lion") is True
    assert reg.get_active_version("vendor_lion") == "1.0.0"
    assert reg.is_vendor_enabled("vendor_lion") is True
    assert reg.get_enabled_vendors() == ["vendor_lion"]

    # Store state updated
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.enabled is True
    assert p_rec.active_version == "1.0.0"

    # URL resolution functions through newly activated adapter
    adapter, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter is not None
    assert isinstance(adapter, IVendorAdapter)
    assert adapter.vendor_id == "vendor_lion"
    assert adapter.base_url == "https://lion.ir"


def test_activation_without_explicit_version_uses_active_or_latest(isolated_env):
    """Calling activate_plugin() without version activates the active version from store."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.2.0", enabled=False, set_active=True)

    res = mgr.activate_plugin("vendor_lion")
    assert res.success is True
    assert res.status == LifecycleStatus.SUCCESS
    assert res.version == "1.2.0"
    assert reg.get_active_version("vendor_lion") == "1.2.0"


# ===========================================================================
# 3. Idempotent Activation & Deactivation Tests
# ===========================================================================

def test_activation_idempotence(isolated_env):
    """Activating an already active plugin returns ALREADY_ACTIVE safely without error."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    res1 = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res1.success is True
    assert res1.status == LifecycleStatus.SUCCESS

    # Second activation call
    res2 = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res2.success is True
    assert res2.status == LifecycleStatus.ALREADY_ACTIVE
    assert res2.vendor_id == "vendor_lion"
    assert res2.version == "1.0.0"

    assert reg.get_active_version("vendor_lion") == "1.0.0"


def test_deactivation_purges_routes_and_preserves_files(isolated_env):
    """Deactivating vendor purges domain routes, sets enabled=False, and keeps files on disk."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    install_dir = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0")
    mgr.activate_plugin("vendor_lion", "1.0.0")

    # Deactivate
    res_deact = mgr.deactivate_plugin("vendor_lion")
    assert res_deact.success is True
    assert res_deact.status == LifecycleStatus.SUCCESS

    # Registry state
    assert reg.get_active_version("vendor_lion") is None
    assert reg.is_vendor_enabled("vendor_lion") is False
    assert reg.get_enabled_vendors() == []
    adapter_deact, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter_deact is None

    # Persistent store state
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.enabled is False
    assert p_rec.active_version == "1.0.0"

    # Files remain intact on disk
    assert install_dir.is_dir()
    assert (install_dir / "manifest.json").is_file()


def test_deactivation_idempotence(isolated_env):
    """Deactivating an already inactive plugin returns ALREADY_INACTIVE safely."""
    mgr: PluginLifecycleManager = isolated_env["manager"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    # Deactivating initially disabled plugin
    res = mgr.deactivate_plugin("vendor_lion")
    assert res.success is True
    assert res.status == LifecycleStatus.ALREADY_INACTIVE


def test_reactivation_after_deactivation(isolated_env):
    """A deactivated plugin can be cleanly re-activated without duplicate registration errors."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0")
    mgr.activate_plugin("vendor_lion", "1.0.0")
    mgr.deactivate_plugin("vendor_lion")

    adapter_deact, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter_deact is None

    # Re-activate
    res_reactivate = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res_reactivate.success is True
    assert res_reactivate.status == LifecycleStatus.SUCCESS

    assert reg.get_active_version("vendor_lion") == "1.0.0"
    adapter_react, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter_react is not None


# ===========================================================================
# 4. Security Integrity Gate — Tamper Resistance Tests
# ===========================================================================

def test_tampered_installed_file_blocks_activation(isolated_env):
    """Modifying an installed file causes digest mismatch, blocking activation fail-closed."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    install_dir = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    # Tamper with selectors.py by appending unauthorized payload
    selectors_p = install_dir / "lion" / "selectors.py"
    selectors_p.write_text(selectors_p.read_text(encoding="utf-8") + "\n# MALICIOUS_INJECTION = True\n", encoding="utf-8")

    # Attempt activation
    res = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res.success is False
    assert res.status == LifecycleStatus.TAMPERED_FILES_DETECTED
    assert "Digest mismatch" in res.error_message

    # Registry must remain untouched
    assert reg.list_vendors() == []
    assert reg.get_active_version("vendor_lion") is None

    # Store must record TAMPERED_FILES_DETECTED and disabled
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.enabled is False
    assert p_rec.installed_versions["1.0.0"].status == InstalledPluginStatus.TAMPERED_FILES_DETECTED


def test_missing_installed_file_blocks_activation(isolated_env):
    """Deleting a required file fails activation with CORRUPTED_MISSING_FILES."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    install_dir = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    # Delete selectors.py
    (install_dir / "lion" / "selectors.py").unlink()

    res = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res.success is False
    assert res.status == LifecycleStatus.CORRUPTED_MISSING_FILES
    assert "missing" in res.error_message.lower()

    assert reg.list_vendors() == []
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.enabled is False
    assert p_rec.installed_versions["1.0.0"].status == InstalledPluginStatus.CORRUPTED_MISSING_FILES


# ===========================================================================
# 5. Contract Validation Gate Tests
# ===========================================================================

def test_non_subclass_adapter_blocks_activation(isolated_env):
    """Adapter class not inheriting from IVendorAdapter fails with LOAD_FAILED."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    bad_adapter_code = """
class LionAdapter:
    pass
"""
    helper_create_installed_plugin(
        isolated_env,
        vendor_id="vendor_lion",
        version="1.0.0",
        adapter_code=bad_adapter_code,
        enabled=False,
    )

    res = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res.success is False
    assert res.status == LifecycleStatus.LOAD_FAILED
    assert "IVendorAdapter" in res.error_message

    assert reg.list_vendors() == []


def test_missing_abstract_methods_blocks_activation(isolated_env):
    """Adapter class failing to implement mandatory IVendorAdapter methods fails with LOAD_FAILED."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    partial_adapter_code = """
from core.vendor_interface import IVendorAdapter

class LionAdapter(IVendorAdapter):
    # Only implements vendor_id, missing other 14 abstract methods
    @property
    def vendor_id(self) -> str:
        return "vendor_lion"
"""
    helper_create_installed_plugin(
        isolated_env,
        vendor_id="vendor_lion",
        version="1.0.0",
        adapter_code=partial_adapter_code,
        enabled=False,
    )

    res = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res.success is False
    assert res.status == LifecycleStatus.LOAD_FAILED
    assert "mandatory IVendorAdapter operations" in res.error_message

    assert reg.list_vendors() == []


# ===========================================================================
# 6. Multi-Version Indexing & Version Switching Tests
# ===========================================================================

def test_multi_version_installation_and_atomic_switching(isolated_env):
    """Multiple versions can be installed and switched atomically under lock."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    # Install v1.0.0
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False, set_active=True)

    # Install v1.1.0 side-by-side
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.1.0", enabled=False, set_active=False)

    p_rec = store.get_plugin("vendor_lion")
    assert len(p_rec.installed_versions) == 2
    assert "1.0.0" in p_rec.installed_versions
    assert "1.1.0" in p_rec.installed_versions

    # Activate v1.0.0
    res_act = mgr.activate_plugin("vendor_lion", "1.0.0")
    assert res_act.success is True
    assert reg.get_active_version("vendor_lion") == "1.0.0"

    # Switch to v1.1.0
    res_switch = mgr.switch_active_version("vendor_lion", "1.1.0")
    assert res_switch.success is True
    assert res_switch.status == LifecycleStatus.SUCCESS
    assert res_switch.version == "1.1.0"

    # Verify registry active pointer and store active_version updated
    assert reg.get_active_version("vendor_lion") == "1.1.0"
    p_rec_updated = store.get_plugin("vendor_lion")
    assert p_rec_updated.active_version == "1.1.0"
    assert p_rec_updated.enabled is True

    # Switching to already active version returns ALREADY_ACTIVE
    res_idempotent = mgr.switch_active_version("vendor_lion", "1.1.0")
    assert res_idempotent.success is True
    assert res_idempotent.status == LifecycleStatus.ALREADY_ACTIVE


def test_switch_to_corrupted_version_preserves_active_version(isolated_env):
    """If candidate version fails integrity check, existing active version remains intact."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    # Install healthy v1.0.0 and active
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False, set_active=True)
    mgr.activate_plugin("vendor_lion", "1.0.0")
    assert reg.get_active_version("vendor_lion") == "1.0.0"

    # Install v1.1.0 and corrupt it
    dir_110 = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.1.0", enabled=False, set_active=False)
    (dir_110 / "lion" / "adapter.py").write_text("# Corrupted content", encoding="utf-8")

    # Attempt switch to corrupted v1.1.0
    res_switch = mgr.switch_active_version("vendor_lion", "1.1.0")
    assert res_switch.success is False
    assert res_switch.status == LifecycleStatus.TAMPERED_FILES_DETECTED

    # Invariant: v1.0.0 remains active and uncorrupted in registry and store
    assert reg.get_active_version("vendor_lion") == "1.0.0"
    assert reg.is_vendor_enabled("vendor_lion") is True
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.active_version == "1.0.0"
    assert p_rec.enabled is True


# ===========================================================================
# 7. Application Startup Recovery & Restoration Tests
# ===========================================================================

def test_startup_restores_previously_enabled_plugins(isolated_env):
    """Startup reconciliation restores enabled plugins into a clean registry."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    # Create enabled plugin in store
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=True, set_active=True)

    # Registry starts fresh/empty
    assert reg.list_vendors() == []

    # Run startup restoration
    results = mgr.restore_on_startup()
    assert "vendor_lion" in results
    assert results["vendor_lion"].success is True
    assert results["vendor_lion"].status == LifecycleStatus.SUCCESS

    # Plugin is now active in registry
    assert reg.has_active_vendor("vendor_lion") is True
    assert reg.get_active_version("vendor_lion") == "1.0.0"
    adapter_boot, _ = reg.resolve_adapter_for_url("https://lion.ir/product/123")
    assert adapter_boot is not None


def test_startup_skips_disabled_plugins(isolated_env):
    """Startup reconciliation leaves disabled plugins dormant on disk."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    # Create disabled plugin in store
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False, set_active=True)

    results = mgr.restore_on_startup()
    # Not attempted / not restored
    assert "vendor_lion" not in results
    assert reg.list_vendors() == []


def test_startup_handles_tampered_plugin_without_crashing(isolated_env):
    """A tampered plugin marked enabled fails closed on startup without crashing the host."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    dir_lion = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=True, set_active=True)
    # Corrupt a file
    (dir_lion / "lion" / "adapter.py").write_text("# Corrupt payload", encoding="utf-8")

    results = mgr.restore_on_startup()
    assert "vendor_lion" in results
    assert results["vendor_lion"].success is False
    assert results["vendor_lion"].status == LifecycleStatus.TAMPERED_FILES_DETECTED

    # Registry remains completely empty
    assert reg.list_vendors() == []

    # Store index updated to disabled
    p_rec = store.get_plugin("vendor_lion")
    assert p_rec.enabled is False


# ===========================================================================
# 8. Uninstallation Lifecycle Tests
# ===========================================================================

def test_uninstall_single_version(isolated_env):
    """Uninstalling a single version removes its directory and store record while keeping older versions."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    dir_100 = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)
    dir_110 = helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.1.0", enabled=False)

    mgr.activate_plugin("vendor_lion", "1.1.0")
    assert reg.get_active_version("vendor_lion") == "1.1.0"

    # Uninstall version 1.1.0
    res_uninst = mgr.uninstall_plugin("vendor_lion", "1.1.0")
    assert res_uninst.success is True
    assert res_uninst.status == LifecycleStatus.SUCCESS

    # 1.1.0 files deleted, 1.0.0 files remain
    assert not dir_110.exists()
    assert dir_100.is_dir()

    # Invariant: active pointer cleared (no silent auto-fallback)
    p_rec = store.get_plugin("vendor_lion")
    assert "1.1.0" not in p_rec.installed_versions
    assert "1.0.0" in p_rec.installed_versions
    assert p_rec.active_version is None
    assert p_rec.enabled is False
    assert reg.get_active_version("vendor_lion") is None


def test_uninstall_entire_vendor_family(isolated_env):
    """Uninstalling entire vendor purges all versions, files, and index records."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]
    store: PluginStore = isolated_env["store"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0")
    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.1.0")
    mgr.activate_plugin("vendor_lion", "1.0.0")

    # Complete uninstall
    res = mgr.uninstall_plugin("vendor_lion")
    assert res.success is True
    assert res.status == LifecycleStatus.SUCCESS

    # Registry clean
    assert reg.has_vendor("vendor_lion") is False

    # Disk files purged
    vendor_root = store.installed_root / "vendor_lion"
    assert not vendor_root.exists()

    # Store record deleted
    assert store.get_plugin("vendor_lion") is None


# ===========================================================================
# 9. Status Reporting & Thread Safety Tests
# ===========================================================================

def test_get_plugin_status_reporting(isolated_env):
    """get_plugin_status() returns accurate combined store and registry state."""
    mgr: PluginLifecycleManager = isolated_env["manager"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", domains=["lion.ir"], enabled=False)

    status_before = mgr.get_plugin_status("vendor_lion")
    assert status_before["is_installed"] is True
    assert status_before["installed_versions"] == ["1.0.0"]
    assert status_before["enabled_store"] is False
    assert status_before["is_enabled_in_registry"] is False

    mgr.activate_plugin("vendor_lion", "1.0.0")

    status_after = mgr.get_plugin_status("vendor_lion")
    assert status_after["is_installed"] is True
    assert status_after["active_version_store"] == "1.0.0"
    assert status_after["enabled_store"] is True
    assert status_after["is_registered_in_registry"] is True
    assert status_after["active_version_registry"] == "1.0.0"
    assert status_after["is_enabled_in_registry"] is True
    assert status_after["routed_domains"] == ["lion.ir"]


def test_concurrent_lifecycle_operations_under_lock(isolated_env):
    """Concurrent activation and deactivation calls maintain data integrity without deadlocks."""
    mgr: PluginLifecycleManager = isolated_env["manager"]
    reg: VendorRegistry = isolated_env["registry"]

    helper_create_installed_plugin(isolated_env, vendor_id="vendor_lion", version="1.0.0", enabled=False)

    errors = []

    def worker_activate():
        for _ in range(15):
            res = mgr.activate_plugin("vendor_lion", "1.0.0")
            if not res.success:
                errors.append(f"Activation error: {res.error_message}")

    def worker_deactivate():
        for _ in range(15):
            res = mgr.deactivate_plugin("vendor_lion")
            if not res.success:
                errors.append(f"Deactivation error: {res.error_message}")

    t1 = threading.Thread(target=worker_activate)
    t2 = threading.Thread(target=worker_deactivate)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == [], f"Thread errors encountered: {errors}"
    # Verify final state is consistent
    active_ver = reg.get_active_version("vendor_lion")
    assert active_ver in ("1.0.0", None)
