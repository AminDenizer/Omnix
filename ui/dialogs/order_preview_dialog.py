"""
Omnix UI — Multi-Vendor Order Preview & Candidate Selection Dialog
Governing GAP: GAP-07 (Multi-Candidate Comparison & Alternative Selection) & Mode A Fast Confirmation
Reuses UniversalProcurementOrchestrator, CandidateEvaluation, ProcurementBridge, and GAP-13 Delta Synchronization.
"""

import math
import os
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import CartMutationResult
from core.procurement.bridge import ProcurementBridge
from core.procurement.vendor_links import parse_vendor_links
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    ProcurementMode,
    ProcurementRequest,
    RequestProcurementResult,
    VendorProcurementCandidate,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry, default_registry
from core.procurement.reporting import (
    ProcurementCSVExporter,
    ProcurementPDFExporter,
    ProcurementReportBuilder,
    ProcurementXLSXExporter,
)
from settings_manager import settings
from ui.dialogs.settings_dialog import SettingsDialog


class PlanDiscoveryWorkerThread(QThread):
    """Background worker thread to gather and evaluate vendor candidates asynchronously without freezing GUI."""

    progress_signal = pyqtSignal(int, int, str, str)  # current, total, part_name, msg
    finished_signal = pyqtSignal(object)  # BOMProcurementPlan

    def __init__(
        self,
        requests: List[ProcurementRequest],
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        vendor_ids: Optional[List[str]] = None,
    ):
        super().__init__()
        self.requests = requests
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator()
        self.vendor_ids = vendor_ids

    def run(self):
        try:
            def on_progress(cur: int, total: int, part: str, msg: str):
                self.progress_signal.emit(cur, total, part, msg)

            plan = self.orchestrator.build_plan(
                self.requests,
                vendor_ids=self.vendor_ids,
                progress_callback=on_progress,
            )
            self.finished_signal.emit(plan)
        except Exception:
            empty_plan = BOMProcurementPlan(results=[])
            self.finished_signal.emit(empty_plan)


class OrderWorkerThread(QThread):
    """
    Background worker thread to execute procurement staging:
    - Mode A: Batch staging directly via ProcurementBridge and vendor adapters.
    - Mode B / GAP-07: Staging selected candidate evaluations via UniversalProcurementOrchestrator.
    """

    progress_signal = pyqtSignal(int, int, str, int, str)  # current, total, part_name, qty, msg
    finished_signal = pyqtSignal(dict)

    def __init__(
        self,
        results: Optional[List[RequestProcurementResult]] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        registry: Optional[VendorRegistry] = None,
    ):
        super().__init__()
        self.results = results or []
        self.items = items or []
        self.registry = registry or VendorRegistry.get_default_registry()
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator(registry=self.registry)

    def run(self):
        if self.items:
            self._run_direct_items()
        else:
            self._run_procurement_results()

    def _get_vendor_name(self, vid: str) -> str:
        if not vid:
            return "Vendor"
        if hasattr(self.registry, "get_vendor_name"):
            return self.registry.get_vendor_name(vid)
        return vid.replace("vendor_", "").title()

    def _run_direct_items(self):
        """Execute direct shortage ordering via unified ProcurementBridge."""
        def on_progress(current: int, total: int, part_name: str, qty: int, msg: str):
            self.progress_signal.emit(current, total, part_name, qty, msg)

        res = ProcurementBridge.execute_staged_procurement_batch(
            items=self.items,
            progress_callback=on_progress,
            registry=self.registry,
            orchestrator=self.orchestrator,
        )
        self.finished_signal.emit(res)

    def _run_procurement_results(self):
        """Execute Mode B / GAP-07 staging via orchestrator."""
        orderable_results = [r for r in self.results if r.selected_evaluation is not None and r.selected_evaluation.is_eligible]

        if not orderable_results:
            self.finished_signal.emit({
                "success": True,
                "message": "No eligible candidate items selected for staging.",
                "successful_count": 0,
                "failed_count": 0,
                "noop_count": 0,
                "staged_count": 0,
                "results": [],
            })
            return

        successful_count = 0
        failed_count = 0
        noop_count = 0
        staged_count = 0
        results_log = []

        for idx, r in enumerate(orderable_results, start=1):
            p_name = r.request.part_number
            cand = r.selected_evaluation.candidate
            eff_qty = r.selected_evaluation.effective_quantity
            v_name = cand.vendor_id.replace("vendor_", "").title()

            self.progress_signal.emit(
                idx, len(orderable_results), p_name, eff_qty, f"Staging {eff_qty} pcs to {v_name}..."
            )

            try:
                stage_res: CartMutationResult = self.orchestrator.stage_candidate(
                    cand, eff_qty, sync_cart=True
                )
                if stage_res.success:
                    successful_count += 1
                    if stage_res.is_noop:
                        noop_count += 1
                        msg = f"Already satisfied in cart ({stage_res.initial_cart_qty}/{stage_res.target_qty} pcs)"
                    else:
                        staged_count += 1
                        msg = stage_res.raw_vendor_message or f"Added {stage_res.actual_quantity_staged} pcs"

                    r.status = "RESOLVED"
                    results_log.append({
                        "part": p_name,
                        "status": "SUCCESS",
                        "qty": stage_res.actual_quantity_staged,
                        "msg": msg,
                        "vendor_id": cand.vendor_id,
                        "is_noop": stage_res.is_noop,
                    })
                    self.progress_signal.emit(idx, len(orderable_results), p_name, stage_res.actual_quantity_staged, msg)
                else:
                    failed_count += 1
                    msg = stage_res.raw_vendor_message or stage_res.error_category or "Staging failed"
                    results_log.append({
                        "part": p_name,
                        "status": "FAILED",
                        "qty": 0,
                        "msg": msg,
                        "vendor_id": cand.vendor_id,
                    })
                    self.progress_signal.emit(idx, len(orderable_results), p_name, 0, f"Failed: {msg}")
            except Exception as e:
                failed_count += 1
                err_msg = str(e)
                results_log.append({
                    "part": p_name,
                    "status": "FAILED",
                    "qty": 0,
                    "msg": err_msg,
                    "vendor_id": cand.vendor_id,
                })
                self.progress_signal.emit(idx, len(orderable_results), p_name, 0, f"Error: {err_msg}")

        overall_success = (failed_count == 0) and (successful_count > 0)
        self.finished_signal.emit({
            "success": overall_success,
            "message": f"Staging completed: {successful_count} succeeded ({noop_count} no-op), {failed_count} failed.",
            "successful_count": successful_count,
            "failed_count": failed_count,
            "noop_count": noop_count,
            "staged_count": staged_count,
            "results": results_log,
        })


class VendorSelectionDialog(QDialog):
    """
    Minimal dialog prompting the user to select which vendor to purchase from
    for components that have multiple valid supplier URLs (Mode A Case B).

    Guarantees:
    1. Shows human-readable vendor display names ("Lion Electronic", "Javan Electronic").
    2. Never exposes raw combined URL string as selection label.
    3. Presents only vendors with valid parsed URLs for that specific component.
    4. If cancelled, safely cancels procurement dispatch.
    5. Preserves user selection into item['selected_vendor_id'] and item['selected_url'].
    """

    def __init__(
        self,
        items_needing_selection: List[Dict[str, Any]],
        registry: Optional[VendorRegistry] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.items = items_needing_selection
        self.registry = registry or VendorRegistry.get_default_registry()

        self.setWindowTitle("Select Vendor — Multi-Link Components")
        self.resize(540, min(600, 200 + len(self.items) * 70))
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                color: #f8fafc;
                font-size: 13px;
                min-width: 180px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton#primaryBtn {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton#primaryBtn:hover { background-color: #10b981; }
            QPushButton#secondaryBtn {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #94a3b8;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton#secondaryBtn:hover { background-color: #334155; color: #f8fafc; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        header = QLabel("⚡ Select Vendor for Multi-Link Components")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(header)

        desc = QLabel(
            "The following component(s) have multiple supplier options configured. "
            "Please select which vendor to use for procurement dispatch:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc)

        self.combo_boxes: List[Tuple[Dict[str, Any], QComboBox]] = []

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 4, 0, 4)
        scroll_layout.setSpacing(10)

        for it in self.items:
            row_frame = QFrame()
            row_frame.setStyleSheet("""
                QFrame {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 6px 10px;
                }
            """)
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 6, 8, 6)

            p_name = it.get("part_name") or it.get("part_number") or it.get("designator") or "Component"
            needed = it.get("needed_qty") if it.get("needed_qty") is not None else it.get("shortage_qty", 1)
            info_lbl = QLabel(f"<b>{p_name}</b> &nbsp;<span style='color: #fbbf24;'>({needed} pcs)</span>")
            info_lbl.setTextFormat(Qt.TextFormat.RichText)
            row_layout.addWidget(info_lbl, 1)

            combo = QComboBox()
            vendor_links = it.get("vendor_links", {})
            for vid in sorted(vendor_links.keys()):
                disp_name = (
                    self.registry.get_vendor_name(vid)
                    if hasattr(self.registry, "get_vendor_name")
                    else vid.replace("vendor_", "").title()
                )
                combo.addItem(disp_name, vid)

            if it.get("selected_vendor_id"):
                idx = combo.findData(it["selected_vendor_id"])
                if idx >= 0:
                    combo.setCurrentIndex(idx)

            row_layout.addWidget(combo)
            scroll_layout.addWidget(row_frame)
            self.combo_boxes.append((it, combo))

        layout.addWidget(scroll_widget)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        confirm_btn = QPushButton("Confirm Selection")
        confirm_btn.setObjectName("primaryBtn")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_box.addWidget(confirm_btn)

        layout.addLayout(btn_box)

    def _on_confirm(self):
        for it, combo in self.combo_boxes:
            selected_vid = combo.currentData()
            vendor_links = it.get("vendor_links", {})
            if selected_vid in vendor_links:
                it["selected_vendor_id"] = selected_vid
                it["selected_url"] = vendor_links[selected_vid]
                it["vendor_id"] = selected_vid
                it["link"] = vendor_links[selected_vid]
        self.accept()


class OrderPreviewDialog(QDialog):
    """
    Unified Procurement & Order Confirmation Dialog supporting:
    1. Mode A (Database-Aware / Shortages): Instant high-contrast confirmation table (Image 2)
       with direct store link validation, non-blocking batch ordering, browser cart links,
       and atomic inventory update.
    2. Mode B (Turnkey Direct BOM / Plan): Master-Detail multi-candidate comparison table (GAP-07)
       with candidate switching, dynamic cost recalculation, and multi-format reporting (GAP-18).
    """

    def __init__(
        self,
        all_shortages: Optional[List[Dict[str, Any]]] = None,
        orderable_items: Optional[List[Dict[str, Any]]] = None,
        missing_db_items: Optional[List[Dict[str, Any]]] = None,
        plan: Optional[BOMProcurementPlan] = None,
        source_title: str = "Project BOM Shortages",
        inventory_loader=None,
        on_stock_updated=None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        async_discovery: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        items_in = all_shortages if all_shortages is not None else (orderable_items or [])
        self.all_shortages = items_in
        self.missing_db_items = missing_db_items or []
        self.source_title = source_title
        self.inventory_loader = inventory_loader
        self.on_stock_updated = on_stock_updated
        self.registry = registry or VendorRegistry.get_default_registry()
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator(registry=self.registry)
        self.async_discovery = async_discovery

        self.worker: Optional[OrderWorkerThread] = None
        self.discovery_worker: Optional[PlanDiscoveryWorkerThread] = None
        self.staging_results_log: Optional[List[Dict[str, Any]]] = None
        self._has_updated_inventory = False
        self.active_row_idx: Optional[int] = None

        # Determine if this is Mode B (pre-computed / multi-candidate plan) or Mode A (direct shortage confirmation)
        if plan is not None and len(plan.results) > 0:
            self.is_mode_b_preview = True
            self.plan = plan
            self.results = plan.results
        else:
            self.is_mode_b_preview = False
            self.plan = plan or BOMProcurementPlan(results=[])
            self.results = []

        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        if self.is_mode_b_preview:
            self.setWindowTitle(f"Procurement Preview & Multi-Candidate Selection — {source_title}")
            self.resize(1140, 720)
            self._init_mode_b_ui()
        else:
            self.setWindowTitle(f"Procurement & Order Confirmation — {source_title}")
            self.resize(980, 620)
            self._init_mode_a_ui()

        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)

    def showEvent(self, event):
        super().showEvent(event)
        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)

    # =========================================================================
    # MODE A: FAST DIRECT CONFIRMATION UI (IMAGE 2)
    # =========================================================================

    def _init_mode_a_ui(self):
        # Classify shortages
        self.lion_items: List[Dict[str, Any]] = []
        self.other_vendor_items: List[Dict[str, Any]] = []
        self.multi_vendor_items: List[Dict[str, Any]] = []
        self.external_items: List[Dict[str, Any]] = []
        self.blank_link_items: List[Dict[str, Any]] = []

        for it in self.all_shortages:
            link = str(it.get("link", "")).strip()
            raw_link = str(it.get("raw_link") or link).strip()

            parsed = parse_vendor_links(raw_link or link, registry=self.registry)
            if parsed.is_empty:
                self.blank_link_items.append(it)
                continue
            if not parsed.is_valid:
                self.external_items.append(it)
                continue

            if "vendor_links" not in it or not it["vendor_links"]:
                it["vendor_links"] = {vid: e.url for vid, e in parsed.links.items()}

            if parsed.count > 1:
                it["is_multi_vendor"] = True
                self.multi_vendor_items.append(it)
            elif parsed.count == 1:
                entry = parsed.get_single_entry()
                vid = entry.vendor_id
                it["vendor_id"] = vid
                it["selected_url"] = entry.url
                it["link"] = entry.url
                if self.registry.has_vendor(vid) and self.registry.is_vendor_enabled(vid):
                    if vid == "vendor_lion":
                        self.lion_items.append(it)
                    else:
                        self.other_vendor_items.append(it)
                else:
                    self.external_items.append(it)
            else:
                self.external_items.append(it)

        self.orderable_items = self.lion_items + self.other_vendor_items + self.multi_vendor_items
        self.invalid_items = self.external_items + self.blank_link_items

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Header Title
        title_lbl = QLabel(f"🛒 {self.source_title}")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        # Summary Subtitle
        summary_text = (
            f"<b>{len(self.orderable_items)}</b> of <b>{len(self.all_shortages)}</b> shortage items have valid vendor links ready for automated purchasing."
        )
        if self.invalid_items:
            summary_text += f" &nbsp; (❌ <b>{len(self.external_items)}</b> external non-registered links, ⚠️ <b>{len(self.blank_link_items)}</b> blank links)."

        desc_lbl = QLabel(summary_text)
        desc_lbl.setTextFormat(Qt.TextFormat.RichText)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Main Table of All Shortages (6 columns matching Image 2)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Part / Designator", "Part Number / Description", "Current Stock", "Shortage Needed", "Store Link", "Validation & Status"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 240)
        self.table.setColumnWidth(5, 150)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_mode_a_item_double_clicked)

        self._populate_mode_a_table()
        layout.addWidget(self.table)

        # Compact Status Ribbon in footer
        status_ribbon = QFrame()
        status_ribbon.setObjectName("ribbonFrame")
        status_layout = QHBoxLayout(status_ribbon)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(10)

        # 1. Ready to Order Pill (Green)
        pill_ready = QLabel(f"✅ Ready to Order: {len(self.orderable_items)}")
        pill_ready.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.12); "
            "border: 1px solid rgba(16, 185, 129, 0.35); "
            "color: #34d399; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
        )
        ready_names = [it.get("part_name") or it.get("part_number") or it.get("designator", "") for it in self.orderable_items]
        pill_ready.setToolTip(f"Ready for automated purchase ({len(self.orderable_items)} items):\n" + "\n".join(f"• {n}" for n in ready_names[:25]))
        status_layout.addWidget(pill_ready)

        # 2. Invalid Link Pill (Red)
        if self.external_items:
            pill_ext = QLabel(f"❌ Invalid Link: {len(self.external_items)}")
            pill_ext.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "border: 1px solid rgba(239, 68, 68, 0.35); "
                "color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            ext_names = [
                f"{it.get('part_name') or it.get('part_number') or it.get('designator', '')} ({it.get('link_domain', 'external')})"
                for it in self.external_items
            ]
            pill_ext.setToolTip(
                f"External / Unsupported Store Links ({len(self.external_items)} items):\n"
                f"Action: Update store URLs to a registered vendor in Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in ext_names[:25])
            )
            status_layout.addWidget(pill_ext)

        # 3. Blank Link Pill (Amber)
        if self.blank_link_items:
            pill_blank = QLabel(f"⚠️ Blank Link: {len(self.blank_link_items)}")
            pill_blank.setStyleSheet(
                "background-color: rgba(245, 158, 11, 0.12); "
                "border: 1px solid rgba(245, 158, 11, 0.35); "
                "color: #fbbf24; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            blank_names = [it.get("part_name") or it.get("part_number") or it.get("designator", "") for it in self.blank_link_items]
            pill_blank.setToolTip(
                f"Blank Store Links in DB ({len(self.blank_link_items)} items):\n"
                f"Action: Add vendor product links in Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in blank_names[:25])
            )
            status_layout.addWidget(pill_blank)

        # 4. Missing DB Pill (Red)
        if self.missing_db_items:
            pill_missing = QLabel(f"🔴 Not in DB: {len(self.missing_db_items)}")
            pill_missing.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "border: 1px solid rgba(239, 68, 68, 0.35); "
                "color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            missing_names = [
                it.get("part_number") or it.get("comment") or it.get("part_name", "")
                for it in self.missing_db_items
            ]
            pill_missing.setToolTip(
                f"Items Not Found in Inventory.xlsx ({len(self.missing_db_items)} items):\n"
                f"Action: Register these components into Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in missing_names[:25])
            )
            status_layout.addWidget(pill_missing)

        status_layout.addStretch()
        layout.addWidget(status_ribbon)

        # Progress Area
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(len(self.orderable_items), 1))
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;")
        self.progress_lbl.hide()
        layout.addWidget(self.progress_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.settings_btn = QPushButton("⚙️ Account Settings")
        self.settings_btn.setObjectName("secondaryBtn")
        self.settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.settings_btn)

        self.export_btn = QPushButton("📄 Export Report ▼")
        self.export_btn.setObjectName("secondaryBtn")
        self.export_btn.clicked.connect(self._show_export_menu)
        btn_layout.addWidget(self.export_btn)

        btn_layout.addStretch()

        self.confirm_payment_btn = QPushButton("💰 Confirm Payment & Add Stock")
        self.confirm_payment_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        self.confirm_payment_btn.hide()
        self.confirm_payment_btn.clicked.connect(self._confirm_payment_and_add_stock)
        btn_layout.addWidget(self.confirm_payment_btn)

        self.cancel_btn = QPushButton("Cancel / Dismiss")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.open_cart_btn = QPushButton("🛒 Open Shopping Cart in Browser")
        self.open_cart_btn.setObjectName("secondaryBtn")
        self.open_cart_btn.hide()
        self.open_cart_btn.clicked.connect(self._open_shopping_cart)
        btn_layout.addWidget(self.open_cart_btn)

        # Order Button
        order_vendor_name = "Lion Electronic" if (len(self.lion_items) == len(self.orderable_items) and len(self.lion_items) > 0) else "Multi-Vendor"
        self.order_btn = QPushButton(f"🛒 Order {len(self.orderable_items)} Items on {order_vendor_name}")
        self.order_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        if len(self.orderable_items) == 0:
            self.order_btn.setEnabled(False)
            self.order_btn.setText("❌ No Orderable Items")
        self.order_btn.clicked.connect(self._execute_mode_a_order)
        btn_layout.addWidget(self.order_btn)

        layout.addLayout(btn_layout)

    def _get_vendor_name(self, vendor_id: Optional[str]) -> str:
        if not vendor_id:
            return "Vendor"
        if hasattr(self.registry, "get_vendor_name"):
            res = self.registry.get_vendor_name(vendor_id)
            if isinstance(res, str):
                return res
        return str(vendor_id).replace("vendor_", "").title()

    def _populate_mode_a_table(self):
        self.table.setRowCount(len(self.all_shortages))
        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        for row, it in enumerate(self.all_shortages):
            # 0. Part / Designator
            p_name = it.get("part_name") or it.get("part_number") or it.get("designator", f"Item {row+1}")
            item0 = QTableWidgetItem(str(p_name))
            item0.setFont(font_txt)
            self.table.setItem(row, 0, item0)

            # 1. Part Number / Description
            desc = it.get("description") or it.get("comment") or it.get("part_number", "")
            item1 = QTableWidgetItem(str(desc))
            item1.setFont(font_txt)
            self.table.setItem(row, 1, item1)

            # 2. Current Stock
            raw_c_stock = it.get("current_stock")
            if raw_c_stock is None:
                raw_c_stock = it.get("in_stock")
            if raw_c_stock is None:
                raw_c_stock = it.get("db_stock_qty")
            if raw_c_stock is None:
                raw_c_stock = it.get("stock_qty")
            if raw_c_stock is None:
                raw_c_stock = it.get("stock")
            c_stock = str(raw_c_stock) if raw_c_stock is not None else "-"
            item2 = QTableWidgetItem(str(c_stock))
            item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item2.setFont(font_num)
            self.table.setItem(row, 2, item2)

            # 3. Shortage Needed
            needed = it.get("needed_qty") if it.get("needed_qty") is not None else it.get("shortage_qty", 0)
            item3 = QTableWidgetItem(str(needed))
            item3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item3.setFont(font_num)
            item3.setForeground(QColor("#fbbf24"))
            self.table.setItem(row, 3, item3)

            # 4. Store Link & 5. Validation & Status
            vendor_links = it.get("vendor_links") or {}
            is_multi = it.get("is_multi_vendor") or len(vendor_links) > 1
            selected_vid = it.get("selected_vendor_id")
            link = str(it.get("link", "")).strip()

            item4 = QTableWidgetItem()
            item4.setFont(font_txt)
            item5 = QTableWidgetItem()
            item5.setFont(font_txt)

            if is_multi:
                v_names = [self._get_vendor_name(v) for v in sorted(vendor_links.keys())]
                if selected_vid and selected_vid in vendor_links:
                    sel_name = self._get_vendor_name(selected_vid)
                    sel_url = it.get("selected_url") or vendor_links[selected_vid]
                    item4.setText(f"{sel_name}: {sel_url}")
                    item4.setForeground(QColor("#38bdf8"))
                    item4.setToolTip(f"Selected: {sel_name}\nURL: {sel_url}\nAvailable: {', '.join(v_names)}")
                    item5.setText(f"✅ {sel_name} Selected")
                    item5.setForeground(QColor("#34d399"))
                else:
                    item4.setText(f"⚡ Multi-Vendor ({', '.join(v_names)})")
                    item4.setForeground(QColor("#a78bfa"))
                    tt = "Multiple vendor options configured:\n" + "\n".join(f"• {self._get_vendor_name(v)}: {u}" for v, u in vendor_links.items()) + "\n\nDouble-click row to select vendor."
                    item4.setToolTip(tt)
                    item5.setText("⚡ Selection Required")
                    item5.setForeground(QColor("#a78bfa"))
            else:
                vid = it.get("vendor_id") or self.registry.get_vendor_for_url(link, enabled_only=True)
                is_registered_and_enabled = bool(vid and self.registry.has_vendor(vid) and self.registry.is_vendor_enabled(vid))

                if is_registered_and_enabled:
                    v_display = self._get_vendor_name(vid)
                    item4.setText(link)
                    item4.setForeground(QColor("#38bdf8"))
                    item4.setToolTip(f"{v_display} link (Auto-Order Ready):\n{link}")
                    item5.setText(f"✅ {v_display} Ready")
                    item5.setForeground(QColor("#34d399"))
                elif link.startswith("http"):
                    domain = it.get("link_domain") or (link.split("/")[2] if "//" in link else "external")
                    item4.setText(f"❌ Non-registered URL ({domain})")
                    item4.setForeground(QColor("#f87171"))
                    item4.setToolTip(f"No vendor plugin installed for this storefront URL: {link}\nAction: Install a compatible vendor plugin or update to a registered vendor in Inventory.xlsx.")
                    item5.setText("❌ No Plugin Installed")
                    item5.setForeground(QColor("#f87171"))
                else:
                    item4.setText("❌ Blank Store Link")
                    item4.setForeground(QColor("#f87171"))
                    item4.setToolTip("Store link is missing in database. Please add vendor URL in Inventory.xlsx.")
                    item5.setText("⚠️ Blank Link")
                    item5.setForeground(QColor("#fbbf24"))

            self.table.setItem(row, 4, item4)
            self.table.setItem(row, 5, item5)

    def _on_mode_a_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        raw_it = self.all_shortages[row] if row < len(self.all_shortages) else {}
        vendor_links = raw_it.get("vendor_links") or {}
        if len(vendor_links) > 1:
            dlg = VendorSelectionDialog([raw_it], registry=self.registry, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._populate_mode_a_table()
            return

        link_item = self.table.item(row, 4)
        if link_item:
            link = raw_it.get("link") or link_item.text()
            if link and link.startswith("http"):
                webbrowser.open(link)

    def _execute_mode_a_order(self):
        """Execute automated purchasing on Lion / multi-vendor for Mode A items."""
        if not self.orderable_items:
            QMessageBox.warning(self, "No Items", "There are no valid vendor items to order.")
            return

        # Prompt for any multi-vendor items lacking user selection
        items_needing_selection = [
            it for it in self.orderable_items
            if it.get("vendor_links") and len(it.get("vendor_links")) > 1 and not it.get("selected_vendor_id")
        ]
        if items_needing_selection:
            dlg = VendorSelectionDialog(items_needing_selection, registry=self.registry, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                # User cancelled selection dialog: abort order safely without dispatching
                return
            self._populate_mode_a_table()

        # Check credentials for Lion items if present in final selections
        has_lion_order = any(
            (it.get("selected_vendor_id") == "vendor_lion") or
            (it.get("vendor_id") == "vendor_lion") or
            (it in self.lion_items)
            for it in self.orderable_items
        )
        if has_lion_order:
            user = settings.get("lion_username", "").strip()
            pwd = settings.get("lion_password", "").strip()
            if not user or not pwd:
                reply = QMessageBox.question(
                    self,
                    "Lion Electronic Login Required",
                    "Lion Electronic credentials (Phone/Username & Password) are not configured.\n\n"
                    "Would you like to open Settings now to enter your credentials?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._open_settings()
                return

        self.order_btn.setEnabled(False)
        self.order_btn.setText("⏳ Ordering...")
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, len(self.orderable_items))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_lbl.setText("Starting automated purchase...")
        self.progress_lbl.show()

        self.worker = OrderWorkerThread(
            items=self.orderable_items,
            registry=self.registry,
            orchestrator=self.orchestrator,
        )
        self.worker.progress_signal.connect(self._on_mode_a_order_progress)
        self.worker.finished_signal.connect(self._on_mode_a_order_finished)
        self.worker.start()

    def _on_mode_a_order_progress(self, current: int, total: int, part_name: str, qty: int, msg: str):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(f"Processing ({current}/{total}): {part_name} — {msg}")

        for row in range(self.table.rowCount()):
            p_item = self.table.item(row, 0)
            if p_item and p_item.text().strip() == part_name.strip():
                status_item = self.table.item(row, 5)
                if status_item:
                    if "Logging" in msg or "Authenticating" in msg:
                        status_item.setText("⏳ Logging in...")
                        status_item.setForeground(QColor("#38bdf8"))
                    elif "Staging" in msg or "Opening" in msg:
                        status_item.setText("⏳ Processing...")
                        status_item.setForeground(QColor("#38bdf8"))
                    elif "Partial" in msg:
                        status_item.setText(f"⚠️ Partial ({qty} pcs)")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif msg.lower().startswith("already satisfied in cart"):
                        status_item.setText("No new quantity added")
                        status_item.setForeground(QColor("#94a3b8"))
                    elif "Added" in msg or "Queued" in msg:
                        status_item.setText(f"✅ Added {qty} pcs")
                        status_item.setForeground(QColor("#34d399"))
                    elif "Insufficient" in msg:
                        status_item.setText("⚠️ Low Site Stock")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif "Inquiry" in msg or "Sale Closed" in msg:
                        status_item.setText("⚠️ Inquiry Only")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif "Coming Soon" in msg:
                        status_item.setText("⏳ Coming Soon")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif "Out of stock" in msg or "0 available" in msg:
                        status_item.setText("❌ Out of Stock")
                        status_item.setForeground(QColor("#f87171"))
                    else:
                        short_txt = msg[:20] if len(msg) > 20 else msg
                        status_item.setText(f"❌ {short_txt}")
                        status_item.setForeground(QColor("#f87171"))
                break

    def _on_mode_a_order_finished(self, results: Dict[str, Any]):
        self.order_btn.setEnabled(True)
        self.order_btn.setText("🛒 Order Batch Finished")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.confirm_payment_btn.show()
        self.confirm_payment_btn.setEnabled(True)
        self.staging_results_log = results.get("results") or None

        show_browser = settings.get("show_browser", False)

        if results.get("success"):
            succ_count = results.get('successful_count', 0)
            self.progress_lbl.setText(f"✅ Order batch completed! ({succ_count} items in cart)")
            self.progress_lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold;")

            QMessageBox.information(
                self,
                "Order Processed",
                f"Successfully added {succ_count} item(s) into your vendor cart!\n\n"
                f"Click 'Open Shopping Cart in Browser' or review items to finalize checkout."
            )
            if not show_browser:
                self._open_shopping_cart()
        else:
            self.progress_lbl.setText(f"❌ Order issue: {results.get('message', 'Unknown error')}")
            self.progress_lbl.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold;")
            QMessageBox.warning(
                self,
                "Order Incomplete",
                f"Automated ordering encountered an issue:\n{results.get('message')}"
            )

    # =========================================================================
    # MODE B: MASTER-DETAIL MULTI-CANDIDATE SELECTION UI (GAP-07 / GAP-18)
    # =========================================================================

    def _init_mode_b_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Title
        title_lbl = QLabel(f"🛒 {self.source_title}")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        self.header_sub_lbl = QLabel("")
        self.header_sub_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(self.header_sub_lbl)

        # Master-Detail Splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)

        # Top: Master Line Items Table
        master_container = QWidget()
        m_layout = QVBoxLayout(master_container)
        m_layout.setContentsMargins(0, 0, 0, 0)
        m_layout.setSpacing(4)

        m_header = QLabel("📋 Sourced Line Items (Select a row to inspect and compare candidate offers):")
        m_header.setStyleSheet("font-weight: bold; font-size: 12px; color: #e2e8f0;")
        m_layout.addWidget(m_header)

        self.master_table = QTableWidget()
        self.master_table.setColumnCount(9)
        self.master_table.setHorizontalHeaderLabels([
            "Status", "Designator", "Part Number / MPN", "Selected Vendor", "Selected SKU",
            "Effective Qty", "Unit Price", "Total Cost", "Candidate Offers"
        ])
        m_hdr = self.master_table.horizontalHeader()
        m_hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        m_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.master_table.verticalHeader().setVisible(False)
        self.master_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.master_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.master_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.master_table.itemSelectionChanged.connect(self._on_master_row_selected)
        self.master_table.itemDoubleClicked.connect(self._on_master_table_double_clicked)
        m_layout.addWidget(self.master_table)
        splitter.addWidget(master_container)

        # Bottom: Detail Candidate Alternatives Table
        detail_container = QWidget()
        d_layout = QVBoxLayout(detail_container)
        d_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.setSpacing(4)

        self.detail_header_lbl = QLabel("📦 Candidate Offers & Alternatives (Select a row above):")
        self.detail_header_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #38bdf8;")
        d_layout.addWidget(self.detail_header_lbl)

        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(12)
        self.detail_table.setHorizontalHeaderLabels([
            "Select", "Vendor", "SKU", "MPN", "Manufacturer", "Package",
            "Stock", "MOQ", "Step", "Unit Price (IRR)", "Total Cost (IRR)", "Status / Compatibility"
        ])
        d_hdr = self.detail_table.horizontalHeader()
        d_hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        d_hdr.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.detail_table.itemDoubleClicked.connect(self._on_detail_table_double_clicked)
        d_layout.addWidget(self.detail_table)
        splitter.addWidget(detail_container)

        splitter.setSizes([320, 240])
        layout.addWidget(splitter)

        # Aliases for backward compatibility in tests
        self.candidates_table = self.detail_table

        # KPI Status Ribbon
        self.status_ribbon = QFrame()
        self.status_ribbon.setObjectName("ribbonFrame")
        s_layout = QHBoxLayout(self.status_ribbon)
        s_layout.setContentsMargins(8, 4, 8, 4)
        s_layout.setSpacing(10)

        self.pill_resolved = QLabel("✅ Ready to Order: 0")
        self.pill_resolved.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); "
            "color: #34d399; border-radius: 6px; padding: 4px 10px; font-weight: bold;"
        )
        s_layout.addWidget(self.pill_resolved)

        self.pill_alternatives = QLabel("🌐 Multiple Offers: 0")
        self.pill_alternatives.setStyleSheet(
            "background-color: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); "
            "color: #38bdf8; border-radius: 6px; padding: 4px 10px; font-weight: bold;"
        )
        s_layout.addWidget(self.pill_alternatives)

        self.pill_unresolved = QLabel("❌ Unresolved: 0")
        self.pill_unresolved.setStyleSheet(
            "background-color: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); "
            "color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold;"
        )
        s_layout.addWidget(self.pill_unresolved)

        s_layout.addStretch()

        self.lbl_total_cost = QLabel("💰 Total Order Cost: 0 IRR")
        self.lbl_total_cost.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8; padding-right: 8px;")
        s_layout.addWidget(self.lbl_total_cost)
        self.total_cost_lbl = self.lbl_total_cost

        layout.addWidget(self.status_ribbon)

        # Progress Area
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;")
        self.progress_lbl.hide()
        layout.addWidget(self.progress_lbl)

        # Bottom Action Bar
        btn_layout = QHBoxLayout()

        self.settings_btn = QPushButton("⚙️ Account Settings")
        self.settings_btn.setObjectName("secondaryBtn")
        self.settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.settings_btn)

        self.export_btn = QPushButton("📄 Export Report ▼")
        self.export_btn.setObjectName("secondaryBtn")
        self.export_btn.clicked.connect(self._show_export_menu)
        btn_layout.addWidget(self.export_btn)

        self.open_cart_btn = QPushButton("🛒 Open Shopping Cart in Browser")
        self.open_cart_btn.setObjectName("secondaryBtn")
        self.open_cart_btn.hide()
        self.open_cart_btn.clicked.connect(self._open_shopping_cart)
        btn_layout.addWidget(self.open_cart_btn)

        self.confirm_payment_btn = QPushButton("💰 Confirm Payment & Add Stock")
        self.confirm_payment_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        self.confirm_payment_btn.hide()
        self.confirm_payment_btn.clicked.connect(self._confirm_payment_and_add_stock)
        btn_layout.addWidget(self.confirm_payment_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel / Dismiss")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.order_btn = QPushButton("🛒 Order Items Across Vendors")
        self.order_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self.order_btn.clicked.connect(self._execute_staging_order)
        btn_layout.addWidget(self.order_btn)

        layout.addLayout(btn_layout)

        self._populate_master_table()
        if self.results:
            self.master_table.selectRow(0)

    def _populate_master_table(self):
        self.master_table.setRowCount(len(self.results))
        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        resolved_count = 0
        multi_offer_count = 0
        unresolved_count = 0
        total_cost = 0

        for row_idx, r in enumerate(self.results):
            req = r.request
            sel = r.selected_evaluation
            cand_count = len(r.candidates)
            eligible_cands = [e for e in r.evaluations if e.is_eligible]

            if cand_count > 1:
                multi_offer_count += 1

            # 0. Status Badge
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFont(font_txt)
            if sel and sel.is_eligible:
                resolved_count += 1
                status_item.setText("✅ READY")
                status_item.setForeground(QColor("#34d399"))
                status_item.setToolTip("Candidate selected and ready for automated cart staging.")
            else:
                unresolved_count += 1
                status_item.setText("🔴 UNRESOLVED")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip(r.error_message or "No eligible candidate selected.")
            self.master_table.setItem(row_idx, 0, status_item)

            # 1. Designator
            des = str(req.metadata.get("designator") or req.source or "—")
            self.master_table.setItem(row_idx, 1, QTableWidgetItem(des))

            # 2. Part Number / MPN
            self.master_table.setItem(row_idx, 2, QTableWidgetItem(req.part_number))

            # 3. Selected Vendor
            v_str = sel.candidate.vendor_id.replace("vendor_", "").title() if sel else "—"
            item_v = QTableWidgetItem(v_str)
            if sel:
                item_v.setForeground(QColor("#38bdf8"))
            self.master_table.setItem(row_idx, 3, item_v)

            # 4. Selected SKU
            sku_str = sel.candidate.product_ref.vendor_sku if sel else "—"
            self.master_table.setItem(row_idx, 4, QTableWidgetItem(sku_str))

            # 5. Effective Qty
            qty_str = str(sel.effective_quantity) if sel else str(req.required_quantity)
            item_qty = QTableWidgetItem(qty_str)
            item_qty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_qty.setFont(font_num)
            self.master_table.setItem(row_idx, 5, item_qty)

            # 6. Unit Price (IRR)
            up_str = f"{sel.effective_unit_price_irr:,} IRR" if sel and sel.effective_unit_price_irr is not None else "—"
            item_up = QTableWidgetItem(up_str)
            item_up.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_up.setFont(font_num)
            self.master_table.setItem(row_idx, 6, item_up)

            # 7. Total Cost (IRR)
            tc_str = f"{sel.effective_total_price_irr:,} IRR" if sel and sel.effective_total_price_irr is not None else "—"
            item_tc = QTableWidgetItem(tc_str)
            item_tc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_tc.setFont(font_num)
            item_tc.setForeground(QColor("#38bdf8") if sel else QColor("#94a3b8"))
            self.master_table.setItem(row_idx, 7, item_tc)
            if sel and sel.effective_total_price_irr is not None:
                total_cost += sel.effective_total_price_irr

            # 8. Candidate Offers Summary
            offers_str = f"📦 {cand_count} offer(s) ({len(eligible_cands)} eligible)"
            item_offers = QTableWidgetItem(offers_str)
            item_offers.setFont(font_txt)
            self.master_table.setItem(row_idx, 8, item_offers)

        # Update KPIs and Subtitle
        self.pill_resolved.setText(f"✅ Ready to Order: {resolved_count}")
        self.pill_alternatives.setText(f"🌐 Multiple Offers: {multi_offer_count}")
        self.pill_unresolved.setText(f"❌ Unresolved: {unresolved_count}")
        self.lbl_total_cost.setText(f"💰 Total Order Cost: {total_cost:,} IRR")

        self.header_sub_lbl.setText(
            f"<b>{resolved_count}</b> of <b>{len(self.results)}</b> items resolved across enabled vendors. "
            f"Total estimated procurement cost: <b>{total_cost:,} IRR</b>."
        )

        if resolved_count > 0:
            self.order_btn.setEnabled(True)
            self.order_btn.setText(f"🛒 Order {resolved_count} Ready Items Across Vendors")
        else:
            self.order_btn.setEnabled(False)
            self.order_btn.setText("❌ No Eligible Items to Order")

    def _on_master_row_selected(self):
        selected_rows = self.master_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row_idx = selected_rows[0].row()
        self.active_row_idx = row_idx
        self._on_master_row_changed(row_idx)

    def _on_master_row_changed(self, row_idx: int):
        if not (0 <= row_idx < len(self.results)):
            return

        r = self.results[row_idx]
        des = r.request.metadata.get("designator") or r.request.source or ""
        des_str = f" ({des})" if des else ""
        self.detail_header_lbl.setText(
            f"📦 Candidate Offers & Alternatives for '{r.request.part_number}'{des_str} — {len(r.evaluations)} offer(s):"
        )
        self._populate_detail_table(r)

    def _populate_detail_table(self, result: RequestProcurementResult):
        self.detail_table.setRowCount(len(result.evaluations))
        font_txt = QFont("Segoe UI", 9)
        font_num = QFont("Segoe UI", 9, QFont.Weight.DemiBold)

        for r_idx, ev in enumerate(result.evaluations):
            cand = ev.candidate
            is_selected = (result.selected_evaluation is not None and result.selected_evaluation == ev)

            # 0. Selection Radio Button
            radio = QRadioButton()
            radio.setChecked(is_selected)
            radio.setEnabled(ev.is_eligible)
            radio.toggled.connect(lambda checked, idx=r_idx: self._on_candidate_radio_toggled(idx, checked))
            w = QWidget()
            h_layout = QHBoxLayout(w)
            h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.addWidget(radio)
            self.detail_table.setCellWidget(r_idx, 0, w)

            # 1. Vendor
            v_name = cand.vendor_id.replace("vendor_", "").title()
            item_v = QTableWidgetItem(v_name)
            item_v.setFont(font_txt)
            if is_selected:
                item_v.setForeground(QColor("#38bdf8"))
            self.detail_table.setItem(r_idx, 1, item_v)

            # 2. SKU
            self.detail_table.setItem(r_idx, 2, QTableWidgetItem(cand.product_ref.vendor_sku))

            # 3. MPN
            self.detail_table.setItem(r_idx, 3, QTableWidgetItem(cand.part_number))

            # 4. Manufacturer
            self.detail_table.setItem(r_idx, 4, QTableWidgetItem(cand.manufacturer or "—"))

            # 5. Package
            self.detail_table.setItem(r_idx, 5, QTableWidgetItem(cand.package or cand.footprint or "—"))

            # 6. Live Stock
            stock_str = str(cand.stock_quantity) if cand.stock_quantity is not None else ("In Stock" if cand.in_stock else "Out of Stock")
            item_stock = QTableWidgetItem(stock_str)
            item_stock.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_stock.setFont(font_num)
            item_stock.setForeground(QColor("#34d399") if cand.in_stock else QColor("#f87171"))
            self.detail_table.setItem(r_idx, 6, item_stock)

            # 7. MOQ
            moq_val = cand.order_constraints.moq_raw or 1
            item_moq = QTableWidgetItem(str(moq_val))
            item_moq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_moq.setFont(font_txt)
            self.detail_table.setItem(r_idx, 7, item_moq)

            # 8. Step
            step_val = cand.order_constraints.packaging_step_raw or 1
            item_step = QTableWidgetItem(str(step_val))
            item_step.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_step.setFont(font_txt)
            self.detail_table.setItem(r_idx, 8, item_step)

            # 9. Unit Price (IRR)
            up_val = ev.effective_unit_price_irr if ev.effective_unit_price_irr is not None else cand.base_unit_price_irr
            up_str = f"{up_val:,} IRR" if up_val is not None else "—"
            item_up = QTableWidgetItem(up_str)
            item_up.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_up.setFont(font_num)
            self.detail_table.setItem(r_idx, 9, item_up)

            # 10. Total Cost (IRR)
            tc_val = ev.effective_total_price_irr if ev.effective_total_price_irr is not None else None
            tc_str = f"{tc_val:,} IRR" if tc_val is not None else "—"
            item_tc = QTableWidgetItem(tc_str)
            item_tc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_tc.setFont(font_num)
            item_tc.setForeground(QColor("#38bdf8") if is_selected else QColor("#94a3b8"))
            self.detail_table.setItem(r_idx, 10, item_tc)

            # 11. Status / Compatibility
            item_status = QTableWidgetItem()
            item_status.setFont(font_txt)
            if is_selected:
                item_status.setText("🌟 SELECTED TARGET")
                item_status.setForeground(QColor("#38bdf8"))
                item_status.setToolTip("Currently selected offer to be staged into cart.")
            elif ev.is_eligible:
                item_status.setText("✅ ELIGIBLE (Alternative)")
                item_status.setForeground(QColor("#34d399"))
                item_status.setToolTip("Meets all technical and brand constraints. Click radio button to select.")
            else:
                reasons_str = "; ".join(ev.rejection_reasons) or ev.state.value
                item_status.setText(f"❌ REJECTED ({ev.state.value})")
                item_status.setForeground(QColor("#f87171"))
                item_status.setToolTip(f"Cannot be selected: {reasons_str}")
            self.detail_table.setItem(r_idx, 11, item_status)

        for c in range(11):
            self.detail_table.resizeColumnToContents(c)

    def _render_detail_table(self, result: RequestProcurementResult):
        self._populate_detail_table(result)

    def _on_candidate_radio_toggled(self, eval_idx: int, checked: bool):
        if not checked or self.active_row_idx is None:
            return

        res = self.results[self.active_row_idx]
        if 0 <= eval_idx < len(res.evaluations):
            chosen_ev = res.evaluations[eval_idx]
            if chosen_ev.is_eligible:
                res.selected_evaluation = chosen_ev
                res.status = "RESOLVED"
                self._populate_master_table()
                self._populate_detail_table(res)

    def _on_candidate_toggled(self, cand_idx: int, checked: bool):
        self._on_candidate_radio_toggled(cand_idx, checked)

    def _on_master_table_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        if 0 <= row < len(self.results):
            sel = self.results[row].selected_evaluation
            if sel and sel.candidate.product_ref and sel.candidate.product_ref.pdp_url:
                webbrowser.open(sel.candidate.product_ref.pdp_url)

    def _on_detail_table_double_clicked(self, item: QTableWidgetItem):
        if not item or self.active_row_idx is None:
            return
        row = item.row()
        res = self.results[self.active_row_idx]
        if 0 <= row < len(res.evaluations):
            cand = res.evaluations[row].candidate
            if cand.product_ref and cand.product_ref.pdp_url:
                webbrowser.open(cand.product_ref.pdp_url)

    def _execute_staging_order(self):
        """Execute multi-vendor procurement staging for selected candidate evaluations."""
        orderable = [r for r in self.results if r.selected_evaluation and r.selected_evaluation.is_eligible]
        if not orderable:
            QMessageBox.warning(self, "No Items", "There are no eligible candidates selected for ordering.")
            return

        self.order_btn.setEnabled(False)
        self.order_btn.setText("⏳ Staging Items...")
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, len(orderable))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_lbl.setText("Starting multi-vendor cart staging...")
        self.progress_lbl.show()

        self.worker = OrderWorkerThread(
            results=self.results,
            orchestrator=self.orchestrator,
        )
        self.worker.progress_signal.connect(self._on_staging_progress)
        self.worker.finished_signal.connect(self._on_staging_finished)
        self.worker.start()

    def _on_staging_progress(self, current: int, total: int, part_name: str, qty: int, msg: str):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(f"Staging ({current}/{total}): {part_name} — {msg}")

    def _on_staging_finished(self, results: Dict[str, Any]):
        self.order_btn.setEnabled(True)
        self.order_btn.setText("🛒 Staging Finished")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.confirm_payment_btn.show()
        self.confirm_payment_btn.setEnabled(True)
        self.staging_results_log = results.get("results", [])

        if results.get("success"):
            succ_count = results.get("successful_count", 0)
            noop_count = results.get("noop_count", 0)
            staged_count = results.get("staged_count", 0)
            self.progress_lbl.setText(f"✅ Staging completed! ({staged_count} added, {noop_count} already in cart)")
            self.progress_lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold;")

            QMessageBox.information(
                self,
                "Staging Completed",
                f"Successfully staged {succ_count} item(s) across vendor carts!\n\n"
                f"• {staged_count} item(s) added to cart.\n"
                f"• {noop_count} item(s) already satisfied in cart.\n\n"
                f"Click 'Open Shopping Cart in Browser' to review and complete your order."
            )
        else:
            self.progress_lbl.setText(f"❌ Staging issue: {results.get('message')}")
            self.progress_lbl.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold;")
            QMessageBox.warning(
                self,
                "Staging Incomplete",
                f"Multi-vendor staging encountered issues:\n{results.get('message')}"
            )

    # =========================================================================
    # COMMON ACTIONS: INVENTORY UPDATE, CART, SETTINGS, EXPORT
    # =========================================================================

    def _confirm_payment_and_add_stock(self):
        """Atomically increment Quantity in Stock in Inventory.xlsx for successfully ordered items."""
        if self._has_updated_inventory:
            QMessageBox.information(self, "Already Updated", "Inventory stock has already been updated for this batch.")
            return

        if not self.inventory_loader:
            QMessageBox.warning(self, "No Database", "Active inventory database reference is not available.")
            return

        # Build list of items to increment
        success_items: List[Dict[str, Any]] = []

        if not self.is_mode_b_preview:
            # Mode A: check orderable_items
            for it in self.orderable_items:
                if it.get("order_success") is True and (it.get("actual_ordered_qty") or 0) > 0:
                    success_items.append(it)
                elif it.get("order_success") is None:
                    qty = it.get("actual_ordered_qty") or it.get("qty_ordered") or it.get("needed_qty") or it.get("shortage_qty")
                    if qty and qty > 0:
                        success_items.append(it)
        else:
            # Mode B: check results
            for r in self.results:
                if r.selected_evaluation and r.selected_evaluation.is_eligible:
                    success_items.append({
                        "part_number": r.request.part_number,
                        "part_name": r.request.part_number,
                        "actual_ordered_qty": r.selected_evaluation.effective_quantity,
                        "needed_qty": r.request.required_quantity,
                    })

        if not success_items:
            QMessageBox.information(
                self,
                "No Items Ordered",
                "No items were successfully purchased in this batch to add to inventory."
            )
            return

        lines = []
        for it in success_items:
            name = it.get("part_name") or it.get("part_number") or it.get("designator", "")
            qty = it.get("actual_ordered_qty") if it.get("actual_ordered_qty") is not None else (it.get("qty_ordered") or it.get("needed_qty") or 0)
            if qty > 0:
                lines.append(f"• <b>{name}</b>: +{qty} pcs")

        items_text = "<br>".join(lines[:15])
        if len(lines) > 15:
            items_text += f"<br><i>(+{len(lines)-15} more items)</i>"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Payment & Stock Update")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(
            f"<b>Did you complete and pay for this order on the vendor site?</b><br><br>"
            f"The following successfully purchased quantities (<b>{len(success_items)} item(s)</b>) will be added to <code>Quantity in Stock</code> in <code>Inventory.xlsx</code>:<br><br>"
            f"{items_text}<br><br>"
            f"Click <b>Yes</b> to add these quantities to your inventory now."
        )
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton("Yes, Add to Inventory", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("No / Cancel", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(yes_btn)
        msg_box.exec()

        if msg_box.clickedButton() != yes_btn:
            return

        count, msg = self.inventory_loader.batch_increment_stock(success_items)
        if count > 0:
            self._has_updated_inventory = True
            self.confirm_payment_btn.setText("✅ Stock Added to Inventory")
            self.confirm_payment_btn.setEnabled(False)
            self.confirm_payment_btn.setStyleSheet("background-color: #1e293b; color: #34d399; font-weight: bold;")

            QMessageBox.information(
                self,
                "Inventory Updated",
                f"✅ Success!\n\n{count} item(s) have been added to your current stock in Inventory.xlsx."
            )

            if self.on_stock_updated:
                self.on_stock_updated()
        else:
            QMessageBox.warning(
                self,
                "Update Failed",
                f"Could not update stock in Inventory.xlsx:\n{msg}"
            )

    def _open_shopping_cart(self):
        """Open shopping cart URL in user's default browser via registered vendor adapters."""
        target_vendors = set()

        if self.is_mode_b_preview:
            for r in self.results:
                if r.selected_evaluation and r.selected_evaluation.candidate:
                    vid = r.selected_evaluation.candidate.vendor_id
                    if vid:
                        target_vendors.add(vid)
        else:
            items_to_scan = self.orderable_items if self.orderable_items else self.all_shortages
            for it in (items_to_scan or []):
                link = str(it.get("link", "")).strip()
                vid = it.get("vendor_id") or (self.registry.get_vendor_for_url(link, enabled_only=True) if link else None)
                if vid:
                    target_vendors.add(vid)

        if not target_vendors:
            QMessageBox.warning(
                self,
                "Cart Unavailable",
                "No registered vendor items could be resolved to open shopping carts.",
            )
            return

        opened_vendors = set()
        failed_vendors = []

        for v_id in sorted(target_vendors):
            cart_url = None
            try:
                adapter = self.registry.get_adapter(v_id)
                if hasattr(adapter, "get_cart_url") and callable(adapter.get_cart_url):
                    cart_url = adapter.get_cart_url()
            except Exception:
                cart_url = None

            clean_url = str(cart_url or "").strip()
            if clean_url and (clean_url.startswith("http://") or clean_url.startswith("https://")):
                webbrowser.open(clean_url)
                opened_vendors.add(v_id)
            else:
                v_name = str(self._get_vendor_name(v_id) if hasattr(self, "_get_vendor_name") else v_id)
                failed_vendors.append(v_name)

        if failed_vendors and not opened_vendors:
            QMessageBox.warning(
                self,
                "Cart Unavailable",
                f"Could not open shopping cart for: {', '.join(failed_vendors)}. No valid cart URL available.",
            )
        elif failed_vendors:
            QMessageBox.warning(
                self,
                "Some Carts Unavailable",
                f"Could not open shopping cart for: {', '.join(failed_vendors)}.",
            )

    def _open_settings(self):
        dlg = SettingsDialog(parent=self)
        dlg.exec()

    def _show_export_menu(self):
        menu = QMenu(self)
        csv_act = menu.addAction("📊 Export as CSV (.csv)")
        xlsx_act = menu.addAction("📗 Export as Excel (.xlsx)")
        pdf_act = menu.addAction("📕 Export as Vector PDF (.pdf)")

        csv_act.triggered.connect(lambda: self._export_procurement_report("csv"))
        xlsx_act.triggered.connect(lambda: self._export_procurement_report("xlsx"))
        pdf_act.triggered.connect(lambda: self._export_procurement_report("pdf"))

        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def _export_procurement_report(self, format_type: str):
        default_name = f"Procurement_Report_{self.source_title.replace(' ', '_')}.{format_type}"
        filters = {
            "csv": "CSV Files (*.csv)",
            "xlsx": "Excel Files (*.xlsx)",
            "pdf": "PDF Files (*.pdf)",
        }

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Procurement Report ({format_type.upper()})",
            default_name,
            filters.get(format_type, "All Files (*.*)"),
        )
        if not path:
            return

        if self.is_mode_b_preview and self.plan and len(self.plan.results) > 0:
            report_data = ProcurementReportBuilder.build(
                plan=self.plan,
                source_title=self.source_title,
                staging_results=self.staging_results_log,
            )
        else:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=self.all_shortages,
                source_title=self.source_title,
                staging_results=self.staging_results_log,
            )

        success = False
        err_msg = ""
        try:
            if format_type == "csv":
                ProcurementCSVExporter.export(report_data, path)
                success = True
            elif format_type == "xlsx":
                ProcurementXLSXExporter.export(report_data, path)
                success = True
            elif format_type == "pdf":
                ProcurementPDFExporter.export(report_data, path)
                success = True
        except Exception as e:
            success = False
            err_msg = str(e)

        if success:
            QMessageBox.information(
                self,
                "Export Successful",
                f"Procurement report successfully exported to:\n{path}",
            )
            webbrowser.open(f"file:///{os.path.abspath(path)}")
        else:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Failed to export procurement report:\n{err_msg or 'Unknown exporter error'}",
            )

    def closeEvent(self, event):
        if self.discovery_worker and self.discovery_worker.isRunning():
            self.discovery_worker.terminate()
            self.discovery_worker.wait(500)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(500)
        super().closeEvent(event)
