"""
Omnix UI — Dedicated Vendor Plugins View
Governing Requirement: Separation of Executable Plugins from Supplier Directory
"""

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QCheckBox,
    QScrollArea,
)

from core.procurement.registry import VendorRegistry, default_registry
from settings_manager import settings
from core.models import VendorSettings


class VendorPluginsWidget(QWidget):
    """
    Dedicated view for inspecting and configuring executable vendor plugins.
    Decoupled from Supplier Directory (which manages static supplier records).
    """

    def __init__(self, registry: Optional[VendorRegistry] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.registry = registry or default_registry
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Header Info Banner
        hdr_layout = QHBoxLayout()
        title_lbl = QLabel("Vendor Plugins")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(self.summary_lbl)
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

    def refresh_plugins(self):
        """Re-render plugin list based on current registry contents."""
        self.refresh()

    def refresh(self):
        """Re-render plugin list based on current registry contents."""
        # Clear existing items
        while self.content_layout.count() > 0:
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if hasattr(self.registry, "list_vendors"):
            vendors = self.registry.list_vendors()
        elif hasattr(self.registry, "get_all_vendors"):
            vendors = list(self.registry.get_all_vendors().keys())
        else:
            vendors = []

        self.summary_lbl.setText(f"{len(vendors)} plugin(s) installed")

        if not vendors:
            # Empty state card
            card = QFrame()
            card.setObjectName("cardFrame")
            card.setStyleSheet("""
                QFrame#cardFrame {
                    background-color: #0f172a;
                    border: 1px solid #1e293b;
                    border-radius: 8px;
                    padding: 32px 24px;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(12)
            c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_lbl = QLabel("🔌")
            icon_lbl.setStyleSheet("font-size: 36px; background-color: transparent;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_layout.addWidget(icon_lbl)

            empty_title = QLabel("No Vendor Plugins Installed")
            empty_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f1f5f9; background-color: transparent;")
            empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_layout.addWidget(empty_title)

            empty_desc = QLabel(
                "A clean installation of Omnix contains zero pre-installed vendor plugins.\n"
                "In-tree reference adapters (Lion, Javan, RoboEQ) are registered via test fixtures or configured in release environments."
            )
            empty_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5; background-color: transparent;")
            empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_desc.setWordWrap(True)
            c_layout.addWidget(empty_desc)

            self.content_layout.addWidget(card)
            self.content_layout.addStretch(1)
            return

        for vid in sorted(vendors):
            reg_entry = self.registry.get_registration(vid) if hasattr(self.registry, "get_registration") else None
            disp_name = getattr(reg_entry, "display_name", None) or vid.replace("vendor_", "").title()
            active_version = self.registry.get_active_version(vid) if hasattr(self.registry, "get_active_version") else "1.0.0"
            domains = getattr(reg_entry, "domains", []) or []
            domain_str = ", ".join(domains) if domains else "None"
            desc = getattr(reg_entry, "description", "") or f"{disp_name} automated procurement plugin."
            is_enabled = self.registry.is_vendor_enabled(vid) if hasattr(self.registry, "is_vendor_enabled") else True

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

            top_row.addStretch()

            active_chk = QCheckBox("Active")
            active_chk.setStyleSheet("font-weight: bold; color: #38bdf8; background-color: transparent;")
            active_chk.setChecked(is_enabled)
            active_chk.toggled.connect(lambda chk, v=vid: self._on_vendor_toggled(v, chk))
            top_row.addWidget(active_chk)

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

            card_layout.addLayout(top_row)

            # Metadata sub-row
            meta_lbl = QLabel(f"ID: <span style='color: #94a3b8;'>{vid}</span> &nbsp;|&nbsp; Domains: <span style='color: #94a3b8;'>{domain_str}</span>")
            meta_lbl.setTextFormat(Qt.TextFormat.RichText)
            meta_lbl.setStyleSheet("font-size: 11px; color: #64748b; background-color: transparent;")
            card_layout.addWidget(meta_lbl)

            desc_w = QLabel(desc)
            desc_w.setStyleSheet("font-size: 11px; color: #94a3b8; background-color: transparent;")
            desc_w.setWordWrap(True)
            card_layout.addWidget(desc_w)

            self.content_layout.addWidget(card)

        self.content_layout.addStretch(1)

    def _configure_vendor(self, vendor_id: str):
        parent_win = self.window()
        if hasattr(parent_win, "_open_settings"):
            parent_win._open_settings(initial_tab="plugins")

    def _on_vendor_toggled(self, vendor_id: str, enabled: bool):
        if hasattr(self.registry, "set_vendor_enabled"):
            self.registry.set_vendor_enabled(vendor_id, enabled)
        v_cfg = settings.get_vendor_settings(vendor_id)
        if v_cfg:
            v_cfg.enabled = enabled
            settings.set_vendor_settings(vendor_id, v_cfg)
