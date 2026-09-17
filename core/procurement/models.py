"""
Omnix Core - Normalized Procurement Data Models
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from core.errors import MaxQuantityExceededError
from core.models import ProductReference, OrderConstraints


class EvaluationState(str, Enum):
    """
    Deterministic qualification state of a vendor candidate against a ProcurementRequest.
    Governing GAPs: GAP-04, GAP-05, GAP-06.
    """
    ELIGIBLE = "ELIGIBLE"
    INCOMPATIBLE_MPN = "INCOMPATIBLE_MPN"
    INCOMPATIBLE_MANUFACTURER = "INCOMPATIBLE_MANUFACTURER"
    INCOMPATIBLE_PACKAGE = "INCOMPATIBLE_PACKAGE"
    INCOMPATIBLE_FOOTPRINT = "INCOMPATIBLE_FOOTPRINT"
    INCOMPATIBLE_DIMENSIONS = "INCOMPATIBLE_DIMENSIONS"
    UNKNOWN_REQUIRED_PARAMETER = "UNKNOWN_REQUIRED_PARAMETER"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNORDERABLE = "UNORDERABLE"
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"


def normalize_constraint_string(s: Optional[str]) -> str:
    """
    Conservative string normalization for technical constraints (MPN, package, footprint, brand, specs).
    Rules:
    - Strip leading/trailing whitespace
    - Lowercase
    - Remove hyphen '-'
    - Remove underscore '_'
    - Remove spaces ' '
    
    Invariants:
    - 'SOIC-8', 'SOIC_8', ' SOIC 8 ' -> 'soic8' (Match)
    - 'DIP-8' ('dip8') vs 'PDIP-8' ('pdip8') -> Mismatch (OD-001 preserved OPEN).
    """
    if not s or not isinstance(s, str):
        return ""
    return s.strip().lower().replace("-", "").replace("_", "").replace(" ", "")


@dataclass
class PriceTier:
    """Represents a volume discount bracket for quantity-based tiered pricing."""
    min_quantity: int
    unit_price_irr: int
    raw_label: str = ""

    def __post_init__(self):
        if self.min_quantity < 1:
            raise ValueError(f"min_quantity must be >= 1 (got {self.min_quantity}).")
        if self.unit_price_irr < 0:
            raise ValueError(f"unit_price_irr must be >= 0 (got {self.unit_price_irr}).")


@dataclass
class ProcurementRequest:
    """Encapsulates a vendor-neutral request for a single BOM or shortage component."""
    part_number: str
    required_quantity: int
    description: str = ""
    explicit_vendor_id: Optional[str] = None
    explicit_vendor_url: Optional[str] = None
    manufacturer: Optional[str] = None
    allowed_manufacturers: Optional[List[str]] = None
    is_manufacturer_any: bool = False
    package: Optional[str] = None
    footprint: Optional[str] = None
    required_specs: Dict[str, str] = field(default_factory=dict)
    required_dimensions: Dict[str, str] = field(default_factory=dict)
    exact_mpn_required: bool = True
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.part_number or not isinstance(self.part_number, str) or not self.part_number.strip():
            raise ValueError("part_number must be a non-empty string.")
        if self.required_quantity < 1:
            raise ValueError(f"required_quantity must be >= 1 (got {self.required_quantity}).")
        self.part_number = self.part_number.strip()
        if self.package:
            self.package = self.package.strip()
        if self.footprint:
            self.footprint = self.footprint.strip()
        if self.manufacturer:
            self.manufacturer = self.manufacturer.strip()


@dataclass
class VendorProcurementCandidate:
    """Normalized vendor component offer extracted from a vendor catalog or PDP."""
    vendor_id: str
    part_number: str
    product_ref: ProductReference
    description: str = ""
    in_stock: bool = False
    stock_quantity: int = 0
    can_order: bool = False
    base_unit_price_irr: Optional[int] = None
    price_tiers: List[PriceTier] = field(default_factory=list)
    order_constraints: OrderConstraints = field(default_factory=OrderConstraints)
    manufacturer: Optional[str] = None
    package: Optional[str] = None
    footprint: Optional[str] = None
    dimensions: Dict[str, str] = field(default_factory=dict)
    raw_status_text: str = ""
    specs: Dict[str, str] = field(default_factory=dict)


@dataclass
class CandidateEvaluation:
    """Deterministic evaluation of a candidate against a specific required quantity and constraints."""
    candidate: VendorProcurementCandidate
    required_quantity: int
    effective_quantity: int
    effective_unit_price_irr: Optional[int] = None
    effective_total_price_irr: Optional[int] = None
    is_eligible: bool = False
    is_exact_mpn: bool = False
    state: EvaluationState = EvaluationState.ELIGIBLE
    rejection_reasons: List[str] = field(default_factory=list)
    unknown_parameters: List[str] = field(default_factory=list)


@dataclass
class RequestProcurementResult:
    """Procurement outcome for an individual ProcurementRequest."""
    request: ProcurementRequest
    candidates: List[VendorProcurementCandidate] = field(default_factory=list)
    evaluations: List[CandidateEvaluation] = field(default_factory=list)
    selected_evaluation: Optional[CandidateEvaluation] = None
    status: str = "UNRESOLVED"  # "RESOLVED", "OUT_OF_STOCK", "UNRESOLVED", "ERROR"
    error_message: str = ""


@dataclass
class BOMProcurementPlan:
    """Aggregate multi-vendor procurement plan for a BOM or inventory shortage batch."""
    plan_id: str = ""
    created_at: str = ""
    results: List[RequestProcurementResult] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return len(self.results)

    @property
    def resolved_count(self) -> int:
        return sum(1 for r in self.results if r.status == "RESOLVED" and r.selected_evaluation is not None)

    @property
    def unresolved_count(self) -> int:
        return self.total_items - self.resolved_count

    @property
    def is_complete(self) -> bool:
        return self.total_items > 0 and self.unresolved_count == 0

    @property
    def total_cost_irr(self) -> int:
        total = 0
        for r in self.results:
            if r.selected_evaluation and r.selected_evaluation.effective_total_price_irr:
                total += r.selected_evaluation.effective_total_price_irr
        return total

    def get_selected_evaluations(self) -> List[CandidateEvaluation]:
        return [r.selected_evaluation for r in self.results if r.selected_evaluation is not None]

    def get_unresolved_results(self) -> List[RequestProcurementResult]:
        return [r for r in self.results if r.status != "RESOLVED" or r.selected_evaluation is None]


def calculate_effective_quantity(
    needed_qty: int,
    packaging_step: int = 1,
    moq: int = 1,
    max_orderable: Optional[int] = None,
) -> int:
    """
    Deterministically calculate order quantity respecting packaging step, MOQ, and limits.
    
    Formula:
        effective_qty = max(ceil(needed_qty / packaging_step) * packaging_step, moq)
        
    Raises:
        ValueError: If needed_qty, packaging_step, or moq < 1.
        MaxQuantityExceededError: If effective_qty > max_orderable.
    """
    if needed_qty < 1:
        raise ValueError(f"needed_qty must be >= 1 (got {needed_qty}).")

    step = max(packaging_step if packaging_step is not None else 1, 1)
    min_order = max(moq if moq is not None else 1, 1)

    multiples = math.ceil(needed_qty / step)
    stepped_qty = multiples * step
    effective_qty = max(stepped_qty, min_order)

    if max_orderable is not None and max_orderable >= 1:
        if effective_qty > max_orderable:
            raise MaxQuantityExceededError(
                f"Calculated effective quantity ({effective_qty}) exceeds max orderable limit ({max_orderable}).",
                context={"needed_qty": needed_qty, "effective_qty": effective_qty, "max_orderable": max_orderable},
            )

    return effective_qty


def effective_unit_price(candidate: VendorProcurementCandidate, quantity: int) -> Optional[int]:
    """
    Deterministically resolve unit price for a given quantity.
    
    Rules:
    1. If price_tiers exist: choose the tier with greatest min_quantity <= quantity.
    2. Else: fall back to base_unit_price_irr.
    3. If neither exists: return None.
    """
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1 (got {quantity}).")

    if candidate.price_tiers:
        matching_tiers = [t for t in candidate.price_tiers if t.min_quantity <= quantity]
        if matching_tiers:
            best_tier = max(matching_tiers, key=lambda t: t.min_quantity)
            return best_tier.unit_price_irr

    return candidate.base_unit_price_irr


def effective_total_price(candidate: VendorProcurementCandidate, quantity: int) -> Optional[int]:
    """Calculate total price = quantity * effective_unit_price."""
    unit_p = effective_unit_price(candidate, quantity)
    if unit_p is None:
        return None
    return unit_p * quantity
