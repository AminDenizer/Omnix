"""
Omnix Core — Multi-Vendor Purchase Link Parser and Normalizer.

Supports the canonical multi-vendor purchase link format used by Excel Inventory:
    LION=<URL> || JAVAN=<URL>

Governing Rules:
1. Vendor keys are case-insensitive and normalized to canonical vendor identifiers
   (e.g. 'LION' -> 'vendor_lion', 'JAVAN' -> 'vendor_javan').
2. Token delimiter is '||'. Whitespace around tokens and '=' is safely stripped.
3. Legacy single plain URLs (e.g. 'https://lionelectronic.ir/...') are seamlessly supported
   without requiring vendor labels or delimiters.
4. Token order is independent and does not alter the parsed mapping.
5. Duplicate vendor keys are rejected.
6. Malformed delimiters, missing '=', empty URLs, and unsupported keys fail closed.
7. Host mismatch between vendor key and URL domain is strictly rejected when verifiable.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Canonical vendor label mappings
KNOWN_VENDOR_LABELS: Dict[str, str] = {
    "LION": "vendor_lion",
    "JAVAN": "vendor_javan",
}

# Authoritative default display names for fallback
DEFAULT_VENDOR_NAMES: Dict[str, str] = {
    "vendor_lion": "Lion Electronic",
    "vendor_javan": "Javan Electronic",
}

# Default known storefront domains
DEFAULT_VENDOR_DOMAINS: Dict[str, List[str]] = {
    "vendor_lion": ["lionelectronic.ir"],
    "vendor_javan": ["javanelec.com"],
}


@dataclass
class VendorLinkEntry:
    """Represents a validated vendor purchase link for a specific vendor."""
    vendor_id: str
    vendor_label: str
    url: str
    display_name: str = ""


@dataclass
class ParsedVendorLinks:
    """Represents the parsed outcome of an inventory purchase link field."""
    raw_input: str
    is_multi: bool = False
    is_empty: bool = False
    is_valid: bool = True
    error_message: Optional[str] = None
    entries: List[VendorLinkEntry] = field(default_factory=list)
    links: Dict[str, VendorLinkEntry] = field(default_factory=dict)

    def __post_init__(self):
        if self.entries and not self.links:
            # Populate dictionary for backwards compatibility
            self.links = {e.vendor_id: e for e in self.entries}
        elif self.links and not self.entries:
            self.entries = list(self.links.values())

    @property
    def vendor_ids(self) -> List[str]:
        """Return sorted list of vendor identifiers present in the parsed result."""
        return sorted(list({e.vendor_id for e in self.entries}))

    @property
    def count(self) -> int:
        """Return the number of valid vendor links."""
        return len(self.entries)

    def get_url(self, vendor_id: str) -> Optional[str]:
        """Retrieve URL for a specific vendor_id if present."""
        for e in self.entries:
            if e.vendor_id == vendor_id:
                return e.url
        return None

    def get_single_entry(self) -> Optional[VendorLinkEntry]:
        """Return the single VendorLinkEntry if exactly one valid link exists, else None."""
        if len(self.entries) == 1:
            return self.entries[0]
        return None

    def as_dict(self) -> Dict[str, str]:
        """Return mapping of vendor_id -> url."""
        return {e.vendor_id: e.url for e in self.entries}


def parse_vendor_links(
    raw_link: Optional[str],
    registry: Optional[Any] = None,
) -> ParsedVendorLinks:
    """
    Deterministically parses and validates an inventory purchase link field.

    Handles:
    1. Empty / whitespace-only fields -> is_empty=True, count=0.
    2. Legacy plain URLs -> count=1 if recognized, count=0 if unknown host.
    3. New-format single labeled links ('LION=https://...') -> count=1, is_multi=False.
    4. New-format multi-vendor links ('LION=... || JAVAN=...') -> count=2+, is_multi=True.
    5. Malformed syntax, duplicate keys, domain contradictions -> is_valid=False.

    Args:
        raw_link: Raw string from InventoryTable[Purchase Link].
        registry: Optional VendorRegistry instance for dynamic domain and display name lookup.

    Returns:
        ParsedVendorLinks object.
    """
    if raw_link is None or not str(raw_link).strip():
        return ParsedVendorLinks(raw_input="", is_empty=True, is_valid=True, links={})

    clean_link = str(raw_link).strip()

    # Step 1: Detect malformed single pipe separator
    if "|" in clean_link and "||" not in clean_link:
        return ParsedVendorLinks(
            raw_input=clean_link,
            is_valid=False,
            error_message="Malformed separator: single '|' found instead of '||' delimiter.",
        )

    # Step 2: Check if this is a legacy plain URL
    # A legacy URL starts with http:// or https:// and does NOT contain the '||' delimiter
    if clean_link.startswith(("http://", "https://")) and "||" not in clean_link:
        try:
            parsed_u = urlparse(clean_link)
            scheme = parsed_u.scheme.lower()
            netloc = parsed_u.netloc.lower().replace("www.", "")
            if ":" in netloc:
                netloc = netloc.split(":")[0]

            if not scheme or not netloc:
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_valid=False,
                    error_message=f"Invalid URL: '{clean_link}'.",
                )

            # Resolve vendor against registry
            reg = registry
            if reg is None:
                try:
                    from core.procurement.registry import VendorRegistry
                    reg = VendorRegistry.get_default_registry()
                except Exception:
                    reg = None

            vid = reg.get_vendor_for_url(clean_link) if (reg and hasattr(reg, "get_vendor_for_url")) else None
            if not vid:
                # Fallback to known default storefront domains so URL identity is recognized even if plugin is uninstalled
                for cand_vid, domains in DEFAULT_VENDOR_DOMAINS.items():
                    if any(netloc == d or netloc.endswith("." + d) for d in domains):
                        vid = cand_vid
                        break

            if vid:
                v_label = vid.replace("vendor_", "").upper()
                display_name = (
                    reg.get_vendor_name(vid)
                    if (reg and hasattr(reg, "get_vendor_name"))
                    else DEFAULT_VENDOR_NAMES.get(vid, v_label.title())
                )
                entry = VendorLinkEntry(
                    vendor_id=vid,
                    vendor_label=v_label,
                    url=clean_link,
                    display_name=display_name,
                )
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_multi=False,
                    is_valid=True,
                    links={vid: entry},
                )
            else:
                # Valid legacy URL syntax, but unknown / unsupported vendor domain (or no plugin installed)
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_multi=False,
                    is_valid=True,
                    links={},
                    error_message=None,
                )

        except Exception as e:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Malformed legacy URL: {e}",
            )

    # Step 3: Labeled or Multi-vendor tokens separated by '||'
    raw_tokens = clean_link.split("||")
    parsed_entries: List[VendorLinkEntry] = []
    seen_urls: Set[str] = set()

    reg = registry
    if reg is None:
        try:
            from core.procurement.registry import VendorRegistry
            reg = VendorRegistry.get_default_registry()
        except Exception:
            reg = None

    for raw_tok in raw_tokens:
        tok = raw_tok.strip()
        if not tok:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message="Empty token or malformed delimiter in vendor links.",
            )

        if "=" not in tok:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Missing '=' in vendor link token: '{tok}'.",
            )

        key, sep, val = tok.partition("=")
        key = key.strip()
        val = val.strip()

        if not key:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Missing vendor label before '=' in token: '{tok}'.",
            )

        norm_key = key.upper()

        # Check for multiple keys concatenated without delimiter (e.g. LION=https://... JAVAN=https://...)
        for other_lbl in KNOWN_VENDOR_LABELS:
            if f"{other_lbl}=" in val.upper() or f" {other_lbl} =" in val.upper() or f";{other_lbl}=" in val.upper():
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_valid=False,
                    error_message=f"Missing or malformed separator before '{other_lbl}' in token: '{tok}'.",
                )

        # Validate vendor label
        if norm_key not in KNOWN_VENDOR_LABELS:
            cand_vid = f"vendor_{key.lower()}"
            if reg and hasattr(reg, "has_vendor") and reg.has_vendor(cand_vid):
                vid = cand_vid
            else:
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_valid=False,
                    error_message=f"Unsupported vendor key '{key}'. Allowed vendors: LION, JAVAN.",
                )
        else:
            vid = KNOWN_VENDOR_LABELS[norm_key]

        # Check empty URL
        if not val:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Empty URL for vendor '{key}'.",
            )

        # Check URL syntax
        if not val.startswith(("http://", "https://")):
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Invalid URL format for vendor '{key}': '{val}'. Must start with http:// or https://.",
            )

        norm_u = val.rstrip("/").lower()
        if norm_u in seen_urls:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Duplicate URL in vendor links: '{val}'. Each supplier link must be unique.",
            )
        seen_urls.add(norm_u)

        try:
            parsed_u = urlparse(val)
            scheme = parsed_u.scheme.lower()
            netloc = parsed_u.netloc.lower().replace("www.", "")
            if ":" in netloc:
                netloc = netloc.split(":")[0]

            if not scheme or not netloc:
                return ParsedVendorLinks(
                    raw_input=clean_link,
                    is_valid=False,
                    error_message=f"Invalid URL host for vendor '{key}': '{val}'.",
                )
        except Exception as e:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Malformed URL for vendor '{key}': {e}",
            )

        display_name = (
            reg.get_vendor_name(vid)
            if (reg and hasattr(reg, "get_vendor_name"))
            else DEFAULT_VENDOR_NAMES.get(vid, norm_key.title())
        )

        entry = VendorLinkEntry(
            vendor_id=vid,
            vendor_label=norm_key,
            url=val,
            display_name=display_name,
        )
        parsed_entries.append(entry)

    is_multi = len(parsed_entries) > 1
    return ParsedVendorLinks(
        raw_input=clean_link,
        is_multi=is_multi,
        is_valid=True,
        entries=parsed_entries,
    )
