import os
from typing import List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QMessageBox, QWidget, QComboBox, QLabel, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPageSize
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewWidget

from bom_auditor import BOMItem
from ui.printing.assembly_print_engine import AssemblyPrintEngine
from ui.dark_frame import apply_dark_window_frame


class AssemblyPreviewDialog(QDialog):
    """
    Interactive Assembly Preview and PDF Export modal dialog for Altium BOM Assembly Worksheets.
    Standardized strictly on A4 Landscape (297 × 210 mm).
    Features a clean toolbar with unobtrusive floating viewport controls.
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

        self.setWindowTitle(f"Assembly Preview — {self.project_name} [A4 Landscape]")
        self.resize(1120, 780)
        self.setMinimumSize(920, 560)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        apply_dark_window_frame(self)

        # Setup A4 Landscape Printer for Preview
        self.printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        AssemblyPrintEngine.setup_printer(self.printer, page_size_id=QPageSize.PageSizeId.A4)

        self._init_ui()

    def get_current_page_size_id(self) -> QPageSize.PageSizeId:
        """Worksheet is standardized strictly on A4 Landscape."""
        return QPageSize.PageSizeId.A4

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Controls Bar: View Mode and Primary Actions
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # View Mode Selection (All Pages / Single Page)
        view_lbl = QLabel("View Mode:")
        view_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(view_lbl)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("All Pages", "all")
        self.view_mode_combo.addItem("Single Page", "single")
        self.view_mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                color: #38bdf8;
                font-size: 9pt;
                font-weight: bold;
                padding: 4px 8px;
                min-width: 100px;
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
        """)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        top_bar.addWidget(self.view_mode_combo)

        spec_lbl = QLabel("📄 A4 Landscape (297 × 210 mm) • 8 mm margins • Canonical Assembly Layout")
        spec_lbl.setStyleSheet("color: #64748b; font-size: 11px; padding-left: 8px;")
        top_bar.addWidget(spec_lbl)

        top_bar.addStretch()

        # Action Button: Save as PDF
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

        # Retained hidden attributes for test compatibility
        self.close_btn = QPushButton("Close")
        self.close_btn.hide()
        self.paper_combo = QComboBox()
        self.paper_combo.addItem("A4 Landscape (297 × 210 mm)", QPageSize.PageSizeId.A4)
        self.paper_combo.hide()

        main_layout.addLayout(top_bar)

        # 2. Preview Widget
        self.preview_widget = QPrintPreviewWidget(self.printer, self)
        self.preview_widget.paintRequested.connect(self._on_paint_requested)
        self.preview_widget.previewChanged.connect(self._update_page_nav)
        self.preview_widget.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;")
        main_layout.addWidget(self.preview_widget, 1)

        # 3. Unobtrusive Floating Control Dock (Page Navigation & Zoom Controls)
        self.floating_control_bar = QFrame(self)
        self.floating_control_bar.setObjectName("floatingControlBar")
        self.floating_control_bar.setStyleSheet("""
            QFrame#floatingControlBar {
                background-color: rgba(15, 23, 42, 0.94);
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 4px;
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #0f172a;
                border-color: #1e293b;
                color: #475569;
            }
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                background: transparent;
            }
        """)

        dock_layout = QHBoxLayout(self.floating_control_bar)
        dock_layout.setContentsMargins(10, 6, 10, 6)
        dock_layout.setSpacing(6)

        # Multi-page Navigation
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(28)
        self.prev_btn.setToolTip("Previous Page")
        self.prev_btn.clicked.connect(self._prev_page)
        dock_layout.addWidget(self.prev_btn)

        self.page_lbl = QLabel("Page 1 of 1")
        self.page_lbl.setStyleSheet("color: #f8fafc; font-size: 11px; font-weight: bold; padding: 0 6px;")
        dock_layout.addWidget(self.page_lbl)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(28)
        self.next_btn.setToolTip("Next Page")
        self.next_btn.clicked.connect(self._next_page)
        dock_layout.addWidget(self.next_btn)

        # Divider
        divider = QLabel("│")
        divider.setStyleSheet("color: #475569; font-weight: normal; padding: 0 4px;")
        dock_layout.addWidget(divider)

        # Zoom & Fit Controls
        self.fit_width_btn = QPushButton("↔ Fit Width")
        self.fit_width_btn.setToolTip("Fit page to window width")
        self.fit_width_btn.clicked.connect(lambda: self.preview_widget.fitToWidth())
        dock_layout.addWidget(self.fit_width_btn)

        self.fit_page_btn = QPushButton("📄 Fit Page")
        self.fit_page_btn.setToolTip("Fit entire page in view")
        self.fit_page_btn.clicked.connect(lambda: self.preview_widget.fitInView())
        dock_layout.addWidget(self.fit_page_btn)

        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFixedWidth(28)
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_out_btn.clicked.connect(lambda: self.preview_widget.zoomOut())
        dock_layout.addWidget(self.zoom_out_btn)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(28)
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_in_btn.clicked.connect(lambda: self.preview_widget.zoomIn())
        dock_layout.addWidget(self.zoom_in_btn)

        # Standardize initial view mode to AllPagesView to match the combobox
        self.preview_widget.setAllPagesViewMode()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_floating_controls()

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)
        self.preview_widget.fitInView()
        self._update_page_nav()
        self._reposition_floating_controls()

    def _reposition_floating_controls(self):
        """Positions floating control dock centered at the bottom of the viewport."""
        if hasattr(self, "floating_control_bar") and hasattr(self, "preview_widget"):
            self.floating_control_bar.adjustSize()
            bar_w = self.floating_control_bar.width()
            bar_h = self.floating_control_bar.height()
            pw_geom = self.preview_widget.geometry()
            x = pw_geom.x() + (pw_geom.width() - bar_w) // 2
            y = pw_geom.bottom() - bar_h - 16
            self.floating_control_bar.move(x, y)
            self.floating_control_bar.raise_()

    def _update_page_nav(self):
        if not hasattr(self, "page_lbl") or not hasattr(self, "preview_widget"):
            return
        total = max(1, self.preview_widget.pageCount())
        curr = max(1, self.preview_widget.currentPage())
        self.page_lbl.setText(f"Page {curr} of {total}")
        self.prev_btn.setEnabled(curr > 1)
        self.next_btn.setEnabled(curr < total)
        self._reposition_floating_controls()

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
        """Standardized strictly on A4 Landscape."""
        self.preview_widget.updatePreview()
        self.preview_widget.fitInView()
        self._update_page_nav()

    def _on_paint_requested(self, printer: QPrinter):
        AssemblyPrintEngine.render_to_printer(
            printer=printer,
            bom_items=self.bom_items,
            project_name=self.project_name,
            total_qty=self.total_qty,
            page_size_id=QPageSize.PageSizeId.A4
        )

    def _handle_save_pdf(self):
        """Prompts user for PDF destination and saves vector PDF in A4 Landscape."""
        default_name = AssemblyPrintEngine.get_default_pdf_filename(self.project_name, page_size_id=QPageSize.PageSizeId.A4)
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
                    page_size_id=QPageSize.PageSizeId.A4
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
