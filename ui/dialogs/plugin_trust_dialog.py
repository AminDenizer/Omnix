"""
Omnix UI — Plugin Trust & Security Confirmation Modal (Milestone 3)
Governing Specifications:
- OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 27.2 (Phase 17) & Section 6
- Gate B/C Publisher Trust and Capability Review

Presents verified cryptographic signature evidence, publisher identity, declared
storefront domains, and requested capabilities to the user prior to extraction,
installation, or activation. Enforces fail-closed trust boundaries.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
)

from core.plugins.package_inspector import PackageInspectionResult
from core.plugins.trust_engine import TrustVerificationResult, TrustStatus
from ui.dark_frame import apply_dark_window_frame
from ui.dialogs.confirmation_dialog import FocusPaddedPushButton


class PluginTrustDialog(QDialog):
    """
    Modal confirmation dialog presenting cryptographic trust and capability review
    for a vendor plugin package before installation and activation.
    """

    def __init__(
        self,
        inspection: PackageInspectionResult,
        trust: TrustVerificationResult,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.inspection = inspection
        self.trust = trust

        disp_name = (
            self.inspection.display_name
            or self.inspection.plugin_id
            or self.inspection.vendor_id
            or "Vendor Plugin"
        )
        self.setWindowTitle(f"Trust & Install — {disp_name}")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMaximumWidth(700)
        self.resize(580, 520)

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

        # 1. Header Banner
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(10)

        icon_lbl = QLabel("🛡️")
        icon_lbl.setStyleSheet("font-size: 26px; background-color: transparent;")
        hdr_row.addWidget(icon_lbl)

        hdr_text_box = QVBoxLayout()
        hdr_text_box.setSpacing(2)

        title_lbl = QLabel("Review & Authorize Plugin Package")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        hdr_text_box.addWidget(title_lbl)

        sub_lbl = QLabel("Verify package authenticity, publisher trust tier, and declared capabilities.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_text_box.addWidget(sub_lbl)

        hdr_row.addLayout(hdr_text_box, 1)

        # Trust Tier Badge
        tier_badge = self._build_trust_badge()
        hdr_row.addWidget(tier_badge)

        layout.addLayout(hdr_row)

        # 2. Package Identity Card
        id_frame = QFrame()
        id_frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 12px 14px;
            }
        """)
        id_layout = QVBoxLayout(id_frame)
        id_layout.setContentsMargins(12, 10, 12, 10)
        id_layout.setSpacing(6)

        disp_title = (
            self.inspection.display_name
            or self.inspection.plugin_id
            or self.inspection.vendor_id
            or "Unknown Plugin"
        )
        plugin_row = QHBoxLayout()
        name_lbl = QLabel(disp_title)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        plugin_row.addWidget(name_lbl)

        ver_lbl = QLabel(f"v{self.inspection.version}")
        ver_lbl.setStyleSheet("""
            background-color: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        plugin_row.addWidget(ver_lbl)
        plugin_row.addStretch()
        id_layout.addLayout(plugin_row)

        # Details table-like info
        meta_html = (
            f"<div style='font-size: 11px; line-height: 1.6; color: #94a3b8;'>"
            f"<b>Vendor ID:</b> <span style='color: #e2e8f0; font-family: Consolas;'>{self.inspection.vendor_id}</span> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Plugin ID:</b> <span style='color: #e2e8f0; font-family: Consolas;'>{self.inspection.plugin_id}</span><br>"
            f"<b>Publisher:</b> <span style='color: #e2e8f0;'>{self.trust.publisher_name or 'Unknown Publisher'}</span><br>"
            f"<b>Key ID:</b> <span style='color: #e2e8f0; font-family: Consolas;'>{self.trust.key_id or 'None'}</span> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Fingerprint:</b> <span style='color: #e2e8f0; font-family: Consolas;'>{self.trust.fingerprint[:16] if self.trust.fingerprint else 'None'}...</span><br>"
            f"<b>Package Hash:</b> <span style='color: #e2e8f0; font-family: Consolas;'>{self.inspection.package_hash[:16] if self.inspection.package_hash else 'None'}...</span>"
            f"</div>"
        )
        meta_lbl = QLabel(meta_html)
        meta_lbl.setTextFormat(Qt.TextFormat.RichText)
        id_layout.addWidget(meta_lbl)

        layout.addWidget(id_frame)

        # 3. Storefront Domains & Capabilities
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)

        # Domains Section
        domains_frame = QFrame()
        domains_frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px 12px;
            }
        """)
        d_layout = QVBoxLayout(domains_frame)
        d_layout.setContentsMargins(10, 8, 10, 8)
        d_layout.setSpacing(4)

        d_title = QLabel("Declared Storefront Domains (Network Egress Boundaries)")
        d_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #f8fafc;")
        d_layout.addWidget(d_title)

        manifest_routes = self.inspection.manifest_metadata.get("routes", {}) if self.inspection.manifest_metadata else {}
        domains = manifest_routes.get("domains", []) or []
        base_url = manifest_routes.get("base_url", "")
        if not domains and base_url:
            domains = [base_url]

        if domains:
            domains_str = ", ".join(domains)
            d_desc = QLabel(f"<span style='color: #38bdf8; font-family: Consolas;'>{domains_str}</span>")
            d_desc.setTextFormat(Qt.TextFormat.RichText)
        else:
            d_desc = QLabel("None declared (No external network egress)")
            d_desc.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        d_layout.addWidget(d_desc)
        details_layout.addWidget(domains_frame)

        # Capabilities Section
        caps_frame = QFrame()
        caps_frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px 12px;
            }
        """)
        c_layout = QVBoxLayout(caps_frame)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(4)

        c_title = QLabel("Declared Capabilities")
        c_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #f8fafc;")
        c_layout.addWidget(c_title)

        caps = self.inspection.manifest_metadata.get("capabilities", []) if self.inspection.manifest_metadata else []
        if caps:
            caps_str = " &nbsp;•&nbsp; ".join(caps)
            c_desc = QLabel(f"<span style='color: #94a3b8; font-size: 11px;'>{caps_str}</span>")
            c_desc.setTextFormat(Qt.TextFormat.RichText)
            c_desc.setWordWrap(True)
        else:
            c_desc = QLabel("Standard adapter procurement capabilities")
            c_desc.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        c_layout.addWidget(c_desc)
        details_layout.addWidget(caps_frame)

        scroll.setWidget(details_container)
        layout.addWidget(scroll, 1)

        # 4. Security Warning Banner
        warn_frame = QFrame()
        if self.trust.is_trusted:
            warn_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(2, 132, 199, 0.1);
                    border: 1px solid #0284c7;
                    border-radius: 6px;
                    padding: 8px 12px;
                }
            """)
            warn_icon = "ℹ️"
            warn_msg = (
                "Verified cryptographic signature from trusted publisher. "
                "Installing will extract files to the local plugins repository and enable procurement automation."
            )
            warn_color = "#38bdf8"
        else:
            warn_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(239, 68, 68, 0.1);
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                    padding: 8px 12px;
                }
            """)
            warn_icon = "⚠️"
            err_text = self.trust.error_message or "Publisher key is untrusted or signature is missing."
            warn_msg = f"Untrusted Package Rejected: {err_text} Installation is blocked under fail-closed security rules."
            warn_color = "#f87171"

        w_layout = QHBoxLayout(warn_frame)
        w_layout.setContentsMargins(8, 6, 8, 6)
        w_layout.setSpacing(8)

        w_icon_lbl = QLabel(warn_icon)
        w_icon_lbl.setStyleSheet("font-size: 16px;")
        w_layout.addWidget(w_icon_lbl)

        w_text_lbl = QLabel(warn_msg)
        w_text_lbl.setStyleSheet(f"font-size: 11px; color: {warn_color};")
        w_text_lbl.setWordWrap(True)
        w_layout.addWidget(w_text_lbl, 1)

        layout.addWidget(warn_frame)

        # 5. Bottom Action Buttons
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
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.install_btn = FocusPaddedPushButton("Install & Activate")
        self.install_btn.setObjectName("primaryBtn")
        if self.trust.is_trusted:
            self.install_btn.setEnabled(True)
            self.install_btn.setStyleSheet("""
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
        else:
            self.install_btn.setEnabled(False)
            self.install_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #64748b;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 6px 18px;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        self.install_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.install_btn)

        layout.addLayout(btn_row)

        # Keyboard defaults: Escape and default button is Cancel for safety
        self.cancel_btn.setDefault(True)
        self.cancel_btn.setFocus()

    def _build_trust_badge(self) -> QLabel:
        badge = QLabel()
        if self.trust.status == TrustStatus.TRUSTED_PRODUCTION:
            badge.setText("OFFICIAL")
            badge.setStyleSheet("""
                background-color: rgba(34, 197, 94, 0.15);
                color: #4ade80;
                border: 1px solid #22c55e;
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        elif self.trust.status == TrustStatus.TRUSTED_DEVELOPMENT:
            badge.setText("DEVELOPMENT")
            badge.setStyleSheet("""
                background-color: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        else:
            badge.setText("UNTRUSTED")
            badge.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid #ef4444;
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: bold;
            """)
        return badge
