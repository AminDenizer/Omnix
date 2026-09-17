import os
import json
from typing import Dict, Any, Optional
from config import get_app_dir
from core.models import VendorSettings


class SettingsManager:
    """
    Manages application settings, multi-vendor configurations, credentials,
    and automation options in settings.json.
    Governing GAP: GAP-11.
    """

    SETTINGS_FILENAME = "settings.json"

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or os.path.join(get_app_dir(), self.SETTINGS_FILENAME)
        self.settings: Dict[str, Any] = self._default_settings()
        self.load()

    def _default_settings(self) -> Dict[str, Any]:
        return {
            "lion_username": "",
            "lion_password": "",
            "show_browser": False,
            "auto_check_startup_shortage": True,
            "default_min_stock": 0,
            "default_target_stock": 0,
            "vendors": {
                "vendor_lion": {
                    "vendor_id": "vendor_lion",
                    "enabled": True,
                    "username": "",
                    "password": "",
                    "timeout_seconds": 10.0,
                    "headless": True,
                    "extra_options": {},
                },
                "vendor_javan": {
                    "vendor_id": "vendor_javan",
                    "enabled": True,
                    "username": "",
                    "password": "",
                    "timeout_seconds": 10.0,
                    "headless": True,
                    "extra_options": {},
                },
                "vendor_roboeq": {
                    "vendor_id": "vendor_roboeq",
                    "enabled": True,
                    "username": "",
                    "password": "",
                    "timeout_seconds": 10.0,
                    "headless": True,
                    "extra_options": {},
                },
            },
        }

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge top level
                    for k, v in loaded.items():
                        if k == "vendors" and isinstance(v, dict):
                            if "vendors" not in self.settings:
                                self.settings["vendors"] = {}
                            for vid, vcfg in v.items():
                                if isinstance(vcfg, dict):
                                    if vid not in self.settings["vendors"]:
                                        self.settings["vendors"][vid] = {}
                                    self.settings["vendors"][vid].update(vcfg)
                        else:
                            self.settings[k] = v
            except Exception:
                pass

        # Sync legacy Lion fields with vendors.vendor_lion
        v_dict = self.settings.setdefault("vendors", {})
        lion_cfg = v_dict.setdefault("vendor_lion", {
            "vendor_id": "vendor_lion",
            "enabled": True,
            "username": "",
            "password": "",
            "timeout_seconds": 10.0,
            "headless": True,
            "extra_options": {},
        })

        if self.settings.get("lion_username") and not lion_cfg.get("username"):
            lion_cfg["username"] = self.settings["lion_username"]
        if self.settings.get("lion_password") and not lion_cfg.get("password"):
            lion_cfg["password"] = self.settings["lion_password"]
        if self.settings.get("show_browser"):
            lion_cfg["headless"] = not self.settings["show_browser"]

        # Ensure legacy keys mirror vendor_lion
        if lion_cfg.get("username"):
            self.settings["lion_username"] = lion_cfg["username"]
        if lion_cfg.get("password"):
            self.settings["lion_password"] = lion_cfg["password"]
        if "headless" in lion_cfg:
            self.settings["show_browser"] = not lion_cfg["headless"]

        return self.settings

    def save(self) -> bool:
        try:
            # Sync legacy keys before write
            lion_cfg = self.settings.get("vendors", {}).get("vendor_lion", {})
            if lion_cfg:
                if "username" in lion_cfg:
                    self.settings["lion_username"] = lion_cfg["username"]
                if "password" in lion_cfg:
                    self.settings["lion_password"] = lion_cfg["password"]
                if "headless" in lion_cfg:
                    self.settings["show_browser"] = not lion_cfg["headless"]

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        # Sync to vendor_lion if legacy key modified
        v_dict = self.settings.setdefault("vendors", {})
        lion_cfg = v_dict.setdefault("vendor_lion", {
            "vendor_id": "vendor_lion",
            "enabled": True,
            "username": "",
            "password": "",
            "timeout_seconds": 10.0,
            "headless": True,
            "extra_options": {},
        })
        if key == "lion_username":
            lion_cfg["username"] = value
        elif key == "lion_password":
            lion_cfg["password"] = value
        elif key == "show_browser":
            lion_cfg["headless"] = not value

        self.save()

    def get_vendor_settings(self, vendor_id: str) -> VendorSettings:
        """Retrieve structured VendorSettings for a vendor."""
        clean_id = vendor_id.strip()
        v_dict = self.settings.setdefault("vendors", {})
        raw = v_dict.get(clean_id)
        if raw and isinstance(raw, dict):
            return VendorSettings.from_dict(raw)

        # Default config if not previously saved
        default_cfg = VendorSettings(vendor_id=clean_id, enabled=True, timeout_seconds=10.0, headless=True)
        v_dict[clean_id] = default_cfg.to_dict()
        return default_cfg

    def set_vendor_settings(self, vendor_id: str, config: VendorSettings):
        """Save structured VendorSettings for a vendor."""
        clean_id = vendor_id.strip()
        v_dict = self.settings.setdefault("vendors", {})
        v_dict[clean_id] = config.to_dict()

        if clean_id == "vendor_lion":
            self.settings["lion_username"] = config.username
            self.settings["lion_password"] = config.password
            self.settings["show_browser"] = not config.headless

        self.save()

    def get_all_vendor_settings(self) -> Dict[str, VendorSettings]:
        """Retrieve all registered/configured vendor settings."""
        v_dict = self.settings.setdefault("vendors", {})
        return {vid: VendorSettings.from_dict(cfg) for vid, cfg in v_dict.items() if isinstance(cfg, dict)}

    def is_vendor_enabled(self, vendor_id: str) -> bool:
        """Check if a specific vendor is enabled."""
        return self.get_vendor_settings(vendor_id).enabled

    def set_vendor_enabled(self, vendor_id: str, enabled: bool):
        """Enable or disable a specific vendor."""
        cfg = self.get_vendor_settings(vendor_id)
        cfg.enabled = enabled
        self.set_vendor_settings(vendor_id, cfg)


# Global settings instance
settings = SettingsManager()
