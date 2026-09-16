"""
Javan Electronic Error Translation Layer
Translates vendor-specific DOM, HTTP, and transport signals into 13 Omnix error categories.
Governing Document: docs/VENDORS/JAVAN/ADAPTER_SPECIFICATION.md Section 8
"""

import re
from typing import Optional, Dict, Any

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

VENDOR_ID = "vendor_javan"


class JavanErrorTranslator:
    """
    3-Tier translation engine for Javan Electronic:
    1. DOM / Modal / Toast analysis
    2. HTTP status & URL redirect analysis
    3. Transport & Selenium driver exception analysis
    """

    # Keyword patterns for validation messages / modals
    MODAL_PATTERNS = [
        (re.compile(r"حداقل|moq|تعداد کمتر از حد مجاز", re.IGNORECASE), "MOQ_VIOLATION"),
        (re.compile(r"ضریب|مضرب|بسته|step|multiple|بسته‌بندی", re.IGNORECASE), "ORDER_MULTIPLE_VIOLATION"),
        (re.compile(r"موجودی کافی نیست|عدم موجودی کافی|سقف موجودی|بیش از موجودی|موجودی انبار", re.IGNORECASE), "MAX_QUANTITY_EXCEEDED"),
        (re.compile(r"اتمام موجودی|ناموجود|تمام شد|عدم موجودی", re.IGNORECASE), "OUT_OF_STOCK"),
        (re.compile(r"ورود|لاگین|auth|login|ابتدا وارد شوید", re.IGNORECASE), "AUTH_REQUIRED"),
    ]

    # Security & WAF signals
    WAF_SIGNALS = ["cloudflare", "arvancloud", "access denied", "403 forbidden", "ddos-guard", "firewall"]
    CAPTCHA_SIGNALS = [
        "turnstile",
        "recaptcha",
        "hcaptcha",
        "security check",
        "security challenge",
        "cf-challenge",
        "challenge-form",
        "cloudflare challenge",
        "کپچا",
        "کد امنیتی",
    ]

    @classmethod
    def translate_modal_message(cls, modal_text: str, context: Optional[Dict[str, Any]] = None) -> OmnixVendorError:
        """
        Translate Persian modal/alert text to typed Omnix error.
        """
        clean_text = (modal_text or "").strip()
        ctx = context or {}

        for pattern, category in cls.MODAL_PATTERNS:
            if pattern.search(clean_text):
                if category == "MOQ_VIOLATION":
                    return MOQViolationError(f"Javan MOQ constraint: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "ORDER_MULTIPLE_VIOLATION":
                    return OrderMultipleViolationError(f"Javan order multiple constraint: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "MAX_QUANTITY_EXCEEDED":
                    return MaxQuantityExceededError(f"Javan stock ceiling exceeded: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "OUT_OF_STOCK":
                    return OutOfStockError(f"Javan out of stock: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)
                elif category == "AUTH_REQUIRED":
                    return AuthenticationRequiredError(f"Javan authentication required: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)

        return UnknownVendorError(f"Javan store notice: {clean_text}", vendor_id=VENDOR_ID, raw_error=clean_text, context=ctx)

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
            return SecurityChallengeError("Javan CAPTCHA or security challenge triggered", vendor_id=VENDOR_ID, raw_error="Security Challenge", context=ctx)

        # HTTP Status Checks & 404 Not Found detection
        if (
            http_status == 404
            or "not found" in lower_title
            or "404" in lower_title
            or "/home/notfound" in lower_url
            or "صفحه مورد نظر شما یافت نشد" in page_source
        ):
            return ProductNotFoundError("Javan product or page not found (HTTP 404 / Not Found)", vendor_id=VENDOR_ID, raw_error="404 Not Found", context=ctx)

        # WAF / Forbidden
        if http_status == 403 or any(w in lower_title or w in lower_src for w in cls.WAF_SIGNALS):
            return WAFBlockError("Javan WAF or firewall block (HTTP 403)", vendor_id=VENDOR_ID, raw_error="WAF Block", context=ctx)

        # Unauthorized / Expired session
        if http_status == 401 or ("/account/login" in lower_url and ctx.get("expect_authenticated", False)):
            return SessionExpiredError("Javan session expired or unauthorized (HTTP 401)", vendor_id=VENDOR_ID, raw_error="401 Unauthorized", context=ctx)

        return None

    @classmethod
    def translate_transport_exception(cls, exc: Exception, context: Optional[Dict[str, Any]] = None) -> OmnixVendorError:
        """
        Translate Python/Selenium/HTTP transport exceptions.
        """
        ctx = context or {}
        err_str = str(exc)

        if "TimeoutException" in type(exc).__name__ or "timeout" in err_str.lower():
            return TransportNetworkError(f"Javan transport timeout: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)

        if (
            "NoSuchElementException" in type(exc).__name__
            or "element not found" in err_str.lower()
            or "nosuchelement" in err_str.lower()
            or "unable to locate element" in err_str.lower()
        ):
            return DOMDriftError(f"Javan DOM element not found: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)

        return TransportNetworkError(f"Javan transport error: {err_str}", vendor_id=VENDOR_ID, raw_error=err_str, context=ctx)
