"""
Omnix Core — Deterministic PDF Exporter (GAP-18)
Renders high-quality multi-page PDF documents via PyQt6 QTextDocument and QPrinter.
Includes full Persian/RTL and mixed-language typography support.
"""

import os
from typing import Optional
from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter

from core.procurement.reporting.models import (
    ProcurementReportData,
    ReportLineItem,
    ReportType,
)


class ProcurementPDFExporter:
    """
    Exports ProcurementReportData to a PDF document with clean printable tables,
    vendor allocation summary boxes, decision audit trails, and status badges.
    """

    @classmethod
    def generate_html(cls, report: ProcurementReportData) -> str:
        """Constructs deterministic HTML for PDF rendering."""
        # 1. Vendor Allocation HTML
        vendor_rows = ""
        for vs in report.vendor_summaries:
            st_badge = (
                '<span style="color:#059669; font-weight:bold;">✅ SUCCESS</span>'
                if vs.staging_status == "SUCCESS"
                else (
                    '<span style="color:#dc2626; font-weight:bold;">❌ FAILED</span>'
                    if vs.staging_status == "FAILED"
                    else (
                        '<span style="color:#d97706; font-weight:bold;">⚠️ PARTIAL</span>'
                        if vs.staging_status == "PARTIAL"
                        else '<span style="color:#64748b;">⏳ PENDING</span>'
                    )
                )
            )
            extra_cols = ""
            if report.report_type == ReportType.POST_STAGING_FINAL:
                extra_cols = f"""
                <td style="text-align:center; padding:5px 8px; border:1px solid #cbd5e1;">{vs.actual_staged_pieces:,}</td>
                <td style="text-align:center; padding:5px 8px; border:1px solid #cbd5e1;">{st_badge}</td>
                """

            vendor_rows += f"""
            <tr>
                <td style="padding:5px 8px; border:1px solid #cbd5e1; font-weight:bold;">{vs.vendor_name}</td>
                <td style="text-align:center; padding:5px 8px; border:1px solid #cbd5e1;">{vs.item_count}</td>
                <td style="text-align:center; padding:5px 8px; border:1px solid #cbd5e1;">{vs.total_pieces:,}</td>
                <td style="text-align:right; padding:5px 8px; border:1px solid #cbd5e1; font-weight:bold; color:#0284c7;">{vs.subtotal_cost_irr:,} IRR</td>
                {extra_cols}
            </tr>
            """

        vendor_extra_hdr = ""
        if report.report_type == ReportType.POST_STAGING_FINAL:
            vendor_extra_hdr = """
            <th width="12%" style="text-align:center;">Staged Pcs</th>
            <th width="15%" style="text-align:center;">Staging Status</th>
            """

        # 2. Sourced Line Items HTML
        item_rows = ""
        for it in report.line_items:
            bg = "#ffffff" if it.line_number % 2 != 0 else "#f8fafc"
            
            # Status Badge
            if it.status in ("READY", "STAGED"):
                st_html = f'<span style="color:#059669; font-weight:bold;">{it.status}</span>'
            elif it.status == "NO_OP_SATISFIED":
                st_html = '<span style="color:#d97706; font-weight:bold;">NO-OP (IN CART)</span>'
            else:
                st_html = f'<span style="color:#dc2626; font-weight:bold;">{it.status}</span>'

            up_str = f"{it.unit_price_irr:,} IRR" if it.unit_price_irr is not None else "—"
            tp_str = f"{it.total_price_irr:,} IRR" if it.total_price_irr is not None else "—"

            extra_cols = ""
            if report.report_type == ReportType.POST_STAGING_FINAL:
                staged_val = str(it.actual_quantity_staged) if it.actual_quantity_staged is not None else "—"
                extra_cols = f"""
                <td style="text-align:center; border:1px solid #cbd5e1; padding:4px 6px;">{staged_val}</td>
                <td style="text-align:center; border:1px solid #cbd5e1; padding:4px 6px; font-size:7pt;">{it.staging_status}</td>
                """

            item_rows += f"""
            <tr style="background-color:{bg};">
                <td style="text-align:center; color:#64748b; border:1px solid #cbd5e1; padding:4px 6px;">{it.line_number}</td>
                <td style="text-align:center; border:1px solid #cbd5e1; padding:4px 6px;">{st_html}</td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px; font-weight:bold;">{it.designator}</td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px;"><code>{it.part_number}</code></td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px; color:#1e293b;" dir="auto">{it.description or it.manufacturer or '—'}</td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px;">{it.package or it.footprint or '—'}</td>
                <td style="text-align:center; border:1px solid #cbd5e1; padding:4px 6px;">{it.target_order_qty}</td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px; font-weight:600; color:#0284c7;">{it.selected_vendor_name}</td>
                <td style="border:1px solid #cbd5e1; padding:4px 6px;"><code>{it.selected_sku}</code></td>
                <td style="text-align:right; border:1px solid #cbd5e1; padding:4px 6px;">{up_str}</td>
                <td style="text-align:right; border:1px solid #cbd5e1; padding:4px 6px; font-weight:bold;">{tp_str}</td>
                {extra_cols}
            </tr>
            """

        item_extra_hdr = ""
        if report.report_type == ReportType.POST_STAGING_FINAL:
            item_extra_hdr = """
            <th width="7%" style="text-align:center;">Staged Qty</th>
            <th width="9%" style="text-align:center;">Staging Status</th>
            """

        # 3. Candidate Decision Audit Trail Summary HTML
        audit_blocks = ""
        has_alternatives_or_rejections = False
        for it in report.line_items:
            if len(it.candidates) > 1 or it.status == "UNRESOLVED" or it.warnings:
                has_alternatives_or_rejections = True
                cand_list_html = ""
                for c in it.candidates:
                    sel_badge = ' <b style="color:#059669;">[SELECTED]</b>' if c.is_selected else ""
                    if c.is_eligible:
                        eval_badge = '<span style="color:#059669;">Eligible</span>'
                    else:
                        eval_badge = f'<span style="color:#dc2626;">Disqualified: {"; ".join(c.rejection_reasons)}</span>'

                    p_str = f"{c.total_price_irr:,} IRR" if c.total_price_irr else "No Price"
                    cand_list_html += f"""
                    <li style="margin-bottom:3px;">
                        <b>{c.vendor_name}</b> — SKU: <code>{c.vendor_sku or c.mpn}</code> | {p_str} | Status: {eval_badge}{sel_badge}
                    </li>
                    """

                warn_html = ""
                if it.warnings:
                    warn_html = f'<div style="color:#b45309; font-size:7.5pt; margin-top:2px;">⚠️ <b>Warnings:</b> {"; ".join(it.warnings)}</div>'

                audit_blocks += f"""
                <div style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:4px; padding:6px 8px; margin-bottom:6px;">
                    <div style="font-weight:bold; color:#0f172a; margin-bottom:3px;">
                        Line {it.line_number}: {it.part_number} ({it.designator}) — {len(it.candidates)} Discovered Offer(s)
                    </div>
                    <ul style="margin:2px 0 2px 18px; padding:0; font-size:8pt; color:#334155;">
                        {cand_list_html}
                    </ul>
                    {warn_html}
                </div>
                """

        audit_section_html = ""
        if has_alternatives_or_rejections:
            audit_section_html = f"""
            <div style="page-break-before: auto; margin-top:16px;">
                <h2 style="font-size:11pt; color:#0f172a; border-bottom:1.5px solid #cbd5e1; padding-bottom:3px; margin-bottom:8px;">
                    🔍 Candidate Decision Audit Trail & Disqualification Log
                </h2>
                {audit_blocks}
            </div>
            """

        mode_badge = (
            '<span style="background-color:#0284c7; color:#ffffff; padding:2px 6px; border-radius:3px; font-weight:bold;">Mode B (Turnkey Direct BOM)</span>'
            if report.procurement_mode.value == "DIRECT_BOM"
            else '<span style="background-color:#059669; color:#ffffff; padding:2px 6px; border-radius:3px; font-weight:bold;">Mode A (Database-Aware Shortages)</span>'
        )

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{report.report_title}</title>
<style>
    body {{ font-family: "Segoe UI", Arial, Helvetica, sans-serif; font-size: 8pt; color: #0f172a; margin: 0; padding: 0; }}
    .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 6px; margin-bottom: 12px; }}
    h1 {{ font-size: 13.5pt; color: #0f172a; margin: 0 0 4px 0; font-weight: bold; }}
    .meta {{ font-size: 8pt; color: #475569; }}
    .kpi-container {{ display: table; width: 100%; margin-bottom: 12px; border-collapse: collapse; }}
    .kpi-cell {{ display: table-cell; background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 6px 10px; text-align: center; }}
    .kpi-lbl {{ font-size: 7.5pt; color: #64748b; text-transform: uppercase; font-weight: bold; }}
    .kpi-val {{ font-size: 11pt; font-weight: bold; color: #0284c7; margin-top: 2px; }}
    table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; border: 1px solid #cbd5e1; }}
    table.data-table th {{ background-color: #1e293b; color: #ffffff; font-weight: bold; font-size: 7.5pt; padding: 5px 6px; border: 1px solid #cbd5e1; text-align: left; }}
    table.data-table td {{ font-size: 8pt; }}
    code {{ font-family: Consolas, "Courier New", monospace; background-color: #f1f5f9; padding: 1px 3px; border-radius: 2px; font-size: 7.5pt; }}
    .footer {{ font-size: 7pt; color: #94a3b8; text-align: center; margin-top: 14px; border-top: 1px solid #cbd5e1; padding-top: 4px; }}
</style>
</head>
<body>
    <div class="header">
        <h1>Omnix Multi-Vendor Procurement Order Report</h1>
        <div class="meta">
            <b>Project:</b> {report.report_title} &nbsp;|&nbsp;
            <b>Procurement Mode:</b> {mode_badge} &nbsp;|&nbsp;
            <b>Batch Multiplier:</b> {report.board_multiplier} Board(s) &nbsp;|&nbsp;
            <b>Date:</b> {report.created_at} &nbsp;|&nbsp;
            <b>Currency:</b> {report.currency}
        </div>
    </div>

    <div class="kpi-container">
        <div class="kpi-cell">
            <div class="kpi-lbl">Total Items</div>
            <div class="kpi-val">{report.total_line_items}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-lbl">Ready / Sourced</div>
            <div class="kpi-val" style="color:#059669;">{report.resolved_line_items}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-lbl">Unresolved Items</div>
            <div class="kpi-val" style="color:#dc2626;">{report.unresolved_line_items}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-lbl">Total Estimated Cost</div>
            <div class="kpi-val">{report.total_estimated_cost_irr:,} IRR</div>
        </div>
    </div>

    <h2 style="font-size:10pt; color:#0f172a; margin:0 0 6px 0;">📦 Multi-Vendor Sourcing Allocation Summary:</h2>
    <table class="data-table" cellspacing="0" cellpadding="4">
        <thead>
            <tr>
                <th width="25%">Vendor</th>
                <th width="15%" style="text-align:center;">Allocated Items</th>
                <th width="15%" style="text-align:center;">Total Units</th>
                <th width="20%" style="text-align:right;">Subtotal (IRR)</th>
                {vendor_extra_hdr}
            </tr>
        </thead>
        <tbody>
            {vendor_rows}
        </tbody>
    </table>

    <h2 style="font-size:10pt; color:#0f172a; margin:12px 0 6px 0;">📋 Sourced Line Items Procurement Schedule:</h2>
    <table class="data-table" cellspacing="0" cellpadding="4">
        <thead>
            <tr>
                <th width="3%" style="text-align:center;">#</th>
                <th width="8%" style="text-align:center;">Status</th>
                <th width="12%">Designator</th>
                <th width="16%">Part Number / MPN</th>
                <th width="13%">Description / Mfg</th>
                <th width="9%">Package</th>
                <th width="6%" style="text-align:center;">Qty</th>
                <th width="12%">Selected Vendor</th>
                <th width="10%">Vendor SKU</th>
                <th width="9%" style="text-align:right;">Unit Price</th>
                <th width="10%" style="text-align:right;">Total Cost</th>
                {item_extra_hdr}
            </tr>
        </thead>
        <tbody>
            {item_rows}
        </tbody>
    </table>

    {audit_section_html}

    <div class="footer">
        Omnix Multi-Vendor Procurement Platform &nbsp;•&nbsp; Report ID: {report.report_id} &nbsp;•&nbsp; Generated Deterministically
    </div>
</body>
</html>
"""
        return html_content

    @classmethod
    def export(cls, report: ProcurementReportData, filepath: str) -> None:
        """Renders HTML content to a vector PDF via QTextDocument and QPrinter."""
        html = cls.generate_html(report)
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        if filepath.lower().endswith(".html"):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            return True

        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(filepath)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)

        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 8))
        page_size = printer.pageLayout().paintRectPixels(printer.resolution()).size()
        doc.setPageSize(QSizeF(page_size))
        doc.setHtml(html)
        doc.print(printer)
        return True
