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
from PyQt6.QtGui import QColor, QFont, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QAbstractItemView,
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





class OrderWorkerThread(QThread):
    """
    Background worker thread to execute procurement staging:
    - Mode A: Batch staging directly via ProcurementBridge and vendor adapters.
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
        self._is_cancelled = False

    def cancel(self):
        """Signals the background staging loop to stop cleanly."""
        self._is_cancelled = True

    def run(self):
        if self.items:
            self._run_direct_items()
        else:
            self.finished_signal.emit({
                "success": False,
                "message": "No items provided for staging.",
                "successful_count": 0,
                "failed_count": 0,
                "noop_count": 0,
                "staged_count": 0,
                "results": [],
            })

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
                cancel_check=lambda: self._is_cancelled,
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
        row_count = len(self.items)
        self.resize(960, min(650, max(360, 200 + row_count * 52)))
        self.setMinimumWidth(880)
        self.setMinimumHeight(320)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b101b;
                color: #f8fafc;
            }
            QLabel {
                color: #f8fafc;
            }
            QTableWidget {
                background-color: #0f172a;
                alternate-background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 8px;
                gridline-color: #1e293b;
                color: #f8fafc;
                font-size: 13px;
                selection-background-color: transparent;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 12px;
                border: none;
                border-bottom: 1px solid #334155;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 12px;
                color: #f8fafc;
                font-size: 13px;
                min-height: 28px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton#primaryBtn {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton#primaryBtn:hover { background-color: #10b981; }
            QPushButton#secondaryBtn {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #94a3b8;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton#secondaryBtn:hover { background-color: #334155; color: #f8fafc; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QLabel("⚡ Select Supplier Link for Multi-Link Components")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(header)

        desc = QLabel(
            "The following component(s) have multiple eligible supplier options configured. "
            "Please select which supplier link to use for this procurement operation:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(desc)

        self.combo_boxes: List[Tuple[Dict[str, Any], QComboBox]] = []

        table = QTableWidget(len(self.items), 4)
        table.setHorizontalHeaderLabels([
            "Part / Designator",
            "Needed",
            "Description",
            "Select Supplier Link",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        for row_idx, it in enumerate(self.items):
            p_name = it.get("part_name") or it.get("part_number") or it.get("designator") or "Component"
            needed = it.get("needed_qty") if it.get("needed_qty") is not None else it.get("shortage_qty", 1)
            desc_txt = it.get("description") or it.get("comment") or ""
            desig_txt = it.get("designator") or ""

            part_display = p_name
            if desig_txt and desig_txt != p_name:
                part_display += f" [{desig_txt}]"

            it_part = QTableWidgetItem(part_display)
            it_part.setForeground(QColor("#f8fafc"))
            f = it_part.font()
            f.setBold(True)
            it_part.setFont(f)
            table.setItem(row_idx, 0, it_part)

            it_needed = QTableWidgetItem(f"{needed} pcs")
            it_needed.setForeground(QColor("#fbbf24"))
            table.setItem(row_idx, 1, it_needed)

            it_desc = QTableWidgetItem(desc_txt)
            it_desc.setForeground(QColor("#94a3b8"))
            it_desc.setToolTip(desc_txt)
            table.setItem(row_idx, 2, it_desc)

            combo = QComboBox()
            combo.setMinimumWidth(380)
            combo.addItem("-- Select Supplier Link --", None)

            # Collect all distinct supplier-link records (tuple of vid, url, display_name)
            all_link_records: List[Tuple[str, str, str]] = []
            supplier_links = it.get("supplier_links") or ()
            if supplier_links:
                for sl in supplier_links:
                    vid = getattr(sl, "vendor_id", None) or ""
                    u = getattr(sl, "url", "") or ""
                    disp = getattr(sl, "display_name", "") or getattr(sl, "vendor_label", "")
                    if u:
                        all_link_records.append((vid, u, disp))

            if not all_link_records:
                if it.get("eligible_records"):
                    all_link_records.extend(it.get("eligible_records"))
                elif it.get("all_vendor_links") or it.get("vendor_links"):
                    for vid, u in (it.get("all_vendor_links") or it.get("vendor_links") or {}).items():
                        all_link_records.append((vid, u, ""))
                else:
                    raw_link = str(it.get("raw_link") or it.get("link", "")).strip()
                    parsed = parse_vendor_links(raw_link, registry=self.registry)
                    if parsed.is_valid:
                        for entry in parsed.entries:
                            all_link_records.append((entry.vendor_id, entry.url, entry.display_name or entry.vendor_label))
                    else:
                        for vid, u in (it.get("all_vendor_links") or it.get("vendor_links") or {}).items():
                            all_link_records.append((vid, u, ""))

            from core.procurement.bridge import ProcurementBridge

            model = QStandardItemModel()
            placeholder_item = QStandardItem("-- Select Supplier Link --")
            placeholder_item.setData(None, Qt.ItemDataRole.UserRole)
            model.appendRow(placeholder_item)

            eligible_indices = []

            for record_idx, (vid, url, custom_disp) in enumerate(all_link_records):
                v_name = (
                    self.registry.get_vendor_name(vid)
                    if hasattr(self.registry, "get_vendor_name")
                    else vid.replace("vendor_", "").title()
                )
                if custom_disp and custom_disp.lower() != v_name.lower():
                    base_label = f"{v_name} ({custom_disp})"
                else:
                    base_label = v_name

                p_stat = ProcurementBridge.get_plugin_status(vid, self.registry)
                is_eligible = (p_stat == "READY FOR ORDER")

                if is_eligible:
                    # If multiple links from the same vendor, show the URL or product slug to distinguish
                    same_vid_count = sum(1 for v, _, _ in all_link_records if v == vid)
                    if same_vid_count > 1:
                        url_tail = url.split('/')[-1] if '/' in url else url
                        item_text = f"{base_label} ({url_tail[:30]})"
                    else:
                        item_text = base_label
                    item = QStandardItem(item_text)
                    item.setData((vid, url), Qt.ItemDataRole.UserRole)
                    item.setToolTip(f"Supplier: {v_name}\nURL: {url}\nStatus: READY FOR ORDER")
                    item.setEnabled(True)
                    item.setSelectable(True)
                    model.appendRow(item)
                    eligible_indices.append(model.rowCount() - 1)
                else:
                    item_text = f"{base_label} — Disabled ({p_stat})"
                    item = QStandardItem(item_text)
                    item.setData(None, Qt.ItemDataRole.UserRole)
                    item.setToolTip(f"Supplier: {v_name}\nURL: {url}\nUnavailable: {p_stat}")
                    item.setEnabled(False)
                    item.setSelectable(False)
                    model.appendRow(item)

            combo.setModel(model)

            # Pre-select if already chosen previously or if exactly 1 eligible link
            curr_sel_url = it.get("selected_url")
            preselected = False
            if curr_sel_url:
                for row_idx in range(1, model.rowCount()):
                    rdata = model.item(row_idx).data(Qt.ItemDataRole.UserRole)
                    if isinstance(rdata, tuple) and rdata[1] == curr_sel_url:
                        combo.setCurrentIndex(row_idx)
                        preselected = True
                        break

            if not preselected and len(eligible_indices) == 1:
                combo.setCurrentIndex(eligible_indices[0])

            table.setCellWidget(row_idx, 3, combo)
            self.combo_boxes.append((it, combo))

        layout.addWidget(table, 1)

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
            it["selected_vendor_id"] = selected_vid
            it["selected_url"] = selected_url
            it["vendor_id"] = selected_vid
            it["link"] = selected_url

        self.accept()


class OrderPreviewDialog(QDialog):
    """
    Unified Procurement & Order Confirmation Dialog supporting:
    Mode A (Database-Aware / Shortages): Instant high-contrast confirmation table
    with direct store link validation, non-blocking batch ordering, browser cart links,
    and atomic inventory update. Mode A is the sole supported workflow.
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
        self.staging_results_log: Optional[List[Dict[str, Any]]] = None
        self.active_row_idx: Optional[int] = None
        self._is_updating_table: bool = False
        self.plan = plan or BOMProcurementPlan(results=[])
        self.results = []

        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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

            # Preserve all parsed vendor links for distinction and display
            all_links = {vid: e.url for vid, e in parsed.links.items()}
            it["all_vendor_links"] = all_links

            # Also check supplier_links records on component
            supplier_links = it.get("supplier_links") or ()
            eligible_records = []
            reg = self.registry

            if supplier_links:
                for sl in supplier_links:
                    vid = getattr(sl, "vendor_id", None) or ""
                    u = getattr(sl, "url", "") or ""
                    disp = getattr(sl, "display_name", "") or getattr(sl, "vendor_label", "")
                    if u and reg is not None and reg.has_vendor(vid) and reg.is_vendor_enabled(vid):
                        eligible_records.append((vid, u, disp))

            if not eligible_records:
                for entry in parsed.entries:
                    vid = entry.vendor_id
                    u = entry.url
                    disp = entry.display_name or entry.vendor_label
                    if u and reg is not None and reg.has_vendor(vid) and reg.is_vendor_enabled(vid):
                        eligible_records.append((vid, u, disp))

            it["eligible_records"] = eligible_records
            # Eligible vendor links dict (for backwards compatibility)
            eligible_links: Dict[str, str] = {vid: u for vid, u, _ in eligible_records}
            it["vendor_links"] = eligible_links

            if len(eligible_records) == 1:
                # Exactly one eligible link: use without unnecessary prompting
                vid, sel_url, _ = eligible_records[0]
                it["vendor_id"] = vid
                it["selected_vendor_id"] = vid
                it["selected_url"] = sel_url
                it["link"] = sel_url
                it["is_multi_vendor"] = False
                if vid == "vendor_lion":
                    self.lion_items.append(it)
                else:
                    self.other_vendor_items.append(it)
            elif len(eligible_records) > 1:
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
                f"Action: Update store URLs to a registered vendor in Inventory\n\n"
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
                f"Action: Add vendor product links in Inventory\n\n"
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
                f"Items Not Found in Inventory ({len(self.missing_db_items)} items):\n"
                f"Action: Register these components into Inventory\n\n"
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

        self.order_btn.setEnabled(True)
        self.order_btn.setText(f"🛒 Add {sel_count} Items to Cart")

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
                link = str(it.get("link", "")).strip()
                raw_link = str(it.get("raw_link") or link).strip()
                parsed_raw = parse_vendor_links(raw_link or link, registry=self.registry)
                raw_entries = parsed_raw.entries if parsed_raw.is_valid else []
                is_raw_multi = len(raw_entries) > 1 or len(vendor_links) > 1
                is_multi = it.get("is_multi_vendor") or is_raw_multi
                selected_vid = it.get("selected_vendor_id")

                item5 = QTableWidgetItem()
                item5.setFont(font_txt)
                item6 = QTableWidgetItem()
                item6.setFont(font_txt)

                if is_multi:
                    v_names = [self._get_vendor_name(v) for v in sorted(vendor_links.keys())] if vendor_links else [self._get_vendor_name(e.vendor_id) for e in raw_entries]
                    if selected_vid and (selected_vid in vendor_links or any(e.vendor_id == selected_vid for e in raw_entries)):
                        sel_name = self._get_vendor_name(selected_vid)
                        sel_url = it.get("selected_url") or (vendor_links.get(selected_vid) if vendor_links else "")
                        item5.setText(f"{sel_name}: {sel_url}")
                        item5.setForeground(QColor("#38bdf8"))
                        item5.setToolTip(f"Selected: {sel_name}\nURL: {sel_url}\nAvailable: {', '.join(v_names)}")
                        item6.setText(f"✅ {sel_name} Selected")
                        item6.setForeground(QColor("#34d399"))
                    elif vendor_links:
                        item5.setText(f"⚡ Multi-Vendor ({', '.join(v_names)})")
                        item5.setForeground(QColor("#a78bfa"))
                        tt = "Multiple vendor options configured:\n" + "\n".join(f"• {self._get_vendor_name(v)}: {u}" for v, u in vendor_links.items()) + "\n\nDouble-click row to select vendor."
                        item5.setToolTip(tt)
                        item6.setText("⚡ Selection Required")
                        item6.setForeground(QColor("#a78bfa"))
                    else:
                        # Multi-vendor links exist but NO plugin is currently enabled
                        item5.setText(f"⚡ Multi-Vendor ({', '.join(v_names)})")
                        item5.setForeground(QColor("#f97316"))
                        from core.procurement.bridge import ProcurementBridge
                        eval_lines = []
                        for e in raw_entries:
                            st = ProcurementBridge.get_plugin_status(e.vendor_id, self.registry)
                            eval_lines.append(f"• {self._get_vendor_name(e.vendor_id)}: {st} ({e.url})")
                        tt = "Multiple vendor options configured (None available for ordering):\n" + "\n".join(eval_lines)
                        item5.setToolTip(tt)
                        item6.setText("PLUGIN NOT INSTALLED" if all(ProcurementBridge.get_plugin_status(e.vendor_id, self.registry) == "PLUGIN NOT INSTALLED" for e in raw_entries) else "PLUGINS UNAVAILABLE")
                        item6.setForeground(QColor("#f87171"))
                else:
                    vid = it.get("vendor_id")
                    if not vid and hasattr(self.registry, "get_vendor_for_url"):
                        vid = self.registry.get_vendor_for_url(link, enabled_only=False)

                    if not link or not link.strip():
                        item5.setText("❌ Blank Store Link")
                        item5.setForeground(QColor("#f87171"))
                        item5.setToolTip("Store link is missing in database. Please add vendor URL in Inventory.")
                        item6.setText("⚠️ Blank Link")
                        item6.setForeground(QColor("#fbbf24"))
                    elif not link.startswith(("http://", "https://")):
                        item5.setText(f"❌ INVALID LINK")
                        item5.setForeground(QColor("#f87171"))
                        item5.setToolTip(f"Invalid URL syntax: {link}")
                        item6.setText("❌ INVALID LINK")
                        item6.setForeground(QColor("#f87171"))
                    else:
                        from core.procurement.bridge import ProcurementBridge
                        p_stat = ProcurementBridge.get_plugin_status(vid, self.registry)
                        v_display = self._get_vendor_name(vid) if vid else "Vendor"
                        item5.setText(link)

                        if p_stat == "READY FOR ORDER":
                            item5.setForeground(QColor("#38bdf8"))
                            item5.setToolTip(f"{v_display} link (READY FOR ORDER):\n{link}")
                            item6.setText("READY FOR ORDER")
                            item6.setForeground(QColor("#34d399"))
                        elif p_stat == "PLUGIN DISABLED":
                            item5.setForeground(QColor("#f97316"))
                            item5.setToolTip(f"{v_display} plugin is disabled in Vendor Plugins:\n{link}")
                            item6.setText("PLUGIN DISABLED")
                            item6.setForeground(QColor("#f97316"))
                        elif p_stat == "PLUGIN NOT REGISTERED":
                            item5.setForeground(QColor("#f97316"))
                            item5.setToolTip(f"{v_display} plugin is installed but not registered in registry:\n{link}")
                            item6.setText("PLUGIN NOT REGISTERED")
                            item6.setForeground(QColor("#f97316"))
                        else:
                            item5.setForeground(QColor("#f87171"))
                            item5.setToolTip(f"No plugin installed for {v_display}:\n{link}\nInstall plugin from Vendor Plugins.")
                            item6.setText("PLUGIN NOT INSTALLED")
                            item6.setForeground(QColor("#f87171"))

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
        eligible_records = raw_it.get("eligible_records") or []
        vendor_links = raw_it.get("vendor_links") or {}
        if len(eligible_records) > 1 or len(vendor_links) > 1 or raw_it.get("is_multi_vendor"):
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
            if (len(it.get("eligible_records") or []) > 1 or len(it.get("vendor_links") or {}) > 1 or it.get("is_multi_vendor"))
            and not it.get("selected_url")
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
        self.order_btn.setText("⏳ Adding to Cart...")
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
        self.order_btn.setEnabled(False)
        self.order_btn.setText("✅ Added to Cart")
        self.order_btn.setStyleSheet("""
            QPushButton {
                background-color: #064e3b;
                border: 1px solid #10b981;
                color: #34d399;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
        """)
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
        """Open shopping cart URL in user's default browser exclusively for vendors of ordered/selected items."""
        target_vendors = set()
        # Strictly look at currently selected items or items that were successfully staged
        items_to_scan = self.get_selected_orderable_items()
        if not items_to_scan:
            items_to_scan = [it for it in (self.all_shortages or []) if it.get("_selected")]

        for it in (items_to_scan or []):
            link = str(it.get("selected_url") or it.get("link", "")).strip()
            vid = it.get("selected_vendor_id") or it.get("vendor_id") or (self.registry.get_vendor_for_url(link, enabled_only=True) if link else None)
            if vid:
                target_vendors.add(vid)

        if not target_vendors and self.staging_results_log:
            for r in self.staging_results_log:
                vid = r.get("vendor_id")
                if vid and (r.get("status") == "SUCCESS" or r.get("qty", 0) > 0):
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

        if self.all_shortages:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=self.all_shortages,
                source_title=self.source_title,
                staging_results=self.staging_results_log,
            )
        elif self.plan and self.plan.results:
            report_data = ProcurementReportBuilder.build(
                plan=self.plan,
                source_title=self.source_title,
                staging_results=self.staging_results_log,
            )
        else:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=[],
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

        if self.all_shortages:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=self.all_shortages,
                staging_results=None,
                source_title=self.source_title,
            )
        elif self.plan and self.plan.results:
            report_data = ProcurementReportBuilder.build(
                plan=self.plan,
                staging_results=None,
                source_title=self.source_title,
            )
        else:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=[],
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

        if staged_items:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=staged_items,
                staging_results=self.staging_results_log,
                source_title=self.source_title,
            )
        elif self.plan and self.plan.results:
            report_data = ProcurementReportBuilder.build(
                plan=self.plan,
                staging_results=self.staging_results_log,
                source_title=self.source_title,
            )
        else:
            report_data = ProcurementReportBuilder.build_from_shortages(
                shortages=[],
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
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(500)
        super().closeEvent(event)
