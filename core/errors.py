"""
Omnix Core - Normalized Error Taxonomy
Governing Document: docs/VENDORS/LION/ADAPTER_SPECIFICATION.md Section 8
All 13 standard Omnix vendor error exceptions.
"""

from typing import Optional, Dict, Any


class OmnixVendorError(Exception):
    """Base exception for all normalized vendor adapter errors."""

    def __init__(
        self,
        message: str,
        vendor_id: str = "unknown",
        category: str = "UNKNOWN_VENDOR_ERROR",
        raw_error: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.vendor_id = vendor_id
        self.category = category
        self.raw_error = raw_error or message
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_category": self.category,
            "vendor_id": self.vendor_id,
            "message": self.message,
            "raw_error": self.raw_error,
            "context": self.context,
        }


# Category 1: NOT_FOUND (VERIFIED)
class ProductNotFoundError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="NOT_FOUND", raw_error=raw_error, context=context)


# Category 2: ZERO_RESULTS (VERIFIED)
class ZeroSearchResultsError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="ZERO_RESULTS", raw_error=raw_error, context=context)


# Category 3: OUT_OF_STOCK (VERIFIED)
class OutOfStockError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="OUT_OF_STOCK", raw_error=raw_error, context=context)


# Category 4: MOQ_VIOLATION (VERIFIED)
class MOQViolationError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="MOQ_VIOLATION", raw_error=raw_error, context=context)


# Category 5: ORDER_MULTIPLE_VIOLATION (VERIFIED)
class OrderMultipleViolationError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="ORDER_MULTIPLE_VIOLATION", raw_error=raw_error, context=context)


# Category 6: MAX_QUANTITY_EXCEEDED (VERIFIED)
class MaxQuantityExceededError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="MAX_QUANTITY_EXCEEDED", raw_error=raw_error, context=context)


# Category 7: NETWORK_ERROR (VERIFIED)
class TransportNetworkError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="NETWORK_ERROR", raw_error=raw_error, context=context)


# Category 8: AUTH_REQUIRED (OBSERVED / DEFENSIVE)
class AuthenticationRequiredError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="AUTH_REQUIRED", raw_error=raw_error, context=context)


# Category 9: SESSION_EXPIRED (OBSERVED / DEFENSIVE)
class SessionExpiredError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="SESSION_EXPIRED", raw_error=raw_error, context=context)


# Category 10: CAPTCHA_TRIGGERED (OBSERVED / DEFENSIVE)
class SecurityChallengeError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="CAPTCHA_TRIGGERED", raw_error=raw_error, context=context)


# Category 11: WAF_BLOCK (OBSERVED / DEFENSIVE)
class WAFBlockError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="WAF_BLOCK", raw_error=raw_error, context=context)


# Category 12: DOM_DRIFT (OBSERVED / DEFENSIVE)
class DOMDriftError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="DOM_DRIFT", raw_error=raw_error, context=context)


# Category 13: UNKNOWN_VENDOR_ERROR (OBSERVED / DEFENSIVE)
class UnknownVendorError(OmnixVendorError):
    def __init__(self, message: str, vendor_id: str = "unknown", raw_error: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, vendor_id=vendor_id, category="UNKNOWN_VENDOR_ERROR", raw_error=raw_error, context=context)
