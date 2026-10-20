"""
Omnix Vendor Plugin System — Manifest Validator
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 5

Provides strict, deterministic JSON parsing, schema validation, and semantic validation
for plugin manifest.json documents without executing, importing, or extracting plugin code.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import jsonschema
from jsonschema.validators import Draft202012Validator


# ---------------------------------------------------------------------------
# Constants & Defaults
# ---------------------------------------------------------------------------

# Conservative limit on raw manifest size to protect host memory against abuse.
# The manifest is a metadata descriptor; genuine manifests are < 10 KB.
MAX_MANIFEST_SIZE_BYTES: int = 256 * 1024  # 256 KB

DEFAULT_SCHEMA_PATH = Path(__file__).parent / "manifest.schema.json"

SEMVER_REGEX = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

PLUGIN_ID_REGEX = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
VENDOR_ID_REGEX = re.compile(r"^vendor_[a-z0-9_]+$")
ENTRY_POINT_REGEX = re.compile(r"^[a-zA-Z0-9_.]+(?:\.[a-zA-Z0-9_]+)*:[a-zA-Z0-9_]+$")

CANONICAL_CAPABILITIES = frozenset({
    "PRODUCT_URL_RECOGNITION",
    "PRODUCT_INSPECTION",
    "CART_URL_RESOLUTION",
    "MPN_SEARCH",
    "LIVE_STOCK_PROBE",
    "TIERED_PRICING",
    "MODE_A_STAGING",
    "MODE_B_STAGING",
})

CANONICAL_MODES = frozenset({"MODE_A", "MODE_B"})
CANONICAL_PUBLISHER_TYPES = frozenset({"OFFICIAL", "THIRD_PARTY_VERIFIED", "COMMUNITY"})


# ---------------------------------------------------------------------------
# Structured Errors & Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ManifestValidationError:
    """Represents a single structured validation failure."""
    code: str
    message: str
    path: str = ""
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        loc = f" at '{self.path}'" if self.path else ""
        return f"[{self.code}]{loc} {self.message}"


@dataclass
class ManifestValidationResult:
    """The complete result of manifest parsing and validation."""
    is_valid: bool
    manifest: Optional[Dict[str, Any]] = None
    errors: List[ManifestValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def raise_for_errors(self) -> None:
        """Raise ManifestException if the manifest is invalid."""
        if not self.is_valid:
            if not self.errors:
                raise ManifestSemanticError("Validation failed with unspecified error")
            primary = self.errors[0]
            if primary.code.startswith("JSON_"):
                raise ManifestSyntaxError(primary.message, errors=self.errors)
            elif primary.code == "SCHEMA_VIOLATION":
                raise ManifestSchemaError(primary.message, errors=self.errors)
            else:
                raise ManifestSemanticError(primary.message, errors=self.errors)


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class ManifestError(Exception):
    """Base exception for all manifest validation errors."""
    def __init__(self, message: str, errors: Optional[List[ManifestValidationError]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class ManifestSyntaxError(ManifestError):
    """Raised on malformed JSON, duplicate keys, or invalid JSON constants."""
    pass


class ManifestSchemaError(ManifestError):
    """Raised when manifest fails structural JSON Schema validation."""
    pass


class ManifestSemanticError(ManifestError):
    """Raised when manifest fails domain semantic rules."""
    pass


# ---------------------------------------------------------------------------
# Standards-Compliant SemVer 2.0.0 Parser & Comparator
# ---------------------------------------------------------------------------

class SemanticVersion:
    """
    Self-contained, strict SemVer 2.0.0 parser and comparator.
    Enforces specification rules for precedence, numeric vs alphanumeric identifiers.
    """

    def __init__(self, version_str: str):
        match = SEMVER_REGEX.match(version_str)
        if not match:
            raise ValueError(f"Invalid SemVer 2.0.0 string: '{version_str}'")

        self.raw = version_str
        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3))
        self.prerelease = match.group(4)
        self.build = match.group(5)

        self._prerelease_parts: Tuple[Union[int, str], ...] = ()
        if self.prerelease:
            parts: List[Union[int, str]] = []
            for part in self.prerelease.split("."):
                if part.isdigit():
                    parts.append(int(part))
                else:
                    parts.append(part)
            self._prerelease_parts = tuple(parts)

    def __repr__(self) -> str:
        return f"SemanticVersion('{self.raw}')"

    def __str__(self) -> str:
        return self.raw

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, SemanticVersion):
            try:
                other = SemanticVersion(str(other))
            except Exception:
                return False
        return (
            (self.major, self.minor, self.patch, self._prerelease_parts)
            == (other.major, other.minor, other.patch, other._prerelease_parts)
        )

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, SemanticVersion):
            other = SemanticVersion(str(other))

        # 1. Compare major, minor, patch numerically
        self_core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if self_core != other_core:
            return self_core < other_core

        # 2. When major, minor, and patch are equal, a pre-release version has lower precedence
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        if not self.prerelease and not other.prerelease:
            return False

        # 3. Both have prerelease; compare left-to-right identifiers
        for a, b in zip(self._prerelease_parts, other._prerelease_parts):
            if a == b:
                continue
            # Numeric identifiers always have lower precedence than alphanumeric
            if isinstance(a, int) and isinstance(b, int):
                return a < b
            if isinstance(a, int) and isinstance(b, str):
                return True
            if isinstance(a, str) and isinstance(b, int):
                return False
            if isinstance(a, str) and isinstance(b, str):
                return a < b

        # A larger set of pre-release fields has a higher precedence than a smaller set
        return len(self._prerelease_parts) < len(other._prerelease_parts)

    def __le__(self, other: Any) -> bool:
        return self < other or self == other

    def __gt__(self, other: Any) -> bool:
        return not (self <= other)

    def __ge__(self, other: Any) -> bool:
        return not (self < other)


# ---------------------------------------------------------------------------
# Strict JSON Decoder Hooks
# ---------------------------------------------------------------------------

def _strict_pairs_hook(pairs: List[Tuple[Any, Any]]) -> Dict[str, Any]:
    """Rejects duplicate keys at any nesting level."""
    res: Dict[str, Any] = {}
    for key, value in pairs:
        if key in res:
            raise ManifestSyntaxError(
                f"Duplicate JSON key rejected: '{key}'",
                errors=[ManifestValidationError(
                    code="JSON_DUPLICATE_KEY",
                    message=f"Duplicate object key '{key}' found in JSON manifest",
                    path=str(key)
                )]
            )
        res[key] = value
    return res


def _strict_constant_hook(constant: str) -> None:
    """Rejects non-standard JSON numeric constants like NaN, Infinity, -Infinity."""
    raise ManifestSyntaxError(
        f"Non-standard JSON constant rejected: '{constant}'",
        errors=[ManifestValidationError(
            code="JSON_INVALID_CONSTANT",
            message=f"Non-standard JSON constant '{constant}' is strictly prohibited",
            details={"constant": constant}
        )]
    )


# ---------------------------------------------------------------------------
# Main Manifest Validator
# ---------------------------------------------------------------------------

class ManifestValidator:
    """
    Validates Omnix vendor plugin manifest.json archives.

    Responsibilities:
    - Safe, size-bounded strict JSON parsing with duplicate-key rejection.
    - JSON Schema Draft 2020-12 structural validation.
    - Deep domain semantic checks (SemVer 2.0.0, path safety, capabilities, routes).

    Guarantees:
    - Zero code execution / zero plugin module imports.
    - Zero network access.
    - Zero filesystem mutation or archive extraction.
    """

    def __init__(self, schema_path: Optional[Union[str, Path]] = None):
        self.schema_path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
        self._schema_data: Optional[Dict[str, Any]] = None
        self._validator: Optional[Draft202012Validator] = None

    @property
    def schema(self) -> Dict[str, Any]:
        """Lazy-loaded JSON Schema dictionary."""
        if self._schema_data is None:
            if not self.schema_path.is_file():
                raise FileNotFoundError(f"Manifest schema not found at: {self.schema_path}")
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema_data = json.load(f)
        return self._schema_data

    @property
    def validator(self) -> Draft202012Validator:
        """Compiled jsonschema validator."""
        if self._validator is None:
            Draft202012Validator.check_schema(self.schema)
            self._validator = Draft202012Validator(self.schema)
        return self._validator

    def parse_strict(self, raw_input: Union[str, bytes]) -> Dict[str, Any]:
        """
        Parses raw JSON manifest with strict bounds and security rejection:
        - Rejects input exceeding MAX_MANIFEST_SIZE_BYTES.
        - Rejects empty or whitespace-only input.
        - Rejects duplicate object keys at any nesting level.
        - Rejects NaN, Infinity, -Infinity.
        """
        if not isinstance(raw_input, (str, bytes)):
            raise ManifestSyntaxError(
                f"Unsupported input type '{type(raw_input).__name__}'; expected str or bytes",
                errors=[ManifestValidationError(
                    code="JSON_INVALID_TYPE",
                    message=f"Input must be str or bytes, got {type(raw_input).__name__}"
                )]
            )

        # 1. Size-bound guard
        byte_len = len(raw_input.encode("utf-8") if isinstance(raw_input, str) else raw_input)
        if byte_len > MAX_MANIFEST_SIZE_BYTES:
            raise ManifestSyntaxError(
                f"Manifest size ({byte_len} bytes) exceeds maximum limit ({MAX_MANIFEST_SIZE_BYTES} bytes)",
                errors=[ManifestValidationError(
                    code="JSON_OVERSIZED",
                    message=f"Manifest input exceeds {MAX_MANIFEST_SIZE_BYTES} bytes limit",
                    details={"size_bytes": byte_len, "max_bytes": MAX_MANIFEST_SIZE_BYTES}
                )]
            )

        # 2. Empty / whitespace check
        text = raw_input.decode("utf-8") if isinstance(raw_input, bytes) else raw_input
        if not text.strip():
            raise ManifestSyntaxError(
                "Manifest input is empty or whitespace-only",
                errors=[ManifestValidationError(
                    code="JSON_EMPTY_INPUT",
                    message="Manifest input string is empty or contains only whitespace"
                )]
            )

        # 3. Strict JSON parse
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_strict_pairs_hook,
                parse_constant=_strict_constant_hook,
            )
        except json.JSONDecodeError as exc:
            raise ManifestSyntaxError(
                f"Malformed JSON syntax: {exc.msg} (line {exc.lineno}, col {exc.colno})",
                errors=[ManifestValidationError(
                    code="JSON_PARSE_ERROR",
                    message=str(exc),
                    details={"lineno": exc.lineno, "colno": exc.colno, "pos": exc.pos}
                )]
            ) from exc

        if not isinstance(parsed, dict):
            raise ManifestSyntaxError(
                f"Manifest root must be a JSON object, found '{type(parsed).__name__}'",
                errors=[ManifestValidationError(
                    code="JSON_INVALID_ROOT",
                    message=f"Root element must be an object, got {type(parsed).__name__}"
                )]
            )

        return parsed

    def validate_file(
        self,
        file_path: Union[str, Path],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> ManifestValidationResult:
        """Validates a manifest file located on disk."""
        path = Path(file_path)
        if not path.is_file():
            return ManifestValidationResult(
                is_valid=False,
                errors=[ManifestValidationError(
                    code="FILE_NOT_FOUND",
                    message=f"Manifest file not found: {path}"
                )]
            )
        try:
            with open(path, "rb") as f:
                content = f.read()
            return self.validate_content(
                content,
                host_omnix_version=host_omnix_version,
                host_contract_version=host_contract_version,
            )
        except Exception as exc:
            return ManifestValidationResult(
                is_valid=False,
                errors=[ManifestValidationError(
                    code="FILE_READ_ERROR",
                    message=f"Failed to read manifest file: {exc}"
                )]
            )

    def validate_content(
        self,
        raw_input: Union[str, bytes],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> ManifestValidationResult:
        """Parses and validates raw manifest content string or bytes."""
        try:
            manifest_dict = self.parse_strict(raw_input)
        except ManifestError as exc:
            return ManifestValidationResult(is_valid=False, errors=exc.errors)
        except Exception as exc:
            return ManifestValidationResult(
                is_valid=False,
                errors=[ManifestValidationError(
                    code="JSON_UNEXPECTED_ERROR",
                    message=f"Unexpected parsing failure: {exc}"
                )]
            )

        return self.validate_dict(
            manifest_dict,
            host_omnix_version=host_omnix_version,
            host_contract_version=host_contract_version,
        )

    def validate_dict(
        self,
        manifest_dict: Dict[str, Any],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> ManifestValidationResult:
        """
        Validates an already-parsed manifest dictionary against schema and semantic rules.
        """
        errors: List[ManifestValidationError] = []
        warnings: List[str] = []

        if not isinstance(manifest_dict, dict):
            errors.append(ManifestValidationError(
                code="SCHEMA_INVALID_TYPE",
                message=f"Manifest root must be a dict, got {type(manifest_dict).__name__}"
            ))
            return ManifestValidationResult(is_valid=False, errors=errors)

        # -------------------------------------------------------------------
        # Step 1: JSON Schema Structural Validation
        # -------------------------------------------------------------------
        schema_errors = list(self.validator.iter_errors(manifest_dict))
        for err in schema_errors:
            # Construct human-friendly path e.g. "routes.domains[0]"
            path_parts = []
            for elem in err.path:
                if isinstance(elem, int):
                    path_parts.append(f"[{elem}]")
                else:
                    if path_parts and not path_parts[-1].endswith("]"):
                        path_parts.append(f".{elem}")
                    else:
                        path_parts.append(str(elem))
            loc = "".join(path_parts) if path_parts else "root"
            errors.append(ManifestValidationError(
                code="SCHEMA_VIOLATION",
                message=err.message,
                path=loc,
                details={"validator": err.validator, "validator_value": str(err.validator_value)[:100]}
            ))

        # If fundamental schema validation failed, abort deep semantic checks to avoid type errors
        if errors:
            return ManifestValidationResult(is_valid=False, manifest=manifest_dict, errors=errors)

        # -------------------------------------------------------------------
        # Step 2: Semantic Identifiers Validation
        # -------------------------------------------------------------------
        plugin_id = manifest_dict.get("plugin_id", "")
        if not PLUGIN_ID_REGEX.match(plugin_id):
            errors.append(ManifestValidationError(
                code="SEMANTIC_INVALID_IDENTIFIER",
                message=f"plugin_id '{plugin_id}' must follow reverse-DNS convention (e.g. 'com.omnix.vendor.lion')",
                path="plugin_id"
            ))

        vendor_id = manifest_dict.get("vendor_id", "")
        if not VENDOR_ID_REGEX.match(vendor_id):
            errors.append(ManifestValidationError(
                code="SEMANTIC_INVALID_IDENTIFIER",
                message=f"vendor_id '{vendor_id}' must start with 'vendor_' and contain only lowercase alphanumeric and underscore",
                path="vendor_id"
            ))

        # -------------------------------------------------------------------
        # Step 3: Semantic Versioning (SemVer 2.0.0)
        # -------------------------------------------------------------------
        semver_fields = ["version", "min_omnix_version", "omnix_contract_version"]
        parsed_versions: Dict[str, SemanticVersion] = {}
        for vf in semver_fields:
            val = manifest_dict.get(vf)
            if val is not None:
                try:
                    parsed_versions[vf] = SemanticVersion(str(val))
                except ValueError as exc:
                    errors.append(ManifestValidationError(
                        code="SEMANTIC_INVALID_SEMVER",
                        message=f"{vf} '{val}' is not a valid SemVer 2.0.0 string: {exc}",
                        path=vf
                    ))

        # Check max_omnix_version (optional / nullable)
        max_omnix_str = manifest_dict.get("max_omnix_version")
        if max_omnix_str is not None:
            try:
                parsed_max = SemanticVersion(str(max_omnix_str))
                parsed_versions["max_omnix_version"] = parsed_max
                # Check range consistency: max >= min
                if "min_omnix_version" in parsed_versions:
                    if parsed_max < parsed_versions["min_omnix_version"]:
                        errors.append(ManifestValidationError(
                            code="SEMANTIC_VERSION_RANGE_INVALID",
                            message=f"max_omnix_version '{max_omnix_str}' cannot be lower than min_omnix_version '{manifest_dict.get('min_omnix_version')}'",
                            path="max_omnix_version"
                        ))
            except ValueError as exc:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_SEMVER",
                    message=f"max_omnix_version '{max_omnix_str}' is not a valid SemVer 2.0.0 string: {exc}",
                    path="max_omnix_version"
                ))

        # Optional host runtime compatibility check
        if host_omnix_version:
            try:
                host_semver = SemanticVersion(host_omnix_version)
                if "min_omnix_version" in parsed_versions and host_semver < parsed_versions["min_omnix_version"]:
                    errors.append(ManifestValidationError(
                        code="COMPATIBILITY_HOST_TOO_OLD",
                        message=f"Host Omnix version '{host_omnix_version}' is below minimum required '{manifest_dict.get('min_omnix_version')}'",
                        path="min_omnix_version"
                    ))
                if "max_omnix_version" in parsed_versions and host_semver > parsed_versions["max_omnix_version"]:
                    errors.append(ManifestValidationError(
                        code="COMPATIBILITY_HOST_TOO_NEW",
                        message=f"Host Omnix version '{host_omnix_version}' exceeds maximum compatible '{max_omnix_str}'",
                        path="max_omnix_version"
                    ))
            except ValueError:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_HOST_VERSION",
                    message=f"Provided host_omnix_version '{host_omnix_version}' is not valid SemVer",
                    path="host_omnix_version"
                ))

        if host_contract_version:
            try:
                host_contract_semver = SemanticVersion(host_contract_version)
                if "omnix_contract_version" in parsed_versions:
                    if parsed_versions["omnix_contract_version"].major != host_contract_semver.major:
                        errors.append(ManifestValidationError(
                            code="COMPATIBILITY_CONTRACT_MISMATCH",
                            message=f"Plugin contract major version ({parsed_versions['omnix_contract_version'].major}) does not match host contract major ({host_contract_semver.major})",
                            path="omnix_contract_version"
                        ))
            except ValueError:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_HOST_CONTRACT",
                    message=f"Provided host_contract_version '{host_contract_version}' is not valid SemVer",
                    path="host_contract_version"
                ))

        # -------------------------------------------------------------------
        # Step 4: Entry-Point Path & Module Safety
        # -------------------------------------------------------------------
        entry_point = manifest_dict.get("entry_point", "")
        if not ENTRY_POINT_REGEX.match(entry_point):
            errors.append(ManifestValidationError(
                code="SEMANTIC_INVALID_ENTRY_POINT",
                message=f"entry_point '{entry_point}' must follow 'module.path:ClassName' format",
                path="entry_point"
            ))
        else:
            # Deep path traversal and forbidden syntax inspection
            if ".." in entry_point or "/" in entry_point or "\\" in entry_point or "\0" in entry_point:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_UNSAFE_ENTRY_POINT",
                    message=f"entry_point contains prohibited path characters: '{entry_point}'",
                    path="entry_point"
                ))

        # -------------------------------------------------------------------
        # Step 5: Capabilities and Supported Modes
        # -------------------------------------------------------------------
        capabilities = manifest_dict.get("capabilities", [])
        supported_modes = manifest_dict.get("supported_modes", [])

        # Check capabilities validity
        for cap in capabilities:
            if cap not in CANONICAL_CAPABILITIES:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_CAPABILITY",
                    message=f"Unrecognized capability declared: '{cap}'",
                    path="capabilities"
                ))

        # Check supported modes validity
        for mode in supported_modes:
            if mode not in CANONICAL_MODES:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_MODE",
                    message=f"Unrecognized procurement mode: '{mode}'",
                    path="supported_modes"
                ))

        # Mode and Capability Coherence
        if "MODE_A_STAGING" in capabilities and "MODE_A" not in supported_modes:
            errors.append(ManifestValidationError(
                code="SEMANTIC_MODE_CAPABILITY_MISMATCH",
                message="Capability 'MODE_A_STAGING' declared but 'MODE_A' is absent from supported_modes",
                path="supported_modes"
            ))
        if "MODE_B_STAGING" in capabilities and "MODE_B" not in supported_modes:
            errors.append(ManifestValidationError(
                code="SEMANTIC_MODE_CAPABILITY_MISMATCH",
                message="Capability 'MODE_B_STAGING' declared but 'MODE_B' is absent from supported_modes",
                path="supported_modes"
            ))

        # -------------------------------------------------------------------
        # Step 6: Routes & Storefront Verification
        # -------------------------------------------------------------------
        routes = manifest_dict.get("routes", {})
        base_url = routes.get("base_url", "")
        cart_url = routes.get("cart_url", "")
        domains = routes.get("domains", [])
        pdp_patterns = routes.get("pdp_patterns", [])

        # Validate URL schemes
        for url_name, url_val in [("base_url", base_url), ("cart_url", cart_url)]:
            parsed_u = urlparse(url_val)
            if parsed_u.scheme not in ("http", "https") or not parsed_u.netloc:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_URL",
                    message=f"routes.{url_name} must be a valid absolute HTTP/HTTPS URL, got '{url_val}'",
                    path=f"routes.{url_name}"
                ))

        # Validate domains syntax
        for idx, dom in enumerate(domains):
            if "/" in dom or ":" in dom or dom.startswith("http") or dom.startswith("."):
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_DOMAIN",
                    message=f"Domain must be a bare hostname without scheme, port, or path: '{dom}'",
                    path=f"routes.domains[{idx}]"
                ))

        # Validate regular expressions in pdp_patterns
        for idx, pattern in enumerate(pdp_patterns):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(ManifestValidationError(
                    code="SEMANTIC_INVALID_REGEX",
                    message=f"Invalid regular expression in pdp_patterns: '{pattern}' ({exc})",
                    path=f"routes.pdp_patterns[{idx}]"
                ))

        # -------------------------------------------------------------------
        # Step 7: Publisher Trust Claim Note (Security Boundary)
        # -------------------------------------------------------------------
        # Record informational note that publisher claim is unverified at manifest stage.
        publisher = manifest_dict.get("publisher", {})
        pub_type = publisher.get("type")
        if pub_type in CANONICAL_PUBLISHER_TYPES:
            warnings.append(
                f"Publisher claims tier '{pub_type}'. Independent signature and trust store verification required at Gate B."
            )

        # -------------------------------------------------------------------
        # Step 8: Declarative Configuration Schema (config_schema)
        # -------------------------------------------------------------------
        config_schema = manifest_dict.get("config_schema")
        if isinstance(config_schema, dict):
            fields_list = config_schema.get("fields", [])
            seen_config_keys = set()
            for idx, fld in enumerate(fields_list):
                if not isinstance(fld, dict):
                    continue
                k = fld.get("key")
                if k in seen_config_keys:
                    errors.append(ManifestValidationError(
                        code="SEMANTIC_DUPLICATE_CONFIG_KEY",
                        message=f"Duplicate config_schema field key: '{k}'",
                        path=f"config_schema.fields[{idx}].key"
                    ))
                elif k:
                    seen_config_keys.add(k)

                fld_type = fld.get("type")
                default_val = fld.get("default")
                is_secret = fld.get("is_secret")

                # Type-specific validation of defaults
                if default_val is not None:
                    if fld_type == "integer":
                        if isinstance(default_val, bool) or not isinstance(default_val, int) or isinstance(default_val, float):
                            errors.append(ManifestValidationError(
                                code="SEMANTIC_INVALID_CONFIG_DEFAULT",
                                message=f"Field '{k}' of type 'integer' has invalid default '{default_val}'; must be an integer (boolean and non-integer values rejected)",
                                path=f"config_schema.fields[{idx}].default"
                            ))
                    elif fld_type == "boolean":
                        if not isinstance(default_val, bool):
                            errors.append(ManifestValidationError(
                                code="SEMANTIC_INVALID_CONFIG_DEFAULT",
                                message=f"Field '{k}' of type 'boolean' has invalid default '{default_val}'; must be a boolean",
                                path=f"config_schema.fields[{idx}].default"
                            ))
                    elif fld_type == "string":
                        if not isinstance(default_val, str):
                            errors.append(ManifestValidationError(
                                code="SEMANTIC_INVALID_CONFIG_DEFAULT",
                                message=f"Field '{k}' of type 'string' has invalid default '{default_val}'; must be a string",
                                path=f"config_schema.fields[{idx}].default"
                            ))
                    elif fld_type == "password":
                        errors.append(ManifestValidationError(
                            code="SEMANTIC_INVALID_CONFIG_DEFAULT",
                            message=f"Password field '{k}' must not declare a default credential value in package manifest",
                            path=f"config_schema.fields[{idx}].default"
                        ))

                if fld_type == "password":
                    # Password fields must never bypass secret protection
                    if is_secret is False:
                        errors.append(ManifestValidationError(
                            code="SEMANTIC_INVALID_CONFIG_SECRET",
                            message=f"Field '{k}' has type 'password' and cannot bypass protected storage by declaring is_secret=false",
                            path=f"config_schema.fields[{idx}].is_secret"
                        ))

                elif fld_type == "select":
                    opts = fld.get("options")
                    if not opts or not isinstance(opts, list) or len(opts) == 0:
                        errors.append(ManifestValidationError(
                            code="SEMANTIC_INVALID_CONFIG_SELECT",
                            message=f"Select field '{k}' must declare a non-empty 'options' list",
                            path=f"config_schema.fields[{idx}].options"
                        ))
                    else:
                        seen_option_vals = set()
                        valid_vals = []
                        for opt_idx, opt in enumerate(opts):
                            if isinstance(opt, dict):
                                val = opt.get("value")
                                lbl = opt.get("label")
                                if not lbl or not isinstance(lbl, str):
                                    errors.append(ManifestValidationError(
                                        code="SEMANTIC_INVALID_CONFIG_SELECT",
                                        message=f"Select field '{k}' option at index {opt_idx} must declare a non-empty string label",
                                        path=f"config_schema.fields[{idx}].options[{opt_idx}].label"
                                    ))
                            else:
                                val = opt

                            if val is None or (isinstance(val, str) and not val.strip()):
                                errors.append(ManifestValidationError(
                                    code="SEMANTIC_INVALID_CONFIG_SELECT",
                                    message=f"Select field '{k}' option at index {opt_idx} has invalid empty value",
                                    path=f"config_schema.fields[{idx}].options[{opt_idx}]"
                                ))
                            elif val in seen_option_vals:
                                errors.append(ManifestValidationError(
                                    code="SEMANTIC_DUPLICATE_CONFIG_OPTION",
                                    message=f"Select field '{k}' contains duplicate option value: '{val}'",
                                    path=f"config_schema.fields[{idx}].options[{opt_idx}]"
                                ))
                            else:
                                seen_option_vals.add(val)
                                valid_vals.append(val)

                        if default_val is not None and default_val not in valid_vals:
                            errors.append(ManifestValidationError(
                                code="SEMANTIC_INVALID_CONFIG_DEFAULT",
                                message=f"Select field '{k}' default value '{default_val}' does not belong to declared options {valid_vals}",
                                path=f"config_schema.fields[{idx}].default"
                            ))


        return ManifestValidationResult(
            is_valid=(len(errors) == 0),
            manifest=manifest_dict if len(errors) == 0 else None,
            errors=errors,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Convenience Module-Level Functions
# ---------------------------------------------------------------------------

_DEFAULT_VALIDATOR = ManifestValidator()


def validate_manifest(
    manifest_input: Union[str, bytes, Dict[str, Any]],
    host_omnix_version: Optional[str] = None,
    host_contract_version: Optional[str] = None,
) -> ManifestValidationResult:
    """Convenience function to validate manifest from string, bytes, or dict."""
    if isinstance(manifest_input, dict):
        return _DEFAULT_VALIDATOR.validate_dict(
            manifest_input,
            host_omnix_version=host_omnix_version,
            host_contract_version=host_contract_version,
        )
    return _DEFAULT_VALIDATOR.validate_content(
        manifest_input,
        host_omnix_version=host_omnix_version,
        host_contract_version=host_contract_version,
    )


def validate_manifest_file(
    file_path: Union[str, Path],
    host_omnix_version: Optional[str] = None,
    host_contract_version: Optional[str] = None,
) -> ManifestValidationResult:
    """Convenience function to validate manifest file at path."""
    return _DEFAULT_VALIDATOR.validate_file(
        file_path,
        host_omnix_version=host_omnix_version,
        host_contract_version=host_contract_version,
    )
