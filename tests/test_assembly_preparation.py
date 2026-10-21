import os
import pytest
from typing import List
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem, BOMAuditResult
from core.procurement.models import ProcurementMode
from ui.printing.assembly_print_engine import AssemblyPrintEngine
from ui.dialogs.assembly_preview_dialog import AssemblyPreviewDialog
from ui.widgets.assembly_preparation_widget import AssemblyTableWidget, AssemblyPreparationWidget
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance for all UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_sample_bom_items() -> List[BOMItem]:
    """Helper to create a representative set of normalized Altium BOMItems."""
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
            comment="4.7uF",
            description="Capacitor 0805 4.7uF 50VDC 10%",
            designator="C2,C23",
            footprint="SMDCAP0805",
            lib_ref="SMD Ceramic Capacitor",
            part_number="C2012X5R1H475K125AB",
            unit_qty=2,
            board_multiplier=1,
            package="0805"
        ),
        BOMItem(
            row_idx=3,
            comment="خازن ۱۰ نانو",
            description="خازن سرامیکی smd 100nF 50V 0603",
            designator="C3,C4,C5,C6",
            footprint="SMDCAP0603",
            lib_ref="SMD Ceramic Capacitor",
            part_number="GRM188R71H104KA93D",
            unit_qty=4,
            board_multiplier=1,
            package="0603"
        ),
    ]


class TestAssemblyProjectNameContract:
    """Tests for Authoritative Project Name stem extraction."""

    def test_project_name_stem_extraction(self):
        assert AssemblyPrintEngine.extract_project_name("FC_IO_V1.3.xlsx") == "FC_IO_V1.3"
        assert AssemblyPrintEngine.extract_project_name("Motor_Controller_Rev2.xlsx") == "Motor_Controller_Rev2"
        assert AssemblyPrintEngine.extract_project_name("PowerSupply_V3.xls") == "PowerSupply_V3"
        assert AssemblyPrintEngine.extract_project_name("C:/altium/projects/Sample_Board_v2.1.xlsm") == "Sample_Board_v2.1"
        assert AssemblyPrintEngine.extract_project_name("") == "UNTITLED_PROJECT"
        assert AssemblyPrintEngine.extract_project_name(None) == "UNTITLED_PROJECT"

    def test_default_pdf_filename(self):
        fn = AssemblyPrintEngine.get_default_pdf_filename("FC_IO_V1.3")
        assert fn == "FC_IO_V1.3_Assembly_Worksheet_A5.pdf"


class TestAssemblyNNumberingContract:
    """Tests for N1...Nn row marker generation and isolation."""

    def test_n_numbering_sequential_1_based(self, qapp):
        items = create_sample_bom_items()
        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        assert table.rowCount() == 3
        assert table.item(0, 0).text() == "N1"
        assert table.item(1, 0).text() == "N2"
        assert table.item(2, 0).text() == "N3"

    def test_project_name_appears_only_in_column_0_header(self, qapp):
        items = create_sample_bom_items()
        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        # Header 0 must be NO (project name is in heading card above table)
        assert table.horizontalHeaderItem(0).text() == "NO"

        # Data cells in column 0 must be N1...Nn ONLY (not prepended with project name)
        for r in range(table.rowCount()):
            cell_text = table.item(r, 0).text()
            assert cell_text == f"N{r + 1}"
            assert "FC_IO_V1.3" not in cell_text

    def test_second_bom_resets_numbering_to_n1(self, qapp):
        widget = AssemblyPreparationWidget()

        # Load BOM A (3 items)
        res_a = BOMAuditResult(
            file_path="C:/projects/Board_A_Rev1.xlsx",
            board_multiplier=1
        )
        res_a.items = create_sample_bom_items()
        widget.set_bom_data(res_a)
        assert widget.project_name == "Board_A_Rev1"
        assert widget.table.rowCount() == 3
        assert widget.table.item(0, 0).text() == "N1"
        assert widget.table.item(2, 0).text() == "N3"

        # Load BOM B (2 items)
        res_b = BOMAuditResult(
            file_path="C:/projects/Board_B_Rev2.xlsx",
            board_multiplier=1
        )
        res_b.items = create_sample_bom_items()[:2]
        widget.set_bom_data(res_b)
        assert widget.project_name == "Board_B_Rev2"
        assert widget.table.rowCount() == 2
        assert widget.table.item(0, 0).text() == "N1"
        assert widget.table.item(1, 0).text() == "N2"


class TestAssemblyTableContract:
    """Tests for exact 8-column assembly table structure and data preservation."""

    def test_assembly_table_columns_and_data_preservation(self, qapp):
        items = create_sample_bom_items()
        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        assert table.columnCount() == 8
        assert [table.horizontalHeaderItem(c).text() for c in range(8)] == [
            "NO", "Comment", "Description", "Designator", "Footprint", "Qty", "Part Number", "Package"
        ]

        # Row 1: C2,C23 multi-designator
        assert table.item(1, 0).text() == "N2"
        assert table.item(1, 1).text() == "4.7uF"
        assert table.item(1, 2).text() == "Capacitor 0805 4.7uF 50VDC 10%"
        assert table.item(1, 3).text() == "C2,C23"
        assert table.item(1, 4).text() == "SMDCAP0805"
        assert table.item(1, 5).text() == "2"
        assert table.item(1, 6).text() == "C2012X5R1H475K125AB"
        assert table.item(1, 7).text() == "0805"

    def test_package_fallback_when_package_empty(self, qapp):
        item_no_pkg = BOMItem(
            row_idx=1,
            comment="10k",
            description="RES 10K",
            designator="R1",
            footprint="RES0603",
            lib_ref="RES",
            part_number="RC0603FR-0710KL",
            unit_qty=1,
            package=""  # Empty package string
        )
        table = AssemblyTableWidget()
        table.populate_items([item_no_pkg], "TestProj")
        # Should fallback to footprint in column 7 (Package)
        assert table.item(0, 7).text() == "RES0603"

    def test_copy_tsv_row(self, qapp):
        items = create_sample_bom_items()
        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")
        table._copy_row_tsv(0)

        clipboard_text = QApplication.clipboard().text()
        assert "N1" in clipboard_text
        assert "TAJD107K016RNJ" in clipboard_text
        assert "100uF" in clipboard_text


class TestAssemblyPrintEngine:
    """Tests for A5 Landscape HTML generation, margins, and vector PDF export."""

    def test_a5_landscape_printer_geometry(self):
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        AssemblyPrintEngine.setup_a5_printer(printer)

        assert printer.pageLayout().pageSize().id() == QPageSize.PageSizeId.A5
        assert printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape

    def test_generate_html_content_and_rtl_support(self):
        items = create_sample_bom_items()
        html_output = AssemblyPrintEngine.generate_html(items, "FC_IO_V1.3", total_qty=7)

        assert "FC_IO_V1.3" in html_output
        assert "A5 landscape" in html_output
        assert "6mm" in html_output
        assert "col-no-header" in html_output
        assert "N1" in html_output
        assert "N2" in html_output
        assert "N3" in html_output
        assert "TAJD107K016RNJ" in html_output
        assert "C2,C23" in html_output
        assert "خازن ۱۰ نانو" in html_output
        assert "dir=\"auto\"" in html_output

    def test_deterministic_html_generation(self):
        items = create_sample_bom_items()
        html1 = AssemblyPrintEngine.generate_html(items, "FC_IO_V1.3", total_qty=7)
        html2 = AssemblyPrintEngine.generate_html(items, "FC_IO_V1.3", total_qty=7)
        assert html1 == html2

    def test_pdf_export_file_creation(self, tmp_path, qapp):
        items = create_sample_bom_items()
        pdf_path = str(tmp_path / "FC_IO_V1.3_Assembly_Worksheet_A5.pdf")

        exported_path = AssemblyPrintEngine.export_pdf(
            bom_items=items,
            project_name="FC_IO_V1.3",
            total_qty=7,
            output_filepath=pdf_path
        )

        assert os.path.exists(exported_path)
        assert os.path.getsize(exported_path) > 0

        # Verify PDF magic bytes
        with open(exported_path, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"


class TestAssemblyDialogsAndUX:
    """Tests for AssemblyPreviewDialog and interactive actions."""

    def test_preview_dialog_initialization(self, qapp):
        items = create_sample_bom_items()
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=7)
        assert dialog.project_name == "FC_IO_V1.3"
        assert dialog.printer.pageLayout().pageSize().id() == QPageSize.PageSizeId.A5
        assert dialog.printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape

        # Trigger paint event on printer
        mock_printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        AssemblyPrintEngine.setup_a5_printer(mock_printer)
        dialog._on_paint_requested(mock_printer)


class TestProcurementAndStateIsolation:
    """Tests guaranteeing that Assembly workflow does not mutate BOM data or procurement state."""

    def test_assembly_does_not_mutate_bom_item_attributes(self, qapp):
        items = create_sample_bom_items()
        original_comment = items[0].comment
        original_mpn = items[0].part_number
        original_qty = items[0].unit_qty

        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        # Ensure no N-attribute was injected into BOMItem
        assert not hasattr(items[0], "n_marker")
        assert items[0].comment == original_comment
        assert items[0].part_number == original_mpn
        assert items[0].unit_qty == original_qty

    def test_main_window_three_tabs_and_wiring(self, qapp):
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file="")
            assert win.tabs.count() == 3
            assert "Inventory" in win.tabs.tabText(0)
            assert "Auditor" in win.tabs.tabText(1)
            assert "Assembly" in win.tabs.tabText(2)

            # Verify AssemblyPreparationWidget instance is attached
            assert isinstance(win.assembly_widget, AssemblyPreparationWidget)

            # Simulate BOM load in Auditor and verify Tab 3 receives data
            sample_res = BOMAuditResult(
                file_path="D:/projects/FC_IO_V1.3.xlsx",
                board_multiplier=1
            )
            sample_res.items = create_sample_bom_items()
            win.bom_audit_widget.audit_result = sample_res
            win.bom_audit_widget.bomLoaded.emit(sample_res)

            assert win.assembly_widget.project_name == "FC_IO_V1.3"
            assert win.assembly_widget.table.rowCount() == 3
            assert win.assembly_widget.table.item(0, 0).text() == "N1"

            # Simulate BOM unload and verify Tab 3 clears
            win.bom_audit_widget.bomUnloaded.emit()
            assert win.assembly_widget.audit_result is None
            assert win.assembly_widget.table.rowCount() == 0
            win._is_force_closing = True
            win.close()
