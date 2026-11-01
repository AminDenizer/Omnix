"""
Omnix Vendor Plugin System — Core Plugins Package
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md
"""

from core.plugins.manifest_validator import (
    ManifestValidator,
    ManifestValidationResult,
    ManifestValidationError,
    ManifestError,
    ManifestSyntaxError,
    ManifestSchemaError,
    ManifestSemanticError,
    SemanticVersion,
    validate_manifest,
    validate_manifest_file,
    MAX_MANIFEST_SIZE_BYTES,
)
from core.plugins.manifest_mf import (
    ManifestMF,
    ManifestMFEntry,
    ManifestMFError,
    ManifestMFSyntaxError,
    ManifestMFValidationError,
    ManifestMFSemanticError,
    parse_manifest_mf,
    generate_manifest_mf,
)
from core.plugins.package_inspector import (
    PackageInspectionStatus,
    PackageInspectionError,
    PackageInspectionResult,
    PackageInspectionException,
    PackageInspector,
    inspect_package,
    MAX_COMPRESSED_SIZE_BYTES,
    MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES,
    MAX_SINGLE_ENTRY_UNCOMPRESSED_SIZE_BYTES,
    MAX_COMPRESSION_RATIO,
    COMPRESSION_RATIO_THRESHOLD_BYTES,
    MAX_ARCHIVE_ENTRIES,
    ALLOWED_EXTENSIONS,
)
from core.plugins.trust_engine import (
    TrustEngine,
    TrustStatus,
    TrustVerificationResult,
    TrustVerificationError,
    ED25519_SIGNATURE_LENGTH_BYTES,
    ED25519_PUBLIC_KEY_LENGTH_BYTES,
)
from core.plugins.plugin_store import (
    PluginStore,
    TransactionState,
    InstalledPluginStatus,
    TransactionJournal,
    InstalledVersionRecord,
    InstalledPluginRecord,
)
from core.plugins.plugin_installer import (
    PluginInstaller,
    PluginInstallationResult,
)
from core.plugins.plugin_loader import (
    PluginLoader,
    PluginLoadResult,
)
from core.plugins.plugin_lifecycle_manager import (
    PluginLifecycleManager,
    LifecycleResult,
    LifecycleStatus,
    get_lifecycle_manager,
    restore_installed_plugins,
)

__all__ = [
    "ManifestValidator",
    "ManifestValidationResult",
    "ManifestValidationError",
    "ManifestError",
    "ManifestSyntaxError",
    "ManifestSchemaError",
    "ManifestSemanticError",
    "SemanticVersion",
    "validate_manifest",
    "validate_manifest_file",
    "MAX_MANIFEST_SIZE_BYTES",
    "ManifestMF",
    "ManifestMFEntry",
    "ManifestMFError",
    "ManifestMFSyntaxError",
    "ManifestMFValidationError",
    "ManifestMFSemanticError",
    "parse_manifest_mf",
    "generate_manifest_mf",
    "PackageInspectionStatus",
    "PackageInspectionError",
    "PackageInspectionResult",
    "PackageInspectionException",
    "PackageInspector",
    "inspect_package",
    "MAX_COMPRESSED_SIZE_BYTES",
    "MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES",
    "MAX_SINGLE_ENTRY_UNCOMPRESSED_SIZE_BYTES",
    "MAX_COMPRESSION_RATIO",
    "COMPRESSION_RATIO_THRESHOLD_BYTES",
    "MAX_ARCHIVE_ENTRIES",
    "ALLOWED_EXTENSIONS",
    # Trust Engine
    "TrustEngine",
    "TrustStatus",
    "TrustVerificationResult",
    "TrustVerificationError",
    "ED25519_SIGNATURE_LENGTH_BYTES",
    "ED25519_PUBLIC_KEY_LENGTH_BYTES",
    # Plugin Store
    "PluginStore",
    "TransactionState",
    "InstalledPluginStatus",
    "TransactionJournal",
    "InstalledVersionRecord",
    "InstalledPluginRecord",
    # Plugin Installer
    "PluginInstaller",
    "PluginInstallationResult",
    # Plugin Loader
    "PluginLoader",
    "PluginLoadResult",
    # Plugin Lifecycle Manager
    "PluginLifecycleManager",
    "LifecycleResult",
    "LifecycleStatus",
    "get_lifecycle_manager",
    "restore_installed_plugins",
]

