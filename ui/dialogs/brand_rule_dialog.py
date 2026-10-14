"""
Omnix UI - Brand / Manufacturer Rule Configuration Dialog.
Allows technicians and procurement engineers to configure manufacturer constraints:
- ANY (Generic allowed)
- Predefined popular electronic manufacturers checklist
- Custom manufacturer input
"""

from typing import Any, List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QLineEdit, QPushButton, QScrollArea, QWidget, QFrame,
    QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

POPULAR_MANUFACTURERS = [
    "Texas Instruments",
    "STMicroelectronics",
    "Microchip Technology",
    "NXP Semiconductors",
    "Infineon Technologies",
    "Analog Devices",
    "Vishay Intertechnology",
    "Murata Manufacturing",
    "TDK Corporation",
    "Samsung Electro-Mechanics",
    "Yageo Corporation",
    "Diodes Incorporated",
    "onsemi",
    "Renesas Electronics",
    "KEMET Corporation",
    "Bourns",
    "Walsin Technology",
    "Broadcom",
    "Espressif Systems",
    "Nordic Semiconductor",
    "Silicon Labs",
    "Maxim Integrated",
    "Winbond",
    "Cypress Semiconductor",
    "Littelfuse",
    "Omron",
    "TE Connectivity",
    "Molex",
]


class BrandRuleDialog(QDialog):
    """
    Interactive modal dialog for configuring Brand / Manufacturer constraints on a BOM item.
    Supports:
    - ANY (Generic allowed)
    - Multi-selection from curated electronic brand list
    - Adding custom brand names
    - Mutual exclusivity: Selecting ANY clears explicit brands; selecting explicit brands unchecks ANY.
    """

    def __init__(self, item: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"🏷️ Brand / Manufacturer Rule — {item.designator} ({item.part_number})")
        self.resize(540, 580)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.mfg_checkboxes: dict[str, QCheckBox] = {}
        self._init_ui()
        self._load_current_state()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header card
        header_card = QFrame()
        header_card.setObjectName("cardFrame")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(4)

        title_lbl = QLabel(f"<b>Part Number:</b> {self.item.part_number}")
        title_lbl.setStyleSheet("font-size: 13px; color: #38bdf8;")
        h_layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            f"<b>Designator:</b> {self.item.designator} &nbsp;|&nbsp; "
            f"<b>Footprint:</b> {self.item.footprint or '—'}"
        )
        desc_lbl.setStyleSheet("font-size: 11.5px; color: #94a3b8;")
        h_layout.addWidget(desc_lbl)
        layout.addWidget(header_card)

        # 1. ANY Checkbox (prominent)
        self.any_cb = QCheckBox("🌐 ANY — Allow Any Brand / Generic Equivalent")
        self.any_cb.setStyleSheet("font-size: 13px; font-weight: bold; color: #34d399; padding: 4px 0px;")
        self.any_cb.toggled.connect(self._on_any_toggled)
        layout.addWidget(self.any_cb)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #1e293b;")
        layout.addWidget(sep)

        # 2. Filter Bar
        filter_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Filter brand list...")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)

        # 3. Scrollable List of Predefined Brands
        list_lbl = QLabel("Select Approved Manufacturer(s):")
        list_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e8f0;")
        layout.addWidget(list_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #0b101b; border: 1px solid #1e293b; border-radius: 6px;")

        self.scroll_content = QWidget()
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(8)

        # Populate popular manufacturers in 2 columns
        for idx, mfg in enumerate(POPULAR_MANUFACTURERS):
            cb = QCheckBox(mfg)
            cb.setStyleSheet("font-size: 12px; color: #f8fafc;")
            cb.toggled.connect(self._on_mfg_toggled)
            self.mfg_checkboxes[mfg] = cb
            row = idx // 2
            col = idx % 2
            self.grid_layout.addWidget(cb, row, col)

        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll, stretch=1)

        # 4. Custom Manufacturer Add Box
        custom_box = QFrame()
        custom_layout = QHBoxLayout(custom_box)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)

        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("Enter custom brand name (or comma-separated)...")
        self.custom_input.returnPressed.connect(self._add_custom_brand)
        custom_layout.addWidget(self.custom_input)

        add_btn = QPushButton("➕ Add Brand")
        add_btn.setObjectName("secondaryBtn")
        add_btn.clicked.connect(self._add_custom_brand)
        custom_layout.addWidget(add_btn)

        layout.addWidget(custom_box)

        # 5. Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.apply_btn = QPushButton("💾 Apply Brand Rule")
        self.apply_btn.clicked.connect(self._apply_and_close)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)

    def _add_custom_brand(self):
        text = self.custom_input.text().strip()
        if not text:
            return

        brands = [b.strip() for b in text.split(",") if b.strip()]
        for b in brands:
            if b not in self.mfg_checkboxes:
                cb = QCheckBox(b)
                cb.setStyleSheet("font-size: 12px; color: #38bdf8; font-weight: 600;")
                cb.setChecked(True)
                cb.toggled.connect(self._on_mfg_toggled)
                self.mfg_checkboxes[b] = cb
                count = len(self.mfg_checkboxes) - 1
                self.grid_layout.addWidget(cb, count // 2, count % 2)
            else:
                self.mfg_checkboxes[b].setChecked(True)

        self.custom_input.clear()
        self.any_cb.setChecked(False)

    def _on_any_toggled(self, checked: bool):
        if checked:
            for cb in self.mfg_checkboxes.values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _on_mfg_toggled(self, checked: bool):
        if checked:
            self.any_cb.blockSignals(True)
            self.any_cb.setChecked(False)
            self.any_cb.blockSignals(False)

    def _on_filter_changed(self, text: str):
        query = text.strip().lower()
        for name, cb in self.mfg_checkboxes.items():
            cb.setVisible(not query or query in name.lower())

    def _load_current_state(self):
        if self.item.is_manufacturer_any or not (self.item.allowed_manufacturers or self.item.manufacturer):
            self.any_cb.setChecked(True)
        else:
            self.any_cb.setChecked(False)
            selected = self.item.allowed_manufacturers or ([self.item.manufacturer] if self.item.manufacturer else [])
            for s in selected:
                s_clean = s.strip()
                if not s_clean:
                    continue
                matched = False
                for mfg, cb in self.mfg_checkboxes.items():
                    if mfg.lower() == s_clean.lower():
                        cb.setChecked(True)
                        matched = True
                        break
                if not matched:
                    cb = QCheckBox(s_clean)
                    cb.setStyleSheet("font-size: 12px; color: #38bdf8; font-weight: 600;")
                    cb.setChecked(True)
                    cb.toggled.connect(self._on_mfg_toggled)
                    self.mfg_checkboxes[s_clean] = cb
                    count = len(self.mfg_checkboxes) - 1
                    self.grid_layout.addWidget(cb, count // 2, count % 2)

    def _apply_and_close(self):
        if self.any_cb.isChecked():
            self.item.update_brand_rule("ANY", None)
        else:
            selected = [name for name, cb in self.mfg_checkboxes.items() if cb.isChecked()]
            if not selected:
                self.item.update_brand_rule("ANY", None)
            elif len(selected) == 1:
                self.item.update_brand_rule("EXACT", selected)
            else:
                self.item.update_brand_rule("APPROVED_LIST", selected)
        self.accept()
