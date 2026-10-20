"""
Omnix Core — Deterministic Component Identification & Link Validation Service
Governing Document: Mode A Deterministic Procurement & Link Validation Spec
"""

import re
import urllib.parse
import urllib.request
from enum import Enum
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass

from core.inventory.models import normalize_identity_part, SupplierLink
from core.procurement.registry import VendorRegistry, default_registry
from core.procurement.vendor_links import parse_vendor_links


import ipaddress
import urllib.error


class LinkValidationStatus(str, Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    UNSUPPORTED_VENDOR = "UNSUPPORTED_VENDOR"
    UNSUPPORTED_PROVIDER = "UNSUPPORTED_VENDOR"
    INVALID_URL = "INVALID_URL"
    HTTP_ERROR = "HTTP_ERROR"
    NETWORK_ERROR = "HTTP_ERROR"



def is_private_or_local_host(hostname: str) -> bool:
    """Detects localhost and private network destinations to prevent Server-Side Request Forgery (SSRF)."""
    if not hostname:
        return True
    host = hostname.strip().lower()
    if host in ("localhost", "localhost.localdomain", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass
    if host.endswith(".local") or host.endswith(".internal") or host.endswith(".lan"):
        return True
    return False


@dataclass
class LinkValidationItem:
    """Input payload representing a supplier link attached to a physical component or BOM row."""
    component_id: Optional[int] = None
    component_name: str = ""
    manufacturer: str = ""
    mpn: str = ""
    url: str = ""
    vendor_id: str = ""
    vendor_label: str = ""


@dataclass
class LinkValidationResult:
    """Result of deterministic validation for a single supplier link."""
    item: LinkValidationItem
    status: LinkValidationStatus
    extracted_mpn: Optional[str] = None
    extracted_manufacturer: Optional[str] = None
    extracted_package: Optional[str] = None
    message: str = ""
    status_code: Optional[int] = None

    @property
    def is_verified(self) -> bool:
        return self.status == LinkValidationStatus.VERIFIED_MATCH

    @property
    def is_mismatch(self) -> bool:
        return self.status == LinkValidationStatus.IDENTITY_MISMATCH


def default_http_fetcher(url: str, timeout: float = 6.0) -> Tuple[int, str]:
    """Default HTTP fetcher using standard urllib with browser-like user agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        code = response.getcode()
        html = response.read().decode("utf-8", errors="replace")
        return code, html


class LinkValidator:
    """
    Deterministic link validation engine for Mode A.
    Verifies URL format, reachability, extracts technical specifications via vendor
    adapters, and confirms that the remote product matches the local component record.
    """

    def __init__(
        self,
        registry: Optional[VendorRegistry] = None,
        fetcher: Optional[Callable[[str, float], Tuple[int, str]]] = None,
        timeout: float = 6.0,
    ):
        self.registry = registry or default_registry
        self.fetcher = fetcher or default_http_fetcher
        self.timeout = timeout

    def resolve_adapter_for_url(self, url: str) -> Optional[Any]:
        """Resolves registered IVendorAdapter instance for a given product URL."""
        if not url:
            return None
        low = url.lower()
        if "lionelectronic.ir" in low or "lion" in low:
            vid = "vendor_lion"
        elif "javanelec.com" in low or "javan" in low:
            vid = "vendor_javan"
        elif "roboeq.ir" in low or "roboeq" in low:
            vid = "vendor_roboeq"
        else:
            vid = None

        if vid and self.registry.has_vendor(vid):
            try:
                return self.registry.get_adapter(vid)
            except Exception:
                pass

        # Try to resolve via registered domain mappings
        for reg_vid in self.registry.list_vendors():
            meta = self.registry.get_registration(reg_vid)
            if meta and meta.domains:
                for d in meta.domains:
                    if d.lower() in low:
                        try:
                            return self.registry.get_adapter(reg_vid)
                        except Exception:
                            pass
        return None

    def validate_item(self, item: LinkValidationItem) -> LinkValidationResult:
        """Deterministically validate a single LinkValidationItem."""
        url = (item.url or "").strip()
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.INVALID_URL,
                message="Missing or malformed store URL (must begin with http:// or https://).",
            )

        hostname = parsed_url.hostname or ""
        if is_private_or_local_host(hostname):
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.INVALID_URL,
                message="Security restriction: Localhost and private network destinations are prohibited (SSRF prevention).",
            )

        if not (item.mpn or "").strip():
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.NOT_VERIFIABLE,
                message="Incomplete component identity: MPN is required for verification.",
            )

        adapter = self.resolve_adapter_for_url(url)
        if not adapter or not hasattr(adapter, "extract_product_data"):
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.UNSUPPORTED_VENDOR,
                message=f"No registered vendor adapter recognized URL domain: {url}",
            )

        # HTTP fetch
        try:
            status_code, html = self.fetcher(url, self.timeout)
            if status_code != 200:
                return LinkValidationResult(
                    item=item,
                    status=LinkValidationStatus.HTTP_ERROR,
                    status_code=status_code,
                    message=f"HTTP request returned status {status_code}.",
                )
        except urllib.error.HTTPError as e:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.HTTP_ERROR,
                status_code=e.code,
                message=f"HTTP request returned error {e.code}: {e.reason}",
            )
        except Exception as e:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.HTTP_ERROR,
                message=f"Network transport error: {e}",
            )

        # Extract specification draft via adapter
        try:
            draft = adapter.extract_product_data(html)
        except Exception as e:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.NOT_VERIFIABLE,
                status_code=200,
                message=f"Error parsing product page: {e}",
            )

        ext_mpn = draft.mpn if draft else None
        ext_mfr = draft.manufacturer if draft else None
        ext_pkg = draft.package if draft else None

        if not ext_mpn and not ext_mfr:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.NOT_VERIFIABLE,
                status_code=200,
                extracted_mpn=ext_mpn,
                extracted_manufacturer=ext_mfr,
                extracted_package=ext_pkg,
                message="Page fetched successfully, but no MPN or Manufacturer could be extracted from page HTML.",
            )

        comp_mpn_norm = normalize_identity_part(item.mpn)
        comp_mfr_norm = normalize_identity_part(item.manufacturer)
        ext_mpn_norm = normalize_identity_part(ext_mpn)
        ext_mfr_norm = normalize_identity_part(ext_mfr)

        mpn_matched = False
        if comp_mpn_norm and ext_mpn_norm:
            if comp_mpn_norm == ext_mpn_norm or comp_mpn_norm in ext_mpn_norm or ext_mpn_norm in comp_mpn_norm:
                mpn_matched = True

        mfr_matched = False
        if comp_mfr_norm and ext_mfr_norm:
            if comp_mfr_norm == ext_mfr_norm or comp_mfr_norm in ext_mfr_norm or ext_mfr_norm in comp_mfr_norm:
                mfr_matched = True

        # Check for explicit mismatch
        if comp_mpn_norm and ext_mpn_norm and not mpn_matched:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.IDENTITY_MISMATCH,
                status_code=200,
                extracted_mpn=ext_mpn,
                extracted_manufacturer=ext_mfr,
                extracted_package=ext_pkg,
                message=f"Extracted MPN '{ext_mpn}' does not match component MPN '{item.mpn}'.",
            )

        if comp_mfr_norm and ext_mfr_norm and not mfr_matched and not mpn_matched:
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.IDENTITY_MISMATCH,
                status_code=200,
                extracted_mpn=ext_mpn,
                extracted_manufacturer=ext_mfr,
                extracted_package=ext_pkg,
                message=f"Extracted Manufacturer '{ext_mfr}' does not match component Manufacturer '{item.manufacturer}'.",
            )

        if mpn_matched or mfr_matched:
            matched_on = "MPN & Manufacturer" if (mpn_matched and mfr_matched) else ("MPN" if mpn_matched else "Manufacturer")
            return LinkValidationResult(
                item=item,
                status=LinkValidationStatus.VERIFIED_MATCH,
                status_code=200,
                extracted_mpn=ext_mpn,
                extracted_manufacturer=ext_mfr,
                extracted_package=ext_pkg,
                message=f"Verified: Deterministic match on {matched_on}.",
            )

        return LinkValidationResult(
            item=item,
            status=LinkValidationStatus.NOT_VERIFIABLE,
            status_code=200,
            extracted_mpn=ext_mpn,
            extracted_manufacturer=ext_mfr,
            extracted_package=ext_pkg,
            message="Extracted partial attributes but unable to definitively match identity.",
        )

    def validate_batch(
        self,
        items: List[LinkValidationItem],
        progress_callback: Optional[Callable[[int, int, LinkValidationResult], None]] = None,
    ) -> List[LinkValidationResult]:
        """Validate a collection of LinkValidationItems sequentially."""
        results: List[LinkValidationResult] = []
        total = len(items)
        for idx, item in enumerate(items, start=1):
            res = self.validate_item(item)
            results.append(res)
            if progress_callback:
                progress_callback(idx, total, res)
        return results
