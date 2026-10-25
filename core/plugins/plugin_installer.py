"""
Omnix Vendor Plugin System — Plugin Installer (Milestone 1)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Implements deterministic, crash-safe, fail-closed installation transactions:
1. Stage 1: Offline archive inspection (limits, traversal, extension whitelist).
2. Stage 2: Manifest schema and semantic validation.
3. Stage 3: Per-file digest verification against META-INF/MANIFEST.MF.
4. Stage 4: Cryptographic Ed25519 signature & publisher trust verification.
   -> CRITICAL INVARIANT: Hard block on untrusted/unsigned packages BEFORE extraction.
5. Stage 5: Isolated staging in data/plugins/.staging/<tx_id>/payload/.
6. Stage 6: Post-extraction disk digest verification & entry-point file check.
7. Stage 7: Static AST pre-promotion contract inspection (zero code import).
8. Stage 8: Durable transaction journal writing.
9. Stage 9: Atomic directory promotion to data/plugins/installed/<vendor_id>/<version>/.
10. Stage 10: Atomic persistence to data/plugins/installed_plugins.json.
11. Stage 11: Transaction commit and staging cleanup.
"""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.plugins.manifest_validator import (
    ManifestValidationError,
    ManifestValidationResult,
    ManifestValidator,
)
from core.plugins.package_inspector import (
    PackageInspectionError,
    PackageInspectionResult,
    PackageInspectionStatus,
    PackageInspector,
    inspect_package,
)
from core.plugins.plugin_store import (
    InstalledPluginRecord,
    InstalledPluginStatus,
    InstalledVersionRecord,
    PluginStore,
    TransactionJournal,
    TransactionState,
)
from core.plugins.trust_engine import (
    TrustEngine,
    TrustStatus,
    TrustVerificationResult,
)


@dataclass
class PluginInstallationResult:
    """Outcome of an installation transaction."""
    success: bool
    status: str
    plugin_id: Optional[str] = None
    vendor_id: Optional[str] = None
    version: Optional[str] = None
    package_hash: Optional[str] = None
    install_path: Optional[str] = None
    error_message: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    trust_status: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class PluginInstaller:
    """
    Coordinates fail-closed, transaction-journaled plugin installations.
    """

    def __init__(
        self,
        store: Optional[PluginStore] = None,
        trust_engine: Optional[TrustEngine] = None,
        inspector: Optional[PackageInspector] = None,
    ):
        self.store = store or PluginStore()
        self.trust_engine = trust_engine or TrustEngine()
        self.inspector = inspector or PackageInspector()

    def install_package(self, archive_path: Union[str, Path]) -> PluginInstallationResult:
        """
        Execute full installation transaction on an .xpl package archive.

        Args:
            archive_path: Path to the .xpl package archive.

        Returns:
            PluginInstallationResult detailing outcome and errors.
        """
        path_obj = Path(archive_path).resolve()
        if not path_obj.is_file():
            return PluginInstallationResult(
                success=False,
                status="FILE_NOT_FOUND",
                error_message=f"Package file does not exist: '{path_obj}'",
                errors=[f"File not found: '{path_obj}'"],
            )

        # -------------------------------------------------------------------
        # Stage 1-3: Offline Archive Inspection, Manifest & Digest Integrity
        # -------------------------------------------------------------------
        inspect_res = self.inspector.inspect_file(path_obj)
        if not inspect_res.is_valid:
            err_msgs = [str(e) for e in inspect_res.errors]
            return PluginInstallationResult(
                success=False,
                status=inspect_res.status.value,
                plugin_id=inspect_res.plugin_id,
                vendor_id=inspect_res.vendor_id,
                version=inspect_res.version,
                package_hash=inspect_res.package_hash,
                error_message=f"Package inspection failed: {inspect_res.status.value}",
                errors=err_msgs,
                details={"errors": [asdict(e) if hasattr(e, "__dict__") else str(e) for e in inspect_res.errors]},
            )

        manifest = inspect_res.manifest_metadata or {}
        vendor_id = str(inspect_res.vendor_id)
        plugin_id = str(inspect_res.plugin_id)
        version = str(inspect_res.version)
        package_hash = inspect_res.package_hash
        display_name = manifest.get("display_name", vendor_id)
        entry_point = manifest.get("entry_point", "")
        publisher = manifest.get("publisher", {})
        key_id = publisher.get("key_id")
        publisher_name = publisher.get("name")

        # -------------------------------------------------------------------
        # Stage 4: Cryptographic Trust & Signature Verification
        # (CRITICAL INVARIANT: Must pass BEFORE extraction or import)
        # -------------------------------------------------------------------
        signature_bytes: Optional[bytes] = None
        manifest_mf_bytes: Optional[bytes] = None

        try:
            with zipfile.ZipFile(path_obj, "r") as zf:
                if "META-INF/SIGNATURE.sig" in zf.namelist():
                    signature_bytes = zf.read("META-INF/SIGNATURE.sig")
                if "META-INF/MANIFEST.MF" in zf.namelist():
                    manifest_mf_bytes = zf.read("META-INF/MANIFEST.MF")
        except Exception as exc:
            return PluginInstallationResult(
                success=False,
                status="ARCHIVE_READ_FAILED",
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                error_message=f"Failed to read archive signature members: {exc}",
                errors=[str(exc)],
            )

        if not manifest_mf_bytes:
            return PluginInstallationResult(
                success=False,
                status="MISSING_INTEGRITY_MANIFEST",
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                error_message="Missing canonical META-INF/MANIFEST.MF",
                errors=["Archive missing META-INF/MANIFEST.MF"],
            )

        trust_res = self.trust_engine.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=signature_bytes,
            key_id=key_id,
            publisher_name=publisher_name,
        )

        if not trust_res.is_trusted:
            return PluginInstallationResult(
                success=False,
                status=trust_res.status.value,
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                trust_status=trust_res.status.value,
                error_message=trust_res.error_message or "Publisher trust verification rejected",
                errors=[trust_res.error_message or "Untrusted package signature"],
                details=trust_res.details,
            )

        # -------------------------------------------------------------------
        # Stage 5 Preflight: Destination Collision Check
        # -------------------------------------------------------------------
        target_dir = (self.store.installed_root / vendor_id / version).resolve()
        if target_dir.is_dir():
            # Check if identical package is already installed
            existing_plugin = self.store.get_plugin(vendor_id)
            if existing_plugin and version in existing_plugin.installed_versions:
                existing_ver = existing_plugin.installed_versions[version]
                if existing_ver.package_hash == package_hash:
                    return PluginInstallationResult(
                        success=True,
                        status="ALREADY_INSTALLED",
                        plugin_id=plugin_id,
                        vendor_id=vendor_id,
                        version=version,
                        package_hash=package_hash,
                        install_path=str(target_dir),
                        trust_status=trust_res.status.value,
                        error_message=f"Plugin '{plugin_id}' v{version} is already installed with identical hash",
                    )

            # Different content with same SemVer: immutable version collision
            return PluginInstallationResult(
                success=False,
                status="VERSION_IMMUTABLE_CONFLICT",
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                error_message=(
                    f"Destination directory already exists for vendor '{vendor_id}' version '{version}'. "
                    "Cannot overwrite existing version; bump version number in manifest."
                ),
                errors=[f"Destination directory collision at '{target_dir}'"],
            )

        # -------------------------------------------------------------------
        # Stage 5: Staged Extraction (Isolated in .staging/<tx_id>/payload/)
        # -------------------------------------------------------------------
        tx_id = f"tx_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        staging_dir = self.store.staging_root / tx_id
        payload_dir = staging_dir / "payload"

        # Authenticated file digests from PackageInspector (validated against Ed25519 signature)
        all_digests = dict(inspect_res.file_digests)
        if manifest_mf_bytes:
            all_digests["META-INF/MANIFEST.MF"] = hashlib.sha256(manifest_mf_bytes).hexdigest().lower()

        journal = self.store.create_journal(
            tx_id=tx_id,
            vendor_id=vendor_id,
            plugin_id=plugin_id,
            version=version,
            package_hash=package_hash,
            archive_path=path_obj,
            staging_dir=staging_dir,
            target_dir=target_dir,
            manifest_metadata=manifest,
            file_digests=all_digests,
        )

        try:
            payload_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path_obj, "r") as zf:
                # Extract members safely
                for member in zf.infolist():
                    # Check Zip-slip normalization
                    norm_path = member.filename.replace("\\", "/")
                    dest_file = payload_dir / norm_path
                    # Ensure dest is strictly inside payload_dir
                    resolved_dest = dest_file.resolve()
                    if not str(resolved_dest).startswith(str(payload_dir.resolve())):
                        raise ValueError(f"Extracted member '{norm_path}' escapes staging payload boundary")

                    if member.is_dir() or norm_path.endswith("/"):
                        resolved_dest.mkdir(parents=True, exist_ok=True)
                    else:
                        resolved_dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member, "r") as src, open(resolved_dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            self.store.advance_journal(journal, TransactionState.EXTRACTION_VERIFIED)

            # ---------------------------------------------------------------
            # Stage 6: Post-Extraction Disk Verification
            # ---------------------------------------------------------------
            for rel_path, expected_digest in inspect_res.file_digests.items():
                disk_file = payload_dir / rel_path
                if not disk_file.is_file():
                    raise ValueError(f"Post-extraction verification missing expected file on disk: '{rel_path}'")

                with open(disk_file, "rb") as f:
                    actual_digest = hashlib.sha256(f.read()).hexdigest().lower()
                if actual_digest != expected_digest.lower():
                    raise ValueError(
                        f"Post-extraction digest mismatch for '{rel_path}': expected {expected_digest}, got {actual_digest}"
                    )

            # Verify entry point file exists
            entry_point_file = inspect_res.entry_point_file
            if not entry_point_file or not (payload_dir / entry_point_file).is_file():
                raise ValueError(f"Entry-point file '{entry_point_file}' is missing from extracted payload")

            self.store.advance_journal(journal, TransactionState.TRUST_VERIFIED)

            # ---------------------------------------------------------------
            # Stage 7: Static Pre-Promotion Contract Inspection (AST)
            # (Checks Python syntax and class presence without executing code)
            # ---------------------------------------------------------------
            full_entry_file = payload_dir / entry_point_file
            with open(full_entry_file, "r", encoding="utf-8", errors="replace") as f:
                source_text = f.read()

            try:
                tree = ast.parse(source_text, filename=str(entry_point_file))
            except SyntaxError as syn_err:
                raise ValueError(f"Syntax error in entry-point module '{entry_point_file}': {syn_err}") from syn_err

            # Verify class presence in AST
            target_class_name = entry_point.split(":")[-1].strip()
            class_found = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == target_class_name:
                    class_found = True
                    break

            if not class_found:
                raise ValueError(
                    f"Entry-point class '{target_class_name}' is not defined in module '{entry_point_file}'"
                )

            self.store.advance_journal(journal, TransactionState.CONTRACT_CHECKED)

            # ---------------------------------------------------------------
            # Stage 8: Atomic Promotion to Immutable Destination
            # ---------------------------------------------------------------
            self.store.advance_journal(journal, TransactionState.PROMOTION_STARTED)
            target_dir.parent.mkdir(parents=True, exist_ok=True)

            try:
                # Same-filesystem atomic rename / move
                payload_dir.replace(target_dir)
            except OSError:
                # Fallback to shutil.move if replace fails across specific mount configurations
                shutil.move(str(payload_dir), str(target_dir))

            self.store.advance_journal(journal, TransactionState.PROMOTION_COMPLETED)

            # ---------------------------------------------------------------
            # Stage 9: Persistent Installation State Index Update
            # ---------------------------------------------------------------
            ver_record = InstalledVersionRecord(
                version=version,
                install_path=str(target_dir),
                package_hash=package_hash,
                installed_at=journal.updated_at,
                entry_point=entry_point,
                publisher=publisher,
                status=InstalledPluginStatus.INSTALLED,
                manifest=manifest,
                file_digests=all_digests,
            )
            self.store.record_installed_version(
                vendor_id=vendor_id,
                plugin_id=plugin_id,
                display_name=display_name,
                version_record=ver_record,
                set_active=True,
                enabled=False,  # Plugins are disabled by default
            )
            self.store.advance_journal(journal, TransactionState.PERSISTENCE_COMPLETED)

            # ---------------------------------------------------------------
            # Stage 10: Commit & Cleanup Staging
            # ---------------------------------------------------------------
            self.store.advance_journal(journal, TransactionState.COMMITTED)
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass

            return PluginInstallationResult(
                success=True,
                status="SUCCESS",
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                install_path=str(target_dir),
                trust_status=trust_res.status.value,
                details={"publisher": publisher, "installed_at": ver_record.installed_at},
            )

        except Exception as exc:
            # Transaction failed: clean up staging and rollback
            error_msg = str(exc)
            try:
                self.store.advance_journal(journal, TransactionState.ABORTED, error_message=error_msg)
            except Exception:
                pass

            # If promotion was completed before failure, quarantine promoted dir
            if journal.state == TransactionState.PROMOTION_COMPLETED:
                if target_dir.is_dir():
                    self.store.quarantine_directory(target_dir, f"Aborted transaction after promotion: {error_msg}")

            # Clean staging
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass

            return PluginInstallationResult(
                success=False,
                status="INSTALLATION_FAILED",
                plugin_id=plugin_id,
                vendor_id=vendor_id,
                version=version,
                package_hash=package_hash,
                trust_status=trust_res.status.value if trust_res else None,
                error_message=f"Installation transaction failed: {error_msg}",
                errors=[error_msg],
            )
