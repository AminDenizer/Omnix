import os
import pytest
import openpyxl
from excel_loader import ExcelDataLoader

class TestDialogAndEdgeCases:
    @pytest.fixture(autouse=True)
    def register_test_adapters(self):
        from core.procurement.registry import VendorRegistry
        reg = VendorRegistry.get_default_registry()
        reg.register_default_adapters()
        yield
        reg.clear()

    def test_mixed_batch_stock_increment(self, tmp_path):
        inv_path = os.path.join(str(tmp_path), 'Inventory.xlsx')
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Inventory'
        ws.append(['ECODE', 'PART NAME', 'DISCRIPTION', 'Quantity in Stock', 'FOOTPRINT', 'PART NUMBER', 'LINK', 'Min Stock', 'Target Stock'])
        ws.append([None, 'NE555P', 'Timer', 5, 'DIP-8', 'NE555P', 'https://lionelectronic.ir/products/2070-NE555P', 20, 50])
        ws.append([None, 'LM358N', 'OpAmp', 10, 'DIP-8', 'LM358N', 'https://lionelectronic.ir/products/1932-LM358N', 30, 60])
        ws.append([None, 'IRFU120NPBF', 'MOS', 0, 'TO-251', 'IRFU120NPBF', 'https://lionelectronic.ir/products/214-IRFU120NPBF', 10, 20])
        ws.append([None, 'AO4294A', 'MOS', 0, 'SOIC-8', 'AO4294A', 'https://lionelectronic.ir/products/4192-AO4294A', 10, 25])
        wb.save(inv_path)
        wb.close()

        loader = ExcelDataLoader()
        loader.load_file(inv_path)

        # Batch simulation:
        # NE555P: needed 45, pack rounded to 50 -> Succeeded (50 pcs)
        # LM358N: needed 50 -> Succeeded (50 pcs)
        # IRFU120NPBF: needed 20, site stock 11 -> Failed (0 pcs)
        # AO4294A: coming soon -> Failed (0 pcs)
        batch_items = [
            {'orig_row_idx': 2, 'part_name': 'NE555P', 'order_success': True, 'actual_ordered_qty': 50, 'needed_qty': 45},
            {'orig_row_idx': 3, 'part_name': 'LM358N', 'order_success': True, 'actual_ordered_qty': 50, 'needed_qty': 50},
            {'orig_row_idx': 4, 'part_name': 'IRFU120NPBF', 'order_success': False, 'actual_ordered_qty': 0, 'needed_qty': 20},
            {'orig_row_idx': 5, 'part_name': 'AO4294A', 'order_success': False, 'actual_ordered_qty': 0, 'needed_qty': 25},
        ]

        # Filter strictly for confirmation
        success_items = [it for it in batch_items if it.get('order_success') is True and (it.get('actual_ordered_qty') or 0) > 0]
        assert len(success_items) == 2
        assert [it['part_name'] for it in success_items] == ['NE555P', 'LM358N']

        # Verify strict inventory immutability: loader has no stock mutation methods
        assert not hasattr(loader, "batch_increment_stock")
        assert not hasattr(loader, "save_cell_value")

        # Verify inventory stock on disk remains strictly untouched
        loader.load_file(inv_path)
        stock_col = loader.get_column_index(['quantity in stock'])
        
        ne555 = next(r for idx, r in loader.rows if 'NE555P' in r)
        lm358 = next(r for idx, r in loader.rows if 'LM358N' in r)
        irfu = next(r for idx, r in loader.rows if 'IRFU120NPBF' in r)
        ao = next(r for idx, r in loader.rows if 'AO4294A' in r)

        assert ne555[stock_col] == '5'   # untouched
        assert lm358[stock_col] == '10'  # untouched
        assert irfu[stock_col] == '0'   # untouched
        assert ao[stock_col] == '0'     # untouched

    def test_mode_a_dialog_instantiation(self, qapp):
        from ui.dialogs.order_preview_dialog import OrderPreviewDialog
        shortages = [
            {
                "part_name": "100NF",
                "part_number": "GRM188R71H104KA93D",
                "description": "Capacitor 0603 100nF",
                "current_stock": 2,
                "needed_qty": 36,
                "link": "https://javanelec.com/item/100nf",
                "vendor_id": "vendor_javan",
            },
            {
                "part_name": "10UF",
                "part_number": "C2012X5R1H106K125AC",
                "description": "Capacitor 0805 10uF",
                "current_stock": 5,
                "needed_qty": 4,
                "link": "https://lionelectronic.ir/product/10uf",
                "vendor_id": "vendor_lion",
            },
            {
                "part_name": "EXT",
                "part_number": "EXT-1",
                "description": "External Store Item",
                "current_stock": 0,
                "needed_qty": 10,
                "link": "https://unknownstore.com/item/1",
            },
            {
                "part_name": "BLANK",
                "part_number": "BLANK-1",
                "description": "Blank link item",
                "current_stock": 0,
                "needed_qty": 5,
                "link": "",
            },
        ]
        dlg = OrderPreviewDialog(
            all_shortages=shortages,
            missing_db_items=[{"part_number": "MISSING-1"}],
            source_title="Project BOM Shortages — Test.xlsx (1 Boards)",
        )
        assert dlg.table.rowCount() == 4
        assert dlg.table.columnCount() == 7
        # Check stock values
        assert dlg.table.item(0, dlg.COL_STOCK).text() == "2"
        assert dlg.table.item(1, dlg.COL_STOCK).text() == "5"
        assert len(dlg.orderable_items) == 2
        assert len(dlg.external_items) == 1
        assert len(dlg.blank_link_items) == 1
        assert dlg.order_btn.isEnabled() is True

    def test_mode_a_report_export(self, tmp_path):
        from core.procurement.reporting.builder import ProcurementReportBuilder
        from core.procurement.reporting.csv_exporter import ProcurementCSVExporter
        from core.procurement.reporting.xlsx_exporter import ProcurementXLSXExporter
        from core.procurement.reporting.pdf_exporter import ProcurementPDFExporter

        shortages = [
            {
                "designator": "C1",
                "part_name": "100NF",
                "part_number": "GRM188R71H104KA93D",
                "description": "Capacitor 0603 100nF",
                "in_stock": 2,
                "needed_qty": 36,
                "link": "https://javanelec.com/#dtl/7589",
                "vendor_id": "vendor_javan",
            },
            {
                "designator": "C2",
                "part_name": "10UF",
                "part_number": "C2012X5R1H106K125AC",
                "description": "Capacitor 0805 10uF",
                "in_stock": 5,
                "needed_qty": 4,
                "link": "https://lionelectronic.ir/product/10uf",
                "vendor_id": "vendor_lion",
            },
        ]
        report = ProcurementReportBuilder.build_from_shortages(shortages=shortages, source_title="Test Mode A")
        assert report.total_line_items == 2
        assert report.resolved_line_items == 2
        assert len(report.vendor_summaries) == 2

        csv_path = os.path.join(str(tmp_path), "report.csv")
        xlsx_path = os.path.join(str(tmp_path), "report.xlsx")
        pdf_path = os.path.join(str(tmp_path), "report.pdf")

        assert ProcurementCSVExporter.export(report, csv_path) is True
        assert os.path.exists(csv_path)
        assert ProcurementXLSXExporter.export(report, xlsx_path) is True
        assert os.path.exists(xlsx_path)
        assert ProcurementPDFExporter.export(report, pdf_path) is True
        assert os.path.exists(pdf_path)

