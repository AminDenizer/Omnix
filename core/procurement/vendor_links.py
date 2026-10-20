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
    "ROBOEQ": "vendor_roboeq",
}

# Authoritative default display names for fallback
DEFAULT_VENDOR_NAMES: Dict[str, str] = {
    "vendor_lion": "Lion Electronic",
    "vendor_javan": "Javan Electronic",
    "vendor_roboeq": "RoboEq",
}

# Default known storefront domains
DEFAULT_VENDOR_DOMAINS: Dict[str, List[str]] = {
    "vendor_lion": ["lionelectronic.ir"],
    "vendor_javan": ["javanelec.com"],
    "vendor_roboeq": ["roboeq.ir"],
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
    links: Dict[str, VendorLinkEntry] = field(default_factory=dict)

    @property
    def vendor_ids(self) -> List[str]:
        """Return sorted list of vendor identifiers present in the parsed result."""
        return sorted(list(self.links.keys()))

    @property
    def count(self) -> int:
        """Return the number of valid vendor links."""
        return len(self.links)

    def get_url(self, vendor_id: str) -> Optional[str]:
        """Retrieve URL for a specific vendor_id if present."""
        entry = self.links.get(vendor_id)
        return entry.url if entry else None

    def get_single_entry(self) -> Optional[VendorLinkEntry]:
        """Return the single VendorLinkEntry if exactly one valid link exists, else None."""
        if len(self.links) == 1:
            return next(iter(self.links.values()))
        return None

    def as_dict(self) -> Dict[str, str]:
        """Return mapping of vendor_id -> url."""
        return {vid: entry.url for vid, entry in self.links.items()}


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
    parsed_entries: Dict[str, VendorLinkEntry] = {}
    seen_labels: Set[str] = set()

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

        if norm_key in seen_labels:
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=f"Duplicate vendor key '{key}' in vendor links.",
            )
        seen_labels.add(norm_key)

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

        # Domain mismatch check (Rule 11)
        url_vid = reg.get_vendor_for_url(val) if (reg and hasattr(reg, "get_vendor_for_url")) else None
        if not url_vid:
            for candidate_vid, domains in DEFAULT_VENDOR_DOMAINS.items():
                if any(netloc == d or netloc.endswith("." + d) for d in domains):
                    url_vid = candidate_vid
                    break

        if url_vid and url_vid != vid:
            url_v_name = (
                reg.get_vendor_name(url_vid)
                if (reg and hasattr(reg, "get_vendor_name"))
                else DEFAULT_VENDOR_NAMES.get(url_vid, url_vid)
            )
            key_v_name = (
                reg.get_vendor_name(vid)
                if (reg and hasattr(reg, "get_vendor_name"))
                else DEFAULT_VENDOR_NAMES.get(vid, key)
            )
            return ParsedVendorLinks(
                raw_input=clean_link,
                is_valid=False,
                error_message=(
                    f"Vendor key '{key}' ({key_v_name}) contradicts URL host '{netloc}' "
                    f"(belongs to {url_v_name})."
                ),
            )

        display_name = (
            reg.get_vendor_name(vid)
            if (reg and hasattr(reg, "get_vendor_name"))
            else DEFAULT_VENDOR_NAMES.get(vid, norm_key.title())
        )

        parsed_entries[vid] = VendorLinkEntry(
            vendor_id=vid,
            vendor_label=norm_key,
            url=val,
            display_name=display_name,
        )

    is_multi = len(parsed_entries) > 1
    return ParsedVendorLinks(
        raw_input=clean_link,
        is_multi=is_multi,
        is_valid=True,
        links=parsed_entries,
    )
