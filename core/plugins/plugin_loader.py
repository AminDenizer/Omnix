"""
Omnix Vendor Plugin System — Dynamic Plugin Loader (Milestone 1)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10 & 27.2
- Phase 2 Final Architecture Closure & Consistency Gate Specifications

Implements isolated runtime dynamic loading for verified, installed plugins:
1. Loads exclusively from permanent, indexed installation directories in data/plugins/installed/.
2. Refuses to load unindexed, missing, or corrupted directories.
3. Injects modules into an isolated synthetic namespace (omnix_plugins.pkg_<vendor_id>_v<version>).
4. Establishes proper __package__ and __path__ attributes so package-relative imports function seamlessly.
5. NEVER modifies sys.path globally.
6. Performs runtime reflection checks confirming entry-point class inherits from IVendorAdapter.
7. Traps all syntax, import, and initialization errors, returning structured load results
   without crashing the host application or registering broken adapters.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from core.plugins.plugin_store import (
    InstalledPluginRecord,
    InstalledPluginStatus,
    InstalledVersionRecord,
    PluginStore,
)
from core.vendor_interface import IVendorAdapter


@dataclass
class PluginLoadResult:
    """Outcome of loading an installed vendor adapter class."""
    success: bool
    status: str
    vendor_id: str
    version: Optional[str] = None
    adapter_class: Optional[Type[IVendorAdapter]] = None
    error_message: Optional[str] = None
    entry_point: Optional[str] = None
    install_path: Optional[str] = None
    manifest: Optional[Dict[str, Any]] = None
    synthetic_namespace: Optional[str] = None


class PluginLoader:
    """
    Dynamically loads vendor adapter classes from authoritative installation paths
    into isolated synthetic namespaces without sys.path manipulation.
    """

    def __init__(self, store: Optional[PluginStore] = None):
        self.store = store or PluginStore()

    @staticmethod
    def _sanitize_namespace_part(part: str) -> str:
        """Sanitize vendor_id or version string into valid Python identifier."""
        return re.sub(r"[^a-zA-Z0-9_]", "_", part).strip("_")

    def load_adapter(
        self,
        vendor_id: str,
        version: Optional[str] = None,
    ) -> PluginLoadResult:
        """
        Load the adapter class for a vendor from its permanent, authoritative installation.

        Args:
            vendor_id: Canonical vendor identifier (e.g. 'vendor_lion').
            version: Optional SemVer string. If omitted, uses active_version.

        Returns:
            PluginLoadResult with loaded adapter class or structured error.
        """
        clean_vid = str(vendor_id).strip()

        # Step 1: Check authoritative store index
        plugin_rec = self.store.get_plugin(clean_vid)
        if plugin_rec is None:
            return PluginLoadResult(
                success=False,
                status="UNINDEXED_PLUGIN",
                vendor_id=clean_vid,
                error_message=f"Vendor '{clean_vid}' is not recorded in the installed plugins index",
            )

        target_ver = version or plugin_rec.active_version
        if not target_ver or target_ver not in plugin_rec.installed_versions:
            return PluginLoadResult(
                success=False,
                status="VERSION_NOT_FOUND",
                vendor_id=clean_vid,
                version=target_ver,
                error_message=f"Version '{target_ver}' for vendor '{clean_vid}' is not recorded as installed",
            )

        ver_rec = plugin_rec.installed_versions[target_ver]
        install_dir = Path(ver_rec.install_path).resolve()
        is_active = (plugin_rec.active_version == target_ver)

        # Step 2: Validate permanent expected installation path
        expected_path = (self.store.installed_root / clean_vid / target_ver).resolve()
        if install_dir != expected_path:
            ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
            ver_rec.error_message = (
                f"Installation path '{install_dir}' does not match expected permanent path '{expected_path}'"
            )
            self.store.record_installed_version(
                vendor_id=clean_vid,
                plugin_id=plugin_rec.plugin_id,
                display_name=plugin_rec.display_name,
                version_record=ver_rec,
                set_active=is_active,
            )
            return PluginLoadResult(
                success=False,
                status="TAMPERED_FILES_DETECTED",
                vendor_id=clean_vid,
                version=target_ver,
                install_path=str(install_dir),
                error_message=ver_rec.error_message,
            )

        # Step 3: Validate physical directory existence
        if not install_dir.is_dir() or not (install_dir / "manifest.json").is_file():
            ver_rec.status = InstalledPluginStatus.CORRUPTED_MISSING_FILES
            ver_rec.error_message = f"Installation directory '{install_dir}' is missing or corrupted on disk"
            self.store.record_installed_version(
                vendor_id=clean_vid,
                plugin_id=plugin_rec.plugin_id,
                display_name=plugin_rec.display_name,
                version_record=ver_rec,
                set_active=is_active,
            )
            return PluginLoadResult(
                success=False,
                status="CORRUPTED_MISSING_FILES",
                vendor_id=clean_vid,
                version=target_ver,
                install_path=str(install_dir),
                error_message=ver_rec.error_message,
            )

        # Step 4: Validate installed manifest.json identity
        try:
            with open(install_dir / "manifest.json", "r", encoding="utf-8") as f:
                disk_manifest = json.load(f)
        except Exception as exc:
            ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
            ver_rec.error_message = f"Installed manifest.json is unreadable or corrupted: {exc}"
            self.store.record_installed_version(
                vendor_id=clean_vid,
                plugin_id=plugin_rec.plugin_id,
                display_name=plugin_rec.display_name,
                version_record=ver_rec,
                set_active=is_active,
            )
            return PluginLoadResult(
                success=False,
                status="TAMPERED_FILES_DETECTED",
                vendor_id=clean_vid,
                version=target_ver,
                install_path=str(install_dir),
                error_message=ver_rec.error_message,
            )

        if (
            disk_manifest.get("vendor_id") != clean_vid
            or disk_manifest.get("plugin_id") != plugin_rec.plugin_id
            or disk_manifest.get("version") != target_ver
        ):
            ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
            ver_rec.error_message = (
                f"Installed manifest identity mismatch: declares vendor={disk_manifest.get('vendor_id')}, "
                f"plugin={disk_manifest.get('plugin_id')}, version={disk_manifest.get('version')}; "
                f"expected {clean_vid}, {plugin_rec.plugin_id}, {target_ver}"
            )
            self.store.record_installed_version(
                vendor_id=clean_vid,
                plugin_id=plugin_rec.plugin_id,
                display_name=plugin_rec.display_name,
                version_record=ver_rec,
                set_active=is_active,
            )
            return PluginLoadResult(
                success=False,
                status="TAMPERED_FILES_DETECTED",
                vendor_id=clean_vid,
                version=target_ver,
                install_path=str(install_dir),
                error_message=ver_rec.error_message,
            )

        # Step 5: Authenticated Expected Per-File Digest Verification
        # Expected digests originate from authenticated installation metadata in installed_plugins.json.
        expected_digests = ver_rec.file_digests
        if not expected_digests:
            # Fallback for backward-compatibility if stored in manifest metadata
            if ver_rec.manifest and "_file_digests" in ver_rec.manifest:
                expected_digests = ver_rec.manifest["_file_digests"]
            else:
                ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
                ver_rec.error_message = "Installation record lacks authenticated file digest metadata; failing closed"
                self.store.record_installed_version(
                    vendor_id=clean_vid,
                    plugin_id=plugin_rec.plugin_id,
                    display_name=plugin_rec.display_name,
                    version_record=ver_rec,
                    set_active=is_active,
                )
                return PluginLoadResult(
                    success=False,
                    status="TAMPERED_FILES_DETECTED",
                    vendor_id=clean_vid,
                    version=target_ver,
                    install_path=str(install_dir),
                    error_message=ver_rec.error_message,
                )

        for rel_path, expected_hash in expected_digests.items():
            norm_rel = rel_path.replace("\\", "/")
            disk_file = (install_dir / norm_rel).resolve()

            # Ensure disk_file does not escape install_dir
            if not str(disk_file).startswith(str(install_dir)):
                ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
                ver_rec.error_message = f"File path '{norm_rel}' escapes installation directory boundary"
                self.store.record_installed_version(
                    vendor_id=clean_vid,
                    plugin_id=plugin_rec.plugin_id,
                    display_name=plugin_rec.display_name,
                    version_record=ver_rec,
                    set_active=is_active,
                )
                return PluginLoadResult(
                    success=False,
                    status="TAMPERED_FILES_DETECTED",
                    vendor_id=clean_vid,
                    version=target_ver,
                    install_path=str(install_dir),
                    error_message=ver_rec.error_message,
                )

            # Check existence
            if not disk_file.is_file():
                ver_rec.status = InstalledPluginStatus.CORRUPTED_MISSING_FILES
                ver_rec.error_message = f"Required installed file '{norm_rel}' is missing from disk"
                self.store.record_installed_version(
                    vendor_id=clean_vid,
                    plugin_id=plugin_rec.plugin_id,
                    display_name=plugin_rec.display_name,
                    version_record=ver_rec,
                    set_active=is_active,
                )
                return PluginLoadResult(
                    success=False,
                    status="CORRUPTED_MISSING_FILES",
                    vendor_id=clean_vid,
                    version=target_ver,
                    install_path=str(install_dir),
                    error_message=ver_rec.error_message,
                )

            # Recalculate SHA-256 digest
            try:
                with open(disk_file, "rb") as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest().lower()
                if actual_hash != expected_hash.lower():
                    ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
                    ver_rec.error_message = (
                        f"Digest mismatch for installed file '{norm_rel}': "
                        f"expected {expected_hash.lower()}, got {actual_hash}"
                    )
                    self.store.record_installed_version(
                        vendor_id=clean_vid,
                        plugin_id=plugin_rec.plugin_id,
                        display_name=plugin_rec.display_name,
                        version_record=ver_rec,
                        set_active=is_active,
                    )
                    return PluginLoadResult(
                        success=False,
                        status="TAMPERED_FILES_DETECTED",
                        vendor_id=clean_vid,
                        version=target_ver,
                        install_path=str(install_dir),
                        entry_point=ver_rec.entry_point,
                        error_message=ver_rec.error_message,
                        manifest=ver_rec.manifest,
                    )
            except Exception as exc:
                ver_rec.status = InstalledPluginStatus.TAMPERED_FILES_DETECTED
                ver_rec.error_message = f"Error reading installed file '{norm_rel}' for digest check: {exc}"
                self.store.record_installed_version(
                    vendor_id=clean_vid,
                    plugin_id=plugin_rec.plugin_id,
                    display_name=plugin_rec.display_name,
                    version_record=ver_rec,
                    set_active=is_active,
                )
                return PluginLoadResult(
                    success=False,
                    status="TAMPERED_FILES_DETECTED",
                    vendor_id=clean_vid,
                    version=target_ver,
                    install_path=str(install_dir),
                    error_message=ver_rec.error_message,
                )

        # Step 6: Validate entry_point declaration and locate physical entry file
        entry_point = ver_rec.entry_point
        if not entry_point or ":" not in entry_point:
            return PluginLoadResult(
                success=False,
                status="INVALID_ENTRY_POINT",
                vendor_id=clean_vid,
                version=target_ver,
                install_path=str(install_dir),
                entry_point=entry_point,
                error_message=f"Malformed entry_point '{entry_point}'; must be in 'module.path:ClassName' format",
            )

        module_path_str, class_name = [s.strip() for s in entry_point.split(":", 1)]

        # Convert dotted module path to file path
        rel_as_path = Path(*module_path_str.split("."))
        candidate_file = install_dir / f"{rel_as_path}.py"
        candidate_pkg = install_dir / rel_as_path / "__init__.py"

        if candidate_file.is_file():
            entry_py_file = candidate_file
        elif candidate_pkg.is_file():
            entry_py_file = candidate_pkg
        else:
            first_part = module_path_str.split(".")[0]
            rest_parts = module_path_str.split(".")[1:]
            inner_candidate = install_dir / Path(*rest_parts).with_suffix(".py") if rest_parts else None
            if inner_candidate and inner_candidate.is_file():
                entry_py_file = inner_candidate
            else:
                ver_rec.status = InstalledPluginStatus.CORRUPTED_MISSING_FILES
                ver_rec.error_message = f"Entry-point file '{module_path_str}.py' does not exist in '{install_dir}'"
                self.store.record_installed_version(
                    vendor_id=clean_vid,
                    plugin_id=plugin_rec.plugin_id,
                    display_name=plugin_rec.display_name,
                    version_record=ver_rec,
                    set_active=is_active,
                )
                return PluginLoadResult(
                    success=False,
                    status="CORRUPTED_MISSING_FILES",
                    vendor_id=clean_vid,
                    version=target_ver,
                    install_path=str(install_dir),
                    entry_point=entry_point,
                    error_message=ver_rec.error_message,
                )

        # Step 4: Synthetic Namespace Construction
        safe_vid = self._sanitize_namespace_part(clean_vid)
        safe_ver = self._sanitize_namespace_part(target_ver)
        synthetic_root_name = f"omnix_plugins.pkg_{safe_vid}_v{safe_ver}"

        # Determine package root folder inside install_dir
        # If entry_py_file is inside a package subfolder (e.g. install_dir / 'lion' / 'adapter.py'),
        # the package dir is that subfolder. Otherwise it is install_dir.
        package_subparts = module_path_str.split(".")[:-1]
        if package_subparts:
            package_dir = install_dir / Path(*package_subparts)
            if not package_dir.is_dir():
                package_dir = install_dir
        else:
            package_dir = install_dir

        try:
            # Ensure top-level 'omnix_plugins' pseudo-package exists in sys.modules
            if "omnix_plugins" not in sys.modules:
                root_pkg = types.ModuleType("omnix_plugins")
                root_pkg.__path__ = []  # namespace package
                sys.modules["omnix_plugins"] = root_pkg

            # Create or update synthetic root package module
            if synthetic_root_name not in sys.modules:
                pkg_mod = types.ModuleType(synthetic_root_name)
                pkg_mod.__path__ = [str(package_dir.resolve())]
                pkg_mod.__package__ = synthetic_root_name
                sys.modules[synthetic_root_name] = pkg_mod
            else:
                pkg_mod = sys.modules[synthetic_root_name]
                pkg_mod.__path__ = [str(package_dir.resolve())]
                pkg_mod.__package__ = synthetic_root_name

            # Target module full synthetic name
            leaf_mod_name = module_path_str.split(".")[-1]
            full_module_name = f"{synthetic_root_name}.{leaf_mod_name}"

            # Step 5: Load module using importlib
            spec = importlib.util.spec_from_file_location(
                full_module_name,
                str(entry_py_file.resolve()),
                submodule_search_locations=[str(package_dir.resolve())],
            )

            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to create importlib spec for '{entry_py_file}'")

            module = importlib.util.module_from_spec(spec)
            sys.modules[full_module_name] = module

            # Execute module in its isolated namespace
            spec.loader.exec_module(module)

            # Step 6: Runtime Contract Validation
            if not hasattr(module, class_name):
                raise AttributeError(
                    f"Entry-point module '{module_path_str}' does not export class '{class_name}'"
                )

            cls_obj = getattr(module, class_name)
            if not isinstance(cls_obj, type):
                raise TypeError(f"Exported symbol '{class_name}' is not a class")

            if not issubclass(cls_obj, IVendorAdapter):
                raise TypeError(
                    f"Class '{class_name}' does not inherit from IVendorAdapter. "
                    "All vendor plugin adapters must subclass IVendorAdapter."
                )

            # Verify all abstract methods from IVendorAdapter are implemented
            abstract_methods = getattr(cls_obj, "__abstractmethods__", None)
            if abstract_methods:
                unimplemented = sorted(list(abstract_methods))
                raise TypeError(
                    f"Adapter class '{class_name}' does not implement mandatory IVendorAdapter operations: {unimplemented}"
                )

            # Successfully loaded and validated
            return PluginLoadResult(
                success=True,
                status="SUCCESS",
                vendor_id=clean_vid,
                version=target_ver,
                adapter_class=cls_obj,
                entry_point=entry_point,
                install_path=str(install_dir),
                manifest=ver_rec.manifest,
                synthetic_namespace=full_module_name,
            )

        except Exception as exc:
            err_msg = str(exc)
            ver_rec.status = InstalledPluginStatus.LOAD_FAILED
            ver_rec.error_message = err_msg
            self.store.record_installed_version(
                vendor_id=clean_vid,
                plugin_id=plugin_rec.plugin_id,
                display_name=plugin_rec.display_name,
                version_record=ver_rec,
                set_active=is_active,
            )
            return PluginLoadResult(
                success=False,
                status="LOAD_FAILED",
                vendor_id=clean_vid,
                version=target_ver,
                entry_point=entry_point,
                install_path=str(install_dir),
                error_message=f"Failed to load adapter class '{class_name}': {err_msg}",
                manifest=ver_rec.manifest,
            )
