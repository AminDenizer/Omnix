"""
Phase 1.3 Verification Tests:
- Settings Chevron Direction and Synchronization
- BOM Table Alignment, Word-Wrap, and Row Heights
- A5/A4 Print Preview Scaling, Paper Fallback, and PDF Generation
- Printer Dialog Safety and Error Handling
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QDialog, QTableWidgetItem
from PyQt6.QtCore import Qt, QSize, QSizeF, QRectF
from PyQt6.QtGui import QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem, BOMAuditResult
from ui.printing.assembly_print_engine import AssemblyPrintEngine
from ui.dialogs.assembly_preview_dialog import AssemblyPreviewDialog
from ui.widgets.assembly_preparation_widget import AssemblyTableWidget, AssemblyPreparationWidget
from ui.widgets.bom_audit_widget import BOMAuditWidget
from ui.widgets.sidebar import CollapsibleSidebar
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance for UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_sample_bom_items():
    """Create sample BOM items including a row with many designators."""
    return [
        BOMItem(
            row_idx=1,
            comment="100uF",
            description="Capacitor D Case 100uF 16VDC 10%",
            designator="C1",
            footprint="SMDCAPCASED",
            lib_ref="SMD Tantalum Capacitor",
            part_number="TAJD107K016RNJ",
            unit_qty=1,
            board_multiplier=1,
            package="D Case"
        ),
        BOMItem(
            row_idx=2,
            comment="100nF",
            description="Capacitor 0603 100nF 50V Ceramic Multilayer X7R",
            designator="C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C23, C24, C25, C26, C27, C28, C29, C30, C31, C32, C33, C34, C35, C36, C37, C38, C39",
            footprint="SMDCAP0603",
            lib_ref="SMD Ceramic Capacitor",
            part_number="GRM188R71H104KA93D",
            unit_qty=38,
            board_multiplier=1,
            package="0603"
        ),
    ]


class TestSettingsChevronDirectionAndState:
    """Tests chevron orientation, sync, and HiDPI rendering in CollapsibleSidebar."""

    def test_chevron_direction_toggle_and_sync(self, qapp):
        sidebar = CollapsibleSidebar()
        sidebar.show()
        qapp.processEvents()

        # Initial state: collapsed submenu -> chevron points right
        assert sidebar.is_submenu_expanded() is False
        assert sidebar.settings_parent_btn._chevron.direction == "right"

        # Expand submenu -> chevron points down
        sidebar.set_submenu_expanded(True)
        qapp.processEvents()
        assert sidebar.is_submenu_expanded() is True
        assert sidebar.settings_parent_btn._chevron.direction == "down"

        # Collapse again -> chevron points right
        sidebar.set_submenu_expanded(False)
        qapp.processEvents()
        assert sidebar.is_submenu_expanded() is False
        assert sidebar.settings_parent_btn._chevron.direction == "right"

        # Simulating button click cycle
        sidebar.settings_parent_btn.click()
        qapp.processEvents()
        assert sidebar.settings_parent_btn._chevron.direction == "down"

        sidebar.settings_parent_btn.click()
        qapp.processEvents()
        assert sidebar.settings_parent_btn._chevron.direction == "right"
        sidebar.close()

    def test_chevron_sync_when_navigating_to_child(self, qapp):
        sidebar = CollapsibleSidebar()
        sidebar.show()
        qapp.processEvents()

        # When navigating directly to a child destination, submenu auto-expands and chevron points down
        sidebar.set_active_page("settings_general")
        qapp.processEvents()
        assert sidebar.is_submenu_expanded() is True
        assert sidebar.settings_parent_btn._chevron.direction == "down"
        assert sidebar._submenu_buttons["general_settings"]._is_active is True
        assert sidebar.settings_parent_btn._is_active is True
        sidebar.close()


class TestBOMViewsAlignmentAndWrapping:
    """Tests alignment, word-wrapping, and vertical row height adjustment for both BOM views."""

    def test_assembly_table_alignment_and_word_wrap(self, qapp):
        table = AssemblyTableWidget()
        items = create_sample_bom_items()
        table.populate_items(items, "FC_IO_V1.3")

        # Word wrap must be enabled
        assert table.wordWrap() is True

        # Header alignment matches content alignment:
        # Col 0 (NO), Col 4 (Footprint), Col 5 (Qty), Col 7 (Package) are Centered
        # Col 1 (Comment), Col 2 (Desc), Col 3 (Designator), Col 6 (Part Number) are Left aligned
        assert table.horizontalHeaderItem(0).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.horizontalHeaderItem(4).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.horizontalHeaderItem(5).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.horizontalHeaderItem(7).textAlignment() == Qt.AlignmentFlag.AlignCenter

        assert table.horizontalHeaderItem(1).textAlignment() == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        assert table.horizontalHeaderItem(2).textAlignment() == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        assert table.horizontalHeaderItem(3).textAlignment() == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        assert table.horizontalHeaderItem(6).textAlignment() == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Cell alignments
        assert table.item(0, 0).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.item(0, 4).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.item(0, 5).textAlignment() == Qt.AlignmentFlag.AlignCenter
        assert table.item(0, 7).textAlignment() == Qt.AlignmentFlag.AlignCenter

        # Ensure row 1 (with 38 designators) is taller than row 0 (1 designator)
        table.resize(1000, 600)
        table._distribute_column_widths()
        table.resizeRowsToContents()
        qapp.processEvents()

        row0_height = table.rowHeight(0)
        row1_height = table.rowHeight(1)
        assert row1_height >= row0_height
        assert row1_height >= 40  # 38 designators wrapped across multiple lines

    def test_bom_audit_widget_word_wrap_and_alignment(self, qapp):
        widget = BOMAuditWidget(inventory_loader=MagicMock())
        assert widget.table.wordWrap() is True


class TestPrintPreviewScalingAndPaperFallback:
    """Tests A5/A4 recommendations, logical-point scaling, and preview rendering."""

    def test_recommend_paper_size(self):
        # Phase 1.4 standardizes on A4 Landscape
        items = [
            BOMItem(row_idx=1, comment="100uF", description="Capacitor 100uF", designator="C1, C2", unit_qty=2)
        ]
        assert AssemblyPrintEngine.recommend_paper_size(items) == QPageSize.PageSizeId.A4

        items_long = [
            BOMItem(row_idx=1, comment="100nF", description="Capacitor", designator=",".join([f"C{i}" for i in range(1, 60)]), unit_qty=59)
        ]
        assert AssemblyPrintEngine.recommend_paper_size(items_long) == QPageSize.PageSizeId.A4

    def test_generate_html_a5_and_a4(self):
        items = create_sample_bom_items()

        # A5 HTML
        html_a5 = AssemblyPrintEngine.generate_html(items, "FC_IO_V1.3", total_qty=39, page_size_id=QPageSize.PageSizeId.A5)
        assert "A5 landscape" in html_a5
        assert "6mm" in html_a5
        assert "font-size: 7.5pt" in html_a5

        # A4 HTML
        html_a4 = AssemblyPrintEngine.generate_html(items, "FC_IO_V1.3", total_qty=39, page_size_id=QPageSize.PageSizeId.A4)
        assert "A4 landscape" in html_a4
        assert "8mm" in html_a4
        assert "font-size: 8pt" in html_a4

    def test_render_to_printer_uses_points_not_pixels(self, qapp):
        items = create_sample_bom_items()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        AssemblyPrintEngine.setup_printer(printer, QPageSize.PageSizeId.A5)

        # HighResolution printer has high DPI (e.g. 600 or 1200 DPI)
        paint_pixels = printer.pageLayout().paintRectPixels(printer.resolution())
        paint_points = printer.pageLayout().paintRectPoints()

        # In HighResolution mode, pixels are much greater than points
        assert paint_pixels.width() > paint_points.width()

        # render_to_printer should calculate page size in points so it matches the canvas correctly
        doc = AssemblyPrintEngine.render_to_printer(printer, items, "FC_IO_V1.3", total_qty=39)
        assert abs(doc.pageSize().width() - paint_points.width()) < 1.0
        assert abs(doc.pageSize().height() - paint_points.height()) < 1.0

    def test_preview_dialog_paper_switching(self, qapp):
        items = create_sample_bom_items()
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=39)
        dialog.show()
        qapp.processEvents()

        # Paper combo is retained for backwards compatibility but standardized to A4
        assert hasattr(dialog, "paper_combo")
        assert dialog.paper_combo.count() == 1
        assert dialog.printer.pageLayout().pageSize().id() == QPageSize.PageSizeId.A4
        dialog.close()


class TestPreviewAndPdfSafety:
    """Tests that printing UI is completely removed while Assembly Preview and PDF export remain functional."""

    def test_assembly_preparation_widget_has_no_print_button(self, qapp):
        prep_widget = AssemblyPreparationWidget()
        items = create_sample_bom_items()
        prep_widget.bom_items = items
        prep_widget.table.populate_items(items, "FC_IO_V1.3")
        prep_widget.project_name = "FC_IO_V1.3"

        # Action bar must contain preview_btn and pdf_btn, but NO print_btn
        assert hasattr(prep_widget, "preview_btn")
        assert hasattr(prep_widget, "pdf_btn")
        assert not hasattr(prep_widget, "print_btn")
        assert not hasattr(prep_widget, "print_worksheet")

    def test_preview_dialog_has_no_print_button_and_retains_pdf(self, qapp):
        items = create_sample_bom_items()
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=39)

        # Dialog top bar must contain PDF export button, but NO physical print button or handler
        assert hasattr(dialog, "pdf_btn")
        assert not hasattr(dialog, "print_btn")
        assert not hasattr(dialog, "_handle_print")
        dialog.close()
