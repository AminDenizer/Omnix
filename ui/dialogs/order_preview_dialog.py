"""
Omnix UI — Multi-Vendor Order Preview & Candidate Selection Dialog
Governing GAP: GAP-07 (Multi-Candidate Comparison & Alternative Selection)
Reuses UniversalProcurementOrchestrator, CandidateEvaluation, and GAP-13 Delta Synchronization.
"""

import os
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
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


class OrderWorkerThread(QThread):
    """Background worker thread to execute multi-vendor procurement staging with user-selected candidates."""

    progress_signal = pyqtSignal(int, int, str, int, str)  # current, total, part_name, qty, msg
    finished_signal = pyqtSignal(dict)

    def __init__(
        self,
        results: List[RequestProcurementResult],
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
    ):
        super().__init__()
        self.results = results
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator()

    def run(self):
        total = len(self.results)
        successful_count = 0
        failed_count = 0
        noop_count = 0
        staged_count = 0
        results_log = []

        # Filter items with a valid selected evaluation
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


class OrderPreviewDialog(QDialog):
    """
    Master-Detail Order Preview & Multi-Candidate Selection Dialog.
    Enables users to review all discovered vendor candidate offers per BOM component,
    compare factual parameters without hidden rankings, and override candidate selection.
    Governing GAP: GAP-07.
    """

    def __init__(
        self,
        all_shortages: Optional[List[Dict[str, Any]]] = None,
        orderable_items: Optional[List[Dict[str, Any]]] = None,
        missing_db_items: Optional[List[Dict[str, Any]]] = None,
        plan: Optional[BOMProcurementPlan] = None,
        source_title: str = "Procurement Order Preview",
        inventory_loader=None,
        on_stock_updated=None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.all_shortages = all_shortages if all_shortages is not None else (orderable_items or [])
        self.missing_db_items = missing_db_items or []
        self.source_title = source_title
        self.inventory_loader = inventory_loader
        self.on_stock_updated = on_stock_updated
        self.registry = registry or default_registry
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator(registry=self.registry)

        self.worker: Optional[OrderWorkerThread] = None
        self.staging_results_log: Optional[List[Dict[str, Any]]] = None
        self._has_updated_inventory = False
        self.active_row_idx: Optional[int] = None

        # Build or wrap procurement results
        if plan is not None:
            self.plan = plan
            self.results = plan.results
        else:
            self.results = self._generate_results_from_items(self.all_shortages)
            self.plan = BOMProcurementPlan(results=self.results)

        self.setWindowTitle(f"🛒 Procurement Preview & Multi-Candidate Selection — {source_title}")
        self.resize(1140, 720)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _generate_results_from_items(self, items: List[Dict[str, Any]]) -> List[RequestProcurementResult]:
        """Convert input item dicts into formal RequestProcurementResult objects with full candidate gathering."""
        requests: List[ProcurementRequest] = []
        for it in items:
            try:
                req = ProcurementBridge.item_to_request(it, registry=self.registry)
                requests.append(req)
            except Exception:
                continue

        if not requests:
            return []

        plan = self.orchestrator.build_plan(requests)
        return plan.results

    def _init_ui(self):
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

        # Set initial splitter proportions (55% master, 45% detail)
        splitter.setSizes([320, 240])
        layout.addWidget(splitter)

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

        layout.addWidget(self.status_ribbon)

        # Progress Bar & Progress Label
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
        self.order_btn.clicked.connect(self._start_order)
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
            self.order_btn.setText(f"🛒 Order {resolved_count} Resolved Items Across Vendors")
            self.order_btn.setEnabled(True)
        else:
            self.order_btn.setText("🛒 No Eligible Items to Order")
            self.order_btn.setEnabled(False)

        for c in range(9):
            self.master_table.resizeColumnToContents(c)

    def _on_master_row_selected(self):
        selected_rows = self.master_table.selectionModel().selectedRows()
        if not selected_rows:
            self.detail_table.setRowCount(0)
            self.detail_header_lbl.setText("📦 Candidate Offers & Alternatives (Select a row above):")
            self.active_row_idx = None
            return

        row_idx = selected_rows[0].row()
        if 0 <= row_idx < len(self.results):
            self.active_row_idx = row_idx
            self._render_detail_table(self.results[row_idx])

    def _render_detail_table(self, res: RequestProcurementResult):
        req = res.request
        evals = res.evaluations
        sel = res.selected_evaluation

        des = str(req.metadata.get("designator") or req.source or "")
        self.detail_header_lbl.setText(
            f"📦 Discovered Candidate Offers for '{req.part_number}' {f'({des})' if des else ''} — {len(evals)} offer(s):"
        )

        self.detail_table.setRowCount(len(evals))
        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        for r_idx, ev in enumerate(evals):
            cand = ev.candidate
            is_selected = (sel is not None and sel == ev)

            # 0. Selection Radio
            radio = QRadioButton()
            radio.setEnabled(ev.is_eligible)
            radio.setChecked(is_selected)
            radio.toggled.connect(lambda checked, idx=r_idx: self._on_candidate_radio_toggled(idx, checked))
            r_box = QWidget()
            r_lay = QHBoxLayout(r_box)
            r_lay.setContentsMargins(0, 0, 0, 0)
            r_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            r_lay.addWidget(radio)
            self.detail_table.setCellWidget(r_idx, 0, r_box)

            # 1. Vendor
            v_name = cand.vendor_id.replace("vendor_", "").title()
            item_v = QTableWidgetItem(v_name)
            item_v.setFont(font_txt)
            self.detail_table.setItem(r_idx, 1, item_v)

            # 2. SKU
            self.detail_table.setItem(r_idx, 2, QTableWidgetItem(cand.product_ref.vendor_sku or "—"))

            # 3. MPN
            self.detail_table.setItem(r_idx, 3, QTableWidgetItem(cand.part_number or "—"))

            # 4. Manufacturer
            self.detail_table.setItem(r_idx, 4, QTableWidgetItem(cand.manufacturer or "—"))

            # 5. Package / Footprint
            pkg_str = f"{cand.package or ''} / {cand.footprint or ''}".strip(" /") or "—"
            self.detail_table.setItem(r_idx, 5, QTableWidgetItem(pkg_str))

            # 6. Stock
            stk_str = str(cand.stock_quantity) if cand.in_stock else "Out of Stock"
            item_stk = QTableWidgetItem(stk_str)
            item_stk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_stk.setFont(font_num)
            item_stk.setForeground(QColor("#34d399") if cand.in_stock else QColor("#f87171"))
            self.detail_table.setItem(r_idx, 6, item_stk)

            # 7. MOQ & 8. Step
            moq_val = cand.order_constraints.moq_raw or 1
            step_val = cand.order_constraints.packaging_step_raw or 1
            item_moq = QTableWidgetItem(str(moq_val))
            item_moq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_moq.setFont(font_num)
            self.detail_table.setItem(r_idx, 7, item_moq)

            item_step = QTableWidgetItem(str(step_val))
            item_step.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_step.setFont(font_num)
            self.detail_table.setItem(r_idx, 8, item_step)

            # 9. Unit Price
            up_str = f"{ev.effective_unit_price_irr:,} IRR" if ev.effective_unit_price_irr is not None else "—"
            item_up = QTableWidgetItem(up_str)
            item_up.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_up.setFont(font_num)
            self.detail_table.setItem(r_idx, 9, item_up)

            # 10. Total Cost
            tc_str = f"{ev.effective_total_price_irr:,} IRR" if ev.effective_total_price_irr is not None else "—"
            item_tc = QTableWidgetItem(tc_str)
            item_tc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_tc.setFont(font_num)
            item_tc.setForeground(QColor("#38bdf8") if ev.is_eligible else QColor("#94a3b8"))
            self.detail_table.setItem(r_idx, 10, item_tc)

            # 11. Status / Eligibility
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
                self._render_detail_table(res)

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

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _open_shopping_cart(self):
        cart_urls = {
            "vendor_lion": "https://lionelectronic.ir/orders/cart",
            "vendor_javan": "https://javanelec.com/cart",
            "vendor_roboeq": "https://roboeq.ir/cart",
        }
        opened = set()
        for r in self.results:
            if r.selected_evaluation:
                v_id = r.selected_evaluation.candidate.vendor_id
                if v_id in cart_urls and v_id not in opened:
                    webbrowser.open(cart_urls[v_id])
                    opened.add(v_id)
        if not opened:
            webbrowser.open("https://lionelectronic.ir/orders/cart")

    def _start_order(self):
        orderable = [r for r in self.results if r.selected_evaluation is not None and r.selected_evaluation.is_eligible]
        if not orderable:
            QMessageBox.warning(self, "No Eligible Items", "No resolved and eligible items are available to order.")
            return

        self.order_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, len(orderable))
        self.progress_bar.setValue(0)
        self.progress_lbl.show()
        self.progress_lbl.setText("Initiating multi-vendor procurement staging with user-selected candidates...")

        self.worker = OrderWorkerThread(self.results, orchestrator=self.orchestrator)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current: int, total: int, part_name: str, qty: int, msg: str):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(f"[{current}/{total}] {part_name}: {msg}")

    def _on_finished(self, results: Dict[str, Any]):
        self.order_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.confirm_payment_btn.show()
        self.confirm_payment_btn.setEnabled(True)

        self.staging_results_log = results.get("results")
        succ_count = results.get("successful_count", 0)
        noop_count = results.get("noop_count", 0)

        if results.get("success"):
            self.progress_lbl.setText(f"✅ Staging completed! ({succ_count} items staged/satisfied)")
            self.progress_lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold;")
            QMessageBox.information(
                self,
                "Procurement Staging Complete",
                f"Successfully staged {succ_count} items across vendor shopping carts ({noop_count} already satisfied)!\n\n"
                f"Click 'Open Shopping Cart in Browser' to review and complete checkout.",
            )
        else:
            self.progress_lbl.setText(f"⚠️ Staging completed with issues ({succ_count} ok, {results.get('failed_count', 0)} failed)")
            self.progress_lbl.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: bold;")
            QMessageBox.warning(
                self,
                "Procurement Staging Incomplete",
                f"Staging results:\n{results.get('message')}",
            )

        self._populate_master_table()

    def _show_export_menu(self):
        """Displays format selection menu for deterministic report export."""
        menu = QMenu(self)
        act_xlsx = menu.addAction("📊 Export as Excel Workbook (*.xlsx)")
        act_xlsx.triggered.connect(lambda: self._export_report("xlsx"))

        act_pdf = menu.addAction("📑 Export as PDF Document (*.pdf)")
        act_pdf.triggered.connect(lambda: self._export_report("pdf"))

        act_csv = menu.addAction("📋 Export as CSV Table (*.csv)")
        act_csv.triggered.connect(lambda: self._export_report("csv"))

        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def _export_report(self, fmt: str):
        """Pure functional report generation and file export."""
        report_data = ProcurementReportBuilder.build(
            plan=self.plan,
            staging_results=self.staging_results_log,
            source_title=self.source_title,
        )

        clean_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in self.source_title.replace(" ", "_"))
        clean_title = clean_title.strip("_") or "Procurement_Report"

        if fmt == "xlsx":
            file_filter = "Excel Workbook (*.xlsx)"
            default_ext = ".xlsx"
        elif fmt == "pdf":
            file_filter = "PDF Document (*.pdf)"
            default_ext = ".pdf"
        elif fmt == "csv":
            file_filter = "CSV Spreadsheet (*.csv)"
            default_ext = ".csv"
        else:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save Procurement Report ({fmt.upper()})",
            f"Omnix_{clean_title}{default_ext}",
            file_filter,
        )
        if not file_path:
            return

        try:
            if fmt == "xlsx":
                ProcurementXLSXExporter.export(report_data, file_path)
            elif fmt == "pdf":
                ProcurementPDFExporter.export(report_data, file_path)
            elif fmt == "csv":
                ProcurementCSVExporter.export(report_data, file_path)

            QMessageBox.information(
                self,
                "Report Exported Successfully",
                f"✅ Procurement report successfully saved to:\n\n{file_path}",
            )
            if os.path.exists(file_path):
                webbrowser.open(f"file:///{os.path.abspath(file_path)}")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"An error occurred while exporting the report:\n\n{str(e)}",
            )

    def _confirm_payment_and_add_stock(self):
        if self._has_updated_inventory:
            QMessageBox.information(self, "Already Updated", "Inventory stock has already been updated for this batch.")
            return

        if not self.inventory_loader:
            QMessageBox.warning(self, "No Database", "Active inventory database reference is not available.")
            return

        items_to_add = []
        for r in self.results:
            if r.selected_evaluation and r.selected_evaluation.is_eligible:
                cand = r.selected_evaluation.candidate
                qty = r.selected_evaluation.effective_quantity
                if qty > 0:
                    items_to_add.append({
                        "part_number": cand.part_number,
                        "part_name": cand.part_number,
                        "actual_ordered_qty": qty,
                        "order_success": True,
                    })

        if not items_to_add:
            QMessageBox.information(self, "No Items Ordered", "No items were successfully staged in this batch.")
            return

        lines = [f"• <b>{it['part_number']}</b>: +{it['actual_ordered_qty']} pcs" for it in items_to_add[:15]]
        items_text = "<br>".join(lines)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Payment & Stock Update")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(
            f"<b>Did you complete and pay for this order on the vendor storefront(s)?</b><br><br>"
            f"The following successfully ordered quantities (<b>{len(items_to_add)} item(s)</b>) "
            f"will be added to <code>Quantity in Stock</code> in <code>Inventory.xlsx</code>:<br><br>"
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

        count, msg = self.inventory_loader.batch_increment_stock(items_to_add)
        if count > 0:
            self._has_updated_inventory = True
            self.confirm_payment_btn.setText("✅ Stock Added to Inventory")
            self.confirm_payment_btn.setEnabled(False)
            self.confirm_payment_btn.setStyleSheet("background-color: #1e293b; color: #34d399; font-weight: bold;")
            QMessageBox.information(
                self, "Inventory Updated", f"✅ Success!\n\n{count} item(s) have been added to current stock in Inventory.xlsx."
            )
            if self.on_stock_updated:
                self.on_stock_updated()
        else:
            QMessageBox.warning(self, "Update Failed", f"Could not update stock in Inventory.xlsx:\n{msg}")

