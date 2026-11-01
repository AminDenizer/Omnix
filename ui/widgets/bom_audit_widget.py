import os
import webbrowser
import datetime
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QSpinBox, QLineEdit, QFrame,
    QFileDialog, QHeaderView, QApplication, QMenu, QComboBox,
    QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QMarginsF, QSizeF
from PyQt6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent, QTextDocument, QPageSize, QPageLayout, QIntValidator
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMAuditor, BOMAuditResult, BOMItem
from core.procurement.models import ProcurementMode, ManufacturerRule, ManufacturerDataState
from excel_loader import ExcelDataLoader
from core.procurement.reporting import (
    ProcurementReportBuilder,
    ProcurementXLSXExporter,
)
from ui.dialogs.order_preview_dialog import OrderPreviewDialog
from ui.dialogs.brand_rule_dialog import BrandRuleDialog


class DropZoneFrame(QFrame):
    """Modern unified Drag-and-Drop file upload zone for Altium BOM Excel files."""

    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("dropZoneCard")
        self.setStyleSheet("""
            QFrame#dropZoneCard {
                background-color: #0f172a;
                border: 2px dashed #38bdf8;
                border-radius: 12px;
                padding: 36px 24px;
            }
            QFrame#dropZoneCard:hover {
                background-color: #13203b;
                border-color: #60a5fa;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        icon_lbl = QLabel("📂")
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent; border: none;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("Drag & Drop Altium BOM Excel File Here")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        sub_lbl = QLabel("or click anywhere in this box to browse and select a file (.xlsx)")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; background: transparent; border: none;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_browse()
        super().mousePressEvent(event)

    def _on_browse(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Altium BOM Excel File",
            "",
            "Excel Files (*.xlsx *.xls *.xlsm)"
        )
        if file_path and os.path.exists(file_path):
            self.fileDropped.emit(file_path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.xlsx', '.xls', '.xlsm')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.xlsx', '.xls', '.xlsm')) and os.path.exists(file_path):
                self.fileDropped.emit(file_path)
                event.acceptProposedAction()
                return
        event.ignore()
from ui.widgets.number_stepper import NumberStepperWidget


class BOMAuditWidget(QWidget):
    """
    Altium BOM Project Assembly Auditor Tab:
    Mode A (Database-Aware): Reconciles BOM components against active inventory database,
    calculates net shortages, and links to registered store URLs. Mode A is the sole supported workflow.
    """

    bomLoaded = pyqtSignal(object)
    bomUnloaded = pyqtSignal()

    def __init__(self, inventory_loader: Optional[Any] = None, parent=None):
        super().__init__(parent)
        self.inventory = inventory_loader
        self.repository = inventory_loader
        self.current_bom_path: Optional[str] = None
        self.audit_result: Optional[BOMAuditResult] = None
        self.current_mode: ProcurementMode = ProcurementMode.DATABASE_AWARE
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def set_repository(self, repository: Any):
        """Updates the active inventory repository and recalculates the audit if a BOM is loaded."""
        self.inventory = repository
        self.repository = repository
        if self.current_bom_path and os.path.exists(self.current_bom_path):
            self._recalculate_audit()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 8)
        main_layout.setSpacing(10)

        # 1. Top Control Bar: Shown ONLY when a BOM file is loaded
        self.top_card = QFrame()
        self.top_card.setObjectName("ribbonFrame")
        top_layout = QHBoxLayout(self.top_card)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(14)

        self.file_info_lbl = QLabel("No Altium BOM Loaded")
        self.file_info_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        top_layout.addWidget(self.file_info_lbl)

        # Clear / Unload Button (✖)
        self.clear_btn = QPushButton("✖ Clear BOM")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.35);
                color: #f87171;
                font-weight: 600;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
        """)
        self.clear_btn.clicked.connect(self.unload_bom)
        top_layout.addWidget(self.clear_btn)

        top_layout.addStretch()

        # Deduct Internal Stock Checkbox
        self.stock_checkbox = QCheckBox("Deduct internal stock")
        self.stock_checkbox.setChecked(True)
        self.stock_checkbox.setMinimumHeight(28)
        self.stock_checkbox.setStyleSheet("""
            QCheckBox {
                font-weight: 600;
                color: #e2e8f0;
                font-size: 12px;
                spacing: 8px;
                padding-right: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid #334155;
                background-color: #0f172a;
            }
            QCheckBox::indicator:checked {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
        """)
        self.stock_checkbox.toggled.connect(self._recalculate_audit)
        top_layout.addWidget(self.stock_checkbox)

        top_layout.addSpacing(10)

        # Board Assembly Quantity Multiplier (Modern Stepper with External Buttons)
        mult_lbl = QLabel("Boards to Assemble:")
        mult_lbl.setStyleSheet("font-weight: 600; color: #e2e8f0; font-size: 12px;")
        top_layout.addWidget(mult_lbl)

        self.multiplier_spin = NumberStepperWidget(value=1, min_val=1, max_val=100000)
        self.multiplier_spin.valueChanged.connect(self._recalculate_audit)
        top_layout.addWidget(self.multiplier_spin)

        main_layout.addWidget(self.top_card)
        self.top_card.hide()

        # 2. Unified Single Drop Zone (shown by default when no BOM is loaded)
        self.drop_zone = DropZoneFrame()
        self.drop_zone.fileDropped.connect(self.load_bom_file)
        main_layout.addWidget(self.drop_zone)

        # 3. KPI Summary Stats Ribbon (shown after BOM loaded)
        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("ribbonFrame")
        stats_layout = QHBoxLayout(self.stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        stats_layout.setSpacing(10)

        self.pill_total = QLabel("Total BOM Items: 0")
        self.pill_total.setProperty("class", "statPill")
        self.pill_total.setStyleSheet("background-color: #131d31; border: 1px solid #22324e; border-radius: 6px; padding: 4px 10px; font-weight: 500;")
        stats_layout.addWidget(self.pill_total)

        self.pill_in_stock = QLabel("✅ Fully Available: 0")
        self.pill_in_stock.setStyleSheet("background-color: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); color: #34d399; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        stats_layout.addWidget(self.pill_in_stock)

        self.pill_shortage = QLabel("⚠️ Shortages: 0")
        self.pill_shortage.setStyleSheet("background-color: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); color: #fbbf24; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        stats_layout.addWidget(self.pill_shortage)

        self.pill_not_in_db = QLabel("🔴 Not in Database: 0")
        self.pill_not_in_db.setStyleSheet("background-color: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        stats_layout.addWidget(self.pill_not_in_db)

        self.pill_missing_link = QPushButton("⚠️ Missing Links: 0")
        self.pill_missing_link.setObjectName("secondaryBtn")
        self.pill_missing_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pill_missing_link.setToolTip("Click to toggle filter for components with missing or blank store links")
        self.pill_missing_link.setStyleSheet("""
            QPushButton {
                background-color: rgba(249, 115, 22, 0.12);
                border: 1px solid rgba(249, 115, 22, 0.35);
                color: #f97316;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(249, 115, 22, 0.25);
            }
        """)
        self.pill_missing_link.clicked.connect(self._toggle_blank_link_filter)
        stats_layout.addWidget(self.pill_missing_link)

        stats_layout.addStretch()
        main_layout.addWidget(self.stats_frame)
        self.stats_frame.hide()

        # 4. Detailed Checklist Table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Status", "Designator", "Part Number", "Comment", "Footprint",
            "Qty / Board", "Total Needed", "In Stock", "Shortage", "Store Link"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        main_layout.addWidget(self.table)
        self.table.hide()

        # 5. Bottom Action Ribbon
        self.action_card = QFrame()
        self.action_card.setObjectName("ribbonFrame")
        action_layout = QHBoxLayout(self.action_card)
        action_layout.setContentsMargins(12, 8, 12, 8)
        action_layout.setSpacing(12)

        action_layout.addStretch()

        self.order_btn = QPushButton("🛒 Add Shortages to Cart")
        self.order_btn.clicked.connect(self._open_order_dialog)
        action_layout.addWidget(self.order_btn)

        main_layout.addWidget(self.action_card)
        self.action_card.hide()

    def _choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Altium BOM Excel File",
            "",
            "Excel Files (*.xlsx *.xls *.xlsm)"
        )
        if file_path and os.path.exists(file_path):
            self.load_bom_file(file_path)

    def load_bom_file(self, file_path: str):
        self.current_bom_path = file_path
        self._recalculate_audit()

    def _recalculate_audit(self):
        if not self.current_bom_path or not os.path.exists(self.current_bom_path):
            return

        multiplier = self.multiplier_spin.value()
        inv = self.inventory
        deduct = self.stock_checkbox.isChecked() if hasattr(self, "stock_checkbox") else True
        ok, msg, res = BOMAuditor.audit_bom(
            self.current_bom_path,
            inventory=inv,
            board_multiplier=multiplier,
            mode=self.current_mode,
            deduct_stock=deduct,
        )
        if not ok or not res:
            return

        self.audit_result = res
        self._render_results()
        self.bomLoaded.emit(self.audit_result)

    def unload_bom(self):
        """Unload active Altium BOM and reset view back to the drop zone."""
        self.current_bom_path = None
        self.audit_result = None
        self.top_card.hide()
        self.stats_frame.hide()
        self.table.hide()
        self.action_card.hide()
        self.drop_zone.show()
        self.bomUnloaded.emit()

    def _render_results(self):
        if not self.audit_result:
            return

        res = self.audit_result

        # Update Top Info
        self.file_info_lbl.setText(f"📄 Project BOM: <b>{res.file_name}</b> <span style='color:#94a3b8; font-size:11px;'>[Mode A (Database-Aware)]</span>")
        self.drop_zone.hide()
        self.top_card.show()
        self.stats_frame.show()
        self.table.show()
        self.action_card.show()

        # Update KPIs and Table Headers for Mode A
        self.pill_total.setText(f"Total BOM Items: {res.total_items_count}")
        self.pill_in_stock.setText(f"✅ Fully Available: {res.in_stock_count}")
        self.pill_shortage.setText(f"⚠️ Shortages: {res.shortage_count}")
        self.pill_not_in_db.setText(f"🔴 Not in Database: {res.not_in_db_count}")
        self.pill_missing_link.setText(f"⚠️ Missing Links: {res.blank_link_count}")

        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Status", "Designator", "Part Number", "Comment", "Footprint",
            "Qty / Board", "Total Needed", "In Stock", "Shortage", "Store Link"
        ])

        # Populate Table
        items = res.items
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(items))

        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        for row_idx, it in enumerate(items):
            # Mode A Columns
            # 0. Status Badge
            status_item = QTableWidgetItem()
            if not it.is_valid:
                status_item.setText("❌ INVALID")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip("; ".join(it.validation_errors))
            elif it.status == "IN_STOCK":
                status_item.setText("✅ IN STOCK")
                status_item.setForeground(QColor("#34d399"))
                status_item.setToolTip("Sufficient stock in database for this assembly batch.")
            elif it.status == "SHORTAGE":
                if it.is_orderable:
                    v_name = it.vendor_id.replace("vendor_", "").title() if it.vendor_id else "Vendor"
                    status_item.setText("⚠️ SHORTAGE")
                    status_item.setForeground(QColor("#fbbf24"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. {v_name} link ready for automated purchase.")
                elif it.link_type == "INVALID":
                    status_item.setText("❌ INVALID LINK")
                    status_item.setForeground(QColor("#f87171"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Store link ({it.link_domain}) is not a registered vendor. Please update in Inventory.")
                elif it.link and it.link.strip():
                    from core.procurement.bridge import ProcurementBridge
                    from core.procurement.registry import VendorRegistry
                    reg = VendorRegistry.get_default_registry()
                    p_stat = ProcurementBridge.get_plugin_status(it.vendor_id, reg)
                    status_item.setText(f"⚠️ {p_stat}")
                    status_item.setForeground(QColor("#f97316"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Plugin unavailable: {p_stat}.")
                else:
                    status_item.setText("⚠️ BLANK LINK")
                    status_item.setForeground(QColor("#f97316"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Component exists in database but has no store link. Please add vendor URL in Inventory.")
            else:
                status_item.setText("🔴 NOT IN DB")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip("Component not found in inventory database. Please register in Inventory.")

            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFont(font_txt)
            self.table.setItem(row_idx, 0, status_item)

            # 1. Designator
            self.table.setItem(row_idx, 1, QTableWidgetItem(it.designator))
            # 2. Part Number
            self.table.setItem(row_idx, 2, QTableWidgetItem(it.part_number))
            # 3. Comment
            self.table.setItem(row_idx, 3, QTableWidgetItem(it.comment))
            # 4. Footprint
            self.table.setItem(row_idx, 4, QTableWidgetItem(it.footprint))

            # 5. Qty / Board
            item5 = QTableWidgetItem(str(it.unit_qty))
            item5.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item5.setFont(font_num)
            self.table.setItem(row_idx, 5, item5)

            # 6. Total Needed
            item6 = QTableWidgetItem(str(it.total_needed_qty))
            item6.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item6.setFont(font_num)
            self.table.setItem(row_idx, 6, item6)

            # 7. In Stock
            stock_str = str(it.db_stock_qty) if it.status != "NOT_IN_DB" else "-"
            item7 = QTableWidgetItem(stock_str)
            item7.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item7.setFont(font_num)
            self.table.setItem(row_idx, 7, item7)

            # 8. Shortage
            short_str = str(it.shortage_qty) if it.shortage_qty > 0 else "0"
            item8 = QTableWidgetItem(short_str)
            item8.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item8.setFont(font_num)
            if it.shortage_qty > 0:
                item8.setForeground(QColor("#fbbf24") if it.is_orderable else QColor("#f87171"))
            self.table.setItem(row_idx, 8, item8)

            # 9. Store Link
            item9 = QTableWidgetItem()
            item9.setFont(font_txt)
            if it.link and it.link.strip():
                if it.is_orderable:
                    if it.is_multi_vendor:
                        item9.setText("⚡ Multi-Vendor Link")
                        item9.setForeground(QColor("#a855f7"))
                        vendor_names = ", ".join(k.replace("vendor_", "").title() for k in it.vendor_links.keys())
                        item9.setToolTip(f"Multiple vendor links available ({vendor_names}):\n{it.link}\n(Select vendor in Order Preview)")
                    else:
                        v_name = it.vendor_id.replace("vendor_", "").title() if it.vendor_id else "Vendor"
                        clean_url = it.to_dict().get("link") or it.link
                        item9.setText(clean_url)
                        item9.setForeground(QColor("#38bdf8"))
                        item9.setToolTip(f"{v_name} link (READY FOR ORDER): {clean_url}")
                elif it.link_type == "INVALID":
                    item9.setText(f"❌ INVALID LINK ({it.link_domain})")
                    item9.setForeground(QColor("#f87171"))
                    item9.setToolTip(f"Invalid store link ({it.link}). Please update to a valid HTTP/HTTPS URL.")
                else:
                    # Valid URL, but plugin is not available
                    from core.procurement.bridge import ProcurementBridge
                    from core.procurement.registry import VendorRegistry
                    reg = VendorRegistry.get_default_registry()
                    p_stat = ProcurementBridge.get_plugin_status(it.vendor_id, reg)
                    v_name = it.vendor_id.replace("vendor_", "").title() if it.vendor_id else "Vendor"
                    clean_url = it.to_dict().get("link") or it.link
                    item9.setText(f"⚠️ {clean_url}")
                    item9.setForeground(QColor("#f97316"))
                    item9.setToolTip(f"{v_name} URL: {clean_url}\nStatus: {p_stat} (Cannot order until plugin is enabled)")
            else:
                if it.status == "SHORTAGE":
                    item9.setText("⚠️ Blank Store Link")
                    item9.setForeground(QColor("#f97316"))
                    item9.setToolTip("Component is in inventory database but store link is blank. Please add vendor URL in Inventory.")
                else:
                    item9.setText("— Not in DB —" if it.status == "NOT_IN_DB" else "⚠️ Blank Store Link")
                    item9.setForeground(QColor("#64748b"))
            self.table.setItem(row_idx, 9, item9)

        # Align column headers
        for c in range(self.table.columnCount()):
            hdr_item = self.table.horizontalHeaderItem(c)
            if hdr_item:
                if c in (0, 4, 5, 6, 7, 8):
                    hdr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    hdr_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Distribute column widths and calculate row heights for text wrapping
        self._distribute_table_columns()
        self.table.setSortingEnabled(True)

        # Update order button count and label
        orderable_items = res.get_orderable_shortages()
        all_shortages = res.get_all_shortages()
        if len(orderable_items) > 0:
            self.order_btn.setText(f"🛒 Add Shortages to Cart ({len(orderable_items)} Items Ready / {len(all_shortages)} Total)")
            self.order_btn.setEnabled(True)
        elif len(all_shortages) > 0:
            self.order_btn.setText(f"❌ Shortages Missing Vendor Links ({len(all_shortages)} Items)")
            self.order_btn.setEnabled(True)
        else:
            self.order_btn.setText("✅ All Components in Stock")
            self.order_btn.setEnabled(False)

    def _distribute_table_columns(self):
        """Distributes column widths appropriately based on role and available space."""
        total_w = self.table.viewport().width()
        if total_w <= 0:
            return

        base_widths = {
            0: 115,  # Status
            1: 180,  # Designator
            2: 150,  # Part Number
            3: 110,  # Comment
            4: 105,  # Footprint
            5: 70,   # Qty / Board
            6: 80,   # Total Needed
            7: 70,   # In Stock
            8: 70,   # Shortage
            9: 180,  # Store Link
        }
        stretch_col1 = 1
        stretch_col2 = 9

        base_sum = sum(base_widths.values())
        if total_w > base_sum:
            extra = total_w - base_sum
            extra1 = int(extra * 0.5)
            extra2 = extra - extra1
            for c, w in base_widths.items():
                if c == stretch_col1:
                    self.table.setColumnWidth(c, w + extra1)
                elif c == stretch_col2:
                    self.table.setColumnWidth(c, w + extra2)
                else:
                    self.table.setColumnWidth(c, w)
        else:
            for c, w in base_widths.items():
                self.table.setColumnWidth(c, w)
        self.table.resizeRowsToContents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.audit_result and hasattr(self, "table") and self.table.isVisible():
            self._distribute_table_columns()

    def _open_order_dialog(self):
        if not self.audit_result:
            return

        res = self.audit_result
        all_shortages = res.get_all_shortages()
        missing_db = [it.to_dict() for it in res.items if it.status == "NOT_IN_DB"]

        dlg = OrderPreviewDialog(
            all_shortages=all_shortages,
            missing_db_items=missing_db,
            source_title=f"Project BOM Shortages — {res.file_name} ({res.board_multiplier} Boards)",
            inventory_loader=self.inventory,
            on_stock_updated=self._recalculate_audit,
            parent=self
        )
        dlg.exec()

    def _export_pre_order_plan(self):
        """Export Pre-Order Procurement Plan (.xlsx) before staging operations."""
        if not self.audit_result:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        res = self.audit_result
        default_base = res.file_name.replace(".xlsx", "").replace(".xls", "")
        default_name = f"Omnix_Procurement_Plan_{default_base}_{timestamp}.xlsx"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pre-Order Procurement Plan (.xlsx)",
            default_name,
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        all_shortages = res.get_all_shortages()
        report_data = ProcurementReportBuilder.build_from_shortages(
            shortages=all_shortages,
            staging_results=None,
            source_title=f"Project BOM Shortages — {res.file_name} ({res.board_multiplier} Boards)",
            source_file=res.file_name,
            procurement_mode=res.mode,
            board_multiplier=res.board_multiplier,
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

    _export_missing_report = _export_pre_order_plan

    def _edit_brand_rule(self, row_idx: int):
        """Open the interactive Brand / Manufacturer Rule Dialog for a BOM item."""
        if not self.audit_result or not (0 <= row_idx < len(self.audit_result.items)):
            return
        it = self.audit_result.items[row_idx]
        dlg = BrandRuleDialog(it, parent=self)
        if dlg.exec():
            # Refresh table display with updated brand rule
            self._render_results()

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item or not self.audit_result:
            return
        row = item.row()
        col = item.column()

        # Store Link column (Col 9)
        if col == 9:
            link_item = self.table.item(row, 9)
            if link_item and link_item.text().startswith("http"):
                webbrowser.open(link_item.text())
                return

        val = item.text().strip()
        if val.startswith("http"):
            webbrowser.open(val)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        val = item.text().strip()

        copy_act = menu.addAction("📋 Copy Cell Value")
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(val))

        row_idx = item.row()
        copy_row_act = menu.addAction("📑 Copy Entire Row")
        def _copy_row():
            cols = [self.table.item(row_idx, c).text() if self.table.item(row_idx, c) else "" for c in range(self.table.columnCount())]
            QApplication.clipboard().setText("\t".join(cols))
        copy_row_act.triggered.connect(_copy_row)

        if self.audit_result and 0 <= row_idx < len(self.audit_result.items):
            it = self.audit_result.items[row_idx]
            menu.addSeparator()
            brand_act = menu.addAction("🏷️ Edit Brand / Manufacturer Rule...")
            brand_act.triggered.connect(lambda _, r=row_idx: self._edit_brand_rule(r))
            if it.link and it.link.startswith("http"):
                open_link_act = menu.addAction(f"🌐 Open Store Link ({it.link_domain or 'Browser'})")
                open_link_act.triggered.connect(lambda _, url=it.link: webbrowser.open(url))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_blank_link_filter(self):
        """Toggles filter to show only rows with missing or blank store links."""
        if not hasattr(self, "_filter_blank_active"):
            self._filter_blank_active = False
        self._filter_blank_active = not self._filter_blank_active

        if self._filter_blank_active:
            self.pill_missing_link.setStyleSheet("""
                QPushButton {
                    background-color: #f97316;
                    border: 1.5px solid #ea580c;
                    color: #0f172a;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
        else:
            self.pill_missing_link.setStyleSheet("""
                QPushButton {
                    background-color: rgba(249, 115, 22, 0.12);
                    border: 1px solid rgba(249, 115, 22, 0.35);
                    color: #f97316;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)

        if not self.audit_result or not self.audit_result.items:
            return

        for r, it in enumerate(self.audit_result.items):
            if r >= self.table.rowCount():
                break
            if not self._filter_blank_active:
                self.table.setRowHidden(r, False)
            else:
                is_blank = (it.status == "SHORTAGE" and (not it.link or not it.link.strip()))
                self.table.setRowHidden(r, not is_blank)
