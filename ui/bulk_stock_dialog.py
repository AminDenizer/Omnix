import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QRadioButton, QButtonGroup, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWheelEvent, QIcon
from typing import Dict, Optional, Tuple
from models import Component


class SmoothSpinBox(QSpinBox):
    """SpinBox that passes mouse wheel events to parent viewport to prevent unintended value changes."""
    def wheelEvent(self, event: QWheelEvent):
        event.ignore()


class BulkStockDialog(QDialog):
    """Dedicated bulk stock increment/decrement dialog with drawer breakdown and live validation."""

    def __init__(self, parent=None, component: Optional[Component] = None):
        super().__init__(parent)
        self.comp = component
        self.setWindowTitle("کسر / افزایش کلی موجودی")
        self.resize(520, 540)
        self.setMinimumWidth(460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.drawer_spinboxes: Dict[int, SmoothSpinBox] = {}

        self._init_ui()
        self._on_amount_changed()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        # 1. Component specification header card
        header_card = QFrame()
        header_card.setObjectName("cardFrame")
        header_layout = QVBoxLayout(header_card)
        header_layout.setSpacing(4)

        val_text = self.comp.value if self.comp else "قطعه نامشخص"
        name_text = self.comp.name if self.comp else ""
        qty_text = f"{self.comp.quantity:,} عدد" if self.comp else "۰"

        lbl_val = QLabel(f"{val_text} — {name_text}")
        lbl_val.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(lbl_val)

        lbl_cur_qty = QLabel(f"موجودی فعلی کل انبار: {qty_text}")
        lbl_cur_qty.setStyleSheet("font-size: 12px; color: #94a3b8;")
        lbl_cur_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(lbl_cur_qty)

        layout.addWidget(header_card)

        # 2. Operation type selector (Add or Deduct)
        type_group_box = QFrame()
        type_group_box.setObjectName("cardFrame")
        type_layout = QHBoxLayout(type_group_box)
        type_layout.setContentsMargins(10, 6, 10, 6)

        self.btn_group = QButtonGroup(self)

        self.radio_add = QRadioButton("افزایش موجودی (+)")
        self.radio_add.setChecked(True)
        self.radio_add.setStyleSheet("color: #34d399; font-weight: 600;")
        self.btn_group.addButton(self.radio_add)
        type_layout.addWidget(self.radio_add)

        self.radio_deduct = QRadioButton("کسر از موجودی (−)")
        self.radio_deduct.setStyleSheet("color: #fbbf24; font-weight: 600;")
        self.btn_group.addButton(self.radio_deduct)
        type_layout.addWidget(self.radio_deduct)

        self.radio_add.toggled.connect(self._on_mode_toggled)
        layout.addWidget(type_group_box)

        # 3. Total amount input and quick increment buttons
        amount_card = QFrame()
        amount_card.setObjectName("cardFrame")
        amount_layout = QVBoxLayout(amount_card)
        amount_layout.setSpacing(8)

        lbl_amount_title = QLabel("تعداد کل عملیات:")
        lbl_amount_title.setStyleSheet("font-weight: 600; color: #e2e8f0;")
        amount_layout.addWidget(lbl_amount_title)

        amount_input_layout = QHBoxLayout()
        self.total_amount_spin = SmoothSpinBox()
        self.total_amount_spin.setRange(1, 1000000)
        self.total_amount_spin.setValue(10)
        self.total_amount_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_amount_spin.setStyleSheet("font-size: 15px; font-weight: 700; padding: 6px;")
        self.total_amount_spin.valueChanged.connect(self._on_amount_changed)
        amount_input_layout.addWidget(self.total_amount_spin, 2)

        # Quick preset buttons (+10, +50, +100, +500)
        for quick_val in (10, 50, 100, 500):
            btn = QPushButton(f"+{quick_val}")
            btn.setObjectName("secondaryBtn")
            btn.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            btn.setStyleSheet(
                "QPushButton {"
                "   padding: 4px 6px;"
                "   font-size: 11px;"
                "   font-weight: 700;"
                "   font-family: 'Consolas', 'Segoe UI Mono', monospace;"
                "   min-width: 54px;"
                "}"
            )
            btn.setToolTip(f"افزودن {quick_val} عدد به تعداد کل")
            btn.clicked.connect(lambda _, v=quick_val: self.total_amount_spin.setValue(self.total_amount_spin.value() + v))
            amount_input_layout.addWidget(btn)

        amount_layout.addLayout(amount_input_layout)
        layout.addWidget(amount_card)

        # 4. Drawer distribution and breakdown panel
        self.breakdown_card = QFrame()
        self.breakdown_card.setObjectName("cardFrame")
        self.breakdown_layout = QVBoxLayout(self.breakdown_card)
        self.breakdown_layout.setSpacing(8)

        breakdown_header = QHBoxLayout()
        lbl_bd_title = QLabel("تفکیک سهم کشوها:")
        lbl_bd_title.setStyleSheet("font-weight: 600; color: #e2e8f0;")
        breakdown_header.addWidget(lbl_bd_title)

        breakdown_header.addStretch()

        self.btn_auto_distribute = QPushButton("توزیع خودکار / یکنواخت")
        self.btn_auto_distribute.setObjectName("secondaryBtn")
        self.btn_auto_distribute.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        self.btn_auto_distribute.clicked.connect(self._auto_distribute_amount)
        breakdown_header.addWidget(self.btn_auto_distribute)

        self.breakdown_layout.addLayout(breakdown_header)

        # Build drawer inputs
        drawer_list = self.comp.drawer_list if self.comp else []
        if len(drawer_list) <= 1:
            self.btn_auto_distribute.setVisible(False)
            d_num = drawer_list[0] if drawer_list else 1
            lbl_single = QLabel(f"این قطعه تنها در کشوی {d_num} قرار دارد و کل عملیات روی همین کشو اعمال می‌شود.")
            lbl_single.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self.breakdown_layout.addWidget(lbl_single)
        else:
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)

            for idx, d in enumerate(drawer_list):
                cur_d_qty = self.comp.get_drawer_qty(d)
                lbl_d_name = QLabel(f"کشو {d}:")
                lbl_d_name.setStyleSheet("font-weight: 600; color: #38bdf8;")

                lbl_d_cur = QLabel(f"(موجودی: {cur_d_qty:,})")
                lbl_d_cur.setStyleSheet("color: #64748b; font-size: 11px;")

                spin = SmoothSpinBox()
                spin.setRange(0, 1000000)
                spin.setValue(0)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet("font-weight: 600; min-width: 80px;")
                spin.valueChanged.connect(self._validate_balance)
                self.drawer_spinboxes[d] = spin

                grid.addWidget(lbl_d_name, idx, 0)
                grid.addWidget(lbl_d_cur, idx, 1)
                grid.addWidget(spin, idx, 2)

            self.breakdown_layout.addLayout(grid)

        # 5. Live validation and balance indicator
        self.balance_status_lbl = QLabel()
        self.balance_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.breakdown_layout.addWidget(self.balance_status_lbl)

        layout.addWidget(self.breakdown_card)

        layout.addStretch()

        # 6. Action buttons (Submit and Cancel)
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        self.btn_submit = QPushButton("تایید و اعمال تغییرات")
        self.btn_submit.clicked.connect(self._on_submit)
        actions_layout.addWidget(self.btn_submit, 2)

        btn_cancel = QPushButton("انصراف")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        actions_layout.addWidget(btn_cancel, 1)

        layout.addLayout(actions_layout)

        # If single drawer, assign total quantity automatically
        if len(drawer_list) == 1:
            self.drawer_spinboxes[drawer_list[0]] = self.total_amount_spin
        elif drawer_list:
            self._auto_distribute_amount()

    def _on_mode_toggled(self):
        is_deduct = self.radio_deduct.isChecked()
        if is_deduct:
            self.btn_submit.setText("تایید و کسر از موجودی")
            self.btn_submit.setStyleSheet("background-color: #b91c1c; color: #ffffff;")
        else:
            self.btn_submit.setText("تایید و افزایش موجودی")
            self.btn_submit.setStyleSheet("background-color: #15803d; color: #ffffff;")
        self._validate_balance()

    def _on_amount_changed(self):
        if len(self.comp.drawer_list if self.comp else []) > 1:
            self._auto_distribute_amount()
        else:
            self._validate_balance()

    def _auto_distribute_amount(self):
        """Intelligently distribute total operation amount across drawers."""
        if not self.comp or not self.drawer_spinboxes:
            return

        total = self.total_amount_spin.value()
        drawers = self.comp.drawer_list
        is_deduct = self.radio_deduct.isChecked()

        if not drawers:
            return

        # Deduct mode: prioritize drawers with higher current stock
        if is_deduct:
            remaining = total
            for d in sorted(drawers, key=lambda x: self.comp.get_drawer_qty(x), reverse=True):
                cur_qty = self.comp.get_drawer_qty(d)
                take = min(remaining, cur_qty)
                if d in self.drawer_spinboxes:
                    self.drawer_spinboxes[d].blockSignals(True)
                    self.drawer_spinboxes[d].setValue(take)
                    self.drawer_spinboxes[d].blockSignals(False)
                remaining -= take
        else:
            # Add mode: distribute evenly among available drawers
            base = total // len(drawers)
            rem = total % len(drawers)
            for idx, d in enumerate(drawers):
                if d in self.drawer_spinboxes:
                    val = base + (1 if idx < rem else 0)
                    self.drawer_spinboxes[d].blockSignals(True)
                    self.drawer_spinboxes[d].setValue(val)
                    self.drawer_spinboxes[d].blockSignals(False)

        self._validate_balance()

    def _validate_balance(self):
        """Validate that breakdown sum strictly equals the total amount and check stock boundaries."""
        if not self.comp:
            return

        total_req = self.total_amount_spin.value()
        is_deduct = self.radio_deduct.isChecked()
        drawer_list = self.comp.drawer_list

        # 1. Check total available stock ceiling in deduct mode
        if is_deduct and total_req > self.comp.quantity:
            self.balance_status_lbl.setText(
                f"✕ خطا: تعداد درخواستی ({total_req:,}) بیشتر از کل موجودی انبار ({self.comp.quantity:,}) است!"
            )
            self.balance_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            self.btn_submit.setEnabled(False)
            return

        # 2. Single-drawer components
        if len(drawer_list) <= 1:
            self.balance_status_lbl.setText("✓ آماده اعمال روی کشوی قطعه")
            self.balance_status_lbl.setStyleSheet("color: #34d399; font-weight: 600; font-size: 11px;")
            self.btn_submit.setEnabled(True)
            return

        # 3. Multi-drawer components: check individual drawer stock capacity
        current_sum = 0
        drawer_overflow = False
        overflow_msg = ""

        for d, spin in self.drawer_spinboxes.items():
            val = spin.value()
            current_sum += val
            if is_deduct:
                cur_qty = self.comp.get_drawer_qty(d)
                if val > cur_qty:
                    drawer_overflow = True
                    overflow_msg = f"✕ خطا: کسر {val:,} از کشو {d} غیرمجاز است (موجودی کشو فقط {cur_qty:,} است)"
                    break

        if drawer_overflow:
            self.balance_status_lbl.setText(overflow_msg)
            self.balance_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            self.btn_submit.setEnabled(False)
            return

        # 4. Check breakdown sum equality with requested total
        diff = total_req - current_sum
        if diff == 0:
            self.balance_status_lbl.setText(f"✓ مجموع تفکیک کشوها ({current_sum:,}) با تعداد کل برابر است.")
            self.balance_status_lbl.setStyleSheet("color: #34d399; font-weight: 600; font-size: 11px;")
            self.btn_submit.setEnabled(True)
        else:
            direction = "کمتر" if diff > 0 else "بیشتر"
            self.balance_status_lbl.setText(
                f"✕ اختلاف تفکیک: مجموع ورودی‌ها {abs(diff):,} عدد {direction} از تعداد کل ({total_req:,}) است."
            )
            self.balance_status_lbl.setStyleSheet("color: #fbbf24; font-weight: 700; font-size: 11px;")
            self.btn_submit.setEnabled(False)

    def _on_submit(self):
        self.accept()

    def get_result(self) -> Tuple[bool, int, Dict[int, int]]:
        """Return: (is_deduct, total_amount, breakdown_dict)"""
        is_deduct = self.radio_deduct.isChecked()
        total_amount = self.total_amount_spin.value()
        drawer_list = self.comp.drawer_list if self.comp else []

        if len(drawer_list) <= 1:
            d_num = drawer_list[0] if drawer_list else 1
            breakdown = {d_num: total_amount}
        else:
            breakdown = {d: spin.value() for d, spin in self.drawer_spinboxes.items() if spin.value() > 0}

        return is_deduct, total_amount, breakdown
