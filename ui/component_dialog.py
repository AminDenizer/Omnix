import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QPlainTextEdit, QPushButton, QMessageBox,
    QFrame, QGridLayout, QWidget, QScrollArea
)
from PyQt6.QtGui import QPainter, QColor, QFont, QWheelEvent, QIcon
from PyQt6.QtCore import Qt
from typing import Optional, Dict, List
from models import Component
from database import Database, DEFAULT_CATEGORIES, DEFAULT_PACKAGES


def auto_detect_text_direction(widget, text: str):
    """Auto-detect text direction (RTL for Persian/Arabic, LTR for English/Latin)."""
    clean = text.strip()
    if not clean:
        widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        return

    for ch in clean:
        if ('\u0600' <= ch <= '\u06FF') or ('\uFB50' <= ch <= '\uFDFF') or ('\uFE70' <= ch <= '\uFEFF'):
            widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            return
        elif ch.isalpha() and ch.isascii():
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            return


class SmoothSpinBox(QSpinBox):
    """SpinBox that passes mouse wheel events to parent viewport to prevent accidental scrolling changes."""
    def wheelEvent(self, event: QWheelEvent):
        event.ignore()


class SmoothComboBox(QComboBox):
    """ComboBox that ignores scroll wheel events when its pop-up list is closed."""
    def wheelEvent(self, event: QWheelEvent):
        if not self.view().isVisible():
            event.ignore()
        else:
            super().wheelEvent(event)


class DescriptionPlainTextEdit(QPlainTextEdit):
    """Multi-line plain text editor with custom placeholder rendering."""
    def __init__(self, placeholder="درصد خطا، ولتاژ کاری، شرکت سازنده یا یادداشت‌های فنی...", parent=None):
        super().__init__(parent)
        self.custom_placeholder = placeholder
        self.document().setDocumentMargin(8)
        self.setFont(QFont("Segoe UI", 10))

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.toPlainText().strip():
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QColor("#64748b"))
            p.setFont(self.font())
            rect = self.viewport().rect().adjusted(10, 8, -10, -8)
            p.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self.custom_placeholder)
            p.end()


class ComponentDialog(QDialog):
    """Component creation and editing dialog with smooth scrolling and drawer allocation."""

    def __init__(self, parent=None, component: Optional[Component] = None, db: Optional[Database] = None):
        super().__init__(parent)
        self.component = component
        self.db = db
        self.is_edit_mode = component is not None
        self.drawer_spinboxes: Dict[int, SmoothSpinBox] = {}

        title = "ویرایش مشخصات قطعه" if self.is_edit_mode else "ثبت قطعه جدید در انبار"
        self.setWindowTitle(title)
        self.resize(560, 680)
        self.setMinimumSize(480, 520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self._init_ui()
        if self.is_edit_mode and self.component:
            self._load_component_data(self.component)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 16, 18, 16)

        # Dialog header
        header_layout = QHBoxLayout()
        title_lbl = QLabel(self.windowTitle())
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #38bdf8;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Scroll area with smooth single step scrolling
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("dialogScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.verticalScrollBar().setSingleStep(25)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(14)
        form_layout.setContentsMargins(4, 4, 10, 24)  # 24px bottom padding for clean spacing

        # Primary specifications card
        form_frame = QFrame()
        form_frame.setObjectName("cardFrame")
        grid = QGridLayout(form_frame)
        grid.setSpacing(12)
        grid.setColumnMinimumWidth(0, 140)
        grid.setColumnStretch(1, 1)

        # 1. Component Name
        lbl_name = QLabel("نام قطعه:")
        lbl_name.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_name, 0, 0)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("مثلاً: مقاومت، خازن سرامیکی، رگولاتور ولتاژ")
        self.name_input.textChanged.connect(lambda t: auto_detect_text_direction(self.name_input, t))
        grid.addWidget(self.name_input, 0, 1)

        # 2. Value / Part Number
        lbl_val = QLabel("مقدار یا پارت‌نامبر: *")
        lbl_val.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_val, 1, 0)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("مثلاً: 10k, 100nF, AMS1117-3.3, NE555, BC547")
        self.value_input.textChanged.connect(lambda t: auto_detect_text_direction(self.value_input, t))
        grid.addWidget(self.value_input, 1, 1)

        # 3. Package / Footprint ComboBox
        lbl_pkg = QLabel("پکیج / فوت‌پرینت:")
        lbl_pkg.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_pkg, 2, 0)

        self.package_combo = SmoothComboBox()
        self.package_combo.setEditable(False)
        packages = self.db.get_packages() if self.db else DEFAULT_PACKAGES
        self.package_combo.addItems(packages)
        grid.addWidget(self.package_combo, 2, 1)

        # 4. Category ComboBox
        lbl_cat = QLabel("دسته‌بندی:")
        lbl_cat.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_cat, 3, 0)

        self.category_combo = SmoothComboBox()
        self.category_combo.setEditable(False)
        categories = self.db.get_categories() if self.db else DEFAULT_CATEGORIES
        self.category_combo.addItems(categories)
        grid.addWidget(self.category_combo, 3, 1)

        # 5. Drawer Numbers
        lbl_drawers = QLabel("شماره کشو(ها): *")
        lbl_drawers.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_drawers, 4, 0)

        drawer_col = QVBoxLayout()
        drawer_col.setSpacing(4)
        self.drawers_input = QLineEdit()
        self.drawers_input.setPlaceholderText("مثال: 1 یا چند کشو: 1, 4, 8")
        self.drawers_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.drawers_input.textChanged.connect(self._on_drawers_changed)
        drawer_col.addWidget(self.drawers_input)

        self.drawer_preview_lbl = QLabel("💡 شماره کشوها را با کاما وارد نمایید (مثال: 1, 4, 8)")
        self.drawer_preview_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        drawer_col.addWidget(self.drawer_preview_lbl)
        grid.addLayout(drawer_col, 4, 1)

        # 6. Total Quantity
        lbl_qty = QLabel("موجودی کل (تعداد): *")
        lbl_qty.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_qty, 5, 0)

        self.qty_spin = SmoothSpinBox()
        self.qty_spin.setRange(0, 1000000)
        self.qty_spin.setValue(0)
        self.qty_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_spin.valueChanged.connect(self._on_total_qty_changed)
        grid.addWidget(self.qty_spin, 5, 1)

        # 7. Low Stock Minimum Alert Threshold
        lbl_min = QLabel("حداقل هشدار کسری:")
        lbl_min.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        grid.addWidget(lbl_min, 6, 0)

        self.min_alert_spin = SmoothSpinBox()
        self.min_alert_spin.setRange(0, 100000)
        self.min_alert_spin.setValue(10)
        self.min_alert_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.min_alert_spin, 6, 1)

        form_layout.addWidget(form_frame)

        # Drawer stock breakdown card (visible when component spans multiple drawers)
        self.allocation_card = QFrame()
        self.allocation_card.setObjectName("cardFrame")
        self.allocation_layout = QVBoxLayout(self.allocation_card)
        self.allocation_layout.setSpacing(10)

        alloc_header = QHBoxLayout()
        lbl_alloc_title = QLabel("تفکیک سهم موجودی کشوها:")
        lbl_alloc_title.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 12px;")
        alloc_header.addWidget(lbl_alloc_title)

        alloc_header.addStretch()

        self.btn_auto_distribute = QPushButton("توزیع خودکار / یکنواخت")
        self.btn_auto_distribute.setObjectName("secondaryBtn")
        self.btn_auto_distribute.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_auto_distribute.clicked.connect(self._auto_distribute)
        alloc_header.addWidget(self.btn_auto_distribute)

        self.allocation_layout.addLayout(alloc_header)

        self.drawers_grid = QGridLayout()
        self.drawers_grid.setHorizontalSpacing(14)
        self.drawers_grid.setVerticalSpacing(8)
        self.drawers_grid.setColumnMinimumWidth(0, 140)
        self.drawers_grid.setColumnStretch(1, 1)
        self.allocation_layout.addLayout(self.drawers_grid)

        self.alloc_status_lbl = QLabel()
        self.alloc_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alloc_status_lbl.setWordWrap(True)
        self.alloc_status_lbl.setMinimumHeight(26)
        self.allocation_layout.addWidget(self.alloc_status_lbl)

        self.allocation_card.setVisible(False)
        form_layout.addWidget(self.allocation_card)

        # Technical notes card
        desc_frame = QFrame()
        desc_frame.setObjectName("cardFrame")
        desc_layout = QVBoxLayout(desc_frame)
        desc_layout.setSpacing(8)

        lbl_desc = QLabel("توضیحات فنی / یادداشت کارگاهی:")
        lbl_desc.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        desc_layout.addWidget(lbl_desc)

        self.desc_input = DescriptionPlainTextEdit(
            placeholder="درصد خطا، ولتاژ کاری، شرکت سازنده یا یادداشت‌های فنی..."
        )
        self.desc_input.setMaximumHeight(70)
        self.desc_input.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.desc_input.textChanged.connect(self._on_desc_text_changed)
        desc_layout.addWidget(self.desc_input)

        form_layout.addWidget(desc_frame)
        self.scroll_area.setWidget(form_container)
        main_layout.addWidget(self.scroll_area)

        # Dialog action buttons (Save & Cancel)
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("ذخیره قطعه")
        self.save_btn.setObjectName("successBtn")
        self.save_btn.clicked.connect(self._save)

        self.cancel_btn = QPushButton("انصراف")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        main_layout.addLayout(btn_layout)

    def _extract_drawers(self) -> List[int]:
        temp = Component(drawers=self.drawers_input.text())
        return temp.drawer_list

    def _on_drawers_changed(self, text: str):
        drawers = self._extract_drawers()
        if drawers:
            formatted = " ، ".join(f"کشو {d}" for d in drawers)
            self.drawer_preview_lbl.setText(f"✓ کشوهای ثبت‌شده: {formatted}")
            self.drawer_preview_lbl.setStyleSheet("color: #4ade80; font-size: 11px;")
        else:
            self.drawer_preview_lbl.setText("💡 شماره کشوها را با کاما وارد نمایید (مثال: 1, 4, 8)")
            self.drawer_preview_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self._rebuild_allocation_grid(drawers)

    def _rebuild_allocation_grid(self, drawers: List[int]):
        while self.drawers_grid.count():
            item = self.drawers_grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.drawer_spinboxes.clear()

        if len(drawers) <= 1:
            self.allocation_card.setVisible(False)
            return

        self.allocation_card.setVisible(True)
        for idx, d in enumerate(drawers):
            lbl = QLabel(f"موجودی در کشو شماره {d}:")
            lbl.setStyleSheet("color: #e2e8f0; font-weight: 600;")
            
            spin = SmoothSpinBox()
            spin.setRange(0, 1000000)
            spin.setValue(0)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spin.setStyleSheet("font-weight: 600; min-width: 90px;")
            spin.valueChanged.connect(self._validate_drawer_allocation)
            self.drawer_spinboxes[d] = spin

            self.drawers_grid.addWidget(lbl, idx, 0)
            self.drawers_grid.addWidget(spin, idx, 1)

        self._auto_distribute()

    def _on_total_qty_changed(self, val: int):
        drawers = self._extract_drawers()
        if len(drawers) > 1:
            if not self.drawer_spinboxes:
                self._rebuild_allocation_grid(drawers)
            else:
                self._validate_drawer_allocation()
        else:
            self.drawer_spinboxes.clear()

    def _auto_distribute(self):
        drawers = self._extract_drawers()
        if len(drawers) <= 1 or not self.drawer_spinboxes:
            return

        total = self.qty_spin.value()
        base = total // len(drawers)
        rem = total % len(drawers)

        for idx, d in enumerate(drawers):
            if d in self.drawer_spinboxes:
                val = base + (1 if idx < rem else 0)
                self.drawer_spinboxes[d].blockSignals(True)
                self.drawer_spinboxes[d].setValue(val)
                self.drawer_spinboxes[d].blockSignals(False)

        self._validate_drawer_allocation()

    def _validate_drawer_allocation(self):
        drawers = self._extract_drawers()
        if len(drawers) <= 1:
            return True

        total_qty = self.qty_spin.value()
        cur_sum = sum(s.value() for s in self.drawer_spinboxes.values())
        diff = total_qty - cur_sum

        if diff == 0:
            self.alloc_status_lbl.setText(f"✓ مجموع موجودی کشوها ({cur_sum:,}) با موجودی کل قطعه برابر است.")
            self.alloc_status_lbl.setStyleSheet("color: #34d399; font-weight: 600; font-size: 11px;")
            self.save_btn.setEnabled(True)
            return True
        elif diff > 0:
            self.alloc_status_lbl.setText(
                f"✕ کسری تخصیص: تعداد {diff:,} عدد از موجودی کل به کشوها اختصاص نیافته است."
            )
            self.alloc_status_lbl.setStyleSheet("color: #fbbf24; font-weight: 700; font-size: 11px;")
            self.save_btn.setEnabled(False)
            return False
        else:
            self.alloc_status_lbl.setText(
                f"✕ مازاد تخصیص: مجموع کشوها ({cur_sum:,}) بیشتر از موجودی کل ({total_qty:,}) است."
            )
            self.alloc_status_lbl.setStyleSheet("color: #f87171; font-weight: 700; font-size: 11px;")
            self.save_btn.setEnabled(False)
            return False

    def _on_desc_text_changed(self):
        text = self.desc_input.toPlainText().strip()
        if not text:
            self.desc_input.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            return

        for ch in text:
            if ('\u0600' <= ch <= '\u06FF') or ('\uFB50' <= ch <= '\uFDFF') or ('\uFE70' <= ch <= '\uFEFF'):
                self.desc_input.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                return
            elif ch.isalpha() and ch.isascii():
                self.desc_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                return

    def _load_component_data(self, comp: Component):
        self.name_input.setText(comp.name if comp.name != "—" else "")
        self.value_input.setText(comp.value)
        
        idx_pkg = self.package_combo.findText(comp.package)
        if idx_pkg >= 0:
            self.package_combo.setCurrentIndex(idx_pkg)
        else:
            self.package_combo.setCurrentIndex(0)

        idx_cat = self.category_combo.findText(comp.category)
        if idx_cat >= 0:
            self.category_combo.setCurrentIndex(idx_cat)
        else:
            self.category_combo.setCurrentIndex(0)

        self.drawers_input.setText(comp.formatted_drawers)
        self.qty_spin.setValue(comp.quantity)
        self.min_alert_spin.setValue(comp.min_alert)
        self.desc_input.setPlainText(comp.description)

        stocks = comp.drawer_stocks
        if len(comp.drawer_list) > 1:
            self._rebuild_allocation_grid(comp.drawer_list)
            for d, spin in self.drawer_spinboxes.items():
                spin.setValue(stocks.get(d, 0))
            self._validate_drawer_allocation()

    def get_component_data(self) -> Component:
        comp_id = self.component.id if self.component else None
        pkg_text = self.package_combo.currentText().strip() or "—"
        cat_text = self.category_combo.currentText().strip() or "—"

        drawers = self._extract_drawers()
        total_qty = self.qty_spin.value()

        if len(drawers) <= 1:
            d_num = drawers[0] if drawers else 1
            drawers_str = f"{d_num}:{total_qty}"
        else:
            parts = []
            for d in drawers:
                q = self.drawer_spinboxes[d].value() if d in self.drawer_spinboxes else 0
                parts.append(f"{d}:{q}")
            drawers_str = ", ".join(parts)

        return Component(
            id=comp_id,
            name=self.name_input.text().strip() or self.value_input.text().strip(),
            value=self.value_input.text().strip(),
            package=pkg_text,
            category=cat_text,
            quantity=total_qty,
            min_alert=self.min_alert_spin.value(),
            drawers=drawers_str,
            description=self.desc_input.toPlainText().strip()
        )

    def _save(self):
        val = self.value_input.text().strip()
        if not val:
            QMessageBox.warning(self, "خطای ورودی", "لطفاً مقدار قطعه یا پارت‌نامبر را وارد فرمایید (مثلاً 10k یا AMS1117-3.3).")
            self.value_input.setFocus()
            return

        drawers = self._extract_drawers()
        if not drawers:
            QMessageBox.warning(self, "خطای شماره کشو", "لطفاً حداقل یک شماره کشو معتبر وارد فرمایید (مثلاً: 1 یا 1, 4, 8).")
            self.drawers_input.setFocus()
            return

        if len(drawers) > 1:
            is_valid = self._validate_drawer_allocation()
            if not is_valid:
                total_qty = self.qty_spin.value()
                cur_sum = sum(s.value() for s in self.drawer_spinboxes.values())
                QMessageBox.warning(
                    self, "عدم تراز موجودی کشوها",
                    f"مجموع موجودی تفکیک‌شده کشوها ({cur_sum:,}) با موجودی کل ({total_qty:,}) برابر نیست.\n\n"
                    "لطفاً سهم هر کشو را تصحیح فرمایید یا بر روی دکمه «توزیع خودکار» کلیک نمایید."
                )
                return

        self.accept()
