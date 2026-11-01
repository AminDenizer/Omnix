"""
Omnix Core — Normalized Procurement Reporting Models (GAP-18)
Authoritative, immutable data structures for multi-vendor procurement export.
Preserves strict determinism, currency integrity (IRR), and planned vs actual quantities.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.procurement.models import ProcurementMode


class ReportType(str, Enum):
    """Classification of the procurement export report."""
    PRE_ORDER_CONFIRMATION = "PRE_ORDER_CONFIRMATION"
    POST_STAGING_FINAL = "POST_STAGING_FINAL"


class CandidateLifecycleState(str, Enum):
    """Deterministic candidate evaluation & decision state."""
    DISCOVERED = "DISCOVERED"
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    SELECTED_BY_USER = "SELECTED_BY_USER"
    ACTUALLY_STAGED = "ACTUALLY_STAGED"


@dataclass
class ReportCandidateRecord:
    """Factual, immutable record of an individual vendor candidate offer."""
    vendor_id: str
    vendor_name: str
    vendor_sku: str
    pdp_url: str
    mpn: str
    manufacturer: str
    package: str
    footprint: str
    in_stock: bool
    stock_quantity: int
    moq: int
    packaging_step: int
    unit_price_irr: Optional[int] = None
    total_price_irr: Optional[int] = None
    price_tiers_summary: str = ""
    is_eligible: bool = False
    is_selected: bool = False
    is_actually_staged: bool = False
    qualification_state: str = "DISCOVERED"
    rejection_reasons: List[str] = field(default_factory=list)
    unknown_parameters: List[str] = field(default_factory=list)


@dataclass
class ReportLineItem:
    """Deterministic representation of a single BOM requirement and its evaluated outcome."""
    line_number: int  # 1-based canonical index
    designator: str
    part_number: str
    description: str = ""
    package: str = ""
    footprint: str = ""
    manufacturer: str = ""
    bom_demand_qty: int = 1
    db_stock_qty: int = 0
    shortage_qty: int = 1
    target_order_qty: int = 1  # Q_target_orderable (A3 MOQ/step compliant)
    existing_cart_qty: Optional[int] = None  # Q_existing_cart (Post-staging)
    delta_qty: Optional[int] = None  # Delta_Q (Post-staging)
    actual_quantity_staged: Optional[int] = None  # actual_quantity_staged (Post-staging)
    final_cart_qty: Optional[int] = None  # Q_final_cart (Post-staging)
    is_noop: bool = False
    status: str = "READY"  # "READY", "UNRESOLVED", "STAGED", "NO_OP_SATISFIED", "FAILED"
    selected_vendor_id: Optional[str] = None
    selected_vendor_name: str = "—"
    selected_sku: str = "—"
    pdp_url: str = ""
    unit_price_irr: Optional[int] = None
    total_price_irr: Optional[int] = None
    moq: int = 1
    packaging_step: int = 1
    candidate_count: int = 0
    candidates: List[ReportCandidateRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    staging_status: str = "PENDING_CONFIRMATION"
    vendor_response_message: str = ""


@dataclass
class VendorSummary:
    """Multi-vendor financial and line allocation aggregation."""
    vendor_id: str
    vendor_name: str
    item_count: int = 0
    total_pieces: int = 0
    subtotal_cost_irr: int = 0
    actual_staged_pieces: int = 0
    staging_status: str = "PENDING"  # "PENDING", "SUCCESS", "PARTIAL", "FAILED"
    error_message: str = ""


@dataclass
class ProcurementReportData:
    """Complete, normalized, immutable snapshot ready for deterministic export."""
    report_id: str
    report_title: str
    report_type: ReportType
    created_at: str  # ISO-8601 string metadata
    procurement_mode: ProcurementMode
    source_file: str
    board_multiplier: int = 1
    currency: str = "IRR"
    enabled_vendors: List[str] = field(default_factory=list)
    line_items: List[ReportLineItem] = field(default_factory=list)
    vendor_summaries: List[VendorSummary] = field(default_factory=list)
    total_line_items: int = 0
    resolved_line_items: int = 0
    unresolved_line_items: int = 0
    total_estimated_cost_irr: int = 0
    total_actual_staged_cost_irr: int = 0
    total_warnings_count: int = 0
