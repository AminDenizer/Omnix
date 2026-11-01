"""
Omnix Vendor Plugin System — Persistent Plugin Store & Transaction Journal (Milestone 1)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Manages:
1. Authoritative durable index: data/plugins/installed_plugins.json
2. Atomic metadata persistence using same-directory temporary file replacement and fsync.
3. Durable per-transaction journaling in data/plugins/.staging/<tx_id>/journal.json.
4. Fail-closed, idempotent boot-time recovery protocol:
   - Journal inspection and reconciliation BEFORE staging cleanup.
   - Resuming completed promotions that crashed before JSON persistence.
   - Quarantining interrupted, partial, or unindexed directories to data/plugins/.quarantine/.
   - Marking missing or corrupted installations as CORRUPTED_MISSING_FILES.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class TransactionState(str, Enum):
    """Deterministic states of an installation transaction."""
    TX_CREATED = "TX_CREATED"
    EXTRACTION_VERIFIED = "EXTRACTION_VERIFIED"
    TRUST_VERIFIED = "TRUST_VERIFIED"
    CONTRACT_CHECKED = "CONTRACT_CHECKED"
    PROMOTION_STARTED = "PROMOTION_STARTED"
    PROMOTION_COMPLETED = "PROMOTION_COMPLETED"
    PERSISTENCE_COMPLETED = "PERSISTENCE_COMPLETED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


class InstalledPluginStatus(str, Enum):
    """Lifecycle status of an installed plugin record."""
    INSTALLED = "INSTALLED"
    DISABLED = "DISABLED"
    LOAD_FAILED = "LOAD_FAILED"
    CORRUPTED_MISSING_FILES = "CORRUPTED_MISSING_FILES"
    TAMPERED_FILES_DETECTED = "TAMPERED_FILES_DETECTED"
    QUARANTINED = "QUARANTINED"


@dataclass
class TransactionJournal:
    """In-flight record tracking a cross-resource installation transaction."""
    tx_id: str
    state: TransactionState
    vendor_id: str
    plugin_id: str
    version: str
    package_hash: str
    archive_path: str
    staging_dir: str
    target_dir: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_message: Optional[str] = None
    manifest_metadata: Optional[Dict[str, Any]] = None
    file_digests: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TransactionJournal:
        state_str = data.get("state", TransactionState.TX_CREATED.value)
        try:
            state = TransactionState(state_str)
        except ValueError:
            state = TransactionState.ABORTED

        return cls(
            tx_id=data["tx_id"],
            state=state,
            vendor_id=data["vendor_id"],
            plugin_id=data["plugin_id"],
            version=data["version"],
            package_hash=data["package_hash"],
            archive_path=data["archive_path"],
            staging_dir=data["staging_dir"],
            target_dir=data["target_dir"],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            error_message=data.get("error_message"),
            manifest_metadata=data.get("manifest_metadata"),
            file_digests=data.get("file_digests"),
        )


@dataclass
class InstalledVersionRecord:
    """Metadata for an immutable installed plugin version."""
    version: str
    install_path: str
    package_hash: str
    installed_at: str
    entry_point: str
    publisher: Dict[str, Any]
    status: InstalledPluginStatus = InstalledPluginStatus.INSTALLED
    manifest: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    file_digests: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InstalledVersionRecord:
        status_str = data.get("status", InstalledPluginStatus.INSTALLED.value)
        try:
            status = InstalledPluginStatus(status_str)
        except ValueError:
            status = InstalledPluginStatus.LOAD_FAILED

        return cls(
            version=data["version"],
            install_path=data["install_path"],
            package_hash=data["package_hash"],
            installed_at=data.get("installed_at", datetime.now(timezone.utc).isoformat()),
            entry_point=data.get("entry_point", ""),
            publisher=data.get("publisher", {}),
            status=status,
            manifest=data.get("manifest"),
            error_message=data.get("error_message"),
            file_digests=data.get("file_digests"),
        )


@dataclass
class InstalledPluginRecord:
    """Registry record for a vendor plugin family supporting multi-version indexing."""
    vendor_id: str
    plugin_id: str
    display_name: str
    active_version: Optional[str] = None
    enabled: bool = False
    installed_versions: Dict[str, InstalledVersionRecord] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "plugin_id": self.plugin_id,
            "display_name": self.display_name,
            "active_version": self.active_version,
            "enabled": self.enabled,
            "installed_versions": {v: rec.to_dict() for v, rec in self.installed_versions.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InstalledPluginRecord:
        raw_versions = data.get("installed_versions", {})
        versions = {}
        for ver_str, ver_data in raw_versions.items():
            if isinstance(ver_data, dict):
                versions[ver_str] = InstalledVersionRecord.from_dict(ver_data)

        return cls(
            vendor_id=data["vendor_id"],
            plugin_id=data["plugin_id"],
            display_name=data.get("display_name", data["vendor_id"]),
            active_version=data.get("active_version"),
            enabled=data.get("enabled", False),
            installed_versions=versions,
        )


class PluginStore:
    """
    Authoritative persistent store managing the installed plugins index,
    transaction journals, atomic promotions, and crash-recovery protocols.
    """

    INDEX_FILENAME = "installed_plugins.json"
    INDEX_SCHEMA_VERSION = "1.0.0"

    def __init__(self, plugins_root: Optional[Union[str, Path]] = None):
        if plugins_root:
            self.plugins_root = Path(plugins_root).resolve()
        else:
            try:
                from config import get_app_dir
                base_dir = Path(get_app_dir()).resolve()
            except Exception:
                base_dir = Path(__file__).resolve().parent.parent.parent
            self.plugins_root = (base_dir / "data" / "plugins").resolve()

        self.staging_root = self.plugins_root / ".staging"
        self.installed_root = self.plugins_root / "installed"
        self.quarantine_root = self.plugins_root / ".quarantine"
        self.index_path = self.plugins_root / self.INDEX_FILENAME

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create base directory hierarchy if not existing."""
        self.plugins_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.installed_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Durable Installed-Plugin Index Access
    # -----------------------------------------------------------------------

    def load_index(self) -> Dict[str, InstalledPluginRecord]:
        """
        Load and parse installed_plugins.json.
        Returns mapping of vendor_id -> InstalledPluginRecord.
        If file does not exist, returns empty dict.
        """
        if not self.index_path.is_file():
            return {}

        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return {}

            raw_plugins = data.get("plugins", {})
            result: Dict[str, InstalledPluginRecord] = {}
            for vid, p_data in raw_plugins.items():
                if isinstance(p_data, dict) and "vendor_id" in p_data and "plugin_id" in p_data:
                    result[vid] = InstalledPluginRecord.from_dict(p_data)
            return result
        except Exception:
            # Corrupted index: return empty in-memory view to avoid crashing, but preserve file
            return {}

    def save_index(self, plugins: Dict[str, InstalledPluginRecord]) -> None:
        """
        Atomically persist installed plugins index to installed_plugins.json.
        Writes to a temporary file in the same directory, fsyncs, and replaces destination.
        """
        payload = {
            "schema_version": self.INDEX_SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "plugins": {vid: rec.to_dict() for vid, rec in plugins.items()},
        }

        # Write to temporary file in same filesystem for atomic rename
        temp_path = self.plugins_root / f"{self.INDEX_FILENAME}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename / replace
            temp_path.replace(self.index_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def get_plugin(self, vendor_id: str) -> Optional[InstalledPluginRecord]:
        """Get record for vendor_id, or None."""
        idx = self.load_index()
        return idx.get(vendor_id)

    def has_version(self, vendor_id: str, version: str) -> bool:
        """Check if specific version of vendor is installed."""
        p = self.get_plugin(vendor_id)
        return p is not None and version in p.installed_versions

    def record_installed_version(
        self,
        vendor_id: str,
        plugin_id: str,
        display_name: str,
        version_record: InstalledVersionRecord,
        set_active: bool = True,
        enabled: bool = False,
    ) -> None:
        """
        Persist a newly installed version into the authoritative index.
        """
        idx = self.load_index()
        if vendor_id not in idx:
            idx[vendor_id] = InstalledPluginRecord(
                vendor_id=vendor_id,
                plugin_id=plugin_id,
                display_name=display_name,
                active_version=version_record.version if set_active else None,
                enabled=enabled,
                installed_versions={version_record.version: version_record},
            )
        else:
            rec = idx[vendor_id]
            rec.installed_versions[version_record.version] = version_record
            if set_active or rec.active_version is None:
                rec.active_version = version_record.version
            if enabled:
                rec.enabled = True

        self.save_index(idx)

    def set_active_version(self, vendor_id: str, version: str) -> bool:
        """Set the active version for an installed vendor plugin."""
        idx = self.load_index()
        if vendor_id not in idx:
            return False
        rec = idx[vendor_id]
        if version not in rec.installed_versions:
            return False
        rec.active_version = version
        self.save_index(idx)
        return True

    def set_plugin_enabled(self, vendor_id: str, enabled: bool) -> bool:
        """Set the enabled flag for an installed vendor plugin."""
        idx = self.load_index()
        if vendor_id not in idx:
            return False
        rec = idx[vendor_id]
        rec.enabled = bool(enabled)
        self.save_index(idx)
        return True

    def remove_installed_version(self, vendor_id: str, version: str) -> bool:
        """Remove a specific installed version from the index."""
        idx = self.load_index()
        if vendor_id not in idx:
            return False
        rec = idx[vendor_id]
        if version not in rec.installed_versions:
            return False
        del rec.installed_versions[version]
        if rec.active_version == version:
            rec.active_version = None
            rec.enabled = False
        if len(rec.installed_versions) == 0:
            del idx[vendor_id]
        self.save_index(idx)
        return True

    def remove_plugin(self, vendor_id: str) -> bool:
        """Remove an entire plugin and all its versions from the index."""
        idx = self.load_index()
        if vendor_id not in idx:
            return False
        del idx[vendor_id]
        self.save_index(idx)
        return True

    # -----------------------------------------------------------------------
    # Transaction Journal Operations
    # -----------------------------------------------------------------------

    def create_journal(
        self,
        tx_id: str,
        vendor_id: str,
        plugin_id: str,
        version: str,
        package_hash: str,
        archive_path: Path,
        staging_dir: Path,
        target_dir: Path,
        manifest_metadata: Optional[Dict[str, Any]] = None,
        file_digests: Optional[Dict[str, str]] = None,
    ) -> TransactionJournal:
        """Create and persist an initial TX_CREATED journal for a new installation transaction."""
        journal = TransactionJournal(
            tx_id=tx_id,
            state=TransactionState.TX_CREATED,
            vendor_id=vendor_id,
            plugin_id=plugin_id,
            version=version,
            package_hash=package_hash,
            archive_path=str(archive_path.resolve()),
            staging_dir=str(staging_dir.resolve()),
            target_dir=str(target_dir.resolve()),
            manifest_metadata=manifest_metadata,
            file_digests=file_digests,
        )
        self.save_journal(journal)
        return journal

    def get_journal_path(self, staging_dir: Union[str, Path]) -> Path:
        """Get the journal.json path for a staging directory."""
        return Path(staging_dir) / "journal.json"

    def save_journal(self, journal: TransactionJournal) -> None:
        """Atomically persist transaction journal."""
        j_path = self.get_journal_path(journal.staging_dir)
        j_path.parent.mkdir(parents=True, exist_ok=True)
        journal.updated_at = datetime.now(timezone.utc).isoformat()

        temp_j = j_path.parent / f"journal.json.tmp.{int(time.time() * 1000)}"
        try:
            with open(temp_j, "w", encoding="utf-8") as f:
                json.dump(journal.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            temp_j.replace(j_path)
        except Exception:
            if temp_j.exists():
                try:
                    temp_j.unlink()
                except Exception:
                    pass
            raise

    def load_journal(self, staging_dir: Union[str, Path]) -> Optional[TransactionJournal]:
        """Load journal from staging directory, or None."""
        j_path = self.get_journal_path(staging_dir)
        if not j_path.is_file():
            return None
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TransactionJournal.from_dict(data)
        except Exception:
            return None

    def advance_journal(
        self,
        journal: TransactionJournal,
        new_state: TransactionState,
        error_message: Optional[str] = None,
    ) -> None:
        """Advance transaction journal state and persist durably before transition."""
        journal.state = new_state
        if error_message is not None:
            journal.error_message = error_message
        self.save_journal(journal)

    # -----------------------------------------------------------------------
    # Quarantine & Cleanup Utilities
    # -----------------------------------------------------------------------

    def quarantine_directory(self, target_path: Path, reason: str) -> Path:
        """
        Move an unindexed, ambiguous, or damaged directory into .quarantine/ with timestamp.
        Never permanently deletes user data.
        """
        if not target_path.exists():
            return self.quarantine_root

        ts = int(time.time())
        quarantine_dest = self.quarantine_root / f"{ts}_{target_path.name}"
        try:
            shutil.move(str(target_path), str(quarantine_dest))
            # Record reason
            with open(quarantine_dest / ".quarantine_reason.txt", "w", encoding="utf-8") as f:
                f.write(f"Quarantined at: {datetime.now(timezone.utc).isoformat()}\nReason: {reason}\nOriginal path: {target_path}\n")
        except Exception:
            pass
        return quarantine_dest

    def _verify_promoted_destination(
        self,
        target_dir: Path,
        journal: TransactionJournal,
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Verify that an interrupted or promoted destination directory belongs to this
        transaction and satisfies complete authenticated file presence and digests.

        Returns:
            Tuple of (is_valid, error_reason, is_owned)
            - is_valid: True only if all files exist and all digests match.
            - error_reason: Detailed failure message if not valid.
            - is_owned: True if the directory belongs to this transaction;
                        False if ownership is ambiguous or belongs to an unrelated installation.
        """
        if not target_dir.is_dir():
            return False, f"Destination directory '{target_dir}' does not exist on disk", False

        manifest_file = target_dir / "manifest.json"
        if not manifest_file.is_file():
            # target_dir exists, but manifest.json is missing: incomplete promotion
            return False, "Destination is missing manifest.json", True

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                disk_manifest = json.load(f)
        except Exception as exc:
            return False, f"Destination manifest.json is corrupt or unreadable: {exc}", True

        if not isinstance(disk_manifest, dict):
            return False, "Destination manifest.json is not a valid JSON object", True

        disk_vendor = disk_manifest.get("vendor_id")
        disk_plugin = disk_manifest.get("plugin_id")
        disk_version = disk_manifest.get("version")

        # Identity check: If the directory has manifest metadata for a DIFFERENT vendor,
        # plugin, or version, this directory is NOT owned by this transaction!
        # Ambiguous ownership / pre-existing unrelated destination.
        if (
            disk_vendor != journal.vendor_id
            or disk_plugin != journal.plugin_id
            or disk_version != journal.version
        ):
            return (
                False,
                f"Destination identity mismatch: expected {journal.vendor_id}/{journal.plugin_id} v{journal.version}, "
                f"found {disk_vendor}/{disk_plugin} v{disk_version}",
                False,  # is_owned = False: must NOT overwrite or quarantine!
            )

        # Ownership established
        is_owned = True

        # Verify entry point format and presence
        entry_point = disk_manifest.get("entry_point", "")
        if not entry_point or ":" not in entry_point:
            return False, f"Invalid entry_point declaration in destination manifest: '{entry_point}'", is_owned

        mod_path_str = entry_point.split(":")[0].strip()
        rel_as_path = Path(*mod_path_str.split("."))
        candidate_file = target_dir / f"{rel_as_path}.py"
        candidate_pkg = target_dir / rel_as_path / "__init__.py"
        inner_parts = mod_path_str.split(".")[1:]
        inner_candidate = target_dir / Path(*inner_parts).with_suffix(".py") if inner_parts else None

        if not (candidate_file.is_file() or candidate_pkg.is_file() or (inner_candidate and inner_candidate.is_file())):
            return False, f"Entry-point file for '{entry_point}' is missing in destination", is_owned

        # Recalculate SHA-256 digests specified by the authenticated digest manifest
        expected_digests: Dict[str, str] = {}
        if journal.file_digests:
            expected_digests = journal.file_digests
        else:
            mf_path = target_dir / "META-INF" / "MANIFEST.MF"
            if not mf_path.is_file():
                return False, "Destination lacks META-INF/MANIFEST.MF and journal lacks file_digests", is_owned
            try:
                from core.plugins.manifest_mf import ManifestMF
                parsed_mf = ManifestMF.parse_file(mf_path)
                expected_digests = {rel: entry.digest for rel, entry in parsed_mf.entries.items()}
            except Exception as exc:
                return False, f"Failed to parse destination META-INF/MANIFEST.MF: {exc}", is_owned

        if not expected_digests:
            return False, "No expected file digests available to verify destination integrity", is_owned

        for rel_path, expected_hash in expected_digests.items():
            norm_rel = rel_path.replace("\\", "/")
            disk_file = target_dir / norm_rel
            if not disk_file.is_file():
                return False, f"Required file '{norm_rel}' is missing in destination", is_owned

            try:
                with open(disk_file, "rb") as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest().lower()
                if actual_hash != expected_hash.lower():
                    return (
                        False,
                        f"Digest mismatch for '{norm_rel}': expected {expected_hash.lower()}, got {actual_hash}",
                        is_owned,
                    )
            except Exception as exc:
                return False, f"Failed to read '{norm_rel}' for digest verification: {exc}", is_owned

        return True, None, is_owned

    # -----------------------------------------------------------------------
    # Startup Recovery & Reconciliation (Pre-Sweep)
    # -----------------------------------------------------------------------

    def reconcile_on_startup(self) -> List[str]:
        """
        Execute crash recovery on application boot BEFORE any staging cleanup.

        Order of operations:
        1. Inspect all existing in-flight journals under .staging/.
        2. If promotion completed but persistence crashed, reconcile index and commit.
        3. If promotion started but was interrupted, check target integrity; quarantine if corrupt.
        4. Clean up verified completed/abandoned staging folders.
        5. Reconcile installed/ directories against index: quarantine unindexed directories.
        6. Validate indexed installations: flag missing folders as CORRUPTED_MISSING_FILES.

        Returns:
            List of diagnostic recovery messages.
        """
        messages: List[str] = []

        # -------------------------------------------------------------------
        # Step 1: Scan and reconcile in-flight transaction journals
        # -------------------------------------------------------------------
        halted_targets: Set[str] = set()

        if self.staging_root.is_dir():
            for entry in list(self.staging_root.iterdir()):
                if not entry.is_dir():
                    continue

                journal = self.load_journal(entry)
                if journal is None:
                    # Staging directory without valid journal: quarantine
                    messages.append(f"Found orphaned staging folder without journal: '{entry.name}'")
                    self.quarantine_directory(entry, "Orphaned staging folder without journal on startup")
                    continue

                target_dir = Path(journal.target_dir)

                if journal.state in (TransactionState.COMMITTED, TransactionState.PERSISTENCE_COMPLETED):
                    # Clean up completed transaction staging
                    messages.append(f"Cleaning completed transaction staging: {journal.tx_id}")
                    try:
                        shutil.rmtree(entry)
                    except Exception:
                        pass

                elif journal.state == TransactionState.PROMOTION_COMPLETED:
                    # Promotion succeeded, but crashed before persistence or commit!
                    messages.append(
                        f"Reconciling interrupted persistence for promoted version {journal.vendor_id} v{journal.version}"
                    )
                    manifest = journal.manifest_metadata or {}
                    publisher = manifest.get("publisher", {})
                    display_name = manifest.get("display_name", journal.vendor_id)
                    entry_point = manifest.get("entry_point", "")

                    ver_record = InstalledVersionRecord(
                        version=journal.version,
                        install_path=str(target_dir),
                        package_hash=journal.package_hash,
                        installed_at=journal.updated_at,
                        entry_point=entry_point,
                        publisher=publisher,
                        status=InstalledPluginStatus.INSTALLED,
                        manifest=manifest,
                        file_digests=journal.file_digests,
                    )
                    self.record_installed_version(
                        vendor_id=journal.vendor_id,
                        plugin_id=journal.plugin_id,
                        display_name=display_name,
                        version_record=ver_record,
                        set_active=True,
                        enabled=False,
                    )
                    try:
                        shutil.rmtree(entry)
                    except Exception:
                        pass

                elif journal.state == TransactionState.PROMOTION_STARTED:
                    # Rename was started or finished, but journal was never advanced to PROMOTION_COMPLETED
                    is_valid, reason, is_owned = self._verify_promoted_destination(target_dir, journal)

                    if is_valid:
                        # Full integrity verified: rename completed before crash!
                        messages.append(
                            f"Reconciling verified promoted version {journal.vendor_id} v{journal.version}"
                        )
                        manifest = journal.manifest_metadata or {}
                        publisher = manifest.get("publisher", {})
                        display_name = manifest.get("display_name", journal.vendor_id)
                        entry_point = manifest.get("entry_point", "")

                        ver_record = InstalledVersionRecord(
                            version=journal.version,
                            install_path=str(target_dir),
                            package_hash=journal.package_hash,
                            installed_at=journal.updated_at,
                            entry_point=entry_point,
                            publisher=publisher,
                            status=InstalledPluginStatus.INSTALLED,
                            manifest=manifest,
                            file_digests=journal.file_digests,
                        )
                        self.record_installed_version(
                            vendor_id=journal.vendor_id,
                            plugin_id=journal.plugin_id,
                            display_name=display_name,
                            version_record=ver_record,
                            set_active=True,
                            enabled=False,
                        )
                        try:
                            shutil.rmtree(entry)
                        except Exception:
                            pass

                    elif is_owned:
                        # Promotion was incomplete or corrupted, but owned by this transaction
                        messages.append(
                            f"Quarantining incomplete promotion for {journal.vendor_id} v{journal.version}: {reason}"
                        )
                        if target_dir.is_dir():
                            self.quarantine_directory(
                                target_dir,
                                f"Incomplete promotion interrupted by crash: {reason}"
                            )

                        # Preserve remaining staging payload files; do not blindly delete staging directory!
                        payload_dir = entry / "payload"
                        if payload_dir.is_dir() and any(payload_dir.iterdir()):
                            messages.append(f"Preserving staging payload for interrupted transaction: {journal.tx_id}")
                            self.quarantine_directory(
                                entry,
                                f"Preserved staging payload from interrupted transaction {journal.tx_id}: {reason}"
                            )
                        else:
                            try:
                                shutil.rmtree(entry)
                            except Exception:
                                pass

                    else:
                        # Ownership is ambiguous or destination belongs to an unrelated installation!
                        # Never overwrite or quarantine a valid pre-existing destination belonging to another installation!
                        messages.append(
                            f"Recovery halted for transaction {journal.tx_id}: {reason}. Data preserved without modification."
                        )
                        diag_file = entry / ".recovery_halted_reason.txt"
                        try:
                            with open(diag_file, "w", encoding="utf-8") as f:
                                f.write(f"Recovery halted: {reason}\nTarget: {target_dir}\n")
                        except Exception:
                            pass
                        halted_targets.add(str(target_dir.resolve()))

                else:
                    # Pre-promotion state: promotion never happened, safe to remove staging
                    messages.append(
                        f"Cleaning unpromoted transaction staging ({journal.state.value}): {journal.tx_id}"
                    )
                    try:
                        shutil.rmtree(entry)
                    except Exception:
                        pass

        # -------------------------------------------------------------------
        # Step 2: Reconcile installed/ directories against index
        # -------------------------------------------------------------------
        index = self.load_index()
        indexed_paths: Set[str] = set()
        for p_rec in index.values():
            for v_rec in p_rec.installed_versions.values():
                indexed_paths.add(str(Path(v_rec.install_path).resolve()))

        if self.installed_root.is_dir():
            for vendor_dir in list(self.installed_root.iterdir()):
                if not vendor_dir.is_dir():
                    continue
                for version_dir in list(vendor_dir.iterdir()):
                    if not version_dir.is_dir():
                        continue
                    resolved_str = str(version_dir.resolve())
                    if resolved_str in halted_targets:
                        # Ambiguous ownership or halted transaction: preserved untouched
                        continue
                    if resolved_str not in indexed_paths:
                        messages.append(
                            f"Quarantining unindexed installation directory: '{version_dir.name}' under '{vendor_dir.name}'"
                        )
                        self.quarantine_directory(
                            version_dir,
                            f"Directory not indexed in {self.INDEX_FILENAME} on startup"
                        )

        # -------------------------------------------------------------------
        # Step 3: Check for missing/corrupted indexed folders
        # -------------------------------------------------------------------
        updated = False
        for p_rec in index.values():
            for v_rec in p_rec.installed_versions.values():
                inst_p = Path(v_rec.install_path)
                if not inst_p.is_dir() or not (inst_p / "manifest.json").is_file():
                    if v_rec.status != InstalledPluginStatus.CORRUPTED_MISSING_FILES:
                        v_rec.status = InstalledPluginStatus.CORRUPTED_MISSING_FILES
                        v_rec.error_message = f"Installation directory '{inst_p}' is missing or corrupted on disk."
                        updated = True
                        messages.append(f"Flagged missing installation directory: {inst_p}")

        if updated:
            self.save_index(index)

        return messages
