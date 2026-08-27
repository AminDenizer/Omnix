import os
import tempfile
import pytest
from models import Component
from export_utils import export_to_excel, export_to_csv


class TestExportUtils:
    """Test suite for Excel and CSV export functions."""

    def test_export_to_excel(self, sample_component):
        temp_dir = tempfile.mkdtemp()
        xlsx_path = os.path.join(temp_dir, "test_out.xlsx")

        res_path = export_to_excel([sample_component], xlsx_path)
        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 0

        # Verify reading generated Excel file using openpyxl
        import openpyxl
        wb = openpyxl.load_workbook(res_path)
        sheet = wb.active
        # Check that header row exists
        assert sheet.max_row >= 2
        # Check first data row contains the component value
        found_val = False
        for row in sheet.iter_rows(values_only=True):
            if sample_component.value in str(row):
                found_val = True
                break
        assert found_val is True

        # Cleanup
        wb.close()
        os.remove(xlsx_path)
        os.rmdir(temp_dir)

    def test_export_to_csv(self, sample_component):
        temp_dir = tempfile.mkdtemp()
        csv_path = os.path.join(temp_dir, "test_out.csv")

        res_path = export_to_csv([sample_component], csv_path)
        assert os.path.exists(res_path)

        with open(res_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        assert sample_component.value in content
        assert sample_component.name in content
        assert "Total_Quantity" in content
        assert "Part_Number" in content

        # Cleanup
        os.remove(csv_path)
        os.rmdir(temp_dir)
