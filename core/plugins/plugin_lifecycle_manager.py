"""
Omnix Vendor Plugin System — Plugin Lifecycle Manager (Milestone 2)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Connects persistent installed-plugin records (data/plugins/installed_plugins.json)
to runtime VendorRegistry (core/procurement/registry.py).

Responsibilities:
1. Dynamic Activation & Registration (Gate E):
   - Securely loads installed plugins through PluginLoader (verifying cryptographic digests,
     permanent paths, AST syntax, and IVendorAdapter contracts).
   - Atomically registers and activates adapters in VendorRegistry under lock.
   - Updates persistent store index (active_version, enabled=True).
2. Deactivation & Route Removal:
   - Deactivates vendor and purges storefront route mappings in VendorRegistry.
   - Updates persistent store index (enabled=False).
   - Preserves installed files on disk for instant re-activation.
3. Multi-Version Management:
   - Maintains single active version per vendor.
   - Supports atomic version switching without fallback or partial registry exposure.
4. Application Startup Recovery & Restoration:
   - Reconciles crash journals and unindexed directories via PluginStore.reconcile_on_startup().
   - Restores previously enabled plugins into VendorRegistry fail-closed.
   - Corrupted or tampered plugins are left disabled without crashing startup.
5. Deterministic Lifecycle Status & Safe Error Propagation:
   - Clear, non-leaking diagnostic error reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shutil
import threading
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING, Union

from core.logger import log_event, track_operation
from core.plugins.manifest_validator import SemanticVersion
from core.plugins.plugin_loader import PluginLoader, PluginLoadResult
from core.plugins.plugin_store import (
    InstalledPluginRecord,
    InstalledPluginStatus,
    InstalledVersionRecord,
    PluginStore,
)
from core.vendor_interface import IVendorAdapter

if TYPE_CHECKING:
    from core.procurement.registry import (
        PluginVersionRegistration,
        VendorRegistry,
    )


class LifecycleStatus(str, Enum):
    """Outcomes of plugin lifecycle operations."""
    SUCCESS = "SUCCESS"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    ALREADY_INACTIVE = "ALREADY_INACTIVE"
    NOT_INSTALLED = "NOT_INSTALLED"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    LOAD_FAILED = "LOAD_FAILED"
    REGISTRATION_FAILED = "REGISTRATION_FAILED"
    TAMPERED_FILES_DETECTED = "TAMPERED_FILES_DETECTED"
    CORRUPTED_MISSING_FILES = "CORRUPTED_MISSING_FILES"
    UNINDEXED_PLUGIN = "UNINDEXED_PLUGIN"
    UNINSTALL_FAILED = "UNINSTALL_FAILED"


@dataclass
class LifecycleResult:
    """Detailed outcome of a plugin lifecycle operation."""
    success: bool
    status: LifecycleStatus
    vendor_id: str
    version: Optional[str] = None
    error_message: Optional[str] = None
    registration: Optional[PluginVersionRegistration] = None
    details: Dict[str, Any] = field(default_factory=dict)


class PluginLifecycleManager:
    """
    Coordinates plugin installation records in PluginStore with runtime dispatch
    and domain routing in VendorRegistry.
    """

    def __init__(
        self,
        store: Optional[PluginStore] = None,
        loader: Optional[PluginLoader] = None,
        registry: Optional[VendorRegistry] = None,
    ):
        self._lock = threading.RLock()
        self.store = store or PluginStore()
        self.loader = loader or PluginLoader(store=self.store)
        if registry is not None:
            self.registry = registry
        else:
            from core.procurement.registry import default_registry
            self.registry = default_registry

    # -----------------------------------------------------------------------
    # Activation & Deactivation
    # -----------------------------------------------------------------------

    def activate_plugin(
        self,
        vendor_id: str,
        version: Optional[str] = None,
    ) -> LifecycleResult:
        """
        Activate an installed plugin version and register it into VendorRegistry.

        Executes Gate E under lock:
        1. Verifies that the plugin and target version exist in authoritative store index.
        2. Idempotently returns SUCCESS if the version is already active and enabled.
        3. Loads adapter class through PluginLoader, verifying file digests, paths, AST, and contracts.
        4. Atomically registers manifest and adapter in VendorRegistry, establishing storefront routes.
        5. Persists active_version and enabled=True in installed_plugins.json.

        Returns:
            LifecycleResult with status and registration details.
        """
        if not vendor_id or not isinstance(vendor_id, str) or not vendor_id.strip():
            return LifecycleResult(
                success=False,
                status=LifecycleStatus.NOT_INSTALLED,
                vendor_id=str(vendor_id),
                error_message="Invalid vendor_id provided",
            )

        clean_vid = vendor_id.strip()

        with self._lock:
            # Step 1: Query persistent store
            p_rec = self.store.get_plugin(clean_vid)
            if p_rec is None:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.NOT_INSTALLED,
                    vendor_id=clean_vid,
                    error_message=f"Vendor '{clean_vid}' is not recorded as installed in PluginStore",
                )

            # Determine target version
            target_ver = version or p_rec.active_version
            if not target_ver:
                if p_rec.installed_versions:
                    sorted_vers = sorted(p_rec.installed_versions.keys(), key=lambda v: SemanticVersion(v))
                    target_ver = sorted_vers[-1]
                else:
                    return LifecycleResult(
                        success=False,
                        status=LifecycleStatus.VERSION_NOT_FOUND,
                        vendor_id=clean_vid,
                        error_message=f"No installed versions found for vendor '{clean_vid}'",
                    )

            target_ver = target_ver.strip()
            if target_ver not in p_rec.installed_versions:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.VERSION_NOT_FOUND,
                    vendor_id=clean_vid,
                    version=target_ver,
                    error_message=f"Version '{target_ver}' is not installed for vendor '{clean_vid}'",
                )

            # Step 2: Idempotency check
            if (
                self.registry.has_vendor(clean_vid)
                and self.registry.get_active_version(clean_vid) == target_ver
                and self.registry.is_vendor_enabled(clean_vid)
                and p_rec.enabled
                and p_rec.active_version == target_ver
            ):
                reg = self.registry.get_version_registration(clean_vid, target_ver)
                return LifecycleResult(
                    success=True,
                    status=LifecycleStatus.ALREADY_ACTIVE,
                    vendor_id=clean_vid,
                    version=target_ver,
                    registration=reg,
                )

            # Step 3: Secure Dynamic Loading (pre-import digest checks & AST validation)
            load_res = self.loader.load_adapter(clean_vid, target_ver)
            if not load_res.success:
                status_map = {
                    "TAMPERED_FILES_DETECTED": LifecycleStatus.TAMPERED_FILES_DETECTED,
                    "CORRUPTED_MISSING_FILES": LifecycleStatus.CORRUPTED_MISSING_FILES,
                    "UNINDEXED_PLUGIN": LifecycleStatus.UNINDEXED_PLUGIN,
                    "VERSION_NOT_FOUND": LifecycleStatus.VERSION_NOT_FOUND,
                    "LOAD_FAILED": LifecycleStatus.LOAD_FAILED,
                }
                mapped_status = status_map.get(load_res.status, LifecycleStatus.LOAD_FAILED)

                # Fail-closed: ensure store reflects disabled status
                self.store.set_plugin_enabled(clean_vid, False)

                return LifecycleResult(
                    success=False,
                    status=mapped_status,
                    vendor_id=clean_vid,
                    version=target_ver,
                    error_message=load_res.error_message,
                )

            adapter_cls = load_res.adapter_class
            manifest_dict = load_res.manifest
            if adapter_cls is None or manifest_dict is None:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.LOAD_FAILED,
                    vendor_id=clean_vid,
                    version=target_ver,
                    error_message="Loader succeeded but returned empty adapter class or manifest",
                )

            # Step 4: Register / Activate in VendorRegistry
            try:
                if self.registry.has_vendor(clean_vid) and target_ver in self.registry.list_versions(clean_vid):
                    self.registry.activate_version(clean_vid, target_ver)
                    self.registry.set_vendor_enabled(clean_vid, True)
                    reg = self.registry.get_version_registration(clean_vid, target_ver)
                else:
                    reg = self.registry.register_plugin_manifest(
                        manifest=manifest_dict,
                        adapter_class=adapter_cls,
                        activate=True,
                        enabled=True,
                    )
            except Exception as exc:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.REGISTRATION_FAILED,
                    vendor_id=clean_vid,
                    version=target_ver,
                    error_message=f"Failed to register in VendorRegistry: {exc}",
                )

            # Step 5: Update persistent store index
            self.store.set_active_version(clean_vid, target_ver)
            self.store.set_plugin_enabled(clean_vid, True)

            log_event(
                domain="Plugins",
                event_type="PLUGIN_ACTIVATED",
                message=f"Activated plugin '{clean_vid}' v{target_ver}",
                level="INFO",
                details={"vendor_id": clean_vid, "version": target_ver},
            )

            return LifecycleResult(
                success=True,
                status=LifecycleStatus.SUCCESS,
                vendor_id=clean_vid,
                version=target_ver,
                registration=reg,
            )

    def deactivate_plugin(self, vendor_id: str) -> LifecycleResult:
        """
        Deactivate a vendor plugin, purging storefront route mappings from VendorRegistry.

        Installed files remain on disk. Updates persistent store index (enabled=False).
        """
        if not vendor_id or not isinstance(vendor_id, str) or not vendor_id.strip():
            return LifecycleResult(
                success=False,
                status=LifecycleStatus.NOT_INSTALLED,
                vendor_id=str(vendor_id),
                error_message="Invalid vendor_id provided",
            )

        clean_vid = vendor_id.strip()

        with self._lock:
            p_rec = self.store.get_plugin(clean_vid)
            if p_rec is None:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.NOT_INSTALLED,
                    vendor_id=clean_vid,
                    error_message=f"Vendor '{clean_vid}' is not recorded as installed in PluginStore",
                )

            # Idempotency check
            is_reg_active = (
                self.registry.has_vendor(clean_vid)
                and self.registry.get_active_version(clean_vid) is not None
                and self.registry.is_vendor_enabled(clean_vid)
            )
            if not p_rec.enabled and not is_reg_active:
                return LifecycleResult(
                    success=True,
                    status=LifecycleStatus.ALREADY_INACTIVE,
                    vendor_id=clean_vid,
                    version=p_rec.active_version,
                )

            # Deactivate in VendorRegistry
            if self.registry.has_vendor(clean_vid):
                self.registry.set_vendor_enabled(clean_vid, False)
                self.registry.deactivate_vendor(clean_vid)

            # Update persistent store
            self.store.set_plugin_enabled(clean_vid, False)

            log_event(
                domain="Plugins",
                event_type="PLUGIN_DEACTIVATED",
                message=f"Deactivated plugin '{clean_vid}'",
                level="INFO",
                details={"vendor_id": clean_vid},
            )

            return LifecycleResult(
                success=True,
                status=LifecycleStatus.SUCCESS,
                vendor_id=clean_vid,
                version=p_rec.active_version,
            )

    # -----------------------------------------------------------------------
    # Version Switching
    # -----------------------------------------------------------------------

    def switch_active_version(
        self,
        vendor_id: str,
        new_version: str,
    ) -> LifecycleResult:
        """
        Atomically switch the active version of an installed vendor plugin.

        Pre-verifies the target version through PluginLoader. If the target version fails
        verification, the existing active version remains untouched in VendorRegistry and store.
        """
        if not vendor_id or not new_version:
            return LifecycleResult(
                success=False,
                status=LifecycleStatus.NOT_INSTALLED,
                vendor_id=str(vendor_id),
                version=str(new_version),
                error_message="vendor_id and new_version must be provided",
            )

        clean_vid = vendor_id.strip()
        clean_ver = new_version.strip()

        with self._lock:
            p_rec = self.store.get_plugin(clean_vid)
            if p_rec is None:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.NOT_INSTALLED,
                    vendor_id=clean_vid,
                    error_message=f"Vendor '{clean_vid}' is not recorded as installed in PluginStore",
                )

            if clean_ver not in p_rec.installed_versions:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.VERSION_NOT_FOUND,
                    vendor_id=clean_vid,
                    version=clean_ver,
                    error_message=f"Version '{clean_ver}' is not installed for vendor '{clean_vid}'",
                )

            # Check if already active and enabled
            if (
                p_rec.active_version == clean_ver
                and p_rec.enabled
                and self.registry.has_vendor(clean_vid)
                and self.registry.get_active_version(clean_vid) == clean_ver
                and self.registry.is_vendor_enabled(clean_vid)
            ):
                reg = self.registry.get_version_registration(clean_vid, clean_ver)
                return LifecycleResult(
                    success=True,
                    status=LifecycleStatus.ALREADY_ACTIVE,
                    vendor_id=clean_vid,
                    version=clean_ver,
                    registration=reg,
                )

            # Securely verify and load the candidate new version first
            load_res = self.loader.load_adapter(clean_vid, clean_ver)
            if not load_res.success:
                status_map = {
                    "TAMPERED_FILES_DETECTED": LifecycleStatus.TAMPERED_FILES_DETECTED,
                    "CORRUPTED_MISSING_FILES": LifecycleStatus.CORRUPTED_MISSING_FILES,
                    "LOAD_FAILED": LifecycleStatus.LOAD_FAILED,
                }
                mapped_status = status_map.get(load_res.status, LifecycleStatus.LOAD_FAILED)
                # Fail-closed: existing active version remains completely active and unchanged
                return LifecycleResult(
                    success=False,
                    status=mapped_status,
                    vendor_id=clean_vid,
                    version=clean_ver,
                    error_message=f"Cannot switch to version '{clean_ver}': {load_res.error_message}",
                )

            # Target version is verified and valid. Perform atomic switch in VendorRegistry
            try:
                if self.registry.has_vendor(clean_vid) and clean_ver in self.registry.list_versions(clean_vid):
                    self.registry.activate_version(clean_vid, clean_ver)
                    self.registry.set_vendor_enabled(clean_vid, True)
                    reg = self.registry.get_version_registration(clean_vid, clean_ver)
                else:
                    reg = self.registry.register_plugin_manifest(
                        manifest=load_res.manifest,
                        adapter_class=load_res.adapter_class,
                        activate=True,
                        enabled=True,
                    )
            except Exception as exc:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.REGISTRATION_FAILED,
                    vendor_id=clean_vid,
                    version=clean_ver,
                    error_message=f"Failed to switch version in VendorRegistry: {exc}",
                )

            # Update persistent store index
            self.store.set_active_version(clean_vid, clean_ver)
            self.store.set_plugin_enabled(clean_vid, True)

            log_event(
                domain="Plugins",
                event_type="VERSION_SWITCHED",
                message=f"Switched active version for '{clean_vid}' to v{clean_ver}",
                level="INFO",
                details={"vendor_id": clean_vid, "active_version": clean_ver},
            )

            return LifecycleResult(
                success=True,
                status=LifecycleStatus.SUCCESS,
                vendor_id=clean_vid,
                version=clean_ver,
                registration=reg,
            )

    # -----------------------------------------------------------------------
    # Startup Recovery & Restoration
    # -----------------------------------------------------------------------

    def restore_on_startup(self) -> Dict[str, LifecycleResult]:
        """
        Execute application startup plugin reconciliation and restoration.

        1. Reconciles crash journals and orphaned/unindexed staging directories.
        2. Queries authoritative installed_plugins.json.
        3. Restores previously enabled plugins into VendorRegistry fail-closed.
        4. Leaves corrupted or tampered plugins inactive without crashing startup.

        Returns:
            Dict mapping vendor_id to its LifecycleResult.
        """
        with self._lock:
            # Step 1: Run crash recovery reconciliation
            try:
                reconcile_logs = self.store.reconcile_on_startup()
                if reconcile_logs:
                    log_event(
                        domain="Plugins",
                        event_type="STARTUP_RECONCILE",
                        message=f"Startup reconciliation completed: {len(reconcile_logs)} actions",
                        level="INFO",
                    )
            except Exception as exc:
                log_event(
                    domain="Plugins",
                    event_type="STARTUP_RECONCILE_ERROR",
                    message=f"Startup reconciliation encountered error: {exc}",
                    level="WARNING",
                )

            # Step 2: Read authoritative index
            index = self.store.load_index()
            results: Dict[str, LifecycleResult] = {}

            for vid, p_rec in sorted(index.items()):
                # Only restore plugins marked enabled with a valid active_version
                if p_rec.enabled and p_rec.active_version:
                    target_ver = p_rec.active_version
                    try:
                        res = self.activate_plugin(vid, target_ver)
                        results[vid] = res
                        if not res.success:
                            log_event(
                                domain="Plugins",
                                event_type="STARTUP_RESTORE_FAILED",
                                message=f"Failed to restore plugin '{vid}' v{target_ver} on startup: {res.error_message}",
                                level="WARNING",
                                details={"vendor_id": vid, "version": target_ver, "status": res.status.value},
                            )
                    except Exception as exc:
                        results[vid] = LifecycleResult(
                            success=False,
                            status=LifecycleStatus.LOAD_FAILED,
                            vendor_id=vid,
                            version=target_ver,
                            error_message=f"Unhandled exception during startup restoration: {exc}",
                        )
                        log_event(
                            domain="Plugins",
                            event_type="STARTUP_RESTORE_EXCEPTION",
                            message=f"Unhandled exception restoring '{vid}': {exc}",
                            level="ERROR",
                        )

            return results

    # -----------------------------------------------------------------------
    # Uninstallation
    # -----------------------------------------------------------------------

    def uninstall_plugin(
        self,
        vendor_id: str,
        version: Optional[str] = None,
    ) -> LifecycleResult:
        """
        Uninstall a plugin version or entire vendor plugin family.

        1. Deactivates and purges routes from VendorRegistry if active.
        2. Safely deletes physical files from data/plugins/installed/.
        3. Updates or purges persistent record in installed_plugins.json.
        """
        if not vendor_id or not isinstance(vendor_id, str) or not vendor_id.strip():
            return LifecycleResult(
                success=False,
                status=LifecycleStatus.NOT_INSTALLED,
                vendor_id=str(vendor_id),
                error_message="Invalid vendor_id provided",
            )

        clean_vid = vendor_id.strip()

        with self._lock:
            p_rec = self.store.get_plugin(clean_vid)
            if p_rec is None:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.NOT_INSTALLED,
                    vendor_id=clean_vid,
                    error_message=f"Vendor '{clean_vid}' is not installed",
                )

            # Single version uninstall
            if version is not None:
                clean_ver = version.strip()
                if clean_ver not in p_rec.installed_versions:
                    return LifecycleResult(
                        success=False,
                        status=LifecycleStatus.VERSION_NOT_FOUND,
                        vendor_id=clean_vid,
                        version=clean_ver,
                        error_message=f"Version '{clean_ver}' is not installed for vendor '{clean_vid}'",
                    )

                # If active, deactivate first
                if p_rec.active_version == clean_ver:
                    self.deactivate_plugin(clean_vid)

                if self.registry.has_vendor(clean_vid):
                    self.registry.unregister_version(clean_vid, clean_ver)

                # Remove physical files
                ver_rec = p_rec.installed_versions[clean_ver]
                install_dir = Path(ver_rec.install_path).resolve()
                installed_root_resolved = self.store.installed_root.resolve()

                # Explicit path containment check (defense in depth)
                try:
                    if not install_dir.is_relative_to(installed_root_resolved) or install_dir == installed_root_resolved:
                        log_event(
                            domain="Plugins",
                            event_type="UNINSTALL_PATH_ESCAPE",
                            message=f"Security violation: install_path '{install_dir}' escapes installed_root '{installed_root_resolved}'",
                            level="ERROR",
                            details={"vendor_id": clean_vid, "version": clean_ver, "path": str(install_dir)},
                        )
                        return LifecycleResult(
                            success=False,
                            status=LifecycleStatus.UNINSTALL_FAILED,
                            vendor_id=clean_vid,
                            version=clean_ver,
                            error_message=f"Path containment violation: install path '{install_dir}' is not within '{installed_root_resolved}'",
                        )
                except (ValueError, TypeError) as exc:
                    return LifecycleResult(
                        success=False,
                        status=LifecycleStatus.UNINSTALL_FAILED,
                        vendor_id=clean_vid,
                        version=clean_ver,
                        error_message=f"Invalid install path containment: {exc}",
                    )

                if install_dir.is_dir():
                    try:
                        shutil.rmtree(install_dir)
                    except Exception as exc:
                        log_event(
                            domain="Plugins",
                            event_type="FILE_DELETE_ERROR",
                            message=f"Failed to delete directory '{install_dir}': {exc}",
                            level="WARNING",
                        )

                # Remove from persistent index
                self.store.remove_installed_version(clean_vid, clean_ver)

                # Check if all versions removed
                p_after = self.store.get_plugin(clean_vid)
                if p_after is None or len(p_after.installed_versions) == 0:
                    vendor_dir = (self.store.installed_root / clean_vid).resolve()
                    if vendor_dir.is_relative_to(installed_root_resolved) and vendor_dir != installed_root_resolved:
                        if vendor_dir.is_dir():
                            shutil.rmtree(vendor_dir, ignore_errors=True)
                    if self.registry.has_vendor(clean_vid):
                        self.registry.unregister_adapter(clean_vid)

                log_event(
                    domain="Plugins",
                    event_type="VERSION_UNINSTALLED",
                    message=f"Uninstalled version '{clean_ver}' of plugin '{clean_vid}'",
                    level="INFO",
                    details={"vendor_id": clean_vid, "version": clean_ver},
                )

                return LifecycleResult(
                    success=True,
                    status=LifecycleStatus.SUCCESS,
                    vendor_id=clean_vid,
                    version=clean_ver,
                )

            # Full vendor family uninstall
            self.deactivate_plugin(clean_vid)

            if self.registry.has_vendor(clean_vid):
                self.registry.unregister_adapter(clean_vid)

            # Remove physical files
            vendor_dir = (self.store.installed_root / clean_vid).resolve()
            installed_root_resolved = self.store.installed_root.resolve()

            # Explicit path containment check (defense in depth)
            try:
                if not vendor_dir.is_relative_to(installed_root_resolved) or vendor_dir == installed_root_resolved:
                    log_event(
                        domain="Plugins",
                        event_type="UNINSTALL_PATH_ESCAPE",
                        message=f"Security violation: vendor_dir '{vendor_dir}' escapes installed_root '{installed_root_resolved}'",
                        level="ERROR",
                        details={"vendor_id": clean_vid, "path": str(vendor_dir)},
                    )
                    return LifecycleResult(
                        success=False,
                        status=LifecycleStatus.UNINSTALL_FAILED,
                        vendor_id=clean_vid,
                        error_message=f"Path containment violation: vendor path '{vendor_dir}' is not within '{installed_root_resolved}'",
                    )
            except (ValueError, TypeError) as exc:
                return LifecycleResult(
                    success=False,
                    status=LifecycleStatus.UNINSTALL_FAILED,
                    vendor_id=clean_vid,
                    error_message=f"Invalid vendor path containment: {exc}",
                )

            if vendor_dir.is_dir():
                try:
                    shutil.rmtree(vendor_dir)
                except Exception as exc:
                    log_event(
                        domain="Plugins",
                        event_type="FILE_DELETE_ERROR",
                        message=f"Failed to delete vendor directory '{vendor_dir}': {exc}",
                        level="WARNING",
                    )

            # Remove from persistent index
            self.store.remove_plugin(clean_vid)

            log_event(
                domain="Plugins",
                event_type="PLUGIN_UNINSTALLED",
                message=f"Uninstalled plugin '{clean_vid}' completely",
                level="INFO",
                details={"vendor_id": clean_vid},
            )

            return LifecycleResult(
                success=True,
                status=LifecycleStatus.SUCCESS,
                vendor_id=clean_vid,
            )

    # -----------------------------------------------------------------------
    # Status & Diagnostics
    # -----------------------------------------------------------------------

    def get_plugin_status(self, vendor_id: str) -> Dict[str, Any]:
        """
        Return consolidated status of a vendor plugin across persistent store
        and runtime VendorRegistry.
        """
        clean_vid = str(vendor_id).strip()
        with self._lock:
            p_rec = self.store.get_plugin(clean_vid)
            if p_rec is None:
                return {
                    "vendor_id": clean_vid,
                    "is_installed": False,
                    "installed_versions": [],
                    "active_version_store": None,
                    "enabled_store": False,
                    "is_registered_in_registry": self.registry.has_vendor(clean_vid),
                    "active_version_registry": self.registry.get_active_version(clean_vid),
                    "is_enabled_in_registry": self.registry.is_vendor_enabled(clean_vid),
                    "routed_domains": [],
                    "version_statuses": {},
                }

            # Map version statuses
            v_statuses = {
                ver: v_rec.status.value
                for ver, v_rec in p_rec.installed_versions.items()
            }

            # Get routed domains from registry if active
            routed_domains = []
            if self.registry.has_vendor(clean_vid):
                active_ver = self.registry.get_active_version(clean_vid)
                if active_ver and active_ver in self.registry.list_versions(clean_vid):
                    reg = self.registry.get_version_registration(clean_vid, active_ver)
                    routed_domains = list(reg.domains)

            return {
                "vendor_id": clean_vid,
                "is_installed": True,
                "installed_versions": sorted(list(p_rec.installed_versions.keys()), key=lambda v: SemanticVersion(v)),
                "active_version_store": p_rec.active_version,
                "enabled_store": p_rec.enabled,
                "is_registered_in_registry": self.registry.has_vendor(clean_vid),
                "active_version_registry": self.registry.get_active_version(clean_vid),
                "is_enabled_in_registry": self.registry.is_vendor_enabled(clean_vid),
                "routed_domains": routed_domains,
                "version_statuses": v_statuses,
            }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_default_lifecycle_manager: Optional[PluginLifecycleManager] = None
_manager_lock = threading.Lock()


def get_lifecycle_manager(
    store: Optional[PluginStore] = None,
    loader: Optional[PluginLoader] = None,
    registry: Optional[VendorRegistry] = None,
) -> PluginLifecycleManager:
    """Retrieve or create the default singleton PluginLifecycleManager."""
    global _default_lifecycle_manager
    if store is not None or loader is not None or registry is not None:
        return PluginLifecycleManager(store=store, loader=loader, registry=registry)

    with _manager_lock:
        if _default_lifecycle_manager is None:
            _default_lifecycle_manager = PluginLifecycleManager()
        return _default_lifecycle_manager


def restore_installed_plugins(
    registry: Optional[VendorRegistry] = None,
    store: Optional[PluginStore] = None,
    loader: Optional[PluginLoader] = None,
) -> Dict[str, LifecycleResult]:
    """Convenience helper to restore installed plugins on application boot."""
    mgr = get_lifecycle_manager(store=store, loader=loader, registry=registry)
    return mgr.restore_on_startup()
