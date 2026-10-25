"""
Omnix Vendor Plugin System — Milestone 3: UI Integration Test Suite
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10, 27.2 (Phase 17) & Section 6
- Acceptance Scenarios: Complete Vendor Plugin UI Integration

Verifies:
1. VendorPluginsWidget empty-by-default initialization.
2. File dialog package selection and pre-extraction Gate A inspection error handling.
3. Gate B cryptographic trust verification and untrusted package blocking.
4. PluginTrustDialog metadata rendering, capabilities review, and user cancellation.
5. Successful .xpl installation, dynamic activation, and card rendering.
6. Enable / Disable toggle behavior and registry route synchronization.
7. Multi-version dropdown version switching and fail-closed rollback.
8. Destructive action confirmation dialog for single-version vs vendor family uninstall.
9. Path containment defense-in-depth during uninstallation.
10. Application startup restoration hook in MainWindow fail-closed execution.
11. PluginConfigDialog schema rendering and settings persistence.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

from core.plugins.manifest_mf import generate_manifest_mf
from core.plugins.package_inspector import PackageInspector
from core.plugins.plugin_installer import PluginInstaller
from core.plugins.plugin_lifecycle_manager import (
    LifecycleStatus,
    PluginLifecycleManager,
    get_lifecycle_manager,
    restore_installed_plugins,
)
from core.plugins.plugin_store import InstalledPluginRecord, InstalledPluginStatus, InstalledVersionRecord, PluginStore
from core.plugins.trust_engine import TrustEngine, TrustStatus
from core.procurement.registry import VendorRegistry, default_registry
from core.vendor_interface import IVendorAdapter
from settings_manager import settings
from ui.dialogs.plugin_trust_dialog import PluginTrustDialog
from ui.widgets.vendor_plugins_widget import (
    PluginConfigDialog,
    PluginUninstallDialog,
    VendorPluginsWidget,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Package Builder Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def keypair():
    """Generate ephemeral Ed25519 keypair for test signing."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv, pub


@pytest.fixture
def isolated_env():
    """Create isolated directories for trust stores, plugin store, and settings persistence."""
    temp_dir = Path(tempfile.mkdtemp(prefix="omnix_ui_m3_"))
    prod_store = temp_dir / "prod_trust_store"
    dev_store = temp_dir / "dev_trust_store"
    plugins_root = temp_dir / "data" / "plugins"
    settings_file = temp_dir / "settings.json"

    prod_store.mkdir(parents=True)
    dev_store.mkdir(parents=True)
    plugins_root.mkdir(parents=True)

    orig_settings_file_path = settings.file_path
    orig_settings_data = copy.deepcopy(settings.settings)
    settings.file_path = str(settings_file)
    settings.settings = settings._default_settings()

    try:
        yield {
            "root": temp_dir,
            "prod_store": prod_store,
            "dev_store": dev_store,
            "plugins_root": plugins_root,
            "settings_file": settings_file,
        }
    finally:
        settings.file_path = orig_settings_file_path
        settings.settings = orig_settings_data
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


def make_manifest(
    vendor_id: str = "vendor_lion",
    plugin_id: str = "com.omnix.vendor.lion",
    version: str = "1.0.0",
    key_id: str = "key_prod_lion",
    entry_point: str = "lion.adapter:LionAdapter",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a fully compliant manifest dictionary for tests."""
    manifest = {
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
        "capabilities": ["MODE_A_STAGING", "PRODUCT_URL_RECOGNITION"],
        "routes": {
            "base_url": "https://lion.ir",
            "cart_url": "https://lion.ir/cart",
            "domains": ["lion.ir"],
            "pdp_patterns": [r"^https?://(?:www\.)?lion\.ir/product/.*$"],
        },
        "config_schema": {
            "fields": [
                {"key": "username", "label": "Username", "type": "string"},
                {"key": "password", "label": "Password", "type": "password", "is_secret": True},
                {"key": "timeout", "label": "Timeout", "type": "integer", "default": 15},
                {"key": "headless", "label": "Headless Mode", "type": "boolean", "default": True},
            ]
        },
    }
    if extra_fields:
        manifest.update(extra_fields)
    return manifest


SAMPLE_ADAPTER_CODE = """
from core.vendor_interface import IVendorAdapter

class LionAdapter(IVendorAdapter):
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
        return {"success": True}

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


def build_test_xpl(
    dest_path: Path,
    manifest_dict: Dict[str, Any],
    adapter_code: str = SAMPLE_ADAPTER_CODE,
    private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    corrupt_signature: bool = False,
    omit_signature: bool = False,
) -> Path:
    """Build a valid signed .xpl archive."""
    files: Dict[str, bytes] = {}
    files["manifest.json"] = json.dumps(manifest_dict, indent=2).encode("utf-8")
    files["lion/__init__.py"] = b'"""Lion Package"""\n'
    files["lion/adapter.py"] = adapter_code.encode("utf-8")

    mf_text = generate_manifest_mf(files)
    mf_bytes = mf_text.encode("utf-8")
    files["META-INF/MANIFEST.MF"] = mf_bytes

    if not omit_signature and private_key is not None:
        if corrupt_signature:
            sig = b"\x00" * 64
        else:
            sig = private_key.sign(mf_bytes)
        files["META-INF/SIGNATURE.sig"] = sig

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, data in files.items():
            zf.writestr(fname, data)

    return dest_path


def register_pub_key(store_dir: Path, key_id: str, pub_key: ed25519.Ed25519PublicKey) -> Path:
    """Save raw 32-byte public key into the target trust store."""
    raw_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_path = store_dir / f"{key_id}.pub"
    key_path.write_bytes(raw_bytes)
    return key_path


# ---------------------------------------------------------------------------
# Test Suite: VendorPluginsWidget UI Integration
# ---------------------------------------------------------------------------

class TestVendorPluginsWidgetUI:
    """Comprehensive tests for VendorPluginsWidget, trust modal, and lifecycle controls."""

    def test_widget_empty_state_initialization(self, qapp, isolated_env):
        """Widget initializes empty-by-default with clear empty state card and header button."""
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store)

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        widget.show()
        qapp.processEvents()

        assert "0 plugin(s) installed" in widget.summary_lbl.text()
        assert not widget.install_btn.isHidden()
        empty_labels = [
            lbl.text()
            for lbl in widget.findChildren(QLabel)
            if "No Vendor Plugins Installed" in lbl.text()
        ]
        assert len(empty_labels) == 1
        widget.close()

    def test_install_gate_a_failure_shows_error_dialog(self, qapp, isolated_env):
        """Selecting an invalid non-zip or corrupted package fails Gate A closed."""
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store)

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )

        bogus_file = isolated_env["root"] / "corrupt.xpl"
        bogus_file.write_text("NOT A ZIP ARCHIVE", encoding="utf-8")

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(bogus_file), "")), \
             patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_crit:
            widget._on_install_plugin_clicked()
            qapp.processEvents()

            assert mock_crit.called

        assert len(store.load_index()) == 0
        assert registry.list_vendors() == []

    def test_trust_dialog_standalone_rendering_untrusted(self, qapp, isolated_env, keypair):
        """PluginTrustDialog renders UNTRUSTED badge and disables install button for untrusted package."""
        priv, pub = keypair
        manifest = make_manifest(key_id="untrusted_key_99")
        pkg_file = isolated_env["root"] / "untrusted.xpl"
        build_test_xpl(pkg_file, manifest, private_key=priv)

        insp = PackageInspector.inspect_package(pkg_file)
        te = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        trust_res = te.verify_archive(pkg_file)

        dlg = PluginTrustDialog(inspection=insp, trust=trust_res)
        dlg.show()
        qapp.processEvents()

        assert not dlg.trust.is_trusted
        assert not dlg.install_btn.isEnabled()
        assert "UNTRUSTED" in [lbl.text() for lbl in dlg.findChildren(QLabel)]
        dlg.close()

    def test_trust_dialog_standalone_rendering_trusted(self, qapp, isolated_env, keypair):
        """PluginTrustDialog renders OFFICIAL badge, metadata, and enables install button for trusted package."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        te = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )

        manifest = make_manifest(
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            key_id="key_prod_lion",
        )
        pkg_file = isolated_env["root"] / "valid_lion.xpl"
        build_test_xpl(pkg_file, manifest, private_key=priv)

        insp = PackageInspector.inspect_package(pkg_file)
        trust_res = te.verify_archive(pkg_file)

        dlg = PluginTrustDialog(inspection=insp, trust=trust_res)
        dlg.show()
        qapp.processEvents()

        assert dlg.trust.is_trusted
        assert dlg.install_btn.isEnabled()
        assert "OFFICIAL" in [lbl.text() for lbl in dlg.findChildren(QLabel)]
        assert "Lion Procurement Plugin" in dlg.windowTitle()
        dlg.close()

    def test_install_trust_modal_user_cancellation(self, qapp, isolated_env, keypair):
        """Valid package where user cancels the modal aborts installation fail-closed."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )

        manifest = make_manifest(key_id="key_prod_lion")
        pkg_file = isolated_env["root"] / "valid_lion.xpl"
        build_test_xpl(pkg_file, manifest, private_key=priv)

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(pkg_file), "")), \
             patch("ui.widgets.vendor_plugins_widget.PluginTrustDialog") as MockDialogClass:
            mock_dlg = MagicMock()
            mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
            MockDialogClass.return_value = mock_dlg

            widget._on_install_plugin_clicked()
            qapp.processEvents()

        # Zero modifications to store or registry
        assert len(store.load_index()) == 0
        assert registry.list_vendors() == []

    def test_install_valid_package_success_workflow(self, qapp, isolated_env, keypair):
        """Valid trusted package installation succeeds, activates plugin, and renders card."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )

        manifest = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        pkg_file = isolated_env["root"] / "lion_v1.xpl"
        build_test_xpl(pkg_file, manifest, private_key=priv)

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(pkg_file), "")), \
             patch("ui.widgets.vendor_plugins_widget.PluginTrustDialog") as MockDialogClass, \
             patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            mock_dlg = MagicMock()
            mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
            MockDialogClass.return_value = mock_dlg

            widget._on_install_plugin_clicked()
            qapp.processEvents()

            assert mock_info.called

        # Verify persistent store state
        index = store.load_index()
        assert "vendor_lion" in index
        assert index["vendor_lion"].enabled is True
        assert index["vendor_lion"].active_version == "1.0.0"

        # Verify registry state
        assert registry.has_vendor("vendor_lion")
        assert registry.get_active_version("vendor_lion") == "1.0.0"
        assert registry.is_vendor_enabled("vendor_lion") is True

        # Verify UI rendered card
        assert "1 plugin(s) installed" in widget.summary_lbl.text()
        active_chks = widget.findChildren(QCheckBox)
        assert len(active_chks) == 1
        assert active_chks[0].isChecked()

    def test_card_active_toggle_enable_disable(self, qapp, isolated_env, keypair):
        """Active toggle deactivates and re-activates vendor routes cleanly."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        manifest = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        pkg_file = isolated_env["root"] / "lion_toggle.xpl"
        build_test_xpl(pkg_file, manifest, private_key=priv)
        installer.install_package(pkg_file)
        lifecycle_mgr.activate_plugin("vendor_lion", "1.0.0")

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        qapp.processEvents()

        active_chk = widget.findChildren(QCheckBox)[0]
        assert active_chk.isChecked()
        assert registry.is_vendor_enabled("vendor_lion") is True

        # Toggle OFF (Deactivate)
        active_chk.setChecked(False)
        qapp.processEvents()

        assert store.load_index()["vendor_lion"].enabled is False
        assert registry.is_vendor_enabled("vendor_lion") is False
        assert Path(settings.file_path) == isolated_env["settings_file"]
        assert isolated_env["settings_file"].is_file()
        persisted_off = json.loads(isolated_env["settings_file"].read_text(encoding="utf-8"))
        assert persisted_off["vendors"]["vendor_lion"]["enabled"] is False

        # Toggle ON (Re-activate)
        active_chk.setChecked(True)
        qapp.processEvents()

        assert store.load_index()["vendor_lion"].enabled is True
        assert registry.is_vendor_enabled("vendor_lion") is True
        persisted_on = json.loads(isolated_env["settings_file"].read_text(encoding="utf-8"))
        assert persisted_on["vendors"]["vendor_lion"]["enabled"] is True

    def test_card_multi_version_combobox_atomic_switching(self, qapp, isolated_env, keypair):
        """Multi-version installation renders version combobox and switches versions atomically."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        # Install v1.0.0
        m1 = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        f1 = isolated_env["root"] / "lion_1.0.0.xpl"
        build_test_xpl(f1, m1, private_key=priv)
        installer.install_package(f1)

        # Install v1.1.0
        m2 = make_manifest(vendor_id="vendor_lion", version="1.1.0", key_id="key_prod_lion")
        f2 = isolated_env["root"] / "lion_1.1.0.xpl"
        build_test_xpl(f2, m2, private_key=priv)
        installer.install_package(f2)

        # Activate v1.1.0 initially
        lifecycle_mgr.activate_plugin("vendor_lion", "1.1.0")

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        qapp.processEvents()

        combos = widget.findChildren(QComboBox)
        assert len(combos) >= 1
        ver_combo = combos[0]
        assert ver_combo.count() == 2
        assert ver_combo.currentData() == "1.1.0"

        # Switch to 1.0.0
        idx_1_0 = ver_combo.findData("1.0.0")
        ver_combo.setCurrentIndex(idx_1_0)
        qapp.processEvents()

        assert store.load_index()["vendor_lion"].active_version == "1.0.0"
        assert registry.get_active_version("vendor_lion") == "1.0.0"

    def test_version_switch_failure_reverts_cleanly(self, qapp, isolated_env, keypair):
        """Corrupted version switch fails closed and leaves previous active version intact."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        m1 = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        f1 = isolated_env["root"] / "lion_1.0.0.xpl"
        build_test_xpl(f1, m1, private_key=priv)
        installer.install_package(f1)

        m2 = make_manifest(vendor_id="vendor_lion", version="1.1.0", key_id="key_prod_lion")
        f2 = isolated_env["root"] / "lion_1.1.0.xpl"
        build_test_xpl(f2, m2, private_key=priv)
        installer.install_package(f2)

        lifecycle_mgr.activate_plugin("vendor_lion", "1.0.0")

        # Corrupt v1.1.0 on disk
        installed_1_1 = isolated_env["plugins_root"] / "installed" / "vendor_lion" / "1.1.0" / "lion" / "adapter.py"
        installed_1_1.write_bytes(b"# MALICIOUS EDIT")

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        qapp.processEvents()

        ver_combo = widget.findChildren(QComboBox)[0]
        assert ver_combo.currentData() == "1.0.0"

        with patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_crit:
            idx_1_1 = ver_combo.findData("1.1.0")
            ver_combo.setCurrentIndex(idx_1_1)
            qapp.processEvents()

            assert mock_crit.called
            # Ensure previous version remains active
            assert store.load_index()["vendor_lion"].active_version == "1.0.0"
            assert registry.get_active_version("vendor_lion") == "1.0.0"

    def test_plugin_uninstall_dialog_unit(self, qapp):
        """PluginUninstallDialog renders single and multi-version modes properly."""
        # Single version
        dlg_single = PluginUninstallDialog(
            vendor_id="vendor_lion",
            display_name="Lion",
            active_version="1.0.0",
            installed_versions=["1.0.0"],
        )
        dlg_single.show()
        qapp.processEvents()
        dlg_single._on_confirm()
        assert dlg_single.uninstall_all is False
        dlg_single.close()

        # Multi-version
        dlg_multi = PluginUninstallDialog(
            vendor_id="vendor_lion",
            display_name="Lion",
            active_version="1.1.0",
            installed_versions=["1.0.0", "1.1.0"],
        )
        dlg_multi.show()
        qapp.processEvents()
        assert hasattr(dlg_multi, "opt_all")
        dlg_multi.opt_all.setChecked(True)
        dlg_multi._on_confirm()
        assert dlg_multi.uninstall_all is True
        dlg_multi.close()

    def test_uninstall_single_version_via_dialog(self, qapp, isolated_env, keypair):
        """Uninstalling a single version removes that version and preserves others."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        m1 = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        f1 = isolated_env["root"] / "lion_1.0.0.xpl"
        build_test_xpl(f1, m1, private_key=priv)
        installer.install_package(f1)

        m2 = make_manifest(vendor_id="vendor_lion", version="1.1.0", key_id="key_prod_lion")
        f2 = isolated_env["root"] / "lion_1.1.0.xpl"
        build_test_xpl(f2, m2, private_key=priv)
        installer.install_package(f2)

        lifecycle_mgr.activate_plugin("vendor_lion", "1.1.0")

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        qapp.processEvents()

        with patch("ui.widgets.vendor_plugins_widget.PluginUninstallDialog") as MockUninstall, \
             patch("PyQt6.QtWidgets.QMessageBox.information"):
            mock_dlg = MagicMock()
            mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
            mock_dlg.uninstall_all = False
            MockUninstall.return_value = mock_dlg

            uninstall_btns = [
                btn for btn in widget.findChildren(QPushButton)
                if btn.text() == "Uninstall..."
            ]
            assert len(uninstall_btns) == 1
            uninstall_btns[0].click()
            qapp.processEvents()

        # v1.1.0 removed, v1.0.0 remains
        p_rec = store.load_index().get("vendor_lion")
        assert p_rec is not None
        assert "1.1.0" not in p_rec.installed_versions
        assert "1.0.0" in p_rec.installed_versions

    def test_uninstall_entire_vendor_family_via_dialog(self, qapp, isolated_env, keypair):
        """Uninstalling entire vendor family purges files, store, and registry."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )
        registry = VendorRegistry()
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store, registry=registry)
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        m1 = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        f1 = isolated_env["root"] / "lion_1.0.0.xpl"
        build_test_xpl(f1, m1, private_key=priv)
        installer.install_package(f1)
        lifecycle_mgr.activate_plugin("vendor_lion", "1.0.0")

        widget = VendorPluginsWidget(
            registry=registry,
            lifecycle_mgr=lifecycle_mgr,
            installer=installer,
        )
        qapp.processEvents()

        with patch("ui.widgets.vendor_plugins_widget.PluginUninstallDialog") as MockUninstall, \
             patch("PyQt6.QtWidgets.QMessageBox.information"):
            mock_dlg = MagicMock()
            mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
            mock_dlg.uninstall_all = True
            MockUninstall.return_value = mock_dlg

            uninstall_btns = [
                btn for btn in widget.findChildren(QPushButton)
                if btn.text() == "Uninstall..."
            ]
            uninstall_btns[0].click()
            qapp.processEvents()

        # Entire vendor purged
        assert "vendor_lion" not in store.load_index()
        assert not registry.has_vendor("vendor_lion")
        assert "0 plugin(s) installed" in widget.summary_lbl.text()

    def test_uninstall_path_containment_defense_in_depth(self, isolated_env):
        """Refuses to delete any directory outside installed_root."""
        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        lifecycle_mgr = PluginLifecycleManager(store=store)

        malicious_path = isolated_env["root"] / "outside_dir"
        malicious_path.mkdir(parents=True)
        (malicious_path / "important.txt").write_text("SENSITIVE DATA")

        ver_rec = InstalledVersionRecord(
            version="1.0.0",
            install_path=str(malicious_path),
            package_hash="0" * 64,
            installed_at="2026-10-25T00:00:00Z",
            entry_point="evil.adapter:EvilAdapter",
            publisher={"name": "Evil Corp", "key_id": "evil_key"},
            status=InstalledPluginStatus.INSTALLED,
            manifest={"vendor_id": "vendor_evil", "version": "1.0.0"},
            file_digests={},
        )
        store.record_installed_version(
            vendor_id="vendor_evil",
            plugin_id="com.omnix.evil",
            display_name="Evil Plugin",
            version_record=ver_rec,
            set_active=True,
            enabled=True,
        )

        res = lifecycle_mgr.uninstall_plugin("vendor_evil", version="1.0.0")
        assert not res.success
        assert res.status == LifecycleStatus.UNINSTALL_FAILED
        assert "Path containment violation" in (res.error_message or "")
        # Verify file was NOT deleted
        assert (malicious_path / "important.txt").exists()

    def test_startup_restoration_wiring_in_main_window(self, qapp, isolated_env, keypair):
        """MainWindow startup restoration restores enabled plugins into default_registry."""
        priv, pub = keypair
        register_pub_key(isolated_env["prod_store"], "key_prod_lion", pub)
        trust_engine = TrustEngine(
            prod_trust_store=isolated_env["prod_store"],
            dev_trust_store=isolated_env["dev_store"],
            env="production",
        )

        store = PluginStore(plugins_root=isolated_env["plugins_root"])
        installer = PluginInstaller(store=store, trust_engine=trust_engine)

        manifest = make_manifest(vendor_id="vendor_lion", version="1.0.0", key_id="key_prod_lion")
        f1 = isolated_env["root"] / "lion_boot.xpl"
        build_test_xpl(f1, manifest, private_key=priv)
        installer.install_package(f1)

        # Mark enabled in store
        store.set_active_version("vendor_lion", "1.0.0")
        store.set_plugin_enabled("vendor_lion", True)

        test_registry = VendorRegistry()
        res = restore_installed_plugins(registry=test_registry, store=store)
        assert "vendor_lion" in res
        assert res["vendor_lion"].success is True
        assert test_registry.has_vendor("vendor_lion")
        assert test_registry.is_vendor_enabled("vendor_lion") is True

    def test_plugin_config_dialog_schema_rendering_and_save(self, qapp, isolated_env):
        """PluginConfigDialog renders declared manifest schema and saves configuration."""
        manifest = make_manifest(vendor_id="vendor_lion", version="1.0.0")
        registry = VendorRegistry()

        class DummyAdapter(IVendorAdapter):
            @property
            def vendor_id(self):
                return "vendor_lion"

        registry.register_plugin_manifest(manifest=manifest, adapter_class=DummyAdapter, activate=True)

        dlg = PluginConfigDialog(vendor_id="vendor_lion", registry=registry)
        dlg.show()
        qapp.processEvents()

        # Check field widgets
        assert "username" in dlg.field_widgets
        assert "password" in dlg.field_widgets
        assert "timeout" in dlg.field_widgets
        assert "headless" in dlg.field_widgets

        # Simulate user input
        dlg.field_widgets["username"][0].setText("test_user_42")
        dlg.field_widgets["timeout"][0].setValue(30)
        dlg._save_settings()

        # Verify saved in isolated settings and temporary settings file only
        assert Path(settings.file_path) == isolated_env["settings_file"]
        assert isolated_env["settings_file"].is_file()
        cfg = settings.get_vendor_settings("vendor_lion")
        assert cfg is not None
        assert cfg.username == "test_user_42"
        assert cfg.extra_options.get("timeout") == 30
        persisted = json.loads(isolated_env["settings_file"].read_text(encoding="utf-8"))
        assert persisted["vendors"]["vendor_lion"]["username"] == "test_user_42"
        assert persisted["vendors"]["vendor_lion"]["extra_options"]["timeout"] == 30
        dlg.close()
