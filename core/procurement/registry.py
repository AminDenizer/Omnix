"""
Omnix Core - Vendor Registry & Adapter Factory
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 15
"""

import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, Any

from core.errors import UnknownVendorError
from core.models import AdapterConfig, VendorSettings
from core.vendor_interface import IVendorAdapter


@dataclass
class VendorRegistration:
    """Metadata describing a registered vendor adapter and its storefront routing."""
    vendor_id: str
    adapter_class: Type[IVendorAdapter]
    default_config: Optional[AdapterConfig] = None
    domains: List[str] = field(default_factory=list)
    display_name: str = ""
    description: str = ""
    enabled: bool = True
    settings: Optional[VendorSettings] = None


class VendorRegistry:
    """
    Thread-safe registry and factory for Omnix Vendor Adapters.
    
    Responsibilities:
    1. Dynamic registration of IVendorAdapter classes.
    2. Deterministic adapter lookup and instantiation without browser side-effects.
    3. Declarative storefront URL routing without hardcoded inline conditions.
    4. Duplicate registration protection and unknown vendor error enforcement.
    5. Multi-vendor dynamic enable/disable tracking (GAP-11).
    6. Complete isolation from DOM selectors, HTML parsing, or procurement math.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._registrations: Dict[str, VendorRegistration] = {}
        self._domain_to_vendor: Dict[str, str] = {}

    def register_adapter(
        self,
        vendor_id: str,
        adapter_class: Type[IVendorAdapter],
        config: Optional[AdapterConfig] = None,
        domains: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        description: str = "",
        enabled: bool = True,
        settings: Optional[VendorSettings] = None,
    ) -> None:
        """
        Register a vendor adapter class with the registry.
        
        Args:
            vendor_id: Unique string identifier (e.g. 'vendor_lion', 'vendor_javan').
            adapter_class: Subclass of IVendorAdapter.
            config: Optional default AdapterConfig.
            domains: Optional list of storefront domains (e.g. ['lionelectronic.ir']).
            display_name: Human-readable vendor name.
            description: Optional vendor description.
            enabled: Initial enabled flag for the vendor (GAP-11).
            settings: Optional VendorSettings model.
            
        Raises:
            ValueError: If vendor_id is invalid, adapter_class is not an IVendorAdapter,
                        or vendor_id is already registered.
        """
        if not vendor_id or not isinstance(vendor_id, str) or not vendor_id.strip():
            raise ValueError("vendor_id must be a non-empty string.")

        clean_id = vendor_id.strip()

        if not isinstance(adapter_class, type) or not issubclass(adapter_class, IVendorAdapter):
            raise ValueError(f"adapter_class for '{clean_id}' must be a subclass of IVendorAdapter.")

        with self._lock:
            if clean_id in self._registrations:
                raise ValueError(f"Vendor '{clean_id}' is already registered in VendorRegistry.")

            # Determine domain list
            target_domains: List[str] = []
            if domains:
                for d in domains:
                    norm_d = self._normalize_domain(d)
                    if norm_d and norm_d not in target_domains:
                        target_domains.append(norm_d)
            elif config and config.base_url:
                norm_d = self._extract_domain_from_url(config.base_url)
                if norm_d and norm_d not in target_domains:
                    target_domains.append(norm_d)

            effective_enabled = enabled
            if settings is not None:
                effective_enabled = settings.enabled

            reg = VendorRegistration(
                vendor_id=clean_id,
                adapter_class=adapter_class,
                default_config=config,
                domains=target_domains,
                display_name=display_name or clean_id,
                description=description,
                enabled=effective_enabled,
                settings=settings,
            )

            self._registrations[clean_id] = reg

            # Map domains
            for d in target_domains:
                self._domain_to_vendor[d] = clean_id

    def is_vendor_enabled(self, vendor_id: str) -> bool:
        """
        Check if a registered vendor is currently enabled.
        Governing GAP: GAP-11 Section 3.1.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        clean_id = vendor_id.strip()
        with self._lock:
            reg = self._registrations.get(clean_id)
            if reg is None:
                return False
            return reg.enabled

    def set_vendor_enabled(self, vendor_id: str, enabled: bool) -> None:
        """
        Dynamically enable or disable a registered vendor.
        Governing GAP: GAP-11 Section 3.1.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))
        clean_id = vendor_id.strip()
        with self._lock:
            reg = self._registrations.get(clean_id)
            if reg is None:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            reg.enabled = enabled
            if reg.settings is not None:
                reg.settings.enabled = enabled

    def get_enabled_vendors(self) -> List[str]:
        """
        Return a sorted list of all registered vendor identifiers that are currently enabled.
        Governing GAP: GAP-11 Section 3.1.
        """
        with self._lock:
            return sorted([vid for vid, reg in self._registrations.items() if reg.enabled])

    def get_adapter(
        self,
        vendor_id: str,
        config: Optional[AdapterConfig] = None,
    ) -> IVendorAdapter:
        """
        Instantiate and return an IVendorAdapter for the given vendor_id.
        
        Note:
            Does NOT launch browser sessions or call initialize().
            Lifecycle initialization is managed explicitly by the caller/orchestrator.
            
        Args:
            vendor_id: Registered vendor identifier.
            config: Optional custom AdapterConfig. If None, uses registered default_config.
            
        Returns:
            An instantiated IVendorAdapter object.
            
        Raises:
            UnknownVendorError: If vendor_id is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid or empty vendor_id provided.", vendor_id=str(vendor_id))

        clean_id = vendor_id.strip()

        with self._lock:
            reg = self._registrations.get(clean_id)
            if reg is None:
                raise UnknownVendorError(
                    f"Unknown vendor identifier '{clean_id}'. Registered vendors: {list(self._registrations.keys())}",
                    vendor_id=clean_id,
                )

            effective_config = config or reg.default_config
            adapter_instance = reg.adapter_class(config=effective_config)
            return adapter_instance

    def get_vendor_for_url(self, url: str, enabled_only: bool = False) -> Optional[str]:
        """
        Deterministically resolve an e-commerce storefront URL to a registered vendor_id.
        
        Args:
            url: Storefront URL or product link.
            enabled_only: If True, returns None if the matching vendor is disabled.
            
        Returns:
            Matching vendor_id string, or None if the URL does not belong to any registered vendor
            (or if vendor is disabled when enabled_only is True).
        """
        if not url or not isinstance(url, str) or not url.strip():
            return None

        extracted_domain = self._extract_domain_from_url(url)
        if not extracted_domain:
            return None

        with self._lock:
            matched_vid: Optional[str] = None
            # 1. Exact domain match
            if extracted_domain in self._domain_to_vendor:
                matched_vid = self._domain_to_vendor[extracted_domain]
            else:
                # 2. Subdomain match (e.g. shop.lionelectronic.ir -> lionelectronic.ir)
                for registered_domain, vid in self._domain_to_vendor.items():
                    if extracted_domain.endswith("." + registered_domain):
                        matched_vid = vid
                        break

            if matched_vid is not None:
                if enabled_only and not self.is_vendor_enabled(matched_vid):
                    return None
                return matched_vid

        return None

    def list_vendors(self) -> List[str]:
        """Return a sorted list of all registered vendor identifiers."""
        with self._lock:
            return sorted(self._registrations.keys())

    def get_registration(self, vendor_id: str) -> VendorRegistration:
        """
        Retrieve metadata for a registered vendor.
        
        Raises:
            UnknownVendorError: If vendor_id is not registered.
        """
        if not vendor_id or not isinstance(vendor_id, str):
            raise UnknownVendorError("Invalid vendor_id provided.", vendor_id=str(vendor_id))

        clean_id = vendor_id.strip()

        with self._lock:
            reg = self._registrations.get(clean_id)
            if reg is None:
                raise UnknownVendorError(f"Vendor '{clean_id}' is not registered.", vendor_id=clean_id)
            return reg

    def get_vendor_name(self, vendor_id: str) -> str:
        """Return human-readable display name for a vendor."""
        if not vendor_id:
            return "Vendor"
        clean_id = vendor_id.strip()
        with self._lock:
            reg = self._registrations.get(clean_id)
            if reg and reg.display_name:
                return reg.display_name
            return clean_id.replace("vendor_", "").title()

    def has_vendor(self, vendor_id: str) -> bool:
        """Check if a vendor_id is registered."""
        if not vendor_id or not isinstance(vendor_id, str):
            return False
        with self._lock:
            return vendor_id.strip() in self._registrations

    def clear(self) -> None:
        """Clear all registrations (for testing isolation)."""
        with self._lock:
            self._registrations.clear()
            self._domain_to_vendor.clear()

    def register_default_adapters(self, settings_mgr: Optional[Any] = None) -> None:
        """
        Register the standard Omnix production vendor adapters:
        - vendor_lion (Lion Electronic: lionelectronic.ir)
        - vendor_javan (Javan Electronic: javanelec.com)
        - vendor_roboeq (RoboEq Electronic: roboeq.ir)
        
        Ingests multi-vendor settings from SettingsManager (GAP-11).
        """
        from vendors.lion.adapter import LionVendorAdapter
        from vendors.javan.adapter import JavanVendorAdapter
        from vendors.roboeq.adapter import RoboEqVendorAdapter

        if settings_mgr is None:
            try:
                from settings_manager import settings
                settings_mgr = settings
            except Exception:
                settings_mgr = None

        with self._lock:
            # 1. Lion Electronic
            if not self.has_vendor(LionVendorAdapter.VENDOR_ID):
                lion_settings = settings_mgr.get_vendor_settings(LionVendorAdapter.VENDOR_ID) if settings_mgr else None
                lion_enabled = lion_settings.enabled if lion_settings else True
                lion_timeout = lion_settings.timeout_seconds if lion_settings else 10.0
                lion_headless = lion_settings.headless if lion_settings else True

                self.register_adapter(
                    vendor_id=LionVendorAdapter.VENDOR_ID,
                    adapter_class=LionVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=LionVendorAdapter.VENDOR_ID,
                        base_url=LionVendorAdapter.BASE_URL,
                        headless=lion_headless,
                        timeout_seconds=lion_timeout,
                    ),
                    domains=["lionelectronic.ir"],
                    display_name="Lion Electronic",
                    description="Lion Electronic Component Distributor",
                    enabled=lion_enabled,
                    settings=lion_settings,
                )

            # 2. Javan Electronic
            if not self.has_vendor(JavanVendorAdapter.VENDOR_ID):
                javan_settings = settings_mgr.get_vendor_settings(JavanVendorAdapter.VENDOR_ID) if settings_mgr else None
                javan_enabled = javan_settings.enabled if javan_settings else True
                javan_timeout = javan_settings.timeout_seconds if javan_settings else 10.0
                javan_headless = javan_settings.headless if javan_settings else True

                self.register_adapter(
                    vendor_id=JavanVendorAdapter.VENDOR_ID,
                    adapter_class=JavanVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=JavanVendorAdapter.VENDOR_ID,
                        base_url=JavanVendorAdapter.BASE_URL,
                        headless=javan_headless,
                        timeout_seconds=javan_timeout,
                    ),
                    domains=["javanelec.com"],
                    display_name="Javan Electronic",
                    description="Javan Electronic Components & Kits",
                    enabled=javan_enabled,
                    settings=javan_settings,
                )

            # 3. RoboEq Electronic
            if not self.has_vendor(RoboEqVendorAdapter.VENDOR_ID):
                roboeq_settings = settings_mgr.get_vendor_settings(RoboEqVendorAdapter.VENDOR_ID) if settings_mgr else None
                roboeq_enabled = roboeq_settings.enabled if roboeq_settings else True
                roboeq_timeout = roboeq_settings.timeout_seconds if roboeq_settings else 10.0
                roboeq_headless = roboeq_settings.headless if roboeq_settings else True

                self.register_adapter(
                    vendor_id=RoboEqVendorAdapter.VENDOR_ID,
                    adapter_class=RoboEqVendorAdapter,
                    config=AdapterConfig(
                        vendor_id=RoboEqVendorAdapter.VENDOR_ID,
                        base_url=RoboEqVendorAdapter.BASE_URL,
                        headless=roboeq_headless,
                        timeout_seconds=roboeq_timeout,
                    ),
                    domains=["roboeq.ir"],
                    display_name="RoboEq Electronic",
                    description="RoboEq Marketplace Distributor",
                    enabled=roboeq_enabled,
                    settings=roboeq_settings,
                )

    @staticmethod
    def _normalize_domain(domain_str: str) -> str:
        """Normalize a domain string (lowercase, stripped, remove leading www.)."""
        d = domain_str.strip().lower()
        if d.startswith("http://") or d.startswith("https://"):
            return VendorRegistry._extract_domain_from_url(d)
        if d.startswith("www."):
            d = d[4:]
        # Remove any trailing path/slash
        d = d.split("/")[0].split(":")[0]
        return d

    @staticmethod
    def _extract_domain_from_url(url: str) -> str:
        """Extract and normalize hostname from URL."""
        if not url or not isinstance(url, str):
            return ""
        u = url.strip()
        if not u:
            return ""

        # Check scheme case-insensitively
        u_lower = u.lower()
        if not (u_lower.startswith("http://") or u_lower.startswith("https://") or u_lower.startswith("//")):
            u = "https://" + u

        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.netloc or parsed.path.split("/")[0]
            # Strip port
            host = host.split(":")[0].strip().lower()
            # Strip leading www.
            if host.startswith("www."):
                host = host[4:]
            return host
        except Exception:
            return ""

    @classmethod
    def get_default_registry(cls) -> "VendorRegistry":
        """Retrieve the global default singleton with production adapters registered."""
        global _default_registry_initialized
        if not _default_registry_initialized:
            with default_registry._lock:
                if not _default_registry_initialized:
                    default_registry.register_default_adapters()
                    _default_registry_initialized = True
        return default_registry


# Module-level default singleton registry
default_registry = VendorRegistry()
_default_registry_initialized = False
