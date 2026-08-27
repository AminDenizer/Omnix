from typing import Callable, Optional
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from models import Component


class DrawerChipsWidget(QWidget):
    """Widget to display drawer chips with max 3 tags per row, empty drawer highlights, and ellipsis button."""

    def __init__(
        self,
        component: Component,
        on_click_filter: Callable[[int], None],
        on_toggle_expand: Callable[[], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.comp = component
        self.drawer_list = component.drawer_list
        self.on_click_filter = on_click_filter
        self.on_toggle_expand = on_toggle_expand
        self.is_expanded = False
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(3)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rebuild(expanded=False)

    def rebuild(self, expanded: bool):
        self.is_expanded = expanded

        # Clean up existing widgets
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        if not self.drawer_list:
            lbl = QLabel("—")
            lbl.setStyleSheet("color: #64748b;")
            self.main_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            return

        if not expanded and len(self.drawer_list) > 3:
            # Compact mode: First 3 drawers + ellipsis button (...)
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            for d in self.drawer_list[:3]:
                qty = self.comp.get_drawer_qty(d)
                chip = self._create_chip(d, qty)
                row_layout.addWidget(chip)

            more_chip = QPushButton("...")
            more_chip.setProperty("class", "drawerChipMore")
            more_chip.setToolTip("مشاهده تمام کشوها (کلیک یا فشردن Enter)")
            more_chip.clicked.connect(self.on_toggle_expand)
            row_layout.addWidget(more_chip)

            self.main_layout.addLayout(row_layout)
        else:
            # Expanded mode: Rows of max 3 chips with detailed stock info
            chunks = [self.drawer_list[i:i + 3] for i in range(0, len(self.drawer_list), 3)]
            for chunk in chunks:
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                for d in chunk:
                    qty = self.comp.get_drawer_qty(d)
                    chip = self._create_chip(d, qty, detailed=expanded)
                    row_layout.addWidget(chip)
                self.main_layout.addLayout(row_layout)

    def _create_chip(self, d_num: int, qty: int, detailed: bool = False) -> QPushButton:
        num_drawers = max(1, len(self.drawer_list))
        drawer_threshold = max(2, self.comp.min_alert // num_drawers)

        is_empty = (qty == 0)
        is_low = (0 < qty <= drawer_threshold)

        # Chip label: raw drawer number in compact mode, or number + count in expanded mode
        label = f"{d_num} ({qty:,})" if detailed else str(d_num)
        chip = QPushButton(label)
        chip.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        if is_empty:
            chip.setProperty("class", "drawerChipEmpty")
            chip.setToolTip(f"کشو شماره {d_num} | وضعیت: ناموجود و خالی (۰ عدد)")
        elif is_low:
            chip.setProperty("class", "drawerChipLow")
            chip.setToolTip(f"کشو شماره {d_num} | وضعیت: کسری موجودی ({qty:,} عدد — آستانه هشدار: {drawer_threshold:,})")
        else:
            chip.setProperty("class", "drawerChip")
            chip.setToolTip(f"کشو شماره {d_num} | وضعیت: موجودی کافی ({qty:,} عدد)")

        chip.clicked.connect(lambda _, n=d_num: self.on_click_filter(n))
        return chip
