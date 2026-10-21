import os
from typing import List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QMessageBox, QWidget, QComboBox, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPageSize
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewWidget, QPrintDialog

from bom_auditor import BOMItem
from ui.printing.assembly_print_engine import AssemblyPrintEngine


class AssemblyPreviewDialog(QDialog):
    """
    Interactive Print Preview and Export modal dialog for Altium BOM Assembly Worksheets.
    Supports A5 Landscape (default) and A4 Landscape (fallback/selection).
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

        # Detect recommended paper size (A5 default, A4 fallback for large tables)
        self._initial_page_size = AssemblyPrintEngine.recommend_paper_size(self.bom_items)

        size_label = "A4" if self._initial_page_size == QPageSize.PageSizeId.A4 else "A5"
        self.setWindowTitle(f"Assembly Print Preview — {self.project_name} [{size_label} Landscape]")
        self.resize(1120, 780)
        self.setMinimumSize(920, 560)

        # Setup Landscape Printer for Preview
        self.printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        AssemblyPrintEngine.setup_printer(self.printer, page_size_id=self._initial_page_size)

        self._init_ui()

    def get_current_page_size_id(self) -> QPageSize.PageSizeId:
        if hasattr(self, "paper_combo") and self.paper_combo.currentData() is not None:
            return self.paper_combo.currentData()
        return self._initial_page_size

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Controls Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Paper Size Selection
        paper_lbl = QLabel("Paper:")
        paper_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(paper_lbl)

        self.paper_combo = QComboBox()
        self.paper_combo.addItem("A5 Landscape", QPageSize.PageSizeId.A5)
        self.paper_combo.addItem("A4 Landscape", QPageSize.PageSizeId.A4)
        if self._initial_page_size == QPageSize.PageSizeId.A4:
            self.paper_combo.setCurrentIndex(1)
        else:
            self.paper_combo.setCurrentIndex(0)
        self.paper_combo.setToolTip("Paper Size: A5 (210×148mm) or A4 (297×210mm)")

        combo_style = """
            QComboBox {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 6px;
                min-width: 105px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                border: 1px solid #334155;
                color: #f8fafc;
                selection-background-color: #0284c7;
            }
        """
        self.paper_combo.setStyleSheet(combo_style)
        self.paper_combo.currentIndexChanged.connect(self._on_paper_size_changed)
        top_bar.addWidget(self.paper_combo)

        top_bar.addSpacing(4)

        # View Mode Selection (All Pages / Single Page)
        view_lbl = QLabel("View:")
        view_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(view_lbl)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("All Pages", "all")
        self.view_mode_combo.addItem("Single Page", "single")
        view_combo_style = combo_style.replace("min-width: 105px;", "min-width: 85px;")
        self.view_mode_combo.setStyleSheet(view_combo_style)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        top_bar.addWidget(self.view_mode_combo)

        top_bar.addSpacing(4)

        # Multi-page Navigation
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setObjectName("secondaryBtn")
        self.prev_btn.setFixedWidth(28)
        self.prev_btn.setToolTip("Previous Page")
        self.prev_btn.clicked.connect(self._prev_page)
        top_bar.addWidget(self.prev_btn)

        self.page_lbl = QLabel("Page 1 of 1")
        self.page_lbl.setStyleSheet("color: #f8fafc; font-size: 11px; font-weight: bold; padding: 0 4px;")
        top_bar.addWidget(self.page_lbl)

        self.next_btn = QPushButton("▶")
        self.next_btn.setObjectName("secondaryBtn")
        self.next_btn.setFixedWidth(28)
        self.next_btn.setToolTip("Next Page")
        self.next_btn.clicked.connect(self._next_page)
        top_bar.addWidget(self.next_btn)

        top_bar.addSpacing(6)

        # Navigation & Zoom Controls
        self.fit_width_btn = QPushButton("↔ Fit Width")
        self.fit_width_btn.setObjectName("secondaryBtn")
        self.fit_width_btn.clicked.connect(lambda: self.preview_widget.fitToWidth())
        top_bar.addWidget(self.fit_width_btn)

        self.fit_page_btn = QPushButton("📄 Fit Page")
        self.fit_page_btn.setObjectName("secondaryBtn")
        self.fit_page_btn.clicked.connect(lambda: self.preview_widget.fitInView())
        top_bar.addWidget(self.fit_page_btn)

        self.zoom_in_btn = QPushButton("Zoom +")
        self.zoom_in_btn.setObjectName("secondaryBtn")
        self.zoom_in_btn.clicked.connect(lambda: self.preview_widget.zoomIn())
        top_bar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Zoom -")
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
        self.preview_widget.previewChanged.connect(self._update_page_nav)
        self.preview_widget.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;")
        main_layout.addWidget(self.preview_widget, 1)

    def _update_page_nav(self):
        total = max(1, self.preview_widget.pageCount())
        curr = max(1, self.preview_widget.currentPage())
        self.page_lbl.setText(f"Page {curr} of {total}")
        self.prev_btn.setEnabled(curr > 1)
        self.next_btn.setEnabled(curr < total)

    def _prev_page(self):
        curr = self.preview_widget.currentPage()
        if curr > 1:
            self.preview_widget.setCurrentPage(curr - 1)
            self._update_page_nav()

    def _next_page(self):
        curr = self.preview_widget.currentPage()
        if curr < self.preview_widget.pageCount():
            self.preview_widget.setCurrentPage(curr + 1)
            self._update_page_nav()

    def _on_view_mode_changed(self):
        mode = self.view_mode_combo.currentData()
        if mode == "single":
            self.preview_widget.setSinglePageViewMode()
        else:
            self.preview_widget.setAllPagesViewMode()
        self.preview_widget.fitInView()
        self._update_page_nav()

    def _on_paper_size_changed(self):
        page_size_id = self.get_current_page_size_id()
        size_label = "A4" if page_size_id == QPageSize.PageSizeId.A4 else "A5"
        self.setWindowTitle(f"Assembly Print Preview — {self.project_name} [{size_label} Landscape]")
        AssemblyPrintEngine.setup_printer(self.printer, page_size_id=page_size_id)
        self.preview_widget.updatePreview()
        self.preview_widget.fitInView()
        self._update_page_nav()

    def _on_paint_requested(self, printer: QPrinter):
        page_size_id = self.get_current_page_size_id()
        AssemblyPrintEngine.render_to_printer(
            printer=printer,
            bom_items=self.bom_items,
            project_name=self.project_name,
            total_qty=self.total_qty,
            page_size_id=page_size_id
        )

    def _handle_print(self):
        """Opens standard physical print dialog with safe cancellation and execution."""
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            page_size_id = self.get_current_page_size_id()
            AssemblyPrintEngine.setup_printer(printer, page_size_id=page_size_id)

            print_dialog = QPrintDialog(printer, self)
            size_name = "A4" if page_size_id == QPageSize.PageSizeId.A4 else "A5"
            print_dialog.setWindowTitle(f"Print Assembly Worksheet ({size_name} Landscape)")

            if print_dialog.exec() == QDialog.DialogCode.Accepted:
                if not printer.isValid():
                    QMessageBox.warning(self, "Printer Warning", "Selected printer is invalid or unavailable.")
                    return
                AssemblyPrintEngine.render_to_printer(
                    printer=printer,
                    bom_items=self.bom_items,
                    project_name=self.project_name,
                    total_qty=self.total_qty,
                    page_size_id=page_size_id
                )
                QMessageBox.information(self, "Printed", "Assembly worksheet sent to printer.")
        except Exception as e:
            QMessageBox.critical(self, "Print Error", f"An error occurred while printing: {e}")

    def _handle_save_pdf(self):
        """Prompts user for PDF destination and saves vector PDF with selected paper size."""
        page_size_id = self.get_current_page_size_id()
        default_name = AssemblyPrintEngine.get_default_pdf_filename(self.project_name, page_size_id=page_size_id)
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
                    output_filepath=file_path,
                    page_size_id=page_size_id
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
