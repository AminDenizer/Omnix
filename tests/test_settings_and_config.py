import os
import pytest
from settings_manager import settings, SettingsManager
from config import APP_NAME, APP_VERSION, get_app_dir, get_bundle_dir

class TestSettingsAndConfig:
    def test_config_constants(self):
        assert APP_NAME == 'Omnix'
        assert isinstance(APP_VERSION, str)
        assert os.path.exists(get_app_dir())
        assert os.path.exists(get_bundle_dir())

    def test_settings_manager_operations(self):
        # Test defaults / reading settings
        assert isinstance(settings.get('show_browser', False), bool)
        
        # Test setting and reading back
        old_val = settings.get('test_key', None)
        settings.set('test_key', 'test_value_123')
        assert settings.get('test_key') == 'test_value_123'
        
        # Cleanup
        settings.set('test_key', old_val)
