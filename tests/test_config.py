import pytest
import config


class TestConfig:
    """Test suite for application configuration and constants."""

    def test_config_constants(self):
        assert config.APP_NAME == "Omnix"
        assert config.APP_SUBTITLE == "مدیریت قطعات الکترونیک"
        assert config.DEVELOPER_NAME == "AminDenizer"
        assert config.DEVELOPER_ORG == "DOT"
        assert len(config.DEFAULT_CATEGORIES) > 5
        assert len(config.DEFAULT_PACKAGES) > 5
        assert "Resistor" in config.DEFAULT_CATEGORIES
        assert "SMD 0805" in config.DEFAULT_PACKAGES
        assert config.BACKUP_MAGIC_HEADER == "OMNIX_SECURE_BACKUP"
        assert config.BACKUP_SECRET_SALT is not None
