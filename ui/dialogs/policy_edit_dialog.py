"""
Omnix UI — Stock Policy Threshold Edit Dialog
Governing Document: Phase 1 Refinement Specification

Modal editing interface for updating Min Stock and Target Stock thresholds
for a selected StockPolicyGroup. Validates thresholds, persists them via
StockPolicyWriter to the underlying workbook, and ensures proper feedback.
"""

import os
from typing import Optional, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QPen, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QAbstractSpinBox,
    QToolButton,
    QPushButton,
    QFrame,
    QMessageBox,
)

from core.inventory.models import StockPolicyGroup
from core.inventory.updater import StockPolicyWriter


class PolicySaveWorker(QThread):
    """
    Background worker for executing StockPolicyWriter Excel COM operations
    without blocking the Qt GUI thread, allowing the Save Changes button to animate.
    """
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        writer: StockPolicyWriter,
        workbook_path: str,
        group_key: str,
        min_stock: int,
        target_stock: int,
    ):
        super().__init__()
        self.writer = writer
        self.workbook_path = workbook_path
        self.group_key = group_key
        self.min_stock = min_stock
        self.target_stock = target_stock

    def run(self):
        try:
            success, message = self.writer.update_policy(
                workbook_path=self.workbook_path,
                group_key=self.group_key,
                min_stock=self.min_stock,
                target_stock=self.target_stock,
            )
        except Exception as e:
            success, message = False, f"Unexpected error while writing stock policy: {e}"
        self.finished.emit(success, message)


class PolicyEditDialog(QDialog):
    """
    Compact, readable modal dialog for editing Min Stock and Target Stock thresholds.
    Centered relative to the application window.
    """

    def __init__(
        self,
        group: StockPolicyGroup,
        inventory_path: str = "",
        parent: Optional[QWidget] = None,
        writer: Optional[StockPolicyWriter] = None,
        repository: Optional[Any] = None,
        read_only: Optional[bool] = None,
    ):
        super().__init__(parent)
        self.group = group
        self.inventory_path = inventory_path
        self.writer = writer or StockPolicyWriter()
        self.repository = repository

        # In Option B, if group contains physical components, individual components own thresholds;
        # group-level threshold editing is disabled to prevent overwriting component thresholds.
        if read_only is not None:
            self.is_read_only = bool(read_only)
        else:
            self.is_read_only = bool(self.repository is not None and getattr(self.group, "products", None))

        title = "Stock Policy Thresholds (Read-Only Aggregate)" if self.is_read_only else "Edit Stock Policy Thresholds"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumHeight(380)

        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)

        self._is_saving = False
        self._save_worker: Optional[PolicySaveWorker] = None
        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(60)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)

        # Ensure dialog is styled consistently with dark UI theme
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
                padding: 6px 10px;
                font-family: 'Consolas', monospace;
                font-size: 13px;
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
        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)

        # 1. Header Card with Group Identity
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        hdr_layout = QVBoxLayout(header_frame)
        hdr_layout.setContentsMargins(12, 10, 12, 10)
        hdr_layout.setSpacing(6)

        title_text = "Stock Policy Thresholds (Component-Level Aggregate)" if self.is_read_only else "Stock Policy Thresholds"
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)

        # Descriptive identity string
        identity_str = f"<b>{self.group.category}</b> &nbsp;|&nbsp; {self.group.type_technology} &nbsp;|&nbsp; <b>{self.group.value}</b> &nbsp;|&nbsp; {self.group.package} &nbsp;|&nbsp; {self.group.footprint}"
        comp_lbl = QLabel(identity_str)
        comp_lbl.setTextFormat(Qt.TextFormat.RichText)
        comp_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(comp_lbl)

        # Current stock info pill
        stk_val = f"{self.group.current_stock}" if self.group.current_stock is not None else "Missing"
        stk_lbl = QLabel(f"Current Stock On-Hand: <b>{stk_val}</b> units")
        stk_lbl.setTextFormat(Qt.TextFormat.RichText)
        stk_lbl.setStyleSheet("font-size: 11px; color: #34d399;")
        hdr_layout.addWidget(stk_lbl)

        main_layout.addWidget(header_frame)

        # 2. Form Fields for Min Stock and Target Stock
        form_frame = QFrame()
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(14)

        # Min Stock Row
        min_layout = QVBoxLayout()
        min_layout.setSpacing(4)
        min_title = QLabel("Min Stock (Minimum Safe Threshold):")
        min_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e8f0;")

        self.min_spin = QSpinBox()
        self.min_spin.setFont(QFont("Consolas", 10))
        self.min_spin.setRange(0, 1000000)
        self.min_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.min_spin.setFixedHeight(36)
        self.min_spin.setValue(int(self.group.min_stock) if self.group.min_stock is not None else 0)
        self.min_spin.wheelEvent = lambda event: event.ignore()
        self.min_spin.valueChanged.connect(self._validate_inputs_inline)

        self.min_up_btn = QToolButton()
        self.min_up_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.min_up_btn.setFixedSize(28, 17)
        self.min_up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.min_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_up_btn.setToolTip("Increase Min Stock")
        self.min_up_btn.setAccessibleName("Increase Min Stock")
        self.min_up_btn.setAutoRepeat(True)
        self.min_up_btn.setAutoRepeatDelay(400)
        self.min_up_btn.setAutoRepeatInterval(100)
        self.min_up_btn.clicked.connect(self.min_spin.stepUp)

        self.min_down_btn = QToolButton()
        self.min_down_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.min_down_btn.setFixedSize(28, 17)
        self.min_down_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.min_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_down_btn.setToolTip("Decrease Min Stock")
        self.min_down_btn.setAccessibleName("Decrease Min Stock")
        self.min_down_btn.setAutoRepeat(True)
        self.min_down_btn.setAutoRepeatDelay(400)
        self.min_down_btn.setAutoRepeatInterval(100)
        self.min_down_btn.clicked.connect(self.min_spin.stepDown)

        min_row_layout = QHBoxLayout()
        min_row_layout.setSpacing(6)
        min_row_layout.setContentsMargins(0, 0, 0, 0)
        min_row_layout.addWidget(self.min_spin, 1)

        min_btn_layout = QVBoxLayout()
        min_btn_layout.setSpacing(2)
        min_btn_layout.setContentsMargins(0, 0, 0, 0)
        min_btn_layout.addWidget(self.min_up_btn)
        min_btn_layout.addWidget(self.min_down_btn)
        min_row_layout.addLayout(min_btn_layout)

        min_layout.addWidget(min_title)
        min_layout.addLayout(min_row_layout)
        form_layout.addLayout(min_layout)

        # Target Stock Row
        target_layout = QVBoxLayout()
        target_layout.setSpacing(4)
        target_title = QLabel("Target Stock (Reorder Target Level):")
        target_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e8f0;")

        self.target_spin = QSpinBox()
        self.target_spin.setFont(QFont("Consolas", 10))
        self.target_spin.setRange(0, 1000000)
        self.target_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.target_spin.setFixedHeight(36)
        self.target_spin.setValue(int(self.group.target_stock) if self.group.target_stock is not None else 0)
        self.target_spin.wheelEvent = lambda event: event.ignore()
        self.target_spin.valueChanged.connect(self._validate_inputs_inline)

        self.target_up_btn = QToolButton()
        self.target_up_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.target_up_btn.setFixedSize(28, 17)
        self.target_up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.target_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_up_btn.setToolTip("Increase Target Stock")
        self.target_up_btn.setAccessibleName("Increase Target Stock")
        self.target_up_btn.setAutoRepeat(True)
        self.target_up_btn.setAutoRepeatDelay(400)
        self.target_up_btn.setAutoRepeatInterval(100)
        self.target_up_btn.clicked.connect(self.target_spin.stepUp)

        self.target_down_btn = QToolButton()
        self.target_down_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.target_down_btn.setFixedSize(28, 17)
        self.target_down_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.target_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_down_btn.setToolTip("Decrease Target Stock")
        self.target_down_btn.setAccessibleName("Decrease Target Stock")
        self.target_down_btn.setAutoRepeat(True)
        self.target_down_btn.setAutoRepeatDelay(400)
        self.target_down_btn.setAutoRepeatInterval(100)
        self.target_down_btn.clicked.connect(self.target_spin.stepDown)

        target_row_layout = QHBoxLayout()
        target_row_layout.setSpacing(6)
        target_row_layout.setContentsMargins(0, 0, 0, 0)
        target_row_layout.addWidget(self.target_spin, 1)

        target_btn_layout = QVBoxLayout()
        target_btn_layout.setSpacing(2)
        target_btn_layout.setContentsMargins(0, 0, 0, 0)
        target_btn_layout.addWidget(self.target_up_btn)
        target_btn_layout.addWidget(self.target_down_btn)
        target_row_layout.addLayout(target_btn_layout)

        target_layout.addWidget(target_title)
        target_layout.addLayout(target_row_layout)
        form_layout.addLayout(target_layout)

        main_layout.addWidget(form_frame)

        if self.is_read_only:
            self.min_spin.setReadOnly(True)
            self.min_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.min_up_btn.setEnabled(False)
            self.min_down_btn.setEnabled(False)
            self.target_spin.setReadOnly(True)
            self.target_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.target_up_btn.setEnabled(False)
            self.target_down_btn.setEnabled(False)

            prod_cnt = len(self.group.products) if getattr(self.group, "products", None) else 0
            readonly_notice = QLabel(
                f"ℹ️ <b>Option B Component-Level Inventory:</b> Thresholds belong to individual physical components. "
                f"The values shown above are the aggregate sum of all {prod_cnt} component(s) in this group.<br>"
                "To edit stock thresholds, double-click a component in the <b>Component Inventory</b> tab."
            )
            readonly_notice.setTextFormat(Qt.TextFormat.RichText)
            readonly_notice.setStyleSheet(
                "font-size: 11px; color: #38bdf8; background-color: #0c2340; "
                "border: 1px solid #1e3a8a; border-radius: 6px; padding: 10px;"
            )
            readonly_notice.setWordWrap(True)
            main_layout.addWidget(readonly_notice)

        # 3. Dynamic Validation Feedback Area
        self.validation_lbl = QLabel("")
        self.validation_lbl.setWordWrap(True)
        self.validation_lbl.setStyleSheet("font-size: 11px; color: #f87171; min-height: 28px;")
        main_layout.addWidget(self.validation_lbl)

        # 4. Action Buttons (Cancel / Save)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Close" if self.is_read_only else "Cancel")
        self.cancel_btn.setFixedSize(110 if self.is_read_only else 100, 36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setFixedSize(140, 36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #0369a1;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #475569;
                border-color: #334155;
            }
            QPushButton:disabled[saving="true"] {
                background-color: #0369a1;
                color: #ffffff;
                border: 1px solid #0284c7;
            }
        """)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.save_btn)
        if self.is_read_only:
            self.save_btn.setVisible(False)

        main_layout.addLayout(btn_layout)

        # Initial validation check
        self._validate_inputs_inline()

    def _render_spinner_icon(self, angle: int) -> QIcon:
        """Render a subtle rotating circular progress indicator for the save button."""
        size = 14
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Subtle translucent track ring
        track_pen = QPen(QColor(255, 255, 255, 55), 2)
        painter.setPen(track_pen)
        painter.drawEllipse(1, 1, size - 2, size - 2)

        # Rotating foreground arc in theme cyan
        arc_pen = QPen(QColor("#38bdf8"), 2)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        start_angle_16 = int(-angle * 16)
        span_angle_16 = int(120 * 16)
        painter.drawArc(1, 1, size - 2, size - 2, start_angle_16, span_angle_16)
        painter.end()

        icon = QIcon()
        icon.addPixmap(pixmap, QIcon.Mode.Normal)
        icon.addPixmap(pixmap, QIcon.Mode.Disabled)
        return icon

    def _on_spinner_tick(self):
        """Advance rotating progress indicator angle and update button icon."""
        self._spinner_angle = (self._spinner_angle + 30) % 360
        self.save_btn.setIcon(self._render_spinner_icon(self._spinner_angle))

    def _validate_inputs_inline(self):
        """Validate thresholds dynamically as user changes spinbox values."""
        min_val = self.min_spin.value()
        tgt_val = self.target_spin.value()

        if tgt_val < min_val:
            self.validation_lbl.setText(
                f"Target Stock ({tgt_val}) must be greater than or equal to Min Stock ({min_val}). "
                "Please increase Target Stock or reduce Min Stock."
            )
            self.save_btn.setEnabled(False)
        else:
            self.validation_lbl.setText("")
            self.save_btn.setEnabled(True)

    def _on_save_clicked(self):
        """Perform final validation and launch background Excel save with animated button state."""
        if self._is_saving or self.is_read_only:
            return

        min_val = self.min_spin.value()
        tgt_val = self.target_spin.value()

        if tgt_val < min_val:
            QMessageBox.warning(
                self,
                "Invalid Thresholds",
                f"Target Stock ({tgt_val}) cannot be less than Min Stock ({min_val}).\n\n"
                "In order to maintain valid stock policies, Target Stock must be >= Min Stock >= 0.\n"
                "Please adjust the values before saving.",
            )
            return

        # Direct SQLite repository persistence
        if self.repository is not None and hasattr(self.repository, "set_policy"):
            try:
                self.repository.set_policy(
                    group_key=self.group.group_key,
                    min_stock=min_val,
                    target_stock=tgt_val,
                    category=self.group.category,
                    type_technology=self.group.type_technology,
                    value=self.group.value,
                    package=self.group.package,
                    footprint=self.group.footprint,
                    description=self.group.description,
                )
                self.accept()
                return
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Database Error",
                    f"Failed to update stock policy thresholds in SQLite database:\n\n{e}",
                )
                return

        # 1. Enter animated saving state on the Save Changes button
        self._is_saving = True
        self.save_btn.setProperty("saving", "true")
        self.save_btn.setEnabled(False)
        self.save_btn.setText("Saving...")
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)

        # Disable form controls while save operation is in flight to prevent duplicate submissions
        self.cancel_btn.setEnabled(False)
        self.min_spin.setEnabled(False)
        self.target_spin.setEnabled(False)
        self.min_up_btn.setEnabled(False)
        self.min_down_btn.setEnabled(False)
        self.target_up_btn.setEnabled(False)
        self.target_down_btn.setEnabled(False)

        # Start rotating spinner animation
        self._spinner_angle = 0
        self.save_btn.setIcon(self._render_spinner_icon(self._spinner_angle))
        self._spinner_timer.start(60)

        # 2. Launch background worker thread for Excel COM operation
        self._save_worker = PolicySaveWorker(
            writer=self.writer,
            workbook_path=self.inventory_path,
            group_key=self.group.group_key,
            min_stock=min_val,
            target_stock=tgt_val,
        )
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.start()

    def _on_save_finished(self, success: bool, message: str):
        """Handle save completion on the main GUI thread."""
        self._spinner_timer.stop()
        self._is_saving = False

        if success:
            # Edits persisted successfully; close dialog with Accepted
            self.accept()
            return

        # Failure: restore original button state and re-enable form controls
        self.save_btn.setProperty("saving", "false")
        self.save_btn.setIcon(QIcon())
        self.save_btn.setText("Save Changes")
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)

        self.cancel_btn.setEnabled(True)
        self.min_spin.setEnabled(True)
        self.target_spin.setEnabled(True)
        self.min_up_btn.setEnabled(True)
        self.min_down_btn.setEnabled(True)
        self.target_up_btn.setEnabled(True)
        self.target_down_btn.setEnabled(True)
        self._validate_inputs_inline()

        # Display error message preserving existing behavior
        QMessageBox.critical(
            self,
            "Save Failed",
            f"Could not update stock policy in '{os.path.basename(self.inventory_path)}':\n\n"
            f"{message}\n\n"
            "No changes have been saved to disk.",
        )

    def reject(self):
        """Prevent closing while save operation is in flight."""
        if self._is_saving:
            return
        super().reject()

    def closeEvent(self, event):
        """Prevent closing while save operation is in flight."""
        if self._is_saving:
            event.ignore()
            return
        super().closeEvent(event)

    def done(self, r):
        if hasattr(self, "_spinner_timer") and self._spinner_timer.isActive():
            self._spinner_timer.stop()
        if hasattr(self, "_save_worker") and self._save_worker and self._save_worker.isRunning():
            self._save_worker.wait(3000)
        super().done(r)
