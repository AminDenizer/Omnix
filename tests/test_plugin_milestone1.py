"""
Omnix Vendor Plugin System — Milestone 1 Comprehensive Test Suite
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Covers:
1. Trust Engine & Ed25519 Cryptographic Verification:
   - Valid signature verification in production trust store.
   - Missing, malformed, tampered signatures rejected fail-closed.
   - Production vs Development trust domain separation.
   - Explicit development key authorization (authorized_keys.json).
   - Revocation list checking (revocations.json).
   - Sentinel proof: untrusted/rejected code is NEVER imported or executed.
2. Plugin Store, Durable Index & Transaction Journaling:
   - Multi-version indexing (side-by-side versions).
   - Atomic index persistence and fsync replacement.
   - Durable transaction journaling and state advancement.
3. Crash Recovery & Fault Injection:
   - Pre-sweep journal reconciliation.
   - Recovery of unpersisted promotions after crash.
   - Quarantine of damaged/interrupted promotions.
   - Quarantine of orphaned staging folders.
   - Quarantine of unindexed installed directories.
   - Detection and flagging of deleted/corrupted installations.
4. Plugin Installer:
   - End-to-end installation transaction.
   - Pre-extraction trust verification invariant.
   - Destination collision check (identical hash vs version clash).
   - Static AST pre-promotion contract inspection (zero code execution).
5. Plugin Loader & Runtime Boundary:
   - Dynamic import from permanent paths into isolated synthetic namespaces.
   - Support for package-relative imports (e.g. from .selectors import ...).
   - Zero sys.path manipulation guarantee.
   - IVendorAdapter contract validation and error trapping.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.plugins.manifest_mf import ManifestMF, generate_manifest_mf
from core.plugins.manifest_validator import ManifestValidator
from core.plugins.package_inspector import PackageInspector
from core.plugins.plugin_installer import PluginInstallationResult, PluginInstaller
from core.plugins.plugin_loader import PluginLoader, PluginLoadResult
from core.plugins.plugin_store import (
    InstalledPluginRecord,
    InstalledPluginStatus,
    InstalledVersionRecord,
    PluginStore,
    TransactionJournal,
    TransactionState,
)
from core.plugins.trust_engine import (
    ED25519_PUBLIC_KEY_LENGTH_BYTES,
    ED25519_SIGNATURE_LENGTH_BYTES,
    TrustEngine,
    TrustStatus,
    TrustVerificationError,
    TrustVerificationResult,
)
from core.vendor_interface import IVendorAdapter


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def keypair():
    """Generate an ephemeral Ed25519 keypair for testing."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv, pub


@pytest.fixture
def temp_environment():
    """Create a pristine isolated directory structure for tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="omnix_test_m1_"))
    prod_store = temp_dir / "prod_trust_store"
    dev_store = temp_dir / "dev_trust_store"
    plugins_root = temp_dir / "data" / "plugins"

    prod_store.mkdir(parents=True)
    dev_store.mkdir(parents=True)
    plugins_root.mkdir(parents=True)

    yield {
        "root": temp_dir,
        "prod_store": prod_store,
        "dev_store": dev_store,
        "plugins_root": plugins_root,
    }

    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


def make_manifest(
    vendor_id: str = "vendor_lion",
    plugin_id: str = "com.omnix.vendor.lion",
    version: str = "1.0.0",
    key_id: str = "key_lion_1",
    entry_point: str = "lion.adapter:LionAdapter",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a fully compliant manifest dictionary."""
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
        "capabilities": ["MODE_A_STAGING"],
        "routes": {
            "base_url": "https://lion.ir",
            "cart_url": "https://lion.ir/cart",
            "domains": ["lion.ir"],
            "pdp_patterns": [r"^https?://(?:www\.)?lion\.ir/product/.*$"],
        },
    }
    if extra_fields:
        manifest.update(extra_fields)
    return manifest


SAMPLE_ADAPTER_CODE = """
from core.vendor_interface import IVendorAdapter
from .selectors import LION_SELECTORS

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


def build_test_xpl(
    dest_path: Path,
    manifest_dict: Dict[str, Any],
    adapter_code: str = SAMPLE_ADAPTER_CODE,
    selectors_code: str = SAMPLE_SELECTORS_CODE,
    private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    corrupt_signature: bool = False,
    omit_signature: bool = False,
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
) -> Path:
    """Build a complete, syntactically and structurally valid .xpl archive."""
    files: Dict[str, bytes] = {}

    # 1. manifest.json
    files["manifest.json"] = json.dumps(manifest_dict, indent=2).encode("utf-8")

    # 2. Python modules
    files["lion/__init__.py"] = b'"""Lion Vendor Package"""\n'
    files["lion/adapter.py"] = adapter_code.encode("utf-8")
    files["lion/selectors.py"] = selectors_code.encode("utf-8")

    if extra_files:
        for k, v in extra_files.items():
            files[k] = v.encode("utf-8") if isinstance(v, str) else v

    # 3. META-INF/MANIFEST.MF
    mf_text = generate_manifest_mf(files)
    mf_bytes = mf_text.encode("utf-8")
    files["META-INF/MANIFEST.MF"] = mf_bytes

    # 4. Detached Signature
    if not omit_signature and private_key is not None:
        if corrupt_signature:
            sig = b"\x00" * 64
        else:
            sig = private_key.sign(mf_bytes)
        files["META-INF/SIGNATURE.sig"] = sig

    # Write ZIP
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, data in files.items():
            zf.writestr(fname, data)

    return dest_path


def write_public_key_pem(dest_path: Path, pub_key: ed25519.Ed25519PublicKey) -> None:
    """Write public key in PEM format."""
    pem_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(pem_bytes)


# ===========================================================================
# 1. Test Suite: TrustEngine & Signature Verification
# ===========================================================================

class TestTrustEngine:
    """Validates Ed25519 signature checks, trust stores, and domain separation."""

    def test_verify_signature_production_success(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )

        manifest_mf_bytes = b"Manifest-Version: 1.0\r\nSHA-256-Digest-Manifest: abc\r\n\r\n"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id=key_id,
            publisher_name="Lion Official",
        )

        assert result.is_trusted is True
        assert result.status == TrustStatus.TRUSTED_PRODUCTION
        assert result.key_id == key_id
        assert result.fingerprint is not None
        assert len(result.fingerprint) == 64

    def test_verify_signature_missing_signature(self, temp_environment):
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        result = engine.verify_manifest_signature(
            manifest_mf_bytes=b"sample manifest mf",
            signature_bytes=None,
            key_id="some_key",
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_MISSING_SIGNATURE
        with pytest.raises(TrustVerificationError):
            result.raise_for_errors()

    def test_verify_signature_malformed_length(self, temp_environment):
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        result = engine.verify_manifest_signature(
            manifest_mf_bytes=b"sample manifest mf",
            signature_bytes=b"\x01\x02\x03",  # only 3 bytes, must be 64
            key_id="some_key",
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_MALFORMED_SIGNATURE

    def test_verify_signature_tampered_payload_or_signature(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )

        manifest_mf_bytes = b"Original manifest bytes"
        sig_bytes = priv.sign(manifest_mf_bytes)

        # Alter manifest bytes after signing
        tampered_manifest = b"Tampered manifest bytes!"
        result = engine.verify_manifest_signature(
            manifest_mf_bytes=tampered_manifest,
            signature_bytes=sig_bytes,
            key_id=key_id,
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_INVALID_SIGNATURE

    def test_verify_signature_unknown_key(self, temp_environment, keypair):
        priv, _ = keypair
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        manifest_mf_bytes = b"Test bytes"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id="nonexistent_key_id",
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_UNKNOWN_KEY

    def test_verify_signature_revoked_key_in_production(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "revoked_prod_key"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        # Write revocation entry
        rev_file = temp_environment["prod_store"] / "revocations.json"
        with open(rev_file, "w", encoding="utf-8") as f:
            json.dump({"revoked_keys": [key_id]}, f)

        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        manifest_mf_bytes = b"Test data"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id=key_id,
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_REVOKED_KEY

    def test_verify_signature_dev_key_rejected_in_production_mode(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_dev_tester"
        write_public_key_pem(temp_environment["dev_store"] / f"{key_id}.pub", pub)

        # Running in production mode: dev keys MUST be rejected
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        manifest_mf_bytes = b"Dev test package"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id=key_id,
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_PROD_DEV_MISMATCH

    def test_verify_signature_dev_key_accepted_in_dev_mode_with_authorization(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_dev_authorized"
        write_public_key_pem(temp_environment["dev_store"] / f"{key_id}.pub", pub)

        # Authorize key in authorized_keys.json
        auth_file = temp_environment["dev_store"] / "authorized_keys.json"
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump({"authorized_keys": [key_id]}, f)

        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="development",
        )
        manifest_mf_bytes = b"Dev authorized payload"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id=key_id,
        )
        assert result.is_trusted is True
        assert result.status == TrustStatus.TRUSTED_DEVELOPMENT

    def test_verify_signature_dev_key_rejected_without_explicit_authorization(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_dev_unauthorized"
        write_public_key_pem(temp_environment["dev_store"] / f"{key_id}.pub", pub)

        # authorized_keys.json exists but does NOT include key_id
        auth_file = temp_environment["dev_store"] / "authorized_keys.json"
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump({"authorized_keys": ["some_other_dev_key"]}, f)

        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="development",
        )
        manifest_mf_bytes = b"Dev test payload"
        sig_bytes = priv.sign(manifest_mf_bytes)

        result = engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=sig_bytes,
            key_id=key_id,
        )
        assert result.is_trusted is False
        assert result.status == TrustStatus.REJECTED_UNAUTHORIZED_DEV_KEY

    def test_sentinel_proof_untrusted_code_never_executed(self, temp_environment, keypair):
        """
        Proof of Pre-Execution Trust Boundary Invariant:
        An untrusted package containing executable code that would write a sentinel file
        upon module import is rejected strictly before extraction or execution.
        """
        priv, _ = keypair
        sentinel_file = temp_environment["root"] / "MALICIOUS_EXECUTION_TRIGGERED.txt"
        assert not sentinel_file.exists()

        # Malicious module code that writes to sentinel_file if imported
        malicious_adapter_code = f"""
from core.vendor_interface import IVendorAdapter
with open(r"{sentinel_file}", "w") as f:
    f.write("Pwned!")

class LionAdapter(IVendorAdapter):
    pass
"""
        manifest = make_manifest(key_id="untrusted_key_123")
        archive_path = temp_environment["root"] / "malicious.xpl"

        # Build package without valid trust store entry
        build_test_xpl(
            archive_path,
            manifest_dict=manifest,
            adapter_code=malicious_adapter_code,
            private_key=priv,
        )

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        installer = PluginInstaller(store=store, trust_engine=engine)

        install_res = installer.install_package(archive_path)
        assert install_res.success is False
        assert install_res.status == TrustStatus.REJECTED_UNKNOWN_KEY.value

        # Invariant: Sentinel file was NEVER created
        assert not sentinel_file.exists(), "CRITICAL FAULT: Untrusted code executed during installation attempt!"


# ===========================================================================
# 2. Test Suite: PluginStore, Persistence & Journaling
# ===========================================================================

class TestPluginStore:
    """Validates durability of installed_plugins.json, side-by-side versions, and journals."""

    def test_store_directory_structure_created(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        assert store.staging_root.is_dir()
        assert store.installed_root.is_dir()
        assert store.quarantine_root.is_dir()

    def test_store_atomic_index_save_and_reload(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        assert store.load_index() == {}

        ver_rec = InstalledVersionRecord(
            version="1.0.0",
            install_path=str(store.installed_root / "vendor_lion" / "1.0.0"),
            package_hash="sha256_dummy_hash",
            installed_at="2026-10-25T10:00:00Z",
            entry_point="lion.adapter:LionAdapter",
            publisher={"name": "Lion", "key_id": "k1"},
            status=InstalledPluginStatus.INSTALLED,
        )

        store.record_installed_version(
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            display_name="Lion Vendor",
            version_record=ver_rec,
            set_active=True,
            enabled=True,
        )

        # Reload store afresh
        store2 = PluginStore(plugins_root=temp_environment["plugins_root"])
        idx = store2.load_index()
        assert "vendor_lion" in idx
        lion = idx["vendor_lion"]
        assert lion.active_version == "1.0.0"
        assert lion.enabled is True
        assert "1.0.0" in lion.installed_versions
        assert lion.installed_versions["1.0.0"].package_hash == "sha256_dummy_hash"

    def test_store_multi_version_coexistence(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])

        v1 = InstalledVersionRecord(
            version="1.0.0",
            install_path=str(store.installed_root / "vendor_lion" / "1.0.0"),
            package_hash="hash_v1",
            installed_at="2026-10-25T10:00:00Z",
            entry_point="lion.adapter:LionAdapter",
            publisher={},
        )
        v2 = InstalledVersionRecord(
            version="1.1.0",
            install_path=str(store.installed_root / "vendor_lion" / "1.1.0"),
            package_hash="hash_v2",
            installed_at="2026-10-25T11:00:00Z",
            entry_point="lion.adapter:LionAdapter",
            publisher={},
        )

        store.record_installed_version("vendor_lion", "com.omnix.vendor.lion", "Lion", v1, set_active=True)
        store.record_installed_version("vendor_lion", "com.omnix.vendor.lion", "Lion", v2, set_active=True)

        idx = store.load_index()
        lion = idx["vendor_lion"]
        assert lion.active_version == "1.1.0"
        assert len(lion.installed_versions) == 2
        assert "1.0.0" in lion.installed_versions
        assert "1.1.0" in lion.installed_versions

    def test_store_journal_lifecycle(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_test_123"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"
        archive_path = temp_environment["root"] / "archive.xpl"

        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash123",
            archive_path=archive_path,
            staging_dir=staging_dir,
            target_dir=target_dir,
        )
        assert journal.state == TransactionState.TX_CREATED

        # Check journal written to disk
        loaded_j = store.load_journal(staging_dir)
        assert loaded_j is not None
        assert loaded_j.tx_id == tx_id
        assert loaded_j.state == TransactionState.TX_CREATED

        # Advance state
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)
        loaded_j2 = store.load_journal(staging_dir)
        assert loaded_j2.state == TransactionState.PROMOTION_STARTED

    def test_store_quarantine_directory(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        damaged_dir = temp_environment["root"] / "damaged_folder"
        damaged_dir.mkdir()
        (damaged_dir / "test.txt").write_text("corrupted content", encoding="utf-8")

        q_path = store.quarantine_directory(damaged_dir, "Manual test quarantine")
        assert not damaged_dir.exists()
        assert q_path.is_dir()
        assert (q_path / "test.txt").is_file()
        assert (q_path / ".quarantine_reason.txt").is_file()


# ===========================================================================
# 3. Test Suite: Crash Recovery & Fault Injection
# ===========================================================================

class TestCrashRecoveryAndFaultInjection:
    """Simulates crashes at critical transaction boundaries and verifies self-healing."""

    def test_recovery_cleans_unpromoted_staging(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        staging_dir = store.staging_root / "tx_crashed_before_promotion"
        staging_dir.mkdir(parents=True)
        (staging_dir / "payload").mkdir()

        journal = store.create_journal(
            tx_id="tx_crashed_before_promotion",
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=store.installed_root / "vendor_lion" / "1.0.0",
        )
        store.advance_journal(journal, TransactionState.EXTRACTION_VERIFIED)

        # Crash occurred before promotion
        messages = store.reconcile_on_startup()
        assert not staging_dir.exists(), "Unpromoted staging directory was not cleaned"
        assert store.load_index() == {}, "Unpromoted plugin was incorrectly registered"

    def test_recovery_reconciles_completed_promotion_before_persistence(self, temp_environment):
        """
        Fault: Process dies immediately AFTER atomic folder promotion, BEFORE writing installed_plugins.json.
        Recovery: Detects PROMOTION_COMPLETED journal, reads metadata, adds record to index, and cleans staging.
        """
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crashed_after_promotion"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        # Simulate promoted folder existing on disk
        target_dir.mkdir(parents=True)
        manifest_data = make_manifest()
        (target_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash_promoted_100",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest_data,
        )
        store.advance_journal(journal, TransactionState.PROMOTION_COMPLETED)

        # Boot recovery runs
        messages = store.reconcile_on_startup()
        assert any("Reconciling interrupted persistence" in m for m in messages)
        assert not staging_dir.exists()

        # Prove index now contains recovered version
        idx = store.load_index()
        assert "vendor_lion" in idx
        assert "1.0.0" in idx["vendor_lion"].installed_versions
        assert idx["vendor_lion"].installed_versions["1.0.0"].package_hash == "hash_promoted_100"

    def test_recovery_quarantines_incomplete_promotion(self, temp_environment):
        """
        Fault: Process dies while moving files (PROMOTION_STARTED), leaving corrupt folder.
        Recovery: Detects missing manifest.json in destination, moves corrupt destination to .quarantine/.
        """
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crashed_during_promotion"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        # Corrupt destination (no manifest.json)
        target_dir.mkdir(parents=True)
        (target_dir / "partial.bin").write_text("incomplete", encoding="utf-8")

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=target_dir,
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()
        assert any("Quarantining incomplete promotion" in m for m in messages)
        assert not target_dir.exists()

        # Destination was preserved in quarantine
        quarantine_dirs = list(store.quarantine_root.iterdir())
        assert len(quarantine_dirs) > 0

    def test_recovery_quarantines_unindexed_installed_folder(self, temp_environment):
        """
        Fault: Rogue or untracked directory physically created in installed/.
        Recovery: Quarantined to .quarantine/.
        """
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        rogue_dir = store.installed_root / "vendor_rogue" / "1.0.0"
        rogue_dir.mkdir(parents=True)
        (rogue_dir / "manifest.json").write_text("{}", encoding="utf-8")

        messages = store.reconcile_on_startup()
        assert any("Quarantining unindexed installation directory" in m for m in messages)
        assert not rogue_dir.exists()

    def test_recovery_flags_missing_installation_as_corrupted(self, temp_environment):
        """
        Fault: A registered version in installed_plugins.json is deleted from disk.
        Recovery: Status marked as CORRUPTED_MISSING_FILES.
        """
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        missing_path = store.installed_root / "vendor_lion" / "1.0.0"

        ver_rec = InstalledVersionRecord(
            version="1.0.0",
            install_path=str(missing_path),
            package_hash="hash",
            installed_at="2026-10-25T10:00:00Z",
            entry_point="lion.adapter:LionAdapter",
            publisher={},
            status=InstalledPluginStatus.INSTALLED,
        )
        store.record_installed_version("vendor_lion", "com.omnix.vendor.lion", "Lion", ver_rec)

        messages = store.reconcile_on_startup()
        assert any("Flagged missing installation directory" in m for m in messages)

        idx = store.load_index()
        assert idx["vendor_lion"].installed_versions["1.0.0"].status == InstalledPluginStatus.CORRUPTED_MISSING_FILES


# ===========================================================================
# 4. Test Suite: PluginInstaller
# ===========================================================================

class TestPluginInstaller:
    """Validates complete end-to-end installation transactions, AST checks, and immutability."""

    def test_install_signed_production_package_success(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_1.0.0.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(
            prod_trust_store=temp_environment["prod_store"],
            dev_trust_store=temp_environment["dev_store"],
            env="production",
        )
        installer = PluginInstaller(store=store, trust_engine=engine)

        result = installer.install_package(archive_path)
        assert result.success is True
        assert result.status == "SUCCESS"
        assert result.vendor_id == "vendor_lion"
        assert result.version == "1.0.0"
        assert result.install_path is not None
        assert Path(result.install_path).is_dir()
        assert (Path(result.install_path) / "manifest.json").is_file()
        assert (Path(result.install_path) / "lion" / "adapter.py").is_file()

        # Check durable store index
        plugin_rec = store.get_plugin("vendor_lion")
        assert plugin_rec is not None
        assert "1.0.0" in plugin_rec.installed_versions
        assert plugin_rec.installed_versions["1.0.0"].status == InstalledPluginStatus.INSTALLED

        # Check staging cleanup
        assert len(list(store.staging_root.iterdir())) == 0

    def test_install_idempotent_reinstall_same_hash(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_1.0.0.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)

        # First install
        res1 = installer.install_package(archive_path)
        assert res1.success is True

        # Second install with same archive
        res2 = installer.install_package(archive_path)
        assert res2.success is True
        assert res2.status == "ALREADY_INSTALLED"

    def test_install_version_immutable_conflict(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id, version="1.0.0")
        archive_path1 = temp_environment["root"] / "lion_1.0.0.xpl"
        build_test_xpl(archive_path1, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)

        # Install version 1.0.0
        res1 = installer.install_package(archive_path1)
        assert res1.success is True

        # Create different package with same version 1.0.0
        archive_path2 = temp_environment["root"] / "lion_1.0.0_modified.xpl"
        build_test_xpl(
            archive_path2,
            manifest_dict=manifest,
            private_key=priv,
            extra_files={"extra.txt": "different payload content"},
        )

        res2 = installer.install_package(archive_path2)
        assert res2.success is False
        assert res2.status == "VERSION_IMMUTABLE_CONFLICT"

    def test_install_rejection_ast_syntax_error(self, temp_environment, keypair):
        """
        Stage 7 AST static check: syntax error in Python module is detected
        before directory promotion, preventing deployment of unparseable code.
        """
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        broken_code = "def syntax_error(\n    missing_parenthesis\n"
        archive_path = temp_environment["root"] / "lion_broken.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, adapter_code=broken_code, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)

        result = installer.install_package(archive_path)
        assert result.success is False
        assert result.status == "INSTALLATION_FAILED"
        assert any("Syntax error" in e for e in result.errors)
        # Ensure target dir was NOT promoted
        assert not (store.installed_root / "vendor_lion" / "1.0.0").exists()

    def test_install_rejection_ast_missing_adapter_class(self, temp_environment, keypair):
        """
        Stage 7 AST check: entry_point class LionAdapter is not defined in adapter.py.
        """
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id, entry_point="lion.adapter:LionAdapter")
        code_without_lion_adapter = "class WrongNameAdapter:\n    pass\n"
        archive_path = temp_environment["root"] / "lion_wrong_class.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, adapter_code=code_without_lion_adapter, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)

        result = installer.install_package(archive_path)
        assert result.success is False
        assert result.status == "INSTALLATION_FAILED"
        assert any("not defined in module" in e for e in result.errors)
        assert not (store.installed_root / "vendor_lion" / "1.0.0").exists()


# ===========================================================================
# 5. Test Suite: PluginLoader & Runtime Isolation
# ===========================================================================

class TestPluginLoader:
    """Validates dynamic import, synthetic namespaces, relative imports, and contract reflection."""

    def test_load_adapter_success_and_synthetic_namespace(self, temp_environment, keypair):
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_1.0.0.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        installer.install_package(archive_path)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        assert load_res.success is True
        assert load_res.status == "SUCCESS"
        assert load_res.adapter_class is not None
        assert issubclass(load_res.adapter_class, IVendorAdapter)

        # Validate synthetic namespace isolation
        assert "omnix_plugins.pkg_vendor_lion_v1_0_0" in sys.modules
        assert load_res.synthetic_namespace == "omnix_plugins.pkg_vendor_lion_v1_0_0.adapter"

    def test_load_adapter_resolves_package_relative_imports(self, temp_environment, keypair):
        """
        Verifies that `from .selectors import LION_SELECTORS` inside `lion/adapter.py`
        resolves properly without throwing ModuleNotFoundError or modifying sys.path.
        """
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_rel_import.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        installer.install_package(archive_path)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")
        assert load_res.success is True

        # Instantiate and test method relying on relative import
        adapter_inst = load_res.adapter_class()
        cart_res = adapter_inst.add_to_cart("LM317", 1)
        assert cart_res["success"] is True
        assert cart_res["selector"] == "#cart-btn"

    def test_load_adapter_zero_sys_path_modification(self, temp_environment, keypair):
        """Invariant: Plugin loading must NEVER mutate sys.path."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_syspath.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        installer.install_package(archive_path)

        sys_path_before = list(sys.path)

        loader = PluginLoader(store=store)
        loader.load_adapter("vendor_lion", "1.0.0")

        sys_path_after = list(sys.path)
        assert sys_path_before == sys_path_after, "CRITICAL: sys.path was modified during plugin loading!"

    def test_load_adapter_rejection_not_subclass_of_vendor_interface(self, temp_environment, keypair):
        """Adapter class does not inherit IVendorAdapter -> LOAD_FAILED."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        non_subclass_code = """
class LionAdapter:
    def initialize(self): pass
    def search_part(self): pass
    def resolve_product(self): pass
    def inspect_product(self): pass
    def add_to_cart(self): pass
    def close(self): pass
"""
        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_not_subclass.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, adapter_code=non_subclass_code, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        installer.install_package(archive_path)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")
        assert load_res.success is False
        assert load_res.status == "LOAD_FAILED"
        assert "does not inherit from IVendorAdapter" in load_res.error_message

    def test_load_adapter_rejection_missing_mandatory_operations(self, temp_environment, keypair):
        """Adapter inherits IVendorAdapter but deletes/omits one mandatory method -> LOAD_FAILED."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        incomplete_adapter_code = """
from core.vendor_interface import IVendorAdapter
class LionAdapter(IVendorAdapter):
    # Missing add_to_cart method
    @property
    def vendor_id(self): return "vendor_lion"
    @property
    def base_url(self): return "https://lion.ir"
    def initialize(self, config=None): return None
    def search_part(self, query): return None
    def resolve_product(self, url_or_sku): return None
    def inspect_product(self, product_ref): return None
    def extract_product_data(self, dom_context): return None
    def inspect_stock(self, product_ref): return None
    def determine_order_constraints(self, product_ref): return None
    def inspect_cart(self): return None
    def authenticate(self, credentials=None, challenge_handler=None): return None
    def validate_session(self): return None
    def recover_from_error(self, error_context): return None
    def close(self): pass
"""
        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_missing_op.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, adapter_code=incomplete_adapter_code, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        installer.install_package(archive_path)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")
        assert load_res.success is False
        assert load_res.status == "LOAD_FAILED"
        assert "does not implement mandatory IVendorAdapter operations" in load_res.error_message
        assert "add_to_cart" in load_res.error_message

    def test_load_adapter_unindexed_vendor_rejected(self, temp_environment):
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("nonexistent_vendor")
        assert load_res.success is False
        assert load_res.status == "UNINDEXED_PLUGIN"


# ===========================================================================
# 6. Test Suite: Remediation - Crash Recovery Integrity (Fix A)
# ===========================================================================

class TestCrashRecoveryRemediation:
    """Validates Fix A: Strict verification of interrupted promotions before index reconciliation."""

    def test_recovery_promotion_started_with_missing_adapter_rejected(self, temp_environment, keypair):
        """Incomplete promotion with manifest.json but missing adapter file must NEVER be registered as installed."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crash_missing_adapter"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        # Simulate incomplete destination: only manifest.json exists
        target_dir.mkdir(parents=True)
        manifest_data = make_manifest(key_id=key_id)
        (target_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash_123",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest_data,
            file_digests={"manifest.json": "abc", "lion/adapter.py": "def"},
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()

        # Incomplete directory must not be registered as installed
        assert store.load_index() == {}, "Incomplete promotion was registered as installed!"
        assert not target_dir.exists(), "Incomplete promotion directory was not quarantined"
        assert any("Quarantining incomplete promotion" in m for m in messages)

    def test_recovery_promotion_started_with_modified_file_fails_digest(self, temp_environment, keypair):
        """Destination directory with modified file must fail digest check and be quarantined."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crash_corrupt_file"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        manifest_data = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "valid.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest_data, private_key=priv)

        # Unpack archive into target_dir
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)

        # Tamper with adapter.py in target_dir
        (target_dir / "lion" / "adapter.py").write_text("# Corrupted content", encoding="utf-8")

        # Create inspector digests
        inspector = PackageInspector()
        insp_res = inspector.inspect_file(archive_path)

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash=insp_res.package_hash,
            archive_path=archive_path,
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest_data,
            file_digests=insp_res.file_digests,
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()

        assert store.load_index() == {}, "Corrupted promotion was registered as installed!"
        assert not target_dir.exists()
        assert any("Quarantining incomplete promotion" in m for m in messages)

    def test_recovery_promotion_started_complete_destination_succeeds(self, temp_environment, keypair):
        """Complete matching destination after successful move but before journal advance is reconciled safely."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crash_complete_rename"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        manifest_data = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "valid.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest_data, private_key=priv)

        # Unpack archive completely into target_dir (simulating rename succeeded)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)

        inspector = PackageInspector()
        insp_res = inspector.inspect_file(archive_path)

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash=insp_res.package_hash,
            archive_path=archive_path,
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest_data,
            file_digests=insp_res.file_digests,
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()

        # Complete destination must be reconciled
        idx = store.load_index()
        assert "vendor_lion" in idx
        assert "1.0.0" in idx["vendor_lion"].installed_versions
        assert idx["vendor_lion"].installed_versions["1.0.0"].status == InstalledPluginStatus.INSTALLED
        assert not staging_dir.exists()
        assert any("Reconciling verified promoted version" in m for m in messages)

    def test_recovery_preserves_staging_payload_on_incomplete_promotion(self, temp_environment, keypair):
        """Remaining staging payload must NOT be silently deleted when recovery detects incomplete promotion."""
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crash_partial_move"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        # Destination has only manifest.json
        target_dir.mkdir(parents=True)
        manifest_data = make_manifest()
        (target_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        # Staging still has payload folder with remaining files
        payload_dir = staging_dir / "payload"
        payload_dir.mkdir(parents=True)
        (payload_dir / "remaining_adapter.py").write_text("# Remaining unpromoted code", encoding="utf-8")

        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash_123",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest_data,
            file_digests={"manifest.json": "abc", "lion/adapter.py": "def"},
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()

        assert any("Preserving staging payload for interrupted transaction" in m for m in messages)
        # Check that quarantine contains the preserved staging payload
        quarantine_entries = list(store.quarantine_root.iterdir())
        preserved_found = any("Preserved staging payload" in (q / ".quarantine_reason.txt").read_text(encoding="utf-8", errors="ignore") for q in quarantine_entries if (q / ".quarantine_reason.txt").is_file())
        assert preserved_found, "Remaining staging payload was not preserved in quarantine!"

    def test_recovery_unrelated_preexisting_destination_untouched(self, temp_environment):
        """Unrelated pre-existing destination belonging to another installation must remain untouched."""
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        tx_id = "tx_crash_ambiguous_ownership"
        staging_dir = store.staging_root / tx_id
        target_dir = store.installed_root / "vendor_lion" / "1.0.0"

        # Pre-existing destination with DIFFERENT vendor/plugin identity
        target_dir.mkdir(parents=True)
        unrelated_manifest = {"vendor_id": "vendor_unrelated", "plugin_id": "com.other.plugin", "version": "1.0.0"}
        (target_dir / "manifest.json").write_text(json.dumps(unrelated_manifest), encoding="utf-8")
        (target_dir / "important_data.txt").write_text("pre-existing user files", encoding="utf-8")

        staging_dir.mkdir(parents=True)
        journal = store.create_journal(
            tx_id=tx_id,
            vendor_id="vendor_lion",
            plugin_id="com.omnix.vendor.lion",
            version="1.0.0",
            package_hash="hash_123",
            archive_path=temp_environment["root"] / "dummy.xpl",
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=make_manifest(),
        )
        store.advance_journal(journal, TransactionState.PROMOTION_STARTED)

        messages = store.reconcile_on_startup()

        # Unrelated destination must be strictly preserved untouched
        assert target_dir.is_dir(), "Pre-existing destination was deleted or moved!"
        assert (target_dir / "important_data.txt").read_text(encoding="utf-8") == "pre-existing user files"
        assert any("Recovery halted" in m for m in messages)
        assert any("Data preserved without modification" in m for m in messages)

    def test_recovery_repeated_execution_is_idempotent(self, temp_environment):
        """Running recovery repeatedly must produce identical state and 0 second-pass mutations."""
        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        (store.staging_root / "stray_dir").mkdir()

        pass1_msgs = store.reconcile_on_startup()
        assert len(pass1_msgs) > 0

        pass2_msgs = store.reconcile_on_startup()
        assert len(pass2_msgs) == 0, "Second recovery pass made redundant mutations!"


# ===========================================================================
# 7. Test Suite: Remediation - Loader Tampering Rejection (Fix B)
# ===========================================================================

class TestLoaderTamperingRemediation:
    """Validates Fix B: Loader verifies authenticated digests before importing or executing any code."""

    def test_loader_rejects_modified_entry_point_before_execution(self, temp_environment, keypair):
        """Modifying entry-point file causes load failure before executing any tampered code."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_pkg.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)
        assert install_res.success is True

        # Setup sentinel file
        sentinel_file = temp_environment["root"] / "MALICIOUS_LOAD_TRIGGERED.txt"
        assert not sentinel_file.exists()

        # Tamper with installed entry point adapter.py
        adapter_path = Path(install_res.install_path) / "lion" / "adapter.py"
        malicious_content = f"""
from core.vendor_interface import IVendorAdapter
with open(r"{sentinel_file}", "w") as f:
    f.write("Tampered code executed!")

class LionAdapter(IVendorAdapter):
    pass
"""
        adapter_path.write_text(malicious_content, encoding="utf-8")

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        # Must reject as TAMPERED_FILES_DETECTED
        assert load_res.success is False
        assert load_res.status == "TAMPERED_FILES_DETECTED"
        assert "Digest mismatch for installed file" in load_res.error_message

        # INVARIANT: Sentinel file must NOT exist (proves module was NEVER executed)
        assert not sentinel_file.exists(), "CRITICAL: Tampered code was executed during load!"

        # Durable index must accurately reflect TAMPERED_FILES_DETECTED
        plugin_rec = store.get_plugin("vendor_lion")
        assert plugin_rec.installed_versions["1.0.0"].status == InstalledPluginStatus.TAMPERED_FILES_DETECTED

    def test_loader_rejects_modified_sibling_module_before_execution(self, temp_environment, keypair):
        """Modifying a non-entry-point sibling module causes load failure before any code executes."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_sibling.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)
        assert install_res.success is True

        sentinel_file = temp_environment["root"] / "SIBLING_SENTINEL.txt"

        # Tamper with sibling module selectors.py
        selectors_path = Path(install_res.install_path) / "lion" / "selectors.py"
        selectors_path.write_text(f"""
with open(r"{sentinel_file}", "w") as f:
    f.write("Sibling executed!")
LION_SELECTORS = {{}}
""", encoding="utf-8")

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        assert load_res.success is False
        assert load_res.status == "TAMPERED_FILES_DETECTED"
        assert not sentinel_file.exists(), "CRITICAL: Sibling module was executed despite digest tampering!"

    def test_loader_rejects_deleted_required_file(self, temp_environment, keypair):
        """Deleting an installed file is accurately flagged as CORRUPTED_MISSING_FILES before import."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_del.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)
        assert install_res.success is True

        # Delete sibling file selectors.py
        selectors_path = Path(install_res.install_path) / "lion" / "selectors.py"
        selectors_path.unlink()

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        assert load_res.success is False
        assert load_res.status == "CORRUPTED_MISSING_FILES"
        assert "is missing from disk" in load_res.error_message

        # Durable index must be updated with CORRUPTED_MISSING_FILES
        plugin_rec = store.get_plugin("vendor_lion")
        assert plugin_rec.installed_versions["1.0.0"].status == InstalledPluginStatus.CORRUPTED_MISSING_FILES

    def test_loader_rejects_modified_on_disk_manifest(self, temp_environment, keypair):
        """Modifying on-disk manifest is rejected because digests originate from authenticated metadata."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_mf.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)

        # Tamper with on-disk manifest.json
        manifest_path = Path(install_res.install_path) / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            m_data = json.load(f)
        m_data["display_name"] = "Hacked Display Name"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(m_data, f)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        assert load_res.success is False
        assert load_res.status == "TAMPERED_FILES_DETECTED"

    def test_loader_succeeds_for_unmodified_package(self, temp_environment, keypair):
        """Valid, unmodified package passes all digest checks and loads successfully."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_clean.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)

        loader = PluginLoader(store=store)
        load_res = loader.load_adapter("vendor_lion", "1.0.0")

        assert load_res.success is True
        assert load_res.status == "SUCCESS"
        assert load_res.adapter_class is not None

    def test_loader_preserves_tampered_files_for_diagnosis(self, temp_environment, keypair):
        """Tampered files on disk are preserved for forensic diagnosis and not automatically deleted."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_preserve.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)

        adapter_path = Path(install_res.install_path) / "lion" / "adapter.py"
        adapter_path.write_text("# tampered forensic evidence", encoding="utf-8")

        loader = PluginLoader(store=store)
        loader.load_adapter("vendor_lion", "1.0.0")

        # File must still exist on disk for inspection
        assert adapter_path.is_file()
        assert adapter_path.read_text(encoding="utf-8") == "# tampered forensic evidence"

    def test_loader_zero_sys_path_tampering_on_failure(self, temp_environment, keypair):
        """sys.path must remain strictly unchanged when loading fails due to tampering."""
        priv, pub = keypair
        key_id = "key_lion_prod"
        write_public_key_pem(temp_environment["prod_store"] / f"{key_id}.pub", pub)

        manifest = make_manifest(key_id=key_id)
        archive_path = temp_environment["root"] / "lion_syspath_tamper.xpl"
        build_test_xpl(archive_path, manifest_dict=manifest, private_key=priv)

        store = PluginStore(plugins_root=temp_environment["plugins_root"])
        engine = TrustEngine(prod_trust_store=temp_environment["prod_store"], env="production")
        installer = PluginInstaller(store=store, trust_engine=engine)
        install_res = installer.install_package(archive_path)

        # Alter file
        adapter_path = Path(install_res.install_path) / "lion" / "adapter.py"
        adapter_path.write_text("# bad", encoding="utf-8")

        sys_path_before = list(sys.path)

        loader = PluginLoader(store=store)
        loader.load_adapter("vendor_lion", "1.0.0")

        sys_path_after = list(sys.path)
        assert sys_path_before == sys_path_after, "sys.path was mutated during failed load attempt!"

