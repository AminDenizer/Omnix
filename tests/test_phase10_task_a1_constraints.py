"""
Omnix Deterministic Unit & Contract Tests for TASK-A1:
Core Technical Matching, Package/Footprint Constraints & Brand Rules
Governing Document: docs/PRODUCT/MASTER_PRODUCT_COMPLETION_GAP_ANALYSIS.md (GAPs: GAP-04, GAP-05, GAP-06)
"""

import pytest
from core.models import ProductReference, OrderConstraints
from core.procurement.models import (
    EvaluationState,
    normalize_constraint_string,
    PriceTier,
    ProcurementRequest,
    VendorProcurementCandidate,
    CandidateEvaluation,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry


@pytest.fixture
def orchestrator():
    registry = VendorRegistry()
    return UniversalProcurementOrchestrator(registry=registry)


def make_candidate(
    vendor_id="vendor_demo",
    part_number="ABC123",
    manufacturer="Texas Instruments",
    package="DIP-8",
    footprint="DIP-8",
    in_stock=True,
    can_order=True,
    price_irr=50000,
    specs=None,
    dimensions=None,
    stock_quantity=100,
):
    return VendorProcurementCandidate(
        vendor_id=vendor_id,
        part_number=part_number,
        product_ref=ProductReference(vendor_id, f"SKU-{part_number}", f"https://demo.ir/{part_number}"),
        manufacturer=manufacturer,
        package=package,
        footprint=footprint,
        in_stock=in_stock,
        can_order=can_order,
        base_unit_price_irr=price_irr,
        stock_quantity=stock_quantity,
        specs=specs or {},
        dimensions=dimensions or {},
    )


class TestTaskA1PackageConstraints:
    """GAP-04: Package constraint verification with conservative normalization."""

    def test_exact_package_match(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, package="DIP-8")
        cand = make_candidate(part_number="NE555P", package="DIP-8")
        ev = orchestrator.evaluate_candidate(cand, required_quantity=10, request=req)
        assert ev.is_eligible is True
        assert ev.state == EvaluationState.ELIGIBLE
        assert len(ev.rejection_reasons) == 0

    def test_conservative_package_normalization_match(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, package="SOIC-8")
        cand1 = make_candidate(part_number="NE555P", package="SOIC_8")
        cand2 = make_candidate(part_number="NE555P", package=" SOIC 8 ")
        cand3 = make_candidate(part_number="NE555P", package="soic-8")

        for c in [cand1, cand2, cand3]:
            ev = orchestrator.evaluate_candidate(c, required_quantity=10, request=req)
            assert ev.is_eligible is True
            assert ev.state == EvaluationState.ELIGIBLE

    def test_package_mismatch_rejection(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, package="DIP-8")
        cand = make_candidate(part_number="NE555P", package="SOP-8")
        ev = orchestrator.evaluate_candidate(cand, required_quantity=10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_PACKAGE
        assert any("Package mismatch" in r for r in ev.rejection_reasons)

    def test_od001_open_no_package_family_assumption(self, orchestrator):
        # DIP-8 != PDIP-8
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, package="DIP-8")
        cand = make_candidate(part_number="NE555P", package="PDIP-8")
        ev = orchestrator.evaluate_candidate(cand, required_quantity=10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_PACKAGE

        # SOIC-8 != SOP-8
        req2 = ProcurementRequest(part_number="NE555P", required_quantity=10, package="SOIC-8")
        cand2 = make_candidate(part_number="NE555P", package="SOP-8")
        ev2 = orchestrator.evaluate_candidate(cand2, required_quantity=10, request=req2)
        assert ev2.is_eligible is False
        assert ev2.state == EvaluationState.INCOMPATIBLE_PACKAGE

    def test_package_unknown_on_candidate(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, package="DIP-8")
        cand = make_candidate(part_number="NE555P", package=None)
        ev = orchestrator.evaluate_candidate(cand, required_quantity=10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.UNKNOWN_REQUIRED_PARAMETER
        assert "package" in ev.unknown_parameters


class TestTaskA1FootprintConstraints:
    """GAP-04: Footprint constraint verification evaluated independently."""

    def test_exact_footprint_match(self, orchestrator):
        req = ProcurementRequest(part_number="STM32", required_quantity=5, footprint="LQFP-48")
        cand = make_candidate(part_number="STM32", footprint="LQFP-48")
        ev = orchestrator.evaluate_candidate(cand, required_quantity=5, request=req)
        assert ev.is_eligible is True
        assert ev.state == EvaluationState.ELIGIBLE

    def test_footprint_mismatch_rejection(self, orchestrator):
        req = ProcurementRequest(part_number="STM32", required_quantity=5, footprint="LQFP-48")
        cand = make_candidate(part_number="STM32", footprint="QFN-48")
        ev = orchestrator.evaluate_candidate(cand, required_quantity=5, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_FOOTPRINT

    def test_footprint_unknown_on_candidate(self, orchestrator):
        req = ProcurementRequest(part_number="STM32", required_quantity=5, footprint="LQFP-48")
        cand = make_candidate(part_number="STM32", footprint=None)
        ev = orchestrator.evaluate_candidate(cand, required_quantity=5, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.UNKNOWN_REQUIRED_PARAMETER
        assert "footprint" in ev.unknown_parameters

    def test_package_and_footprint_evaluated_independently(self, orchestrator):
        req = ProcurementRequest(part_number="U1", required_quantity=5, package="DIP-8", footprint="DIP-8")

        # Case A: package matches, footprint mismatches
        cand_a = make_candidate(part_number="U1", package="DIP-8", footprint="SOIC-8")
        ev_a = orchestrator.evaluate_candidate(cand_a, required_quantity=5, request=req)
        assert ev_a.is_eligible is False
        assert ev_a.state == EvaluationState.INCOMPATIBLE_FOOTPRINT

        # Case B: footprint matches, package mismatches
        cand_b = make_candidate(part_number="U1", package="SOP-8", footprint="DIP-8")
        ev_b = orchestrator.evaluate_candidate(cand_b, required_quantity=5, request=req)
        assert ev_b.is_eligible is False
        assert ev_b.state == EvaluationState.INCOMPATIBLE_PACKAGE


class TestTaskA1ManufacturerBrandConstraints:
    """GAP-06: Brand / Manufacturer rules (ANY vs Explicit Approved Set)."""

    def test_any_manufacturer_accepts_all(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, is_manufacturer_any=True)
        cand_ti = make_candidate(part_number="NE555P", manufacturer="Texas Instruments")
        cand_st = make_candidate(part_number="NE555P", manufacturer="STMicroelectronics")
        cand_none = make_candidate(part_number="NE555P", manufacturer=None)

        assert orchestrator.evaluate_candidate(cand_ti, 10, request=req).is_eligible is True
        assert orchestrator.evaluate_candidate(cand_st, 10, request=req).is_eligible is True
        assert orchestrator.evaluate_candidate(cand_none, 10, request=req).is_eligible is True

    def test_any_string_accepts_all(self, orchestrator):
        req = ProcurementRequest(part_number="NE555P", required_quantity=10, manufacturer="ANY")
        cand = make_candidate(part_number="NE555P", manufacturer="GenericMfg")
        assert orchestrator.evaluate_candidate(cand, 10, request=req).is_eligible is True

    def test_explicit_manufacturer_set_accepts_approved(self, orchestrator):
        req = ProcurementRequest(
            part_number="STM32",
            required_quantity=10,
            allowed_manufacturers=["STMicroelectronics", "Texas Instruments"]
        )
        cand_st = make_candidate(part_number="STM32", manufacturer="STMicroelectronics")
        cand_ti = make_candidate(part_number="STM32", manufacturer="Texas Instruments")
        assert orchestrator.evaluate_candidate(cand_st, 10, request=req).is_eligible is True
        assert orchestrator.evaluate_candidate(cand_ti, 10, request=req).is_eligible is True

    def test_explicit_manufacturer_set_rejects_unapproved(self, orchestrator):
        req = ProcurementRequest(
            part_number="STM32",
            required_quantity=10,
            allowed_manufacturers=["STMicroelectronics", "Texas Instruments"]
        )
        cand_unapproved = make_candidate(part_number="STM32", manufacturer="UnapprovedCloneBrand")
        ev = orchestrator.evaluate_candidate(cand_unapproved, 10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_MANUFACTURER

    def test_unlisted_manufacturer_when_explicit_required_is_unknown(self, orchestrator):
        req = ProcurementRequest(
            part_number="STM32",
            required_quantity=10,
            allowed_manufacturers=["STMicroelectronics"]
        )
        cand_none = make_candidate(part_number="STM32", manufacturer=None)
        ev = orchestrator.evaluate_candidate(cand_none, 10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.UNKNOWN_REQUIRED_PARAMETER
        assert "manufacturer" in ev.unknown_parameters

    def test_cheaper_unapproved_manufacturer_cannot_beat_approved(self, orchestrator):
        req = ProcurementRequest(
            part_number="STM32",
            required_quantity=10,
            allowed_manufacturers=["STMicroelectronics"]
        )
        cand_cheap_unapproved = make_candidate(vendor_id="v1", part_number="STM32", manufacturer="Clone", price_irr=1000)
        cand_pricier_approved = make_candidate(vendor_id="v2", part_number="STM32", manufacturer="STMicroelectronics", price_irr=5000)

        ev1 = orchestrator.evaluate_candidate(cand_cheap_unapproved, 10, request=req)
        ev2 = orchestrator.evaluate_candidate(cand_pricier_approved, 10, request=req)

        assert ev1.is_eligible is False
        assert ev2.is_eligible is True

        best = orchestrator.select_best_candidate([ev1, ev2])
        assert best is not None
        assert best.candidate.vendor_id == "v2"
        assert best.candidate.manufacturer == "STMicroelectronics"


class TestTaskA1TechnicalSpecsAndDimensions:
    """GAP-05: Generic technical parameters and physical dimensions verification."""

    def test_required_spec_missing_is_unknown_state(self, orchestrator):
        req = ProcurementRequest(
            part_number="CAP-100U",
            required_quantity=10,
            required_specs={"voltage": "25V", "tolerance": "10%"}
        )
        # Candidate only has voltage, missing tolerance
        cand = make_candidate(part_number="CAP-100U", specs={"voltage": "25V"})
        ev = orchestrator.evaluate_candidate(cand, 10, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.UNKNOWN_REQUIRED_PARAMETER
        assert "tolerance" in ev.unknown_parameters

    def test_required_spec_mismatch(self, orchestrator):
        req = ProcurementRequest(
            part_number="CAP-100U",
            required_quantity=10,
            required_specs={"voltage": "25V"}
        )
        cand = make_candidate(part_number="CAP-100U", specs={"voltage": "16V"})
        ev = orchestrator.evaluate_candidate(cand, 10, request=req)
        assert ev.is_eligible is False
        assert any("Parameter mismatch for 'voltage'" in r for r in ev.rejection_reasons)

    def test_required_dimension_missing_is_unknown_state(self, orchestrator):
        req = ProcurementRequest(
            part_number="CONN-8P",
            required_quantity=5,
            required_dimensions={"lead_pitch": "2.54mm"}
        )
        cand = make_candidate(part_number="CONN-8P", dimensions={})
        ev = orchestrator.evaluate_candidate(cand, 5, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.UNKNOWN_REQUIRED_PARAMETER
        assert "dimension:lead_pitch" in ev.unknown_parameters

    def test_dimension_mismatch_is_incompatible_dimensions(self, orchestrator):
        req = ProcurementRequest(
            part_number="CONN-8P",
            required_quantity=5,
            required_dimensions={"lead_pitch": "2.54mm"}
        )
        cand = make_candidate(part_number="CONN-8P", dimensions={"lead_pitch": "1.27mm"})
        ev = orchestrator.evaluate_candidate(cand, 5, request=req)
        assert ev.is_eligible is False
        assert ev.state == EvaluationState.INCOMPATIBLE_DIMENSIONS
        assert any("Physical dimension mismatch" in r for r in ev.rejection_reasons)


class TestTaskA1MultipleFailuresAndCriticalScenario:
    """Preservation of multiple simultaneous failures and Section 14 regression scenario."""

    def test_multiple_simultaneous_failures_preserved(self, orchestrator):
        req = ProcurementRequest(
            part_number="ABC123",
            required_quantity=10,
            manufacturer="Texas Instruments",
            package="DIP-8",
            footprint="DIP-8",
            required_dimensions={"lead_pitch": "2.54mm"}
        )
        # Candidate has: wrong MPN + wrong mfg + wrong pkg + missing footprint + missing dimension
        cand = make_candidate(
            part_number="WRONG-MPN",
            manufacturer="UnapprovedBrand",
            package="SOP-8",
            footprint=None,
            dimensions={},
        )
        ev = orchestrator.evaluate_candidate(cand, 10, request=req)
        assert ev.is_eligible is False
        # State reports top-priority failure
        assert ev.state == EvaluationState.INCOMPATIBLE_MPN
        # All rejection reasons preserved
        assert any("MPN mismatch" in r for r in ev.rejection_reasons)
        assert any("Manufacturer mismatch" in r for r in ev.rejection_reasons)
        assert any("Package mismatch" in r for r in ev.rejection_reasons)
        # All unknown params preserved
        assert "footprint" in ev.unknown_parameters
        assert "dimension:lead_pitch" in ev.unknown_parameters

    def test_critical_section_14_regression_scenario(self, orchestrator):
        """
        Requested: MPN = ABC123, Manufacturer = Texas Instruments, Package = DIP-8, Footprint = DIP-8
        Candidate 1: MPN = ABC123, Manufacturer = UnapprovedBrand, Package = DIP-8, Footprint = DIP-8, Price = 5,000
        Candidate 2: MPN = ABC123, Manufacturer = Texas Instruments, Package = DIP-8, Footprint = DIP-8, Price = 7,000
        Candidate 3: MPN = ABC123, Manufacturer = Texas Instruments, Package = SOP-8, Footprint = DIP-8, Price = 1,000

        Expected: Candidate 1 -> INCOMPATIBLE_MANUFACTURER
                  Candidate 2 -> ELIGIBLE (Selected!)
                  Candidate 3 -> INCOMPATIBLE_PACKAGE (Cannot win due to lower price)
        """
        req = ProcurementRequest(
            part_number="ABC123",
            required_quantity=10,
            manufacturer="Texas Instruments",
            package="DIP-8",
            footprint="DIP-8",
        )

        c1 = make_candidate(vendor_id="v1", part_number="ABC123", manufacturer="UnapprovedBrand", package="DIP-8", footprint="DIP-8", price_irr=5000)
        c2 = make_candidate(vendor_id="v2", part_number="ABC123", manufacturer="Texas Instruments", package="DIP-8", footprint="DIP-8", price_irr=7000)
        c3 = make_candidate(vendor_id="v3", part_number="ABC123", manufacturer="Texas Instruments", package="SOP-8", footprint="DIP-8", price_irr=1000)

        ev1 = orchestrator.evaluate_candidate(c1, 10, request=req)
        ev2 = orchestrator.evaluate_candidate(c2, 10, request=req)
        ev3 = orchestrator.evaluate_candidate(c3, 10, request=req)

        assert ev1.is_eligible is False
        assert ev1.state == EvaluationState.INCOMPATIBLE_MANUFACTURER

        assert ev2.is_eligible is True
        assert ev2.state == EvaluationState.ELIGIBLE

        assert ev3.is_eligible is False
        assert ev3.state == EvaluationState.INCOMPATIBLE_PACKAGE

        best = orchestrator.select_best_candidate([ev1, ev2, ev3])
        assert best is not None
        assert best.candidate.vendor_id == "v2"
        assert best.candidate.base_unit_price_irr == 7000
