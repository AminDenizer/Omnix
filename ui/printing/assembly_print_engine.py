import os
import html
import datetime
from typing import List, Optional
from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QFont, QTextDocument, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem


class AssemblyPrintEngine:
    """
    Unified canonical rendering and print engine for Altium BOM Assembly Worksheets.
    Target: A5 Landscape (210 x 148 mm), 6 mm margins.
    Drives:
    - Print Preview (QPrintPreviewDialog)
    - Physical Print (QPrintDialog / QPrinter)
    - Vector PDF Export (QPrinter in PDF format)
    """

    PAGE_SIZE_ID = QPageSize.PageSizeId.A5
    PAGE_ORIENTATION = QPageLayout.Orientation.Landscape
    MARGIN_MM = 6.0

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
    def get_default_pdf_filename(cls, project_name: str, page_size_id: QPageSize.PageSizeId = QPageSize.PageSizeId.A5) -> str:
        """Returns the canonical default filename for Assembly PDF export."""
        safe_name = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", ".")).strip()
        if not safe_name:
            safe_name = "Assembly_Project"
        suffix = "A4" if page_size_id == QPageSize.PageSizeId.A4 else "A5"
        return f"{safe_name}_Assembly_Worksheet_{suffix}.pdf"

    @classmethod
    def recommend_paper_size(cls, bom_items: List[BOMItem]) -> QPageSize.PageSizeId:
        """
        Recommends A5 Landscape when readable, or falls back to A4 Landscape
        when long designators or descriptions exceed A5 readability thresholds.
        """
        for item in bom_items:
            desig_len = len(str(item.designator or ""))
            desc_len = len(str(item.description or ""))
            if desig_len > 180 or desc_len > 140:
                return QPageSize.PageSizeId.A4
        return QPageSize.PageSizeId.A5

    @classmethod
    def generate_html(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        page_size_id: QPageSize.PageSizeId = QPageSize.PageSizeId.A5
    ) -> str:
        """
        Generates canonical HTML representation of the Assembly Worksheet conforming to the 9-column contract:
        | <PROJECT_NAME> | Comment | Description | Designator | Footprint | LibRef | Quantity | Part Number | Package |
        """
        esc_project_name = html.escape(project_name)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        total_items_count = len(bom_items)
        computed_total_qty = total_qty if total_qty is not None else sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in bom_items)

        is_a4 = (page_size_id == QPageSize.PageSizeId.A4)
        css_page_size = "A4 landscape" if is_a4 else "A5 landscape"
        css_page_margin = "8mm" if is_a4 else "6mm"
        css_body_font_size = "8pt" if is_a4 else "7.5pt"

        # Build table rows with N1...Nn numbering
        table_rows_html = []
        for idx, item in enumerate(bom_items, start=1):
            n_marker = f"N{idx}"
            comment = html.escape(str(item.comment or "").strip())
            description = html.escape(str(item.description or "").strip())
            designator = html.escape(str(item.designator or "").strip())
            footprint = html.escape(str(item.footprint or "").strip())
            lib_ref = html.escape(str(item.lib_ref or "").strip())
            qty = str(getattr(item, "total_needed_qty", getattr(item, "unit_qty", 1)))
            part_number = html.escape(str(item.part_number or "").strip())
            package = html.escape(str(item.package or item.footprint or "").strip())

            row_class = "even-row" if idx % 2 == 0 else "odd-row"
            table_rows_html.append(f"""
            <tr class="{row_class}">
                <td class="col-n" style="text-align: center; font-weight: bold; font-family: monospace; color: #0284c7;">{n_marker}</td>
                <td class="col-comment" dir="auto">{comment}</td>
                <td class="col-desc" dir="auto">{description}</td>
                <td class="col-desig" dir="ltr" style="font-family: monospace;">{designator}</td>
                <td class="col-footprint" dir="ltr" style="text-align: center; font-family: monospace;">{footprint}</td>
                <td class="col-libref" dir="auto">{lib_ref}</td>
                <td class="col-qty" style="text-align: center; font-weight: bold;">{qty}</td>
                <td class="col-mpn" dir="ltr" style="font-weight: bold; font-family: monospace; color: #0f172a;">{part_number}</td>
                <td class="col-pkg" dir="ltr" style="text-align: center; font-family: monospace;">{package}</td>
            </tr>
            """)

        rows_content = "\n".join(table_rows_html)

        html_template = f"""<!DOCTYPE html>
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
        .header-card {{
            border-bottom: 2px solid #0284c7;
            padding-bottom: 4px;
            margin-bottom: 6px;
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
        table.assembly-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }}
        table.assembly-table thead {{
            display: table-header-group;
        }}
        table.assembly-table tr {{
            page-break-inside: avoid;
        }}
        table.assembly-table th {{
            background-color: #0f172a;
            color: #ffffff;
            font-size: 7pt;
            font-weight: bold;
            padding: 4px 3px;
            border: 1px solid #0f172a;
            text-align: left;
            white-space: nowrap;
        }}
        table.assembly-table th.col-project-header {{
            background-color: #0369a1;
            color: #ffffff;
            text-align: center;
            font-family: monospace;
            font-size: 7.5pt;
            white-space: nowrap;
        }}
        table.assembly-table td {{
            padding: 3px 3px;
            border: 1px solid #cbd5e1;
            font-size: 7pt;
            vertical-align: middle;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .odd-row {{
            background-color: #ffffff;
        }}
        .even-row {{
            background-color: #f8fafc;
        }}
        .col-n {{ width: 8%; }}
        .col-comment {{ width: 9.5%; }}
        .col-desc {{ width: 21%; }}
        .col-desig {{ width: 17%; }}
        .col-footprint {{ width: 10%; }}
        .col-libref {{ width: 9%; }}
        .col-qty {{ width: 6.5%; }}
        .col-mpn {{ width: 12.5%; }}
        .col-pkg {{ width: 6.5%; }}
        .footer {{
            margin-top: 6px;
            padding-top: 3px;
            border-top: 1px solid #e2e8f0;
            font-size: 6.5pt;
            color: #94a3b8;
            text-align: center;
        }}
    </style>
</head>
<body>
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
                </td>
            </tr>
        </table>
    </div>

    <table class="assembly-table">
        <thead>
            <tr>
                <th class="col-n col-project-header">{esc_project_name}</th>
                <th class="col-comment">Comment</th>
                <th class="col-desc">Description</th>
                <th class="col-desig">Designator</th>
                <th class="col-footprint" style="text-align: center;">Footprint</th>
                <th class="col-libref">LibRef</th>
                <th class="col-qty" style="text-align: center;">Qty</th>
                <th class="col-mpn">Part Number</th>
                <th class="col-pkg" style="text-align: center;">Package</th>
            </tr>
        </thead>
        <tbody>
            {rows_content}
        </tbody>
    </table>

    <div class="footer">
        Omnix Electronic Components & Altium BOM Assembly System &bull; Physical Worksheet
    </div>
</body>
</html>
"""
        return html_template

    @classmethod
    def setup_printer(
        cls,
        printer: QPrinter,
        page_size_id: QPageSize.PageSizeId = QPageSize.PageSizeId.A5,
        output_filepath: Optional[str] = None
    ) -> None:
        """Configures a QPrinter instance for Landscape orientation (A5 or A4) with appropriate margins."""
        margin_mm = 8.0 if page_size_id == QPageSize.PageSizeId.A4 else cls.MARGIN_MM
        printer.setPageSize(QPageSize(page_size_id))
        printer.setPageOrientation(cls.PAGE_ORIENTATION)
        printer.setPageMargins(QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm), QPageLayout.Unit.Millimeter)
        if output_filepath:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(output_filepath)

    @classmethod
    def setup_a5_printer(cls, printer: QPrinter, output_filepath: Optional[str] = None) -> None:
        """Configures a QPrinter instance strictly for A5 Landscape with 6mm margins."""
        cls.setup_printer(printer, QPageSize.PageSizeId.A5, output_filepath=output_filepath)

    @classmethod
    def render_to_printer(
        cls,
        printer: QPrinter,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        page_size_id: Optional[QPageSize.PageSizeId] = None
    ) -> None:
        """Renders the canonical HTML to any pre-configured QPrinter (Physical, Preview, or PDF)."""
        if page_size_id is None:
            page_size_id = printer.pageLayout().pageSize().id()
        html_doc = cls.generate_html(bom_items, project_name, total_qty, page_size_id=page_size_id)
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
        Exports the canonical Assembly Worksheet to a vector PDF in Landscape (A5 or A4).
        Returns the absolute filepath of the generated PDF.
        """
        if page_size_id is None:
            page_size_id = cls.PAGE_SIZE_ID

        if not output_filepath:
            output_filepath = cls.get_default_pdf_filename(project_name, page_size_id=page_size_id)

        output_filepath = os.path.abspath(output_filepath)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        cls.setup_printer(printer, page_size_id=page_size_id, output_filepath=output_filepath)
        cls.render_to_printer(printer, bom_items, project_name, total_qty, page_size_id=page_size_id)

        return output_filepath
