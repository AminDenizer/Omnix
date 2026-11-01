"""
Omnix Matrix Assembly & Component Label Engine
Generates transposed columnar component label worksheets with cut guides for assembly.
- Black and white friendly (no dark or colored fills that waste ink)
- Clear dashed cut borders with scissor guides (✂)
- Formats:
  1. Excel (.xlsx) matrix with column-per-component and dashed borders
  2. Printable Vector PDF / HTML with vertical cut strips organized in a 4-column printable grid
"""

import os
import html
import datetime
from typing import List, Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from PyQt6.QtCore import QSizeF
from PyQt6.QtGui import QFont, QTextDocument, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem
from ui.printing.assembly_print_engine import AssemblyPrintEngine


class MatrixLabelEngine:
    """Handles generation of transposed matrix label sheets and printable strips."""

    @classmethod
    def clean_project_name(cls, project_name: str) -> str:
        """Strips recognized file extensions (.xlsx, .xls, .csv) without truncating version numbers like V1.3."""
        if not project_name:
            return "UNTITLED_PROJECT"
        base = os.path.basename(project_name)
        lower = base.lower()
        for ext in (".xlsx", ".xls", ".csv", ".tsv"):
            if lower.endswith(ext):
                base = base[:-len(ext)]
                break
        return base or "UNTITLED_PROJECT"

    ROWS_SPEC = [
        ("Comment", lambda it: str(getattr(it, "comment", "") or "").strip()),
        ("Description", lambda it: str(getattr(it, "description", "") or "").strip()),
        ("Designator", lambda it: str(getattr(it, "designator", "") or "").strip()),
        ("Footprint", lambda it: str(getattr(it, "footprint", "") or "").strip()),
        ("LibRef", lambda it: str(getattr(it, "libref", "") or getattr(it, "lib_ref", "") or "").strip()),
        ("Quantity", lambda it: str(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))))),
    ]

    @classmethod
    def export_excel(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        output_filepath: str
    ) -> str:
        """
        Exports the BOM into an Excel file where each component is a column (N1..Nn),
        with dashed cut lines, bold headers, and high-contrast B&W print layout.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Matrix Labels"

        # Enable grid lines when printing
        ws.views.sheetView[0].showGridLines = True

        # Pure Black & White styles
        font_header_corner = Font(name="Segoe UI", size=11, bold=True, color="000000")
        font_marker = Font(name="Segoe UI", size=10, bold=True, color="000000")
        font_row_header = Font(name="Segoe UI", size=10, bold=True, color="000000")
        font_data = Font(name="Segoe UI", size=9, color="000000")

        # Dashed border for scissor cutting guide between columns and cells
        dashed_side = Side(border_style="dashed", color="000000")
        solid_side = Side(border_style="thin", color="000000")
        cut_border = Border(left=dashed_side, right=dashed_side, top=dashed_side, bottom=dashed_side)
        label_border = Border(left=solid_side, right=solid_side, top=solid_side, bottom=solid_side)

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # 1. Row 1: Header (Corner Project Name, then Project_N1, Project_N2...)
        clean_project = cls.clean_project_name(project_name)
        cell_corner = ws.cell(row=1, column=1, value=clean_project)
        cell_corner.font = font_header_corner
        cell_corner.alignment = align_left
        cell_corner.border = label_border

        for col_idx, item in enumerate(bom_items, start=2):
            marker = f"{clean_project}_N{col_idx - 1}"
            cell = ws.cell(row=1, column=col_idx, value=marker)
            cell.font = font_marker
            cell.alignment = align_center
            cell.border = cut_border

        # 2. Rows 2-7: Properties transposed
        for row_idx, (prop_name, extractor) in enumerate(cls.ROWS_SPEC, start=2):
            header_cell = ws.cell(row=row_idx, column=1, value=prop_name)
            header_cell.font = font_row_header
            header_cell.alignment = align_left
            header_cell.border = label_border

            for col_idx, item in enumerate(bom_items, start=2):
                val = extractor(item)
                val_cell = ws.cell(row=row_idx, column=col_idx, value=val)
                val_cell.font = font_data
                val_cell.alignment = align_center if prop_name in ("Comment", "Quantity") else align_left
                val_cell.border = cut_border

        # Auto-adjust column widths
        ws.column_dimensions["A"].width = 16
        for col_idx in range(2, len(bom_items) + 2):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 24

        # Page setup: Landscape, fit to page
        ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
        ws.page_setup.paperSize = ws.PAPERSIZE_A4

        output_filepath = os.path.abspath(output_filepath)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        wb.save(output_filepath)
        return output_filepath

    @classmethod
    def generate_cut_strip_html(
        cls,
        bom_items: List[BOMItem],
        project_name: str
    ) -> str:
        """
        Generates high-contrast black-and-white printable HTML with 4-column scissor cut grids.
        Each component forms a dedicated vertical box with dashed cut borders.
        """
        clean_project = cls.clean_project_name(project_name)

        html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4 landscape;
        margin: 6mm;
    }}
    body {{
        font-family: 'Segoe UI', Arial, sans-serif;
        color: #000000;
        background: #ffffff;
        margin: 0;
        padding: 4px;
    }}
    .header {{
        border-bottom: 2px solid #000000;
        padding-bottom: 4px;
        margin-bottom: 8px;
    }}
    .header h2 {{
        margin: 0;
        font-size: 14pt;
        display: inline-block;
    }}
    .header span {{
        float: right;
        font-size: 9pt;
        color: #333333;
    }}
    table.label-grid {{
        border-collapse: separate;
        border-spacing: 10px;
        width: 100%;
    }}
    td.label-box {{
        border: 2px dashed #000000;
        padding: 8px 10px;
        vertical-align: top;
        width: 25%;
        background-color: #ffffff;
    }}
    .cut-line {{
        font-size: 8pt;
        color: #444444;
        text-align: center;
        border-bottom: 1px dotted #888888;
        padding-bottom: 2px;
        margin-bottom: 5px;
    }}
    .marker-title {{
        font-size: 11pt;
        font-weight: bold;
        text-align: center;
        border-bottom: 1.5px solid #000000;
        padding-bottom: 3px;
        margin-bottom: 5px;
    }}
    .row-text {{
        font-size: 8.5pt;
        margin-bottom: 3px;
        line-height: 1.25;
    }}
    .bold-lbl {{
        font-weight: bold;
    }}
    .qty-tag {{
        border: 1.5px solid #000000;
        padding: 1px 5px;
        font-weight: bold;
        display: inline-block;
    }}
</style>
</head>
<body>
    <div class="header">
        <h2>{html.escape(clean_project)} — Component Assembly & Cut Labels</h2>
        <span>Total Items: {len(bom_items)} | Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
    </div>
    <table class="label-grid">
"""
        # Split into rows of 4 columns per row
        for i in range(0, len(bom_items), 4):
            html_out += "        <tr>\n"
            chunk = bom_items[i:i + 4]
            for j, item in enumerate(chunk):
                item_idx = i + j + 1
                marker = f"{clean_project}_N{item_idx}"
                comment = html.escape(str(getattr(item, "comment", "") or "-"))
                desc = html.escape(str(getattr(item, "description", "") or "-"))
                desig = html.escape(str(getattr(item, "designator", "") or "-"))
                fp = html.escape(str(getattr(item, "footprint", "") or "-"))
                libref = html.escape(str(getattr(item, "libref", "") or getattr(item, "lib_ref", "") or "-"))
                qty = max(1, getattr(item, "total_needed_qty", getattr(item, "unit_qty", 1)))

                html_out += f"""            <td class="label-box">
                <div class="cut-line">✂ - - - - - - - - - - - - ✂</div>
                <div class="marker-title">{html.escape(marker)}</div>
                <div class="row-text"><span class="bold-lbl">Comment:</span> {comment}</div>
                <div class="row-text"><span class="bold-lbl">Qty:</span> <span class="qty-tag">{qty} pcs</span></div>
                <div class="row-text"><span class="bold-lbl">Footprint:</span> {fp}</div>
                <div class="row-text"><span class="bold-lbl">Designators:</span> {desig}</div>
                <div class="row-text"><span class="bold-lbl">Description:</span> {desc}</div>
                <div class="row-text"><span class="bold-lbl">LibRef:</span> {libref}</div>
            </td>
"""
            # Fill empty cells if last row has less than 4 items
            for _ in range(4 - len(chunk)):
                html_out += "            <td style='border: none; width: 25%;'></td>\n"
            html_out += "        </tr>\n"

        html_out += """    </table>
</body>
</html>
"""
        return html_out

    @classmethod
    def export_pdf(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        output_filepath: str
    ) -> str:
        """Exports the printable cut-strip labels to vector PDF."""
        output_filepath = os.path.abspath(output_filepath)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(output_filepath)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)

        html_doc = cls.generate_cut_strip_html(bom_items, project_name)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 9))
        rect_points = printer.pageLayout().paintRectPoints()
        doc.setPageSize(QSizeF(rect_points.width(), rect_points.height()))
        doc.setHtml(html_doc)
        doc.print(printer)
        return output_filepath
