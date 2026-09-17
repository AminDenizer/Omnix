"""
Omnix Unit & Contract Tests for GAP-17: Universal Security Challenge / CAPTCHA Handler
Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-17)
"""

import pytest
from core.procurement.challenge_handler import (
    ChallengeType,
    ChallengeState,
    AuthLifecycleState,
    SessionContinuityMode,
    SessionPromotionResult,
    ChallengeContext,
    ChallengeResult,
    IChallengeHandler,
    CallbackChallengeHandler,
)


class TestChallengeModelEnumsAndContracts:
    """Verifies all challenge types and state transitions (GAP-17)."""

    def test_challenge_type_all_8_classes(self):
        expected_types = [
            "CAPTCHA",
            "IMAGE_CAPTCHA",
            "TEXT_CAPTCHA",
            "RECAPTCHA",
            "HCAPTCHA",
            "TURNSTILE",
            "OTP",
            "CUSTOM",
        ]
        for t in expected_types:
            assert ChallengeType(t) is not None
            assert ChallengeType(t).value == t

    def test_challenge_state_all_states(self):
        expected_states = [
            "NO_CHALLENGE",
            "DETECTED",
            "WAITING_FOR_USER",
            "SOLVED",
            "CANCELLED",
            "TIMED_OUT",
            "UNSUPPORTED",
            "FAILED",
        ]
        for s in expected_states:
            assert ChallengeState(s) is not None
            assert ChallengeState(s).value == s

    def test_auth_lifecycle_states(self):
        expected_states = [
            "UNAUTHENTICATED",
            "AUTHENTICATING",
            "AUTHENTICATED",
            "AUTH_FAILED",
            "CHALLENGE_REQUIRED",
            "INTERACTIVE_REQUIRED",
            "WAITING_FOR_USER",
            "CANCELLED",
            "SESSION_EXPIRED",
        ]
        for s in expected_states:
            assert AuthLifecycleState(s) is not None

    def test_session_continuity_mode_enum(self):
        modes = [
            "SAME_CONTEXT_PRESERVED",
            "STATE_TRANSFERRED",
            "BROWSER_RECREATED_UNAUTHENTICATED",
            "CONTINUITY_UNAVAILABLE",
        ]
        for m in modes:
            assert SessionContinuityMode(m) is not None


class TestChallengeContextAndResult:
    """Tests for ChallengeContext and ChallengeResult data structures."""

    def test_valid_challenge_context(self):
        ctx = ChallengeContext(
            vendor_id="vendor_lion",
            challenge_type=ChallengeType.IMAGE_CAPTCHA,
            prompt_message="Please solve CAPTCHA",
            target_url="https://lionelectronic.ir/login",
            image_base64="data:image/png;base64,iVBORw0KGgo...",
            timeout_seconds=45.0,
        )
        assert ctx.vendor_id == "vendor_lion"
        assert ctx.challenge_type == ChallengeType.IMAGE_CAPTCHA
        assert ctx.timeout_seconds == 45.0

    def test_invalid_vendor_id_raises(self):
        with pytest.raises(ValueError):
            ChallengeContext(
                vendor_id="",
                challenge_type=ChallengeType.CAPTCHA,
                prompt_message="test",
                target_url="https://test.ir",
            )

    def test_challenge_result_properties(self):
        res_solved = ChallengeResult(
            vendor_id="vendor_lion",
            challenge_type=ChallengeType.IMAGE_CAPTCHA,
            state=ChallengeState.SOLVED,
            solution="4792",
        )
        assert res_solved.is_solved is True
        assert res_solved.is_cancelled is False

        res_cancelled = ChallengeResult(
            vendor_id="vendor_lion",
            challenge_type=ChallengeType.TURNSTILE,
            state=ChallengeState.CANCELLED,
        )
        assert res_cancelled.is_solved is False
        assert res_cancelled.is_cancelled is True


class TestCallbackChallengeHandler:
    """Tests for CallbackChallengeHandler resolution flows (GAP-17)."""

    def test_default_solved_flow(self):
        handler = CallbackChallengeHandler(default_solution="CAPTCHA_1234", default_state=ChallengeState.SOLVED)
        ctx = ChallengeContext(
            vendor_id="vendor_javan",
            challenge_type=ChallengeType.IMAGE_CAPTCHA,
            prompt_message="Solve image",
            target_url="https://javanelec.com/login",
        )
        res = handler.handle_challenge(ctx)
        assert res.state == ChallengeState.SOLVED
        assert res.solution == "CAPTCHA_1234"
        assert len(handler.handled_contexts) == 1

    def test_cancelled_flow(self):
        handler = CallbackChallengeHandler(default_state=ChallengeState.CANCELLED)
        ctx = ChallengeContext(
            vendor_id="vendor_roboeq",
            challenge_type=ChallengeType.TURNSTILE,
            prompt_message="Turnstile required",
            target_url="https://roboeq.ir/login",
        )
        res = handler.handle_challenge(ctx)
        assert res.state == ChallengeState.CANCELLED
        assert res.solution is None

    def test_timeout_flow(self):
        handler = CallbackChallengeHandler(default_state=ChallengeState.TIMED_OUT)
        ctx = ChallengeContext(
            vendor_id="vendor_lion",
            challenge_type=ChallengeType.OTP,
            prompt_message="SMS OTP",
            target_url="https://lionelectronic.ir/login",
        )
        res = handler.handle_challenge(ctx)
        assert res.state == ChallengeState.TIMED_OUT

    def test_custom_callback_resolution(self):
        def my_resolver(c: ChallengeContext) -> ChallengeResult:
            if c.challenge_type == ChallengeType.OTP:
                return ChallengeResult(
                    vendor_id=c.vendor_id,
                    challenge_type=c.challenge_type,
                    state=ChallengeState.SOLVED,
                    solution="891011",
                )
            return ChallengeResult(
                vendor_id=c.vendor_id,
                challenge_type=c.challenge_type,
                state=ChallengeState.CANCELLED,
            )

        handler = CallbackChallengeHandler(resolver_callback=my_resolver)
        otp_ctx = ChallengeContext(vendor_id="v1", challenge_type=ChallengeType.OTP, prompt_message="OTP", target_url="https://v1.ir")
        res1 = handler.handle_challenge(otp_ctx)
        assert res1.state == ChallengeState.SOLVED
        assert res1.solution == "891011"

        captcha_ctx = ChallengeContext(vendor_id="v1", challenge_type=ChallengeType.CAPTCHA, prompt_message="Captcha", target_url="https://v1.ir")
        res2 = handler.handle_challenge(captcha_ctx)
        assert res2.state == ChallengeState.CANCELLED
