"""
Deterministic Unit Tests for Procurement Models and Helper Functions
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
"""

import pytest
from core.errors import MaxQuantityExceededError
from core.models import ProductReference, OrderConstraints
from core.procurement.models import (
    PriceTier,
    ProcurementRequest,
    VendorProcurementCandidate,
    BOMProcurementPlan,
    calculate_effective_quantity,
    effective_unit_price,
    effective_total_price,
)


class TestPriceTierAndValidation:
    """Verify PriceTier initialization, invariants, and validation."""

    def test_valid_price_tier(self):
        tier = PriceTier(min_quantity=50, unit_price_irr=78100, raw_label="50+ pcs")
        assert tier.min_quantity == 50
        assert tier.unit_price_irr == 78100
        assert tier.raw_label == "50+ pcs"

    def test_invalid_min_quantity_raises(self):
        with pytest.raises(ValueError, match="min_quantity must be >= 1"):
            PriceTier(min_quantity=0, unit_price_irr=50000)
        with pytest.raises(ValueError, match="min_quantity must be >= 1"):
            PriceTier(min_quantity=-10, unit_price_irr=50000)

    def test_invalid_price_raises(self):
        with pytest.raises(ValueError, match="unit_price_irr must be >= 0"):
            PriceTier(min_quantity=1, unit_price_irr=-500)


class TestProcurementRequestValidation:
    """Verify ProcurementRequest validation and defaulting."""

    def test_valid_request(self):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10)
        assert req.part_number == "NE555P"
        assert req.required_quantity == 10
        assert req.exact_mpn_required is True

    def test_invalid_part_number_raises(self):
        with pytest.raises(ValueError, match="part_number must be a non-empty string"):
            ProcurementRequest(part_number="", required_quantity=5)
        with pytest.raises(ValueError, match="part_number must be a non-empty string"):
            ProcurementRequest(part_number="   ", required_quantity=5)

    def test_invalid_quantity_raises(self):
        with pytest.raises(ValueError, match="required_quantity must be >= 1"):
            ProcurementRequest(part_number="LM358", required_quantity=0)
        with pytest.raises(ValueError, match="required_quantity must be >= 1"):
            ProcurementRequest(part_number="LM358", required_quantity=-5)


class TestEffectiveQuantityCalculations:
    """Verify deterministic quantity stepping, MOQ, and max limit enforcement."""

    def test_step_1_exact(self):
        assert calculate_effective_quantity(needed_qty=5, packaging_step=1, moq=1) == 5

    def test_step_10_rounds_up(self):
        assert calculate_effective_quantity(needed_qty=1, packaging_step=10, moq=1) == 10
        assert calculate_effective_quantity(needed_qty=10, packaging_step=10, moq=1) == 10
        assert calculate_effective_quantity(needed_qty=11, packaging_step=10, moq=1) == 20
        assert calculate_effective_quantity(needed_qty=45, packaging_step=10, moq=1) == 50

    def test_step_25_rounds_up(self):
        assert calculate_effective_quantity(needed_qty=30, packaging_step=25, moq=1) == 50
        assert calculate_effective_quantity(needed_qty=50, packaging_step=25, moq=1) == 50

    def test_moq_floor_enforcement(self):
        assert calculate_effective_quantity(needed_qty=3, packaging_step=1, moq=10) == 10
        assert calculate_effective_quantity(needed_qty=15, packaging_step=10, moq=30) == 30

    def test_max_orderable_exceeded_raises(self):
        with pytest.raises(MaxQuantityExceededError):
            calculate_effective_quantity(needed_qty=100, packaging_step=1, moq=1, max_orderable=50)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            calculate_effective_quantity(needed_qty=0)


class TestPriceTierEvaluation:
    """Verify tier selection, boundary checking, and fallback pricing."""

    def test_single_base_price_when_no_tiers(self):
        candidate = VendorProcurementCandidate(
            vendor_id="vendor_demo",
            part_number="NE555",
            product_ref=ProductReference("vendor_demo", "SKU1", "https://demo.com/p/1"),
            base_unit_price_irr=85000,
            price_tiers=[],
        )
        assert effective_unit_price(candidate, 1) == 85000
        assert effective_unit_price(candidate, 50) == 85000
        assert effective_total_price(candidate, 10) == 850000

    def test_multi_tier_volume_discounts(self):
        candidate = VendorProcurementCandidate(
            vendor_id="vendor_demo",
            part_number="LM358",
            product_ref=ProductReference("vendor_demo", "SKU2", "https://demo.com/p/2"),
            base_unit_price_irr=95000,
            price_tiers=[
                PriceTier(min_quantity=1, unit_price_irr=95000),
                PriceTier(min_quantity=50, unit_price_irr=78000),
                PriceTier(min_quantity=100, unit_price_irr=65000),
            ],
        )
        # Quantity 1 -> Tier 1
        assert effective_unit_price(candidate, 1) == 95000
        assert effective_total_price(candidate, 1) == 95000

        # Quantity 49 -> Tier 1
        assert effective_unit_price(candidate, 49) == 95000

        # Quantity 50 (exact boundary) -> Tier 2
        assert effective_unit_price(candidate, 50) == 78000
        assert effective_total_price(candidate, 50) == 3900000

        # Quantity 75 -> Tier 2
        assert effective_unit_price(candidate, 75) == 78000

        # Quantity 100 -> Tier 3
        assert effective_unit_price(candidate, 100) == 65000

        # Quantity 500 -> Tier 3
        assert effective_unit_price(candidate, 500) == 65000
        assert effective_total_price(candidate, 500) == 32500000

    def test_missing_price_returns_none(self):
        candidate = VendorProcurementCandidate(
            vendor_id="vendor_demo",
            part_number="OPA2134",
            product_ref=ProductReference("vendor_demo", "SKU3", "https://demo.com/p/3"),
            base_unit_price_irr=None,
            price_tiers=[],
        )
        assert effective_unit_price(candidate, 10) is None
        assert effective_total_price(candidate, 10) is None


class TestTaskA1ModelExtensions:
    """Verify Task A1 model fields, EvaluationState enum, and string normalization."""

    def test_evaluation_state_enum_members(self):
        from core.procurement.models import EvaluationState
        assert EvaluationState.ELIGIBLE == "ELIGIBLE"
        assert EvaluationState.INCOMPATIBLE_MPN == "INCOMPATIBLE_MPN"
        assert EvaluationState.INCOMPATIBLE_MANUFACTURER == "INCOMPATIBLE_MANUFACTURER"
        assert EvaluationState.INCOMPATIBLE_PACKAGE == "INCOMPATIBLE_PACKAGE"
        assert EvaluationState.INCOMPATIBLE_FOOTPRINT == "INCOMPATIBLE_FOOTPRINT"
        assert EvaluationState.INCOMPATIBLE_DIMENSIONS == "INCOMPATIBLE_DIMENSIONS"
        assert EvaluationState.UNKNOWN_REQUIRED_PARAMETER == "UNKNOWN_REQUIRED_PARAMETER"
        assert EvaluationState.OUT_OF_STOCK == "OUT_OF_STOCK"
        assert EvaluationState.UNORDERABLE == "UNORDERABLE"
        assert EvaluationState.PRICE_UNAVAILABLE == "PRICE_UNAVAILABLE"

    def test_conservative_string_normalization(self):
        from core.procurement.models import normalize_constraint_string
        # Case folding, whitespace trim, hyphen, underscore, space removal
        assert normalize_constraint_string("SOIC-8") == "soic8"
        assert normalize_constraint_string("SOIC_8") == "soic8"
        assert normalize_constraint_string(" SOIC 8 ") == "soic8"
        assert normalize_constraint_string("  soic-8  ") == "soic8"

        # OD-001 preserved OPEN: no package family equivalence
        assert normalize_constraint_string("DIP-8") == "dip8"
        assert normalize_constraint_string("PDIP-8") == "pdip8"
        assert normalize_constraint_string("DIP-8") != normalize_constraint_string("PDIP-8")
        assert normalize_constraint_string("DIP-8") != normalize_constraint_string("SOP-8")
        assert normalize_constraint_string("SOIC-8") != normalize_constraint_string("SOP-8")

        # None / empty handling
        assert normalize_constraint_string(None) == ""
        assert normalize_constraint_string("") == ""
        assert normalize_constraint_string("   ") == ""

    def test_procurement_request_with_constraints(self):
        req = ProcurementRequest(
            part_number="STM32F103C8T6",
            required_quantity=25,
            manufacturer="STMicroelectronics",
            allowed_manufacturers=["STMicroelectronics", "Texas Instruments"],
            package="LQFP-48",
            footprint="LQFP-48",
            required_specs={"voltage": "3.3V", "frequency": "72MHz"},
            required_dimensions={"lead_pitch": "0.5mm"},
        )
        assert req.package == "LQFP-48"
        assert req.footprint == "LQFP-48"
        assert req.manufacturer == "STMicroelectronics"
        assert len(req.allowed_manufacturers) == 2
        assert req.required_specs["voltage"] == "3.3V"
        assert req.required_dimensions["lead_pitch"] == "0.5mm"

    def test_vendor_candidate_with_constraints(self):
        candidate = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="STM32F103C8T6",
            product_ref=ProductReference("vendor_lion", "SKU100", "https://lion.ir/100"),
            manufacturer="STMicroelectronics",
            package="LQFP-48",
            footprint="LQFP-48",
            dimensions={"lead_pitch": "0.5mm"},
            specs={"voltage": "3.3V", "frequency": "72MHz"},
        )
        assert candidate.package == "LQFP-48"
        assert candidate.footprint == "LQFP-48"
        assert candidate.dimensions["lead_pitch"] == "0.5mm"
        assert candidate.specs["voltage"] == "3.3V"

