import os
import pytest
import openpyxl
from excel_loader import ExcelDataLoader, find_local_excel_file, normalize_string, clean_cell_value


@pytest.fixture
def temp_excel_file(tmp_path):
    file_path = str(tmp_path / 'Inventory.xlsx')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Inventory'

    headers = [
        'ECODE', 'PART NAME', 'DISCRIPTION', 'Quantity in Stock',
        'FOOTPRINT', 'PART NUMBER', 'LINK', 'Pisition', 'Unit Per length',
        'Min Stock', 'Target Stock'
    ]
    rows = [
        [None, 'NE555P', 'Precision Timer IC DIP-8', 5, 'DIP-8', 'NE555P', 'https://lionelectronic.ir/products/2070-NE555P', 'IC-01', None, 20, 50],
        [None, 'LM358N', 'Dual Op-Amp DIP-8', 10, 'DIP-8', 'LM358N', 'https://lionelectronic.ir/products/1932-LM358N', 'IC-02', None, 30, 60],
        [None, 'L7805CV', 'Linear Regulator TO-220', 2, 'TO-220', 'L7805CV', 'https://lionelectronic.ir/products/1954-L7805CV', 'REG-01', None, 10, 25],
        [None, 'IRLR024NTRPBF', 'N-CH MOS TO-252', 0, 'TO-252', 'IRLR024NTRPBF', 'https://lionelectronic.ir/products/2686-IRLR024NTRPBF', 'TR-02', None, 10, 20],
        [None, 'ATmega328P-PU', 'AVR Microcontroller', 2, 'DIP-28', 'ATmega328P-PU', None, 'MCU-01', None, 10, 20],
        [None, '1N4007', 'Rectifier Diode', 250, 'DO-41', '1N4007', 'https://lionelectronic.ir/products/1779-1N4007', 'D-01', None, 50, 100]
    ]

    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(file_path)
    wb.close()
    return file_path


class TestExcelDataLoader:
    def test_normalize_string(self):
        assert normalize_string('  NE555P  ') == 'ne555p'
        assert normalize_string('تست‌نرم‌افزار') == 'تستنرمافزار'
        assert normalize_string('سایت كالا يزد') == 'سایت کالا یزد'
        assert normalize_string('Part–Number—Test') == 'part-number-test'

    def test_clean_cell_value(self):
        assert clean_cell_value(None) == ''
        assert clean_cell_value(50.0) == '50'
        assert clean_cell_value(45) == '45'
        assert clean_cell_value('  Test IC  ') == 'Test IC'
        assert clean_cell_value(3.14159) == '3.1416'

    def test_strict_file_detection(self, tmp_path):
        app_dir = str(tmp_path)
        random_file = tmp_path / 'MyOtherData.xlsx'
        random_file.touch()
        assert find_local_excel_file(app_dir) is None

        inv_file = tmp_path / 'Inventory.xlsx'
        inv_file.touch()
        assert find_local_excel_file(app_dir) == str(inv_file)

    def test_load_and_shortages(self, temp_excel_file):
        loader = ExcelDataLoader()
        ok, msg = loader.load_file(temp_excel_file)
        assert ok is True
        assert loader.total_rows == 6

        shortages = loader.get_shortage_items()
        assert len(shortages) == 5

        ne555 = next(s for s in shortages if s['part_name'] == 'NE555P')
        assert ne555['current_stock'] == 5
        assert ne555['min_stock'] == 20
        assert ne555['target_stock'] == 50
        assert ne555['needed_qty'] == 45
        assert ne555['link_type'] == 'LION'

        mcu = next(s for s in shortages if s['part_name'] == 'ATmega328P-PU')
        assert mcu['needed_qty'] == 18
        assert mcu['link_type'] == 'NONE'

    def test_filter_rows(self, temp_excel_file):
        loader = ExcelDataLoader()
        loader.load_file(temp_excel_file)

        res = loader.filter_rows('LM358N')
        assert len(res) == 1
        assert 'LM358N' in res[0][1]

        res2 = loader.filter_rows('Timer DIP-8')
        assert len(res2) == 1
        assert 'NE555P' in res2[0][1]

        assert len(loader.filter_rows('')) == 6

    def test_batch_increment_stock_strictly(self, temp_excel_file):
        loader = ExcelDataLoader()
        loader.load_file(temp_excel_file)

        items_to_update = [
            {'orig_row_idx': 2, 'part_name': 'NE555P', 'actual_ordered_qty': 50, 'needed_qty': 45},
            {'orig_row_idx': 5, 'part_name': 'IRLR024NTRPBF', 'actual_ordered_qty': 0, 'needed_qty': 20},
        ]

        count, msg = loader.batch_increment_stock(items_to_update)
        assert count == 1

        loader.load_file(temp_excel_file)
        ne555_row = next(r for idx, r in loader.rows if 'NE555P' in r)
        irlr_row = next(r for idx, r in loader.rows if 'IRLR024NTRPBF' in r)

        stock_col = loader.get_column_index(['quantity in stock'])
        assert ne555_row[stock_col] == '55'
        assert irlr_row[stock_col] == '0'
