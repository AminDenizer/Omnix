"""
Omnix Core - Vendor Registry & Adapter Factory
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 15
"""

import os
from pathlib import Path
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, Any, Union, Tuple

from core.errors import UnknownVendorError
from core.models import AdapterConfig, VendorSettings
from core.vendor_interface import IVendorAdapter
from core.logger import log_event, track_operation
from core.plugins.manifest_validator import (
    validate_manifest,
    validate_manifest_file,
    ManifestError,
    ManifestValidationError,
    SemanticVersion,
    SEMVER_REGEX,
)

LEGACY_DEFAULT_VERSION = "0.0.0-dev"


@dataclass
class PluginVersionRegistration:
    """Metadata describing a registered vendor plugin version and its storefront routing."""
    vendor_id: str
    adapter_class: Type[IVendorAdapter]
    version: str = LEGACY_DEFAULT_VERSION
    plugin_id: str = ""
    default_config: Optional[AdapterConfig] = None
    domains: List[str] = field(default_factory=list)
    display_name: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    modes: List[str] = field(default_factory=list)
    routes: Dict[str, Any] = field(default_factory=dict)
    manifest: Optional[Dict[str, Any]] = None
    is_manifest_backed: bool = False
    enabled: bool = True
    settings: Optional[VendorSettings] = None


# Backward-compatible alias for existing callers and test suites
VendorRegistration = PluginVersionRegistration


class VendorRegistry:
    """
    Thread-safe registry and factory for Omnix Vendor Adapters and Plugins.

    Responsibilities:
    1. Multi-version metadata indexing: Allow multiple SemVer versions of a vendor plugin family.
    2. Active version pointer management: Maintain an atomic active pointer per vendor.
    3. Active storefront route dispatching: Storefront domains resolve exclusively through active versions.
    4. Provider identity consistency: 1-to-1 mapping between vendor_id and plugin_id per registry instance.
    5. Atomic route-to-adapter resolution: Single snapshot URL resolution eliminating TOCTOU race conditions.
    6. Multi-vendor dynamic enable/disable tracking (GAP-11).
    7. Complete isolation from DOM selectors, HTML parsing, or procurement math.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # vendor_id -> {version_str: PluginVersionRegistration}
        self._versions: Dict[str, Dict[str, PluginVersionRegistration]] = {}
        # vendor_id -> Optional[str] (active SemVer version string or None)
        self._active_versions: Dict[str, Optional[str]] = {}
        # vendor_id -> bool
        self._vendor_enabled: Dict[str, bool] = {}
        # vendor_id -> Optional[VendorSettings]
        self._vendor_settings: Dict[str, Optional[VendorSettings]] = {}
        # domain -> (vendor_id, version)
        self._domain_to_route: Dict[str, Tuple[str, str]] = {}
        # vendor_id -> plugin_id
        self._vendor_to_plugin_id: Dict[str, str] = {}
        # plugin_id -> vendor_id
        self._plugin_id_to_vendor: Dict[str, str] = {}

    @property
    def _registrations(self) -> Dict[str, PluginVersionRegistration]:
        """Backward-compatibility property returning active or latest registration per vendor."""
        with self._lock:
            result = {}
            for vid, vers in self._versions.items():
                active_v = self._active_versions.get(vid)
                if active_v and active_v in vers:
                    result[vid] = vers[active_v]
                elif vers:
                    sorted_vers = sorted(vers.keys(), key=lambda v: SemanticVersion(v))
                    result[vid] = vers[sorted_vers[-1]]
            return result

    @property
    def _domain_to_vendor(self) -> Dict[str, str]:
        """Backward-compatibility property mapping domain to active vendor_id."""
        with self._lock:
            return {d: vid for d, (vid, ver) in self._domain_to_route.items()}

    def register_adapter(
        self,
        vendor_id: str,
        adapter_class: Type[IVendorAdapter],
        config: Optional[AdapterConfig] = None,
        domains: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        description: str = "",
        enabled: bool = True,
        settings: Optional[VendorSettings] = None,
        version: str = LEGACY_DEFAULT_VERSION,
        plugin_id: Optional[str] = None,
        activate: Optional[bool] = None,
    ) -> PluginVersionRegistration:
        """
        Register a vendor adapter class with the registry (legacy programmatic / in-tree path).

        Args:
            vendor_id: Unique string identifier (e.g. 'vendor_lion', 'vendor_javan').
            adapter_class: Subclass of IVendorAdapter.
            config: Optional default AdapterConfig.
            domains: Optional list of storefront domains (e.g. ['lionelectronic.ir']).
            display_name: Human-readable vendor name.
            description: Optional vendor description.
            enabled: Initial enabled flag for the vendor (GAP-11).
            settings: Optional VendorSettings model.
            version: SemVer 2.0.0 version string (defaults to '0.0.0-dev').
            plugin_id: Plugin family identifier (defaults to 'local.{vendor_id}.in_tree').
            activate: Optional activation flag. If None, auto-activates only on first version registration.

        Raises:
            ValueError: If vendor_id, adapter_class, version, or plugin_id is invalid,
                        if version is already registered, or if domain conflicts occur.
        """
        if not vendor_id or not isinstance(vendor_id, str) or not vendor_id.strip():
            raise ValueError("vendor_id must be a non-empty string.")

        clean_id = vendor_id.strip()

        if not isinstance(adapter_class, type) or not issubclass(adapter_class, IVendorAdapter):
            raise ValueError(f"adapter_class for '{clean_id}' must be a subclass of IVendorAdapter.")

        clean_ver = (version or LEGACY_DEFAULT_VERSION).strip()
        try:
            SemanticVersion(clean_ver)
        except Exception as e:
            raise ValueError(f"Invalid version '{clean_ver}': must be valid SemVer 2.0.0.") from e

        clean_plugin_id = (plugin_id or f"local.{clean_id}.in_tree").strip()

        # Determine target domains
        target_domains: List[str] = []
        if domains:
            for d in domains:
                norm_d = self._normalize_domain(d)
                if norm_d and norm_d not in target_domains:
                    target_domains.append(norm_d)
        elif config and config.base_url:
            norm_d = self._extract_domain_from_url(config.base_url)
            if norm_d and norm_d not in target_domains:
                target_domains.append(norm_d)

        effective_enabled = enabled
        if settings is not None:
            effective_enabled = settings.enabled

        tracker = track_operation("Plugins", f"Register vendor adapter '{clean_id}' v{clean_ver}")
        tracker.__enter__()
        self._lock.acquire()
        try:
            # Identity consistency check
            existing_pid = self._vendor_to_plugin_id.get(clean_id)
            if existing_pid is not None and existing_pid != clean_plugin_id:
                raise ValueError(
                    f"Plugin identity conflict: Vendor '{clean_id}' is already registered with plugin_id '{existing_pid}'. "
                    f"Cannot register version with different plugin_id '{clean_plugin_id}'. Unregister vendor first to replace provider."
                )
            existing_vid = self._plugin_id_to_vendor.get(clean_plugin_id)
            if existing_vid is not None and existing_vid != clean_id:
                raise ValueError(
                    f"Plugin identity conflict: Plugin ID '{clean_plugin_id}' is already registered to vendor '{existing_vid}'. "
                    f"Cannot register to vendor '{clean_id}'."
                )

            # Duplicate version check
            if clean_id in self._versions and clean_ver in self._versions[clean_id]:
                raise ValueError(f"Vendor '{clean_id}' version '{clean_ver}' is already registered in VendorRegistry.")

            # Activation policy
            num_existing = len(self._versions.get(clean_id, {}))
            if activate is None:
                should_activate = (num_existing == 0)
            else:
                should_activate = bool(activate)

            # Route collision check if activating
            if should_activate:
                for d in target_domains:
                    if d in self._domain_to_route:
                        colliding_vid, colliding_ver = self._domain_to_route[d]
                        if colliding_vid != clean_id:
                            raise ValueError(
                                f"Domain conflict: Domain '{d}' is already routed to '{colliding_vid}' (version '{colliding_ver}')."
                            )

            reg = PluginVersionRegistration(
                vendor_id=clean_id,
                adapter_class=adapter_class,
                version=clean_ver,
                plugin_id=clean_plugin_id,
                default_config=config,
                domains=target_domains,
                display_name=display_name or clean_id,
                description=description,
                capabilities=[],
                modes=[],
                routes={"domains": target_domains, "base_url": config.base_url if config else ""},
                manifest=None,
                is_manifest_backed=False,
                enabled=effective_enabled,
                settings=settings,
            )

            if clean_id not in self._versions:
                self._versions[clean_id] = {}
            self._versions[clean_id][clean_ver] = reg

            self._vendor_to_plugin_id[clean_id] = clean_plugin_id
            self._plugin_id_to_vendor[clean_plugin_id] = clean_id

            self._vendor_enabled.setdefault(clean_id, effective_enabled)
            self._vendor_settings.setdefault(clean_id, settings)
            if settings is not None:
                self._vendor_settings[clean_id] = settings
                self._vendor_enabled[clean_id] = settings.enabled

            if should_activate:
                prev_ver = self._active_versions.get(clean_id)
                if prev_ver and prev_ver in self._versions[clean_id]:
                    for d in self._versions[clean_id][prev_ver].domains:
                        if self._domain_to_route.get(d) == (clean_id, prev_ver):
                            del self._domain_to_route[d]
                for d in target_domains:
                    self._domain_to_route[d] = (clean_id, clean_ver)
                self._active_versions[clean_id] = clean_ver
            else:
                if clean_id not in self._active_versions:
                    self._active_versions[clean_id] = None

            tracker.complete(f"Registered vendor adapter '{clean_id}' (version {clean_ver})")
            return reg
        except Exception:
            tracker.fail()
            raise
        finally:
            self._lock.release()

    def register_plugin_manifest(
        self,
        manifest: Union[str, bytes, Dict[str, Any], Path],
        adapter_class: Type[IVendorAdapter],
        config: Optional[AdapterConfig] = None,
        settings: Optional[VendorSettings] = None,
        enabled: bool = True,
        activate: Optional[bool] = None,
    ) -> PluginVersionRegistration:
        """
        Explicitly register a vendor plugin version backed by a validated manifest descriptor.

        Requirements:
        1. Validates manifest metadata strictly against schema and semantic rules before mutation.
        2. Rejects invalid manifests atomically without mutating registry, identity indexes, or domain routing.
        3. Enforces provider identity consistency across versions.
        4. Prevents duplicate version registrations and active domain collisions.
        5. Derives registration metadata (vendor_id, plugin_id, version, capabilities, modes, routes)
           directly from the validated manifest.
        6. Preserves IVendorAdapter contract validation.
        7. Governs activation via Phase 3 policy (auto-activates first version; additional versions default inactive).

        Raises:
            ManifestError: If the manifest fails schema, syntax, or semantic validation.
            ValueError: If adapter_class is invalid, version duplicated, identity conflicted, or domain collision occurs.
        """
        # Step 1: Validate manifest metadata before touching any registry state
        if isinstance(manifest, Path) or (isinstance(manifest, str) and os.path.isfile(manifest)):
            val_res = validate_manifest_file(manifest)
        else:
            val_res = validate_manifest(manifest)

        if not val_res.is_valid:
            val_res.raise_for_errors()

        manifest_dict = val_res.manifest
        if not manifest_dict:
            raise ValueError("Manifest validation succeeded but produced empty manifest dictionary.")

        # Step 2: Extract metadata from validated manifest
        vendor_id = manifest_dict["vendor_id"].strip()
        plugin_id = manifest_dict["plugin_id"].strip()
        version = manifest_dict["version"].strip()
        display_name = manifest_dict.get("display_name", vendor_id)
        description = manifest_dict.get("description", "")
        capabilities = list(manifest_dict.get("capabilities", []))
        modes = list(manifest_dict.get("supported_modes", []))
        routes = manifest_dict.get("routes", {})
        base_url = routes.get("base_url", "")
        raw_domains = routes.get("domains", [])

        # Step 3: Validate adapter_class contract
        if not isinstance(adapter_class, type) or not issubclass(adapter_class, IVendorAdapter):
            raise ValueError(f"adapter_class for '{vendor_id}' must be a subclass of IVendorAdapter.")

        if hasattr(adapter_class, "VENDOR_ID") and getattr(adapter_class, "VENDOR_ID") != vendor_id:
            raise ValueError(
                f"Manifest vendor_id '{vendor_id}' does not match adapter class VENDOR_ID '{getattr(adapter_class, 'VENDOR_ID')}'."
            )

        # Normalize domains
        target_domains: List[str] = []
        for d in raw_domains:
            norm_d = self._normalize_domain(d)
            if norm_d and norm_d not in target_domains:
                target_domains.append(norm_d)

        effective_config = config
        if effective_config is None and base_url:
            effective_config = AdapterConfig(vendor_id=vendor_id, base_url=base_url)

        effective_enabled = enabled
        if settings is not None:
            effective_enabled = settings.enabled

        # Step 4: Atomic registration under lock
        tracker = track_operation("Plugins", f"Register manifest plugin '{plugin_id}' v{version}")
        tracker.__enter__()
        self._lock.acquire()
        try:
            # Identity consistency check
            existing_pid = self._vendor_to_plugin_id.get(vendor_id)
            if existing_pid is not None and existing_pid != plugin_id:
                raise ValueError(
                    f"Plugin identity conflict: Vendor '{vendor_id}' is already registered with plugin_id '{existing_pid}'. "
                    f"Cannot register version with different plugin_id '{plugin_id}'. Unregister vendor first to replace provider."
                )
            existing_vid = self._plugin_id_to_vendor.get(plugin_id)
            if existing_vid is not None and existing_vid != vendor_id:
                raise ValueError(
                    f"Plugin identity conflict: Plugin ID '{plugin_id}' is already registered to vendor '{existing_vid}'. "
                    f"Cannot register to vendor '{vendor_id}'."
                )

            # Duplicate version check
            if vendor_id in self._versions and version in self._versions[vendor_id]:
                raise ValueError(f"Version '{version}' for vendor '{vendor_id}' is already registered in VendorRegistry.")

            # Activation policy
            num_existing = len(self._versions.get(vendor_id, {}))
            if activate is None:
                should_activate = (num_existing == 0)
            else:
                should_activate = bool(activate)

            # Route collision check if activating
            if should_activate:
                for d in target_domains:
                    if d in self._domain_to_route:
                        colliding_vid, colliding_ver = self._domain_to_route[d]
                        if colliding_vid != vendor_id:
                            raise ValueError(
                                f"Domain conflict: Domain '{d}' is already routed to '{colliding_vid}' (version '{colliding_ver}')."
                            )

            reg = PluginVersionRegistration(
                vendor_id=vendor_id,
                adapter_class=adapter_class,
                version=version,
                plugin_id=plugin_id,
                default_config=effective_config,
                domains=target_domains,
                display_name=display_name,
                description=description,
                capabilities=capabilities,
                modes=modes,
                routes=routes,
                manifest=manifest_dict,
                is_manifest_backed=True,
                enabled=effective_enabled,
                settings=settings,
            )

            if vendor_id not in self._versions:
                self._versions[vendor_id] = {}
            self._versions[vendor_id][version] = reg

            self._vendor_to_plugin_id[vendor_id] = plugin_id
            self._plugin_id_to_vendor[plugin_id] = vendor_id

            self._vendor_enabled.setdefault(vendor_id, effective_enabled)
            self._vendor_settings.setdefault(vendor_id, settings)
            if settings is not None:
                self._vendor_settings[vendor_id] = settings
                self._vendor_enabled[vendor_id] = settings.enabled

            if should_activate:
                prev_ver = self._active_versions.get(vendor_id)
                if prev_ver and prev_ver in self._versions[vendor_id]:
                    for d in self._versions[vendor_id][prev_ver].domains:
                        if self._domain_to_route.get(d) == (vendor_id, prev_ver):
                            del self._domain_to_route[d]
                for d in target_domains:
                    self._domain_to_route[d] = (vendor_id, version)
                self._active_versions[vendor_id] = version
            else:
                if vendor_id not in self._active_versions:
                    self._active_versions[vendor_id] = None

            tracker.complete(f"Registered manifest plugin '{plugin_id}' v{version} for vendor '{vendor_id}'")
            return reg
        except Exception:
            tracker.fail()
            raise
        finally:
            self._lock.release()

    def activate_version(self, vendor_id: str, version: str) -> None:
        """
        Explicitly activate a specific registered version for a vendor.

        Atomically switches the active pointer and active storefront domain route mappings.

        Raises:
            UnknownVendorError: If vendor_id is not registered.
            ValueError: If version is not registered for vendor_id, or if a domain collision occurs.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))
        if not version or not isinstance(version, str):
            raise ValueError("Invalid version provided.")

        clean_id = vendor_id.strip()
        clean_ver = version.strip()

        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            if clean_ver not in self._versions[clean_id]:
                raise ValueError(f"Version '{clean_ver}' is not registered for vendor '{clean_id}'.")

            target_reg = self._versions[clean_id][clean_ver]

            # Validate route collisions before modifying any state
            for d in target_reg.domains:
                if d in self._domain_to_route:
                    colliding_vid, colliding_ver = self._domain_to_route[d]
                    if colliding_vid != clean_id:
                        raise ValueError(
                            f"Domain conflict: Domain '{d}' is already routed to '{colliding_vid}' (version '{colliding_ver}')."
                        )

            # Remove previous active routes for this vendor
            old_ver = self._active_versions.get(clean_id)
            if old_ver and old_ver in self._versions[clean_id]:
                for d in self._versions[clean_id][old_ver].domains:
                    if self._domain_to_route.get(d) == (clean_id, old_ver):
                        del self._domain_to_route[d]

            # Clear any orphan routes for clean_id
            orphans = [d for d, (vid, v) in self._domain_to_route.items() if vid == clean_id]
            for d in orphans:
                del self._domain_to_route[d]

            # Map new active version routes
            for d in target_reg.domains:
                self._domain_to_route[d] = (clean_id, clean_ver)

            # Update active version pointer
            self._active_versions[clean_id] = clean_ver

    def deactivate_vendor(self, vendor_id: str) -> None:
        """
        Deactivate a vendor, removing all its active storefront domain route mappings
        and setting its active pointer to None without deleting its registered versions.

        Raises:
            UnknownVendorError: If vendor_id is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))

        clean_id = vendor_id.strip()

        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)

            old_ver = self._active_versions.get(clean_id)
            if old_ver and old_ver in self._versions[clean_id]:
                for d in self._versions[clean_id][old_ver].domains:
                    if self._domain_to_route.get(d) == (clean_id, old_ver):
                        del self._domain_to_route[d]

            orphans = [d for d, (vid, v) in self._domain_to_route.items() if vid == clean_id]
            for d in orphans:
                del self._domain_to_route[d]

            self._active_versions[clean_id] = None

    def get_active_version(self, vendor_id: str) -> Optional[str]:
        """
        Return the currently active SemVer version string for vendor_id, or None if inactive/unregistered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            return None
        clean_id = vendor_id.strip()
        with self._lock:
            return self._active_versions.get(clean_id)

    def list_versions(self, vendor_id: str) -> List[str]:
        """
        Return a deterministically sorted list of all registered SemVer versions for a vendor.

        Raises:
            UnknownVendorError: If vendor_id is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))
        clean_id = vendor_id.strip()
        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            return [str(v) for v in sorted(self._versions[clean_id].keys(), key=lambda v: SemanticVersion(v))]

    def get_version_registration(self, vendor_id: str, version: str) -> PluginVersionRegistration:
        """
        Retrieve metadata for a specific registered version regardless of active state.

        Raises:
            UnknownVendorError: If vendor_id is not registered.
            ValueError: If version is not registered for vendor_id.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))
        if not version or not isinstance(version, str):
            raise ValueError("Invalid version provided.")
        clean_id = vendor_id.strip()
        clean_ver = version.strip()
        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            if clean_ver not in self._versions[clean_id]:
                raise ValueError(f"Version '{clean_ver}' is not registered for vendor '{clean_id}'.")
            return self._versions[clean_id][clean_ver]

    def unregister_version(self, vendor_id: str, version: str) -> bool:
        """
        Unregister a specific version of a vendor.

        If the unregistered version is currently active, clears its active pointer and routes
        without silent fallback/auto-promotion.
        If all versions of the vendor are unregistered, cleans up vendor-level state and identity bindings.

        Returns:
            True if version was found and unregistered; False otherwise.
        """
        if not vendor_id or not isinstance(vendor_id, str) or not version or not isinstance(version, str):
            return False
        clean_id = vendor_id.strip()
        clean_ver = version.strip()

        with self._lock:
            if clean_id not in self._versions or clean_ver not in self._versions[clean_id]:
                return False

            # If active, deactivate without promoting another version
            if self._active_versions.get(clean_id) == clean_ver:
                self.deactivate_vendor(clean_id)

            del self._versions[clean_id][clean_ver]

            # If no versions remain, clean up vendor-level state
            if len(self._versions[clean_id]) == 0:
                del self._versions[clean_id]
                self._active_versions.pop(clean_id, None)
                self._vendor_enabled.pop(clean_id, None)
                self._vendor_settings.pop(clean_id, None)
                pid = self._vendor_to_plugin_id.pop(clean_id, None)
                if pid and pid in self._plugin_id_to_vendor:
                    del self._plugin_id_to_vendor[pid]

            return True

    def unregister_adapter(self, vendor_id: str) -> bool:
        """
        Unregister all versions of a vendor and clear all associated storefront route mappings.
        Thread-safe and atomic.

        Returns:
            True if the vendor was found and unregistered; False if not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        clean_id = vendor_id.strip()
        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                return False

            if self._active_versions.get(clean_id) is not None:
                self.deactivate_vendor(clean_id)

            orphans = [d for d, (vid, v) in self._domain_to_route.items() if vid == clean_id]
            for d in orphans:
                del self._domain_to_route[d]

            del self._versions[clean_id]
            self._active_versions.pop(clean_id, None)
            self._vendor_enabled.pop(clean_id, None)
            self._vendor_settings.pop(clean_id, None)
            pid = self._vendor_to_plugin_id.pop(clean_id, None)
            if pid and pid in self._plugin_id_to_vendor:
                del self._plugin_id_to_vendor[pid]

            return True

    def is_vendor_enabled(self, vendor_id: str) -> bool:
        """
        Check if a registered vendor is currently enabled.
        Governing GAP: GAP-11 Section 3.1.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        clean_id = vendor_id.strip()
        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                return False
            return self._vendor_enabled.get(clean_id, True)

    def set_vendor_enabled(self, vendor_id: str, enabled: bool) -> None:
        """
        Dynamically enable or disable a registered vendor.
        Governing GAP: GAP-11 Section 3.1.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))
        clean_id = vendor_id.strip()
        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            action_word = "Enable" if enabled else "Disable"
            with track_operation("Plugins", f"{action_word} vendor plugin '{clean_id}'") as tracker:
                self._vendor_enabled[clean_id] = enabled
                settings = self._vendor_settings.get(clean_id)
                if settings is not None:
                    settings.enabled = enabled
                for reg in self._versions[clean_id].values():
                    reg.enabled = enabled
                status_word = "Enabled" if enabled else "Disabled"
                tracker.complete(f"{status_word} vendor plugin '{clean_id}'")

    def get_enabled_vendors(self) -> List[str]:
        """
        Return a sorted list of registered vendor identifiers that are currently ACTIVE AND ENABLED.
        Governing GAP: GAP-11 Section 3.1 & Phase 3 Section 7.
        """
        with self._lock:
            return sorted([
                vid for vid, ver in self._active_versions.items()
                if ver is not None
                and vid in self._versions
                and ver in self._versions[vid]
                and self._vendor_enabled.get(vid, True)
            ])

    def get_adapter(
        self,
        vendor_id: str,
        config: Optional[AdapterConfig] = None,
        version: Optional[str] = None,
    ) -> IVendorAdapter:
        """
        Instantiate and return an IVendorAdapter for the given vendor_id.

        Dispatches exclusively to the active version unless a specific version is requested.
        Raises UnknownVendorError if no version is active or vendor is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid or empty vendor_id provided.", vendor_id=str(vendor_id))

        clean_id = vendor_id.strip()

        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(
                    f"Unknown vendor identifier '{clean_id}'. Registered vendors: {self.list_vendors()}",
                    vendor_id=clean_id,
                )

            if version is not None:
                clean_ver = version.strip()
                if clean_ver not in self._versions[clean_id]:
                    raise UnknownVendorError(
                        f"Version '{clean_ver}' for vendor '{clean_id}' is not registered.",
                        vendor_id=clean_id,
                    )
                reg = self._versions[clean_id][clean_ver]
            else:
                active_ver = self._active_versions.get(clean_id)
                if not active_ver or active_ver not in self._versions[clean_id]:
                    raise UnknownVendorError(
                        f"Vendor '{clean_id}' has no active version.",
                        vendor_id=clean_id,
                    )
                reg = self._versions[clean_id][active_ver]

            effective_config = config or reg.default_config
            adapter_instance = reg.adapter_class(config=effective_config)
            return adapter_instance

    def resolve_adapter_for_url(
        self,
        url: str,
        config: Optional[AdapterConfig] = None,
        enabled_only: bool = False,
    ) -> Tuple[Optional[IVendorAdapter], Optional[PluginVersionRegistration]]:
        """
        Atomically resolve a storefront URL to its active vendor adapter instance and version registration.

        Guarantees:
        1. Zero race conditions: The active version used to recognize the domain is the exact version
           instantiated and returned.
        2. Strict active-version routing: Dispatches ONLY to currently active versions.
        3. Thread-safe snapshot: Executed entirely under the registry re-entrant lock.
        """
        if not url or not isinstance(url, str) or not url.strip():
            return None, None

        extracted_domain = self._extract_domain_from_url(url)
        if not extracted_domain:
            return None, None

        with self._lock:
            target: Optional[Tuple[str, str]] = None
            # 1. Exact domain match
            if extracted_domain in self._domain_to_route:
                target = self._domain_to_route[extracted_domain]
            else:
                # 2. Subdomain match
                for registered_domain, route_tuple in self._domain_to_route.items():
                    if extracted_domain.endswith("." + registered_domain):
                        target = route_tuple
                        break

            if target is None:
                return None, None

            vendor_id, version = target

            if enabled_only and not self.is_vendor_enabled(vendor_id):
                return None, None

            # Verify active version match
            if self._active_versions.get(vendor_id) != version:
                return None, None

            if vendor_id not in self._versions or version not in self._versions[vendor_id]:
                return None, None

            reg = self._versions[vendor_id][version]
            effective_config = config or reg.default_config
            adapter_instance = reg.adapter_class(config=effective_config)
            return adapter_instance, reg

    def get_vendor_for_url(self, url: str, enabled_only: bool = False) -> Optional[str]:
        """
        Deterministically resolve an e-commerce storefront URL to an active registered vendor_id.
        """
        if not url or not isinstance(url, str) or not url.strip():
            return None

        extracted_domain = self._extract_domain_from_url(url)
        if not extracted_domain:
            return None

        with self._lock:
            matched_vid: Optional[str] = None
            # 1. Exact domain match
            if extracted_domain in self._domain_to_route:
                matched_vid = self._domain_to_route[extracted_domain][0]
            else:
                # 2. Subdomain match
                for registered_domain, (vid, ver) in self._domain_to_route.items():
                    if extracted_domain.endswith("." + registered_domain):
                        matched_vid = vid
                        break

            if matched_vid is not None:
                if enabled_only and not self.is_vendor_enabled(matched_vid):
                    return None
                return matched_vid

        return None

    def list_vendors(self) -> List[str]:
        """Return a sorted list of all registered vendor identifiers (including inactive)."""
        with self._lock:
            return sorted([vid for vid, vers in self._versions.items() if vers])

    def list_active_vendors(self) -> List[str]:
        """Return a sorted list of vendor identifiers that currently have an active version."""
        with self._lock:
            return sorted([
                vid for vid, ver in self._active_versions.items()
                if ver is not None and vid in self._versions and ver in self._versions[vid]
            ])

    def get_registration(self, vendor_id: str, version: Optional[str] = None) -> PluginVersionRegistration:
        """
        Retrieve metadata for a registered vendor.

        If version is omitted, returns metadata for active version if available,
        or highest SemVer version if inactive (for Settings UI / diagnostics compatibility).

        Raises:
            UnknownVendorError: If vendor_id is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))

        clean_id = vendor_id.strip()

        with self._lock:
            if clean_id not in self._versions or not self._versions[clean_id]:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)

            if version is not None:
                clean_ver = version.strip()
                if clean_ver not in self._versions[clean_id]:
                    raise UnknownVendorError(f"Version '{clean_ver}' for vendor '{clean_id}' is not registered.", vendor_id=clean_id)
                return self._versions[clean_id][clean_ver]

            active_ver = self._active_versions.get(clean_id)
            if active_ver and active_ver in self._versions[clean_id]:
                return self._versions[clean_id][active_ver]

            # Inactive vendor fallback for Settings UI / diagnostics
            sorted_vers = sorted(self._versions[clean_id].keys(), key=lambda v: SemanticVersion(v))
            return self._versions[clean_id][sorted_vers[-1]]

    def get_vendor_name(self, vendor_id: str) -> str:
        """Return human-readable display name for a vendor."""
        if not vendor_id:
            return "Vendor"
        clean_id = vendor_id.strip()
        with self._lock:
            if clean_id in self._versions and self._versions[clean_id]:
                active_ver = self._active_versions.get(clean_id)
                if active_ver and active_ver in self._versions[clean_id]:
                    disp = self._versions[clean_id][active_ver].display_name
                    if disp:
                        return disp
                for reg in self._versions[clean_id].values():
                    if reg.display_name:
                        return reg.display_name
            return clean_id.replace("vendor_", "").title()

    def has_vendor(self, vendor_id: str) -> bool:
        """Check if a vendor_id has at least one registered version."""
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        clean_id = vendor_id.strip()
        with self._lock:
            return clean_id in self._versions and len(self._versions[clean_id]) > 0

    def has_active_vendor(self, vendor_id: str) -> bool:
        """Check if a vendor_id has an active version."""
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        clean_id = vendor_id.strip()
        with self._lock:
            ver = self._active_versions.get(clean_id)
            return ver is not None and clean_id in self._versions and ver in self._versions[clean_id]

    def clear(self) -> None:
        """Clear all registrations, versions, routes, and identity mappings (for testing isolation)."""
        with self._lock:
            self._versions.clear()
            self._active_versions.clear()
            self._vendor_enabled.clear()
            self._vendor_settings.clear()
            self._domain_to_route.clear()
            self._vendor_to_plugin_id.clear()
            self._plugin_id_to_vendor.clear()

    def register_default_adapters(self, settings_mgr: Optional[Any] = None) -> None:
        """
        Explicitly register the standard Omnix production vendor adapters:
        - vendor_lion (Lion Electronic: lionelectronic.ir)
        - vendor_javan (Javan Electronic: javanelec.com)
        - vendor_roboeq (RoboEq Electronic: roboeq.ir)

        Ingests multi-vendor settings from SettingsManager (GAP-11).

        Note:
            This method is retained strictly for testing suites and explicit manual setup.
            It is NEVER called automatically during application startup or default registry retrieval.
            Missing vendor adapter modules will not crash caller imports.
        """
        try:
            from vendors.lion.adapter import LionVendorAdapter
        except ImportError:
            LionVendorAdapter = None

        try:
            from vendors.javan.adapter import JavanVendorAdapter
        except ImportError:
            JavanVendorAdapter = None

        try:
            from vendors.roboeq.adapter import RoboEqVendorAdapter
        except ImportError:
            RoboEqVendorAdapter = None

        if settings_mgr is None:
            try:
                from settings_manager import settings
                settings_mgr = settings
            except Exception:
                settings_mgr = None

        with self._lock:
            # 1. Lion Electronic
            if LionVendorAdapter is not None and not self.has_vendor(LionVendorAdapter.VENDOR_ID):
                lion_settings = settings_mgr.get_vendor_settings(LionVendorAdapter.VENDOR_ID) if settings_mgr else None
                lion_enabled = lion_settings.enabled if lion_settings else True
                lion_timeout = lion_settings.timeout_seconds if lion_settings else 10.0
                lion_headless = lion_settings.headless if lion_settings else True

                self.register_adapter(
                    vendor_id=LionVendorAdapter.VENDOR_ID,
                    adapter_class=LionVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=LionVendorAdapter.VENDOR_ID,
                        base_url=LionVendorAdapter.BASE_URL,
                        headless=lion_headless,
                        timeout_seconds=lion_timeout,
                    ),
                    domains=["lionelectronic.ir"],
                    display_name="Lion Electronic",
                    description="Lion Electronic Component Distributor",
                    enabled=lion_enabled,
                    settings=lion_settings,
                )

            # 2. Javan Electronic
            if JavanVendorAdapter is not None and not self.has_vendor(JavanVendorAdapter.VENDOR_ID):
                javan_settings = settings_mgr.get_vendor_settings(JavanVendorAdapter.VENDOR_ID) if settings_mgr else None
                javan_enabled = javan_settings.enabled if javan_settings else True
                javan_timeout = javan_settings.timeout_seconds if javan_settings else 10.0
                javan_headless = javan_settings.headless if javan_settings else True

                self.register_adapter(
                    vendor_id=JavanVendorAdapter.VENDOR_ID,
                    adapter_class=JavanVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=JavanVendorAdapter.VENDOR_ID,
                        base_url=JavanVendorAdapter.BASE_URL,
                        headless=javan_headless,
                        timeout_seconds=javan_timeout,
                    ),
                    domains=["javanelec.com"],
                    display_name="Javan Electronic",
                    description="Javan Electronic Components & Kits",
                    enabled=javan_enabled,
                    settings=javan_settings,
                )

            # 3. RoboEq Electronic
            if RoboEqVendorAdapter is not None and not self.has_vendor(RoboEqVendorAdapter.VENDOR_ID):
                roboeq_settings = settings_mgr.get_vendor_settings(RoboEqVendorAdapter.VENDOR_ID) if settings_mgr else None
                roboeq_enabled = roboeq_settings.enabled if roboeq_settings else True
                roboeq_timeout = roboeq_settings.timeout_seconds if roboeq_settings else 10.0
                roboeq_headless = roboeq_settings.headless if roboeq_settings else True

                self.register_adapter(
                    vendor_id=RoboEqVendorAdapter.VENDOR_ID,
                    adapter_class=RoboEqVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=RoboEqVendorAdapter.VENDOR_ID,
                        base_url=RoboEqVendorAdapter.BASE_URL,
                        headless=roboeq_headless,
                        timeout_seconds=roboeq_timeout,
                    ),
                    domains=["roboeq.ir"],
                    display_name="RoboEq Electronic",
                    description="RoboEq Marketplace Distributor",
                    enabled=roboeq_enabled,
                    settings=roboeq_settings,
                )

    @staticmethod
    def _normalize_domain(domain_str: str) -> str:
        """Normalize a domain string (lowercase, stripped, remove leading www.)."""
        d = domain_str.strip().lower()
        if d.startswith("http://") or d.startswith("https://"):
            return VendorRegistry._extract_domain_from_url(d)
        if d.startswith("www."):
            d = d[4:]
        # Remove any trailing path/slash
        d = d.split("/")[0].split(":")[0]
        return d

    @staticmethod
    def _extract_domain_from_url(url: str) -> str:
        """Extract and normalize hostname from URL."""
        if not url or not isinstance(url, str):
            return ""
        u = url.strip()
        if not u:
            return ""

        # Check scheme case-insensitively
        u_lower = u.lower()
        if not (u_lower.startswith("http://") or u_lower.startswith("https://") or u_lower.startswith("//")):
            u = "https://" + u

        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.netloc or parsed.path.split("/")[0]
            # Strip port
            host = host.split(":")[0].strip().lower()
            # Strip leading www.
            if host.startswith("www."):
                host = host[4:]
            return host
        except Exception:
            return ""

    @classmethod
    def get_default_registry(cls) -> "VendorRegistry":
        """
        Retrieve the global default singleton registry.

        Per Phase 2.5 and OD-010, the default registry initializes empty (zero registered vendors).
        Vendor plugins must be explicitly registered.
        """
        return default_registry

    @classmethod
    def reset_default_registry(cls) -> "VendorRegistry":
        """
        Reset the default singleton registry to an empty state (primarily for test isolation).
        """
        default_registry.clear()
        return default_registry


# Module-level default singleton registry (starts empty per Phase 2.5 / OD-010)
default_registry = VendorRegistry()


def reset_default_registry() -> VendorRegistry:
    """Convenience helper to clear and return the default singleton registry."""
    return VendorRegistry.reset_default_registry()
