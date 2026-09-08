from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from settings_manager import settings


class SettingsDialog(QDialog):
    """Configuration dialog for Lion Electronic credentials and automation preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Lion Electronic Integration")
        self.resize(460, 380)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title / Description
        title_lbl = QLabel("Lion Electronic Account Settings")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Enter your login credentials for lionelectronic.ir to enable automated ordering of inventory shortages and project BOM components.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 6px;")
        layout.addWidget(desc_lbl)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        # Username / Mobile input
        card_layout.addWidget(QLabel("Username / Mobile / Email:"))
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("e.g. 0912xxxxxxx or your_email@example.com")
        self.user_input.setText(settings.get("lion_username", ""))
        card_layout.addWidget(self.user_input)

        # Password input
        card_layout.addWidget(QLabel("Password:"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Enter your account password")
        self.pwd_input.setText(settings.get("lion_password", ""))
        card_layout.addWidget(self.pwd_input)

        # Checkboxes
        self.show_browser_chk = QCheckBox("Show visible browser during ordering (unchecked = fast background mode)")
        self.show_browser_chk.setChecked(settings.get("show_browser", False))
        card_layout.addWidget(self.show_browser_chk)

        self.startup_chk = QCheckBox("Automatically check inventory shortages on startup")
        self.startup_chk.setChecked(settings.get("auto_check_startup_shortage", True))
        card_layout.addWidget(self.startup_chk)

        layout.addWidget(card)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _save_and_close(self):
        settings.set("lion_username", self.user_input.text().strip())
        settings.set("lion_password", self.pwd_input.text().strip())
        settings.set("show_browser", self.show_browser_chk.isChecked())
        settings.set("auto_check_startup_shortage", self.startup_chk.isChecked())
        self.accept()
