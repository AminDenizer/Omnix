"""
Omnix UI - Universal Security Challenge Dialog & Qt Handler
Governing GAP: GAP-17, GAP-09.
"""

import base64
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QPixmap, QImage

from core.procurement.challenge_handler import (
    ChallengeType,
    ChallengeState,
    ChallengeContext,
    ChallengeResult,
    IChallengeHandler,
)


class UniversalChallengeDialog(QDialog):
    """
    User-facing modal dialog for interactive security challenge resolution (CAPTCHA / Turnstile / OTP).
    Zero automated solving; deterministic human-in-the-loop solver interface.
    """

    def __init__(self, context: ChallengeContext, parent=None):
        super().__init__(parent)
        self.context = context
        self._result_state = ChallengeState.CANCELLED
        self._solution: Optional[str] = None
        self.setWindowTitle(f"Security Challenge — {self.context.vendor_id}")
        self.resize(480, 360)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        type_title = self.context.challenge_type.value.replace("_", " ").title()
        title_lbl = QLabel(f"Human Verification Required: {type_title}")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f59e0b;")
        layout.addWidget(title_lbl)

        # Prompt
        desc_lbl = QLabel(self.context.prompt_message or "Please complete the security challenge to proceed with procurement.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 6px;")
        layout.addWidget(desc_lbl)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        # Image CAPTCHA Display (if available)
        self.image_lbl = QLabel()
        self.image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_lbl.setStyleSheet("background-color: #0f172a; padding: 10px; border-radius: 6px;")
        pixmap = self._load_pixmap()
        if pixmap and not pixmap.isNull():
            self.image_lbl.setPixmap(pixmap)
            card_layout.addWidget(self.image_lbl)
        elif self.context.challenge_type == ChallengeType.IMAGE_CAPTCHA:
            self.image_lbl.setText("[CAPTCHA Image Display]")
            card_layout.addWidget(self.image_lbl)

        # Input field (for image captcha / text captcha / OTP)
        self.input_field = None
        if self.context.challenge_type in (
            ChallengeType.IMAGE_CAPTCHA,
            ChallengeType.TEXT_CAPTCHA,
            ChallengeType.OTP,
            ChallengeType.CAPTCHA,
        ):
            input_label = "Enter CAPTCHA Answer:" if self.context.challenge_type != ChallengeType.OTP else "Enter OTP Code:"
            card_layout.addWidget(QLabel(input_label))
            self.input_field = QLineEdit()
            self.input_field.setPlaceholderText("Type answer here...")
            card_layout.addWidget(self.input_field)
            self.input_field.returnPressed.connect(self._on_solve)
        else:
            # Interactive browser instructions
            browser_info = QLabel(
                "A visible browser window has been opened for you.\n"
                "Please complete the challenge in that window, then click 'I Have Completed the Challenge' below."
            )
            browser_info.setWordWrap(True)
            browser_info.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 500;")
            card_layout.addWidget(browser_info)

        layout.addWidget(card)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)

        solve_text = "Submit Answer" if self.input_field else "I Have Completed the Challenge"
        solve_btn = QPushButton(solve_text)
        solve_btn.setObjectName("primaryBtn")
        solve_btn.clicked.connect(self._on_solve)
        btn_layout.addWidget(solve_btn)

        layout.addLayout(btn_layout)

    def _load_pixmap(self) -> Optional[QPixmap]:
        if self.context.image_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(self.context.image_bytes)
            return pixmap
        if self.context.image_base64:
            b64 = self.context.image_base64
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            try:
                raw_bytes = base64.b64decode(b64)
                pixmap = QPixmap()
                pixmap.loadFromData(raw_bytes)
                return pixmap
            except Exception:
                pass
        return None

    def _on_solve(self):
        if self.input_field:
            ans = self.input_field.text().strip()
            if not ans:
                QMessageBox.warning(self, "Input Required", "Please enter the challenge answer before submitting.")
                return
            self._solution = ans

        self._result_state = ChallengeState.SOLVED
        self.accept()

    def _on_cancel(self):
        self._result_state = ChallengeState.CANCELLED
        self.reject()

    def get_result(self) -> ChallengeResult:
        return ChallengeResult(
            vendor_id=self.context.vendor_id,
            challenge_type=self.context.challenge_type,
            state=self._result_state,
            solution=self._solution,
            message="Challenge resolved by user." if self._result_state == ChallengeState.SOLVED else "Challenge cancelled by user.",
        )


class QtChallengeHandler(IChallengeHandler):
    """
    Qt GUI implementation of IChallengeHandler presenting UniversalChallengeDialog.
    """

    def __init__(self, parent_widget=None):
        self.parent = parent_widget

    def handle_challenge(self, context: ChallengeContext) -> ChallengeResult:
        dialog = UniversalChallengeDialog(context, parent=self.parent)
        dialog.exec()
        return dialog.get_result()
