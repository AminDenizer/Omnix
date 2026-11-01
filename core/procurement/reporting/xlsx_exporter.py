"""
Omnix Core — Deterministic Excel / XLSX Exporter (GAP-18)
Multi-tab workbook with frozen panes, auto-filters, auto-scaled columns, and numeric formats.
"""

import os
from typing import Any, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.procurement.reporting.models import (
    ProcurementReportData,
    ReportLineItem,
    ReportType,
)


class ProcurementXLSXExporter:
    """
    Exports ProcurementReportData to an Excel (.xlsx) workbook using openpyxl.
    Features:
    - Tab 1: Procurement Summary (KPIs, Vendor Allocation Table, Sourced Items Table)
    - Tab 2: Candidate Decision Audit Trail (Complete record of all discovered offers)
    - Tab 3: Warnings & Incompatibilities (Filtered engineering review sheet)
    """

    @classmethod
    def export(cls, report: ProcurementReportData, filepath: str) -> None:
        wb = openpyxl.Workbook()
        # Remove default sheet
        default_sheet = wb.active
        
        # 1. Sheet 1: Procurement Summary
        ws_summary = wb.create_sheet(title="Procurement Summary")
        cls._build_summary_sheet(ws_summary, report)

        # 2. Sheet 2: Candidate Audit Trail
        ws_audit = wb.create_sheet(title="Candidate Audit Trail")
        cls._build_audit_sheet(ws_audit, report)

        # 3. Sheet 3: Warnings & Incompatibilities (if warnings/unresolved exist)
        ws_warnings = wb.create_sheet(title="Warnings & Incompatibilities")
        cls._build_warnings_sheet(ws_warnings, report)

        if default_sheet and default_sheet in wb.worksheets:
            wb.remove(default_sheet)

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        wb.save(filepath)
        return True

    @classmethod
    def _build_summary_sheet(cls, ws, report: ProcurementReportData) -> None:
        font_title = Font(name="Segoe UI", size=14, bold=True, color="0F172A")
        font_sub = Font(name="Segoe UI", size=10, color="475569")
        font_hdr = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=9, color="0F172A")
        font_bold = Font(name="Segoe UI", size=9, bold=True, color="0F172A")
        font_kpi_val = Font(name="Segoe UI", size=12, bold=True, color="0284C7")
        font_kpi_lbl = Font(name="Segoe UI", size=9, color="64748B")

        fill_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_v_hdr = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        fill_kpi = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # 1. Title Block
        ws["A1"] = f"Omnix Multi-Vendor Procurement Order Report — {report.report_title}"
        ws["A1"].font = font_title
        ws["A2"] = (
            f"Report Type: {report.report_type.value} | Mode: {report.procurement_mode.value} | "
            f"Batch Multiplier: {report.board_multiplier} | Created: {report.created_at} | Currency: {report.currency}"
        )
        ws["A2"].font = font_sub

        curr_row = 4

        # 2. Sourced Line Items Table (Header at curr_row)
        ws.cell(row=curr_row, column=1, value="Sourced Line Items Procurement Schedule:").font = font_bold
        curr_row += 1
        tbl_hdr_row = curr_row

        headers = [
            "#", "Status", "Designator", "Part Number / MPN", "Description", "Manufacturer",
            "Package", "Footprint", "BOM Demand", "DB Stock", "Shortage", "Target Order Qty",
            "Selected Vendor", "Selected SKU", "Unit Price (IRR)", "Total Price (IRR)",
            "MOQ", "Step", "Candidate Offers", "PDP URL"
        ]
        if report.report_type == ReportType.POST_STAGING_FINAL:
            headers.extend(["Actual Staged Qty", "Staging Status", "Vendor Message"])

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=tbl_hdr_row, column=c_idx, value=h)
            cell.font = font_hdr
            cell.fill = fill_hdr
            cell.alignment = align_center
            cell.border = thin_border

        curr_row += 1

        for it in report.line_items:
            row_data = [
                it.line_number,
                it.status,
                it.designator,
                it.part_number,
                it.description,
                it.manufacturer,
                it.package,
                it.footprint,
                it.bom_demand_qty,
                it.db_stock_qty,
                it.shortage_qty,
                it.target_order_qty,
                it.selected_vendor_name,
                it.selected_sku,
                it.unit_price_irr if it.unit_price_irr is not None else "",
                it.total_price_irr if it.total_price_irr is not None else "",
                it.moq,
                it.packaging_step,
                it.candidate_count,
                it.pdp_url,
            ]
            if report.report_type == ReportType.POST_STAGING_FINAL:
                row_data.extend([
                    it.actual_quantity_staged if it.actual_quantity_staged is not None else "",
                    it.staging_status,
                    it.vendor_response_message,
                ])

            is_zebra = (it.line_number % 2 == 0)
            for c_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=curr_row, column=c_idx, value=val)
                cell.font = font_data
                cell.border = thin_border
                if is_zebra:
                    cell.fill = fill_zebra

                # Alignments & numeric formats
                if c_idx in (1, 9, 10, 11, 12, 17, 18, 19, 21):
                    cell.alignment = align_center
                    if isinstance(val, (int, float)):
                        cell.number_format = "#,##0"
                elif c_idx in (15, 16):
                    cell.alignment = align_right
                    if isinstance(val, (int, float)):
                        cell.number_format = '#,##0 "IRR"'
                elif c_idx == 2:
                    cell.alignment = align_center
                    if it.status in ("READY", "STAGED"):
                        cell.font = Font(name="Segoe UI", size=9, bold=True, color="059669")
                    elif it.status in ("UNRESOLVED", "FAILED"):
                        cell.font = Font(name="Segoe UI", size=9, bold=True, color="DC2626")
                    elif it.status == "NO_OP_SATISFIED":
                        cell.font = Font(name="Segoe UI", size=9, bold=True, color="D97706")
                else:
                    cell.alignment = align_left

            curr_row += 1

        # Freeze panes below line items header
        ws.freeze_panes = f"A{tbl_hdr_row + 1}"

        # Enable auto-filter on line items table
        last_col_letter = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A{tbl_hdr_row}:{last_col_letter}{curr_row - 1}"

        # Auto-scale column widths
        cls._autofit_columns(ws)

    @classmethod
    def _build_audit_sheet(cls, ws, report: ProcurementReportData) -> None:
        font_hdr = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=9, color="0F172A")
        fill_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        headers = [
            "BOM Line #", "Target MPN", "Designator", "Vendor", "Vendor SKU",
            "Discovered MPN", "Manufacturer", "Package", "Footprint", "Stock Qty",
            "MOQ", "Step", "Unit Price (IRR)", "Total Price (IRR)", "Volume Tiers",
            "Is Selected", "Qualification State", "Rejection Reasons", "Unknown Parameters", "PDP URL"
        ]

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=c_idx, value=h)
            cell.font = font_hdr
            cell.fill = fill_hdr
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        curr_row = 2
        for it in report.line_items:
            for c in it.candidates:
                reasons_str = "; ".join(c.rejection_reasons) if c.rejection_reasons else ""
                unknown_str = "; ".join(c.unknown_parameters) if c.unknown_parameters else ""
                selected_str = "YES" if c.is_selected else "NO"

                row_data = [
                    it.line_number,
                    it.part_number,
                    it.designator,
                    c.vendor_name,
                    c.vendor_sku,
                    c.mpn,
                    c.manufacturer,
                    c.package,
                    c.footprint,
                    c.stock_quantity if c.in_stock else "Out of Stock",
                    c.moq,
                    c.packaging_step,
                    c.unit_price_irr if c.unit_price_irr is not None else "",
                    c.total_price_irr if c.total_price_irr is not None else "",
                    c.price_tiers_summary,
                    selected_str,
                    c.qualification_state,
                    reasons_str,
                    unknown_str,
                    c.pdp_url,
                ]

                is_zebra = (curr_row % 2 == 0)
                for c_idx, val in enumerate(row_data, start=1):
                    cell = ws.cell(row=curr_row, column=c_idx, value=val)
                    cell.font = font_data
                    cell.border = thin_border
                    if is_zebra:
                        cell.fill = fill_zebra

                    if c_idx in (1, 10, 11, 12, 16):
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif c_idx in (13, 14):
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                        if isinstance(val, (int, float)):
                            cell.number_format = '#,##0 "IRR"'
                    else:
                        cell.alignment = Alignment(horizontal="left", vertical="center")

                    if c_idx == 16 and c.is_selected:
                        cell.font = Font(name="Segoe UI", size=9, bold=True, color="059669")

                curr_row += 1

        ws.freeze_panes = "A2"
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A1:{last_col}{curr_row - 1}"
        cls._autofit_columns(ws)

    @classmethod
    def _build_warnings_sheet(cls, ws, report: ProcurementReportData) -> None:
        font_hdr = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=9, color="0F172A")
        fill_hdr = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
        fill_zebra = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        headers = ["BOM Line #", "Status", "Designator", "Part Number / MPN", "Item Warnings & Rejection Details"]
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=c_idx, value=h)
            cell.font = font_hdr
            cell.fill = fill_hdr
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        curr_row = 2
        for it in report.line_items:
            has_issue = (it.status in ("UNRESOLVED", "FAILED")) or bool(it.warnings)
            if not has_issue:
                continue

            all_notes = list(it.warnings)
            if it.status == "UNRESOLVED" and not all_notes:
                all_notes.append("No eligible candidate found across registered vendors.")

            notes_str = " | ".join(all_notes)
            row_data = [it.line_number, it.status, it.designator, it.part_number, notes_str]

            for c_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=curr_row, column=c_idx, value=val)
                cell.font = font_data
                cell.border = thin_border
                cell.fill = fill_zebra
                cell.alignment = Alignment(horizontal="center" if c_idx in (1, 2) else "left", vertical="center")

            curr_row += 1

        ws.freeze_panes = "A2"
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A1:{last_col}{max(curr_row - 1, 1)}"
        cls._autofit_columns(ws)

    @staticmethod
    def _autofit_columns(ws) -> None:
        """Auto-adjusts column widths with padding so content is not truncated."""
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if "\n" in val:
                    val = max(val.split("\n"), key=len)
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 50)
