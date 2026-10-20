"""
Omnix UI - Multi-Vendor Settings Dialog
Governing GAP: GAP-11.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QTabWidget, QWidget,
    QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt
from settings_manager import settings
from core.models import VendorSettings
from core.procurement.registry import VendorRegistry, default_registry


from ui.dark_frame import apply_dark_window_frame


class SettingsDialog(QDialog):
    """
    Multi-Vendor configuration dialog supporting independent credentials,
    enable/disable toggles, timeouts, and browser mode per vendor.
    Governing GAP: GAP-11.
    """

    def __init__(
        self,
        parent=None,
        registry: Optional[VendorRegistry] = None,
        show_reference_data: bool = False,
        initial_tab: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings — Multi-Vendor Procurement & Accounts")
        self.resize(540, 440)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.registry = registry or default_registry
        self._vendor_widgets = {}
        self.show_reference_data = show_reference_data
        self._init_ui()

        if initial_tab:
            target = initial_tab.strip().lower()
            if target == "general":
                for idx in range(self.tabs.count()):
                    if self.tabs.tabText(idx).strip().lower() == "general":
                        self.tabs.setCurrentIndex(idx)
                        break
            elif target in ("plugins", "vendors", "vendor"):
                self.tabs.setCurrentIndex(0)
            elif target in ("reference", "reference_data"):
                for idx in range(self.tabs.count()):
                    if "reference" in self.tabs.tabText(idx).strip().lower():
                        self.tabs.setCurrentIndex(idx)
                        break

        apply_dark_window_frame(self)

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)

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

        # Dynamic Vendor Tabs
        registered_vendors = self.registry.list_vendors()
        if registered_vendors:
            for vid in registered_vendors:
                reg_meta = self.registry.get_registration(vid)
                disp_name = reg_meta.display_name or vid.replace("vendor_", "").title()
                domain_info = f" ({', '.join(reg_meta.domains)})" if reg_meta.domains else ""
                desc = reg_meta.description or f"{disp_name} distributor credentials and automation."
                self.tabs.addTab(
                    self._create_vendor_tab(vid, f"{disp_name}{domain_info}", desc),
                    disp_name,
                )
        else:
            # Empty state tab when zero vendor plugins are installed
            self.tabs.addTab(self._create_empty_vendor_tab(), "Vendors")

        # General Settings Tab
        self.tabs.addTab(self._create_general_tab(), "General")

        # Optional Reference Data Tab
        if self.show_reference_data:
            try:
                from ui.widgets.reference_data_widget import ReferenceDataWidget
                from core.inventory.repository import SqliteInventoryRepository, resolve_database_path
                db_path = resolve_database_path()
                repo = SqliteInventoryRepository(db_path)
                self.ref_widget = ReferenceDataWidget(repository=repo, parent=self)
                self.tabs.addTab(self.ref_widget, "🗂️ Reference Data")
            except Exception:
                pass

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

    def _create_empty_vendor_tab(self) -> QWidget:
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(24, 32, 24, 32)
        v_layout.setSpacing(14)
        v_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 24, 20, 24)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("🔌")
        icon_lbl.setStyleSheet("font-size: 32px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel("No Vendor Plugins Installed")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #e2e8f0;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        msg_lbl = QLabel(
            "No vendor plugins are installed. Vendor procurement features will remain unavailable until plugins are installed."
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        card_layout.addWidget(msg_lbl)

        v_layout.addWidget(card)
        v_layout.addStretch()
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

        # Stock Policy Master & Subordinate Checkboxes (Phase B)
        self.stock_policy_enabled_chk = QCheckBox("Enable stock-policy features")
        self.stock_policy_enabled_chk.setStyleSheet("font-weight: bold; color: #38bdf8;")
        self.stock_policy_enabled_chk.setChecked(settings.get("stock_policy_enabled", True))
        card_layout.addWidget(self.stock_policy_enabled_chk)

        sub_layout = QVBoxLayout()
        sub_layout.setContentsMargins(20, 0, 0, 0)
        sub_layout.setSpacing(6)

        self.stock_policy_validation_chk = QCheckBox("Enable stock-policy validation / shortage checking")
        self.stock_policy_validation_chk.setChecked(settings.get("stock_policy_validation_enabled", True))
        sub_layout.addWidget(self.stock_policy_validation_chk)

        self.stock_policy_show_columns_chk = QCheckBox("Show Min Stock and Target Stock columns in Assembly View")
        self.stock_policy_show_columns_chk.setChecked(settings.get("stock_policy_show_columns", True))
        sub_layout.addWidget(self.stock_policy_show_columns_chk)

        card_layout.addLayout(sub_layout)

        def _on_stock_policy_toggled(checked: bool):
            self.stock_policy_validation_chk.setEnabled(checked)
            self.stock_policy_show_columns_chk.setEnabled(checked)

        self.stock_policy_enabled_chk.toggled.connect(_on_stock_policy_toggled)
        _on_stock_policy_toggled(self.stock_policy_enabled_chk.isChecked())

        # Match Products Display Checkbox
        self.match_products_chk = QCheckBox("Show Matched Products in Assembly View")
        self.match_products_chk.setChecked(settings.get("match_products_enabled", True))
        card_layout.addWidget(self.match_products_chk)

        # Hidden/preserved spinboxes for backward compatibility
        self.min_stock_spin = QSpinBox()
        self.min_stock_spin.setRange(0, 100000)
        self.min_stock_spin.setValue(int(settings.get("default_min_stock", 0)))
        self.min_stock_spin.hide()

        self.target_stock_spin = QSpinBox()
        self.target_stock_spin.setRange(0, 100000)
        self.target_stock_spin.setValue(int(settings.get("default_target_stock", 0)))
        self.target_stock_spin.hide()

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

            # Update registry in memory if initialized
            if self.registry.has_vendor(vendor_id):
                self.registry.set_vendor_enabled(vendor_id, cfg.enabled)

        # Save general settings
        settings.set("auto_check_startup_shortage", self.startup_chk.isChecked())
        settings.set("stock_policy_enabled", self.stock_policy_enabled_chk.isChecked())
        settings.set("stock_policy_validation_enabled", self.stock_policy_validation_chk.isChecked())
        settings.set("stock_policy_show_columns", self.stock_policy_show_columns_chk.isChecked())
        settings.set("default_min_stock", self.min_stock_spin.value())
        settings.set("default_target_stock", self.target_stock_spin.value())
        settings.set("match_products_enabled", self.match_products_chk.isChecked())

        self.accept()
