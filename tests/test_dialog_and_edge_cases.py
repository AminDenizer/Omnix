import os
import pytest
import openpyxl
from excel_loader import ExcelDataLoader

class TestDialogAndEdgeCases:
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

        # Execute stock update
        count, msg = loader.batch_increment_stock(success_items)
        assert count == 2

        # Re-read file to verify exact disk state
        loader.load_file(inv_path)
        stock_col = loader.get_column_index(['quantity in stock'])
        
        ne555 = next(r for idx, r in loader.rows if 'NE555P' in r)
        lm358 = next(r for idx, r in loader.rows if 'LM358N' in r)
        irfu = next(r for idx, r in loader.rows if 'IRFU120NPBF' in r)
        ao = next(r for idx, r in loader.rows if 'AO4294A' in r)

        assert ne555[stock_col] == '55'  # 5 + 50
        assert lm358[stock_col] == '60'  # 10 + 50
        assert irfu[stock_col] == '0'    # untouched
        assert ao[stock_col] == '0'      # untouched
