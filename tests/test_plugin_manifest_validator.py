"""
Comprehensive Test Suite for Omnix Plugin Manifest Validator & JSON Schema
Governing Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 5

Tests:
1. Valid Manifests (Minimal, Full, Mode A-only, Mode B-only, All Capabilities)
2. Strict JSON Parsing (Duplicate keys, NaN, Infinity, Oversized, Malformed)
3. JSON Schema Validation (Draft 2020-12 compliance, Type checks, Extra properties)
4. Domain Semantic Rules (SemVer 2.0.0, Entry-point path safety, Identifier conventions)
5. Security Boundaries (Zero module imports, Zero code execution, Zero network egress)
"""

import copy
import json
import socket
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict

import pytest
from jsonschema.validators import Draft202012Validator

from core.plugins.manifest_validator import (
    DEFAULT_SCHEMA_PATH,
    MAX_MANIFEST_SIZE_BYTES,
    ManifestError,
    ManifestSchemaError,
    ManifestSemanticError,
    ManifestSyntaxError,
    ManifestValidationError,
    ManifestValidationResult,
    ManifestValidator,
    SemanticVersion,
    validate_manifest,
    validate_manifest_file,
)


# ---------------------------------------------------------------------------
# Canonical Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_manifest_data() -> Dict[str, Any]:
    """Returns a fully-populated canonical valid manifest dictionary."""
    return {
        "manifest_version": "1.0.0",
        "plugin_id": "com.omnix.vendor.lion",
        "vendor_id": "vendor_lion",
        "display_name": "Lion Electronic",
        "description": "Official Lion Electronic Procurement Adapter",
        "version": "1.2.0",
        "min_omnix_version": "2.0.0",
        "max_omnix_version": "2.99.99",
        "omnix_contract_version": "1.0.0",
        "entry_point": "plugin.adapter:LionVendorAdapter",
        "publisher": {
            "name": "Omnix Official Engineering",
            "type": "OFFICIAL",
            "key_id": "ed25519-omnix-official-2026-key1",
            "contact": "plugins@omnix.org",
        },
        "capabilities": [
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "CART_URL_RESOLUTION",
            "MPN_SEARCH",
            "LIVE_STOCK_PROBE",
            "TIERED_PRICING",
            "MODE_A_STAGING",
            "MODE_B_STAGING",
        ],
        "supported_modes": [
            "MODE_A",
            "MODE_B",
        ],
        "routes": {
            "base_url": "https://lionelectronic.ir",
            "cart_url": "https://lionelectronic.ir/orders/cart",
            "domains": [
                "lionelectronic.ir",
                "www.lionelectronic.ir",
            ],
            "pdp_patterns": [
                r"^https?://(?:www\.)?lionelectronic\.ir/products/(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.\-\+\/]+)$",
                r"^/products/(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.\-\+\/]+)$",
            ],
        },
        "dependencies": {
            "python": ">=3.11",
            "external_libraries": [
                "beautifulsoup4>=4.12.0",
                "selenium>=4.20.0",
            ],
        },
    }


@pytest.fixture
def minimal_manifest_data() -> Dict[str, Any]:
    """Returns a minimally valid manifest with only strictly required fields."""
    return {
        "manifest_version": "1.0.0",
        "plugin_id": "com.supplier.basic",
        "vendor_id": "vendor_basic",
        "display_name": "Basic Vendor",
        "version": "0.1.0",
        "min_omnix_version": "2.0.0",
        "omnix_contract_version": "1.0.0",
        "entry_point": "adapter:BasicAdapter",
        "publisher": {
            "name": "Community Developer",
            "type": "COMMUNITY",
            "key_id": "key-12345",
        },
        "capabilities": [
            "PRODUCT_INSPECTION",
        ],
        "supported_modes": [
            "MODE_A",
        ],
        "routes": {
            "base_url": "https://basicvendor.com",
            "cart_url": "https://basicvendor.com/cart",
            "domains": [
                "basicvendor.com",
            ],
        },
    }


# ---------------------------------------------------------------------------
# 1. Valid Manifest Tests (Section 11.1)
# ---------------------------------------------------------------------------

class TestValidManifests:
    """Verifies valid manifests across all permitted configurations."""

    def test_schema_itself_is_valid_draft202012(self):
        """Verify that manifest.schema.json is a valid Draft 2020-12 schema."""
        with open(DEFAULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
        Draft202012Validator.check_schema(schema)

    def test_canonical_manifest_validation(self, valid_manifest_data):
        """Full canonical manifest passes schema and semantic checks."""
        validator = ManifestValidator()
        result = validator.validate_dict(valid_manifest_data)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.manifest == valid_manifest_data
        # Verify raise_for_errors does not raise
        result.raise_for_errors()

    def test_minimal_manifest_validation(self, minimal_manifest_data):
        """Minimally required fields pass validation without optional metadata."""
        validator = ManifestValidator()
        result = validator.validate_dict(minimal_manifest_data)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_mode_a_only_plugin_is_valid(self, valid_manifest_data):
        """A plugin supporting only Mode A is valid without Mode B."""
        data = copy.deepcopy(valid_manifest_data)
        data["supported_modes"] = ["MODE_A"]
        data["capabilities"] = [
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "CART_URL_RESOLUTION",
            "MODE_A_STAGING",
        ]
        result = validate_manifest(data)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_mode_b_only_plugin_is_valid(self, valid_manifest_data):
        """A plugin supporting only Mode B is valid without Mode A."""
        data = copy.deepcopy(valid_manifest_data)
        data["supported_modes"] = ["MODE_B"]
        data["capabilities"] = [
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "MPN_SEARCH",
            "MODE_B_STAGING",
        ]
        result = validate_manifest(data)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_all_canonical_capabilities_valid(self, valid_manifest_data):
        """All 8 canonical capabilities are accepted."""
        data = copy.deepcopy(valid_manifest_data)
        all_caps = [
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "CART_URL_RESOLUTION",
            "MPN_SEARCH",
            "LIVE_STOCK_PROBE",
            "TIERED_PRICING",
            "MODE_A_STAGING",
            "MODE_B_STAGING",
        ]
        data["capabilities"] = all_caps
        result = validate_manifest(data)
        assert result.is_valid is True

    @pytest.mark.parametrize("ver", [
        "1.0.0",
        "0.0.1",
        "2.10.45",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-0.3.7",
        "1.0.0-x.7.z.92",
        "1.0.0-beta+exp.sha.5114f85",
        "1.0.0+20130313144700",
    ])
    def test_valid_semver_variations(self, valid_manifest_data, ver):
        """Standard SemVer 2.0.0 variations are recognized as valid."""
        data = copy.deepcopy(valid_manifest_data)
        data["version"] = ver
        result = validate_manifest(data)
        assert result.is_valid is True

    def test_null_max_omnix_version_allowed(self, valid_manifest_data):
        """max_omnix_version can be explicitly null."""
        data = copy.deepcopy(valid_manifest_data)
        data["max_omnix_version"] = None
        result = validate_manifest(data)
        assert result.is_valid is True

    def test_validate_file_convenience(self, valid_manifest_data):
        """validate_manifest_file reads and validates JSON file on disk."""
        with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(valid_manifest_data, f)
            temp_path = f.name

        try:
            result = validate_manifest_file(temp_path)
            assert result.is_valid is True
            assert result.manifest["plugin_id"] == "com.omnix.vendor.lion"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 2. Strict JSON Parsing Tests (Section 11.2)
# ---------------------------------------------------------------------------

class TestStrictJSONParsing:
    """Verifies that parsing rejects malformed, duplicate-key, or non-standard JSON."""

    def test_malformed_json_syntax(self):
        """Rejects unclosed brackets or trailing commas."""
        raw = '{"manifest_version": "1.0.0", "plugin_id": "com.test",}'
        result = validate_manifest(raw)
        assert result.is_valid is False
        assert any(e.code == "JSON_PARSE_ERROR" for e in result.errors)

    def test_empty_input(self):
        """Rejects empty string."""
        result = validate_manifest("")
        assert result.is_valid is False
        assert any(e.code == "JSON_EMPTY_INPUT" for e in result.errors)

    def test_whitespace_only_input(self):
        """Rejects whitespace-only string."""
        result = validate_manifest("   \n\t  ")
        assert result.is_valid is False
        assert any(e.code == "JSON_EMPTY_INPUT" for e in result.errors)

    def test_unsupported_input_type(self):
        """Rejects non-string and non-bytes input."""
        result = validate_manifest(12345)  # type: ignore
        assert result.is_valid is False
        assert any(e.code == "JSON_INVALID_TYPE" for e in result.errors)

    def test_root_not_an_object(self):
        """Rejects JSON arrays or primitives at the root level."""
        result = validate_manifest('["element1", "element2"]')
        assert result.is_valid is False
        assert any(e.code == "JSON_INVALID_ROOT" for e in result.errors)

    def test_duplicate_top_level_keys_rejected(self, valid_manifest_data):
        """Rejects manifests with duplicate top-level keys."""
        raw = json.dumps(valid_manifest_data)
        # Inject duplicate key at end
        tampered = raw[:-1] + ', "plugin_id": "com.malicious.duplicate"}'
        result = validate_manifest(tampered)
        assert result.is_valid is False
        assert any(e.code == "JSON_DUPLICATE_KEY" for e in result.errors)

    def test_duplicate_nested_keys_rejected(self, valid_manifest_data):
        """Rejects manifests with duplicate nested keys."""
        tampered = """
        {
            "manifest_version": "1.0.0",
            "plugin_id": "com.test.nested",
            "vendor_id": "vendor_test",
            "display_name": "Test",
            "version": "1.0.0",
            "min_omnix_version": "2.0.0",
            "omnix_contract_version": "1.0.0",
            "entry_point": "mod:Class",
            "publisher": {
                "name": "Org 1",
                "name": "Org 2",
                "type": "OFFICIAL",
                "key_id": "key1"
            },
            "capabilities": ["PRODUCT_INSPECTION"],
            "supported_modes": ["MODE_A"],
            "routes": {
                "base_url": "https://test.com",
                "cart_url": "https://test.com/cart",
                "domains": ["test.com"]
            }
        }
        """
        result = validate_manifest(tampered)
        assert result.is_valid is False
        assert any(e.code == "JSON_DUPLICATE_KEY" for e in result.errors)

    def test_nan_constant_rejected(self, valid_manifest_data):
        """Rejects non-standard NaN numeric constant."""
        raw = json.dumps(valid_manifest_data)
        tampered = raw[:-1] + ', "bad_val": NaN}'
        result = validate_manifest(tampered)
        assert result.is_valid is False
        assert any(e.code == "JSON_INVALID_CONSTANT" for e in result.errors)

    def test_infinity_constant_rejected(self, valid_manifest_data):
        """Rejects non-standard Infinity constant."""
        raw = json.dumps(valid_manifest_data)
        tampered = raw[:-1] + ', "bad_val": Infinity}'
        result = validate_manifest(tampered)
        assert result.is_valid is False
        assert any(e.code == "JSON_INVALID_CONSTANT" for e in result.errors)

    def test_negative_infinity_constant_rejected(self, valid_manifest_data):
        """Rejects non-standard -Infinity constant."""
        raw = json.dumps(valid_manifest_data)
        tampered = raw[:-1] + ', "bad_val": -Infinity}'
        result = validate_manifest(tampered)
        assert result.is_valid is False
        assert any(e.code == "JSON_INVALID_CONSTANT" for e in result.errors)

    def test_oversized_manifest_rejected(self, valid_manifest_data):
        """Rejects manifests exceeding MAX_MANIFEST_SIZE_BYTES."""
        raw = json.dumps(valid_manifest_data)
        # Pad with large harmless comment or padding field
        padding = "A" * (MAX_MANIFEST_SIZE_BYTES + 1024)
        oversized = raw[:-1] + f', "padding": "{padding}"}}'
        result = validate_manifest(oversized)
        assert result.is_valid is False
        assert any(e.code == "JSON_OVERSIZED" for e in result.errors)


# ---------------------------------------------------------------------------
# 3. Schema Validation Tests (Section 11.3)
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Verifies that schema structural violations are caught deterministically."""

    @pytest.mark.parametrize("missing_field", [
        "manifest_version",
        "plugin_id",
        "vendor_id",
        "display_name",
        "version",
        "min_omnix_version",
        "omnix_contract_version",
        "entry_point",
        "publisher",
        "capabilities",
        "supported_modes",
        "routes",
    ])
    def test_missing_required_fields_rejected(self, valid_manifest_data, missing_field):
        """Omitting any mandatory field fails schema validation."""
        data = copy.deepcopy(valid_manifest_data)
        del data[missing_field]
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_invalid_manifest_version(self, valid_manifest_data):
        """Unsupported schema manifest_version is rejected."""
        data = copy.deepcopy(valid_manifest_data)
        data["manifest_version"] = "99.0.0"
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_unknown_properties_rejected(self, valid_manifest_data):
        """Additional undeclared properties are rejected by additionalProperties: false."""
        data = copy.deepcopy(valid_manifest_data)
        data["unauthorized_field"] = "malicious_payload"
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_invalid_publisher_type_enum(self, valid_manifest_data):
        """Publisher type not in enum is rejected."""
        data = copy.deepcopy(valid_manifest_data)
        data["publisher"]["type"] = "ROOT_SUPERUSER"
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_empty_supported_modes_rejected(self, valid_manifest_data):
        """Empty supported_modes list fails minItems constraint."""
        data = copy.deepcopy(valid_manifest_data)
        data["supported_modes"] = []
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_duplicate_items_in_capabilities_rejected(self, valid_manifest_data):
        """Duplicate capabilities fail uniqueItems constraint."""
        data = copy.deepcopy(valid_manifest_data)
        data["capabilities"] = ["PRODUCT_INSPECTION", "PRODUCT_INSPECTION"]
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_incorrect_types_rejected(self, valid_manifest_data):
        """Supplying integers or booleans where strings/lists are expected fails."""
        data = copy.deepcopy(valid_manifest_data)
        data["display_name"] = 12345
        data["capabilities"] = "NOT_A_LIST"
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)


# ---------------------------------------------------------------------------
# 4. Semantic Validation Tests (Section 11.4)
# ---------------------------------------------------------------------------

class TestSemanticValidation:
    """Verifies domain rules that extend beyond basic JSON schema typing."""

    @pytest.mark.parametrize("bad_plugin_id", [
        "com-invalid-dash",
        "com.UPPERCASE.not.allowed",
        "singleword",
        ".starts.with.dot",
        "ends.with.dot.",
        "com.omnix.vendor.lion." + ("a" * 100),  # too long
    ])
    def test_malformed_plugin_id_rejected(self, valid_manifest_data, bad_plugin_id):
        """plugin_id must strictly follow reverse-DNS convention."""
        data = copy.deepcopy(valid_manifest_data)
        data["plugin_id"] = bad_plugin_id
        result = validate_manifest(data)
        assert result.is_valid is False

    @pytest.mark.parametrize("bad_vendor_id", [
        "lion",  # missing vendor_ prefix
        "vendor-lion",  # dashes instead of underscores
        "vendor_LION",  # uppercase
        "vendor_" + ("x" * 40),  # too long
        "vendor_",  # empty suffix
    ])
    def test_malformed_vendor_id_rejected(self, valid_manifest_data, bad_vendor_id):
        """vendor_id must match ^vendor_[a-z0-9_]+$."""
        data = copy.deepcopy(valid_manifest_data)
        data["vendor_id"] = bad_vendor_id
        result = validate_manifest(data)
        assert result.is_valid is False

    def test_version_range_contradiction_rejected(self, valid_manifest_data):
        """Rejects manifest where max_omnix_version < min_omnix_version."""
        data = copy.deepcopy(valid_manifest_data)
        data["min_omnix_version"] = "2.5.0"
        data["max_omnix_version"] = "2.1.0"
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SEMANTIC_VERSION_RANGE_INVALID" for e in result.errors)

    @pytest.mark.parametrize("bad_entry_point", [
        "module/path/adapter.py:LionAdapter",  # slashes
        "../escape/adapter:LionAdapter",  # directory traversal
        "C:\\system32\\evil:Class",  # Windows drive
        "\\\\server\\share:Class",  # UNC path
        "plugin.adapter\0:LionAdapter",  # null byte
        "plugin.adapter.LionAdapter",  # missing colon separator
    ])
    def test_unsafe_entry_points_rejected(self, valid_manifest_data, bad_entry_point):
        """Rejects traversal, absolute, UNC, and null-byte entry points."""
        data = copy.deepcopy(valid_manifest_data)
        data["entry_point"] = bad_entry_point
        result = validate_manifest(data)
        assert result.is_valid is False

    def test_staging_capability_without_matching_mode_rejected(self, valid_manifest_data):
        """Declaring MODE_A_STAGING without declaring MODE_A in supported_modes is rejected."""
        data = copy.deepcopy(valid_manifest_data)
        data["supported_modes"] = ["MODE_B"]
        data["capabilities"] = ["MODE_A_STAGING", "MODE_B_STAGING"]
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SEMANTIC_MODE_CAPABILITY_MISMATCH" for e in result.errors)

    @pytest.mark.parametrize("bad_url", [
        "ftp://lionelectronic.ir/cart",  # unsupported scheme
        "lionelectronic.ir/cart",  # missing scheme
        "file:///etc/passwd",  # file URI
    ])
    def test_invalid_routes_urls_rejected(self, valid_manifest_data, bad_url):
        """Base and cart URLs must be valid HTTP/HTTPS."""
        data = copy.deepcopy(valid_manifest_data)
        data["routes"]["cart_url"] = bad_url
        result = validate_manifest(data)
        assert result.is_valid is False

    def test_invalid_pdp_regex_pattern_rejected(self, valid_manifest_data):
        """Malformed regular expression in pdp_patterns is rejected."""
        data = copy.deepcopy(valid_manifest_data)
        data["routes"]["pdp_patterns"] = ["[unclosed-bracket-regex("]
        result = validate_manifest(data)
        assert result.is_valid is False
        assert any(e.code == "SEMANTIC_INVALID_REGEX" for e in result.errors)

    def test_host_runtime_compatibility_check(self, valid_manifest_data):
        """Validates host runtime version bounds when supplied."""
        validator = ManifestValidator()

        # In range [2.0.0, 2.99.99]
        res_ok = validator.validate_dict(valid_manifest_data, host_omnix_version="2.5.0", host_contract_version="1.0.0")
        assert res_ok.is_valid is True

        # Host too old
        res_old = validator.validate_dict(valid_manifest_data, host_omnix_version="1.9.0", host_contract_version="1.0.0")
        assert res_old.is_valid is False
        assert any(e.code == "COMPATIBILITY_HOST_TOO_OLD" for e in res_old.errors)

        # Host too new
        res_new = validator.validate_dict(valid_manifest_data, host_omnix_version="3.0.0", host_contract_version="1.0.0")
        assert res_new.is_valid is False
        assert any(e.code == "COMPATIBILITY_HOST_TOO_NEW" for e in res_new.errors)

        # Contract major mismatch
        res_contract = validator.validate_dict(valid_manifest_data, host_omnix_version="2.5.0", host_contract_version="2.0.0")
        assert res_contract.is_valid is False
        assert any(e.code == "COMPATIBILITY_CONTRACT_MISMATCH" for e in res_contract.errors)


# ---------------------------------------------------------------------------
# 5. Security Boundary & Non-Execution Tests (Section 11.5)
# ---------------------------------------------------------------------------

class TestSecurityBoundaries:
    """Verifies that the validator never imports, executes, connects, or extracts."""

    def test_zero_module_import_of_entry_point(self, valid_manifest_data, monkeypatch):
        """Validating a manifest never imports the declared entry point module."""
        fake_module_name = "unimported_fake_plugin_module"
        assert fake_module_name not in sys.modules

        data = copy.deepcopy(valid_manifest_data)
        data["entry_point"] = f"{fake_module_name}:FakeClass"

        # Track __import__ calls
        imported_modules = []
        real_import = __import__

        def audit_import(name, *args, **kwargs):
            imported_modules.append(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", audit_import)

        result = validate_manifest(data)
        # Entry point was validated syntactically
        assert result.is_valid is True
        # Proved that fake_module_name was NEVER imported
        assert fake_module_name not in sys.modules
        assert fake_module_name not in imported_modules

    def test_zero_network_egress(self, valid_manifest_data, monkeypatch):
        """Validating a manifest performs zero outbound network socket calls."""
        def trap_socket_connect(*args, **kwargs):
            raise AssertionError("Network socket connect attempted during manifest validation!")

        monkeypatch.setattr(socket.socket, "connect", trap_socket_connect)

        result = validate_manifest(valid_manifest_data)
        assert result.is_valid is True

    def test_publisher_claims_do_not_authorize_execution(self, valid_manifest_data):
        """
        Publisher metadata claiming 'OFFICIAL' is strictly an unverified claim
        and generates an audit warning; does not authorize execution.
        """
        result = validate_manifest(valid_manifest_data)
        assert result.is_valid is True
        # Warning exists notifying that Gate B signature check is still required
        assert any("Gate B" in w for w in result.warnings)

    def test_error_reporting_does_not_leak_secrets(self, valid_manifest_data):
        """Error messages never echo back sensitive environment data."""
        data = copy.deepcopy(valid_manifest_data)
        data["publisher"]["contact"] = "secret_contact@company.internal"
        data["publisher"]["key_id"] = "a" * 200  # invalid length
        result = validate_manifest(data)
        assert result.is_valid is False
        for err in result.errors:
            assert "secret_contact" not in str(err)

    def test_exception_raise_for_errors(self, valid_manifest_data):
        """raise_for_errors raises appropriate subclass on failure."""
        data = copy.deepcopy(valid_manifest_data)
        del data["plugin_id"]
        result = validate_manifest(data)
        with pytest.raises(ManifestSchemaError):
            result.raise_for_errors()


# ---------------------------------------------------------------------------
# 6. SemVer 2.0.0 Unit Tests
# ---------------------------------------------------------------------------

class TestSemanticVersionComparator:
    """Verifies that our self-contained SemVer class adheres to SemVer 2.0.0 spec."""

    def test_basic_comparisons(self):
        assert SemanticVersion("1.0.0") < SemanticVersion("2.0.0")
        assert SemanticVersion("1.1.0") > SemanticVersion("1.0.9")
        assert SemanticVersion("1.0.1") > SemanticVersion("1.0.0")
        assert SemanticVersion("1.0.0") == SemanticVersion("1.0.0")

    def test_prerelease_precedence(self):
        # 1.0.0-alpha < 1.0.0
        assert SemanticVersion("1.0.0-alpha") < SemanticVersion("1.0.0")
        # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
        assert SemanticVersion("1.0.0-alpha") < SemanticVersion("1.0.0-alpha.1")
        assert SemanticVersion("1.0.0-alpha.1") < SemanticVersion("1.0.0-beta")
        assert SemanticVersion("1.0.0-beta") < SemanticVersion("1.0.0-beta.2")
        assert SemanticVersion("1.0.0-beta.2") < SemanticVersion("1.0.0-beta.11")
        assert SemanticVersion("1.0.0-beta.11") < SemanticVersion("1.0.0-rc.1")
        assert SemanticVersion("1.0.0-rc.1") < SemanticVersion("1.0.0")

    def test_build_metadata_ignored_in_comparison(self):
        # Build metadata does not change precedence
        v1 = SemanticVersion("1.0.0+build1")
        v2 = SemanticVersion("1.0.0+build2")
        assert v1 == v2
        assert not (v1 < v2)
        assert not (v1 > v2)

    def test_invalid_semver_strings(self):
        with pytest.raises(ValueError):
            SemanticVersion("1.0")  # missing patch
        with pytest.raises(ValueError):
            SemanticVersion("v1.0.0")  # leading 'v'
        with pytest.raises(ValueError):
            SemanticVersion("1.0.01")  # leading zero in patch
