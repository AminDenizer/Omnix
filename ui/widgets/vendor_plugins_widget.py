"""
Omnix UI — Dedicated Vendor Plugins View (Milestone 3 Integration)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 10, 27.2 (Phase 17) & Section 6
- Separation of Executable Plugins from Supplier Directory
- Secure installation, Gate B/C trust confirmation, version switching, activation, and uninstall.
"""

from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QRectF
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QToolButton,
)

from core.procurement.registry import VendorRegistry, default_registry
from core.plugins.plugin_store import PluginStore
from core.plugins.plugin_installer import PluginInstaller, PluginInstallationResult
from core.plugins.plugin_lifecycle_manager import (
    PluginLifecycleManager,
    LifecycleStatus,
    LifecycleResult,
    get_lifecycle_manager,
)
from core.plugins.package_inspector import PackageInspector
from ui.widgets.number_stepper import NumberStepperWidget
from core.plugins.manifest_validator import SemanticVersion
from settings_manager import settings
from core.models import VendorSettings
from ui.dialogs.plugin_trust_dialog import PluginTrustDialog
from ui.dialogs.confirmation_dialog import FocusPaddedPushButton, create_confirmation_dialog
from ui.dark_frame import apply_dark_window_frame


class PluginUninstallDialog(QDialog):
    """
    Modal confirmation dialog for destructive plugin uninstallation.
    Supports single version removal vs entire vendor family purge.
    """

    def __init__(
        self,
        vendor_id: str,
        display_name: str,
        active_version: str,
        installed_versions: List[str],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.vendor_id = vendor_id
        self.display_name = display_name
        self.active_version = active_version
        self.installed_versions = installed_versions
        self.uninstall_all = False

        self.setWindowTitle(f"Uninstall Plugin — {display_name}")
        self.setModal(True)
        self.setMinimumWidth(460)
        apply_dark_window_frame(self)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b101b;
                color: #f8fafc;
            }
            QLabel {
                color: #cbd5e1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(10)

        warn_icon = QLabel("🗑️")
        warn_icon.setStyleSheet("font-size: 24px;")
        hdr_row.addWidget(warn_icon)

        title_lbl = QLabel(f"Uninstall {self.display_name}?")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f87171;")
        hdr_row.addWidget(title_lbl, 1)
        layout.addLayout(hdr_row)

        desc_lbl = QLabel(
            "This action is permanent. Deletes installed package files from disk and removes "
            "adapter routing mappings from the procurement registry."
        )
        desc_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Multi-version selection if more than 1 version installed
        if len(self.installed_versions) > 1:
            opts_frame = QFrame()
            opts_frame.setStyleSheet("""
                QFrame {
                    background-color: #0f172a;
                    border: 1px solid #1e293b;
                    border-radius: 6px;
                    padding: 10px 14px;
                }
            """)
            o_layout = QVBoxLayout(opts_frame)
            o_layout.setSpacing(8)

            choose_lbl = QLabel("Select uninstallation scope:")
            choose_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #e2e8f0;")
            o_layout.addWidget(choose_lbl)

            self.opt_single = QRadioButton(f"Uninstall only version v{self.active_version}")
            self.opt_single.setChecked(True)
            self.opt_single.setStyleSheet("color: #e2e8f0; font-size: 12px;")
            o_layout.addWidget(self.opt_single)

            self.opt_all = QRadioButton(
                f"Uninstall entire '{self.vendor_id}' family ({len(self.installed_versions)} versions)"
            )
            self.opt_all.setStyleSheet("color: #f87171; font-size: 12px; font-weight: bold;")
            o_layout.addWidget(self.opt_all)

            layout.addWidget(opts_frame)
        else:
            info_lbl = QLabel(
                f"Installed Version: <span style='color: #38bdf8; font-family: Consolas;'>v{self.active_version}</span>"
            )
            info_lbl.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(info_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.cancel_btn = FocusPaddedPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.uninstall_btn = FocusPaddedPushButton("Uninstall")
        self.uninstall_btn.setObjectName("dangerBtn")
        self.uninstall_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                border: 1px solid #ef4444;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
                border-color: #f87171;
            }
        """)
        self.uninstall_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.uninstall_btn)

        layout.addLayout(btn_row)

        self.cancel_btn.setDefault(True)
        self.cancel_btn.setFocus()

    def _on_confirm(self):
        if len(self.installed_versions) > 1 and hasattr(self, "opt_all"):
            self.uninstall_all = self.opt_all.isChecked()
        else:
            self.uninstall_all = False
        self.accept()


class VendorPluginsWidget(QWidget):
    """
    Dedicated view for inspecting, installing, activating, configuring,
    and managing the lifecycle of executable vendor plugins.
    """

    def __init__(
        self,
        registry: Optional[VendorRegistry] = None,
        lifecycle_mgr: Optional[PluginLifecycleManager] = None,
        installer: Optional[PluginInstaller] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.registry = registry or default_registry
        self.lifecycle_mgr = lifecycle_mgr or get_lifecycle_manager(registry=self.registry)
        self.installer = installer or PluginInstaller(store=self.lifecycle_mgr.store)
        self.store = self.lifecycle_mgr.store
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Header Info Banner & Action Controls
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(12)

        title_lbl = QLabel("Vendor Plugins")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(self.summary_lbl)

        hdr_layout.addStretch()

        # Install Plugin Button
        self.install_btn = QPushButton("Install Plugin (.xpl)...")
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
                border-color: #38bdf8;
            }
        """)
        self.install_btn.clicked.connect(self._on_install_plugin_clicked)
        hdr_layout.addWidget(self.install_btn)

        layout.addLayout(hdr_layout)

        desc_lbl = QLabel(
            "Manage executable distributor adapters providing automated product search, "
            "pricing discovery, and Mode A order staging. Omnix starts empty-by-default."
        )
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Scroll area for plugins list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background-color: transparent;")

        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 10, 0, 10)
        self.content_layout.setSpacing(10)

        self.scroll_area.setWidget(self.content_container)
        layout.addWidget(self.scroll_area, 1)

        self.refresh()

    @staticmethod
    def _clear_layout(layout):
        """Recursively removes and deletes all child widgets and sublayouts."""
        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                VendorPluginsWidget._clear_layout(item.layout())

    def refresh_plugins(self):
        """Public alias for refreshing plugin list."""
        self.refresh()

    def refresh(self):
        """Re-render plugin list combining persistent store records and runtime registry."""
        self._clear_layout(self.content_layout)

        # Collect vendor IDs from persistent store and runtime registry
        store_index = self.store.load_index()
        registry_vendors = (
            self.registry.list_vendors()
            if hasattr(self.registry, "list_vendors")
            else []
        )
        all_vendor_ids = sorted(list(set(list(store_index.keys()) + registry_vendors)))

        self.summary_lbl.setText(f"{len(all_vendor_ids)} plugin(s) installed")

        if not all_vendor_ids:
            # Centered Empty state card
            center_row = QHBoxLayout()
            center_row.addStretch()

            card = QFrame()
            card.setObjectName("cardFrame")
            card.setMaximumWidth(680)
            card.setStyleSheet("""
                QFrame#cardFrame {
                    background-color: #0f172a;
                    border: 1px solid #1e293b;
                    border-radius: 8px;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(36, 32, 36, 32)
            c_layout.setSpacing(14)
            c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_lbl = QLabel("🔌")
            icon_lbl.setStyleSheet("font-size: 38px; background-color: transparent;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_layout.addWidget(icon_lbl)

            empty_title = QLabel("No Vendor Plugins Installed")
            empty_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9; background-color: transparent;")
            empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_layout.addWidget(empty_title)

            empty_desc = QLabel(
                "A clean installation of Omnix contains zero pre-installed vendor plugins.\n"
                "Install a signed distributor package (.xpl) using the button above to enable automated procurement."
            )
            empty_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5; background-color: transparent;")
            empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_desc.setWordWrap(True)
            c_layout.addWidget(empty_desc)

            quick_install_btn = QPushButton("Install Plugin (.xpl)...")
            quick_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            quick_install_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: #ffffff;
                    border: 1px solid #0284c7;
                    border-radius: 4px;
                    padding: 6px 18px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                    border-color: #38bdf8;
                }
            """)
            quick_install_btn.clicked.connect(self._on_install_plugin_clicked)
            c_layout.addWidget(quick_install_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            center_row.addWidget(card)
            center_row.addStretch()

            self.content_layout.addSpacing(20)
            self.content_layout.addLayout(center_row)
            self.content_layout.addStretch(1)
            return

        for vid in all_vendor_ids:
            status_info = self.lifecycle_mgr.get_plugin_status(vid)
            p_rec = store_index.get(vid)
            reg_entry = (
                self.registry.get_registration(vid)
                if hasattr(self.registry, "has_vendor")
                and self.registry.has_vendor(vid)
                and hasattr(self.registry, "get_registration")
                else None
            )

            # Metadata resolution
            disp_name = (
                getattr(reg_entry, "display_name", None)
                or (getattr(p_rec, "display_name", None) if p_rec else None)
                or vid.replace("vendor_", "").title()
            )
            desc = (
                getattr(reg_entry, "description", None)
                or f"{disp_name} automated procurement plugin."
            )
            installed_versions = status_info.get("installed_versions", [])
            active_version = (
                status_info.get("active_version_registry")
                or status_info.get("active_version_store")
                or (installed_versions[0] if installed_versions else "1.0.0")
            )
            is_enabled = bool(
                status_info.get("is_enabled_in_registry")
                or status_info.get("enabled_store")
            )
            domains = status_info.get("routed_domains") or (
                getattr(reg_entry, "domains", []) if reg_entry else []
            )
            domain_str = ", ".join(domains) if domains else "None declared"

            card = QFrame()
            card.setObjectName("pluginCard")
            card.setStyleSheet("""
                QFrame#pluginCard {
                    background-color: #0b101b;
                    border: 1px solid #1e293b;
                    border-radius: 6px;
                    padding: 12px 16px;
                }
                QFrame#pluginCard:hover {
                    border-color: #334155;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(6)

            top_row = QHBoxLayout()
            top_row.setSpacing(8)

            name_lbl = QLabel(disp_name)
            name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f1f5f9; background-color: transparent;")
            top_row.addWidget(name_lbl)

            # Version selection dropdown (or single version pill)
            if len(installed_versions) > 1:
                ver_combo = QComboBox()
                ver_combo.setStyleSheet("""
                    QComboBox {
                        background-color: #1e293b;
                        color: #38bdf8;
                        border: 1px solid #334155;
                        border-radius: 4px;
                        padding: 1px 6px;
                        font-size: 10px;
                        font-family: 'Consolas', monospace;
                        font-weight: bold;
                    }
                """)
                ver_combo.blockSignals(True)
                for v in installed_versions:
                    ver_combo.addItem(f"v{v}", v)
                cur_idx = ver_combo.findData(active_version)
                if cur_idx >= 0:
                    ver_combo.setCurrentIndex(cur_idx)
                ver_combo.blockSignals(False)
                ver_combo.currentIndexChanged.connect(
                    lambda idx, c=ver_combo, v=vid: self._on_version_changed(v, c)
                )
                top_row.addWidget(ver_combo)
            else:
                ver_lbl = QLabel(f"v{active_version}")
                ver_lbl.setStyleSheet("""
                    background-color: rgba(56, 189, 248, 0.12);
                    color: #38bdf8;
                    border-radius: 4px;
                    padding: 1px 6px;
                    font-size: 10px;
                    font-family: 'Consolas', monospace;
                    font-weight: bold;
                """)
                top_row.addWidget(ver_lbl)

            # Status Badge
            status_badge = self._create_status_badge(status_info, is_enabled)
            top_row.addWidget(status_badge)

            top_row.addStretch()

            # Active Toggle Checkbox
            active_chk = QCheckBox("Active")
            active_chk.setStyleSheet("font-weight: bold; color: #38bdf8; background-color: transparent;")
            active_chk.blockSignals(True)
            active_chk.setChecked(is_enabled)
            active_chk.blockSignals(False)
            active_chk.toggled.connect(
                lambda chk, v=vid, cur_v=active_version: self._on_vendor_toggled(v, cur_v, chk)
            )
            top_row.addWidget(active_chk)

            # Configure Button
            config_btn = QPushButton("Configure...")
            config_btn.setObjectName("secondaryBtn")
            config_btn.setFixedHeight(26)
            config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            config_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #e2e8f0;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 2px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #334155;
                    border-color: #38bdf8;
                    color: #38bdf8;
                }
            """)
            config_btn.clicked.connect(lambda _, v=vid: self._configure_vendor(v))
            top_row.addWidget(config_btn)

            # Uninstall Button
            uninstall_btn = QPushButton("Uninstall...")
            uninstall_btn.setFixedHeight(26)
            uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            uninstall_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 2px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    border-color: #ef4444;
                    color: #ffffff;
                }
            """)
            uninstall_btn.clicked.connect(
                lambda _, v=vid, dn=disp_name, av=active_version, ivs=installed_versions: self._on_uninstall_clicked(
                    v, dn, av, ivs
                )
            )
            top_row.addWidget(uninstall_btn)

            card_layout.addLayout(top_row)

            # Metadata sub-row
            meta_lbl = QLabel(
                f"ID: <span style='color: #94a3b8; font-family: Consolas;'>{vid}</span> &nbsp;|&nbsp; "
                f"Domains: <span style='color: #94a3b8;'>{domain_str}</span>"
            )
            meta_lbl.setTextFormat(Qt.TextFormat.RichText)
            meta_lbl.setStyleSheet("font-size: 11px; color: #64748b; background-color: transparent;")
            card_layout.addWidget(meta_lbl)

            desc_w = QLabel(desc)
            desc_w.setStyleSheet("font-size: 11px; color: #94a3b8; background-color: transparent;")
            desc_w.setWordWrap(True)
            card_layout.addWidget(desc_w)

            self.content_layout.addWidget(card)

        self.content_layout.addStretch(1)

    def _create_status_badge(self, status_info: Dict[str, Any], is_enabled: bool) -> QLabel:
        badge = QLabel()
        ver_statuses = status_info.get("version_statuses", {})
        active_ver = status_info.get("active_version_store") or status_info.get("active_version_registry")
        active_ver_status = ver_statuses.get(active_ver, "INSTALLED") if active_ver else "INSTALLED"

        if active_ver_status == "TAMPERED":
            badge.setText("TAMPERED")
            badge.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid #ef4444;
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 9px;
                font-weight: bold;
            """)
        elif active_ver_status == "CORRUPTED":
            badge.setText("CORRUPTED")
            badge.setStyleSheet("""
                background-color: rgba(245, 158, 11, 0.15);
                color: #fbbf24;
                border: 1px solid #f59e0b;
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 9px;
                font-weight: bold;
            """)
        elif is_enabled and status_info.get("is_registered_in_registry"):
            badge.setText("ACTIVE")
            badge.setStyleSheet("""
                background-color: rgba(34, 197, 94, 0.15);
                color: #4ade80;
                border: 1px solid #22c55e;
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 9px;
                font-weight: bold;
            """)
        else:
            badge.setText("DISABLED")
            badge.setStyleSheet("""
                background-color: rgba(100, 116, 139, 0.15);
                color: #94a3b8;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 9px;
                font-weight: bold;
            """)
        return badge

    # -----------------------------------------------------------------------
    # Installation & Trust Modal Workflow
    # -----------------------------------------------------------------------

    def _on_install_plugin_clicked(self):
        """Handle 'Install Plugin (.xpl)...' button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Vendor Plugin Package",
            "",
            "Omnix Plugin Packages (*.xpl);;ZIP Archives (*.zip);;All Files (*)",
        )
        if not file_path:
            return

        archive_path = Path(file_path)

        # Gate A: Package Inspection
        try:
            insp_res = PackageInspector.inspect_package(archive_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Package Inspection Error",
                f"Failed to inspect package '{archive_path.name}':\n\n{exc}",
            )
            return

        if not insp_res.is_valid:
            err_msg = (
                "\n".join([str(e.message if hasattr(e, "message") else e) for e in insp_res.errors])
                if insp_res.errors
                else "Unknown package format error"
            )
            QMessageBox.critical(
                self,
                "Package Inspection Failed",
                f"The package '{archive_path.name}' failed structural validation:\n\n{err_msg}",
            )
            return

        # Gate B: Cryptographic Trust Engine Verification
        try:
            trust_res = self.installer.trust_engine.verify_archive(archive_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Trust Verification Error",
                f"Error during cryptographic signature check for '{archive_path.name}':\n\n{exc}",
            )
            return

        # Show Trust Confirmation Modal
        trust_dlg = PluginTrustDialog(inspection=insp_res, trust=trust_res, parent=self)
        if not trust_dlg.exec():
            # User canceled or rejected installation
            return

        # Execute Transactional Installation
        install_res = self.installer.install_package(archive_path)
        if not install_res.success:
            err_details = (
                "\n".join([str(e.message if hasattr(e, "message") else e) for e in install_res.errors])
                if install_res.errors
                else (install_res.error_message or "Installation failed")
            )
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Failed to install '{archive_path.name}':\n\n{err_details}",
            )
            self.refresh()
            return

        # Dynamic Activation & Registration (Gate E)
        activate_res = self.lifecycle_mgr.activate_plugin(
            install_res.vendor_id,
            install_res.version,
        )
        if not activate_res.success:
            QMessageBox.warning(
                self,
                "Activation Failed",
                f"Plugin '{install_res.vendor_id}' v{install_res.version} installed successfully, "
                f"but activation failed:\n\n{activate_res.error_message}\n\n"
                "The plugin remains installed in a disabled state.",
            )
        else:
            QMessageBox.information(
                self,
                "Plugin Installed",
                f"Plugin '{install_res.vendor_id}' v{install_res.version} was installed and activated successfully.",
            )

        self.refresh()

    # -----------------------------------------------------------------------
    # Lifecycle & Version Management Callbacks
    # -----------------------------------------------------------------------

    def _on_vendor_toggled(self, vendor_id: str, version: str, enabled: bool):
        """Handle Active toggle on a plugin card."""
        if enabled:
            res = self.lifecycle_mgr.activate_plugin(vendor_id, version)
            if not res.success:
                QMessageBox.warning(
                    self,
                    "Activation Failed",
                    f"Could not activate plugin '{vendor_id}':\n\n{res.error_message}",
                )
                self.refresh()
                return
        else:
            res = self.lifecycle_mgr.deactivate_plugin(vendor_id)
            if not res.success:
                QMessageBox.warning(
                    self,
                    "Deactivation Failed",
                    f"Could not deactivate plugin '{vendor_id}':\n\n{res.error_message}",
                )
                self.refresh()
                return

        # Update legacy settings if present
        v_cfg = settings.get_vendor_settings(vendor_id)
        if v_cfg:
            v_cfg.enabled = enabled
            settings.set_vendor_settings(vendor_id, v_cfg)

        self.refresh()

    def _on_version_changed(self, vendor_id: str, combo: QComboBox):
        """Handle version dropdown selection change."""
        new_version = combo.currentData()
        if not new_version:
            return

        res = self.lifecycle_mgr.switch_active_version(vendor_id, str(new_version))
        if not res.success:
            QMessageBox.critical(
                self,
                "Version Switch Failed",
                f"Could not switch '{vendor_id}' to version {new_version}:\n\n{res.error_message}",
            )
        self.refresh()

    def _on_uninstall_clicked(
        self,
        vendor_id: str,
        display_name: str,
        active_version: str,
        installed_versions: List[str],
    ):
        """Handle Uninstall button click with confirmation dialog."""
        dlg = PluginUninstallDialog(
            vendor_id=vendor_id,
            display_name=display_name,
            active_version=active_version,
            installed_versions=installed_versions,
            parent=self,
        )
        if not dlg.exec():
            return

        target_ver = None if dlg.uninstall_all else active_version
        res = self.lifecycle_mgr.uninstall_plugin(vendor_id, version=target_ver)
        if not res.success:
            QMessageBox.critical(
                self,
                "Uninstallation Failed",
                f"Failed to uninstall plugin '{vendor_id}':\n\n{res.error_message}",
            )
        else:
            scope_str = "completely" if target_ver is None else f"version v{target_ver}"
            QMessageBox.information(
                self,
                "Plugin Uninstalled",
                f"Uninstalled {scope_str} of '{display_name}'.",
            )
        self.refresh()

    def _configure_vendor(self, vendor_id: str):
        """Open schema-driven configuration dialog for a vendor plugin."""
        dlg = PluginConfigDialog(vendor_id=vendor_id, registry=self.registry, parent=self)
        if dlg.exec():
            self.refresh()


class PluginConfigDialog(QDialog):
    """
    Schema-driven configuration dialog for a vendor plugin (DOC-OMNIX-PLAN-FINAL-004 Section 9).
    Renders fields declared by plugin manifest or defaults to standard vendor credentials.
    """

    def __init__(self, vendor_id: str, registry: Optional[VendorRegistry] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.vendor_id = vendor_id
        self.registry = registry or default_registry
        self.reg_entry = self.registry.get_registration(vendor_id) if hasattr(self.registry, "get_registration") else None
        self.v_cfg = settings.get_vendor_settings(vendor_id) or VendorSettings(vendor_id=vendor_id)
        self.field_widgets = {}
        self._init_ui()

    def _init_ui(self):
        disp_name = getattr(self.reg_entry, "display_name", None) or self.vendor_id.replace("vendor_", "").title()
        self.setWindowTitle(f"Configure {disp_name} Plugin")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_lbl = QLabel(f"{disp_name} Plugin Configuration")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        desc = getattr(self.reg_entry, "description", "") or f"Configure connection and authentication parameters for {disp_name}."
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        form_frame = QFrame()
        form_frame.setObjectName("pluginConfigFormFrame")
        form_frame.setStyleSheet("QFrame#pluginConfigFormFrame { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; }")
        form_layout = QFormLayout(form_frame)
        form_layout.setSpacing(10)

        manifest = getattr(self.reg_entry, "manifest", None) or {}
        config_schema = manifest.get("config_schema", {}) if isinstance(manifest, dict) else {}
        fields = config_schema.get("fields", []) if isinstance(config_schema, dict) else []

        if not fields:
            # Default schema for in-tree/unmanifested vendor adapters
            fields = [
                {"key": "username", "label": "Username / Mobile", "type": "string", "required": False, "is_secret": False, "description": "Account login username or phone"},
                {"key": "password", "label": "Account Password", "type": "password", "required": False, "is_secret": True, "description": "Account password (masked)"},
                {"key": "timeout_seconds", "label": "Timeout (seconds)", "type": "integer", "default": 10, "description": "Network page timeout"},
            ]

        for f_def in fields:
            key = f_def.get("key", "")
            # Global browser execution settings (e.g. headless) are managed via Main Settings
            if key == "headless":
                continue
            label = f_def.get("label", key)
            f_type = f_def.get("type", "string")
            is_secret = f_def.get("is_secret", False) or f_type == "password"
            default_val = f_def.get("default")

            lbl_widget = QLabel(label + ":")
            lbl_widget.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 500;")

            if f_type in ("string", "password"):
                init_val = getattr(self.v_cfg, key, None)
                if init_val is None:
                    init_val = self.v_cfg.extra_options.get(key, default_val or "")
                line_edit = QLineEdit(str(init_val or ""))
                line_edit.setStyleSheet("background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px;")
                if is_secret:
                    line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                    row_box = QHBoxLayout()
                    row_box.setSpacing(6)
                    row_box.addWidget(line_edit, 1)

                    def _create_eye_icon(open_eye=True, color="#94a3b8", size=32):
                        if open_eye:
                            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>'''
                        else:
                            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                                <line x1="1" y1="1" x2="23" y2="23" stroke="{color}" stroke-width="2"/>
                            </svg>'''
                        pm = QPixmap(size, size)
                        pm.fill(QColor(0, 0, 0, 0))
                        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
                        p = QPainter(pm)
                        r.render(p, QRectF(0, 0, float(size), float(size)))
                        p.end()
                        return QIcon(pm)

                    toggle_btn = QPushButton()
                    toggle_btn.setIcon(_create_eye_icon(True, "#94a3b8"))
                    toggle_btn.setFixedWidth(28)
                    toggle_btn.setFixedHeight(26)
                    toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    toggle_btn.setToolTip("Toggle password visibility")
                    toggle_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #1e293b;
                            border: 1px solid #334155;
                            border-radius: 4px;
                        }
                        QPushButton:hover {
                            background-color: #334155;
                            border-color: #38bdf8;
                        }
                    """)

                    def _toggle_reveal(_checked=False, btn=toggle_btn, edit=line_edit):
                        if edit.echoMode() == QLineEdit.EchoMode.Password:
                            edit.setEchoMode(QLineEdit.EchoMode.Normal)
                            btn.setIcon(_create_eye_icon(False, "#38bdf8"))
                            btn.setStyleSheet("""
                                QPushButton {
                                    background-color: #334155;
                                    border: 1px solid #38bdf8;
                                    border-radius: 4px;
                                }
                            """)
                        else:
                            edit.setEchoMode(QLineEdit.EchoMode.Password)
                            btn.setIcon(_create_eye_icon(True, "#94a3b8"))
                            btn.setStyleSheet("""
                                QPushButton {
                                    background-color: #1e293b;
                                    border: 1px solid #334155;
                                    border-radius: 4px;
                                }
                                QPushButton:hover {
                                    background-color: #334155;
                                    border-color: #38bdf8;
                                }
                            """)

                    toggle_btn.clicked.connect(_toggle_reveal)
                    row_box.addWidget(toggle_btn)
                    form_layout.addRow(lbl_widget, row_box)
                    self.field_widgets[key] = (line_edit, f_def)
                else:
                    form_layout.addRow(lbl_widget, line_edit)
                    self.field_widgets[key] = (line_edit, f_def)

            elif f_type == "integer":
                init_val = getattr(self.v_cfg, key, None)
                if init_val is None:
                    init_val = self.v_cfg.extra_options.get(key, default_val or 10)
                try:
                    init_int = int(init_val)
                except (ValueError, TypeError):
                    init_int = 10
                stepper = NumberStepperWidget(value=init_int, min_val=1, max_val=600)
                stepper.setFixedHeight(32)
                form_layout.addRow(lbl_widget, stepper)
                self.field_widgets[key] = (stepper, f_def)

            elif f_type == "boolean":
                init_val = getattr(self.v_cfg, key, None)
                if init_val is None:
                    init_val = self.v_cfg.extra_options.get(key, default_val if default_val is not None else True)
                chk = QCheckBox(f_def.get("description", ""))
                chk.setChecked(bool(init_val))
                chk.setStyleSheet("color: #94a3b8;")
                form_layout.addRow(lbl_widget, chk)
                self.field_widgets[key] = (chk, f_def)

            elif f_type == "select":
                init_val = getattr(self.v_cfg, key, None)
                if init_val is None:
                    init_val = self.v_cfg.extra_options.get(key, default_val or "")
                combo = QComboBox()
                opts = f_def.get("options", [])
                for opt in opts:
                    if isinstance(opt, dict):
                        combo.addItem(opt.get("label", str(opt.get("value"))), opt.get("value"))
                    else:
                        combo.addItem(str(opt), opt)
                idx = combo.findData(init_val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.setStyleSheet("background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 4px; padding: 2px 6px;")
                form_layout.addRow(lbl_widget, combo)
                self.field_widgets[key] = (combo, f_def)

        layout.addWidget(form_frame)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Configuration")
        save_btn.setObjectName("primaryBtn")
        save_btn.setStyleSheet("background-color: #0284c7; color: white; border-radius: 4px; padding: 6px 14px; font-weight: bold;")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _save_settings(self):
        for key, (w, f_def) in self.field_widgets.items():
            f_type = f_def.get("type", "string")
            if f_type in ("string", "password"):
                val = w.text().strip()
            elif f_type == "integer":
                val = w.value()
            elif f_type == "boolean":
                val = w.isChecked()
            elif f_type == "select":
                val = w.currentData()
            else:
                val = w.text() if hasattr(w, "text") else None

            if hasattr(self.v_cfg, key):
                setattr(self.v_cfg, key, val)
            else:
                self.v_cfg.extra_options[key] = val

        settings.set_vendor_settings(self.vendor_id, self.v_cfg)
        settings.save()
        self.accept()
