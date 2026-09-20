"""
Omnix Core — Deterministic CSV Exporter (GAP-18)
Conforms strictly to RFC 4180 with utf-8-sig encoding and canonical column ordering.
"""

import csv
import io
import os
from typing import List

from core.procurement.reporting.models import (
    ProcurementReportData,
    ReportLineItem,
    ReportType,
)


class ProcurementCSVExporter:
    """
    Exports a ProcurementReportData model to RFC-4180 compliant CSV format
    with UTF-8 Byte Order Mark (utf-8-sig) for native Windows/Excel compatibility.
    """

    @classmethod
    def get_headers(cls, report_type: ReportType) -> List[str]:
        headers = [
            "Line",
            "Status",
            "Designator",
            "MPN",
            "Description",
            "Manufacturer",
            "Package",
            "Footprint",
            "BOM Demand",
            "In Stock",
            "Shortage Qty",
            "Target Order Qty",
            "Vendor",
            "Vendor SKU",
            "Unit Price (IRR)",
            "Total Price (IRR)",
            "MOQ",
            "Packaging Step",
            "Candidate Count",
            "Audit Summary",
            "Warnings",
            "PDP URL",
        ]
        if report_type == ReportType.POST_STAGING_FINAL:
            headers.extend([
                "Actual Staged Qty",
                "Staging Status",
                "Vendor Response Message",
            ])
        return headers

    @classmethod
    def build_row(cls, item: ReportLineItem, report_type: ReportType) -> List[str]:
        # Build audit summary string
        cand_summaries = []
        for c in item.candidates:
            if c.is_selected:
                cand_summaries.append(f"SELECTED: {c.vendor_name} [{c.vendor_sku or c.mpn}]")
            elif c.is_eligible:
                cand_summaries.append(f"ELIGIBLE: {c.vendor_name} [{c.vendor_sku or c.mpn}] ({c.total_price_irr or 0:,} IRR)")
            else:
                reasons_str = "; ".join(c.rejection_reasons) if c.rejection_reasons else c.qualification_state
                cand_summaries.append(f"REJECTED: {c.vendor_name} [{c.vendor_sku or c.mpn}] ({reasons_str})")
        audit_summary_str = " | ".join(cand_summaries)

        warnings_str = " | ".join(item.warnings) if item.warnings else ""

        row = [
            str(item.line_number),
            item.status,
            item.designator,
            item.part_number,
            item.description.replace("\n", " ").replace("\r", ""),
            item.manufacturer,
            item.package,
            item.footprint,
            str(item.bom_demand_qty),
            str(item.db_stock_qty),
            str(item.shortage_qty),
            str(item.target_order_qty),
            item.selected_vendor_name,
            item.selected_sku,
            str(item.unit_price_irr) if item.unit_price_irr is not None else "",
            str(item.total_price_irr) if item.total_price_irr is not None else "",
            str(item.moq),
            str(item.packaging_step),
            str(item.candidate_count),
            audit_summary_str,
            warnings_str,
            item.pdp_url,
        ]

        if report_type == ReportType.POST_STAGING_FINAL:
            row.extend([
                str(item.actual_quantity_staged) if item.actual_quantity_staged is not None else "",
                item.staging_status,
                item.vendor_response_message.replace("\n", " ").replace("\r", ""),
            ])

        return row

    @classmethod
    def to_string(cls, report: ProcurementReportData) -> str:
        """Generates the full deterministic CSV string representation."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

        # Comment Metadata Block
        writer.writerow([f"# Omnix Multi-Vendor Procurement Report: {report.report_title}"])
        writer.writerow([f"# Report Type: {report.report_type.value} | Mode: {report.procurement_mode.value} | Multiplier: {report.board_multiplier}"])
        writer.writerow([f"# Created: {report.created_at} | Currency: {report.currency} | Total Cost: {report.total_estimated_cost_irr:,} IRR"])
        writer.writerow([])

        # Data Table
        headers = cls.get_headers(report.report_type)
        writer.writerow(headers)

        for item in report.line_items:
            row = cls.build_row(item, report.report_type)
            writer.writerow(row)

        return output.getvalue()

    @classmethod
    def export(cls, report: ProcurementReportData, filepath: str) -> None:
        """Writes the report to a file with utf-8-sig encoding."""
        csv_str = cls.to_string(report)
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            f.write(csv_str)
