import os
from typing import List, Optional
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewWidget, QPrintDialog

from bom_auditor import BOMItem
from ui.printing.assembly_print_engine import AssemblyPrintEngine


class AssemblyPreviewDialog(QDialog):
    """
    Interactive Print Preview and Export modal dialog for Altium BOM Assembly Worksheets.
    Configured specifically for A5 Landscape orientation.
    """

    def __init__(
        self,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.bom_items = bom_items
        self.project_name = project_name
        self.total_qty = total_qty

        self.setWindowTitle(f"Assembly Print Preview — {self.project_name} [A5 Landscape]")
        self.resize(980, 680)
        self.setMinimumSize(800, 500)

        # Setup A5 Landscape Printer for Preview
        self.printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        AssemblyPrintEngine.setup_a5_printer(self.printer)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Controls Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Navigation & Zoom Controls
        self.fit_width_btn = QPushButton("↔ Fit Width")
        self.fit_width_btn.setObjectName("secondaryBtn")
        self.fit_width_btn.clicked.connect(lambda: self.preview_widget.fitToWidth())
        top_bar.addWidget(self.fit_width_btn)

        self.fit_page_btn = QPushButton("📄 Fit Page")
        self.fit_page_btn.setObjectName("secondaryBtn")
        self.fit_page_btn.clicked.connect(lambda: self.preview_widget.fitInView())
        top_bar.addWidget(self.fit_page_btn)

        self.zoom_in_btn = QPushButton("🔍 Zoom +")
        self.zoom_in_btn.setObjectName("secondaryBtn")
        self.zoom_in_btn.clicked.connect(lambda: self.preview_widget.zoomIn())
        top_bar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("🔍 Zoom -")
        self.zoom_out_btn.setObjectName("secondaryBtn")
        self.zoom_out_btn.clicked.connect(lambda: self.preview_widget.zoomOut())
        top_bar.addWidget(self.zoom_out_btn)

        top_bar.addStretch()

        # Action Buttons: Physical Print & Save PDF
        self.print_btn = QPushButton("🖨️ Print Sheet")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        self.print_btn.clicked.connect(self._handle_print)
        top_bar.addWidget(self.print_btn)

        self.pdf_btn = QPushButton("📥 Save as PDF")
        self.pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #34d399;
                color: #0f172a;
            }
        """)
        self.pdf_btn.clicked.connect(self._handle_save_pdf)
        top_bar.addWidget(self.pdf_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryBtn")
        self.close_btn.clicked.connect(self.accept)
        top_bar.addWidget(self.close_btn)

        main_layout.addLayout(top_bar)

        # 2. Preview Widget
        self.preview_widget = QPrintPreviewWidget(self.printer, self)
        self.preview_widget.paintRequested.connect(self._on_paint_requested)
        self.preview_widget.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;")
        main_layout.addWidget(self.preview_widget, 1)

    def _on_paint_requested(self, printer: QPrinter):
        AssemblyPrintEngine.render_to_printer(
            printer=printer,
            bom_items=self.bom_items,
            project_name=self.project_name,
            total_qty=self.total_qty
        )

    def _handle_print(self):
        """Opens standard physical print dialog."""
        print_dialog = QPrintDialog(self.printer, self)
        print_dialog.setWindowTitle("Print Assembly Worksheet (A5 Landscape)")
        if print_dialog.exec() == QDialog.DialogCode.Accepted:
            AssemblyPrintEngine.render_to_printer(
                printer=self.printer,
                bom_items=self.bom_items,
                project_name=self.project_name,
                total_qty=self.total_qty
            )
            QMessageBox.information(self, "Printed", "Assembly worksheet sent to printer.")

    def _handle_save_pdf(self):
        """Prompts user for PDF destination and saves A5 vector PDF."""
        default_name = AssemblyPrintEngine.get_default_pdf_filename(self.project_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Assembly Worksheet as Vector PDF",
            default_name,
            "PDF Files (*.pdf)"
        )
        if file_path:
            try:
                saved_path = AssemblyPrintEngine.export_pdf(
                    bom_items=self.bom_items,
                    project_name=self.project_name,
                    total_qty=self.total_qty,
                    output_filepath=file_path
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
