"""
Lion Electronic Error Translation Layer
Translates vendor-specific DOM, HTTP, and transport signals into 13 Omnix error categories.
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md Section 8
"""

import re
from typing import Optional, Dict, Any, Tuple

from core.errors import (
    OmnixVendorError,
    ProductNotFoundError,
    ZeroSearchResultsError,
    OutOfStockError,
    MOQViolationError,
    OrderMultipleViolationError,
    MaxQuantityExceededError,
    TransportNetworkError,
    AuthenticationRequiredError,
    SessionExpiredError,
    SecurityChallengeError,
    WAFBlockError,
    DOMDriftError,
    UnknownVendorError,
)

VENDOR_ID = "vendor_lion"


class LionErrorTranslator:
    """
    3-Tier translation engine for Lion Electronic:
    1. DOM / SweetAlert modal analysis
    2. HTTP status & URL redirect analysis
    3. Transport & Selenium driver exception analysis
    """

    # SweetAlert keyword mapping
    SWAL_PATTERNS = [
        (re.compile(r"حداقل|moq", re.IGNORECASE), "MOQ_VIOLATION"),
        (re.compile(r"ضریب|مضرب|بسته|step|multiple", re.IGNORECASE), "ORDER_MULTIPLE_VIOLATION"),
        (re.compile(r"موجودی کافی نیست|عدم موجودی کافی|سقف موجودی", re.IGNORECASE), "MAX_QUANTITY_EXCEEDED"),
        (re.compile(r"اتمام موجودی|ناموجود|تمام شد", re.IGNORECASE), "OUT_OF_STOCK"),
        (re.compile(r"ورود|لاگین|auth|login", re.IGNORECASE), "AUTH_REQUIRED"),
    ]

    # Security & WAF signals
    WAF_SIGNALS = ["cloudflare", "arvancloud", "access denied", "403 forbidden", "ddos-guard"]
    CAPTCHA_SIGNALS = ["turnstile", "recaptcha", "hcaptcha", "security check", "challenge"]

    @classmethod
    def translate_modal_message(cls, modal_text: str, context: Optional[Dict[str, Any]] = None) -> OmnixVendorError:
        """
        Translate Persian SweetAlert2 modal text to typed Omnix error.
        """
        clean_text = (modal_text or "").strip()
        ctx = context or {}

        for pattern, category in cls.SWAL_PATTERNS:
            if pattern.search(clean_text):
                if category == "MOQ_VIOLATION":
                    return MOQViolationError(f"Lion MOQ constraint: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "ORDER_MULTIPLE_VIOLATION":
                    return OrderMultipleViolationError(f"Lion order multiple constraint: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "MAX_QUANTITY_EXCEEDED":
                    return MaxQuantityExceededError(f"Lion stock ceiling exceeded: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "OUT_OF_STOCK":
                    return OutOfStockError(f"Lion out of stock: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "AUTH_REQUIRED":
                    return AuthenticationRequiredError(f"Lion authentication required: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)

        return UnknownVendorError(f"Lion store notice: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)

    @classmethod
    def translate_page_state(
        cls,
        http_status: Optional[int] = None,
        page_title: str = "",
        page_source: str = "",
        current_url: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[OmnixVendorError]:
        """
        Inspect current browser page state and classify errors.
        Returns None if page is in normal operational state.
        """
        ctx = context or {}
        lower_title = page_title.lower()
        lower_url = current_url.lower()
        lower_src = page_source.lower()

        # CAPTCHA / Security challenge
        if any(c in lower_src or c in lower_title for c in cls.CAPTCHA_SIGNALS):
            return SecurityChallengeError("Lion CAPTCHA or Turnstile security challenge triggered", vendor_id=VENDOR_ID, raw_error="Security Challenge", context=ctx)

        # HTTP Status Checks
        if http_status == 404 or "404" in lower_title or "صفحه‌ای یافت نشد" in page_source:
            return ProductNotFoundError("Lion product or page not found (HTTP 404)", vendor_id=VENDOR_ID, raw_error="404 Not Found", context=ctx)

        if http_status == 403 or any(w in lower_title or w in lower_src for w in cls.WAF_SIGNALS):
            return WAFBlockError("Lion WAF or Cloudflare protection block (HTTP 403)", vendor_id=VENDOR_ID, raw_error="WAF Block", context=ctx)

        if http_status == 401 or ("login" in lower_url and ctx.get("expect_authenticated", False)):
            return SessionExpiredError("Lion session expired or unauthorized (HTTP 401)", vendor_id=VENDOR_ID, raw_error="401 Unauthorized", context=ctx)

        return None

    @classmethod
    def translate_transport_exception(cls, exc: Exception, context: Optional[Dict[str, Any]] = None) -> OmnixVendorError:
        """
        Translate Python/Selenium/HTTP transport exceptions.
        """
        ctx = context or {}
        err_str = str(exc)

        if "TimeoutException" in type(exc).__name__ or "timeout" in err_str.lower():
            return TransportNetworkError(f"Lion transport timeout: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)

        if "NoSuchElementException" in type(exc).__name__ or "element not found" in err_str.lower():
            return DOMDriftError(f"Lion DOM element not found: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)

        return TransportNetworkError(f"Lion transport error: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)
