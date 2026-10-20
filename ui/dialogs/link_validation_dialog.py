"""
Omnix UI — Supplier Link Identity & Availability Validation Dialog
Governing Requirement: Mode A Deterministic Component Link Validation
"""

import webbrowser
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
    QProgressBar,
    QFrame,
    QMessageBox,
)

from ui.dark_frame import apply_dark_window_frame
from core.procurement.link_validator import (
    LinkValidator,
    LinkValidationItem,
    LinkValidationResult,
    LinkValidationStatus,
)


class LinkValidationWorker(QThread):
    """Background worker thread executing deterministic link validation without blocking Qt event loop."""
    progress_signal = pyqtSignal(int, int, object)  # current, total, LinkValidationResult
    finished_signal = pyqtSignal(list)               # List[LinkValidationResult]

    def __init__(self, items: List[LinkValidationItem], validator: Optional[LinkValidator] = None):
        super().__init__()
        self.items = items
        self.validator = validator or LinkValidator()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        results: List[LinkValidationResult] = []
        total = len(self.items)

        def on_progress(cur: int, tot: int, res: LinkValidationResult):
            if not self._is_cancelled:
                self.progress_signal.emit(cur, tot, res)

        for idx, it in enumerate(self.items, start=1):
            if self._is_cancelled:
                break
            res = self.validator.validate_item(it)
            results.append(res)
            on_progress(idx, total, res)

        self.finished_signal.emit(results)


class LinkValidationDialog(QDialog):
    """
    Interactive modal dialog performing non-blocking validation of supplier links.
    Shows real-time status badges, extracted identity, and highlights mismatches.
    """

    def __init__(
        self,
        items: List[LinkValidationItem],
        validator: Optional[LinkValidator] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.items = items
        self.validator = validator or LinkValidator()
        self.worker: Optional[LinkValidationWorker] = None
        self.results: List[LinkValidationResult] = []

        self.setWindowTitle("Supplier Link Validation & Component Verification")
        self.resize(1020, 620)
        self.setStyleSheet("background-color: #0b101b; color: #f8fafc;")
        apply_dark_window_frame(self)

        self._init_ui()
        self._start_validation()

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Title
        title_lbl = QLabel("🔍 Supplier Link Verification & Identity Audit")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        # Subtitle
        desc_lbl = QLabel(
            "Verifies remote supplier product URLs, checks HTTP reachability, and extracts "
            "technical specifications to confirm exact match with registered component MPN and Manufacturer."
        )
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Summary Pills Frame
        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet("""
            QFrame {
                background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        sum_layout = QHBoxLayout(self.summary_frame)
        sum_layout.setContentsMargins(0, 0, 0, 0)
        sum_layout.setSpacing(10)

        self.pill_total = QLabel(f"Total Links: {len(self.items)}")
        self.pill_total.setStyleSheet("color: #cbd5e1; font-weight: bold; font-size: 12px;")
        sum_layout.addWidget(self.pill_total)

        self.pill_verified = QLabel("✅ Verified: 0")
        self.pill_verified.setStyleSheet("color: #34d399; font-weight: bold; font-size: 12px;")
        sum_layout.addWidget(self.pill_verified)

        self.pill_mismatch = QLabel("❌ Mismatch: 0")
        self.pill_mismatch.setStyleSheet("color: #f87171; font-weight: bold; font-size: 12px;")
        sum_layout.addWidget(self.pill_mismatch)

        self.pill_unverifiable = QLabel("⚠️ Not Verifiable: 0")
        self.pill_unverifiable.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
        sum_layout.addWidget(self.pill_unverifiable)

        self.pill_error = QLabel("⛔ Errors: 0")
        self.pill_error.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 12px;")
        sum_layout.addWidget(self.pill_error)

        sum_layout.addStretch()
        layout.addWidget(self.summary_frame)

        # Progress Bar & Label
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(len(self.items), 1))
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready to validate links...")
        self.status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px;")
        layout.addWidget(self.status_lbl)

        # Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Component (MFR / MPN)", "Vendor", "Supplier Store URL", "Validation Status", "Remote Extracted Spec", "Details"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(4, 200)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.table, 1)

        # Pre-populate table with initial pending rows
        self.table.setRowCount(len(self.items))
        font_code = QFont("Consolas", 9)
        font_txt = QFont("Segoe UI", 9)
        for r_idx, it in enumerate(self.items):
            mfr_mpn = f"{it.manufacturer} {it.mpn}".strip() or it.component_name
            it0 = QTableWidgetItem(mfr_mpn)
            it0.setFont(font_code)
            self.table.setItem(r_idx, 0, it0)

            v_text = it.vendor_label or it.vendor_id or "Vendor"
            it1 = QTableWidgetItem(v_text)
            it1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r_idx, 1, it1)

            it2 = QTableWidgetItem(it.url)
            it2.setFont(font_code)
            it2.setForeground(QColor("#38bdf8"))
            it2.setToolTip(f"Double-click to open in browser:\n{it.url}")
            self.table.setItem(r_idx, 2, it2)

            it3 = QTableWidgetItem("⏳ Pending...")
            it3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it3.setForeground(QColor("#94a3b8"))
            self.table.setItem(r_idx, 3, it3)

            it4 = QTableWidgetItem("-")
            it4.setFont(font_code)
            self.table.setItem(r_idx, 4, it4)

            it5 = QTableWidgetItem("Queued for validation")
            it5.setFont(font_txt)
            self.table.setItem(r_idx, 5, it5)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.revalidate_btn = QPushButton("🔄 Re-run All")
        self.revalidate_btn.setObjectName("secondaryBtn")
        self.revalidate_btn.clicked.connect(self._start_validation)
        btn_layout.addWidget(self.revalidate_btn)

        self.cancel_btn = QPushButton("⏹ Cancel Validation")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self._cancel_validation)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("primaryBtn")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _start_validation(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)

        self.results.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.cancel_btn.setEnabled(True)
        self.status_lbl.setText("Connecting and validating supplier links...")

        self.worker = LinkValidationWorker(self.items, validator=self.validator)
        self.worker.progress_signal.connect(self._on_worker_progress)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()

    def _cancel_validation(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_lbl.setText("Validation cancelled by user.")
            self.cancel_btn.setEnabled(False)

    def _on_worker_progress(self, current: int, total: int, res: LinkValidationResult):
        self.progress_bar.setValue(current)
        row = current - 1
        self.status_lbl.setText(f"Validated ({current}/{total}): {res.item.component_name or res.item.mpn}")

        # Status item
        status_txt = res.status.value
        status_item = self.table.item(row, 3)
        if not status_item:
            status_item = QTableWidgetItem()
            self.table.setItem(row, 3, status_item)

        font_bold = QFont("Segoe UI", 9, QFont.Weight.Bold)
        status_item.setFont(font_bold)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if res.status == LinkValidationStatus.VERIFIED_MATCH:
            status_item.setText("✅ VERIFIED")
            status_item.setForeground(QColor("#34d399"))
        elif res.status == LinkValidationStatus.IDENTITY_MISMATCH:
            status_item.setText("❌ MISMATCH")
            status_item.setForeground(QColor("#f87171"))
        elif res.status == LinkValidationStatus.NOT_VERIFIABLE:
            status_item.setText("⚠️ NOT VERIFIABLE")
            status_item.setForeground(QColor("#fbbf24"))
        elif res.status == LinkValidationStatus.UNSUPPORTED_VENDOR:
            status_item.setText("UNSUPPORTED")
            status_item.setForeground(QColor("#94a3b8"))
        elif res.status == LinkValidationStatus.INVALID_URL:
            status_item.setText("INVALID URL")
            status_item.setForeground(QColor("#f87171"))
        else:
            status_item.setText("HTTP ERROR")
            status_item.setForeground(QColor("#f87171"))

        # Remote Extracted spec
        spec_parts = []
        if res.extracted_mfr:
            spec_parts.append(res.extracted_mfr)
        if res.extracted_mpn:
            spec_parts.append(res.extracted_mpn)
        spec_text = " / ".join(spec_parts) if spec_parts else "-"
        self.table.setItem(row, 4, QTableWidgetItem(spec_text))

        # Details
        self.table.setItem(row, 5, QTableWidgetItem(res.message))

        self._update_pills()

    def _on_worker_finished(self, results: List[LinkValidationResult]):
        self.results = results
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(f"Completed validation of {len(results)} links.")
        self._update_pills()

    def _update_pills(self):
        verified = sum(1 for r in range(self.table.rowCount()) if "VERIFIED" in (self.table.item(r, 3).text() if self.table.item(r, 3) else ""))
        mismatch = sum(1 for r in range(self.table.rowCount()) if "MISMATCH" in (self.table.item(r, 3).text() if self.table.item(r, 3) else ""))
        unverifiable = sum(1 for r in range(self.table.rowCount()) if "NOT VERIFIABLE" in (self.table.item(r, 3).text() if self.table.item(r, 3) else ""))
        errors = sum(1 for r in range(self.table.rowCount()) if any(e in (self.table.item(r, 3).text() if self.table.item(r, 3) else "") for e in ["ERROR", "INVALID", "UNSUPPORTED"]))

        self.pill_verified.setText(f"✅ Verified: {verified}")
        self.pill_mismatch.setText(f"❌ Mismatch: {mismatch}")
        self.pill_unverifiable.setText(f"⚠️ Not Verifiable: {unverifiable}")
        self.pill_error.setText(f"⛔ Errors: {errors}")

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        url_it = self.table.item(row, 2)
        if url_it:
            url = url_it.text().strip()
            if url.startswith("http://") or url.startswith("https://"):
                webbrowser.open(url)
