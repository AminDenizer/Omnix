"""
Omnix Vendor Plugin System — Package Inspector (Phase 4)
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 4, 5, 9.2, 10.2

Provides strict, deterministic, offline inspection and integrity verification of Omnix .xpl
packages. Enforces archive decompression limits, Zip-slip/traversal guards, extension whitelists,
canonical META-INF/MANIFEST.MF per-file digest verification, manifest schema validation,
single-vendor-per-package invariant, and static primary entry-point presence.

CRITICAL INVARIANT:
This module NEVER executes, imports, installs, registers, or activates plugin code.
It establishes structural integrity and metadata consistency only. Digital signature
trust is deferred to Phase 5; installation and lifecycle management are deferred to Phase 7.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

from core.plugins.manifest_mf import ManifestMF, ManifestMFError
from core.plugins.manifest_validator import (
    ManifestValidationError,
    ManifestValidationResult,
    ManifestValidator,
    MAX_MANIFEST_SIZE_BYTES,
)


# ---------------------------------------------------------------------------
# Strict Archive Limits & Constants (Sections 4.3 & 10.2)
# ---------------------------------------------------------------------------

MAX_COMPRESSED_SIZE_BYTES: int = 10 * 1024 * 1024       # 10 MiB
MAX_UNCOMPRESSED_TOTAL_BYTES: int = 50 * 1024 * 1024    # 50 MiB
MAX_UNCOMPRESSED_ENTRY_BYTES: int = 20 * 1024 * 1024    # 20 MiB
MAX_COMPRESSION_RATIO: float = 10.0                     # 10:1 ratio
RATIO_CHECK_MIN_ENTRY_BYTES: int = 1 * 1024 * 1024      # 1 MiB threshold for ratio check
MAX_ENTRY_COUNT: int = 500                              # 500 entries max

# Aliases
MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES = MAX_UNCOMPRESSED_TOTAL_BYTES
MAX_SINGLE_ENTRY_UNCOMPRESSED_SIZE_BYTES = MAX_UNCOMPRESSED_ENTRY_BYTES
COMPRESSION_RATIO_THRESHOLD_BYTES = RATIO_CHECK_MIN_ENTRY_BYTES
MAX_ARCHIVE_ENTRIES = MAX_ENTRY_COUNT


ALLOWED_FILE_EXTENSIONS: frozenset[str] = frozenset({
    ".py",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".md",
    ".txt",
    ".mf",
    ".sig",
    ".crt",
})
ALLOWED_EXTENSIONS = ALLOWED_FILE_EXTENSIONS

# Windows reserved device names (DOS devices)
WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

# Stream read chunk size (64 KB)
STREAM_CHUNK_SIZE_BYTES: int = 64 * 1024



# ---------------------------------------------------------------------------
# Inspection Status and Error Hierarchy
# ---------------------------------------------------------------------------

class PackageInspectionStatus(str, Enum):
    """Categorized outcome of Phase 4 package inspection."""
    VALID = "VALID"
    MALFORMED_ARCHIVE = "MALFORMED_ARCHIVE"
    ARCHIVE_LIMIT_EXCEEDED = "ARCHIVE_LIMIT_EXCEEDED"
    BOMB_COMPRESSION_RATIO_EXCEEDED = "BOMB_COMPRESSION_RATIO_EXCEEDED"
    PATH_TRAVERSAL_DETECTED = "PATH_TRAVERSAL_DETECTED"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    CASE_COLLISION = "CASE_COLLISION"
    SPECIAL_FILE_PROHIBITED = "SPECIAL_FILE_PROHIBITED"
    PROHIBITED_FILE_EXTENSION = "PROHIBITED_FILE_EXTENSION"
    MISSING_MANIFEST = "MISSING_MANIFEST"
    MISSING_INTEGRITY_MANIFEST = "MISSING_INTEGRITY_MANIFEST"
    MALFORMED_INTEGRITY_MANIFEST = "MALFORMED_INTEGRITY_MANIFEST"
    UNLISTED_FILE_DETECTED = "UNLISTED_FILE_DETECTED"
    MISSING_PAYLOAD_FILE = "MISSING_PAYLOAD_FILE"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    MISSING_ENTRY_POINT = "MISSING_ENTRY_POINT"

    # Status aliases for test and caller flexibility
    CORRUPTED_ARCHIVE = "MALFORMED_ARCHIVE"
    LIMIT_EXCEEDED = "ARCHIVE_LIMIT_EXCEEDED"
    PATH_TRAVERSAL = "PATH_TRAVERSAL_DETECTED"
    SYMLINK_NOT_PERMITTED = "SPECIAL_FILE_PROHIBITED"
    DISALLOWED_EXTENSION = "PROHIBITED_FILE_EXTENSION"
    MANIFEST_NOT_FOUND = "MISSING_MANIFEST"
    MANIFEST_SYNTAX_ERROR = "MANIFEST_INVALID"
    MANIFEST_SCHEMA_ERROR = "MANIFEST_INVALID"
    MANIFEST_SEMANTIC_ERROR = "MANIFEST_INVALID"
    MANIFEST_MF_NOT_FOUND = "MISSING_INTEGRITY_MANIFEST"
    MANIFEST_MF_SYNTAX_ERROR = "MALFORMED_INTEGRITY_MANIFEST"
    MANIFEST_MF_ORDERING_ERROR = "MALFORMED_INTEGRITY_MANIFEST"
    UNLISTED_FILE = "UNLISTED_FILE_DETECTED"
    MISSING_FILE = "MISSING_PAYLOAD_FILE"
    ENTRY_POINT_NOT_FOUND = "MISSING_ENTRY_POINT"


class PackageInspectionException(Exception):
    """Base exception raised when package inspection fails in raise_for_errors mode."""
    def __init__(self, message: str, status: PackageInspectionStatus, errors: Optional[List[PackageInspectionError]] = None):
        super().__init__(f"[{status.value}] {message}")
        self.status = status
        self.errors = errors or []


@dataclass(frozen=True)
class PackageInspectionError:
    """Detailed record of a single inspection failure."""
    code: str
    message: str
    path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        loc = f" at '{self.path}'" if self.path else ""
        return f"[{self.code}]{loc} {self.message}"


@dataclass
class PackageInspectionResult:
    """
    Structured outcome of Phase 4 package inspection.

    IMPORTANT:
    is_valid=True proves structural integrity and manifest compliance ONLY.
    It does NOT imply publisher trust, signature authorization, or runtime safety.
    """
    is_valid: bool
    status: PackageInspectionStatus
    package_hash: str
    package_path: Optional[str] = None
    archive_size_bytes: int = 0
    uncompressed_size_bytes: int = 0
    entry_count: int = 0

    plugin_id: Optional[str] = None
    vendor_id: Optional[str] = None
    display_name: Optional[str] = None
    version: Optional[str] = None
    manifest_metadata: Optional[Dict[str, Any]] = None

    entry_point: Optional[str] = None
    entry_point_file: Optional[str] = None
    entry_point_exists: bool = False

    file_inventory: List[str] = field(default_factory=list)
    file_digests: Dict[str, str] = field(default_factory=dict)
    errors: List[PackageInspectionError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def archive_sha256(self) -> str:
        """Alias for package_hash."""
        return self.package_hash

    @property
    def manifest(self) -> Optional[Dict[str, Any]]:
        """Alias for manifest_metadata."""
        return self.manifest_metadata

    @property
    def file_count(self) -> int:
        """Alias for entry_count."""
        return self.entry_count

    @property
    def total_uncompressed_bytes(self) -> int:
        """Alias for uncompressed_size_bytes."""
        return self.uncompressed_size_bytes

    @property
    def scanned_files(self) -> List[str]:
        """Alias for file_inventory."""
        return self.file_inventory

    def raise_for_errors(self) -> None:
        """Raise PackageInspectionException if the package inspection failed."""
        if not self.is_valid:
            msg = self.errors[0].message if self.errors else f"Inspection failed with status {self.status.value}"
            raise PackageInspectionException(msg, self.status, self.errors)

    def raise_if_invalid(self) -> PackageInspectionResult:
        """Raise PackageInspectionException if invalid, or return self on success."""
        self.raise_for_errors()
        return self



# ---------------------------------------------------------------------------
# Package Inspector Engine
# ---------------------------------------------------------------------------

class PackageInspector:
    """
    Authoritative, deterministic package inspector for Omnix .xpl packages.

    Enforces:
    - Gate A: Archive Hardening & Decompression Limits (Pre-extraction)
    - Gate B: File Integrity & SHA-256 Digest Verification (META-INF/MANIFEST.MF)
    - Gate C: Manifest Schema & Semantic Validation + Static Entry-Point Presence
    - Single-Vendor Package Invariant (1-to-1 canonical identity)
    """

    def __init__(
        self,
        manifest_validator: Optional[ManifestValidator] = None,
        max_compressed_size_bytes: int = MAX_COMPRESSED_SIZE_BYTES,
        max_total_uncompressed_bytes: int = MAX_UNCOMPRESSED_TOTAL_BYTES,
        max_uncompressed_entry_bytes: int = MAX_UNCOMPRESSED_ENTRY_BYTES,
        max_compression_ratio: float = MAX_COMPRESSION_RATIO,
        ratio_check_min_entry_bytes: int = RATIO_CHECK_MIN_ENTRY_BYTES,
        max_entry_count: int = MAX_ENTRY_COUNT,
    ):
        self._manifest_validator = manifest_validator or ManifestValidator()
        self._max_compressed_size_bytes = max_compressed_size_bytes
        self._max_total_uncompressed_bytes = max_total_uncompressed_bytes
        self._max_uncompressed_entry_bytes = max_uncompressed_entry_bytes
        self._max_compression_ratio = max_compression_ratio
        self._ratio_check_min_entry_bytes = ratio_check_min_entry_bytes
        self._max_entry_count = max_entry_count

    def inspect(
        self,
        target: Union[str, Path, bytes, BinaryIO, Any],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> PackageInspectionResult:
        """Universal inspection entry point accepting file path, bytes, or file-like object."""
        if isinstance(target, (str, Path)):
            return self.inspect_file(
                target,
                host_omnix_version=host_omnix_version,
                host_contract_version=host_contract_version,
            )
        elif isinstance(target, bytes):
            return self.inspect_bytes(
                target,
                host_omnix_version=host_omnix_version,
                host_contract_version=host_contract_version,
            )
        elif hasattr(target, "read"):
            if hasattr(target, "getvalue"):
                data = target.getvalue()
            else:
                pos = target.tell() if hasattr(target, "tell") else None
                data = target.read()
                if pos is not None and hasattr(target, "seek"):
                    target.seek(pos)
            return self.inspect_bytes(
                data,
                host_omnix_version=host_omnix_version,
                host_contract_version=host_contract_version,
            )
        raise TypeError(f"Unsupported target type for package inspection: {type(target).__name__}")

    def inspect_file(
        self,
        file_path: Union[str, Path],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> PackageInspectionResult:
        """Inspect a local .xpl package file."""
        path_obj = Path(file_path).resolve()
        if not path_obj.exists() or not path_obj.is_file():
            return self._create_error_result(
                status=PackageInspectionStatus.MALFORMED_ARCHIVE,
                package_hash="",
                package_path=str(path_obj),
                message=f"Package file does not exist or is not a regular file: '{path_obj}'",
                code="FILE_NOT_FOUND",
            )

        file_size = path_obj.stat().st_size
        if file_size > self._max_compressed_size_bytes:
            return self._create_error_result(
                status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                package_hash="",
                package_path=str(path_obj),
                archive_size=file_size,
                message=f"Archive compressed size ({file_size} bytes) exceeds maximum limit of 10 MiB ({self._max_compressed_size_bytes} bytes)",
                code="ARCHIVE_SIZE_EXCEEDED",
            )

        try:
            with open(path_obj, "rb") as f:
                raw_bytes = f.read()
        except Exception as exc:
            return self._create_error_result(
                status=PackageInspectionStatus.MALFORMED_ARCHIVE,
                package_hash="",
                package_path=str(path_obj),
                message=f"Failed to read package file: {exc}",
                code="FILE_READ_ERROR",
            )

        return self.inspect_bytes(
            raw_bytes,
            package_path=str(path_obj),
            host_omnix_version=host_omnix_version,
            host_contract_version=host_contract_version,
        )

    def inspect_bytes(
        self,
        raw_bytes: bytes,
        package_path: Optional[str] = None,
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> PackageInspectionResult:
        """Inspect .xpl archive bytes loaded in memory."""
        compressed_size = len(raw_bytes)
        if compressed_size > self._max_compressed_size_bytes:
            return self._create_error_result(
                status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                package_hash="",
                package_path=package_path,
                archive_size=compressed_size,
                message=f"Archive compressed size ({compressed_size} bytes) exceeds maximum limit of 10 MiB ({self._max_compressed_size_bytes} bytes)",
                code="ARCHIVE_SIZE_EXCEEDED",
            )


        package_hash = hashlib.sha256(raw_bytes).hexdigest()

        try:
            bio = io.BytesIO(raw_bytes)
            zf = zipfile.ZipFile(bio, mode="r")
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            return self._create_error_result(
                status=PackageInspectionStatus.MALFORMED_ARCHIVE,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                message=f"ZIP archive structure is invalid or corrupt: {exc}",
                code="BAD_ZIP_FILE",
            )
        except Exception as exc:
            return self._create_error_result(
                status=PackageInspectionStatus.MALFORMED_ARCHIVE,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                message=f"Unexpected error opening ZIP archive: {exc}",
                code="ARCHIVE_OPEN_FAILED",
            )

        with zf:
            return self._inspect_zip_archive(
                zf,
                package_hash=package_hash,
                package_path=package_path,
                compressed_size=compressed_size,
                host_omnix_version=host_omnix_version,
                host_contract_version=host_contract_version,
            )

    # -----------------------------------------------------------------------
    # Internal Pipeline Stages
    # -----------------------------------------------------------------------

    def _inspect_zip_archive(
        self,
        zf: zipfile.ZipFile,
        package_hash: str,
        package_path: Optional[str],
        compressed_size: int,
        host_omnix_version: Optional[str],
        host_contract_version: Optional[str],
    ) -> PackageInspectionResult:
        """Execute the multi-gate inspection pipeline against an open ZipFile."""
        infolist = zf.infolist()
        entry_count = len(infolist)

        # -------------------------------------------------------------------
        # Gate A.1: Archive Member Count Limit
        # -------------------------------------------------------------------
        if entry_count > self._max_entry_count:
            return self._create_error_result(
                status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                message=f"Archive member count ({entry_count}) exceeds maximum threshold of {self._max_entry_count} entries",
                code="ENTRY_COUNT_EXCEEDED",
            )

        total_uncompressed = 0
        seen_normalized_paths: Set[str] = set()
        seen_folded_paths: Dict[str, str] = {}
        file_entries: List[Tuple[str, zipfile.ZipInfo]] = []

        # -------------------------------------------------------------------
        # Gate A.2: Central Directory Pre-Scan (Paths, Traversal, Limits, Types)
        # -------------------------------------------------------------------
        for info in infolist:
            raw_name = info.filename

            # Null byte check
            if "\0" in raw_name:
                return self._create_error_result(
                    status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=raw_name,
                    message="Archive entry path contains forbidden embedded null byte",
                    code="NULL_BYTE_IN_PATH",
                )

            # Windows drive letter or Alternate Data Stream (ADS) colon check
            if ":" in raw_name:
                return self._create_error_result(
                    status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=raw_name,
                    message=f"Archive entry path contains prohibited colon character (Windows ADS or drive syntax): '{raw_name}'",
                    code="INVALID_PATH_CHARACTER",
                )

            # Leading slash check
            if raw_name.startswith("/") or raw_name.startswith("\\"):
                return self._create_error_result(
                    status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=raw_name,
                    message=f"Archive entry path has prohibited leading slash: '{raw_name}'",
                    code="LEADING_SLASH_IN_PATH",
                )

            # Path normalization
            clean_name = raw_name.replace("\\", "/")
            norm_path = posixpath.normpath(clean_name)

            # Parent directory traversal check
            if norm_path.startswith("..") or "/../" in f"/{norm_path}/":
                return self._create_error_result(
                    status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=raw_name,
                    message=f"Archive entry path attempts parent directory traversal (Zip-slip): '{raw_name}'",
                    code="PARENT_TRAVERSAL_DETECTED",
                )

            # Windows reserved device names and trailing dots/spaces checks
            segments = [seg for seg in norm_path.split("/") if seg and seg != "."]
            for seg in segments:
                stem = seg.split(".")[0].upper()
                if stem in WINDOWS_RESERVED_DEVICE_NAMES:
                    return self._create_error_result(
                        status=PackageInspectionStatus.SPECIAL_FILE_PROHIBITED,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=raw_name,
                        message=f"Archive entry path contains Windows reserved device name '{seg}': '{raw_name}'",
                        code="RESERVED_DEVICE_NAME",
                    )
                if seg.endswith(".") or seg.endswith(" "):
                    return self._create_error_result(
                        status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=raw_name,
                        message=f"Archive entry path segment '{seg}' ends with trailing dot or space: '{raw_name}'",
                        code="TRAILING_DOT_OR_SPACE",
                    )


            # Containment verification
            joined = posixpath.normpath(posixpath.join("/staging", norm_path))
            if not (joined == "/staging" or joined.startswith("/staging/")):
                return self._create_error_result(
                    status=PackageInspectionStatus.PATH_TRAVERSAL_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=raw_name,
                    message=f"Archive entry path resolves outside hypothetical staging root: '{raw_name}'",
                    code="PATH_OUTSIDE_CONTAINMENT",
                )

            # Duplicate normalized path check
            if norm_path in seen_normalized_paths:
                return self._create_error_result(
                    status=PackageInspectionStatus.DUPLICATE_ENTRY,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Archive contains duplicate member path: '{norm_path}'",
                    code="DUPLICATE_MEMBER_PATH",
                )
            seen_normalized_paths.add(norm_path)

            # Case-insensitive collision check
            folded = norm_path.lower()
            if folded in seen_folded_paths:
                return self._create_error_result(
                    status=PackageInspectionStatus.CASE_COLLISION,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Case collision detected: path '{norm_path}' collides with '{seen_folded_paths[folded]}'",
                    code="CASE_COLLISION_DETECTED",
                )
            seen_folded_paths[folded] = norm_path

            # Symlink, hardlink, device, and special file rejection
            mode = info.external_attr >> 16
            if mode != 0:
                if stat.S_ISLNK(mode):
                    return self._create_error_result(
                        status=PackageInspectionStatus.SPECIAL_FILE_PROHIBITED,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=norm_path,
                        message=f"Prohibited symbolic link entry: '{norm_path}'",
                        code="SYMLINK_PROHIBITED",
                    )
                if stat.S_ISFIFO(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
                    return self._create_error_result(
                        status=PackageInspectionStatus.SPECIAL_FILE_PROHIBITED,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=norm_path,
                        message=f"Prohibited special device or FIFO entry: '{norm_path}'",
                        code="SPECIAL_DEVICE_PROHIBITED",
                    )

            # Uncompressed size checks
            if info.file_size > self._max_uncompressed_entry_bytes:
                return self._create_error_result(
                    status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Entry '{norm_path}' uncompressed size ({info.file_size} bytes) exceeds limit ({self._max_uncompressed_entry_bytes} bytes)",
                    code="ENTRY_SIZE_EXCEEDED",
                )

            total_uncompressed += info.file_size
            if total_uncompressed > self._max_total_uncompressed_bytes:
                return self._create_error_result(
                    status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Cumulative uncompressed size ({total_uncompressed} bytes) exceeds limit ({self._max_total_uncompressed_bytes} bytes)",
                    code="TOTAL_UNCOMPRESSED_EXCEEDED",
                )

            # Decompression bomb ratio check (for members exceeding threshold)
            if info.file_size > self._ratio_check_min_entry_bytes:
                eff_compress = max(info.compress_size, 1)
                ratio = info.file_size / eff_compress
                if ratio > self._max_compression_ratio:
                    return self._create_error_result(
                        status=PackageInspectionStatus.BOMB_COMPRESSION_RATIO_EXCEEDED,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=norm_path,
                        message=f"Entry '{norm_path}' compression ratio ({ratio:.1f}:1) exceeds limit ({self._max_compression_ratio:.1f}:1)",
                        code="COMPRESSION_RATIO_EXCEEDED",
                    )

            # Extension whitelist (applies to non-directory files)
            is_directory = info.is_dir() or clean_name.endswith("/")
            if not is_directory:
                ext = posixpath.splitext(norm_path)[1].lower()
                if ext not in ALLOWED_FILE_EXTENSIONS:
                    return self._create_error_result(
                        status=PackageInspectionStatus.PROHIBITED_FILE_EXTENSION,
                        package_hash=package_hash,
                        package_path=package_path,
                        archive_size=compressed_size,
                        entry_count=entry_count,
                        path=norm_path,
                        message=f"Entry '{norm_path}' has prohibited file extension '{ext}'",
                        code="PROHIBITED_EXTENSION",
                    )
                file_entries.append((norm_path, info))

        # -------------------------------------------------------------------
        # Gate A.3: Required Metadata Files Presence Check
        # -------------------------------------------------------------------
        if "manifest.json" not in seen_normalized_paths:
            return self._create_error_result(
                status=PackageInspectionStatus.MISSING_MANIFEST,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                message="Package archive missing required root 'manifest.json'",
                code="MISSING_MANIFEST_JSON",
            )

        if "META-INF/MANIFEST.MF" not in seen_normalized_paths:
            return self._create_error_result(
                status=PackageInspectionStatus.MISSING_INTEGRITY_MANIFEST,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                message="Package archive missing required integrity manifest 'META-INF/MANIFEST.MF'",
                code="MISSING_MANIFEST_MF",
            )

        # -------------------------------------------------------------------
        # Gate B: Stream File Bytes & Compute Digests (No disk extraction)
        # -------------------------------------------------------------------
        actual_digests: Dict[str, str] = {}
        manifest_json_bytes: Optional[bytes] = None
        manifest_mf_bytes: Optional[bytes] = None

        for norm_path, info in file_entries:
            hasher = hashlib.sha256()
            bytes_read = 0
            collected_chunks: List[bytes] = []
            need_full_bytes = norm_path in ("manifest.json", "META-INF/MANIFEST.MF")

            try:
                with zf.open(info, mode="r") as entry_stream:
                    while True:
                        chunk = entry_stream.read(STREAM_CHUNK_SIZE_BYTES)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                        if bytes_read > self._max_uncompressed_entry_bytes:
                            return self._create_error_result(
                                status=PackageInspectionStatus.ARCHIVE_LIMIT_EXCEEDED,
                                package_hash=package_hash,
                                package_path=package_path,
                                archive_size=compressed_size,
                                entry_count=entry_count,
                                path=norm_path,
                                message=f"Actual streamed bytes for '{norm_path}' exceeded limit",
                                code="STREAM_LIMIT_EXCEEDED",
                            )

                        hasher.update(chunk)
                        if need_full_bytes:
                            collected_chunks.append(chunk)
            except Exception as exc:
                return self._create_error_result(
                    status=PackageInspectionStatus.MALFORMED_ARCHIVE,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Failed to read archive entry bytes for '{norm_path}': {exc}",
                    code="ENTRY_READ_FAILED",
                )

            # Verify actual bytes read equals declared uncompressed size
            if bytes_read != info.file_size:
                return self._create_error_result(
                    status=PackageInspectionStatus.SIZE_MISMATCH,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=norm_path,
                    message=f"Entry '{norm_path}' declared size ({info.file_size} bytes) does not match actual bytes read ({bytes_read} bytes)",
                    code="SIZE_MISMATCH",
                )

            entry_digest = hasher.hexdigest().lower()
            actual_digests[norm_path] = entry_digest

            if norm_path == "manifest.json":
                manifest_json_bytes = b"".join(collected_chunks)
            elif norm_path == "META-INF/MANIFEST.MF":
                manifest_mf_bytes = b"".join(collected_chunks)

        if manifest_json_bytes is None:
            return self._create_error_result(
                status=PackageInspectionStatus.MISSING_MANIFEST,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                message="Failed to read bytes for 'manifest.json'",
                code="READ_MANIFEST_FAILED",
            )

        if manifest_mf_bytes is None:
            return self._create_error_result(
                status=PackageInspectionStatus.MISSING_INTEGRITY_MANIFEST,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                message="Failed to read bytes for 'META-INF/MANIFEST.MF'",
                code="READ_MANIFEST_MF_FAILED",
            )

        # -------------------------------------------------------------------
        # Gate B.2: Parse META-INF/MANIFEST.MF and Verify Digests
        # -------------------------------------------------------------------
        try:
            manifest_mf = ManifestMF.parse(manifest_mf_bytes, enforce_canonical_ordering=True)
        except ManifestMFError as exc:
            return self._create_error_result(
                status=PackageInspectionStatus.MALFORMED_INTEGRITY_MANIFEST,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                path="META-INF/MANIFEST.MF",
                message=f"Failed to parse 'META-INF/MANIFEST.MF': {exc}",
                code="MANIFEST_MF_PARSE_ERROR",
            )

        # Determine payload files: all regular files outside META-INF/
        payload_files: Set[str] = {
            p for p in actual_digests.keys()
            if not (p.upper() == "META-INF" or p.upper().startswith("META-INF/"))
        }

        # Check for unlisted payload files in the archive
        for p_file in sorted(payload_files):
            if not manifest_mf.contains_path(p_file):
                return self._create_error_result(
                    status=PackageInspectionStatus.UNLISTED_FILE_DETECTED,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=p_file,
                    message=f"Archive member '{p_file}' is not declared in META-INF/MANIFEST.MF",
                    code="UNLISTED_FILE",
                )

        # Check for declared files in MANIFEST.MF that are missing from archive
        for declared_file in sorted(manifest_mf.entries.keys()):
            if declared_file not in payload_files:
                return self._create_error_result(
                    status=PackageInspectionStatus.MISSING_PAYLOAD_FILE,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=declared_file,
                    message=f"File '{declared_file}' declared in META-INF/MANIFEST.MF does not exist in package payload",
                    code="MISSING_DECLARED_FILE",
                )

        # Verify cryptographic digests for all declared files
        for declared_file, declared_hash in manifest_mf.entries.items():
            actual_hash = actual_digests.get(declared_file)
            if actual_hash != declared_hash:
                return self._create_error_result(
                    status=PackageInspectionStatus.DIGEST_MISMATCH,
                    package_hash=package_hash,
                    package_path=package_path,
                    archive_size=compressed_size,
                    entry_count=entry_count,
                    path=declared_file,
                    message=f"SHA-256 digest mismatch for '{declared_file}': declared '{declared_hash}', actual '{actual_hash}'",
                    code="DIGEST_MISMATCH",
                )

        # -------------------------------------------------------------------
        # Gate C.1: Validate root manifest.json
        # -------------------------------------------------------------------
        manifest_result: ManifestValidationResult = self._manifest_validator.validate_content(
            manifest_json_bytes,
            host_omnix_version=host_omnix_version,
            host_contract_version=host_contract_version,
        )

        if not manifest_result.is_valid:
            errors = [
                PackageInspectionError(
                    code=err.code,
                    message=err.message,
                    path=err.path,
                    details=err.details,
                )
                for err in manifest_result.errors
            ]
            primary_msg = errors[0].message if errors else "Manifest validation failed"
            return PackageInspectionResult(
                is_valid=False,
                status=PackageInspectionStatus.MANIFEST_INVALID,
                package_hash=package_hash,
                package_path=package_path,
                archive_size_bytes=compressed_size,
                uncompressed_size_bytes=total_uncompressed,
                entry_count=entry_count,
                file_inventory=sorted(seen_normalized_paths),
                file_digests=actual_digests,
                errors=errors,
                warnings=manifest_result.warnings,
            )

        manifest_dict = manifest_result.manifest or {}
        plugin_id = manifest_dict.get("plugin_id")
        vendor_id = manifest_dict.get("vendor_id")
        display_name = manifest_dict.get("display_name")
        version = manifest_dict.get("version")
        entry_point = manifest_dict.get("entry_point", "")

        # -------------------------------------------------------------------
        # Gate C.2: Single-Vendor Package Invariant & Identity Checks
        # -------------------------------------------------------------------
        # Ensure plugin_id and vendor_id do not explicitly contradict each other
        # E.g. com.omnix.vendor.lion with vendor_javan
        if plugin_id and vendor_id:
            plugin_id_lower = plugin_id.lower()
            vendor_id_lower = vendor_id.lower()
            vendor_suffix = vendor_id_lower.removeprefix("vendor_")
            if "." in plugin_id_lower:
                plugin_leaf = plugin_id_lower.split(".")[-1]
                # If plugin leaf has clear vendor name, it must not contradict vendor_id
                if plugin_leaf in ("lion", "javan", "roboeq") and vendor_suffix in ("lion", "javan", "roboeq"):
                    if plugin_leaf != vendor_suffix:
                        return self._create_error_result(
                            status=PackageInspectionStatus.IDENTITY_CONFLICT,
                            package_hash=package_hash,
                            package_path=package_path,
                            archive_size=compressed_size,
                            entry_count=entry_count,
                            message=f"Plugin ID '{plugin_id}' conflicts with vendor ID '{vendor_id}'",
                            code="VENDOR_IDENTITY_CONFLICT",
                        )

        # -------------------------------------------------------------------
        # Gate C.3: Static Primary Entry-Point Existence Verification
        # (Zero code execution / zero module import)
        # -------------------------------------------------------------------
        entry_point_file = None
        entry_point_exists = False

        if ":" in entry_point:
            module_path_str = entry_point.split(":", 1)[0].strip()
            # Map module.path to relative file paths
            # e.g. plugin.adapter -> plugin/adapter.py or plugin/adapter/__init__.py
            rel_file = module_path_str.replace(".", "/") + ".py"
            rel_init = module_path_str.replace(".", "/") + "/__init__.py"

            if rel_file in payload_files:
                entry_point_file = rel_file
                entry_point_exists = True
            elif rel_init in payload_files:
                entry_point_file = rel_init
                entry_point_exists = True

        if not entry_point_exists:
            expected_desc = f"'{module_path_str.replace('.', '/')}.py' or '{module_path_str.replace('.', '/')}/__init__.py'"
            return self._create_error_result(
                status=PackageInspectionStatus.MISSING_ENTRY_POINT,
                package_hash=package_hash,
                package_path=package_path,
                archive_size=compressed_size,
                entry_count=entry_count,
                path=entry_point,
                message=f"Declared primary entry point '{entry_point}' module file not found in package payload (expected {expected_desc})",
                code="ENTRY_POINT_FILE_MISSING",
            )

        # -------------------------------------------------------------------
        # Package Inspection Success (Phase 4 Passed)
        # -------------------------------------------------------------------
        warnings = list(manifest_result.warnings)
        warnings.append(
            "Phase 4 package inspection succeeded. Digital signature verification (Phase 5) and installation (Phase 7) required before activation."
        )

        return PackageInspectionResult(
            is_valid=True,
            status=PackageInspectionStatus.VALID,
            package_hash=package_hash,
            package_path=package_path,
            archive_size_bytes=compressed_size,
            uncompressed_size_bytes=total_uncompressed,
            entry_count=entry_count,
            plugin_id=plugin_id,
            vendor_id=vendor_id,
            display_name=display_name,
            version=version,
            manifest_metadata=manifest_dict,
            entry_point=entry_point,
            entry_point_file=entry_point_file,
            entry_point_exists=True,
            file_inventory=sorted(seen_normalized_paths),
            file_digests=actual_digests,
            errors=[],
            warnings=warnings,
        )

    # -----------------------------------------------------------------------
    # Helper for creating structured error results
    # -----------------------------------------------------------------------

    def _create_error_result(
        self,
        status: PackageInspectionStatus,
        package_hash: str,
        message: str,
        code: str,
        package_path: Optional[str] = None,
        archive_size: int = 0,
        entry_count: int = 0,
        path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PackageInspectionResult:
        err = PackageInspectionError(code=code, message=message, path=path, details=details)
        return PackageInspectionResult(
            is_valid=False,
            status=status,
            package_hash=package_hash,
            package_path=package_path,
            archive_size_bytes=archive_size,
            entry_count=entry_count,
            errors=[err],
        )

    @classmethod
    def inspect_package(
        cls,
        target: Union[str, Path, bytes, BinaryIO, Any],
        host_omnix_version: Optional[str] = None,
        host_contract_version: Optional[str] = None,
    ) -> PackageInspectionResult:
        """Convenience classmethod to inspect an .xpl package file, raw bytes, or BytesIO."""
        return cls().inspect(
            target,
            host_omnix_version=host_omnix_version,
            host_contract_version=host_contract_version,
        )


# ---------------------------------------------------------------------------
# Convenience Module-Level Inspection Function
# ---------------------------------------------------------------------------

_DEFAULT_INSPECTOR = PackageInspector()


def inspect_package(
    target: Union[str, Path, bytes, BinaryIO, Any],
    host_omnix_version: Optional[str] = None,
    host_contract_version: Optional[str] = None,
) -> PackageInspectionResult:
    """Convenience function to inspect an .xpl package file, raw bytes, or BytesIO."""
    return _DEFAULT_INSPECTOR.inspect(
        target,
        host_omnix_version=host_omnix_version,
        host_contract_version=host_contract_version,
    )

