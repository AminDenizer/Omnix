import os
import webbrowser
import datetime
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QSpinBox, QLineEdit, QFrame,
    QFileDialog, QHeaderView, QApplication, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QMarginsF, QSizeF
from PyQt6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent, QTextDocument, QPageSize, QPageLayout, QIntValidator
from PyQt6.QtPrintSupport import QPrinter
from bom_auditor import BOMAuditor, BOMAuditResult, BOMItem
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


class NumberStepperWidget(QWidget):
    """
    Modern counter with external dedicated minus/plus buttons and centered numeric input.
    """
    valueChanged = pyqtSignal(int)

    def __init__(self, value: int = 1, min_val: int = 1, max_val: int = 100000, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self._val = max(min_val, min(value, max_val))
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        btn_style = """
            QPushButton {
                background-color: #131d31;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 17px;
                font-weight: bold;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border: 1.5px solid #38bdf8;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0284c7;
                color: #ffffff;
            }
        """

        # Minus button [-]
        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedSize(34, 32)
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.setAutoRepeat(True)
        self.btn_minus.setAutoRepeatDelay(350)
        self.btn_minus.setAutoRepeatInterval(80)
        self.btn_minus.setStyleSheet(btn_style)
        self.btn_minus.clicked.connect(self._step_down)
        layout.addWidget(self.btn_minus)

        # Center input
        self.input_field = QLineEdit(str(self._val))
        self.input_field.setFixedSize(76, 32)
        self.input_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_field.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.input_field.setValidator(QIntValidator(self.min_val, self.max_val, self))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 13px;
                font-weight: bold;
                padding: 2px;
            }
            QLineEdit:focus {
                border: 1.5px solid #38bdf8;
                background-color: #0f172a;
            }
        """)
        self.input_field.textChanged.connect(self._on_text_changed)
        self.input_field.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.input_field)

        # Plus button [+]
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(34, 32)
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.setAutoRepeat(True)
        self.btn_plus.setAutoRepeatDelay(350)
        self.btn_plus.setAutoRepeatInterval(80)
        self.btn_plus.setStyleSheet(btn_style)
        self.btn_plus.clicked.connect(self._step_up)
        layout.addWidget(self.btn_plus)

    def _step_down(self):
        new_val = max(self.min_val, self._val - 1)
        self.setValue(new_val)

    def _step_up(self):
        new_val = min(self.max_val, self._val + 1)
        self.setValue(new_val)

    def _on_text_changed(self, text: str):
        if text.strip().isdigit():
            v = int(text.strip())
            if self.min_val <= v <= self.max_val:
                self._val = v
                self.valueChanged.emit(v)

    def _on_editing_finished(self):
        text = self.input_field.text().strip()
        if not text.isdigit() or int(text) < self.min_val:
            self.setValue(self.min_val)
        elif int(text) > self.max_val:
            self.setValue(self.max_val)
        else:
            self.setValue(int(text))

    def value(self) -> int:
        return self._val

    def setValue(self, val: int):
        val = max(self.min_val, min(val, self.max_val))
        if self._val != val or self.input_field.text() != str(val):
            self._val = val
            self.input_field.setText(str(val))
            self.valueChanged.emit(val)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self._step_up()
        else:
            self._step_down()
        event.accept()

    def setRange(self, min_val: int, max_val: int):
        self.min_val = min_val
        self.max_val = max_val
        self.input_field.setValidator(QIntValidator(min_val, max_val, self))
        self.setValue(self._val)


class BOMAuditWidget(QWidget):
    """
    Altium BOM Project Assembly Auditor Tab:
    Matches BOM components against active inventory database, calculates shortages
    for customized board assembly quantities, and prepares automated web purchases.
    """

    def __init__(self, inventory_loader: ExcelDataLoader, parent=None):
        super().__init__(parent)
        self.inventory = inventory_loader
        self.current_bom_path: Optional[str] = None
        self.audit_result: Optional[BOMAuditResult] = None
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

        self.order_btn = QPushButton("🛒 Order Project Shortages on Lion Electronic")
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
        ok, msg, res = BOMAuditor.audit_bom(self.current_bom_path, self.inventory, board_multiplier=multiplier)
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

        # Update Top Info
        self.file_info_lbl.setText(f"📄 Project BOM: <b>{res.file_name}</b>")
        self.drop_zone.hide()
        self.top_card.show()
        self.stats_frame.show()
        self.table.show()
        self.action_card.show()

        # Update KPIs
        self.pill_total.setText(f"Total BOM Items: {res.total_items_count}")
        self.pill_in_stock.setText(f"✅ Fully Available: {res.in_stock_count}")
        self.pill_shortage.setText(f"⚠️ Shortages: {res.shortage_count}")
        self.pill_not_in_db.setText(f"🔴 Not in Database: {res.not_in_db_count}")

        # Populate Table
        items = res.items
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(items))

        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        for row_idx, it in enumerate(items):
            # 0. Status Badge
            status_item = QTableWidgetItem()
            if it.status == "IN_STOCK":
                status_item.setText("✅ IN STOCK")
                status_item.setForeground(QColor("#34d399"))
                status_item.setToolTip("Sufficient stock in database for this assembly batch.")
            elif it.status == "SHORTAGE":
                if it.link_type == "LION":
                    status_item.setText(f"⚠️ SHORTAGE (-{it.shortage_qty})")
                    status_item.setForeground(QColor("#fbbf24"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Lion Electronic link ready for automated purchase.")
                elif it.link_type == "INVALID":
                    status_item.setText(f"❌ INVALID LINK (-{it.shortage_qty})")
                    status_item.setForeground(QColor("#f87171"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Store link is not from Lion Electronic ({it.link_domain}). Please update link to lionelectronic.ir in Inventory.xlsx.")
                else:
                    status_item.setText(f"❌ BLANK LINK (-{it.shortage_qty})")
                    status_item.setForeground(QColor("#f87171"))
                    status_item.setToolTip(f"Shortage of {it.shortage_qty} pcs. Component exists in database but has no store link. Please add Lion Electronic URL in Inventory.xlsx.")
            else:
                status_item.setText("🔴 NOT IN DB")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip("Component not found in inventory database. Please register in Inventory.xlsx.")

            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFont(font_txt)
            self.table.setItem(row_idx, 0, status_item)

            # 1. Designator
            item1 = QTableWidgetItem(it.designator)
            item1.setFont(font_txt)
            self.table.setItem(row_idx, 1, item1)

            # 2. Part Number
            item2 = QTableWidgetItem(it.part_number)
            item2.setFont(font_txt)
            self.table.setItem(row_idx, 2, item2)

            # 3. Comment
            item3 = QTableWidgetItem(it.comment)
            item3.setFont(font_txt)
            self.table.setItem(row_idx, 3, item3)

            # 4. Footprint
            item4 = QTableWidgetItem(it.footprint)
            item4.setFont(font_txt)
            self.table.setItem(row_idx, 4, item4)

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
                item8.setForeground(QColor("#fbbf24") if it.link_type == "LION" else QColor("#f87171"))
            self.table.setItem(row_idx, 8, item8)

            # 9. Store Link
            item9 = QTableWidgetItem()
            item9.setFont(font_txt)
            if it.link_type == "LION":
                item9.setText(it.link)
                item9.setForeground(QColor("#38bdf8"))
                item9.setToolTip(f"Lion Electronic link (Auto-Order Ready): {it.link}")
            elif it.link_type == "INVALID":
                item9.setText(f"❌ Non-Lion URL ({it.link_domain})")
                item9.setForeground(QColor("#f87171"))
                item9.setToolTip(f"Invalid store link ({it.link}). Please update to lionelectronic.ir in Inventory.xlsx.")
            else:
                if it.status == "SHORTAGE":
                    item9.setText("❌ Blank Store Link")
                    item9.setForeground(QColor("#f87171"))
                    item9.setToolTip("Component is in inventory database but store link is blank. Please add Lion Electronic URL in Inventory.xlsx.")
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
        lion_items = res.get_orderable_shortages()
        all_shortages = res.get_all_shortages()
        if len(lion_items) > 0:
            self.order_btn.setText(f"🛒 Order Shortages ({len(lion_items)} Lion Items / {len(all_shortages)} Total)")
            self.order_btn.setEnabled(True)
        elif len(all_shortages) > 0:
            self.order_btn.setText(f"❌ Shortages Missing Lion Links ({len(all_shortages)} Items)")
            self.order_btn.setEnabled(True)
        else:
            self.order_btn.setText("✅ All Components in Stock")
            self.order_btn.setEnabled(False)

    def _open_order_dialog(self):
        if not self.audit_result:
            return

        all_shortages = self.audit_result.get_all_shortages()
        missing_db = [it.to_dict() for it in self.audit_result.items if it.status == "NOT_IN_DB"]

        dlg = OrderPreviewDialog(
            all_shortages=all_shortages,
            missing_db_items=missing_db,
            source_title=f"Project BOM Shortages — {self.audit_result.file_name} ({self.audit_result.board_multiplier} Boards)",
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
            # Build clean professional report
            not_in_db_rows = [it for it in res.items if it.status == "NOT_IN_DB"]
            shortage_rows = [it for it in res.items if it.status == "SHORTAGE"]

            def format_designators(des_str: str) -> str:
                parts = [p.strip() for p in des_str.split(',') if p.strip()]
                if len(parts) > 6:
                    return f"{', '.join(parts[:5])} ... (+{len(parts)-5})"
                return ", ".join(parts)

            def build_shortage_html(items):
                html = ""
                for idx, it in enumerate(items, 1):
                    if it.link_type == "LION":
                        source_badge = '<span style="color:#047857; font-weight:bold;">⚡ Lion Ready (Auto-Order)</span>'
                    elif it.link_type == "INVALID":
                        source_badge = f'<span style="color:#b91c1c; font-weight:bold;">❌ Invalid Link ({it.link_domain})</span><br><span style="color:#64748b; font-size:7pt;">Update in Inventory.xlsx</span>'
                    else:
                        source_badge = '<span style="color:#b91c1c; font-weight:bold;">❌ Missing Store Link</span><br><span style="color:#64748b; font-size:7pt;">Add Lion URL in Inventory.xlsx</span>'

                    des_display = format_designators(it.designator)
                    bg = 'background-color:#ffffff;' if idx % 2 != 0 else 'background-color:#f8fafc;'
                    html += f"""
                    <tr style="{bg}">
                        <td style="text-align:center; color:#64748b; border:1px solid #94a3b8; padding:4px 6px;">{idx}</td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;"><b>{des_display}</b></td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;"><code>{it.part_number or '-'}</code></td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.comment}</td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.footprint}</td>
                        <td style="text-align:center; border:1px solid #94a3b8; padding:4px 6px;">{it.total_needed_qty}</td>
                        <td style="text-align:center; border:1px solid #94a3b8; padding:4px 6px;">{it.db_stock_qty}</td>
                        <td style="text-align:center; color:#b91c1c; font-weight:bold; border:1px solid #94a3b8; padding:4px 6px;">{it.shortage_qty}</td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;">{source_badge}</td>
                    </tr>
                    """
                return html

            def build_not_in_db_html(items):
                html = ""
                for idx, it in enumerate(items, 1):
                    des_display = format_designators(it.designator)
                    bg = 'background-color:#ffffff;' if idx % 2 != 0 else 'background-color:#f8fafc;'
                    html += f"""
                    <tr style="{bg}">
                        <td style="text-align:center; color:#64748b; border:1px solid #94a3b8; padding:4px 6px;">{idx}</td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;"><b>{des_display}</b></td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;"><code>{it.part_number or '-'}</code></td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.comment}</td>
                        <td style="border:1px solid #94a3b8; padding:4px 6px;">{it.footprint}</td>
                        <td style="text-align:center; font-weight:bold; border:1px solid #94a3b8; padding:4px 6px;">{it.total_needed_qty}</td>
                        <td style="color:#b91c1c; text-align:center; font-weight:bold; border:1px solid #94a3b8; padding:4px 6px;">Not in Inventory.xlsx</td>
                    </tr>
                    """
                return html

            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>BOM Audit Report — {res.file_name}</title>
<style>
    body {{
        font-family: Arial, Helvetica, sans-serif;
        font-size: 8.5pt;
        color: #0f172a;
        margin: 0;
        padding: 0;
    }}
    .header {{
        border-bottom: 2px solid #0f172a;
        padding-bottom: 4px;
        margin-bottom: 10px;
    }}
    h1 {{
        font-size: 13.5pt;
        color: #0f172a;
        margin: 0 0 3px 0;
        font-weight: bold;
    }}
    .meta {{
        font-size: 8.5pt;
        color: #475569;
    }}
    .summary-table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 12px;
        border: 1px solid #94a3b8;
    }}
    .summary-table td {{
        border: 1px solid #94a3b8;
        padding: 6px 10px;
        background-color: #f8fafc;
        font-size: 8.5pt;
        text-align: center;
    }}
    .summary-val {{
        font-size: 11pt;
        font-weight: bold;
        display: block;
        margin-top: 2px;
    }}
    h2 {{
        font-size: 10pt;
        color: #1e293b;
        margin: 10px 0 5px 0;
        border-bottom: 1px solid #94a3b8;
        padding-bottom: 2px;
    }}
    table.data-table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 12px;
        border: 1px solid #475569;
    }}
    table.data-table th {{
        background-color: #1e293b;
        color: #ffffff;
        font-weight: bold;
        font-size: 8pt;
        padding: 5px 6px;
        border: 1px solid #475569;
        text-align: left;
        white-space: nowrap;
    }}
    code {{
        font-family: Consolas, monospace;
        background-color: #f1f5f9;
        padding: 1px 3px;
        font-size: 7.5pt;
    }}
    .footer {{
        font-size: 7.5pt;
        color: #94a3b8;
        text-align: center;
        margin-top: 10px;
        border-top: 1px solid #cbd5e1;
        padding-top: 3px;
    }}
</style>
</head>
<body>
    <div class="header">
        <h1>Altium BOM Assembly & Shortages Audit Report</h1>
        <div class="meta">
            <b>Project BOM:</b> {res.file_name} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Date:</b> {now_str} &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Batch Quantity:</b> {res.board_multiplier} Board(s)
        </div>
    </div>

    <table class="summary-table" border="1" cellspacing="0" cellpadding="6">
        <tr>
            <td width="25%">Total BOM Items<br><span class="summary-val" style="color:#0f172a;">{res.total_items_count}</span></td>
            <td width="25%">Available in Stock<br><span class="summary-val" style="color:#16a34a;">{res.in_stock_count}</span></td>
            <td width="25%">Stock Shortages<br><span class="summary-val" style="color:#d97706;">{res.shortage_count}</span></td>
            <td width="25%">Missing from Database<br><span class="summary-val" style="color:#dc2626;">{res.not_in_db_count}</span></td>
        </tr>
    </table>

    <h2>1. Stock Shortages (Immediate Procurement Required)</h2>
    <table class="data-table" border="1" cellspacing="0" cellpadding="4">
        <thead>
            <tr>
                <th width="3%" style="text-align:center;">#</th>
                <th width="17%">Designator</th>
                <th width="22%">Part Number</th>
                <th width="12%">Comment</th>
                <th width="12%">Footprint</th>
                <th width="6%" style="text-align:center;">Needed</th>
                <th width="6%" style="text-align:center;">In Stock</th>
                <th width="6%" style="text-align:center;">Shortage</th>
                <th width="16%">Procurement Source</th>
            </tr>
        </thead>
        <tbody>
            {build_shortage_html(shortage_rows) if shortage_rows else '<tr><td colspan="9" style="text-align:center; color:#16a34a; border:1px solid #94a3b8;">All registered components have sufficient stock.</td></tr>'}
        </tbody>
    </table>

    <h2>2. Unregistered Components (Missing in Inventory Database)</h2>
    <table class="data-table" border="1" cellspacing="0" cellpadding="4">
        <thead>
            <tr>
                <th width="3%" style="text-align:center;">#</th>
                <th width="18%">Designator</th>
                <th width="24%">Part Number</th>
                <th width="15%">Comment</th>
                <th width="15%">Footprint</th>
                <th width="8%" style="text-align:center;">Needed</th>
                <th width="17%" style="text-align:center;">Database Status</th>
            </tr>
        </thead>
        <tbody>
            {build_not_in_db_html(not_in_db_rows) if not_in_db_rows else '<tr><td colspan="7" style="text-align:center; color:#16a34a; border:1px solid #94a3b8;">All BOM components are registered in database.</td></tr>'}
        </tbody>
    </table>

    <div class="footer">
        Omnix Inventory & Altium BOM Management System — Engineering Audit Report
    </div>
</body>
</html>
"""

            if file_path.lower().endswith(".html"):
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            else:
                # Render to Landscape PDF using QPrinter
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

