import os
import webbrowser
import datetime
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QSpinBox, QLineEdit, QFrame,
    QFileDialog, QHeaderView, QApplication, QMenu, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QMarginsF, QSizeF
from PyQt6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent, QTextDocument, QPageSize, QPageLayout, QIntValidator
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMAuditor, BOMAuditResult, BOMItem
from core.procurement.models import ProcurementMode, ManufacturerRule, ManufacturerDataState
from excel_loader import ExcelDataLoader
from ui.dialogs.order_preview_dialog import OrderPreviewDialog


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
    Supports Dual Procurement Modes:
    - Mode A (Database-Aware): Reconciles BOM components against active inventory database,
      calculates net shortages, and links to registered store URLs.
    - Mode B (Direct BOM Turnkey): Sourcing is 100% inventory-independent, broadcasting BOM
      requirements directly across all enabled multi-vendor catalogs.
    """

    def __init__(self, inventory_loader: ExcelDataLoader, parent=None):
        super().__init__(parent)
        self.inventory = inventory_loader
        self.current_bom_path: Optional[str] = None
        self.audit_result: Optional[BOMAuditResult] = None
        self.current_mode: ProcurementMode = ProcurementMode.DATABASE_AWARE
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

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

        # Procurement Mode Selector (Mode A vs Mode B)
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet("font-weight: 600; color: #e2e8f0; font-size: 12px;")
        top_layout.addWidget(mode_lbl)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("📊 Mode A (Database-Aware)", ProcurementMode.DATABASE_AWARE)
        self.mode_combo.addItem("🚀 Mode B (Direct BOM Turnkey)", ProcurementMode.DIRECT_BOM)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 8px;
                min-width: 190px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                border: 1px solid #334155;
                selection-background-color: #0284c7;
                color: #f8fafc;
            }
        """)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_layout.addWidget(self.mode_combo)

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

        self.export_report_btn = QPushButton("📄 Export Missing & Shortages Report")
        self.export_report_btn.setObjectName("secondaryBtn")
        self.export_report_btn.clicked.connect(self._export_missing_report)
        action_layout.addWidget(self.export_report_btn)

        action_layout.addStretch()

        self.order_btn = QPushButton("🛒 Order Project Shortages")
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

    def _on_mode_changed(self, index: int):
        data = self.mode_combo.currentData()
        if data:
            self.current_mode = data
            self._recalculate_audit()

    def _recalculate_audit(self):
        if not self.current_bom_path or not os.path.exists(self.current_bom_path):
            return

        multiplier = self.multiplier_spin.value()
        inv = self.inventory if self.current_mode == ProcurementMode.DATABASE_AWARE else None
        ok, msg, res = BOMAuditor.audit_bom(
            self.current_bom_path,
            inventory=inv,
            board_multiplier=multiplier,
            mode=self.current_mode
        )
        if not ok or not res:
            return

        self.audit_result = res
        self._render_results()

    def unload_bom(self):
        """Unload active Altium BOM and reset view back to the drop zone."""
        self.current_bom_path = None
        self.audit_result = None
        self.top_card.hide()
        self.stats_frame.hide()
        self.table.hide()
        self.action_card.hide()
        self.drop_zone.show()

    def _render_results(self):
        if not self.audit_result:
            return

        res = self.audit_result
        is_mode_b = res.mode == ProcurementMode.DIRECT_BOM

        # Update Top Info
        mode_badge = "Mode B (Direct Turnkey)" if is_mode_b else "Mode A (Database-Aware)"
        self.file_info_lbl.setText(f"📄 Project BOM: <b>{res.file_name}</b> <span style='color:#94a3b8; font-size:11px;'>[{mode_badge}]</span>")
        self.drop_zone.hide()
        self.top_card.show()
        self.stats_frame.show()
        self.table.show()
        self.action_card.show()

        # Update KPIs and Table Headers according to mode
        if is_mode_b:
            self.pill_total.setText(f"Total BOM Items: {res.total_items_count}")
            self.pill_in_stock.setText(f"🚀 Sourcing Ready: {res.shortage_count}")
            total_req_pcs = sum(it.total_needed_qty for it in res.items if it.is_valid)
            self.pill_shortage.setText(f"📦 Total Sourcing Demand: {total_req_pcs} pcs")
            self.pill_not_in_db.setText(f"❌ Invalid / Blocked: {res.invalid_count}")

            self.table.setHorizontalHeaderLabels([
                "Status", "Designator", "Part Number", "Manufacturer", "Package / Footprint",
                "Qty / Board", "Total Needed", "Brand Rule", "Specs", "Procurement Target"
            ])
        else:
            self.pill_total.setText(f"Total BOM Items: {res.total_items_count}")
            self.pill_in_stock.setText(f"✅ Fully Available: {res.in_stock_count}")
            self.pill_shortage.setText(f"⚠️ Shortages: {res.shortage_count}")
            self.pill_not_in_db.setText(f"🔴 Not in Database: {res.not_in_db_count}")

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
            if is_mode_b:
                # Mode B Columns
                # 0. Status Badge
                status_item = QTableWidgetItem()
                if not it.is_valid:
                    status_item.setText("❌ INVALID")
                    status_item.setForeground(QColor("#f87171"))
                    status_item.setToolTip("; ".join(it.validation_errors))
                else:
                    status_item.setText("🚀 READY")
                    status_item.setForeground(QColor("#38bdf8"))
                    status_item.setToolTip("Ready for multi-vendor catalog discovery and candidate pricing.")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item.setFont(font_txt)
                self.table.setItem(row_idx, 0, status_item)

                # 1. Designator
                self.table.setItem(row_idx, 1, QTableWidgetItem(it.designator))
                # 2. Part Number
                self.table.setItem(row_idx, 2, QTableWidgetItem(it.part_number))
                # 3. Manufacturer
                self.table.setItem(row_idx, 3, QTableWidgetItem(it.manufacturer or "—"))
                # 4. Package / Footprint
                pkg_fp = f"{it.package} / {it.footprint}".strip(" /") or "—"
                self.table.setItem(row_idx, 4, QTableWidgetItem(pkg_fp))

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

                # 7. Brand Rule
                if it.is_manufacturer_any:
                    rule_str = "ANY (Generic Allowed)"
                elif it.allowed_manufacturers and len(it.allowed_manufacturers) > 1:
                    rule_str = f"APPROVED ({len(it.allowed_manufacturers)})"
                elif it.manufacturer:
                    rule_str = f"EXACT ({it.manufacturer})"
                else:
                    rule_str = "MISSING (No Brand Rule)"
                item7 = QTableWidgetItem(rule_str)
                item7.setFont(font_txt)
                self.table.setItem(row_idx, 7, item7)

                # 8. Specs
                specs_summary = ", ".join(f"{k}:{v}" for k, v in it.required_specs.items()) if it.required_specs else "—"
                self.table.setItem(row_idx, 8, QTableWidgetItem(specs_summary))

                # 9. Procurement Target
                item9 = QTableWidgetItem()
                item9.setFont(font_txt)
                if it.is_valid:
                    item9.setText("🌐 Multi-Vendor Catalog Sourcing")
                    item9.setForeground(QColor("#38bdf8"))
                    item9.setToolTip("Will query all active and enabled vendor adapters (Lion, Javan, RoboEq, etc.).")
                else:
                    item9.setText(f"❌ Blocked ({'; '.join(it.validation_errors)})")
                    item9.setForeground(QColor("#f87171"))
                self.table.setItem(row_idx, 9, item9)

            else:
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
                        status_item.setText(f"⚠️ SHORTAGE (-{it.shortage_qty})")
                        status_item.setForeground(QColor("#fbbf24"))
                        status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. {v_name} link ready for automated purchase.")
                    elif it.link_type == "INVALID":
                        status_item.setText(f"❌ INVALID LINK (-{it.shortage_qty})")
                        status_item.setForeground(QColor("#f87171"))
                        status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Store link ({it.link_domain}) is not a registered vendor. Please update in Inventory.xlsx.")
                    else:
                        status_item.setText(f"❌ BLANK LINK (-{it.shortage_qty})")
                        status_item.setForeground(QColor("#f87171"))
                        status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Component exists in database but has no store link. Please add vendor URL in Inventory.xlsx.")
                else:
                    status_item.setText("🔴 NOT IN DB")
                    status_item.setForeground(QColor("#f87171"))
                    status_item.setToolTip("Component not found in inventory database. Please register in Inventory.xlsx.")

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
                if it.is_orderable:
                    v_name = it.vendor_id.replace("vendor_", "").title() if it.vendor_id else "Vendor"
                    item9.setText(it.link)
                    item9.setForeground(QColor("#38bdf8"))
                    item9.setToolTip(f"{v_name} link (Auto-Order Ready): {it.link}")
                elif it.link_type == "INVALID":
                    item9.setText(f"❌ Unsupported URL ({it.link_domain})")
                    item9.setForeground(QColor("#f87171"))
                    item9.setToolTip(f"Unsupported store link ({it.link}). Please update to a registered vendor in Inventory.xlsx.")
                else:
                    if it.status == "SHORTAGE":
                        item9.setText("❌ Blank Store Link")
                        item9.setForeground(QColor("#f87171"))
                        item9.setToolTip("Component is in inventory database but store link is blank. Please add vendor URL in Inventory.xlsx.")
                    else:
                        item9.setText("— Not in DB —" if it.status == "NOT_IN_DB" else it.link)
                        item9.setForeground(QColor("#64748b"))
                self.table.setItem(row_idx, 9, item9)

        # Auto-fit columns
        for c in range(10):
            self.table.resizeColumnToContents(c)
            if self.table.columnWidth(c) < 95:
                self.table.setColumnWidth(c, 95)
            elif self.table.columnWidth(c) > 300:
                self.table.setColumnWidth(c, 300)

        self.table.setSortingEnabled(True)

        # Update order button count and label
        if is_mode_b:
            valid_items = [it for it in res.items if it.is_valid]
            if len(valid_items) > 0:
                self.order_btn.setText(f"🛒 Source All Turnkey BOM Components ({len(valid_items)} Items Ready)")
                self.order_btn.setEnabled(True)
            else:
                self.order_btn.setText("❌ No Valid Items to Source")
                self.order_btn.setEnabled(False)
        else:
            orderable_items = res.get_orderable_shortages()
            all_shortages = res.get_all_shortages()
            if len(orderable_items) > 0:
                self.order_btn.setText(f"🛒 Order Shortages ({len(orderable_items)} Items Ready / {len(all_shortages)} Total)")
                self.order_btn.setEnabled(True)
            elif len(all_shortages) > 0:
                self.order_btn.setText(f"❌ Shortages Missing Vendor Links ({len(all_shortages)} Items)")
                self.order_btn.setEnabled(True)
            else:
                self.order_btn.setText("✅ All Components in Stock")
                self.order_btn.setEnabled(False)

    def _open_order_dialog(self):
        if not self.audit_result:
            return

        res = self.audit_result
        if res.mode == ProcurementMode.DIRECT_BOM:
            all_items = res.get_all_shortages()
            dlg = OrderPreviewDialog(
                all_shortages=all_items,
                orderable_items=res.get_orderable_shortages(),
                missing_db_items=[],
                source_title=f"Turnkey Direct BOM Sourcing — {res.file_name} ({res.board_multiplier} Boards)",
                inventory_loader=None,
                on_stock_updated=self._recalculate_audit,
                parent=self
            )
            dlg.exec()
        else:
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

    def _export_missing_report(self):
        """Export missing components and stock shortages as a clean, printable PDF / CSV report."""
        if not self.audit_result:
            return

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        res = self.audit_result
        is_mode_b = res.mode == ProcurementMode.DIRECT_BOM

        default_base = res.file_name.replace(".xlsx", "").replace(".xls", "")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Missing Components & Shortages Report",
            f"BOM_Shortages_Report_{default_base}.pdf",
            "PDF Document (*.pdf);;CSV Spreadsheet (*.csv);;HTML Document (*.html)"
        )
        if not file_path:
            return

        if file_path.lower().endswith(".csv"):
            if is_mode_b:
                lines = ["Status,Designator,Part Number,Manufacturer,Package,Footprint,Unit Qty,Total Needed,Brand Rule,Specs"]
                for it in res.items:
                    lines.append(
                        f'"{it.status}","{it.designator}","{it.part_number}","{it.manufacturer}","{it.package}",'
                        f'"{it.footprint}",{it.unit_qty},{it.total_needed_qty},"{it.mfg_data_state}","{it.required_specs}"'
                    )
            else:
                lines = ["Status,Designator,Part Number,Comment,Footprint,Unit Qty,Total Needed,In Stock,Shortage,Link,Procurement Source"]
                for it in res.items:
                    if it.status in ["NOT_IN_DB", "SHORTAGE"]:
                        source_str = "Lion Electronic" if it.link_type == "LION" else (it.link_domain if it.link_type == "EXTERNAL" else "None")
                        lines.append(
                            f'"{it.status}","{it.designator}","{it.part_number}","{it.comment}","{it.footprint}",'
                            f'{it.unit_qty},{it.total_needed_qty},{it.db_stock_qty},{it.shortage_qty},"{it.link}","{source_str}"'
                        )
            with open(file_path, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(lines))
            webbrowser.open(f"file:///{os.path.abspath(file_path)}")
        else:
            # HTML / PDF build
            def format_designators(des_str: str) -> str:
                parts = [p.strip() for p in des_str.split(',') if p.strip()]
                if len(parts) > 6:
                    return f"{', '.join(parts[:5])} ... (+{len(parts)-5})"
                return ", ".join(parts)

            html_rows = ""
            for idx, it in enumerate(res.items, 1):
                des_display = format_designators(it.designator)
                bg = 'background-color:#ffffff;' if idx % 2 != 0 else 'background-color:#f8fafc;'
                html_rows += f"""
                <tr style="{bg}">
                    <td style="text-align:center; color:#64748b; border:1px solid #94a3b8; padding:4px 6px;">{idx}</td>
                    <td style="border:1px solid #94a3b8; padding:4px 6px;"><b>{des_display}</b></td>
                    <td style="border:1px solid #94a3b8; padding:4px 6px;"><code>{it.part_number or '-'}</code></td>
                    <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.manufacturer or it.comment or '-'}</td>
                    <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.package or it.footprint or '-'}</td>
                    <td style="text-align:center; border:1px solid #94a3b8; padding:4px 6px;">{it.total_needed_qty}</td>
                    <td style="text-align:center; color:#b91c1c; font-weight:bold; border:1px solid #94a3b8; padding:4px 6px;">{it.shortage_qty}</td>
                </tr>
                """

            mode_title = "Direct Turnkey BOM Report" if is_mode_b else "BOM Assembly & Shortages Audit Report"
            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{mode_title} — {res.file_name}</title>
<style>
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 8.5pt; color: #0f172a; margin: 0; padding: 0; }}
    .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 4px; margin-bottom: 10px; }}
    h1 {{ font-size: 13.5pt; color: #0f172a; margin: 0 0 3px 0; font-weight: bold; }}
    .meta {{ font-size: 8.5pt; color: #475569; }}
    table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; border: 1px solid #475569; }}
    table.data-table th {{ background-color: #1e293b; color: #ffffff; font-weight: bold; font-size: 8pt; padding: 5px 6px; border: 1px solid #475569; text-align: left; }}
    code {{ font-family: Consolas, monospace; background-color: #f1f5f9; padding: 1px 3px; font-size: 7.5pt; }}
    .footer {{ font-size: 7.5pt; color: #94a3b8; text-align: center; margin-top: 10px; border-top: 1px solid #cbd5e1; padding-top: 3px; }}
</style>
</head>
<body>
    <div class="header">
        <h1>{mode_title}</h1>
        <div class="meta">
            <b>Project BOM:</b> {res.file_name} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Date:</b> {now_str} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Batch Quantity:</b> {res.board_multiplier} Board(s)
        </div>
    </div>
    <table class="data-table" border="1" cellspacing="0" cellpadding="4">
        <thead>
            <tr>
                <th width="3%" style="text-align:center;">#</th>
                <th width="18%">Designator</th>
                <th width="25%">Part Number</th>
                <th width="20%">Manufacturer / Comment</th>
                <th width="15%">Package / Footprint</th>
                <th width="10%" style="text-align:center;">Total Qty</th>
                <th width="9%" style="text-align:center;">Shortage</th>
            </tr>
        </thead>
        <tbody>
            {html_rows}
        </tbody>
    </table>
    <div class="footer">Omnix Procurement & Inventory Management System</div>
</body>
</html>
"""
            if file_path.lower().endswith(".html"):
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            else:
                printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(file_path)
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                printer.setPageOrientation(QPageLayout.Orientation.Landscape)
                printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)

                doc = QTextDocument()
                page_size = printer.pageLayout().paintRectPixels(printer.resolution()).size()
                doc.setPageSize(QSizeF(page_size))
                doc.setHtml(html_content)
                doc.print(printer)

            webbrowser.open(f"file:///{os.path.abspath(file_path)}")

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        link_item = self.table.item(row, 9)
        if link_item and link_item.text().startswith("http"):
            webbrowser.open(link_item.text())
        else:
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
            if it.link and it.link.startswith("http"):
                menu.addSeparator()
                open_link_act = menu.addAction(f"🌐 Open Store Link ({it.link_domain or 'Browser'})")
                open_link_act.triggered.connect(lambda _, url=it.link: webbrowser.open(url))

        menu.exec(self.table.viewport().mapToGlobal(pos))
