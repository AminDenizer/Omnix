"""
Omnix Unit & Contract Tests for GAP-09: Interactive Authentication & Headful Fallback
Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-09, GAP-17)
"""

import pytest
from unittest.mock import MagicMock, patch
from core.models import AuthCredentials, AuthResult, SessionStatus, AdapterConfig
from core.models import (
    SessionContinuityMode,
    SessionPromotionResult,
)
from vendors.lion.adapter import LionVendorAdapter
from vendors.javan.adapter import JavanVendorAdapter
from vendors.roboeq.adapter import RoboEqVendorAdapter


class TestSessionPromotionContracts:
    """Tests session promotion between headless and headful modes (GAP-09)."""

    def test_lion_session_promotion_contract(self):
        adapter = LionVendorAdapter()
        session = adapter.session

        # Mock driver state
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = [{"name": "session_id", "value": "xyz123"}]
        mock_driver.current_url = "https://lionelectronic.ir/profile"
        session.driver = mock_driver

        with patch.object(session, "create_driver") as mock_create:
            mock_new_driver = MagicMock()
            mock_create.return_value = mock_new_driver

            res = session.promote_to_headful()
            assert res.success is True
            assert res.continuity_mode == SessionContinuityMode.STATE_TRANSFERRED
            assert res.cookies_transferred == 1
            assert session.config.headless is False

    def test_javan_session_promotion_contract(self):
        adapter = JavanVendorAdapter()
        session = adapter.session

        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = [{"name": "auth_cookie", "value": "abc"}]
        mock_driver.current_url = "https://javanelec.com/user"
        session.driver = mock_driver

        with patch.object(session, "create_driver") as mock_create:
            mock_new_driver = MagicMock()
            mock_create.return_value = mock_new_driver

            res = session.promote_to_headful()
            assert res.success is True
            assert res.continuity_mode == SessionContinuityMode.STATE_TRANSFERRED
            assert res.cookies_transferred == 1
            assert session.config.headless is False

    def test_roboeq_session_promotion_contract(self):
        adapter = RoboEqVendorAdapter()
        session = adapter.session

        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = []
        mock_driver.current_url = "https://roboeq.ir/login"
        session.driver = mock_driver

        with patch.object(session, "create_driver") as mock_create:
            mock_new_driver = MagicMock()
            mock_create.return_value = mock_new_driver

            res = session.promote_to_headful()
            assert res.success is True
            assert res.continuity_mode == SessionContinuityMode.BROWSER_RECREATED_UNAUTHENTICATED
            assert session.config.headless is False


class TestInteractiveAuthenticationFlow:
    """Tests interactive authentication workflows across adapters (GAP-09, GAP-17)."""

    def test_auth_missing_credentials_fails_gracefully(self):
        adapter = LionVendorAdapter()
        with patch("settings_manager.settings.get_vendor_settings", return_value=None):
            res = adapter.authenticate(credentials=None)
            assert res.success is False
            assert "not provided" in res.message
