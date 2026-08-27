import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox
)
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtCore import Qt
from typing import Optional
from database import Database


class DrawerInspectorDialog(QDialog):
    """Warehouse drawer contents inspector dialog with drop-down selector."""

    def __init__(self, parent=None, db: Optional[Database] = None):
        super().__init__(parent)
        self.db = db or Database()
        self.setWindowTitle("بازرسی و مشاهده کشوهای انبار")
        self.resize(840, 560)
        self.setMinimumWidth(720)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.current_drawer: Optional[int] = None

        self._init_ui()
        self._load_active_drawers()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Dialog header
        header = QHBoxLayout()
        title = QLabel("مشاهده و بازرسی محتویات کشوهای انبار")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #38bdf8;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # Drawer selection card with ComboBox
        top_card = QFrame()
        top_card.setObjectName("cardFrame")
        top_layout = QHBoxLayout(top_card)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(12)

        lbl_select = QLabel("کشوهای فعال در انبار:")
        lbl_select.setStyleSheet("font-weight: 600; color: #38bdf8;")
        top_layout.addWidget(lbl_select)

        self.drawer_combo = QComboBox()
        self.drawer_combo.setMinimumWidth(220)
        self.drawer_combo.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.drawer_combo.currentIndexChanged.connect(self._on_drawer_combo_changed)
        top_layout.addWidget(self.drawer_combo)

        # Custom direct drawer number entry
        lbl_custom = QLabel("یا شماره کشو:")
        lbl_custom.setStyleSheet("color: #94a3b8; font-size: 12px;")
        top_layout.addWidget(lbl_custom)

        self.drawer_input = QLineEdit()
        self.drawer_input.setPlaceholderText("شماره (مثلاً: 5)")
        self.drawer_input.setMaximumWidth(100)
        self.drawer_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drawer_input.textChanged.connect(self._on_input_text_changed)
        top_layout.addWidget(self.drawer_input)

        top_layout.addSpacing(10)
        self.info_lbl = QLabel()
        self.info_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        top_layout.addWidget(self.info_lbl)
        top_layout.addStretch()

        layout.addWidget(top_card)

        # Table showing components residing inside the selected drawer
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "نام قطعه", "مقدار / پارت‌نامبر", "پکیج", "دسته‌بندی", "موجودی در این کشو", "موجودی کل", "سایر کشوها"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Close button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        close_btn = QPushButton("بستن")
        close_btn.setObjectName("secondaryBtn")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        layout.addLayout(bottom_layout)

    def _load_active_drawers(self):
        self.drawer_combo.blockSignals(True)
        self.drawer_combo.clear()

        used_drawers = self.db.get_all_used_drawers()
        if not used_drawers:
            self.drawer_combo.addItem("هیچ کشویی ثبت نشده است", None)
            self.info_lbl.setText("هنوز هیچ کشویی در انبار ثبت نشده است.")
            self.drawer_combo.blockSignals(False)
            return

        for d_num in used_drawers:
            comps = self.db.get_components_by_drawer(d_num)
            count = len(comps)
            self.drawer_combo.addItem(f"کشو {d_num}  ({count} قلم قطعه)", d_num)

        self.drawer_combo.blockSignals(False)

        if used_drawers:
            self.drawer_combo.setCurrentIndex(0)
            self._select_drawer_by_number(used_drawers[0])

    def _on_drawer_combo_changed(self, index: int):
        data = self.drawer_combo.currentData()
        if data is not None and isinstance(data, int):
            self.drawer_input.blockSignals(True)
            self.drawer_input.setText(str(data))
            self.drawer_input.blockSignals(False)
            self._show_drawer_contents(data)

    def _on_input_text_changed(self, text: str):
        if text.strip().isdigit():
            num = int(text.strip())
            # Synchronize with combo box selection
            self.drawer_combo.blockSignals(True)
            for idx in range(self.drawer_combo.count()):
                if self.drawer_combo.itemData(idx) == num:
                    self.drawer_combo.setCurrentIndex(idx)
                    break
            self.drawer_combo.blockSignals(False)
            self._show_drawer_contents(num)
        else:
            self.table.setRowCount(0)
            self.info_lbl.setText("شماره کشو باید یک عدد معتبر باشد.")

    def _select_drawer_by_number(self, drawer_num: int):
        self.drawer_input.setText(str(drawer_num))

    def _show_drawer_contents(self, drawer_num: int):
        components = self.db.get_components_by_drawer(drawer_num)
        self.table.setRowCount(len(components))

        self.info_lbl.setText(f"تعداد {len(components)} قلم قطعه در کشوی شماره {drawer_num} قرار دارد.")

        for row_idx, comp in enumerate(components):
            self.table.setRowHeight(row_idx, 42)
            d_qty = comp.get_drawer_qty(drawer_num)

            item_name = QTableWidgetItem(comp.name or "—")
            item_val = QTableWidgetItem(comp.value)
            item_pkg = QTableWidgetItem(comp.package if comp.package else "—")
            item_cat = QTableWidgetItem(comp.category if comp.category else "—")
            
            # Stock quantity in this drawer with 3-state color coding
            item_d_qty = QTableWidgetItem(f"{d_qty:,} عدد")
            if d_qty == 0:
                item_d_qty.setForeground(QColor("#f87171"))  # Red (Empty)
            elif d_qty <= comp.min_alert:
                item_d_qty.setForeground(QColor("#fbbf24"))  # Amber (Low)
            else:
                item_d_qty.setForeground(QColor("#34d399"))  # Green (Sufficient)

            item_total_qty = QTableWidgetItem(f"{comp.quantity:,} عدد")
            
            # Other drawers: raw numbers only (e.g., "4" or "2 , 4") or dash "—"
            other_drawers = [str(d) for d in comp.drawer_list if d != drawer_num]
            other_text = " , ".join(other_drawers) if other_drawers else "—"
            item_others = QTableWidgetItem(other_text)

            for itm in (item_name, item_val, item_pkg, item_cat, item_d_qty, item_total_qty, item_others):
                itm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row_idx, 0, item_name)
            self.table.setItem(row_idx, 1, item_val)
            self.table.setItem(row_idx, 2, item_pkg)
            self.table.setItem(row_idx, 3, item_cat)
            self.table.setItem(row_idx, 4, item_d_qty)
            self.table.setItem(row_idx, 5, item_total_qty)
            self.table.setItem(row_idx, 6, item_others)


DrawerViewDialog = DrawerInspectorDialog
