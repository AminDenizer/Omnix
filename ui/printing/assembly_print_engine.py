import os
import html
import math
import datetime
from typing import List, Optional, Tuple
from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QFont, QTextDocument, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem


class AssemblyPrintEngine:
    """
    Unified canonical rendering and document engine for Altium BOM Assembly Worksheets.
    Target: A4 Landscape (297 x 210 mm), 8 mm margins.
    Drives:
    - Assembly Preview (QPrintPreviewWidget / AssemblyPreviewDialog)
    - Vector PDF Export (QPrinter in PDF format)
    """

    PAGE_SIZE_ID = QPageSize.PageSizeId.A4
    PAGE_ORIENTATION = QPageLayout.Orientation.Landscape
    MARGIN_MM = 8.0

    @staticmethod
    def extract_project_name(filename_or_path: str) -> str:
        """
        Derives authoritative project name from the uploaded BOM filename stem.
        Rule: Original filename without file extension.
        Example: 'FC_IO_V1.3.xlsx' -> 'FC_IO_V1.3'
        """
        if not filename_or_path:
            return "UNTITLED_PROJECT"
        base = os.path.basename(filename_or_path)
        stem, _ = os.path.splitext(base)
        return stem or "UNTITLED_PROJECT"

    @classmethod
    def get_default_pdf_filename(cls, project_name: str, page_size_id: Optional[QPageSize.PageSizeId] = None) -> str:
        """Returns the canonical default filename for Assembly PDF export in A4 Landscape (or A5)."""
        safe_name = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", ".")).strip()
        if not safe_name:
            safe_name = "Assembly_Project"
        size_suffix = "A5" if page_size_id == QPageSize.PageSizeId.A5 else "A4"
        return f"{safe_name}_Assembly_Worksheet_{size_suffix}.pdf"

    @classmethod
    def recommend_paper_size(cls, bom_items: List[BOMItem]) -> QPageSize.PageSizeId:
        """
        Returns A4 Landscape as the sole authoritative paper size for Assembly Worksheets.
        """
        return QPageSize.PageSizeId.A4

    @classmethod
    def calculate_row_height(cls, item: BOMItem, is_a4: bool = True) -> float:
        """Calculates expected rendered row height in points for accurate pagination."""
        desig = str(item.designator or "").strip()
        desc = str(item.description or "").strip()
        comment = str(item.comment or "").strip()

        chars_desc = 38 if is_a4 else 26
        chars_desig = 34 if is_a4 else 22
        chars_comment = 16 if is_a4 else 12

        lines_desc = max(1, math.ceil(len(desc) / chars_desc))
        lines_desig = max(1, math.ceil(len(desig) / chars_desig))
        lines_comment = max(1, math.ceil(len(comment) / chars_comment))

        max_lines = max(lines_desc, lines_desig, lines_comment)
        line_h = 12.0
        return 10.0 + (max_lines * line_h)

    @classmethod
    def chunk_items_for_pages(cls, bom_items: List[BOMItem], is_a4: bool = True) -> List[List[Tuple[int, BOMItem]]]:
        """
        Segments BOM items into distinct pages so rows are never split across page boundaries.
        Page 1 accounts for the large top header card; continuation pages use a compact subheader.
        """
        p1_limit = 360.0 if is_a4 else 240.0
        other_limit = 360.0 if is_a4 else 240.0

        pages = []
        curr_page = []
        curr_h = 0.0
        limit = p1_limit

        for idx, it in enumerate(bom_items, start=1):
            h = cls.calculate_row_height(it, is_a4=is_a4)
            if curr_h + h > limit and curr_page:
                pages.append(curr_page)
                curr_page = [(idx, it)]
                curr_h = h
                limit = other_limit
            else:
                curr_page.append((idx, it))
                curr_h += h

        if curr_page:
            pages.append(curr_page)
        return pages

    @classmethod
    def generate_html(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        page_size_id: QPageSize.PageSizeId = QPageSize.PageSizeId.A4
    ) -> str:
        """
        Generates canonical multi-page paginated HTML representation of the Assembly Worksheet
        conforming to the 8-column contract:
        | NO | Comment | Description | Designator | Footprint | Qty | Part Number | Package |
        Rows are segmented into page blocks with repeated column headers and complete borders on all cells.
        """
        esc_project_name = html.escape(project_name)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        total_items_count = len(bom_items)
        computed_total_qty = total_qty if total_qty is not None else sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in bom_items)

        is_a4 = (page_size_id != QPageSize.PageSizeId.A5)
        css_page_size = "A4 landscape" if is_a4 else "A5 landscape"
        css_page_margin = "8mm" if is_a4 else "6mm"
        css_body_font_size = "8pt" if is_a4 else "7.5pt"

        col_widths = {
            "no": "4.5%", "comment": "10%", "desc": "24%", "desig": "24%",
            "footprint": "11%", "qty": "5%", "mpn": "13%", "pkg": "8.5%"
        }

        pages = cls.chunk_items_for_pages(bom_items, is_a4=is_a4)
        total_pages = len(pages) if pages else 1

        html_parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{esc_project_name} - Assembly Worksheet</title>
    <style>
        @page {{
            size: {css_page_size};
            margin: {css_page_margin};
        }}
        body {{
            font-family: "Segoe UI", "Tahoma", "Vazirmatn", "Arial", sans-serif;
            font-size: {css_body_font_size};
            color: #1e293b;
            margin: 0;
            padding: 0;
            background-color: #ffffff;
            -webkit-print-color-adjust: exact;
        }}
        .page-break {{
            page-break-before: always;
        }}
        .header-card {{
            border-bottom: 2px solid #0284c7;
            padding-bottom: 6px;
            margin-bottom: 14px;
        }}
        .header-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .header-title {{
            font-size: 11pt;
            font-weight: bold;
            color: #0f172a;
            margin: 0;
        }}
        .header-sub {{
            font-size: 7.5pt;
            color: #64748b;
            margin-top: 1px;
        }}
        .header-meta {{
            text-align: right;
            font-size: 7pt;
            color: #475569;
        }}
        .badge {{
            display: inline-block;
            background-color: #e0f2fe;
            color: #0369a1;
            font-weight: bold;
            padding: 1px 6px;
            border-radius: 4px;
            border: 1px solid #bae6fd;
        }}
        .continuation-card {{
            border-bottom: 1.5px solid #0284c7;
            padding-bottom: 5px;
            margin-bottom: 12px;
        }}
        table.assembly-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            border: 1px solid #475569;
        }}
        table.assembly-table th {{
            background-color: #0f172a;
            color: #ffffff;
            font-size: 7.5pt;
            font-weight: bold;
            padding: 5px 4px;
            border: 1px solid #475569;
            text-align: left;
            white-space: nowrap;
        }}
        table.assembly-table th.col-no-header {{
            background-color: #0369a1;
            color: #ffffff;
            text-align: center;
            font-family: monospace;
            font-size: 7.5pt;
            white-space: nowrap;
            border: 1px solid #0284c7;
        }}
        table.assembly-table td {{
            padding: 4px 5px;
            border: 1px solid #94a3b8;
            font-size: {css_body_font_size};
            vertical-align: middle;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        tr.even-row td {{
            background-color: #ffffff;
            border: 1px solid #94a3b8;
        }}
        tr.odd-row td {{
            background-color: #f8fafc;
            border: 1px solid #94a3b8;
        }}
        .footer {{
            font-size: 6.5pt;
            color: #94a3b8;
            text-align: right;
            margin-top: 6px;
            border-top: 1px solid #e2e8f0;
            padding-top: 3px;
        }}
    </style>
</head>
<body>
"""]

        if not pages:
            pages = [[]]

        for page_idx, page_rows in enumerate(pages, start=1):
            is_first = (page_idx == 1)
            break_class = "" if is_first else ' class="page-break"'
            html_parts.append(f'<div{break_class}>')

            if is_first:
                html_parts.append(f"""
                <div class="header-card">
                    <table class="header-table">
                        <tr>
                            <td style="width: 60%; vertical-align: top;">
                                <div class="header-title">🔧 ALTIUM BOM ASSEMBLY WORKSHEET</div>
                                <div class="header-sub">Project: <span class="badge">{esc_project_name}</span> &nbsp;|&nbsp; Physical Component Preparation Sheet</div>
                            </td>
                            <td style="width: 40%; vertical-align: top; text-align: right;" class="header-meta">
                                <div><b>Date:</b> {now_str}</div>
                                <div><b>Line Items:</b> {total_items_count} &nbsp;|&nbsp; <b>Total Components:</b> {computed_total_qty} pcs</div>
                                <div><b>Page:</b> {page_idx} of {total_pages}</div>
                            </td>
                        </tr>
                    </table>
                </div>
                """)
            else:
                html_parts.append(f"""
                <div class="continuation-card">
                    <table class="header-table">
                        <tr>
                            <td style="width: 70%; vertical-align: middle;">
                                <div style="font-size: 8.5pt; font-weight: bold; color: #0f172a;">
                                    🔧 ALTIUM BOM ASSEMBLY WORKSHEET &nbsp;&bull;&nbsp; Project: <span class="badge">{esc_project_name}</span> (Continuation)
                                </div>
                            </td>
                            <td style="width: 30%; vertical-align: middle; text-align: right;" class="header-meta">
                                <div><b>Page:</b> {page_idx} of {total_pages}</div>
                            </td>
                        </tr>
                    </table>
                </div>
                """)

            html_parts.append("""
            <table class="assembly-table">
                <thead>
                    <tr>
                        <th class="col-no-header" style="width: {no}; text-align: center;">NO</th>
                        <th style="width: {comment};">Comment</th>
                        <th style="width: {desc};">Description</th>
                        <th style="width: {desig};">Designator</th>
                        <th style="width: {footprint}; text-align: center;">Footprint</th>
                        <th style="width: {qty}; text-align: center;">Qty</th>
                        <th style="width: {mpn};">Part Number</th>
                        <th style="width: {pkg}; text-align: center;">Package</th>
                    </tr>
                </thead>
                <tbody>
            """.format(**col_widths))

            for row_num, item in page_rows:
                n_marker = f"N{row_num}"
                comment = html.escape(str(item.comment or "").strip())
                description = html.escape(str(item.description or "").strip())
                designator = html.escape(str(item.designator or "").strip())
                footprint = html.escape(str(item.footprint or "").strip())
                qty = str(getattr(item, "total_needed_qty", getattr(item, "unit_qty", 1)))
                part_number = html.escape(str(item.part_number or "").strip())
                package = html.escape(str(item.package or item.footprint or "").strip())

                row_class = "even-row" if row_num % 2 == 0 else "odd-row"
                html_parts.append(f"""
                    <tr class="{row_class}">
                        <td style="text-align: center; font-weight: bold; font-family: monospace; color: #0284c7;">{n_marker}</td>
                        <td dir="auto">{comment}</td>
                        <td dir="auto">{description}</td>
                        <td dir="ltr" style="font-family: monospace; font-size: 7.5pt;">{designator}</td>
                        <td dir="ltr" style="text-align: center; font-family: monospace; font-size: 7.5pt;">{footprint}</td>
                        <td style="text-align: center; font-weight: bold;">{qty}</td>
                        <td dir="ltr" style="font-weight: bold; font-family: monospace; color: #0f172a; font-size: 7.5pt;">{part_number}</td>
                        <td dir="ltr" style="text-align: center; font-family: monospace; font-size: 7.5pt;">{package}</td>
                    </tr>
                """)

            html_parts.append("""
                </tbody>
            </table>
            """)

            html_parts.append(f"""
            <div class="footer">
                Omnix Electronic Components & Altium BOM Assembly System &bull; Physical Worksheet &bull; Page {page_idx} of {total_pages}
            </div>
            </div>
            """)

        html_parts.append("</body></html>")
        return "\n".join(html_parts)

    @classmethod
    def setup_printer(
        cls,
        printer: QPrinter,
        page_size_id: QPageSize.PageSizeId = QPageSize.PageSizeId.A4,
        output_filepath: Optional[str] = None
    ) -> None:
        """Configures a QPrinter instance for Landscape (standard A4 with 8mm margins, or A5 with 6mm margins)."""
        margins = cls.MARGIN_MM if page_size_id != QPageSize.PageSizeId.A5 else 6.0
        printer.setPageSize(QPageSize(page_size_id))
        printer.setPageOrientation(cls.PAGE_ORIENTATION)
        printer.setPageMargins(QMarginsF(margins, margins, margins, margins), QPageLayout.Unit.Millimeter)
        if output_filepath:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(output_filepath)

    @classmethod
    def setup_a5_printer(cls, printer: QPrinter, output_filepath: Optional[str] = None) -> None:
        """Legacy helper for backward compatibility; configures A5 Landscape."""
        cls.setup_printer(printer, QPageSize.PageSizeId.A5, output_filepath=output_filepath)

    @classmethod
    def render_to_printer(
        cls,
        printer: QPrinter,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        page_size_id: Optional[QPageSize.PageSizeId] = None
    ) -> QTextDocument:
        """Renders the canonical HTML to any pre-configured QPrinter (Physical, Preview, or PDF)."""
        if printer.pageLayout().orientation() != cls.PAGE_ORIENTATION:
            printer.setPageOrientation(cls.PAGE_ORIENTATION)

        html_doc = cls.generate_html(bom_items, project_name, total_qty, page_size_id=QPageSize.PageSizeId.A4)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 8))

        # Core Geometry Fix: Set document layout size in device-independent points
        # to ensure perfect physical scaling across preview, PDF export, and physical printers.
        rect_points = printer.pageLayout().paintRectPoints()
        doc.setPageSize(QSizeF(rect_points.width(), rect_points.height()))
        doc.setHtml(html_doc)
        doc.print(printer)
        return doc

    @classmethod
    def export_pdf(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        output_filepath: Optional[str] = None,
        page_size_id: Optional[QPageSize.PageSizeId] = None
    ) -> str:
        """
        Exports the canonical Assembly Worksheet to a vector PDF strictly in A4 Landscape.
        Returns the absolute filepath of the generated PDF.
        """
        page_size_id = QPageSize.PageSizeId.A4

        if not output_filepath:
            output_filepath = cls.get_default_pdf_filename(project_name, page_size_id=page_size_id)

        output_filepath = os.path.abspath(output_filepath)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        cls.setup_printer(printer, page_size_id=page_size_id, output_filepath=output_filepath)
        cls.render_to_printer(printer, bom_items, project_name, total_qty, page_size_id=page_size_id)

        return output_filepath
