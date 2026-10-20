"""
Omnix Vendor Plugin System — Comprehensive Phase 4 Package Inspection Tests
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md

Validates that PackageInspector:
1. Correctly verifies valid packages (single-vendor, multi-module, assets, declarative config).
2. Computes archive SHA-256, validates manifest schema and semantic rules.
3. Enforces strict archive safety limits (10 MiB zip, 50 MiB total, 20 MiB entry, 10:1 ratio, 500 entries, extension whitelist).
4. Detects zip-slip, traversal, case collisions, duplicate members, symlinks/devices.
5. Verifies META-INF/MANIFEST.MF digests, detects unlisted files, missing files, tampered contents, uncanonical ordering.
6. Verifies static entry-point presence without importing or executing.
7. Strictly guarantees zero execution, zero import, zero disk extraction, zero registry mutation.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest

from core.plugins.manifest_mf import ManifestMF, generate_manifest_mf
from core.plugins.package_inspector import (
    ALLOWED_FILE_EXTENSIONS,
    MAX_COMPRESSED_SIZE_BYTES,
    MAX_ENTRY_COUNT,
    MAX_UNCOMPRESSED_ENTRY_BYTES,
    MAX_UNCOMPRESSED_TOTAL_BYTES,
    PackageInspectionError,
    PackageInspectionException,
    PackageInspectionResult,
    PackageInspectionStatus,
    PackageInspector,
    inspect_package,
)
from core.procurement.registry import VendorRegistry, default_registry


# ---------------------------------------------------------------------------
# Test Helpers: Synthetic Package Generator
# ---------------------------------------------------------------------------

def make_valid_manifest_dict(
    plugin_id: str = "com.omnix.vendor.lion",
    vendor_id: str = "vendor_lion",
    version: str = "1.0.0",
    entry_point: str = "plugin.adapter:LionAdapter",
    config_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a baseline valid manifest dictionary conforming to schema."""
    manifest = {
        "manifest_version": "1.0.0",
        "plugin_id": plugin_id,
        "vendor_id": vendor_id,
        "display_name": "Lion Electronics Procurement Plugin",
        "version": version,
        "min_omnix_version": "2.0.0",
        "omnix_contract_version": "1.0.0",
        "entry_point": entry_point,
        "publisher": {
            "name": "Lion Electronics Inc.",
            "type": "OFFICIAL",
            "key_id": "key_lion_1",
        },
        "supported_modes": ["MODE_A"],
        "capabilities": [
            "PRODUCT_URL_RECOGNITION",
            "PRODUCT_INSPECTION",
            "MODE_A_STAGING",
        ],
        "routes": {
            "base_url": "https://lion.ir",
            "cart_url": "https://lion.ir/cart",
            "domains": ["lion.ir", "api.lion.ir"],
            "pdp_patterns": [r"^https?://(?:www\.)?lion\.ir/product/.*$"],
        },
    }

    if config_schema is not None:
        manifest["config_schema"] = config_schema
    return manifest



def build_xpl_package(
    files: Dict[str, Union[str, bytes]],
    include_manifest_mf: bool = True,
    corrupt_manifest_mf_ordering: bool = False,
    extra_mf_entries: Optional[Dict[str, str]] = None,
    omit_manifest_json: bool = False,
    manifest_dict: Optional[Dict[str, Any]] = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    """
    Build an in-memory synthetic .xpl ZIP archive.

    If include_manifest_mf is True, automatically generates a valid canonical
    META-INF/MANIFEST.MF containing SHA-256 digests for all files (excluding META-INF/).
    """
    pkg_files = dict(files)

    # Add manifest.json if requested and not explicitly provided in files
    if not omit_manifest_json and "manifest.json" not in pkg_files:
        m_dict = manifest_dict or make_valid_manifest_dict()
        pkg_files["manifest.json"] = json.dumps(m_dict, indent=2).encode("utf-8")

    # Build META-INF/MANIFEST.MF if requested and not provided
    if include_manifest_mf and "META-INF/MANIFEST.MF" not in pkg_files:
        mf_text = generate_manifest_mf(pkg_files)
        if corrupt_manifest_mf_ordering:
            # Reverse order of entries to violate lexicographical order
            parsed = ManifestMF.parse(mf_text, enforce_canonical_ordering=False)
            reversed_entries = {k: v for k, v in reversed(list(parsed.entries.items()))}
            mf_text = parsed.to_manifest_mf_string(reversed_entries)
        if extra_mf_entries:
            parsed = ManifestMF.parse(mf_text, enforce_canonical_ordering=False)
            combined = dict(parsed.entries)
            combined.update(extra_mf_entries)
            mf_text = parsed.to_manifest_mf_string(combined)
        pkg_files["META-INF/MANIFEST.MF"] = mf_text.encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for path, data in pkg_files.items():
            content = data.encode("utf-8") if isinstance(data, str) else data
            zf.writestr(path, content)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Suite: Valid Package Inspection
# ---------------------------------------------------------------------------

class TestPackageInspectorValidPackages:
    """Tests confirming that well-formed, compliant .xpl packages inspect successfully."""

    def test_minimal_valid_single_vendor_package(self, tmp_path: Path):
        files = {
            "plugin/__init__.py": "# plugin package\n",
            "plugin/adapter.py": "class LionAdapter:\n    pass\n",
        }
        pkg_bytes = build_xpl_package(files)
        pkg_file = tmp_path / "lion-1.0.0.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)

        assert result.is_valid is True
        assert result.status == PackageInspectionStatus.VALID
        assert result.errors == []
        assert result.manifest is not None
        assert result.manifest["plugin_id"] == "com.omnix.vendor.lion"
        assert result.manifest["vendor_id"] == "vendor_lion"
        assert result.archive_sha256 == hashlib.sha256(pkg_bytes).hexdigest()
        assert result.file_count == 4  # manifest.json, META-INF/MANIFEST.MF, plugin/__init__.py, plugin/adapter.py
        assert result.total_uncompressed_bytes > 0
        assert "plugin/adapter.py" in result.scanned_files

    def test_multi_module_package_with_helpers_and_assets(self, tmp_path: Path):
        """Single vendor with multiple internal modules, helper classes, and assets."""
        files = {
            "lion_plugin/__init__.py": "VERSION = '1.0.0'\n",
            "lion_plugin/adapter.py": "from .helpers import parse_response\nclass LionAdapter:\n    pass\n",
            "lion_plugin/helpers.py": "class ResponseParser:\n    pass\ndef parse_response(x): return x\n",
            "lion_plugin/submodels/items.py": "class LineItem:\n    pass\n",
            "docs/README.md": "# Lion Electronics Plugin\nInstructions and details.\n",
            "docs/CHANGELOG.txt": "v1.0.0: Initial release\n",
            "assets/logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4",
            "assets/icon.svg": "<svg></svg>",
        }
        manifest_dict = make_valid_manifest_dict(
            plugin_id="com.omnix.vendor.lion",
            vendor_id="vendor_lion",
            entry_point="lion_plugin.adapter:LionAdapter",
        )
        pkg_bytes = build_xpl_package(files, manifest_dict=manifest_dict)
        pkg_file = tmp_path / "lion_complex.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)

        assert result.is_valid is True
        assert result.status == PackageInspectionStatus.VALID
        assert result.file_count == len(files) + 2  # + manifest.json + META-INF/MANIFEST.MF
        assert "lion_plugin/helpers.py" in result.scanned_files
        assert "assets/logo.png" in result.scanned_files

    def test_package_with_package_style_init_entry_point(self, tmp_path: Path):
        """Entry point pointing to module whose implementation is in __init__.py."""
        files = {
            "lion_entry/__init__.py": "class LionMainAdapter:\n    pass\n",
        }
        manifest_dict = make_valid_manifest_dict(
            plugin_id="com.omnix.vendor.lion",
            vendor_id="vendor_lion",
            entry_point="lion_entry:LionMainAdapter",
        )
        pkg_bytes = build_xpl_package(files, manifest_dict=manifest_dict)
        pkg_file = tmp_path / "lion_init_entry.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is True
        assert result.status == PackageInspectionStatus.VALID

    def test_package_with_valid_declarative_config_schema(self, tmp_path: Path):
        """Package containing declarative config_schema with secrets, select options, and defaults."""
        config_schema = {
            "fields": [
                {
                    "key": "api_key",
                    "label": "API Key",
                    "type": "string",
                    "required": True,
                    "is_secret": True,
                    "description": "Customer API Key for Lion Electronic",
                },
                {
                    "key": "environment",
                    "label": "Environment",
                    "type": "select",
                    "required": False,
                    "options": ["production", "sandbox"],
                    "default": "production",
                },
                {
                    "key": "request_timeout_seconds",
                    "label": "Timeout (seconds)",
                    "type": "integer",
                    "required": False,
                    "default": 30,
                },
            ]
        }
        manifest_dict = make_valid_manifest_dict(
            plugin_id="com.omnix.vendor.lion",
            vendor_id="vendor_lion",
            config_schema=config_schema,
        )
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        pkg_bytes = build_xpl_package(files, manifest_dict=manifest_dict)
        pkg_file = tmp_path / "lion_config.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is True
        assert result.status == PackageInspectionStatus.VALID
        assert result.manifest["config_schema"]["fields"][0]["key"] == "api_key"

    def test_inspect_from_bytes_io_directly(self):
        """Inspector accepts in-memory BytesIO directly."""
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)
        buf = io.BytesIO(pkg_bytes)

        result = inspect_package(buf)
        assert result.is_valid is True
        assert result.archive_sha256 == hashlib.sha256(pkg_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Test Suite: Package Identity & Manifest Rules
# ---------------------------------------------------------------------------

class TestPackageInspectorIdentityAndManifest:
    """Tests verifying manifest integrity, presence, and single-vendor identity rules."""

    def test_missing_manifest_json(self, tmp_path: Path):
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, omit_manifest_json=True)
        pkg_file = tmp_path / "no_manifest.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_NOT_FOUND
        assert any("manifest.json" in err.message for err in result.errors)

    def test_manifest_corrupted_json_syntax(self, tmp_path: Path):
        files = {
            "manifest.json": "NOT_JSON { broken syntax",
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        pkg_bytes = build_xpl_package(files, omit_manifest_json=True)
        pkg_file = tmp_path / "corrupt_json.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SYNTAX_ERROR

    def test_manifest_missing_required_vendor_id(self, tmp_path: Path):
        m = make_valid_manifest_dict()
        del m["vendor_id"]
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "missing_vendor_id.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SCHEMA_ERROR
        assert any("vendor_id" in err.message for err in result.errors)

    def test_single_vendor_identity_mismatch(self, tmp_path: Path):
        """Mismatched plugin_id and vendor_id (e.g. lion plugin declaring javan vendor_id)."""
        m = make_valid_manifest_dict(
            plugin_id="com.omnix.vendor.lion",
            vendor_id="vendor_javan",  # Mismatch!
        )
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "mismatched_identity.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.IDENTITY_CONFLICT
        assert any("conflict" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_duplicate_field_keys(self, tmp_path: Path):
        """config_schema with duplicate keys is rejected."""
        config_schema = {
            "fields": [
                {"key": "token", "label": "Token 1", "type": "string"},
                {"key": "token", "label": "Token 2", "type": "string"},
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "dup_config_keys.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("duplicate" in err.message.lower() and "key" in err.message.lower() for err in result.errors)


    def test_invalid_config_schema_select_without_options(self, tmp_path: Path):
        """config_schema select field missing options list is rejected."""
        config_schema = {
            "fields": [
                {"key": "env", "label": "Environment", "type": "select"},
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "select_no_opts.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("options" in err.message for err in result.errors)

    def test_invalid_config_schema_integer_field_bad_defaults(self, tmp_path: Path):
        """Integer config field rejects boolean, string, or float defaults."""
        bad_defaults = [True, False, "123", 45.67]
        for bad_def in bad_defaults:
            config_schema = {
                "fields": [
                    {"key": "retries", "label": "Retries", "type": "integer", "default": bad_def},
                ]
            }
            m = make_valid_manifest_dict(config_schema=config_schema)
            files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
            pkg_bytes = build_xpl_package(files, manifest_dict=m)
            result = inspect_package(pkg_bytes)
            assert result.is_valid is False
            assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
            assert any("integer" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_boolean_field_bad_defaults(self, tmp_path: Path):
        """Boolean config field rejects integer or string defaults."""
        bad_defaults = [1, 0, "true", "false"]
        for bad_def in bad_defaults:
            config_schema = {
                "fields": [
                    {"key": "debug_mode", "label": "Debug", "type": "boolean", "default": bad_def},
                ]
            }
            m = make_valid_manifest_dict(config_schema=config_schema)
            files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
            pkg_bytes = build_xpl_package(files, manifest_dict=m)
            result = inspect_package(pkg_bytes)
            assert result.is_valid is False
            assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
            assert any("boolean" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_select_default_not_in_options(self, tmp_path: Path):
        """Select default value must belong to declared options."""
        config_schema = {
            "fields": [
                {
                    "key": "env",
                    "label": "Environment",
                    "type": "select",
                    "options": ["sandbox", "production"],
                    "default": "staging",  # Not in options!
                },
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("default" in err.message.lower() and "options" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_select_duplicate_options(self, tmp_path: Path):
        """Select field rejects duplicate option values."""
        config_schema = {
            "fields": [
                {
                    "key": "env",
                    "label": "Environment",
                    "type": "select",
                    "options": ["sandbox", "production", "sandbox"],
                },
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("duplicate option" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_password_cannot_declare_is_secret_false(self, tmp_path: Path):
        """Password fields cannot bypass secret protection with is_secret=False."""
        config_schema = {
            "fields": [
                {"key": "pwd", "label": "Password", "type": "password", "is_secret": False},
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("password" in err.message.lower() and "is_secret" in err.message.lower() for err in result.errors)

    def test_invalid_config_schema_password_cannot_declare_default(self, tmp_path: Path):
        """Password fields must not declare default credential values in package manifests."""
        config_schema = {
            "fields": [
                {"key": "pwd", "label": "Password", "type": "password", "default": "secret123"},
            ]
        }
        m = make_valid_manifest_dict(config_schema=config_schema)
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SEMANTIC_ERROR
        assert any("password" in err.message.lower() and "default" in err.message.lower() for err in result.errors)



# ---------------------------------------------------------------------------
# Test Suite: Archive Safety & Security Limits
# ---------------------------------------------------------------------------

class TestPackageInspectorArchiveSafetyAndLimits:
    """Tests verifying limits, corruption handling, traversal, collisions, and bombs."""

    def test_corrupted_non_zip_file(self, tmp_path: Path):
        pkg_file = tmp_path / "corrupted.xpl"
        pkg_file.write_bytes(b"THIS IS NOT A ZIP ARCHIVE AT ALL")

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.CORRUPTED_ARCHIVE

    def test_oversized_compressed_archive(self, tmp_path: Path):
        """Package whose compressed size exceeds 10 MiB limit."""
        pkg_file = tmp_path / "huge_compressed.xpl"
        # We simulate a large file without filling 10 MiB of RAM by creating a sparse/padded file
        # or testing inspector's check on file size
        # 10 MiB + 1 byte
        with open(pkg_file, "wb") as f:
            f.seek(MAX_COMPRESSED_SIZE_BYTES)
            f.write(b"X")

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.LIMIT_EXCEEDED
        assert any("compressed size" in err.message.lower() for err in result.errors)


    def test_oversized_uncompressed_entry(self, tmp_path: Path):
        """Single entry whose uncompressed size exceeds 20 MiB limit."""
        # Construct archive where central directory reports > 20 MiB
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)

        # Mutate zip header to report > 20 MiB uncompressed size
        buf = io.BytesIO(pkg_bytes)
        # We can test by setting inspector._max_uncompressed_entry_bytes lower for testing
        inspector = PackageInspector()
        inspector._max_uncompressed_entry_bytes = 100  # set threshold small to trigger

        result = inspector.inspect(buf)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.LIMIT_EXCEEDED
        assert any("uncompressed size" in err.message.lower() for err in result.errors)

    def test_oversized_total_uncompressed_archive(self, tmp_path: Path):
        """Cumulative uncompressed size exceeding limit."""
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)
        buf = io.BytesIO(pkg_bytes)

        inspector = PackageInspector()
        inspector._max_total_uncompressed_bytes = 100  # small limit to trigger

        result = inspector.inspect(buf)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.LIMIT_EXCEEDED
        assert any("cumulative uncompressed size" in err.message.lower() for err in result.errors)

    def test_entry_count_exceeds_limit(self, tmp_path: Path):
        """Archive having more than 500 members."""
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)
        buf = io.BytesIO(pkg_bytes)

        inspector = PackageInspector()
        inspector._max_entry_count = 2  # small limit to trigger

        result = inspector.inspect(buf)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.LIMIT_EXCEEDED
        assert any("member count" in err.message.lower() for err in result.errors)

    def test_compression_bomb_ratio_check(self, tmp_path: Path):
        """Ratio check (>10:1) triggers only for entries > 1 MiB uncompressed."""
        inspector = PackageInspector()
        # Set threshold to 1000 bytes and max ratio to 5.0 for deterministic test
        inspector._ratio_check_min_entry_bytes = 1000
        inspector._max_compression_ratio = 5.0

        # Highly compressible repeating payload of 5000 bytes
        repeating_data = b"A" * 5000
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "plugin/huge_repeating.txt": repeating_data,
        }
        pkg_bytes = build_xpl_package(files, compression=zipfile.ZIP_DEFLATED)
        buf = io.BytesIO(pkg_bytes)

        result = inspector.inspect(buf)
        assert result.is_valid is False
        assert result.status in (
            PackageInspectionStatus.BOMB_COMPRESSION_RATIO_EXCEEDED,
            PackageInspectionStatus.LIMIT_EXCEEDED,
        )
        assert any("compression ratio" in err.message.lower() for err in result.errors)


    def test_disallowed_file_extension(self, tmp_path: Path):
        """Archive containing forbidden executable or binary extension (.exe, .dll, .sh)."""
        forbidden_extensions = [
            "bin/malicious.exe",
            "bin/helper.dll",
            "scripts/run.sh",
            "scripts/install.bat",
            "plugin/adapter.pyc",
        ]
        for bad_path in forbidden_extensions:
            files = {
                "plugin/adapter.py": "class LionAdapter: pass\n",
                bad_path: "BINARY CONTENT",
            }
            pkg_bytes = build_xpl_package(files)
            result = inspect_package(io.BytesIO(pkg_bytes))
            assert result.is_valid is False
            assert result.status == PackageInspectionStatus.DISALLOWED_EXTENSION
            assert any(bad_path in err.message for err in result.errors)

    def test_path_traversal_relative_dot_dot(self, tmp_path: Path):
        """Zip-slip attempt with .. relative path."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("../etc/passwd", "root:x:0:0")
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.PATH_TRAVERSAL
        assert any("traversal" in err.message.lower() for err in result.errors)

    def test_path_traversal_absolute_leading_slash(self, tmp_path: Path):
        """Zip-slip attempt with absolute leading slash."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("/var/log/pwn.txt", "evil")
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.PATH_TRAVERSAL

    def test_path_traversal_windows_drive_letter(self, tmp_path: Path):
        """Zip-slip attempt with Windows drive letter."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("C:\\Windows\\System32\\evil.txt", "evil")
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status in (PackageInspectionStatus.PATH_TRAVERSAL, PackageInspectionStatus.DISALLOWED_EXTENSION)

    def test_case_collision_in_archive(self, tmp_path: Path):
        """Two files differing only by case (e.g. plugin/Adapter.py and plugin/adapter.py)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")
            zf.writestr("plugin/Adapter.py", "class LionAdapter2: pass\n")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.CASE_COLLISION
        assert any("collision" in err.message.lower() for err in result.errors)

    def test_duplicate_member_in_archive(self, tmp_path: Path):
        """Duplicate entry in archive central directory."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")
            # Directly append another entry with identical name
            zf.writestr("plugin/adapter.py", "class LionAdapterDuplicate: pass\n")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status in (PackageInspectionStatus.DUPLICATE_ENTRY, PackageInspectionStatus.CASE_COLLISION)

    def test_symlink_rejection(self, tmp_path: Path):
        """Symlink member in ZIP archive is rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("plugin/adapter.py", "class LionAdapter: pass\n")
            # Create a symlink entry (Unix mode 0o120777)
            zinfo = zipfile.ZipInfo("plugin/link.py")
            zinfo.create_system = 3  # Unix
            zinfo.external_attr = 0o120777 << 16  # S_IFLNK
            zf.writestr(zinfo, "adapter.py")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.SYMLINK_NOT_PERMITTED

    def test_windows_alternate_data_stream_rejected(self, tmp_path: Path):
        """Archive entry containing NTFS Alternate Data Stream syntax (colon) is rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
            zf.writestr("plugin/adapter.py:stream", "evil ads stream")

        result = inspect_package(buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.PATH_TRAVERSAL
        assert any("colon" in err.message.lower() for err in result.errors)

    def test_windows_reserved_device_names_rejected(self, tmp_path: Path):
        """Archive entries matching Windows DOS reserved device names are rejected."""
        bad_device_paths = [
            "con.py",
            "plugin/aux.py",
            "nul.txt",
            "com1/adapter.py",
            "lpt3.json",
        ]
        for dev_path in bad_device_paths:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
                zf.writestr(dev_path, "device content")

            result = inspect_package(buf.getvalue())
            assert result.is_valid is False
            assert result.status == PackageInspectionStatus.SPECIAL_FILE_PROHIBITED
            assert any("reserved device" in err.message.lower() for err in result.errors)

    def test_windows_trailing_dots_or_spaces_rejected(self, tmp_path: Path):
        """Archive entries with path segments ending in dot or space are rejected."""
        bad_trailing_paths = [
            "plugin./adapter.py",
            "plugin /adapter.py",
            "plugin/adapter.py.",
            "plugin/secret.txt ",
        ]
        for bad_p in bad_trailing_paths:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("manifest.json", json.dumps(make_valid_manifest_dict()))
                zf.writestr(bad_p, "trailing dot or space content")

            result = inspect_package(buf.getvalue())
            assert result.is_valid is False
            assert result.status == PackageInspectionStatus.PATH_TRAVERSAL
            assert any("trailing dot or space" in err.message.lower() for err in result.errors)



# ---------------------------------------------------------------------------
# Test Suite: META-INF/MANIFEST.MF Integrity Verification
# ---------------------------------------------------------------------------

class TestPackageInspectorManifestMFIntegrity:
    """Tests verifying per-file digests and integrity manifest rules."""

    def test_missing_manifest_mf(self, tmp_path: Path):
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files, include_manifest_mf=False)

        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_MF_NOT_FOUND

    def test_malformed_manifest_mf_syntax(self, tmp_path: Path):
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "META-INF/MANIFEST.MF": "NOT A VALID MANIFEST MF FORMAT : NO DIGESTS",
        }
        pkg_bytes = build_xpl_package(files, include_manifest_mf=False)

        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_MF_SYNTAX_ERROR

    def test_uncanonical_manifest_mf_ordering(self, tmp_path: Path):
        """MANIFEST.MF entries not sorted in lexicographical UTF-8 byte order."""
        files = {
            "b_second.py": "# second\n",
            "a_first.py": "# first\n",
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        # Force reverse ordering
        pkg_bytes = build_xpl_package(files, corrupt_manifest_mf_ordering=True)

        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_MF_ORDERING_ERROR
        assert any("lexicographical" in err.message.lower() for err in result.errors)

    def test_unlisted_file_in_archive(self, tmp_path: Path):
        """Archive contains a payload file that is omitted from MANIFEST.MF."""
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        # Build valid package, then inject an unlisted file
        pkg_bytes = build_xpl_package(files)
        buf = io.BytesIO(pkg_bytes)
        new_buf = io.BytesIO()
        with zipfile.ZipFile(buf, "r") as rzf, zipfile.ZipFile(new_buf, "w") as wzf:
            for item in rzf.infolist():
                wzf.writestr(item, rzf.read(item.filename))
            # Inject unlisted file
            wzf.writestr("plugin/unlisted_backdoor.py", "# unlisted!\n")

        result = inspect_package(new_buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.UNLISTED_FILE
        assert any("plugin/unlisted_backdoor.py" in err.message for err in result.errors)

    def test_missing_file_listed_in_manifest_mf(self, tmp_path: Path):
        """MANIFEST.MF lists a file that is absent from the archive."""
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        ghost_digest = "a" * 64
        pkg_bytes = build_xpl_package(files, extra_mf_entries={"plugin/ghost.py": ghost_digest})

        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MISSING_FILE
        assert any("plugin/ghost.py" in err.message for err in result.errors)

    def test_tampered_payload_digest_mismatch(self, tmp_path: Path):
        """File content tampered after digest computation (digest mismatch)."""
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        pkg_bytes = build_xpl_package(files)
        buf = io.BytesIO(pkg_bytes)
        tampered_buf = io.BytesIO()
        with zipfile.ZipFile(buf, "r") as rzf, zipfile.ZipFile(tampered_buf, "w") as wzf:
            for item in rzf.infolist():
                if item.filename == "plugin/adapter.py":
                    # Tamper content with newly calculated ZipInfo size so SIZE_MISMATCH doesn't mask DIGEST_MISMATCH
                    wzf.writestr("plugin/adapter.py", b"# TAMPERED CONTENT\n")
                else:
                    wzf.writestr(item, rzf.read(item.filename))

        result = inspect_package(tampered_buf.getvalue())
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.DIGEST_MISMATCH
        assert any("digest mismatch" in err.message.lower() for err in result.errors)


    def test_manifest_mf_referencing_forbidden_meta_inf_entry(self, tmp_path: Path):
        """MANIFEST.MF must not contain entries for META-INF/ itself."""
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        bad_entries = {"META-INF/MANIFEST.MF": "a" * 64}
        pkg_bytes = build_xpl_package(files, extra_mf_entries=bad_entries)

        result = inspect_package(pkg_bytes)
        assert result.is_valid is False
        assert result.status in (
            PackageInspectionStatus.MANIFEST_MF_SYNTAX_ERROR,
            PackageInspectionStatus.MANIFEST_MF_ORDERING_ERROR,
        )


# ---------------------------------------------------------------------------
# Test Suite: Static Entry-Point Verification
# ---------------------------------------------------------------------------

class TestPackageInspectorEntryPointVerification:
    """Tests confirming static verification of entry-point presence without importing."""

    def test_missing_entry_point_file_rejected(self, tmp_path: Path):
        """Manifest declares entry_point plugin.nonexistent:Adapter, but file is absent."""
        m = make_valid_manifest_dict(entry_point="plugin.nonexistent:Adapter")
        files = {
            "plugin/adapter.py": "class RealAdapter: pass\n",
        }
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "missing_entry_file.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.ENTRY_POINT_NOT_FOUND
        assert any("entry point" in err.message.lower() and "not found" in err.message.lower() for err in result.errors)


    def test_malformed_entry_point_format_rejected(self, tmp_path: Path):
        """Manifest declares invalid entry_point without colon separator."""
        m = make_valid_manifest_dict(entry_point="invalid_format_without_colon")
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
        }
        pkg_bytes = build_xpl_package(files, manifest_dict=m)
        pkg_file = tmp_path / "bad_entry_point.xpl"
        pkg_file.write_bytes(pkg_bytes)

        result = inspect_package(pkg_file)
        assert result.is_valid is False
        assert result.status == PackageInspectionStatus.MANIFEST_SCHEMA_ERROR


# ---------------------------------------------------------------------------
# Test Suite: Non-Execution & Inertness Guarantees
# ---------------------------------------------------------------------------

class TestPackageInspectorNonExecutionGuarantees:
    """
    Critical security tests verifying that package inspection:
    1. NEVER executes Python code from the archive.
    2. NEVER imports any module into sys.modules.
    3. NEVER extracts files to disk.
    4. NEVER mutates VendorRegistry.
    """

    def test_malicious_code_is_not_executed_or_imported(self, tmp_path: Path):
        """
        Package contains malicious python code with top-level exceptions and system calls.
        Inspection must succeed or fail strictly via static rules without running the code.
        """
        malicious_code = (
            "import sys\n"
            "sys.__omnix_malicious_marker__ = True\n"
            "raise RuntimeError('FATAL: MALICIOUS CODE EXECUTED!')\n"
        )
        files = {
            "plugin/__init__.py": "# harmless\n",
            "plugin/adapter.py": malicious_code,
        }
        pkg_bytes = build_xpl_package(files)

        # Clear marker before test
        if hasattr(sys, "__omnix_malicious_marker__"):
            delattr(sys, "__omnix_malicious_marker__")

        modules_before = set(sys.modules.keys())

        # Perform inspection
        result = inspect_package(pkg_bytes)

        # 1. Inspection completed without RuntimeError being raised
        assert result.is_valid is True

        # 2. Malicious code was NOT executed
        assert not hasattr(sys, "__omnix_malicious_marker__")

        # 3. No module from the package was loaded into sys.modules
        modules_after = set(sys.modules.keys())
        new_modules = modules_after - modules_before
        assert not any("plugin" in m for m in new_modules)
        assert "plugin.adapter" not in sys.modules

    def test_inspection_does_not_extract_files_to_disk(self, tmp_path: Path):
        """Inspect a package and confirm no files are created outside of the input archive."""
        files = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "plugin/secret.txt": "Secret content\n",
        }
        pkg_bytes = build_xpl_package(files)
        pkg_file = tmp_path / "lion.xpl"
        pkg_file.write_bytes(pkg_bytes)

        # Record directory contents before
        files_before = set(tmp_path.rglob("*"))

        result = inspect_package(pkg_file)
        assert result.is_valid is True

        # Record directory contents after
        files_after = set(tmp_path.rglob("*"))
        # Only the original .xpl file should exist
        assert files_after == files_before

    def test_inspection_does_not_mutate_vendor_registry(self, tmp_path: Path):
        """Inspecting a package must leave VendorRegistry completely untouched."""
        from core.errors import UnknownVendorError

        reg = VendorRegistry()
        initial_vendors = reg.list_vendors()
        initial_routes = dict(reg._domain_to_route)

        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)

        result = inspect_package(pkg_bytes)
        assert result.is_valid is True

        # Verify registry unchanged
        assert reg.list_vendors() == initial_vendors
        assert reg._domain_to_route == initial_routes
        with pytest.raises(UnknownVendorError):
            reg.get_adapter("vendor_lion")


    def test_package_inspection_exception_raise_if_invalid(self, tmp_path: Path):
        """raise_if_invalid() raises PackageInspectionException on failure, returns result on success."""
        # Valid package returns result
        files = {"plugin/adapter.py": "class LionAdapter: pass\n"}
        pkg_bytes = build_xpl_package(files)
        res = inspect_package(pkg_bytes)
        assert res.raise_if_invalid() is res

        # Invalid package raises
        corrupted = b"corrupted"
        res_bad = inspect_package(corrupted)
        with pytest.raises(PackageInspectionException) as excinfo:
            res_bad.raise_if_invalid()
        assert excinfo.value.status == PackageInspectionStatus.CORRUPTED_ARCHIVE
        assert len(excinfo.value.errors) > 0


# ---------------------------------------------------------------------------
# Test Suite: Reconciled Limits, Boundaries & Extension Whitelist
# ---------------------------------------------------------------------------

class TestPackageInspectorReconciliationBoundariesAndWhitelist:
    """
    Focused reconciliation tests for Phase 4 archive limits, binary vs decimal units,
    strict boundary checks (immediately below, at, and above thresholds),
    authoritative MANIFEST.MF format verification, and strict extension whitelist.
    """

    def test_authoritative_binary_limits_constants(self):
        """Verify archive limits match authoritative specification using binary (IEC) units."""
        from core.plugins.package_inspector import (
            MAX_COMPRESSED_SIZE_BYTES,
            MAX_UNCOMPRESSED_TOTAL_BYTES,
            MAX_UNCOMPRESSED_ENTRY_BYTES,
            MAX_COMPRESSION_RATIO,
            RATIO_CHECK_MIN_ENTRY_BYTES,
            MAX_ENTRY_COUNT,
        )

        # 10 MiB compressed archive size limit
        assert MAX_COMPRESSED_SIZE_BYTES == 10 * 1024 * 1024
        assert MAX_COMPRESSED_SIZE_BYTES == 10_485_760
        assert MAX_COMPRESSED_SIZE_BYTES != 10_000_000  # Must be binary MiB, not decimal MB

        # 50 MiB cumulative uncompressed size limit
        assert MAX_UNCOMPRESSED_TOTAL_BYTES == 50 * 1024 * 1024
        assert MAX_UNCOMPRESSED_TOTAL_BYTES == 52_428_800
        assert MAX_UNCOMPRESSED_TOTAL_BYTES != 50_000_000

        # 20 MiB single entry uncompressed size limit
        assert MAX_UNCOMPRESSED_ENTRY_BYTES == 20 * 1024 * 1024
        assert MAX_UNCOMPRESSED_ENTRY_BYTES == 20_971_520
        assert MAX_UNCOMPRESSED_ENTRY_BYTES != 20_000_000

        # 10:1 maximum compression ratio
        assert MAX_COMPRESSION_RATIO == 10.0

        # 1 MiB threshold for compression ratio check
        assert RATIO_CHECK_MIN_ENTRY_BYTES == 1 * 1024 * 1024
        assert RATIO_CHECK_MIN_ENTRY_BYTES == 1_048_576
        assert RATIO_CHECK_MIN_ENTRY_BYTES != 1_000_000

        # 500 maximum archive entry count
        assert MAX_ENTRY_COUNT == 500

    def test_compressed_archive_size_boundary_below_at_above(self, tmp_path: Path):
        """Test compressed archive size immediately below, at, and above threshold."""
        # 1. Custom threshold boundary test
        inspector = PackageInspector(max_compressed_size_bytes=1000)

        # Below threshold (999 bytes)
        res_below = inspector.inspect(b"PK\x05\x06" + b"\x00" * 995)
        assert res_below.status != PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED

        # At threshold (1000 bytes)
        res_at = inspector.inspect(b"PK\x05\x06" + b"\x00" * 996)
        assert res_at.status != PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED

        # Above threshold (1001 bytes)
        res_above = inspector.inspect(b"PK\x05\x06" + b"\x00" * 997)
        assert res_above.status == PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED
        assert any("compressed size" in err.message.lower() for err in res_above.errors)

        # 2. File-level boundary test on full 10 MiB limit
        default_inspector = PackageInspector()
        file_at = tmp_path / "at_limit.xpl"
        with open(file_at, "wb") as f:
            f.seek(MAX_COMPRESSED_SIZE_BYTES - 1)
            f.write(b"\x00")
        assert file_at.stat().st_size == MAX_COMPRESSED_SIZE_BYTES
        res_file_at = default_inspector.inspect_file(file_at)
        assert res_file_at.status != PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED

        file_above = tmp_path / "above_limit.xpl"
        with open(file_above, "wb") as f:
            f.seek(MAX_COMPRESSED_SIZE_BYTES)
            f.write(b"\x00")
        assert file_above.stat().st_size == MAX_COMPRESSED_SIZE_BYTES + 1
        res_file_above = default_inspector.inspect_file(file_above)
        assert res_file_above.status == PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED
        assert any("compressed size" in err.message.lower() for err in res_file_above.errors)

    def test_archive_entry_count_boundary_below_at_above(self):
        """Test archive entry count immediately below, at, and above threshold."""
        # Custom boundary threshold = 4 entries
        inspector = PackageInspector(max_entry_count=4)

        # 3 entries (below)
        files_3 = {"manifest.json": "{}", "META-INF/MANIFEST.MF": "", "plugin/adapter.py": ""}
        buf_3 = io.BytesIO()
        with zipfile.ZipFile(buf_3, "w") as zf:
            for k, v in files_3.items():
                zf.writestr(k, v)
        res_3 = inspector.inspect(buf_3.getvalue())
        assert res_3.status != PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED

        # 4 entries (at threshold)
        files_4 = dict(files_3, **{"plugin/helper.py": ""})
        buf_4 = io.BytesIO()
        with zipfile.ZipFile(buf_4, "w") as zf:
            for k, v in files_4.items():
                zf.writestr(k, v)
        res_4 = inspector.inspect(buf_4.getvalue())
        assert res_4.status != PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED

        # 5 entries (above threshold)
        files_5 = dict(files_4, **{"plugin/extra.py": ""})
        buf_5 = io.BytesIO()
        with zipfile.ZipFile(buf_5, "w") as zf:
            for k, v in files_5.items():
                zf.writestr(k, v)
        res_5 = inspector.inspect(buf_5.getvalue())
        assert res_5.status == PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED
        assert any("member count" in err.message.lower() for err in res_5.errors)

    def test_single_entry_uncompressed_size_boundary_below_at_above(self):
        """Test single entry uncompressed size immediately below, at, and above limit."""
        # Using custom threshold of 100 bytes
        inspector = PackageInspector(max_uncompressed_entry_bytes=100)

        # Create zip with entry of 99 bytes (below)
        buf_below = io.BytesIO()
        with zipfile.ZipFile(buf_below, "w") as zf:
            zf.writestr("manifest.json", "X" * 99)
        res_below = inspector.inspect(buf_below.getvalue())
        assert not any("uncompressed size" in err.message.lower() and "exceeds" in err.message.lower() for err in res_below.errors)

        # Create zip with entry of 100 bytes (at threshold)
        buf_at = io.BytesIO()
        with zipfile.ZipFile(buf_at, "w") as zf:
            zf.writestr("manifest.json", "X" * 100)
        res_at = inspector.inspect(buf_at.getvalue())
        assert not any("uncompressed size" in err.message.lower() and "exceeds" in err.message.lower() for err in res_at.errors)

        # Create zip with entry of 101 bytes (above threshold)
        buf_above = io.BytesIO()
        with zipfile.ZipFile(buf_above, "w") as zf:
            zf.writestr("manifest.json", "X" * 101)
        res_above = inspector.inspect(buf_above.getvalue())
        assert res_above.status == PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED
        assert any("uncompressed size" in err.message.lower() for err in res_above.errors)

    def test_total_uncompressed_size_boundary_below_at_above(self):
        """Test cumulative uncompressed size immediately below, at, and above limit."""
        # Using custom total threshold of 200 bytes
        inspector = PackageInspector(max_total_uncompressed_bytes=200, max_uncompressed_entry_bytes=150)

        # Total 199 bytes (below)
        buf_below = io.BytesIO()
        with zipfile.ZipFile(buf_below, "w") as zf:
            zf.writestr("manifest.json", "X" * 100)
            zf.writestr("plugin/adapter.py", "Y" * 99)
        res_below = inspector.inspect(buf_below.getvalue())
        assert not any("cumulative uncompressed size" in err.message.lower() for err in res_below.errors)

        # Total 200 bytes (at threshold)
        buf_at = io.BytesIO()
        with zipfile.ZipFile(buf_at, "w") as zf:
            zf.writestr("manifest.json", "X" * 100)
            zf.writestr("plugin/adapter.py", "Y" * 100)
        res_at = inspector.inspect(buf_at.getvalue())
        assert not any("cumulative uncompressed size" in err.message.lower() for err in res_at.errors)

        # Total 201 bytes (above threshold)
        buf_above = io.BytesIO()
        with zipfile.ZipFile(buf_above, "w") as zf:
            zf.writestr("manifest.json", "X" * 100)
            zf.writestr("plugin/adapter.py", "Y" * 101)
        res_above = inspector.inspect(buf_above.getvalue())
        assert res_above.status == PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED
        assert any("cumulative uncompressed size" in err.message.lower() for err in res_above.errors)

    def test_compression_ratio_boundary_and_threshold(self):
        """
        Verify that compression ratio check (>10:1) is ONLY enforced for entries exceeding 1 MiB.
        Entries <= 1 MiB must NOT trigger the ratio check regardless of ratio.
        Entries > 1 MiB must trigger if ratio > 10.0:1.
        """
        inspector = PackageInspector(
            max_compression_ratio=10.0,
            ratio_check_min_entry_bytes=1000,
        )

        # Entry <= threshold (1000 bytes) with extreme compression ratio (e.g. 50:1)
        # Should NOT trigger compression ratio check
        repeating_below = b"A" * 1000
        files_below = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "plugin/small_compressed.txt": repeating_below,
        }
        pkg_below = build_xpl_package(files_below, compression=zipfile.ZIP_DEFLATED)
        res_below = inspector.inspect(pkg_below)
        assert not any("compression ratio" in err.message.lower() for err in res_below.errors)

        # Entry > threshold (1001 bytes) with extreme compression ratio > 10:1
        # Should trigger compression ratio check
        repeating_above = b"A" * 20000  # Compresses to ~100 bytes, ratio ~200:1
        files_above = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "plugin/bomb.txt": repeating_above,
        }
        pkg_above = build_xpl_package(files_above, compression=zipfile.ZIP_DEFLATED)
        res_above = inspector.inspect(pkg_above)
        assert res_above.status == PackageInspectionStatus.BOMB_COMPRESSION_RATIO_EXCEEDED
        assert any("compression ratio" in err.message.lower() for err in res_above.errors)

    def test_authoritative_extension_whitelist_and_prohibited_types(self):
        """
        Verify the exact 11-extension whitelist from Section 4.3:
        {".py", ".json", ".png", ".jpg", ".jpeg", ".svg", ".md", ".txt", ".mf", ".sig", ".crt"}
        Reject unauthorized extensions mistakenly reported (.csv, .yaml, .yml, .ico, .css, .qss)
        and extensionless files.
        """
        # Exact whitelist comparison
        expected_whitelist = frozenset({
            ".py", ".json", ".png", ".jpg", ".jpeg", ".svg",
            ".md", ".txt", ".mf", ".sig", ".crt"
        })
        assert ALLOWED_FILE_EXTENSIONS == expected_whitelist

        # Valid files with allowed extensions (including uppercase variations and metadata)
        valid_extensions = [
            "plugin/adapter.py",
            "assets/schema.JSON",
            "assets/logo.png",
            "assets/photo.JPG",
            "assets/banner.jpeg",
            "assets/diagram.svg",
            "docs/README.md",
            "docs/notes.TXT",
            "META-INF/MANIFEST.MF",
            "META-INF/SIGNATURE.SIG",
            "META-INF/CERTIFICATE.CRT",
        ]
        for vpath in valid_extensions:
            ext = posixpath.splitext(vpath)[1].lower()
            assert ext in ALLOWED_FILE_EXTENSIONS, f"Expected {vpath} extension {ext} to be allowed"

        # Forbidden extensions (including those mistakenly cited in prior textual reports)
        forbidden_paths = [
            "data/inventory.csv",
            "config/settings.yaml",
            "config/rules.yml",
            "assets/icon.ico",
            "theme/styles.css",
            "theme/theme.qss",
            "bin/binary.exe",
            "bin/lib.dll",
            "bin/module.pyd",
            "scripts/run.sh",
            "scripts/run.bat",
            "LICENSE",         # extensionless
            "README",          # extensionless
        ]
        for fpath in forbidden_paths:
            files = {
                "plugin/adapter.py": "class LionAdapter: pass\n",
                fpath: "sample content\n",
            }
            pkg_bytes = build_xpl_package(files)
            res = inspect_package(pkg_bytes)
            assert res.is_valid is False
            assert res.status == PackageInspectionStatus.PROHIBITED_FILE_EXTENSION
            assert any(fpath in err.message for err in res.errors)

    def test_reconcile_manifest_mf_format_strictness(self):
        """
        Verify that META-INF/MANIFEST.MF strictly requires the authoritative format
        from Section 9.2:
        'File: <path>'
        'SHA-256-Digest: <64-char-hex>'
        separated by blank lines, and rejects JAR-style headers and Base64 digests.
        """
        # 1. Reject JAR-style Manifest-Version header
        jar_style_manifest = (
            "Manifest-Version: 1.0\n"
            "Created-By: Omnix Package Tool\n"
            "\n"
            "Name: manifest.json\n"
            "SHA-256-Digest: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
        )
        files_jar = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "META-INF/MANIFEST.MF": jar_style_manifest,
        }
        pkg_jar = build_xpl_package(files_jar, include_manifest_mf=False)
        res_jar = inspect_package(pkg_jar)
        assert res_jar.is_valid is False
        assert res_jar.status == PackageInspectionStatus.MALFORMED_INTEGRITY_MANIFEST
        assert any("unrecognized header 'manifest-version'" in err.message.lower() for err in res_jar.errors)

        # 2. Reject Base64-encoded digest (44 chars with base64 padding)
        base64_digest_manifest = (
            "File: plugin/adapter.py\n"
            "SHA-256-Digest: 47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=\n"
        )
        files_b64 = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "META-INF/MANIFEST.MF": base64_digest_manifest,
        }
        pkg_b64 = build_xpl_package(files_b64, include_manifest_mf=False)
        res_b64 = inspect_package(pkg_b64)
        assert res_b64.is_valid is False
        assert res_b64.status == PackageInspectionStatus.MALFORMED_INTEGRITY_MANIFEST
        assert any("expected 64 hex characters" in err.message.lower() for err in res_b64.errors)

        # 3. Reject declaring files inside META-INF/ in MANIFEST.MF
        meta_inf_declared_manifest = (
            "File: META-INF/SIGNATURE.SIG\n"
            "SHA-256-Digest: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        )
        files_meta = {
            "plugin/adapter.py": "class LionAdapter: pass\n",
            "META-INF/MANIFEST.MF": meta_inf_declared_manifest,
        }
        pkg_meta = build_xpl_package(files_meta, include_manifest_mf=False)
        res_meta = inspect_package(pkg_meta)
        assert res_meta.is_valid is False
        assert res_meta.status == PackageInspectionStatus.MALFORMED_INTEGRITY_MANIFEST
        assert any("meta-inf" in err.message.lower() for err in res_meta.errors)

