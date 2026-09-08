import os
import re
from typing import List, Dict, Any, Optional, Tuple
import openpyxl
from excel_loader import clean_cell_value, normalize_string, ExcelDataLoader


class BOMItem:
    """Represents a single component line item from an Altium BOM export."""

    def __init__(
        self,
        row_idx: int,
        designator: str,
        comment: str,
        description: str,
        footprint: str,
        lib_ref: str,
        part_number: str,
        unit_qty: int,
        board_multiplier: int = 1
    ):
        self.row_idx = row_idx
        self.designator = designator
        self.comment = comment
        self.description = description
        self.footprint = footprint
        self.lib_ref = lib_ref
        self.part_number = part_number
        self.unit_qty = unit_qty
        self.board_multiplier = max(board_multiplier, 1)
        self.total_needed_qty = self.unit_qty * self.board_multiplier

        # Audit comparison fields
        self.matched_db_row: Optional[Tuple[int, List[str]]] = None
        self.db_part_name: str = ""
        self.db_stock_qty: int = 0
        self.shortage_qty: int = 0
        self.status: str = "NOT_IN_DB"  # "IN_STOCK", "SHORTAGE", "NOT_IN_DB"
        self.link: str = ""

    @property
    def link_type(self) -> str:
        """Returns 'LION', 'INVALID', or 'NONE'."""
        if not self.link or not self.link.strip():
            return "NONE"
        if "lionelectronic.ir" in self.link.lower():
            return "LION"
        return "INVALID"

    @property
    def link_domain(self) -> str:
        if not self.link or not self.link.strip():
            return ""
        try:
            from urllib.parse import urlparse
            p = urlparse(self.link)
            domain = p.netloc or self.link
            return domain.replace("www.", "")
        except Exception:
            return self.link

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_idx": self.row_idx,
            "designator": self.designator,
            "comment": self.comment,
            "description": self.description,
            "footprint": self.footprint,
            "part_number": self.part_number,
            "unit_qty": self.unit_qty,
            "total_needed": self.total_needed_qty,
            "in_stock": self.db_stock_qty,
            "shortage": self.shortage_qty,
            "status": self.status,
            "link": self.link,
            "link_type": self.link_type,
            "link_domain": self.link_domain,
            "db_part_name": self.db_part_name
        }


class BOMAuditResult:
    """Stores the complete analysis outcome of an Altium BOM audit against inventory."""

    def __init__(self, file_path: str, board_multiplier: int):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.board_multiplier = board_multiplier
        self.items: List[BOMItem] = []
        self.total_items_count: int = 0
        self.in_stock_count: int = 0
        self.shortage_count: int = 0
        self.not_in_db_count: int = 0

    @property
    def ready_for_assembly(self) -> bool:
        return self.shortage_count == 0 and self.not_in_db_count == 0

    def get_all_shortages(self) -> List[Dict[str, Any]]:
        """Return list of all shortage items with their procurement classification."""
        shortages = []
        for it in self.items:
            if it.status == "SHORTAGE" and it.shortage_qty > 0:
                shortages.append({
                    "designator": it.designator,
                    "part_name": it.db_part_name or it.part_number or it.comment,
                    "part_number": it.part_number,
                    "comment": it.comment,
                    "footprint": it.footprint,
                    "description": it.description,
                    "needed_qty": it.shortage_qty,
                    "current_stock": it.db_stock_qty,
                    "link": it.link,
                    "link_type": it.link_type,
                    "link_domain": it.link_domain,
                    "is_lion_orderable": it.link_type == "LION"
                })
        return shortages

    def get_orderable_shortages(self) -> List[Dict[str, Any]]:
        """Return list of shortage items that have valid Lion Electronic URLs."""
        return [s for s in self.get_all_shortages() if s["is_lion_orderable"]]

    def get_unsupported_shortages(self) -> List[Dict[str, Any]]:
        """Return list of shortage items with external or missing store links."""
        return [s for s in self.get_all_shortages() if not s["is_lion_orderable"]]


class BOMAuditor:
    """Parses Altium BOM spreadsheets and cross-references with the active inventory database."""

    @staticmethod
    def audit_bom(
        bom_file_path: str,
        inventory: ExcelDataLoader,
        board_multiplier: int = 1
    ) -> Tuple[bool, str, Optional[BOMAuditResult]]:
        """
        Parse Altium BOM Excel file, cross-match each row against inventory,
        and calculate stock sufficiency and shortages.
        """
        if not os.path.exists(bom_file_path):
            return False, f"BOM file not found: {bom_file_path}", None

        try:
            wb = openpyxl.load_workbook(bom_file_path, data_only=True)
            sheet = wb.active or wb[wb.sheetnames[0]]
            raw_rows = list(sheet.iter_rows(values_only=True))
            wb.close()

            if not raw_rows:
                return False, "BOM file is empty.", None

            # Locate columns in BOM header (Row 1)
            raw_headers = [str(h or "").strip() for h in raw_rows[0]]
            header_map = {normalize_string(h): idx for idx, h in enumerate(raw_headers)}

            def find_col(aliases: List[str]) -> Optional[int]:
                for alias in aliases:
                    norm = normalize_string(alias)
                    for h_norm, idx in header_map.items():
                        if norm == h_norm or norm in h_norm:
                            return idx
                return None

            comment_col = find_col(["comment", "کامنت"])
            desc_col = find_col(["description", "شرح"])
            designator_col = find_col(["designator", "محل قطعه"])
            footprint_col = find_col(["footprint", "پکیج", "فوت پرینت"])
            libref_col = find_col(["libref", "lib ref"])
            qty_col = find_col(["quantity", "qty", "تعداد"])
            part_num_col = find_col(["part number", "part_number", "part no"])

            result = BOMAuditResult(bom_file_path, board_multiplier)

            # Build fast lookup indexes from inventory database
            inv_part_name_col = inventory.get_column_index(["part name", "نام قطعه", "name"])
            inv_part_num_col = inventory.get_column_index(["part number", "part_number", "شماره فنی"])
            inv_desc_col = inventory.get_column_index(["discription", "description", "شرح"])
            inv_stock_col = inventory.get_column_index(["quantity in stock", "stock", "quantity", "موجودی"])
            inv_link_col = inventory.get_column_index(["link", "url", "لینک"])

            # Map normalized keys to inventory rows
            # Key 1: Part Name normalized
            # Key 2: Part Number normalized
            # Key 3: Description normalized
            exact_inv_map: Dict[str, Tuple[int, List[str]]] = {}

            for orig_row_idx, row_cells in inventory.rows:
                p_name = normalize_string(row_cells[inv_part_name_col]) if inv_part_name_col is not None and inv_part_name_col < len(row_cells) else ""
                p_num = normalize_string(row_cells[inv_part_num_col]) if inv_part_num_col is not None and inv_part_num_col < len(row_cells) else ""
                p_desc = normalize_string(row_cells[inv_desc_col]) if inv_desc_col is not None and inv_desc_col < len(row_cells) else ""

                if p_name and p_name not in exact_inv_map:
                    exact_inv_map[p_name] = (orig_row_idx, row_cells)
                if p_num and p_num not in exact_inv_map:
                    exact_inv_map[p_num] = (orig_row_idx, row_cells)
                if p_desc and p_desc not in exact_inv_map and len(p_desc) > 3:
                    exact_inv_map[p_desc] = (orig_row_idx, row_cells)

            # Parse BOM data rows
            for row_idx, r in enumerate(raw_rows[1:], start=2):
                if not r or all(c is None or str(c).strip() == "" for c in r):
                    continue

                def get_val(col_idx: Optional[int]) -> str:
                    if col_idx is not None and col_idx < len(r) and r[col_idx] is not None:
                        return str(r[col_idx]).strip()
                    return ""

                comment = get_val(comment_col)
                desc = get_val(desc_col)
                designator = get_val(designator_col)
                footprint = get_val(footprint_col)
                lib_ref = get_val(libref_col)
                part_num = get_val(part_num_col)
                qty_str = get_val(qty_col)

                try:
                    unit_qty = int(float(qty_str)) if qty_str else 1
                except ValueError:
                    unit_qty = 1

                bom_item = BOMItem(
                    row_idx=row_idx,
                    designator=designator,
                    comment=comment,
                    description=desc,
                    footprint=footprint,
                    lib_ref=lib_ref,
                    part_number=part_num,
                    unit_qty=unit_qty,
                    board_multiplier=board_multiplier
                )

                # Matching Strategy:
                # Step 1: Match BOM Part Number
                # Step 2: Match BOM Comment
                # Step 3: Match BOM Description / LibRef
                match_found = None

                norm_part_num = normalize_string(part_num)
                norm_comment = normalize_string(comment)
                norm_desc = normalize_string(desc)

                if norm_part_num and norm_part_num in exact_inv_map:
                    match_found = exact_inv_map[norm_part_num]
                elif norm_comment and norm_comment in exact_inv_map:
                    match_found = exact_inv_map[norm_comment]
                elif norm_desc and norm_desc in exact_inv_map:
                    match_found = exact_inv_map[norm_desc]
                else:
                    # Fuzzy / Substring fallback in inventory rows
                    for orig_idx, inv_cells in inventory.rows:
                        inv_name = normalize_string(inv_cells[inv_part_name_col]) if inv_part_name_col is not None and inv_part_name_col < len(inv_cells) else ""
                        inv_pn = normalize_string(inv_cells[inv_part_num_col]) if inv_part_num_col is not None and inv_part_num_col < len(inv_cells) else ""

                        if (norm_part_num and norm_part_num in inv_name) or (norm_part_num and norm_part_num in inv_pn):
                            match_found = (orig_idx, inv_cells)
                            break
                        if norm_comment and (norm_comment == inv_name or norm_comment == inv_pn):
                            match_found = (orig_idx, inv_cells)
                            break

                if match_found:
                    orig_idx, inv_cells = match_found
                    bom_item.matched_db_row = match_found
                    bom_item.db_part_name = inv_cells[inv_part_name_col] if inv_part_name_col is not None and inv_part_name_col < len(inv_cells) else ""
                    
                    stock_str = inv_cells[inv_stock_col] if inv_stock_col is not None and inv_stock_col < len(inv_cells) else "0"
                    try:
                        bom_item.db_stock_qty = int(float(stock_str)) if stock_str else 0
                    except ValueError:
                        bom_item.db_stock_qty = 0

                    bom_item.link = inv_cells[inv_link_col] if inv_link_col is not None and inv_link_col < len(inv_cells) else ""

                    if bom_item.db_stock_qty >= bom_item.total_needed_qty:
                        bom_item.status = "IN_STOCK"
                        bom_item.shortage_qty = 0
                        result.in_stock_count += 1
                    else:
                        bom_item.status = "SHORTAGE"
                        bom_item.shortage_qty = bom_item.total_needed_qty - bom_item.db_stock_qty
                        result.shortage_count += 1
                else:
                    bom_item.status = "NOT_IN_DB"
                    bom_item.db_stock_qty = 0
                    bom_item.shortage_qty = bom_item.total_needed_qty
                    result.not_in_db_count += 1

                result.items.append(bom_item)

            result.total_items_count = len(result.items)
            return True, f"Audited {result.total_items_count} components from BOM.", result

        except Exception as e:
            return False, f"Failed to audit BOM: {str(e)}", None
