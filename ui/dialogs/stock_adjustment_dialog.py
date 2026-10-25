"""
Omnix UI - Dedicated Manual Stock Management Dialog
Allows explicit manual adjustment of on-hand physical stock for a selected component.
"""

from typing import Optional, Any
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.inventory.models import InventoryProduct, ValidationError, ComponentNotFoundError
from core.inventory.repository import SqliteInventoryRepository
from ui.dark_frame import apply_dark_window_frame


class StockAdjustmentDialog(QDialog):
    """
    Compact, focused dialog for manual component stock adjustments.
    Allows entering a final quantity directly or adjusting with delta buttons (+1, +10, -1, -10).
    """

    def __init__(
        self,
        component: InventoryProduct,
        repository: SqliteInventoryRepository,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.component = component
        self.repository = repository
        self.saved_component: Optional[InventoryProduct] = None

        mfr_name = self.component.manufacturer or "Unknown Manufacturer"
        mpn_name = self.component.mpn or "Unknown MPN"
        self.setWindowTitle(f"Stock Management — {mfr_name} {mpn_name}")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setMinimumHeight(340)

        apply_dark_window_frame(self)

        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                color: #cbd5e1;
            }
            QSpinBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                font-weight: bold;
            }
            QSpinBox:focus {
                border-color: #38bdf8;
            }
            QToolButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                color: #38bdf8;
            }
            QToolButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QToolButton:pressed {
                background-color: #0284c7;
            }
        """)

        self._setup_ui()

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 1. Header Card: Read-only Component Identity
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        hdr_layout = QVBoxLayout(header_frame)
        hdr_layout.setContentsMargins(12, 10, 12, 10)
        hdr_layout.setSpacing(6)

        title_lbl = QLabel("📦 Stock Management")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)

        # MPN and Manufacturer
        mfr = self.component.manufacturer or "Unknown Manufacturer"
        mpn = self.component.mpn or "Unknown MPN"
        comp_hdr = QLabel(f"<b>{mfr}</b> &nbsp;|&nbsp; <b>{mpn}</b>")
        comp_hdr.setTextFormat(Qt.TextFormat.RichText)
        comp_hdr.setStyleSheet("font-size: 12px; color: #f8fafc;")
        hdr_layout.addWidget(comp_hdr)

        # Category, Value, Footprint
        cat = self.component.category or "-"
        tech = self.component.type_technology or "-"
        val = self.component.value or "-"
        fp = self.component.footprint or "-"
        sub_info = f"{cat} &nbsp;•&nbsp; {tech} &nbsp;•&nbsp; Value: {val} &nbsp;•&nbsp; Package: {fp}"
        sub_lbl = QLabel(sub_info)
        sub_lbl.setTextFormat(Qt.TextFormat.RichText)
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(sub_lbl)

        # Description if present
        if self.component.description:
            desc_lbl = QLabel(self.component.description)
            desc_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")
            hdr_layout.addWidget(desc_lbl)

        # Current stock pill
        curr_stock = int(self.component.quantity_in_stock or 0)
        stk_lbl = QLabel(f"Current On-Hand Stock: <b>{curr_stock}</b> units")
        stk_lbl.setTextFormat(Qt.TextFormat.RichText)
        stk_lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 4px;
                color: #34d399;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        hdr_layout.addWidget(stk_lbl)

        main_layout.addWidget(header_frame)

        # 2. Desired Final Quantity Input Section
        input_frame = QFrame()
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        input_title = QLabel("Desired Final On-Hand Quantity:")
        input_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e8f0;")
        input_layout.addWidget(input_title)

        spin_row = QHBoxLayout()
        spin_row.setSpacing(6)
        spin_row.setContentsMargins(0, 0, 0, 0)

        self.qty_spin = QSpinBox()
        self.qty_spin.setFont(QFont("Consolas", 12))
        self.qty_spin.setRange(0, 1000000)
        self.qty_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.qty_spin.setFixedHeight(36)
        self.qty_spin.setValue(curr_stock)
        self.qty_spin.wheelEvent = lambda event: event.ignore()
        self.qty_spin.valueChanged.connect(self._on_quantity_changed)
        spin_row.addWidget(self.qty_spin, 1)

        # Paired up/down tool buttons
        btn_box = QVBoxLayout()
        btn_box.setSpacing(2)
        btn_box.setContentsMargins(0, 0, 0, 0)

        self.up_btn = QToolButton()
        self.up_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.up_btn.setFixedSize(28, 17)
        self.up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.up_btn.setToolTip("Increase quantity (+1)")
        self.up_btn.setAutoRepeat(True)
        self.up_btn.setAutoRepeatDelay(400)
        self.up_btn.setAutoRepeatInterval(100)
        self.up_btn.clicked.connect(self.qty_spin.stepUp)
        btn_box.addWidget(self.up_btn)

        self.down_btn = QToolButton()
        self.down_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.down_btn.setFixedSize(28, 17)
        self.down_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.down_btn.setToolTip("Decrease quantity (-1)")
        self.down_btn.setAutoRepeat(True)
        self.down_btn.setAutoRepeatDelay(400)
        self.down_btn.setAutoRepeatInterval(100)
        self.down_btn.clicked.connect(self.qty_spin.stepDown)
        btn_box.addWidget(self.down_btn)

        spin_row.addLayout(btn_box)
        input_layout.addLayout(spin_row)

        # Quick step controls: -10, -1, +1, +10
        quick_btns_layout = QHBoxLayout()
        quick_btns_layout.setSpacing(8)

        step_deltas = [(-10, "-10"), (-1, "-1"), (+1, "+1"), (+10, "+10")]
        self.step_buttons = []
        for delta, label in step_deltas:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 8px;
                }
                QPushButton:hover {
                    background-color: #334155;
                    color: #38bdf8;
                    border-color: #38bdf8;
                }
            """)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_quantity_by(d))
            quick_btns_layout.addWidget(btn)
            self.step_buttons.append(btn)

        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedHeight(28)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip("Reset to current stock")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                color: #64748b;
                border: 1px dashed #334155;
                border-radius: 4px;
                font-size: 11px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                color: #f8fafc;
                border-color: #64748b;
            }
        """)
        reset_btn.clicked.connect(lambda: self.qty_spin.setValue(curr_stock))
        quick_btns_layout.addWidget(reset_btn)

        input_layout.addLayout(quick_btns_layout)

        # Delta feedback indicator
        self.delta_lbl = QLabel("● No change (quantity unchanged)")
        self.delta_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        input_layout.addWidget(self.delta_lbl)

        main_layout.addWidget(input_frame)

        main_layout.addStretch()

        # 3. Action Buttons: Cancel and Save
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.setFixedHeight(34)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        self.save_btn = QPushButton("Save Stock")
        self.save_btn.setFixedHeight(34)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 20px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
            }
        """)
        self.save_btn.clicked.connect(self._save_stock)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

    def _adjust_quantity_by(self, delta: int):
        cur = self.qty_spin.value()
        new_val = max(0, cur + delta)
        self.qty_spin.setValue(new_val)

    def _on_quantity_changed(self, new_val: int):
        curr_stock = int(self.component.quantity_in_stock or 0)
        diff = new_val - curr_stock
        if diff > 0:
            self.delta_lbl.setText(f"▲ Increase: +{diff} units (from {curr_stock} to {new_val})")
            self.delta_lbl.setStyleSheet("font-size: 11px; color: #34d399; font-weight: 600;")
        elif diff < 0:
            self.delta_lbl.setText(f"▼ Decrease: {diff} units (from {curr_stock} to {new_val})")
            self.delta_lbl.setStyleSheet("font-size: 11px; color: #f87171; font-weight: 600;")
        else:
            self.delta_lbl.setText("● No change (quantity unchanged)")
            self.delta_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")

    def _save_stock(self):
        new_qty = self.qty_spin.value()
        if new_qty < 0:
            QMessageBox.warning(self, "Invalid Quantity", "Quantity in stock cannot be negative.")
            return

        try:
            self.saved_component = self.repository.update_component_stock(
                component_id=self.component.id,
                new_quantity=new_qty,
            )
            self.accept()
        except ValidationError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
        except ComponentNotFoundError as e:
            QMessageBox.critical(self, "Not Found", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update component stock: {e}")
