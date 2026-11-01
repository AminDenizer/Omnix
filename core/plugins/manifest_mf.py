"""
Omnix Vendor Plugin System — Manifest.MF (Integrity Manifest) Parser & Generator
Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 9.2

Provides deterministic parsing, canonicalization, and validation of META-INF/MANIFEST.MF
files containing per-file SHA-256 digests of plugin payloads without circular dependencies.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union


# 64 lowercase hexadecimal characters for standard SHA-256 digest
SHA256_HEX_REGEX = re.compile(r"^[a-f0-9]{64}$")

# Windows reserved device names (DOS devices)
WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


class ManifestMFError(Exception):
    """Base exception for all MANIFEST.MF processing failures."""
    pass


class ManifestMFSyntaxError(ManifestMFError):
    """Raised when MANIFEST.MF contains malformed syntax, unparseable lines, or bad headers."""
    def __init__(self, message: str, line_num: Optional[int] = None):
        super().__init__(f"Line {line_num}: {message}" if line_num is not None else message)
        self.line_num = line_num


class ManifestMFValidationError(ManifestMFError):
    """Raised when MANIFEST.MF violates structural rules (e.g. duplicate keys, forbidden paths, uncanonical order)."""
    pass


# Alias for naming consistency with ManifestSemanticError
ManifestMFSemanticError = ManifestMFValidationError


@dataclass(frozen=True)
class ManifestMFEntry:
    """Represents a single verified file entry in MANIFEST.MF."""
    path: str
    digest: str

    def __post_init__(self) -> None:
        if not self.path:
            raise ManifestMFValidationError("File path cannot be empty")
        if not SHA256_HEX_REGEX.match(self.digest):
            raise ManifestMFValidationError(
                f"Digest for '{self.path}' is not a valid 64-char lowercase SHA-256 hex string: '{self.digest}'"
            )


@dataclass
class ManifestMF:
    """
    Parsed representation of META-INF/MANIFEST.MF.

    Maintains canonical POSIX paths mapped to 64-character lowercase SHA-256 digests.
    """
    entries: Dict[str, str] = field(default_factory=dict)
    _raw_bytes: Optional[bytes] = None

    def get_digest(self, path: str) -> Optional[str]:
        """Return the lowercase SHA-256 digest for normalized path, or None."""
        norm = self.normalize_path(path)
        return self.entries.get(norm)

    def contains_path(self, path: str) -> bool:
        """Check whether normalized path is recorded in MANIFEST.MF."""
        norm = self.normalize_path(path)
        return norm in self.entries

    @staticmethod
    def normalize_path(raw_path: str) -> str:
        """
        Normalize and validate a file path per Section 9.2:
        - Relative POSIX path using forward slashes (/)
        - posixpath.normpath applied
        - No leading slash, no ./, no ../
        - No Windows drive letters or null bytes
        - No paths within META-INF/
        """
        if "\0" in raw_path:
            raise ManifestMFValidationError(f"Path contains null byte: {raw_path!r}")

        # Replace Windows backslashes with POSIX forward slashes
        clean = raw_path.replace("\\", "/")

        if clean.startswith("/"):
            raise ManifestMFValidationError(f"Path must be relative, cannot have leading slash: '{raw_path}'")

        if ":" in clean:
            raise ManifestMFValidationError(
                f"Path cannot contain colon character (Windows ADS or drive specifier): '{raw_path}'"
            )

        norm = posixpath.normpath(clean)

        if norm.startswith("..") or "/../" in f"/{norm}/":
            raise ManifestMFValidationError(f"Path attempts parent directory traversal: '{raw_path}'")

        if norm.startswith("./"):
            norm = norm[2:]

        if not norm or norm == ".":
            raise ManifestMFValidationError(f"Invalid empty normalized path for '{raw_path}'")

        # Windows reserved device names and trailing dots/spaces checks
        segments = [seg for seg in norm.split("/") if seg and seg != "."]
        for seg in segments:
            stem = seg.split(".")[0].upper()
            if stem in WINDOWS_RESERVED_DEVICE_NAMES:
                raise ManifestMFValidationError(
                    f"Path contains Windows reserved device name '{seg}': '{raw_path}'"
                )
            if seg.endswith(".") or seg.endswith(" "):
                raise ManifestMFValidationError(
                    f"Path segment '{seg}' ends with trailing dot or space: '{raw_path}'"
                )


        # META-INF/ exclusion rule:
        # Files inside META-INF/ are strictly excluded from entries in MANIFEST.MF
        if norm.upper() == "META-INF" or norm.upper().startswith("META-INF/"):
            raise ManifestMFValidationError(
                f"Entries in MANIFEST.MF cannot include files within META-INF/: '{raw_path}'"
            )

        return norm

    @classmethod
    def create(cls, entries: Dict[str, str]) -> ManifestMF:
        """
        Create a ManifestMF instance from a dictionary of path -> sha256_digest,
        validating paths and digests, and sorting lexicographically.
        """
        validated: Dict[str, str] = {}
        for raw_path, digest in entries.items():
            norm_path = cls.normalize_path(raw_path)
            lower_digest = digest.strip().lower()
            if not SHA256_HEX_REGEX.match(lower_digest):
                raise ManifestMFValidationError(
                    f"Digest for '{raw_path}' is not a valid 64-character lowercase SHA-256 hex string: '{digest}'"
                )
            if norm_path in validated:
                raise ManifestMFValidationError(f"Duplicate entry for normalized path: '{norm_path}'")
            validated[norm_path] = lower_digest

        # Sort lexicographically by UTF-8 byte order
        sorted_entries = dict(sorted(validated.items(), key=lambda kv: kv[0].encode("utf-8")))
        return cls(entries=sorted_entries)

    def dump(self) -> str:
        """
        Render the canonical UTF-8 text representation of MANIFEST.MF with Unix newlines (\\n).
        Entries are ordered lexicographically by UTF-8 byte order.
        """
        lines: List[str] = []
        # Ensure lexicographical ordering by UTF-8 byte order
        sorted_keys = sorted(self.entries.keys(), key=lambda k: k.encode("utf-8"))
        for path in sorted_keys:
            digest = self.entries[path]
            lines.append(f"File: {path}")
            lines.append(f"SHA-256-Digest: {digest}")
            lines.append("")  # blank separator line
        return "\n".join(lines)

    def dump_bytes(self) -> bytes:
        """Return the canonical UTF-8 encoded bytes of MANIFEST.MF."""
        return self.dump().encode("utf-8")

    @classmethod
    def to_manifest_mf_string(cls, entries: Dict[str, str]) -> str:
        """Format an entries mapping into MANIFEST.MF string in the given dictionary order."""
        lines: List[str] = []
        for path, digest in entries.items():
            lines.append(f"File: {path}")
            lines.append(f"SHA-256-Digest: {digest}")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def generate(cls, files_map: Dict[str, Union[str, bytes]]) -> str:
        """
        Generate canonical MANIFEST.MF text from a dictionary mapping file paths to
        either raw content (str or bytes) or precomputed SHA-256 hex digests.
        Files inside META-INF/ are strictly excluded.
        """
        digests: Dict[str, str] = {}
        for path, item in files_map.items():
            clean = path.replace("\\", "/")
            if clean.startswith("/"):
                clean = clean.lstrip("/")
            if clean.upper() == "META-INF" or clean.upper().startswith("META-INF/"):
                continue
            if isinstance(item, str) and SHA256_HEX_REGEX.match(item.strip().lower()):
                digests[path] = item.strip().lower()
            else:
                raw = item.encode("utf-8") if isinstance(item, str) else item
                digests[path] = hashlib.sha256(raw).hexdigest()
        mf = cls.create(digests)
        return mf.dump()


    @classmethod
    def parse(cls, content: Union[str, bytes], enforce_canonical_ordering: bool = True) -> ManifestMF:
        """
        Parse MANIFEST.MF text or bytes into a ManifestMF instance.

        Format:
        File: <relative-posix-path>
        SHA-256-Digest: <64-char-hex>

        [blank line]

        Args:
            content: Raw string or bytes of MANIFEST.MF.
            enforce_canonical_ordering: If True, reject files where entries are not
                lexicographically ordered by UTF-8 byte order.
        """
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ManifestMFSyntaxError(f"MANIFEST.MF is not valid UTF-8: {exc}")
            raw_bytes = content
        else:
            text = content
            raw_bytes = content.encode("utf-8")

        lines = text.splitlines()
        entries: Dict[str, str] = {}
        keys_in_order: List[str] = []

        current_file: Optional[str] = None
        current_digest: Optional[str] = None
        file_line_num: Optional[int] = None

        def commit_entry(line_no: int) -> None:
            nonlocal current_file, current_digest, file_line_num
            if current_file is not None or current_digest is not None:
                if current_file is None:
                    raise ManifestMFSyntaxError(
                        "Found 'SHA-256-Digest:' without preceding 'File:' header",
                        line_num=line_no
                    )
                if current_digest is None:
                    raise ManifestMFSyntaxError(
                        f"Entry for 'File: {current_file}' is missing 'SHA-256-Digest:' header",
                        line_num=file_line_num or line_no
                    )
                if current_file in entries:
                    raise ManifestMFValidationError(
                        f"Duplicate entry for '{current_file}' in MANIFEST.MF at line {line_no}"
                    )
                entries[current_file] = current_digest
                keys_in_order.append(current_file)
                current_file = None
                current_digest = None
                file_line_num = None

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                # Blank separator line
                commit_entry(idx)
                continue

            # Header must have colon
            if ":" not in line:
                raise ManifestMFSyntaxError(f"Malformed line missing colon header separator: '{line}'", line_num=idx)

            key, value = line.split(":", 1)
            key = key.strip()
            val = value.strip()

            if key == "File":
                if current_file is not None:
                    raise ManifestMFSyntaxError(
                        f"Duplicate 'File:' header without preceding digest or separator: '{val}'",
                        line_num=idx
                    )
                norm_p = cls.normalize_path(val)
                current_file = norm_p
                file_line_num = idx
            elif key == "SHA-256-Digest":
                if current_file is None:
                    raise ManifestMFSyntaxError(
                        f"Orphan 'SHA-256-Digest:' header without matching 'File:': '{val}'",
                        line_num=idx
                    )
                if current_digest is not None:
                    raise ManifestMFSyntaxError(
                        f"Duplicate 'SHA-256-Digest:' header for '{current_file}'",
                        line_num=idx
                    )
                lower_d = val.lower()
                if not SHA256_HEX_REGEX.match(lower_d):
                    raise ManifestMFSyntaxError(
                        f"Malformed SHA-256 digest '{val}' for file '{current_file}'; expected 64 hex characters",
                        line_num=idx
                    )
                current_digest = lower_d
            else:
                raise ManifestMFSyntaxError(
                    f"Unrecognized header '{key}' in MANIFEST.MF (only 'File' and 'SHA-256-Digest' permitted)",
                    line_num=idx
                )

        # Commit final pending entry
        commit_entry(len(lines) + 1)

        if not entries:
            raise ManifestMFValidationError("MANIFEST.MF contains zero valid file digest entries")

        # Canonical ordering validation
        if enforce_canonical_ordering:
            sorted_keys = sorted(keys_in_order, key=lambda k: k.encode("utf-8"))
            if keys_in_order != sorted_keys:
                raise ManifestMFValidationError(
                    "MANIFEST.MF entries are not sorted lexicographically by UTF-8 byte order"
                )

        inst = cls(entries=entries)
        inst._raw_bytes = raw_bytes
        return inst


def parse_manifest_mf(
    content: Union[str, bytes],
    enforce_canonical_ordering: bool = True,
) -> ManifestMF:
    """Parse MANIFEST.MF content into a ManifestMF object."""
    return ManifestMF.parse(content, enforce_canonical_ordering=enforce_canonical_ordering)


def generate_manifest_mf(
    files_map: Dict[str, Union[str, bytes]],
) -> str:
    """Generate canonical MANIFEST.MF text from relative paths and file contents or digests."""
    return ManifestMF.generate(files_map)
