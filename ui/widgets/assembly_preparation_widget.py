import os
import webbrowser
from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QFrame, QFileDialog,
    QHeaderView, QApplication, QMenu, QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPageSize
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from bom_auditor import BOMAuditResult, BOMItem
from ui.printing.assembly_print_engine import AssemblyPrintEngine
from ui.dialogs.assembly_preview_dialog import AssemblyPreviewDialog
from ui.widgets.bom_audit_widget import DropZoneFrame


class AssemblyTableWidget(QTableWidget):
    """
    High-contrast engineering table widget for Altium BOM Assembly Preparation.
    Conforms to the 9-column contract:
    | <PROJECT_NAME> | Comment | Description | Designator | Footprint | LibRef | Quantity | Part Number | Package |
    """

    COLUMN_COUNT = 9
    DEFAULT_HEADERS = [
        "Project Name", "Comment", "Description", "Designator",
        "Footprint", "LibRef", "Quantity", "Part Number", "Package"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(self.COLUMN_COUNT)
        self.setHorizontalHeaderLabels(self.DEFAULT_HEADERS)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Header resize modes and alignments
        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Specific column header alignments
        for c in range(self.COLUMN_COUNT):
            item = self.horizontalHeaderItem(c)
            if item:
                if c in (0, 4, 6, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet("""
            QTableWidget {
                background-color: #0b101b;
                alternate-background-color: #0f172a;
                gridline-color: #1e293b;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #1e293b;
            }
            QTableWidget::item:selected {
                background-color: #1e3a8a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0d1527;
                color: #94a3b8;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 8px;
                border: 1px solid #1e293b;
            }
        """)

    def set_project_name_header(self, project_name: str):
        """Sets the first column header to the authoritative project name."""
        header_item = QTableWidgetItem(project_name)
        header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        header_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        header_item.setFont(header_font)
        header_item.setForeground(QColor("#38bdf8"))
        self.setHorizontalHeaderItem(0, header_item)

    def populate_items(self, items: List[BOMItem], project_name: str):
        """Populates the 9-column assembly table with exact BOM data and sequential N-markers."""
        self.setUpdatesEnabled(False)
        self.setRowCount(0)
        self.set_project_name_header(project_name)

        mono_font = QFont("Consolas", 10)
        bold_mono_font = QFont("Consolas", 10, QFont.Weight.Bold)
        bold_font = QFont("Segoe UI", 10, QFont.Weight.Bold)

        self.setRowCount(len(items))

        for row_idx, item in enumerate(items):
            n_marker = f"N{row_idx + 1}"
            comment = str(item.comment or "").strip()
            description = str(item.description or "").strip()
            designator = str(item.designator or "").strip()
            footprint = str(item.footprint or "").strip()
            lib_ref = str(item.lib_ref or "").strip()
            qty = str(getattr(item, "total_needed_qty", getattr(item, "unit_qty", 1)))
            part_number = str(item.part_number or "").strip()
            package = str(item.package or item.footprint or "").strip()

            # Col 0: N Marker
            it_n = QTableWidgetItem(n_marker)
            it_n.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_n.setFont(bold_mono_font)
            it_n.setForeground(QColor("#38bdf8"))
            self.setItem(row_idx, 0, it_n)

            # Col 1: Comment
            it_comment = QTableWidgetItem(comment)
            it_comment.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row_idx, 1, it_comment)

            # Col 2: Description
            it_desc = QTableWidgetItem(description)
            it_desc.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if description:
                it_desc.setToolTip(description)
            self.setItem(row_idx, 2, it_desc)

            # Col 3: Designator
            it_desig = QTableWidgetItem(designator)
            it_desig.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            it_desig.setFont(mono_font)
            it_desig.setForeground(QColor("#e2e8f0"))
            if designator:
                it_desig.setToolTip(designator)
            self.setItem(row_idx, 3, it_desig)

            # Col 4: Footprint
            it_fp = QTableWidgetItem(footprint)
            it_fp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_fp.setFont(mono_font)
            it_fp.setForeground(QColor("#94a3b8"))
            self.setItem(row_idx, 4, it_fp)

            # Col 5: LibRef
            it_lib = QTableWidgetItem(lib_ref)
            it_lib.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row_idx, 5, it_lib)

            # Col 6: Quantity
            it_qty = QTableWidgetItem(qty)
            it_qty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_qty.setFont(bold_font)
            it_qty.setForeground(QColor("#f8fafc"))
            self.setItem(row_idx, 6, it_qty)

            # Col 7: Part Number (MPN)
            it_pn = QTableWidgetItem(part_number)
            it_pn.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            it_pn.setFont(bold_mono_font)
            it_pn.setForeground(QColor("#38bdf8"))
            if part_number:
                it_pn.setToolTip(part_number)
            self.setItem(row_idx, 7, it_pn)

            # Col 8: Package
            it_pkg = QTableWidgetItem(package)
            it_pkg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pkg.setFont(mono_font)
            it_pkg.setForeground(QColor("#cbd5e1"))
            self.setItem(row_idx, 8, it_pkg)

        self.setUpdatesEnabled(True)
        self.resizeRowsToContents()
        self._distribute_column_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._distribute_column_widths()

    def _distribute_column_widths(self):
        """Distributes extra viewport width to Description and Designator while keeping others compact."""
        total_w = self.viewport().width()
        if total_w <= 0:
            return

        base_widths = {
            0: 85,   # N Marker / Project Name
            1: 110,  # Comment
            2: 240,  # Description
            3: 180,  # Designator
            4: 110,  # Footprint
            5: 110,  # LibRef
            6: 60,   # Quantity
            7: 160,  # Part Number
            8: 95,   # Package
        }
        base_sum = sum(base_widths.values())  # 1150
        if total_w > base_sum:
            extra = total_w - base_sum
            desc_extra = int(extra * 0.6)
            desig_extra = extra - desc_extra
            for c, w in base_widths.items():
                if c == 2:
                    self.setColumnWidth(c, w + desc_extra)
                elif c == 3:
                    self.setColumnWidth(c, w + desig_extra)
                else:
                    self.setColumnWidth(c, w)
        else:
            for c, w in base_widths.items():
                self.setColumnWidth(c, w)
        self.resizeRowsToContents()

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        val = item.text().strip()

        copy_cell_act = menu.addAction("📋 Copy Cell Value")
        copy_cell_act.triggered.connect(lambda: QApplication.clipboard().setText(val))

        row = item.row()
        copy_row_act = menu.addAction("📑 Copy Entire Row (TSV)")
        copy_row_act.triggered.connect(lambda: self._copy_row_tsv(row))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_row_tsv(self, row: int):
        row_values = []
        for col in range(self.columnCount()):
            it = self.item(row, col)
            row_values.append(it.text().strip() if it else "")
        tsv_line = "\t".join(row_values)
        QApplication.clipboard().setText(tsv_line)


class AssemblyPreparationWidget(QWidget):
    """
    Dedicated Tab 3 Widget: 🔧 Assembly & BOM Preparation
    Consumes the active Altium BOMAuditResult, displays the 9-column assembly worksheet,
    generates automatic N1...Nn markers, and provides A5 Landscape print preview and PDF export.
    """

    bomFileRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audit_result: Optional[BOMAuditResult] = None
        self.bom_items: List[BOMItem] = []
        self.project_name: str = "UNTITLED_PROJECT"
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 8)
        main_layout.setSpacing(10)

        # 1. Top Ribbon & Actions Card (shown when BOM loaded)
        self.top_card = QFrame()
        self.top_card.setObjectName("ribbonFrame")
        top_layout = QHBoxLayout(self.top_card)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(14)

        self.project_info_lbl = QLabel("No Altium BOM Loaded")
        self.project_info_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        top_layout.addWidget(self.project_info_lbl)

        # Summary Pills
        self.pill_items_count = QLabel("Items: 0")
        self.pill_items_count.setStyleSheet("background-color: #131d31; border: 1px solid #22324e; border-radius: 6px; padding: 4px 10px; font-weight: 500; font-size: 12px;")
        top_layout.addWidget(self.pill_items_count)

        self.pill_total_qty = QLabel("Total Quantity: 0 pcs")
        self.pill_total_qty.setStyleSheet("background-color: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;")
        top_layout.addWidget(self.pill_total_qty)

        top_layout.addStretch()

        # Action Buttons
        self.preview_btn = QPushButton("👁️ Print Preview")
        self.preview_btn.setObjectName("secondaryBtn")
        self.preview_btn.clicked.connect(self.open_print_preview)
        top_layout.addWidget(self.preview_btn)

        self.print_btn = QPushButton("🖨️ Print Worksheet")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        self.print_btn.clicked.connect(self.print_a5_sheet)
        top_layout.addWidget(self.print_btn)

        self.pdf_btn = QPushButton("📥 Export Assembly PDF")
        self.pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #34d399;
                color: #0f172a;
            }
        """)
        self.pdf_btn.clicked.connect(self.export_pdf)
        top_layout.addWidget(self.pdf_btn)

        main_layout.addWidget(self.top_card)
        self.top_card.hide()

        # 2. Unified Drop Zone (shown by default when no BOM loaded)
        self.drop_zone = DropZoneFrame()
        self.drop_zone.fileDropped.connect(self._on_file_dropped)
        main_layout.addWidget(self.drop_zone)

        # 3. Canonical 9-Column Assembly Table
        self.table = AssemblyTableWidget(self)
        main_layout.addWidget(self.table)
        self.table.hide()

    def _on_file_dropped(self, file_path: str):
        """Emits signal so parent window can audit and synchronize the BOM file."""
        self.bomFileRequested.emit(file_path)

    def set_bom_data(self, audit_result: Optional[BOMAuditResult]):
        """Consumes active BOMAuditResult and renders the Assembly worksheet."""
        if not audit_result or not audit_result.items:
            self.clear_bom()
            return

        self.audit_result = audit_result
        self.bom_items = audit_result.items
        self.project_name = AssemblyPrintEngine.extract_project_name(
            audit_result.file_name or audit_result.file_path
        )

        total_items = len(self.bom_items)
        total_pcs = sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in self.bom_items)

        self.project_info_lbl.setText(f"📄 Project: <b>{self.project_name}</b>")
        self.pill_items_count.setText(f"Items: {total_items}")
        self.pill_total_qty.setText(f"Total Quantity: {total_pcs} pcs")

        self.table.populate_items(self.bom_items, self.project_name)

        self.drop_zone.hide()
        self.top_card.show()
        self.table.show()

    def clear_bom(self):
        """Resets Assembly view back to empty drop zone state."""
        self.audit_result = None
        self.bom_items = []
        self.project_name = "UNTITLED_PROJECT"

        self.table.setRowCount(0)
        self.top_card.hide()
        self.table.hide()
        self.drop_zone.show()

    def open_print_preview(self):
        """Opens interactive A5 Landscape print preview modal dialog."""
        if not self.bom_items:
            QMessageBox.warning(self, "No BOM Loaded", "Please load an Altium BOM project first.")
            return

        total_pcs = sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in self.bom_items)
        dialog = AssemblyPreviewDialog(
            bom_items=self.bom_items,
            project_name=self.project_name,
            total_qty=total_pcs,
            parent=self
        )
        dialog.exec()

    def print_a5_sheet(self):
        """Directly sends Landscape assembly worksheet (A5 or A4) to a physical printer."""
        if not self.bom_items:
            QMessageBox.warning(self, "No BOM Loaded", "Please load an Altium BOM project first.")
            return

        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            rec_size = AssemblyPrintEngine.recommend_paper_size(self.bom_items)
            AssemblyPrintEngine.setup_printer(printer, page_size_id=rec_size)

            print_dialog = QPrintDialog(printer, self)
            size_name = "A4" if rec_size == QPageSize.PageSizeId.A4 else "A5"
            print_dialog.setWindowTitle(f"Print Assembly Worksheet ({size_name} Landscape)")
            print_dialog.setOption(QPrintDialog.PrintDialogOption.PrintCollateCopies, False)

            res = print_dialog.exec()
            if res == QDialog.DialogCode.Accepted:
                if not printer.isValid():
                    QMessageBox.warning(self, "Printer Warning", "Selected printer is invalid or not available.")
                    return
                total_pcs = sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in self.bom_items)
                AssemblyPrintEngine.render_to_printer(
                    printer=printer,
                    bom_items=self.bom_items,
                    project_name=self.project_name,
                    total_qty=total_pcs,
                    page_size_id=rec_size
                )
                QMessageBox.information(self, "Printed", "Assembly worksheet sent to printer successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Print Error", f"An error occurred while printing: {e}")

    def export_pdf(self):
        """Exports the Assembly worksheet to a Landscape vector PDF (A5 or A4)."""
        if not self.bom_items:
            QMessageBox.warning(self, "No BOM Loaded", "Please load an Altium BOM project first.")
            return

        rec_size = AssemblyPrintEngine.recommend_paper_size(self.bom_items)
        default_name = AssemblyPrintEngine.get_default_pdf_filename(self.project_name, page_size_id=rec_size)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Assembly Worksheet as Vector PDF",
            default_name,
            "PDF Files (*.pdf)"
        )
        if file_path:
            try:
                total_pcs = sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in self.bom_items)
                saved_path = AssemblyPrintEngine.export_pdf(
                    bom_items=self.bom_items,
                    project_name=self.project_name,
                    total_qty=total_pcs,
                    output_filepath=file_path,
                    page_size_id=rec_size
                )
                QMessageBox.information(
                    self,
                    "PDF Exported",
                    f"Assembly worksheet PDF saved successfully to:\n{saved_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export Assembly PDF:\n{str(e)}"
                )
