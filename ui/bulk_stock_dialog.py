import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QButtonGroup, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from typing import Dict, Optional, Tuple
from models import Component
from ui.widgets import SmoothSpinBox


class BulkStockDialog(QDialog):
    """Dedicated bulk stock increment/decrement dialog with bidirectional drawer sync and smart validation."""

    def __init__(self, parent=None, component: Optional[Component] = None):
        super().__init__(parent)
        self.comp = component
        self.setWindowTitle("کسر / افزایش کلی موجودی")
        self.resize(520, 560)
        self.setMinimumWidth(460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.drawer_spinboxes: Dict[int, SmoothSpinBox] = {}
        self._sync_lock = False

        self._init_ui()
        self._on_mode_toggled()

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

        # Quick preset buttons (+10, +50, +100, کل موجودی)
        for quick_val in (10, 50, 100):
            btn = QPushButton(f"+{quick_val}")
            btn.setObjectName("secondaryBtn")
            btn.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            btn.setStyleSheet(
                "QPushButton {"
                "   padding: 4px 6px;"
                "   font-size: 11px;"
                "   font-weight: 700;"
                "   font-family: 'Consolas', 'Segoe UI Mono', monospace;"
                "   min-width: 50px;"
                "}"
            )
            btn.setToolTip(f"افزودن {quick_val} عدد به تعداد")
            btn.clicked.connect(lambda _, v=quick_val: self._add_preset(v))
            amount_input_layout.addWidget(btn)

        btn_all = QPushButton("کل موجودی")
        btn_all.setObjectName("secondaryBtn")
        btn_all.setStyleSheet("QPushButton { padding: 4px 8px; font-size: 11px; font-weight: 700; min-width: 70px; }")
        btn_all.setToolTip("انتخاب تمام موجودی کل این قطعه")
        btn_all.clicked.connect(self._set_all_stock)
        amount_input_layout.addWidget(btn_all)

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

        self.btn_auto_distribute = QPushButton("⚡ توزیع هوشمند و تراز")
        self.btn_auto_distribute.setObjectName("secondaryBtn")
        self.btn_auto_distribute.setStyleSheet("font-size: 11px; padding: 4px 8px; font-weight: 600;")
        self.btn_auto_distribute.setToolTip("توزیع متوازن (شارژ بیشتر کشوهای خالی و تراز کردن موجودی کل کشوها)")
        self.btn_auto_distribute.clicked.connect(self._auto_distribute_amount)
        breakdown_header.addWidget(self.btn_auto_distribute)

        self.btn_equal_distribute = QPushButton("تقسیم مساوی")
        self.btn_equal_distribute.setObjectName("secondaryBtn")
        self.btn_equal_distribute.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        self.btn_equal_distribute.setToolTip("تقسیم تعداد به نسبت کاملاً مساوی بین کشوها")
        self.btn_equal_distribute.clicked.connect(self._equal_distribute_amount)
        breakdown_header.addWidget(self.btn_equal_distribute)

        self.breakdown_layout.addLayout(breakdown_header)

        # Build drawer inputs
        drawer_list = self.comp.drawer_list if self.comp else []
        if len(drawer_list) <= 1:
            self.btn_auto_distribute.setVisible(False)
            self.btn_equal_distribute.setVisible(False)
            d_num = drawer_list[0] if drawer_list else 1
            lbl_single = QLabel(f"این قطعه تنها در کشوی {d_num} قرار دارد و کل عملیات روی همین کشو اعمال می‌شود.")
            lbl_single.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self.breakdown_layout.addWidget(lbl_single)
            if drawer_list:
                self.drawer_spinboxes[drawer_list[0]] = self.total_amount_spin
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
                spin.valueChanged.connect(self._on_drawer_spinbox_changed)
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
        self._on_mode_toggled()

    def _add_preset(self, val: int):
        cur = self.total_amount_spin.value()
        if self.radio_deduct.isChecked():
            max_qty = self.comp.quantity if self.comp else 0
            if max_qty > 0:
                self.total_amount_spin.setValue(min(cur + val, max_qty))
        else:
            self.total_amount_spin.setValue(cur + val)

    def _set_all_stock(self):
        if self.comp:
            target = max(1, self.comp.quantity)
            self.total_amount_spin.setValue(target)

    def _on_mode_toggled(self):
        is_deduct = self.radio_deduct.isChecked()
        max_qty = self.comp.quantity if self.comp else 0

        if is_deduct:
            self.btn_submit.setText("تایید و کسر از موجودی")
            self.btn_submit.setStyleSheet("background-color: #b91c1c; color: #ffffff; font-weight: 700;")
            self.btn_auto_distribute.setVisible(False)
            self.btn_equal_distribute.setText("⚡ تقسیم کسر بین کشوها")
            self.btn_equal_distribute.setToolTip("توزیع متناسب کسر بین تمام کشوهای دارای موجودی بدون ایجاد کسری")
            self.total_amount_spin.setMaximum(max(1, max_qty))
            if max_qty <= 0:
                self.total_amount_spin.setValue(0)
            elif self.total_amount_spin.value() > max_qty:
                self.total_amount_spin.setValue(max_qty)

            for d, spin in self.drawer_spinboxes.items():
                if spin is not self.total_amount_spin:
                    cur_d_qty = self.comp.get_drawer_qty(d)
                    spin.setMaximum(cur_d_qty)
                    if cur_d_qty == 0:
                        spin.setValue(0)
                        spin.setEnabled(False)
                    else:
                        spin.setEnabled(True)
        else:
            self.btn_submit.setText("تایید و افزایش موجودی")
            self.btn_submit.setStyleSheet("background-color: #15803d; color: #ffffff; font-weight: 700;")
            self.btn_auto_distribute.setVisible(True)
            self.btn_auto_distribute.setText("⚡ توزیع هوشمند و تراز")
            self.btn_equal_distribute.setText("تقسیم مساوی")
            self.btn_equal_distribute.setToolTip("تقسیم مساوی تعداد بین کشوها")
            self.total_amount_spin.setMaximum(1000000)
            if self.total_amount_spin.value() == 0:
                self.total_amount_spin.setValue(10)
            for d, spin in self.drawer_spinboxes.items():
                if spin is not self.total_amount_spin:
                    spin.setMaximum(1000000)
                    spin.setEnabled(True)

        self._auto_distribute_amount()

    def _on_amount_changed(self):
        if self._sync_lock or not self.comp:
            return
        self._sync_lock = True
        try:
            drawer_list = self.comp.drawer_list
            if len(drawer_list) > 1:
                self._distribute_logic()
            self._validate_balance()
        finally:
            self._sync_lock = False

    def _on_drawer_spinbox_changed(self):
        """Bidirectional sync: editing drawer amounts automatically updates the total amount."""
        if self._sync_lock or not self.comp:
            return
        self._sync_lock = True
        try:
            current_sum = sum(spin.value() for d, spin in self.drawer_spinboxes.items() if spin is not self.total_amount_spin)
            self.total_amount_spin.blockSignals(True)
            self.total_amount_spin.setValue(max(0, current_sum))
            self.total_amount_spin.blockSignals(False)
            self._validate_balance()
        finally:
            self._sync_lock = False

    def _auto_distribute_amount(self):
        """Intelligently distribute total operation amount across drawers."""
        if self._sync_lock or not self.comp:
            return
        self._sync_lock = True
        try:
            self._distribute_logic()
            self._validate_balance()
        finally:
            self._sync_lock = False

    def _fair_deduct_distribution(self, capacities: Dict[int, int], total_to_deduct: int) -> Dict[int, int]:
        """
        Distribute total_to_deduct across drawers such that no drawer exceeds its capacity,
        and the deduction is as evenly shared among eligible drawers as possible.
        """
        total_avail = sum(capacities.values())
        if total_to_deduct >= total_avail:
            return dict(capacities)

        if total_to_deduct <= 0:
            return {d: 0 for d in capacities}

        alloc = {d: 0 for d in capacities}
        remaining = total_to_deduct
        drawers = [d for d in capacities if capacities[d] > 0]

        while remaining > 0 and drawers:
            share = remaining // len(drawers)
            rem = remaining % len(drawers)
            if share == 0:
                for d in drawers[:remaining]:
                    alloc[d] += 1
                remaining = 0
                break

            capped_any = False
            remaining_drawers = []
            for idx, d in enumerate(drawers):
                intended = share + (1 if idx < rem else 0)
                avail = capacities[d] - alloc[d]
                if avail <= intended:
                    alloc[d] += avail
                    remaining -= avail
                    capped_any = True
                else:
                    remaining_drawers.append(d)

            if not capped_any:
                for idx, d in enumerate(drawers):
                    intended = share + (1 if idx < rem else 0)
                    alloc[d] += intended
                    remaining -= intended
                break
            else:
                drawers = remaining_drawers

        return alloc

    def _equal_distribute_amount(self):
        """Divide total amount across drawers (fair capacity-constrained in deduct mode, uniform in add mode)."""
        if self._sync_lock or not self.comp:
            return
        self._sync_lock = True
        try:
            total = self.total_amount_spin.value()
            drawers = self.comp.drawer_list if self.comp else []
            if len(drawers) > 1:
                if self.radio_deduct.isChecked():
                    capacities = {d: self.comp.get_drawer_qty(d) for d in drawers}
                    fair_alloc = self._fair_deduct_distribution(capacities, total)
                    for d, val in fair_alloc.items():
                        if d in self.drawer_spinboxes and self.drawer_spinboxes[d] is not self.total_amount_spin:
                            self.drawer_spinboxes[d].blockSignals(True)
                            self.drawer_spinboxes[d].setValue(val)
                            self.drawer_spinboxes[d].blockSignals(False)
                else:
                    base = total // len(drawers)
                    rem = total % len(drawers)
                    for idx, d in enumerate(drawers):
                        if d in self.drawer_spinboxes and self.drawer_spinboxes[d] is not self.total_amount_spin:
                            val = base + (1 if idx < rem else 0)
                            self.drawer_spinboxes[d].blockSignals(True)
                            self.drawer_spinboxes[d].setValue(val)
                            self.drawer_spinboxes[d].blockSignals(False)
            self._validate_balance()
        finally:
            self._sync_lock = False

    def _smart_balance_add(self, drawers: list, total: int) -> Dict[int, int]:
        """
        Water-filling balancing algorithm: prioritizes empty and low-stock drawers
        first to balance out stock levels across all drawers.
        """
        drawer_qtys = {d: self.comp.get_drawer_qty(d) for d in drawers}
        additions = {d: 0 for d in drawers}
        remaining = total
        current_levels = dict(drawer_qtys)

        while remaining > 0:
            min_val = min(current_levels.values())
            min_drawers = [d for d, val in current_levels.items() if val == min_val]
            other_vals = [val for val in current_levels.values() if val > min_val]

            if other_vals:
                next_min = min(other_vals)
                step_needed = next_min - min_val
                total_step = step_needed * len(min_drawers)
                if remaining >= total_step:
                    for d in min_drawers:
                        additions[d] += step_needed
                        current_levels[d] += step_needed
                    remaining -= total_step
                else:
                    base_per_min = remaining // len(min_drawers)
                    rem_per_min = remaining % len(min_drawers)
                    for idx, d in enumerate(min_drawers):
                        extra = base_per_min + (1 if idx < rem_per_min else 0)
                        additions[d] += extra
                        current_levels[d] += extra
                    remaining = 0
            else:
                base_all = remaining // len(drawers)
                rem_all = remaining % len(drawers)
                for idx, d in enumerate(drawers):
                    extra = base_all + (1 if idx < rem_all else 0)
                    additions[d] += extra
                    current_levels[d] += extra
                remaining = 0

        return additions

    def _distribute_logic(self):
        total = self.total_amount_spin.value()
        drawers = self.comp.drawer_list if self.comp else []
        is_deduct = self.radio_deduct.isChecked()

        if len(drawers) <= 1:
            return

        if is_deduct:
            remaining = total
            # Deduct from drawers with highest stock first
            for d in sorted(drawers, key=lambda x: self.comp.get_drawer_qty(x), reverse=True):
                cur_qty = self.comp.get_drawer_qty(d)
                take = min(remaining, cur_qty)
                if d in self.drawer_spinboxes and self.drawer_spinboxes[d] is not self.total_amount_spin:
                    self.drawer_spinboxes[d].blockSignals(True)
                    self.drawer_spinboxes[d].setValue(take)
                    self.drawer_spinboxes[d].blockSignals(False)
                remaining -= take
        else:
            # Smart Water-Filling balance: fill empty/low drawers first
            balanced_additions = self._smart_balance_add(drawers, total)
            for d, val in balanced_additions.items():
                if d in self.drawer_spinboxes and self.drawer_spinboxes[d] is not self.total_amount_spin:
                    self.drawer_spinboxes[d].blockSignals(True)
                    self.drawer_spinboxes[d].setValue(val)
                    self.drawer_spinboxes[d].blockSignals(False)

    def _validate_balance(self):
        """Validate current state and show clear, friendly feedback."""
        if not self.comp:
            return

        total_req = self.total_amount_spin.value()
        is_deduct = self.radio_deduct.isChecked()
        drawer_list = self.comp.drawer_list

        if is_deduct and self.comp.quantity <= 0:
            self.balance_status_lbl.setText("✕ این قطعه در انبار ناموجود است و امکان کسر وجود ندارد.")
            self.balance_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            self.btn_submit.setEnabled(False)
            return

        if total_req <= 0:
            self.balance_status_lbl.setText("لطفاً تعداد عملیات را مشخص کنید (حداقل ۱ عدد)")
            self.balance_status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self.btn_submit.setEnabled(False)
            return

        if is_deduct and total_req > self.comp.quantity:
            self.balance_status_lbl.setText(
                f"✕ خطا: تعداد درخواستی ({total_req:,}) بیشتر از کل موجودی انبار ({self.comp.quantity:,}) است!"
            )
            self.balance_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            self.btn_submit.setEnabled(False)
            return

        # Multi-drawer verification
        if len(drawer_list) > 1:
            current_sum = sum(spin.value() for d, spin in self.drawer_spinboxes.items() if spin is not self.total_amount_spin)
            if is_deduct:
                for d, spin in self.drawer_spinboxes.items():
                    if spin is not self.total_amount_spin:
                        val = spin.value()
                        cur_d_qty = self.comp.get_drawer_qty(d)
                        if val > cur_d_qty:
                            self.balance_status_lbl.setText(
                                f"✕ خطا: کسر {val:,} از کشو {d} بیشتر از موجودی آن ({cur_d_qty:,}) است."
                            )
                            self.balance_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
                            self.btn_submit.setEnabled(False)
                            return

            diff = total_req - current_sum
            if diff != 0:
                direction = "کمتر" if diff > 0 else "بیشتر"
                self.balance_status_lbl.setText(
                    f"✕ مجموع تفکیک کشوها ({current_sum:,}) با تعداد کل ({total_req:,}) برابر نیست."
                )
                self.balance_status_lbl.setStyleSheet("color: #fbbf24; font-weight: 700; font-size: 11px;")
                self.btn_submit.setEnabled(False)
                return

        # Positive ready status
        if is_deduct:
            future_qty = self.comp.quantity - total_req
            self.balance_status_lbl.setText(
                f"✓ آماده کسر {total_req:,} عدد (موجودی انبار پس از کسر: {future_qty:,} عدد خواهد شد)"
            )
            self.balance_status_lbl.setStyleSheet("color: #34d399; font-weight: 600; font-size: 12px;")
            self.btn_submit.setEnabled(True)
        else:
            future_qty = self.comp.quantity + total_req
            self.balance_status_lbl.setText(
                f"✓ آماده افزایش {total_req:,} عدد (موجودی انبار پس از افزایش: {future_qty:,} عدد خواهد شد)"
            )
            self.balance_status_lbl.setStyleSheet("color: #34d399; font-weight: 600; font-size: 12px;")
            self.btn_submit.setEnabled(True)

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
            breakdown = {
                d: spin.value() for d, spin in self.drawer_spinboxes.items()
                if spin is not self.total_amount_spin and spin.value() > 0
            }

        return is_deduct, total_amount, breakdown
