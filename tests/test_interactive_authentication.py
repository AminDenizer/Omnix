"""
Omnix Unit & Contract Tests for GAP-09: Interactive Authentication & Headful Fallback
Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-09, GAP-17)
"""

import pytest
from unittest.mock import MagicMock, patch
from core.models import AuthCredentials, AuthResult, SessionStatus, AdapterConfig
from core.procurement.challenge_handler import (
    ChallengeType,
    ChallengeState,
    ChallengeContext,
    ChallengeResult,
    SessionContinuityMode,
    SessionPromotionResult,
    CallbackChallengeHandler,
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

    def test_lion_upfront_turnstile_challenge_solved(self):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/login"
        mock_driver.page_source = "<html><body><div class='cf-turnstile'></div></body></html>"
        adapter.session.driver = mock_driver

        # Handler that marks solved
        handler = CallbackChallengeHandler(default_state=ChallengeState.SOLVED)

        with patch.object(adapter.session, "promote_to_headful") as mock_promote, \
             patch.object(adapter, "validate_session") as mock_validate:
            mock_validate.return_value = SessionStatus(vendor_id="vendor_lion", is_authenticated=True, session_valid=True)

            creds = AuthCredentials(username="lion_test", password="test_password")
            res = adapter.authenticate(credentials=creds, challenge_handler=handler)

            assert res.success is True
            assert mock_promote.called
            assert len(handler.handled_contexts) == 1
            assert handler.handled_contexts[0].challenge_type == ChallengeType.TURNSTILE

    def test_lion_upfront_challenge_user_cancelled(self):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/login"
        mock_driver.page_source = "<html><body><div class='cf-turnstile'></div></body></html>"
        adapter.session.driver = mock_driver

        handler = CallbackChallengeHandler(default_state=ChallengeState.CANCELLED)

        with patch.object(adapter.session, "promote_to_headful"):
            creds = AuthCredentials(username="lion_test", password="test_password")
            res = adapter.authenticate(credentials=creds, challenge_handler=handler)

            assert res.success is False
            assert "cancelled" in res.message.lower()

    def test_lion_unhandled_challenge_returns_requires_interactive(self):
        adapter = LionVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://lionelectronic.ir/login"
        mock_driver.page_source = "<html><body><div class='g-recaptcha'></div></body></html>"
        adapter.session.driver = mock_driver

        creds = AuthCredentials(username="lion_test", password="test_password")
        res = adapter.authenticate(credentials=creds, challenge_handler=None)

        assert res.success is False
        assert res.requires_interactive is True
        assert res.challenge_context is not None
        assert res.challenge_context.challenge_type == ChallengeType.RECAPTCHA

    def test_javan_login_interactive_flow(self):
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://javanelec.com/login"
        mock_driver.page_source = "<html><body><input name='username'/><input name='password'/></body></html>"
        mock_driver.find_elements.return_value = []

        mock_user = MagicMock()
        mock_pass = MagicMock()
        mock_btn = MagicMock()
        mock_driver.find_element = lambda by, val: mock_user if "username" in val else (mock_pass if "password" in val else mock_btn)

        adapter.session.driver = mock_driver

        with patch.object(adapter, "validate_session") as mock_val:
            mock_val.return_value = SessionStatus(vendor_id="vendor_javan", is_authenticated=True, session_valid=True)

            creds = AuthCredentials(username="javan_user", password="javan_password")
            res = adapter.authenticate(credentials=creds)
            assert res.success is True
            assert "successful" in res.message.lower()

    def test_javan_image_captcha_solving_flow(self):
        adapter = JavanVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://javanelec.com/login"
        mock_driver.page_source = "<html><body><input name='username'/><input name='password'/><img src='captcha.png'/></body></html>"

        mock_user = MagicMock()
        mock_pass = MagicMock()
        mock_btn = MagicMock()
        mock_captcha_input = MagicMock()
        mock_captcha_img = MagicMock()
        mock_captcha_img.get_attribute.return_value = "data:image/png;base64,FAKEIMAGE"

        def mock_find_element(by, val):
            if "username" in val:
                return mock_user
            if "password" in val:
                return mock_pass
            if "captcha" in val:
                return mock_captcha_input
            return mock_btn

        def mock_find_elements(by, val):
            if "input" in val and "captcha" in val:
                return [mock_captcha_input]
            if "img" in val and "captcha" in val:
                return [mock_captcha_img]
            return []

        mock_driver.find_element = mock_find_element
        mock_driver.find_elements = mock_find_elements
        adapter.session.driver = mock_driver

        handler = CallbackChallengeHandler(default_solution="9876", default_state=ChallengeState.SOLVED)

        with patch.object(adapter, "validate_session") as mock_val:
            mock_val.return_value = SessionStatus(vendor_id="vendor_javan", is_authenticated=True, session_valid=True)

            creds = AuthCredentials(username="javan_user", password="javan_password")
            res = adapter.authenticate(credentials=creds, challenge_handler=handler)
            assert res.success is True
            assert len(handler.handled_contexts) == 1
            assert handler.handled_contexts[0].challenge_type == ChallengeType.IMAGE_CAPTCHA
            mock_captcha_input.send_keys.assert_called_with("9876")

    def test_roboeq_post_login_challenge_escalation(self):
        adapter = RoboEqVendorAdapter()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://roboeq.ir/login"
        # Initial page clean
        mock_driver.page_source = "<html><body><form></form></body></html>"

        mock_user = MagicMock()
        mock_btn = MagicMock()
        mock_driver.find_element = lambda by, val: mock_user if "username" in val or "login" in val else mock_btn

        adapter.session.driver = mock_driver
        adapter.session.get_driver = MagicMock(return_value=mock_driver)

        handler = CallbackChallengeHandler(default_state=ChallengeState.SOLVED)

        # After submit, page source contains OTP prompt
        with patch.object(adapter.session, "promote_to_headful") as mock_promote, \
             patch.object(adapter, "_detect_challenge_on_page", side_effect=[None, ChallengeType.OTP]), \
             patch.object(adapter, "validate_session", return_value=SessionStatus(vendor_id="vendor_roboeq", is_authenticated=True)):

            creds = AuthCredentials(username="09120000000", password="fake")
            res = adapter.authenticate(credentials=creds, challenge_handler=handler)

            assert res.success is True
            assert len(handler.handled_contexts) == 1
            assert handler.handled_contexts[0].challenge_type == ChallengeType.OTP

    def test_multi_vendor_isolation_lion_challenge_does_not_affect_javan(self):
        lion = LionVendorAdapter()
        javan = JavanVendorAdapter()

        assert lion.vendor_id != javan.vendor_id
        assert lion.session is not javan.session
        assert lion.session.config.vendor_id == "vendor_lion"
        assert javan.session.config.vendor_id == "vendor_javan"
