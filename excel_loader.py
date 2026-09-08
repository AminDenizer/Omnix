import os
import re
from typing import List, Dict, Any, Tuple, Optional
import openpyxl


def clean_cell_value(val: Any) -> str:
    """Format an Excel cell value into a clean, normalized string."""
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.4f}".rstrip('0').rstrip('.')
    if isinstance(val, int):
        return str(val)
    return str(val).strip()


def normalize_string(text: str) -> str:
    """Normalize string for robust search and key matching."""
    if not text:
        return ""
    # Lowercase and strip whitespace
    s = text.lower().strip()
    # Normalize Persian / Arabic character variants
    s = s.replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', '')  # Remove ZWNJ
    # Normalize dashes and multiple spaces
    s = s.replace('–', '-').replace('—', '-')
    s = re.sub(r'\s+', ' ', s)
    return s


def find_local_excel_file(app_dir: str) -> Optional[str]:
    """Find the primary Excel database file strictly named Inventory.xlsx in the app directory."""
    if not app_dir or not os.path.exists(app_dir):
        return None
    try:
        # Strictly look for Inventory.xlsx / Inventory.xls (case-insensitive) only
        for inv_name in ["Inventory.xlsx", "inventory.xlsx", "INVENTORY.xlsx", "Inventory.xls", "inventory.xls"]:
            p = os.path.join(app_dir, inv_name)
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    return None


class ExcelDataLoader:
    """Handles parsing, search index, and two-way synchronization for Excel inventory databases."""

    def __init__(self):
        self.file_path: Optional[str] = None
        self.file_name: str = ""
        self.sheet_name: str = ""
        self.headers: List[str] = []
        self.rows: List[Tuple[int, List[str]]] = []  # List of (orig_excel_row_number, row_data)
        self._normalized_rows: List[Tuple[int, List[str], str]] = []  # (orig_row, row_data, searchable_str)
        self.col_index_map: Dict[str, int] = {}

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def total_columns(self) -> int:
        return len(self.headers)

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Load the first sheet from an Excel file, ensure Min Stock and Target Stock
        columns are appended to the end if missing (as part of the native Table),
        and build the in-memory search index.
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        try:
            # First pass: check and self-heal missing columns with native Table formatting
            self._ensure_stock_threshold_columns(file_path)

            wb = openpyxl.load_workbook(file_path, data_only=True)
            if not wb.sheetnames:
                return False, "Workbook contains no sheets."

            sheet = wb.active or wb[wb.sheetnames[0]]
            self.sheet_name = sheet.title
            self.file_path = file_path
            self.file_name = os.path.basename(file_path)

            # Read all rows
            raw_rows = list(sheet.iter_rows(values_only=True))
            if not raw_rows:
                self.headers = []
                self.rows = []
                self._normalized_rows = []
                return True, "Empty sheet."

            # Header row (Row 1)
            raw_headers = raw_rows[0]
            self.headers = [clean_cell_value(h) if h is not None else f"Column {i+1}" for i, h in enumerate(raw_headers)]
            
            # Map column names normalized to their index
            self.col_index_map = {normalize_string(h): idx for idx, h in enumerate(self.headers)}

            # Process data rows
            num_cols = len(self.headers)
            self.rows = []
            self._normalized_rows = []

            for row_idx, raw_row in enumerate(raw_rows[1:], start=2):
                if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                    continue  # Skip completely empty row

                row_cells = [clean_cell_value(raw_row[c]) if c < len(raw_row) else "" for c in range(num_cols)]
                searchable_str = " ".join(normalize_string(val) for val in row_cells)

                self.rows.append((row_idx, row_cells))
                self._normalized_rows.append((row_idx, row_cells, searchable_str))

            wb.close()
            return True, f"Loaded {len(self.rows)} records from '{self.sheet_name}'"

        except Exception as e:
            return False, f"Failed to load Excel file: {str(e)}"

    def _ensure_stock_threshold_columns(self, file_path: str):
        """
        Append 'Min Stock' and 'Target Stock' to the end of the Excel sheet if not present,
        and seamlessly extend native openpyxl Excel Table definitions with matching formatting.
        """
        try:
            from copy import copy
            from openpyxl.worksheet.table import TableColumn
            from openpyxl.utils import get_column_letter

            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active or wb[wb.sheetnames[0]]
            max_col = sheet.max_column
            max_row = sheet.max_row

            if max_row < 1:
                wb.close()
                return

            # Read existing header values
            existing_headers = [sheet.cell(row=1, column=c).value for c in range(1, max_col + 1)]
            normalized_headers = [normalize_string(str(h or "")) for h in existing_headers]

            has_min_stock = any("min stock" in h or "min_stock" in h or "حد کسر" in h for h in normalized_headers)
            has_target_stock = any("target stock" in h or "target_stock" in h or "تعداد سفارش" in h or "reorder" in h for h in normalized_headers)

            modified = False
            current_col = max_col

            # Reference styling from previous header and data cells
            ref_hdr = sheet.cell(row=1, column=max(max_col, 1))

            if not has_min_stock:
                current_col += 1
                cell_min = sheet.cell(row=1, column=current_col, value="Min Stock")
                if ref_hdr.font: cell_min.font = copy(ref_hdr.font)
                if ref_hdr.fill: cell_min.fill = copy(ref_hdr.fill)
                if ref_hdr.border: cell_min.border = copy(ref_hdr.border)
                if ref_hdr.alignment: cell_min.alignment = copy(ref_hdr.alignment)

                for r in range(2, max_row + 1):
                    if any(sheet.cell(row=r, column=c).value is not None for c in range(1, min(4, max_col + 1))):
                        d_cell = sheet.cell(row=r, column=current_col, value=0)
                        ref_d = sheet.cell(row=r, column=max(max_col, 1))
                        if ref_d.border: d_cell.border = copy(ref_d.border)
                        if ref_d.alignment: d_cell.alignment = copy(ref_d.alignment)
                modified = True

            if not has_target_stock:
                current_col += 1
                cell_tgt = sheet.cell(row=1, column=current_col, value="Target Stock")
                if ref_hdr.font: cell_tgt.font = copy(ref_hdr.font)
                if ref_hdr.fill: cell_tgt.fill = copy(ref_hdr.fill)
                if ref_hdr.border: cell_tgt.border = copy(ref_hdr.border)
                if ref_hdr.alignment: cell_tgt.alignment = copy(ref_hdr.alignment)

                for r in range(2, max_row + 1):
                    if any(sheet.cell(row=r, column=c).value is not None for c in range(1, min(4, max_col + 1))):
                        d_cell = sheet.cell(row=r, column=current_col, value=0)
                        ref_d = sheet.cell(row=r, column=max(max_col, 1))
                        if ref_d.border: d_cell.border = copy(ref_d.border)
                        if ref_d.alignment: d_cell.alignment = copy(ref_d.alignment)
                modified = True

            # Extend native openpyxl Table objects if present
            for table in sheet.tables.values():
                col_names = [c.name for c in table.tableColumns]
                if "Min Stock" not in col_names:
                    table.tableColumns.append(TableColumn(id=len(table.tableColumns) + 1, name="Min Stock"))
                if "Target Stock" not in col_names:
                    table.tableColumns.append(TableColumn(id=len(table.tableColumns) + 1, name="Target Stock"))

                # Expand range ref to current_col letter
                end_col_letter = get_column_letter(current_col)
                m = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", table.ref)
                if m:
                    start_col, start_row, _, end_row = m.groups()
                    table.ref = f"{start_col}{start_row}:{end_col_letter}{end_row}"
                    modified = True

            if modified:
                wb.save(file_path)
            wb.close()
        except Exception:
            pass

    def save_cell_value(self, orig_row_idx: int, col_idx: int, new_value: Any) -> bool:
        """
        Save an updated cell value directly back to the active Excel file on disk
        and update the in-memory cache immediately.
        """
        if not self.file_path or not os.path.exists(self.file_path):
            return False

        str_val = clean_cell_value(new_value)

        # 1. Update in-memory structures
        for i, (r_idx, row_data) in enumerate(self.rows):
            if r_idx == orig_row_idx:
                if col_idx < len(row_data):
                    row_data[col_idx] = str_val
                    # Update normalized search string
                    searchable_str = " ".join(normalize_string(val) for val in row_data)
                    self._normalized_rows[i] = (r_idx, row_data, searchable_str)
                break

        # 2. Persist to Excel file on disk
        try:
            wb = openpyxl.load_workbook(self.file_path)
            sheet = wb[self.sheet_name] if self.sheet_name in wb.sheetnames else wb.active
            
            # Convert to numeric if appropriate
            cell_val = str_val
            if str_val.isdigit():
                cell_val = int(str_val)
            elif str_val.replace('.', '', 1).isdigit() and str_val.count('.') < 2:
                cell_val = float(str_val)

            sheet.cell(row=orig_row_idx, column=col_idx + 1, value=cell_val)
            wb.save(self.file_path)
            wb.close()
            return True
        except Exception as e:
            print(f"Error saving cell to Excel: {e}")
            return False

    def batch_increment_stock(self, items_to_increment: List[Dict[str, Any]]) -> Tuple[int, str]:
        """
        Increment the 'Quantity in Stock' for the given items and persist directly to Excel.
        Each item dict can have:
          - 'orig_row_idx': direct row index if from Tab 1
          - 'part_name', 'part_number', 'comment', 'description': to lookup if from Tab 2 BOM
          - 'qty_ordered' or 'needed_qty' or 'shortage_qty': the quantity to add
        Returns: (success_count, message)
        """
        if not self.file_path or not os.path.exists(self.file_path):
            return 0, "Inventory database file not found on disk."

        stock_col = self.get_column_index(["quantity in stock", "stock", "quantity", "موجودی"])
        if stock_col is None:
            return 0, "Quantity in Stock column not found in Inventory.xlsx."

        part_name_col = self.get_column_index(["part name", "part_name", "نام قطعه", "name"])
        part_num_col = self.get_column_index(["part number", "part_number", "part no", "شماره فنی"])
        comment_col = self.get_column_index(["discription", "description", "شرح"])

        try:
            wb = openpyxl.load_workbook(self.file_path)
            sheet = wb[self.sheet_name] if self.sheet_name in wb.sheetnames else wb.active
            updated_count = 0

            for it in items_to_increment:
                if it.get("actual_ordered_qty") is not None:
                    qty_to_add = int(it.get("actual_ordered_qty"))
                elif it.get("qty_ordered") is not None:
                    qty_to_add = int(it.get("qty_ordered"))
                elif it.get("shortage_qty") is not None:
                    qty_to_add = int(it.get("shortage_qty"))
                else:
                    qty_to_add = int(it.get("needed_qty", 0))

                if qty_to_add <= 0:
                    continue

                target_row_idx = it.get("orig_row_idx")

                # If no direct row index (e.g. from BOM audit), find matching row in Excel
                if target_row_idx is None:
                    p_name = normalize_string(it.get("part_name") or "")
                    p_num = normalize_string(it.get("part_number") or "")
                    p_comm = normalize_string(it.get("comment") or "")

                    for r_idx, row_cells in self.rows:
                        r_name = normalize_string(row_cells[part_name_col]) if part_name_col is not None and part_name_col < len(row_cells) else ""
                        r_num = normalize_string(row_cells[part_num_col]) if part_num_col is not None and part_num_col < len(row_cells) else ""
                        r_comm = normalize_string(row_cells[comment_col]) if comment_col is not None and comment_col < len(row_cells) else ""

                        match = False
                        if p_num and (p_num == r_num or p_num == r_name):
                            match = True
                        elif p_name and (p_name == r_name or p_name == r_num):
                            match = True
                        elif p_comm and (p_comm == r_name or p_comm == r_num or p_comm == r_comm):
                            match = True

                        if match:
                            target_row_idx = r_idx
                            break

                if target_row_idx is not None:
                    # Update cell in memory
                    for i, (r_idx, row_cells) in enumerate(self.rows):
                        if r_idx == target_row_idx:
                            curr_stock_str = row_cells[stock_col] if stock_col < len(row_cells) else "0"
                            try:
                                curr_stk = int(float(curr_stock_str)) if curr_stock_str else 0
                            except ValueError:
                                curr_stk = 0
                            new_stk = curr_stk + qty_to_add
                            row_cells[stock_col] = str(new_stk)
                            searchable_str = " ".join(normalize_string(val) for val in row_cells)
                            self._normalized_rows[i] = (r_idx, row_cells, searchable_str)

                            # Update cell in Excel workbook
                            sheet.cell(row=target_row_idx, column=stock_col + 1, value=new_stk)
                            updated_count += 1
                            break

            if updated_count > 0:
                wb.save(self.file_path)
            wb.close()
            return updated_count, f"Successfully incremented stock for {updated_count} item(s) in Inventory.xlsx."

        except Exception as e:
            return 0, f"Error saving stock increments to Excel: {str(e)}"

    def get_column_index(self, possible_names: List[str]) -> Optional[int]:
        """Find the 0-indexed column index matching any of the candidate names."""
        for candidate in possible_names:
            norm = normalize_string(candidate)
            for h_norm, idx in self.col_index_map.items():
                if norm in h_norm or h_norm in norm:
                    return idx
        return None

    def get_shortage_items(self) -> List[Dict[str, Any]]:
        """
        Scan all inventory rows and identify items where current stock <= Min Stock
        (with Min Stock > 0 or when explicitly flagged).
        """
        stock_col = self.get_column_index(["quantity in stock", "stock", "quantity", "موجودی"])
        min_stock_col = self.get_column_index(["min stock", "min_stock", "حد کسر", "minimum"])
        target_stock_col = self.get_column_index(["target stock", "target_stock", "تعداد سفارش", "reorder"])
        part_name_col = self.get_column_index(["part name", "part_name", "نام قطعه", "name"])
        part_num_col = self.get_column_index(["part number", "part_number", "part no", "شماره فنی"])
        desc_col = self.get_column_index(["discription", "description", "شرح"])
        link_col = self.get_column_index(["link", "url", "لینک"])

        shortages = []

        for orig_row_idx, row_data in self.rows:
            stock_str = row_data[stock_col] if stock_col is not None and stock_col < len(row_data) else "0"
            min_stock_str = row_data[min_stock_col] if min_stock_col is not None and min_stock_col < len(row_data) else "0"
            target_stock_str = row_data[target_stock_col] if target_stock_col is not None and target_stock_col < len(row_data) else "0"

            try:
                curr_stock = float(stock_str) if stock_str else 0.0
            except ValueError:
                curr_stock = 0.0

            try:
                min_stock = float(min_stock_str) if min_stock_str else 0.0
            except ValueError:
                min_stock = 0.0

            try:
                target_stock = float(target_stock_str) if target_stock_str else 0.0
            except ValueError:
                target_stock = 0.0

            # Shortage condition: min_stock is configured (> 0) and current stock <= min_stock
            if min_stock > 0 and curr_stock <= min_stock:
                # Calculate needed quantity: difference up to target stock (or min stock if target stock not set)
                target = target_stock if target_stock > min_stock else min_stock
                needed_qty = max(int(target - curr_stock), int(min_stock - curr_stock), 1)

                part_name = row_data[part_name_col] if part_name_col is not None and part_name_col < len(row_data) else ""
                part_num = row_data[part_num_col] if part_num_col is not None and part_num_col < len(row_data) else ""
                desc = row_data[desc_col] if desc_col is not None and desc_col < len(row_data) else ""
                link = row_data[link_col] if link_col is not None and link_col < len(row_data) else ""

                link_type = "NONE"
                link_domain = ""
                if link and link.strip():
                    if "lionelectronic.ir" in link.lower():
                        link_type = "LION"
                    else:
                        link_type = "INVALID"
                        try:
                            from urllib.parse import urlparse
                            p = urlparse(link)
                            link_domain = (p.netloc or link).replace("www.", "")
                        except Exception:
                            link_domain = link

                shortages.append({
                    "orig_row_idx": orig_row_idx,
                    "part_name": part_name or part_num or f"Item Row {orig_row_idx}",
                    "part_number": part_num,
                    "description": desc,
                    "current_stock": int(curr_stock),
                    "min_stock": int(min_stock),
                    "target_stock": int(target_stock),
                    "needed_qty": needed_qty,
                    "link": link,
                    "link_type": link_type,
                    "link_domain": link_domain,
                    "is_lion_orderable": link_type == "LION"
                })

        return shortages

    def filter_rows(self, query: str) -> List[Tuple[int, List[str]]]:
        """High-speed multi-term live search across all columns."""
        if not query or not query.strip():
            return self.rows

        terms = [normalize_string(t) for t in query.split() if t.strip()]
        if not terms:
            return self.rows

        results = []
        for orig_idx, row_cells, searchable_str in self._normalized_rows:
            if all(term in searchable_str for term in terms):
                results.append((orig_idx, row_cells))

        return results

    def get_incomplete_records(self) -> List[Tuple[int, List[str], List[str]]]:
        """
        Scan all rows and identify records with missing/incomplete fields or question marks '?'.
        Returns list of (orig_row_idx, row_data, list_of_missing_field_names).
        """
        stock_col = self.get_column_index(["quantity in stock", "stock", "quantity", "موجودی"])
        part_name_col = self.get_column_index(["part name", "part_name", "نام قطعه", "name"])
        footprint_col = self.get_column_index(["footprint", "پکیج", "فوت پرینت"])
        link_col = self.get_column_index(["link", "url", "لینک"])

        incomplete_list = []
        for orig_row_idx, row_data in self.rows:
            reasons = []

            # Stock check
            stock_val = row_data[stock_col].strip() if stock_col is not None and stock_col < len(row_data) else ""
            if not stock_val or stock_val in ["?", "؟", "None", "nan"]:
                reasons.append("Missing Stock")

            # Part Name / Part Number check
            name_val = row_data[part_name_col].strip() if part_name_col is not None and part_name_col < len(row_data) else ""
            if not name_val or name_val in ["?", "؟", "None", "nan"]:
                reasons.append("Missing Part Name")

            # Footprint check
            if footprint_col is not None and footprint_col < len(row_data):
                fp_val = row_data[footprint_col].strip()
                if fp_val in ["?", "؟"]:
                    reasons.append("Unknown Footprint (?)")

            # Link check
            if link_col is not None and link_col < len(row_data):
                link_val = row_data[link_col].strip()
                if link_val in ["?", "؟"]:
                    reasons.append("Invalid Link (?)")

            if reasons:
                incomplete_list.append((orig_row_idx, row_data, reasons))

        return incomplete_list
