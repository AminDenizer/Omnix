import os
import json
from typing import Dict, Any
from config import get_app_dir


class SettingsManager:
    """Manages application settings, credentials, and automation options in settings.json."""

    SETTINGS_FILENAME = "settings.json"

    def __init__(self):
        self.file_path = os.path.join(get_app_dir(), self.SETTINGS_FILENAME)
        self.settings: Dict[str, Any] = self._default_settings()
        self.load()

    def _default_settings(self) -> Dict[str, Any]:
        return {
            "lion_username": "",
            "lion_password": "",
            "show_browser": False,
            "auto_check_startup_shortage": True,
            "default_min_stock": 0,
            "default_target_stock": 0
        }

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception:
                pass
        return self.settings

    def save(self) -> bool:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        self.save()


# Global settings instance
settings = SettingsManager()
