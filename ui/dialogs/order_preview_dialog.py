"""
Omnix UI — Multi-Vendor Order Preview & Candidate Selection Dialog
Governing GAP: GAP-07 (Multi-Candidate Comparison & Alternative Selection) & Mode A Fast Confirmation
Reuses UniversalProcurementOrchestrator, CandidateEvaluation, ProcurementBridge, and GAP-13 Delta Synchronization.
"""

import datetime
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
    QScrollArea,
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
    SupplierItemResult,
    SupplierOutcomeStatus,
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
from core.procurement.reporting.models import ReportType
from settings_manager import settings
from ui.styles import ensure_checkbox_icons
from core.logger import log_event, track_operation


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
        with track_operation("Procurement", f"Direct procurement batch for {len(self.items)} shortage items") as tracker:
            def on_progress(current: int, total: int, part_name: str, qty: int, msg: str):
                self.progress_signal.emit(current, total, part_name, qty, msg)
                if current % max(1, total // 5) == 0 or current == total:
                    tracker.progress(f"Processing item {current}/{total}: {part_name} - {msg}")

            res = ProcurementBridge.execute_staged_procurement_batch(
                items=self.items,
                progress_callback=on_progress,
                registry=self.registry,
                orchestrator=self.orchestrator,
            )
            if res.get("success"):
                tracker.complete(
                    f"Direct procurement batch finished: {res.get('successful_count', 0)} succeeded, {res.get('failed_count', 0)} failed"
                )
            else:
                tracker.fail(
                    f"Direct procurement batch finished with issues: {res.get('message', 'Errors occurred')}",
                    level="WARNING",
                )
            self.finished_signal.emit(res)

    def _run_procurement_results(self):
        """Execute Mode B / GAP-07 staging via orchestrator."""
        orderable_results = [r for r in self.results if r.selected_evaluation is not None and r.selected_evaluation.is_eligible]

        if not orderable_results:
            log_event("Procurement", "COMPLETION", "No eligible candidate items selected for staging")
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

        with track_operation("Procurement", f"Multi-vendor cart staging for {len(orderable_results)} candidate items") as tracker:
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

                if idx % max(1, len(orderable_results) // 4) == 0 or idx == len(orderable_results):
                    tracker.progress(f"Processed {idx}/{len(orderable_results)} items ({successful_count} succeeded, {failed_count} failed)")

            overall_success = (failed_count == 0) and (successful_count > 0)
            if overall_success:
                tracker.complete(
                    f"Multi-vendor staging completed: {successful_count} succeeded ({staged_count} added, {noop_count} in cart)"
                )
            elif successful_count > 0 and failed_count > 0:
                tracker.fail(
                    f"Multi-vendor staging partially failed: {successful_count} succeeded, {failed_count} failed",
                    level="WARNING",
                )
            else:
                tracker.fail(
                    f"Multi-vendor staging failed: all {failed_count} items failed to stage",
                    level="ERROR",
                )
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
    Dialog prompting the user to explicitly select which supplier link to use
    for components that have multiple valid supplier URLs (Scope C).

    Guarantees:
    1. Shows human-readable vendor display names and supplier URLs.
    2. Displays enough information to distinguish available links (supplier name, URL, custom label).
    3. Requires explicit user choice: does not silently default to first or arbitrary vendor.
    4. Presents only vendors with valid, eligible links for that specific component.
    5. Preserves user selection into item['selected_vendor_id'], item['selected_url'], item['vendor_id'], item['link'].
    6. Does not mutate the persistent database or Excel file.
    7. Supports multiple components independently without mixing up links.
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

        self.setWindowTitle("Select Supplier Link — Multi-Link Components")
        self.resize(640, min(650, 220 + len(self.items) * 85))
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
                font-size: 12px;
                min-width: 280px;
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

        header = QLabel("⚡ Select Supplier Link for Multi-Link Components")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(header)

        desc = QLabel(
            "The following component(s) have multiple eligible supplier options configured. "
            "Please select which supplier link to use for this procurement operation:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc)

        self.combo_boxes: List[Tuple[Dict[str, Any], QComboBox]] = []

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")

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
                    padding: 8px 12px;
                }
            """)
            row_layout = QVBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(6)

            top_row = QHBoxLayout()
            p_name = it.get("part_name") or it.get("part_number") or it.get("designator") or "Component"
            needed = it.get("needed_qty") if it.get("needed_qty") is not None else it.get("shortage_qty", 1)
            desc_txt = it.get("description") or it.get("comment") or ""
            desig_txt = it.get("designator") or ""

            info_text = f"<b>{p_name}</b>"
            if desig_txt and desig_txt != p_name:
                info_text += f" &nbsp;<span style='color: #94a3b8;'>[{desig_txt}]</span>"
            info_text += f" &nbsp;<span style='color: #fbbf24;'>({needed} pcs)</span>"
            if desc_txt:
                info_text += f" &nbsp;<span style='color: #64748b;'>— {desc_txt[:35]}</span>"

            info_lbl = QLabel(info_text)
            info_lbl.setTextFormat(Qt.TextFormat.RichText)
            top_row.addWidget(info_lbl, 1)

            combo = QComboBox()
            combo.addItem("-- Select Supplier Link --", None)

            # Build available link options
            vendor_links = it.get("vendor_links", {})
            supplier_links = it.get("supplier_links") or ()

            # Create mapping of vid -> custom display name from supplier_links if available
            custom_labels: Dict[str, str] = {}
            if supplier_links:
                for sl in supplier_links:
                    vid = getattr(sl, "vendor_id", None) or ""
                    disp = getattr(sl, "display_name", "") or getattr(sl, "vendor_label", "")
                    if vid and disp:
                        custom_labels[vid] = disp

            for vid in sorted(vendor_links.keys()):
                url = vendor_links[vid]
                v_name = (
                    self.registry.get_vendor_name(vid)
                    if hasattr(self.registry, "get_vendor_name")
                    else vid.replace("vendor_", "").title()
                )
                custom_lbl = custom_labels.get(vid)
                if custom_lbl and custom_lbl.lower() != v_name.lower():
                    item_label = f"{v_name} ({custom_lbl})"
                else:
                    item_label = v_name

                combo.addItem(item_label, (vid, url))
                idx = combo.count() - 1
                combo.setItemData(idx, f"Supplier: {v_name}\nURL: {url}", Qt.ItemDataRole.ToolTipRole)

            # Pre-select if already chosen previously
            curr_sel_vid = it.get("selected_vendor_id")
            if curr_sel_vid and curr_sel_vid in vendor_links:
                for idx in range(1, combo.count()):
                    cdata = combo.itemData(idx)
                    if isinstance(cdata, tuple) and cdata[0] == curr_sel_vid:
                        combo.setCurrentIndex(idx)
                        break

            top_row.addWidget(combo, 1)
            row_layout.addLayout(top_row)

            # Show active supplier link URL below combo for distinction without cluttering dropdown
            url_preview_lbl = QLabel("")
            url_preview_lbl.setStyleSheet("color: #64748b; font-size: 11px; padding-left: 4px;")
            url_preview_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            url_preview_lbl.setWordWrap(True)

            def make_update_fn(cb, lbl):
                def update_url():
                    data = cb.currentData()
                    if isinstance(data, tuple) and len(data) >= 2:
                        lbl.setText(f"🔗 {data[1]}")
                        lbl.show()
                    else:
                        lbl.setText("")
                        lbl.hide()
                return update_url

            update_fn = make_update_fn(combo, url_preview_lbl)
            combo.currentIndexChanged.connect(update_fn)
            update_fn()
            row_layout.addWidget(url_preview_lbl)

            scroll_layout.addWidget(row_frame)
            self.combo_boxes.append((it, combo))

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area, 1)

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
        # Validate that every item has an explicit selection (no unselected placeholders)
        unselected = []
        for it, combo in self.combo_boxes:
            cdata = combo.currentData()
            if not cdata or not isinstance(cdata, tuple):
                p_name = it.get("part_name") or it.get("part_number") or it.get("designator") or "Component"
                unselected.append(p_name)

        if unselected:
            QMessageBox.warning(
                self,
                "Selection Incomplete",
                "Please select a supplier link for the following component(s):\n• " + "\n• ".join(unselected)
            )
            return

        for it, combo in self.combo_boxes:
            cdata = combo.currentData()
            selected_vid, selected_url = cdata
            vendor_links = it.get("vendor_links", {})
            if selected_vid in vendor_links:
                it["selected_vendor_id"] = selected_vid
                it["selected_url"] = selected_url
                it["vendor_id"] = selected_vid
                it["link"] = selected_url

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

    COL_SELECT = 0
    COL_PART = 1
    COL_DESC = 2
    COL_STOCK = 3
    COL_NEEDED = 4
    COL_LINK = 5
    COL_STATUS = 6

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
        self.active_row_idx: Optional[int] = None
        self._is_updating_table: bool = False

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

            # Determine eligible vendor links (vendor is registered and enabled)
            eligible_links: Dict[str, str] = {}
            for vid, e in parsed.links.items():
                if self.registry.has_vendor(vid) and self.registry.is_vendor_enabled(vid):
                    eligible_links[vid] = e.url

            it["vendor_links"] = eligible_links

            if len(eligible_links) == 1:
                # Exactly one eligible link: use without unnecessary prompting
                vid = next(iter(eligible_links.keys()))
                sel_url = eligible_links[vid]
                it["vendor_id"] = vid
                it["selected_vendor_id"] = vid
                it["selected_url"] = sel_url
                it["link"] = sel_url
                it["is_multi_vendor"] = False
                if vid == "vendor_lion":
                    self.lion_items.append(it)
                else:
                    self.other_vendor_items.append(it)
            elif len(eligible_links) > 1:
                # More than one eligible link: explicit user selection required
                it["is_multi_vendor"] = True
                self.multi_vendor_items.append(it)
            else:
                it["is_multi_vendor"] = False
                self.external_items.append(it)

        self.orderable_items = self.lion_items + self.other_vendor_items + self.multi_vendor_items
        self.invalid_items = self.external_items + self.blank_link_items

        # Initialize selection state: orderable items default to selected, others unselected
        for it in self.all_shortages:
            if it in self.orderable_items:
                if "_selected" not in it:
                    it["_selected"] = True
            else:
                it["_selected"] = False

        self._is_updating_table = True

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

        # Selection Control Bar (Select All, Deselect All, Count)
        selection_bar = QHBoxLayout()
        selection_bar.setContentsMargins(0, 2, 0, 2)
        selection_bar.setSpacing(8)

        btn_style = """
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #1e293b;
            }
        """

        self.select_all_btn = QPushButton("☑ Select All")
        self.select_all_btn.setObjectName("secondaryBtn")
        self.select_all_btn.setStyleSheet(btn_style)
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.setToolTip("Select all valid orderable items")
        self.select_all_btn.clicked.connect(self._select_all_orderable)
        selection_bar.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("☐ Deselect All")
        self.deselect_all_btn.setObjectName("secondaryBtn")
        self.deselect_all_btn.setStyleSheet(btn_style)
        self.deselect_all_btn.setFixedHeight(28)
        self.deselect_all_btn.setToolTip("Deselect all items")
        self.deselect_all_btn.clicked.connect(self._deselect_all_orderable)
        selection_bar.addWidget(self.deselect_all_btn)

        selection_bar.addStretch()

        self.selection_count_lbl = QLabel()
        self.selection_count_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.selection_count_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        selection_bar.addWidget(self.selection_count_lbl)

        layout.addLayout(selection_bar)

        # Main Table of All Shortages (7 columns: Select + 6 info columns)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Select", "Part / Designator", "Part Number / Description", "Current Stock", "Shortage Needed", "Store Link", "Validation & Status"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_SELECT, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(self.COL_SELECT, 56)
        self.table.setColumnWidth(self.COL_PART, 140)
        self.table.setColumnWidth(self.COL_STOCK, 95)
        self.table.setColumnWidth(self.COL_NEEDED, 115)
        self.table.setColumnWidth(self.COL_LINK, 230)
        self.table.setColumnWidth(self.COL_STATUS, 150)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_mode_a_item_double_clicked)
        _chk = ensure_checkbox_icons()
        self.table.setStyleSheet(f"""
            QTableWidget::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1.5px solid #64748b;
                background-color: #0f172a;
            }}
            QTableWidget::indicator:hover {{
                border-color: #38bdf8;
                background-color: #1e293b;
            }}
            QTableWidget::indicator:checked {{
                background-color: #0284c7;
                border-color: #38bdf8;
                image: url('{_chk}');
            }}
            QTableWidget::indicator:checked:hover {{
                background-color: #0369a1;
                border-color: #7dd3fc;
                image: url('{_chk}');
            }}
            QTableWidget::indicator:disabled {{
                border: 1.5px dashed #334155;
                background-color: rgba(15, 23, 42, 0.45);
            }}
        """)

        self._populate_mode_a_table()
        self.table.itemChanged.connect(self._on_table_item_changed)
        self._is_updating_table = False

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

        self.export_post_operation_btn = QPushButton("📄 Export Staging Results (.xlsx)")
        self.export_post_operation_btn.setObjectName("secondaryBtn")
        self.export_post_operation_btn.setStyleSheet("""
            QPushButton#secondaryBtn:disabled {
                background-color: #1e293b;
                color: #64748b;
                border: 1px solid #334155;
            }
        """)
        self.export_post_operation_btn.setEnabled(False)
        self.export_post_operation_btn.clicked.connect(self._export_post_operation_results)
        btn_layout.addWidget(self.export_post_operation_btn)
        self.export_btn = self.export_post_operation_btn

        btn_layout.addStretch()

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
        self.order_btn = QPushButton()
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
        self.order_btn.clicked.connect(self._execute_mode_a_order)
        btn_layout.addWidget(self.order_btn)

        layout.addLayout(btn_layout)

        # Update initial selection state, count, and order button
        self._update_selection_state_and_order_btn()

    def get_selected_orderable_items(self) -> List[Dict[str, Any]]:
        """Return list of valid orderable items currently selected in the UI."""
        selected = []
        for row in range(self.table.rowCount()):
            item0 = self.table.item(row, self.COL_SELECT)
            if item0 and item0.checkState() == Qt.CheckState.Checked:
                idx = item0.data(Qt.ItemDataRole.UserRole)
                if isinstance(idx, int) and 0 <= idx < len(self.all_shortages):
                    it = self.all_shortages[idx]
                    if it in self.orderable_items:
                        selected.append(it)
        return selected

    @property
    def selected_orderable_items(self) -> List[Dict[str, Any]]:
        return self.get_selected_orderable_items()

    def _select_all_orderable(self):
        """Select all valid orderable items in the table."""
        self._is_updating_table = True
        try:
            for row in range(self.table.rowCount()):
                item0 = self.table.item(row, self.COL_SELECT)
                if item0:
                    idx = item0.data(Qt.ItemDataRole.UserRole)
                    if isinstance(idx, int) and 0 <= idx < len(self.all_shortages):
                        it = self.all_shortages[idx]
                        if it in self.orderable_items:
                            it["_selected"] = True
                            item0.setCheckState(Qt.CheckState.Checked)
                        else:
                            it["_selected"] = False
                            item0.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._is_updating_table = False
        self._update_selection_state_and_order_btn()

    def _deselect_all_orderable(self):
        """Deselect all items in the table."""
        self._is_updating_table = True
        try:
            for row in range(self.table.rowCount()):
                item0 = self.table.item(row, self.COL_SELECT)
                if item0:
                    idx = item0.data(Qt.ItemDataRole.UserRole)
                    if isinstance(idx, int) and 0 <= idx < len(self.all_shortages):
                        self.all_shortages[idx]["_selected"] = False
                    item0.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._is_updating_table = False
        self._update_selection_state_and_order_btn()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handle user toggling of item selection checkbox."""
        if getattr(self, "_is_updating_table", False):
            return
        if not item or item.column() != self.COL_SELECT:
            return

        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self.all_shortages):
            it = self.all_shortages[idx]
            if it in self.orderable_items:
                it["_selected"] = (item.checkState() == Qt.CheckState.Checked)
            else:
                # Force non-orderable items to remain Unchecked
                if item.checkState() != Qt.CheckState.Unchecked:
                    self._is_updating_table = True
                    try:
                        item.setCheckState(Qt.CheckState.Unchecked)
                    finally:
                        self._is_updating_table = False
                it["_selected"] = False

        self._update_selection_state_and_order_btn()

    def _update_selection_state_and_order_btn(self):
        """Update selection label and order button text/state based on current selection."""
        if not hasattr(self, "order_btn"):
            return

        selected = self.get_selected_orderable_items()
        sel_count = len(selected)
        total_orderable = len(self.orderable_items)

        if hasattr(self, "selection_count_lbl"):
            self.selection_count_lbl.setText(
                f"Selected: <b>{sel_count}</b> of <b>{total_orderable}</b> orderable items"
            )

        if total_orderable == 0:
            self.order_btn.setEnabled(False)
            self.order_btn.setText("❌ No Orderable Items")
            if hasattr(self, "select_all_btn"):
                self.select_all_btn.setEnabled(True)
                self.select_all_btn.setToolTip("No items have valid vendor links to select.")
            if hasattr(self, "deselect_all_btn"):
                self.deselect_all_btn.setEnabled(True)
                self.deselect_all_btn.setToolTip("Clear all selections.")
            return

        if hasattr(self, "select_all_btn"):
            self.select_all_btn.setEnabled(True)
            self.select_all_btn.setToolTip("Select all valid orderable items")
        if hasattr(self, "deselect_all_btn"):
            self.deselect_all_btn.setEnabled(True)
            self.deselect_all_btn.setToolTip("Deselect all items")

        if sel_count == 0:
            self.order_btn.setEnabled(False)
            self.order_btn.setText("🛒 No Items Selected")
            return

        selected_lion_count = sum(1 for it in selected if it in self.lion_items)
        if selected_lion_count == sel_count and sel_count > 0:
            order_vendor_name = "Lion Electronic"
        else:
            order_vendor_name = "Multi-Vendor"

        self.order_btn.setEnabled(True)
        self.order_btn.setText(f"🛒 Order {sel_count} Items on {order_vendor_name}")

    def _get_vendor_name(self, vendor_id: Optional[str]) -> str:
        if not vendor_id:
            return "Vendor"
        if hasattr(self.registry, "get_vendor_name"):
            res = self.registry.get_vendor_name(vendor_id)
            if isinstance(res, str):
                return res
        return str(vendor_id).replace("vendor_", "").title()

    def _populate_mode_a_table(self):
        self._is_updating_table = True
        try:
            self.table.setRowCount(len(self.all_shortages))
            font_txt = QFont("Segoe UI", 10)
            font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

            for row, it in enumerate(self.all_shortages):
                # 0. Selection Checkbox
                is_orderable = it in self.orderable_items
                is_selected = is_orderable and it.get("_selected", True)
                it["_selected"] = is_selected

                item_sel = QTableWidgetItem()
                item_sel.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_sel.setData(Qt.ItemDataRole.UserRole, row)

                if is_orderable:
                    item_sel.setFlags(
                        Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )
                    item_sel.setCheckState(
                        Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked
                    )
                    item_sel.setToolTip("Include this item in the purchase order")
                else:
                    item_sel.setFlags(Qt.ItemFlag.ItemIsSelectable)
                    item_sel.setCheckState(Qt.CheckState.Unchecked)
                    item_sel.setToolTip("Cannot select: Component has no valid vendor link registered in database. Add a supplier URL in Inventory to enable ordering.")

                self.table.setItem(row, self.COL_SELECT, item_sel)

                # 1. Part / Designator
                p_name = it.get("part_name") or it.get("part_number") or it.get("designator", f"Item {row+1}")
                item1 = QTableWidgetItem(str(p_name))
                item1.setFont(font_txt)
                self.table.setItem(row, self.COL_PART, item1)

                # 2. Part Number / Description
                desc = it.get("description") or it.get("comment") or it.get("part_number", "")
                item2 = QTableWidgetItem(str(desc))
                item2.setFont(font_txt)
                self.table.setItem(row, self.COL_DESC, item2)

                # 3. Current Stock
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
                item3 = QTableWidgetItem(str(c_stock))
                item3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item3.setFont(font_num)
                self.table.setItem(row, self.COL_STOCK, item3)

                # 4. Shortage Needed
                needed = it.get("needed_qty") if it.get("needed_qty") is not None else it.get("shortage_qty", 0)
                item4 = QTableWidgetItem(str(needed))
                item4.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item4.setFont(font_num)
                item4.setForeground(QColor("#fbbf24"))
                self.table.setItem(row, self.COL_NEEDED, item4)

                # 5. Store Link & 6. Validation & Status
                vendor_links = it.get("vendor_links") or {}
                is_multi = it.get("is_multi_vendor") or len(vendor_links) > 1
                selected_vid = it.get("selected_vendor_id")
                link = str(it.get("link", "")).strip()

                item5 = QTableWidgetItem()
                item5.setFont(font_txt)
                item6 = QTableWidgetItem()
                item6.setFont(font_txt)

                if is_multi:
                    v_names = [self._get_vendor_name(v) for v in sorted(vendor_links.keys())]
                    if selected_vid and selected_vid in vendor_links:
                        sel_name = self._get_vendor_name(selected_vid)
                        sel_url = it.get("selected_url") or vendor_links[selected_vid]
                        item5.setText(f"{sel_name}: {sel_url}")
                        item5.setForeground(QColor("#38bdf8"))
                        item5.setToolTip(f"Selected: {sel_name}\nURL: {sel_url}\nAvailable: {', '.join(v_names)}")
                        item6.setText(f"✅ {sel_name} Selected")
                        item6.setForeground(QColor("#34d399"))
                    else:
                        item5.setText(f"⚡ Multi-Vendor ({', '.join(v_names)})")
                        item5.setForeground(QColor("#a78bfa"))
                        tt = "Multiple vendor options configured:\n" + "\n".join(f"• {self._get_vendor_name(v)}: {u}" for v, u in vendor_links.items()) + "\n\nDouble-click row to select vendor."
                        item5.setToolTip(tt)
                        item6.setText("⚡ Selection Required")
                        item6.setForeground(QColor("#a78bfa"))
                else:
                    vid = it.get("vendor_id") or self.registry.get_vendor_for_url(link, enabled_only=True)
                    is_registered_and_enabled = bool(vid and self.registry.has_vendor(vid) and self.registry.is_vendor_enabled(vid))

                    if is_registered_and_enabled:
                        v_display = self._get_vendor_name(vid)
                        item5.setText(link)
                        item5.setForeground(QColor("#38bdf8"))
                        item5.setToolTip(f"{v_display} link (Auto-Order Ready):\n{link}")
                        item6.setText(f"✅ {v_display} Ready")
                        item6.setForeground(QColor("#34d399"))
                    elif link.startswith("http"):
                        domain = it.get("link_domain") or (link.split("/")[2] if "//" in link else "external")
                        item5.setText(f"❌ Non-registered URL ({domain})")
                        item5.setForeground(QColor("#f87171"))
                        item5.setToolTip(f"No vendor plugin installed for this storefront URL: {link}\nAction: Install a compatible vendor plugin or update to a registered vendor in Inventory.xlsx.")
                        item6.setText("❌ No Plugin Installed")
                        item6.setForeground(QColor("#f87171"))
                    else:
                        item5.setText("❌ Blank Store Link")
                        item5.setForeground(QColor("#f87171"))
                        item5.setToolTip("Store link is missing in database. Please add vendor URL in Inventory.xlsx.")
                        item6.setText("⚠️ Blank Link")
                        item6.setForeground(QColor("#fbbf24"))

                self.table.setItem(row, self.COL_LINK, item5)
                self.table.setItem(row, self.COL_STATUS, item6)
        finally:
            self._is_updating_table = False

        self._update_selection_state_and_order_btn()

    def _on_mode_a_item_double_clicked(self, item: QTableWidgetItem):
        if not item or item.column() == self.COL_SELECT:
            return
        row = item.row()
        raw_it = self.all_shortages[row] if row < len(self.all_shortages) else {}
        vendor_links = raw_it.get("vendor_links") or {}
        if len(vendor_links) > 1:
            dlg = VendorSelectionDialog([raw_it], registry=self.registry, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._populate_mode_a_table()
            return

        link_item = self.table.item(row, self.COL_LINK)
        if link_item:
            link = raw_it.get("link") or link_item.text()
            if link and link.startswith("http"):
                webbrowser.open(link)

    def _execute_mode_a_order(self):
        """Execute automated purchasing on Lion / multi-vendor for Mode A items."""
        selected_orderable = self.get_selected_orderable_items()
        if not selected_orderable:
            QMessageBox.warning(self, "No Items Selected", "Please select at least one orderable item to purchase.")
            return

        # Prompt for any multi-vendor items lacking user selection
        items_needing_selection = [
            it for it in selected_orderable
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
            for it in selected_orderable
        )
        if has_lion_order:
            v_cfg = settings.get_vendor_settings("vendor_lion") if hasattr(settings, "get_vendor_settings") else {}
            user = str(getattr(v_cfg, "username", "") or settings.get("lion_username", "")).strip()
            pwd = str(getattr(v_cfg, "password", "") or settings.get("lion_password", "")).strip()
            if not user or not pwd:
                reply = QMessageBox.question(
                    self,
                    "Lion Electronic Login Required",
                    "Lion Electronic credentials (Phone/Username & Password) are not configured.\n\n"
                    "Would you like to open Settings now to enter your credentials?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._open_settings("vendor_lion")
                return

        self.order_btn.setEnabled(False)
        self.order_btn.setText("⏳ Staging Items...")
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, len(selected_orderable))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_lbl.setText("Starting supplier cart staging...")
        self.progress_lbl.show()

        self.worker = OrderWorkerThread(
            items=selected_orderable,
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
            p_item = self.table.item(row, self.COL_PART)
            desc_item = self.table.item(row, self.COL_DESC)
            p_text = p_item.text().strip() if p_item else ""
            d_text = desc_item.text().strip() if desc_item else ""
            if part_name.strip() in (p_text, d_text) or p_text.startswith(part_name.strip()):
                status_item = self.table.item(row, self.COL_STATUS)
                if status_item:
                    msg_lower = msg.lower()
                    if "logging" in msg_lower or "authenticating" in msg_lower:
                        status_item.setText("⏳ Logging in...")
                        status_item.setForeground(QColor("#38bdf8"))
                    elif "staging" in msg_lower or "opening" in msg_lower:
                        status_item.setText("⏳ Processing...")
                        status_item.setForeground(QColor("#38bdf8"))
                    elif "already satisfied" in msg_lower:
                        status_item.setText("No new quantity added")
                        status_item.setForeground(QColor("#94a3b8"))
                    elif "added" in msg_lower or "queued" in msg_lower:
                        status_item.setText(f"✅ Added {qty} pcs")
                        status_item.setForeground(QColor("#34d399"))
                    elif "insufficient" in msg_lower or "shortage" in msg_lower:
                        status_item.setText("⚠️ Insufficient Stock")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif "out of stock" in msg_lower or "0 available" in msg_lower:
                        status_item.setText("❌ Out of Stock")
                        status_item.setForeground(QColor("#f87171"))
                    elif "challenge" in msg_lower or "blocked" in msg_lower:
                        status_item.setText("❌ Challenge Blocked")
                        status_item.setForeground(QColor("#f87171"))
                    elif "skipped" in msg_lower:
                        status_item.setText("⚠️ Skipped")
                        status_item.setForeground(QColor("#fbbf24"))
                    elif "partial" in msg_lower:
                        status_item.setText(f"⚠️ Partial ({qty} pcs)")
                        status_item.setForeground(QColor("#fbbf24"))
                    else:
                        short_txt = msg[:20] if len(msg) > 20 else msg
                        status_item.setText(f"❌ {short_txt}")
                        status_item.setForeground(QColor("#f87171"))
                break

    def _on_mode_a_order_finished(self, results: Dict[str, Any]):
        self.order_btn.setEnabled(True)
        self.order_btn.setText("Staging Batch Finished")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.staging_results_log = results.get("results") or None
        has_valid_staging = bool(
            self.staging_results_log
            and any(
                r.get("status") == "SUCCESS"
                or r.get("qty", 0) > 0
                or r.get("is_noop", False)
                for r in self.staging_results_log
            )
        )
        self.export_post_operation_btn.setEnabled(has_valid_staging)
        if has_valid_staging:
            self.export_post_operation_btn.setToolTip("Export staging results and cart outcomes to Excel (.xlsx)")
        else:
            self.export_post_operation_btn.setToolTip("No valid staged items available to export.")

        # Update table rows based on final staging results
        results_list = results.get("results") or []
        for r_entry in results_list:
            p_name = str(r_entry.get("part") or "").strip()
            st_code = r_entry.get("status_code")
            is_noop = r_entry.get("is_noop", False)
            qty = r_entry.get("qty", 0)
            raw_msg = r_entry.get("msg", "")

            for row in range(self.table.rowCount()):
                p_item = self.table.item(row, self.COL_PART)
                d_item = self.table.item(row, self.COL_DESC)
                p_text = p_item.text().strip() if p_item else ""
                d_text = d_item.text().strip() if d_item else ""
                if p_name and (p_name in (p_text, d_text) or p_text.startswith(p_name)):
                    status_item = self.table.item(row, self.COL_STATUS)
                    if status_item:
                        if is_noop or st_code == SupplierOutcomeStatus.NO_OP_SATISFIED:
                            status_item.setText("No new quantity added")
                            status_item.setForeground(QColor("#94a3b8"))
                        elif st_code == SupplierOutcomeStatus.ADDED_TO_CART or (r_entry.get("status") == "SUCCESS" and qty > 0):
                            status_item.setText(f"✅ Added {qty} pcs")
                            status_item.setForeground(QColor("#34d399"))
                        elif st_code == SupplierOutcomeStatus.INSUFFICIENT_STOCK:
                            status_item.setText("⚠️ Insufficient Stock")
                            status_item.setForeground(QColor("#fbbf24"))
                        elif st_code == SupplierOutcomeStatus.OUT_OF_STOCK:
                            status_item.setText("❌ Out of Stock")
                            status_item.setForeground(QColor("#f87171"))
                        elif st_code == SupplierOutcomeStatus.CHALLENGE_BLOCKED:
                            status_item.setText("❌ Challenge Blocked")
                            status_item.setForeground(QColor("#f87171"))
                        elif st_code == SupplierOutcomeStatus.SKIPPED:
                            status_item.setText("⚠️ Skipped")
                            status_item.setForeground(QColor("#fbbf24"))
                        elif r_entry.get("status") == "FAILED":
                            status_item.setText(f"❌ {raw_msg[:20]}" if raw_msg else "❌ Failed")
                            status_item.setForeground(QColor("#f87171"))
                    break

        show_browser = settings.get("show_browser", False)

        if results.get("success"):
            succ_count = results.get('successful_count', 0)
            self.progress_lbl.setText(f"✅ Staging batch completed! ({succ_count} items in cart)")
            self.progress_lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold;")

            QMessageBox.information(
                self,
                "Staging Processed",
                f"Successfully added {succ_count} item(s) into your supplier cart!\n\n"
                f"Click 'Open Shopping Cart in Browser' to review items and complete checkout."
            )
            if not show_browser:
                self._open_shopping_cart()
        else:
            self.progress_lbl.setText(f"❌ Staging issue: {results.get('message', 'Unknown error')}")
            self.progress_lbl.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold;")
            QMessageBox.warning(
                self,
                "Staging Incomplete",
                f"Automated staging encountered an issue:\n{results.get('message')}"
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

        self.export_post_operation_btn = QPushButton("📄 Export Staging Results (.xlsx)")
        self.export_post_operation_btn.setObjectName("secondaryBtn")
        self.export_post_operation_btn.setStyleSheet("""
            QPushButton#secondaryBtn:disabled {
                background-color: #1e293b;
                color: #64748b;
                border: 1px solid #334155;
            }
        """)
        self.export_post_operation_btn.setEnabled(False)
        self.export_post_operation_btn.clicked.connect(self._export_post_operation_results)
        btn_layout.addWidget(self.export_post_operation_btn)
        self.export_btn = self.export_post_operation_btn

        self.open_cart_btn = QPushButton("🛒 Open Shopping Cart in Browser")
        self.open_cart_btn.setObjectName("secondaryBtn")
        self.open_cart_btn.hide()
        self.open_cart_btn.clicked.connect(self._open_shopping_cart)
        btn_layout.addWidget(self.open_cart_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel / Dismiss")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.order_btn = QPushButton("Stage Items to Supplier Cart")
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
            self.order_btn.setText(f"Stage {resolved_count} Items to Supplier Cart")
        else:
            self.order_btn.setEnabled(False)
            self.order_btn.setText("❌ No Eligible Items to Stage")

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
        self.order_btn.setText("Staging Batch Finished")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.staging_results_log = results.get("results", [])
        has_valid_staging = bool(
            self.staging_results_log
            and any(
                r.get("status") == "SUCCESS"
                or r.get("qty", 0) > 0
                or r.get("is_noop", False)
                for r in self.staging_results_log
            )
        )
        self.export_post_operation_btn.setEnabled(has_valid_staging)
        if has_valid_staging:
            self.export_post_operation_btn.setToolTip("Export staging results and cart outcomes to Excel (.xlsx)")
        else:
            self.export_post_operation_btn.setToolTip("No valid staged items available to export.")

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
    # COMMON ACTIONS: CART, SETTINGS, EXPORT
    # =========================================================================

    def _open_settings(self, vendor_id: str = "vendor_lion"):
        """Open plugin configuration dialog for the specified vendor or route to Vendor Plugins."""
        try:
            from ui.widgets.vendor_plugins_widget import PluginConfigDialog
            dlg = PluginConfigDialog(vendor_id=vendor_id, registry=self.registry, parent=self)
            dlg.exec()
            return
        except Exception:
            pass
        p = self.parent()
        if p and hasattr(p, "_open_settings"):
            p._open_settings("plugins")

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

    def _export_pre_order_plan(self):
        """Export Pre-Order Procurement Plan (.xlsx) before staging operations."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Omnix_Procurement_Plan_{timestamp}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pre-Order Procurement Plan (.xlsx)",
            default_name,
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        if self.is_mode_b_preview and self.plan and len(self.plan.results) > 0:
            report_data = ProcurementReportBuilder.build(
                plan=self.plan,
                staging_results=None,
                source_title=self.source_title,
            )
        else:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=self.all_shortages,
                staging_results=None,
                source_title=self.source_title,
            )

        try:
            ProcurementXLSXExporter.export(report_data, path)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Pre-Order Procurement Plan successfully exported to:\n{path}",
            )
            webbrowser.open(f"file:///{os.path.abspath(path)}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Failed to export pre-order plan:\n{str(e)}",
            )

    def _export_post_operation_results(self):
        """Export Staging Results (.xlsx) reflecting actual cart outcomes."""
        has_valid_staging = bool(
            self.staging_results_log
            and any(
                r.get("status") == "SUCCESS"
                or r.get("qty", 0) > 0
                or r.get("is_noop", False)
                for r in self.staging_results_log
            )
        )
        if not has_valid_staging:
            QMessageBox.warning(
                self,
                "No Staging Results",
                "No procurement staging operation has produced exportable results yet. Export is available after staging completes with valid items.",
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Omnix_Procurement_Results_{timestamp}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Procurement Staging Results (.xlsx)",
            default_name,
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        if self.is_mode_b_preview and self.plan and len(self.plan.results) > 0:
            staged_results = [r for r in self.plan.results if r.selected_evaluation is not None]
            export_plan = BOMProcurementPlan(results=staged_results if staged_results else self.plan.results)
            report_data = ProcurementReportBuilder.build(
                plan=export_plan,
                staging_results=self.staging_results_log,
                source_title=self.source_title,
            )
        else:
            # Export the actual staged purchase items that were selected and executed
            staged_items = self.get_selected_orderable_items()
            if not staged_items:
                staged_names = {str(r.get("part") or "").strip().upper() for r in (self.staging_results_log or [])}
                staged_items = [
                    it for it in self.all_shortages
                    if str(it.get("part_name") or it.get("part_number") or "").strip().upper() in staged_names
                ]
            if not staged_items:
                staged_items = [it for it in self.all_shortages if it in self.orderable_items]

            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=staged_items,
                staging_results=self.staging_results_log,
                source_title=self.source_title,
            )

        try:
            ProcurementXLSXExporter.export(report_data, path)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Procurement Staging Results successfully exported to:\n{path}",
            )
            webbrowser.open(f"file:///{os.path.abspath(path)}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Failed to export staging results:\n{str(e)}",
            )

    def closeEvent(self, event):
        if self.discovery_worker and self.discovery_worker.isRunning():
            self.discovery_worker.terminate()
            self.discovery_worker.wait(500)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(500)
        super().closeEvent(event)
