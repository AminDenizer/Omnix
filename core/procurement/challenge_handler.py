"""
Omnix Core - Universal Security Challenge & Interactive Authentication Handler
Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-17, GAP-09)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Callable, List


class ChallengeType(str, Enum):
    """
    Formal classification of security challenges encountered on vendor storefronts.
    Governing GAP: GAP-17 Section 4.1.
    """
    CAPTCHA = "CAPTCHA"                    # Generic unspecified CAPTCHA
    IMAGE_CAPTCHA = "IMAGE_CAPTCHA"        # Visual image distorted characters
    TEXT_CAPTCHA = "TEXT_CAPTCHA"          # Math question or textual challenge
    RECAPTCHA = "RECAPTCHA"                # Google reCAPTCHA v2/v3
    HCAPTCHA = "HCAPTCHA"                  # hCaptcha checkbox or puzzle
    TURNSTILE = "TURNSTILE"                # Cloudflare Turnstile managed challenge
    OTP = "OTP"                            # SMS / Email One-Time Password
    CUSTOM = "CUSTOM"                      # Vendor-specific custom challenge / modal


class ChallengeState(str, Enum):
    """
    Deterministic resolution state for security challenges.
    Governing GAP: GAP-17 Section 4.2.
    """
    NO_CHALLENGE = "NO_CHALLENGE"
    DETECTED = "DETECTED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    SOLVED = "SOLVED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class AuthLifecycleState(str, Enum):
    """
    Explicit lifecycle states for vendor authentication.
    Governing GAP: GAP-09 Section 5.
    """
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHENTICATING = "AUTHENTICATING"
    AUTHENTICATED = "AUTHENTICATED"
    AUTH_FAILED = "AUTH_FAILED"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    INTERACTIVE_REQUIRED = "INTERACTIVE_REQUIRED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    CANCELLED = "CANCELLED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class SessionContinuityMode(str, Enum):
    """
    Formal qualification of browser session continuity across headless <-> headful transitions.
    Governing Invariant: GAP-09 Session Continuity.
    """
    SAME_CONTEXT_PRESERVED = "SAME_CONTEXT_PRESERVED"
    STATE_TRANSFERRED = "STATE_TRANSFERRED"
    BROWSER_RECREATED_UNAUTHENTICATED = "BROWSER_RECREATED_UNAUTHENTICATED"
    CONTINUITY_UNAVAILABLE = "CONTINUITY_UNAVAILABLE"


@dataclass
class SessionPromotionResult:
    """Outcome of promoting/demoting browser between headless and headful modes."""
    success: bool
    continuity_mode: SessionContinuityMode
    message: str = ""
    cookies_transferred: int = 0
    active_url: Optional[str] = None


@dataclass
class ChallengeContext:
    """
    Vendor-neutral context payload describing a detected challenge for human solving.
    Zero DOM selectors or vendor HTML leaked into this contract.
    """
    vendor_id: str
    challenge_type: ChallengeType
    prompt_message: str
    target_url: str
    image_base64: Optional[str] = None
    image_bytes: Optional[bytes] = None
    timeout_seconds: float = 60.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.vendor_id or not isinstance(self.vendor_id, str):
            raise ValueError("vendor_id must be a non-empty string.")
        if not isinstance(self.challenge_type, ChallengeType):
            if isinstance(self.challenge_type, str):
                self.challenge_type = ChallengeType(self.challenge_type)
            else:
                raise ValueError(f"Invalid challenge_type: {self.challenge_type}")


@dataclass
class ChallengeResult:
    """
    Explicit outcome of a human-in-the-loop challenge resolution attempt.
    """
    vendor_id: str
    challenge_type: ChallengeType
    state: ChallengeState
    solution: Optional[str] = None
    session_token: Optional[str] = None
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_solved(self) -> bool:
        return self.state == ChallengeState.SOLVED

    @property
    def is_cancelled(self) -> bool:
        return self.state == ChallengeState.CANCELLED


class IChallengeHandler(ABC):
    """
    Universal interface for handling security challenges.
    All challenge handling MUST be human-in-the-loop.
    Zero autonomous CAPTCHA solving or third-party bypass services permitted.
    """

    @abstractmethod
    def handle_challenge(self, context: ChallengeContext) -> ChallengeResult:
        """
        Present the challenge to the user and return the explicit resolution result.
        
        Args:
            context: Vendor-neutral ChallengeContext describing the challenge.
            
        Returns:
            ChallengeResult indicating SOLVED, CANCELLED, TIMED_OUT, UNSUPPORTED, or FAILED.
        """
        pass


class CallbackChallengeHandler(IChallengeHandler):
    """
    Deterministic callback-based challenge handler for automated testing,
    CLI integration, and programmatic resolution workflows.
    """

    def __init__(
        self,
        resolver_callback: Optional[Callable[[ChallengeContext], ChallengeResult]] = None,
        default_solution: Optional[str] = None,
        default_state: ChallengeState = ChallengeState.SOLVED,
    ):
        self._callback = resolver_callback
        self._default_solution = default_solution
        self._default_state = default_state
        self.handled_contexts: List[ChallengeContext] = []

    def handle_challenge(self, context: ChallengeContext) -> ChallengeResult:
        self.handled_contexts.append(context)
        if self._callback is not None:
            return self._callback(context)
        return ChallengeResult(
            vendor_id=context.vendor_id,
            challenge_type=context.challenge_type,
            state=self._default_state,
            solution=self._default_solution,
            message=f"Callback handled challenge ({self._default_state.value}).",
        )
