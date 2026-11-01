"""
Lion Electronic Vendor Adapter Package
Exports LionVendorAdapter, LionSelectors, and LionErrorTranslator.
"""

try:
    from .adapter import LionVendorAdapter
    from .selectors import LionSelectors
    from .errors import LionErrorTranslator
    from .session import LionSessionManager
except ImportError:
    from vendors.lion.adapter import LionVendorAdapter
    from vendors.lion.selectors import LionSelectors
    from vendors.lion.errors import LionErrorTranslator
    from vendors.lion.session import LionSessionManager

__all__ = [
    "LionVendorAdapter",
    "LionSelectors",
    "LionErrorTranslator",
    "LionSessionManager",
]
