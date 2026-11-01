"""
Omnix UI - Dedicated Component Stock Thresholds Dialog
Allows editing of individual component Min Stock and Target Stock thresholds (Option B).
"""

from typing import Optional, Any
from PyQt6.QtCore import Qt
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


class ComponentThresholdDialog(QDialog):
    """
    Focused dialog for editing independent Min Stock and Target Stock thresholds
    for an individual component.
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
        self.setWindowTitle(f"Stock Thresholds — {mfr_name} {mpn_name}")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMinimumHeight(420)

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
                padding: 4px 34px 4px 14px;
                min-height: 24px;
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
                font-size: 11px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QToolButton:pressed {
                background-color: #0284c7;
                color: #ffffff;
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

        # 1. Header Card: Component Identity & Current Stock
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

        title_lbl = QLabel("🎯 Component Stock Thresholds")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)

        mfr = self.component.manufacturer or "Unknown Manufacturer"
        mpn = self.component.mpn or "Unknown MPN"
        comp_hdr = QLabel(f"<b>{mfr}</b> &nbsp;|&nbsp; <b>{mpn}</b>")
        comp_hdr.setTextFormat(Qt.TextFormat.RichText)
        comp_hdr.setStyleSheet("font-size: 13px; color: #f8fafc;")
        hdr_layout.addWidget(comp_hdr)

        cat = self.component.category or "-"
        tech = self.component.type_technology or "-"
        val = self.component.value or "-"
        fp = self.component.footprint or "-"
        sub_info = f"{cat} &nbsp;•&nbsp; {tech} &nbsp;•&nbsp; Value: {val} &nbsp;•&nbsp; Package: {fp}"
        sub_lbl = QLabel(sub_info)
        sub_lbl.setTextFormat(Qt.TextFormat.RichText)
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(sub_lbl)

        curr_stock = int(self.component.quantity_in_stock or 0)
        stk_lbl = QLabel(f"Physical Stock On-Hand: <b>{curr_stock}</b> units")
        stk_lbl.setTextFormat(Qt.TextFormat.RichText)
        stk_lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 4px;
                padding: 4px 8px;
                color: #34d399;
                font-size: 12px;
            }
        """)
        hdr_layout.addWidget(stk_lbl)

        main_layout.addWidget(header_frame)

        # 2. Threshold Controls Form
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(14)

        # Min Stock
        min_lbl = QLabel("Minimum Stock Threshold (Reorder point):")
        min_lbl.setStyleSheet("font-weight: bold; color: #cbd5e1; font-size: 12px;")
        form_layout.addWidget(min_lbl)

        min_row = QHBoxLayout()
        min_row.setSpacing(8)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 10000000)
        self.min_spin.setValue(int(getattr(self.component, "min_stock", 0) or 0))
        self.min_spin.setFixedHeight(34)
        self.min_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.min_spin.valueChanged.connect(self._on_threshold_changed)
        min_row.addWidget(self.min_spin, 1)

        for delta in [-10, -1, +1, +10]:
            btn = QToolButton()
            btn.setText(f"{delta:+d}")
            btn.setFixedSize(38, 34)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_spin(self.min_spin, d))
            min_row.addWidget(btn)

        form_layout.addLayout(min_row)

        # Target Stock
        tgt_lbl = QLabel("Target Stock Threshold (Replenish quantity target):")
        tgt_lbl.setStyleSheet("font-weight: bold; color: #cbd5e1; font-size: 12px;")
        form_layout.addWidget(tgt_lbl)

        tgt_row = QHBoxLayout()
        tgt_row.setSpacing(8)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(0, 10000000)
        self.target_spin.setValue(int(getattr(self.component, "target_stock", 0) or 0))
        self.target_spin.setFixedHeight(34)
        self.target_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.target_spin.valueChanged.connect(self._on_threshold_changed)
        tgt_row.addWidget(self.target_spin, 1)

        for delta in [-10, -1, +1, +10]:
            btn = QToolButton()
            btn.setText(f"{delta:+d}")
            btn.setFixedSize(38, 34)
            btn.clicked.connect(lambda checked, d=delta: self._adjust_spin(self.target_spin, d))
            tgt_row.addWidget(btn)

        form_layout.addLayout(tgt_row)

        # 3. Live Status & Validation Banner
        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        form_layout.addWidget(self.status_banner)

        main_layout.addWidget(form_frame)

        main_layout.addStretch()

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(90, 34)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                color: #cbd5e1;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Thresholds")
        self.save_btn.setFixedHeight(34)
        self.save_btn.setMinimumWidth(130)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                border-color: #334155;
                color: #64748b;
            }
        """)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

        self._on_threshold_changed()

    def _adjust_spin(self, spin: QSpinBox, delta: int):
        new_val = max(0, spin.value() + delta)
        spin.setValue(new_val)

    def _on_threshold_changed(self):
        min_val = self.min_spin.value()
        tgt_val = self.target_spin.value()
        curr_stock = int(self.component.quantity_in_stock or 0)

        if tgt_val < min_val:
            self.status_banner.setText(
                f"⚠️ Invalid: Target Stock ({tgt_val}) cannot be less than Min Stock ({min_val})."
            )
            self.status_banner.setStyleSheet("""
                QLabel {
                    background-color: rgba(239, 68, 68, 0.15);
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    padding: 8px;
                    color: #f87171;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
            self.save_btn.setEnabled(False)
            return

        self.save_btn.setEnabled(True)

        if min_val > 0 and curr_stock < min_val:
            needed = tgt_val - curr_stock
            self.status_banner.setText(
                f"🔴 Low Stock: On-hand quantity ({curr_stock}) is below Min Stock ({min_val}). "
                f"Replenishment needed: {needed} units."
            )
            self.status_banner.setStyleSheet("""
                QLabel {
                    background-color: rgba(248, 113, 113, 0.15);
                    border: 1px solid rgba(248, 113, 113, 0.4);
                    border-radius: 4px;
                    padding: 8px;
                    color: #fca5a5;
                    font-size: 11px;
                }
            """)
        elif min_val > 0:
            self.status_banner.setText(
                f"🟢 Normal: On-hand quantity ({curr_stock}) meets or exceeds Min Stock ({min_val})."
            )
            self.status_banner.setStyleSheet("""
                QLabel {
                    background-color: rgba(16, 185, 129, 0.12);
                    border: 1px solid rgba(16, 185, 129, 0.3);
                    border-radius: 4px;
                    padding: 8px;
                    color: #34d399;
                    font-size: 11px;
                }
            """)
        else:
            self.status_banner.setText(
                "⚪ Thresholds Disabled: Min Stock is 0 (Component will not trigger replenishment)."
            )
            self.status_banner.setStyleSheet("""
                QLabel {
                    background-color: rgba(100, 116, 139, 0.15);
                    border: 1px solid rgba(100, 116, 139, 0.3);
                    border-radius: 4px;
                    padding: 8px;
                    color: #94a3b8;
                    font-size: 11px;
                }
            """)

    def _on_save(self):
        min_val = self.min_spin.value()
        tgt_val = self.target_spin.value()

        if tgt_val < min_val:
            QMessageBox.warning(
                self,
                "Invalid Thresholds",
                f"Target Stock ({tgt_val}) cannot be less than Min Stock ({min_val}).",
            )
            return

        try:
            self.saved_component = self.repository.update_component_thresholds(
                self.component.id, min_val, tgt_val
            )
            self.accept()
        except ValidationError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
        except ComponentNotFoundError as e:
            QMessageBox.critical(self, "Component Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Thresholds", f"Failed to save component thresholds: {e}")
