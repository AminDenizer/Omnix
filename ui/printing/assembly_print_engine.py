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
    def get_default_pdf_filename(cls, project_name: str) -> str:
        """Returns the canonical default filename for Assembly PDF export."""
        safe_name = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", ".")).strip()
        if not safe_name:
            safe_name = "Assembly_Project"
        return f"{safe_name}_Assembly_Worksheet_A5.pdf"

    @classmethod
    def generate_html(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None
    ) -> str:
        """
        Generates canonical HTML representation of the Assembly Worksheet conforming to the 9-column contract:
        | <PROJECT_NAME> | Comment | Description | Designator | Footprint | LibRef | Quantity | Part Number | Package |
        """
        esc_project_name = html.escape(project_name)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        total_items_count = len(bom_items)
        computed_total_qty = total_qty if total_qty is not None else sum(max(1, getattr(it, "total_needed_qty", getattr(it, "unit_qty", 1))) for it in bom_items)

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
            size: A5 landscape;
            margin: 6mm;
        }}
        body {{
            font-family: "Segoe UI", "Tahoma", "Vazirmatn", "Arial", sans-serif;
            font-size: 7.5pt;
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
        }}
        table.assembly-table th.col-project-header {{
            background-color: #0369a1;
            color: #ffffff;
            text-align: center;
            font-family: monospace;
            font-size: 7.5pt;
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
        .col-n {{ width: 6.5%; }}
        .col-comment {{ width: 10%; }}
        .col-desc {{ width: 23%; }}
        .col-desig {{ width: 18%; }}
        .col-footprint {{ width: 10.5%; }}
        .col-libref {{ width: 9%; }}
        .col-qty {{ width: 5%; }}
        .col-mpn {{ width: 12%; }}
        .col-pkg {{ width: 6%; }}
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
    def setup_a5_printer(cls, printer: QPrinter, output_filepath: Optional[str] = None) -> None:
        """Configures a QPrinter instance strictly for A5 Landscape with 6mm margins."""
        printer.setPageSize(QPageSize(cls.PAGE_SIZE_ID))
        printer.setPageOrientation(cls.PAGE_ORIENTATION)
        printer.setPageMargins(QMarginsF(cls.MARGIN_MM, cls.MARGIN_MM, cls.MARGIN_MM, cls.MARGIN_MM), QPageLayout.Unit.Millimeter)
        if output_filepath:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(output_filepath)

    @classmethod
    def render_to_printer(
        cls,
        printer: QPrinter,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None
    ) -> None:
        """Renders the canonical HTML to any pre-configured QPrinter (Physical or Preview)."""
        html_doc = cls.generate_html(bom_items, project_name, total_qty)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 8))
        page_size = printer.pageLayout().paintRectPixels(printer.resolution()).size()
        doc.setPageSize(QSizeF(page_size))
        doc.setHtml(html_doc)
        doc.print(printer)

    @classmethod
    def export_pdf(
        cls,
        bom_items: List[BOMItem],
        project_name: str,
        total_qty: Optional[int] = None,
        output_filepath: Optional[str] = None
    ) -> str:
        """
        Exports the canonical Assembly Worksheet to an A5 Landscape vector PDF.
        Returns the absolute filepath of the generated PDF.
        """
        if not output_filepath:
            output_filepath = cls.get_default_pdf_filename(project_name)

        output_filepath = os.path.abspath(output_filepath)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        cls.setup_a5_printer(printer, output_filepath=output_filepath)
        cls.render_to_printer(printer, bom_items, project_name, total_qty)

        return output_filepath
