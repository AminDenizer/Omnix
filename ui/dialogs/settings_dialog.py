"""
Omnix UI - Multi-Vendor Settings Dialog
Governing GAP: GAP-11.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QTabWidget, QWidget,
    QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt
from settings_manager import settings
from core.models import VendorSettings
from core.procurement.registry import default_registry


class SettingsDialog(QDialog):
    """
    Multi-Vendor configuration dialog supporting independent credentials,
    enable/disable toggles, timeouts, and browser mode per vendor.
    Governing GAP: GAP-11.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Multi-Vendor Procurement & Accounts")
        self.resize(540, 440)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._vendor_widgets = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        title_lbl = QLabel("Omnix Platform Settings")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        # Tab Widget
        self.tabs = QTabWidget()

        # 1. Lion Electronic Tab
        self.tabs.addTab(self._create_vendor_tab("vendor_lion", "Lion Electronic (lionelectronic.ir)", "Lion Electronic distributor credentials and automation."), "Lion Electronic")

        # 2. Javan Electronic Tab
        self.tabs.addTab(self._create_vendor_tab("vendor_javan", "Javan Electronic (javanelec.com)", "Javan Electronic distributor credentials and automation."), "Javan Electronic")

        # 3. RoboEq Electronic Tab
        self.tabs.addTab(self._create_vendor_tab("vendor_roboeq", "RoboEq Electronic (roboeq.ir)", "RoboEq marketplace account and automation settings."), "RoboEq Electronic")

        # 4. General Settings Tab
        self.tabs.addTab(self._create_general_tab(), "General")

        layout.addWidget(self.tabs)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _create_vendor_tab(self, vendor_id: str, title: str, description: str) -> QWidget:
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(12, 12, 12, 12)
        v_layout.setSpacing(10)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; margin-bottom: 4px;")
        v_layout.addWidget(desc_lbl)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        # Retrieve current settings
        v_cfg = settings.get_vendor_settings(vendor_id)

        # Enable / Disable Checkbox (GAP-11.1)
        enable_chk = QCheckBox(f"Enable {title.split()[0]} for automated procurement")
        enable_chk.setChecked(v_cfg.enabled)
        enable_chk.setStyleSheet("font-weight: bold; color: #e2e8f0;")
        card_layout.addWidget(enable_chk)

        # Username / Email
        card_layout.addWidget(QLabel("Username / Email / Mobile:"))
        user_input = QLineEdit()
        user_input.setPlaceholderText("Username or registered mobile")
        user_input.setText(v_cfg.username)
        card_layout.addWidget(user_input)

        # Password
        card_layout.addWidget(QLabel("Password:"))
        pwd_input = QLineEdit()
        pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_input.setPlaceholderText("Account password")
        pwd_input.setText(v_cfg.password)
        card_layout.addWidget(pwd_input)

        # Timeout & Headless
        opts_layout = QHBoxLayout()

        opts_layout.addWidget(QLabel("Timeout (s):"))
        timeout_spin = QSpinBox()
        timeout_spin.setRange(2, 120)
        timeout_spin.setValue(int(v_cfg.timeout_seconds))
        opts_layout.addWidget(timeout_spin)

        headless_chk = QCheckBox("Background (Headless) Mode")
        headless_chk.setChecked(v_cfg.headless)
        opts_layout.addWidget(headless_chk)

        card_layout.addLayout(opts_layout)
        v_layout.addWidget(card)
        v_layout.addStretch()

        self._vendor_widgets[vendor_id] = {
            "enabled": enable_chk,
            "username": user_input,
            "password": pwd_input,
            "timeout": timeout_spin,
            "headless": headless_chk,
        }
        return widget

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(12, 12, 12, 12)
        v_layout.setSpacing(10)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        self.startup_chk = QCheckBox("Automatically check inventory shortages on application startup")
        self.startup_chk.setChecked(settings.get("auto_check_startup_shortage", True))
        card_layout.addWidget(self.startup_chk)

        # Stock defaults
        stock_layout = QHBoxLayout()
        stock_layout.addWidget(QLabel("Default Min Stock:"))
        self.min_stock_spin = QSpinBox()
        self.min_stock_spin.setRange(0, 100000)
        self.min_stock_spin.setValue(int(settings.get("default_min_stock", 0)))
        stock_layout.addWidget(self.min_stock_spin)

        stock_layout.addWidget(QLabel("Default Target Stock:"))
        self.target_stock_spin = QSpinBox()
        self.target_stock_spin.setRange(0, 100000)
        self.target_stock_spin.setValue(int(settings.get("default_target_stock", 0)))
        stock_layout.addWidget(self.target_stock_spin)

        card_layout.addLayout(stock_layout)
        v_layout.addWidget(card)
        v_layout.addStretch()

        return widget

    def _save_and_close(self):
        # Save all vendor settings
        for vendor_id, w in self._vendor_widgets.items():
            cfg = VendorSettings(
                vendor_id=vendor_id,
                enabled=w["enabled"].isChecked(),
                username=w["username"].text().strip(),
                password=w["password"].text().strip(),
                timeout_seconds=float(w["timeout"].value()),
                headless=w["headless"].isChecked(),
            )
            settings.set_vendor_settings(vendor_id, cfg)

            # Update default registry in memory if initialized
            if default_registry.has_vendor(vendor_id):
                default_registry.set_vendor_enabled(vendor_id, cfg.enabled)

        # Save general settings
        settings.set("auto_check_startup_shortage", self.startup_chk.isChecked())
        settings.set("default_min_stock", self.min_stock_spin.value())
        settings.set("default_target_stock", self.target_stock_spin.value())

        self.accept()
