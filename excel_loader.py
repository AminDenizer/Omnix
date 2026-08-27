import os
import re
from typing import List, Dict, Any, Optional, Tuple

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


def normalize_search_text(text: str) -> str:
    """Normalize text for case-insensitive resilient searching."""
    if not text:
        return ""
    text = str(text).lower()
    # Normalize Arabic/Persian letters in case dataset contains Persian text
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("ئ", "ی").replace("ء", "")
    text = text.replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_cell_value(val: Any) -> str:
    """Format any Excel cell value into clean readable text."""
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.4g}"
    if isinstance(val, bool):
        return "True" if val else "False"
    return str(val).strip()


def find_local_excel_file(app_dir: str) -> Optional[str]:
    """Find the first valid Excel database file (.xlsx / .xlsm / .xls) strictly in the app directory."""
    if not app_dir or not os.path.exists(app_dir):
        return None
    try:
        entries = sorted(os.listdir(app_dir))
        for fname in entries:
            if fname.startswith("~$") or fname.startswith("."):
                continue
            if fname.lower().endswith((".xlsx", ".xlsm", ".xls")):
                full_path = os.path.join(app_dir, fname)
                if os.path.isfile(full_path):
                    return full_path
    except Exception:
        pass
    return None


class ExcelDataLoader:
    """Handles parsing and in-memory management of the Excel database."""

    def __init__(self):
        self.file_path: Optional[str] = None
        self.file_name: str = ""
        self.sheet_name: str = ""
        self.headers: List[str] = []
        self.rows: List[List[str]] = []
        self._normalized_rows: List[str] = []

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """Load and parse the first sheet of an Excel workbook."""
        if not file_path or not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        if not OPENPYXL_AVAILABLE:
            return False, "openpyxl library is not installed. Please install it via pip install openpyxl."

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            sheet_names = wb.sheetnames
            if not sheet_names:
                return False, "Excel workbook contains no sheets."

            # Always load the first sheet as requested
            target_sheet = sheet_names[0]
            self.sheet_name = target_sheet
            ws = wb[target_sheet]

            raw_rows = list(ws.iter_rows(values_only=True))
            wb.close()

            if not raw_rows:
                self.headers = []
                self.rows = []
                self._normalized_rows = []
                self.file_path = file_path
                self.file_name = os.path.basename(file_path)
                return True, "Worksheet is empty."

            # Header row (Row 1)
            raw_headers = raw_rows[0]
            col_count = 0
            for idx, h in enumerate(raw_headers):
                if h is not None and str(h).strip() != "":
                    col_count = idx + 1
            if col_count == 0:
                col_count = len(raw_headers)

            self.headers = []
            for i in range(col_count):
                h = raw_headers[i] if i < len(raw_headers) else None
                h_str = str(h).strip() if h is not None else f"Column {i+1}"
                if not h_str:
                    h_str = f"Column {i+1}"
                self.headers.append(h_str)

            # Data rows (Row 2 onwards)
            self.rows = []
            self._normalized_rows = []

            for row_tuple in raw_rows[1:]:
                if not row_tuple or all(v is None or str(v).strip() == "" for v in row_tuple):
                    continue

                formatted_row = []
                for i in range(len(self.headers)):
                    val = row_tuple[i] if i < len(row_tuple) else None
                    formatted_row.append(format_cell_value(val))

                self.rows.append(formatted_row)
                self._normalized_rows.append(normalize_search_text(" ".join(formatted_row)))

            self.file_path = file_path
            self.file_name = os.path.basename(file_path)
            return True, "Database successfully loaded."

        except Exception as e:
            return False, f"Error reading Excel file: {str(e)}"

    def filter_rows(self, query: str) -> List[Tuple[int, List[str]]]:
        """
        Filter rows matching all keywords in query.
        Returns list of tuples: (original_index, row_data)
        """
        if not self.rows:
            return []

        norm_query = normalize_search_text(query)
        if not norm_query:
            return list(enumerate(self.rows))

        terms = norm_query.split(" ")
        results = []

        for idx, norm_row_str in enumerate(self._normalized_rows):
            if all(term in norm_row_str for term in terms):
                results.append((idx, self.rows[idx]))

        return results

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def total_columns(self) -> int:
        return len(self.headers)
