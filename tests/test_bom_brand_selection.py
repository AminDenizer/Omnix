"""
Comprehensive Unit Tests for Manufacturer Rules and Brand Selection Engine
Governing GAPs: GAP-06 (Manufacturer Constraint Engine) + GAP-16 (Altium Contract Ingestion)
"""

import pytest
import openpyxl
import os
from tempfile import NamedTemporaryFile

from bom_auditor import BOMAuditor, BOMItem
from core.models import ProductReference
from core.procurement.models import (
    ProcurementMode,
    ProcurementRequest,
    VendorProcurementCandidate,
    EvaluationState,
    ManufacturerRule,
    ManufacturerDataState,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator


class TestManufacturerRuleDataStateSeparation:
    """Verifies strict separation between ManufacturerRule and ManufacturerDataState."""

    def test_mfg_rule_enum_values(self):
        assert ManufacturerRule.EXACT == "EXACT"
        assert ManufacturerRule.APPROVED_LIST == "APPROVED_LIST"
        assert ManufacturerRule.ANY == "ANY"

    def test_mfg_data_state_enum_values(self):
        assert ManufacturerDataState.EXPLICIT_ANY == "EXPLICIT_ANY"
        assert ManufacturerDataState.EXPLICIT_BRAND_RULE == "EXPLICIT_BRAND_RULE"
        assert ManufacturerDataState.MISSING_MANUFACTURER_DATA == "MISSING_MANUFACTURER_DATA"

    def test_bom_ingestion_exact_rule(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Designator", "Quantity", "MPN", "Manufacturer", "Manufacturer_Rule"])
        ws.append(["U1", "1", "STM32F103C8T6", "STMicroelectronics", "EXACT"])

        with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        wb.save(path)
        wb.close()

        try:
            ok, msg, res = BOMAuditor.audit_bom(path, inventory=None, mode=ProcurementMode.DATABASE_AWARE)
            assert ok is True
            it = res.items[0]
            assert it.manufacturer_rule == ManufacturerRule.EXACT
            assert it.mfg_data_state == ManufacturerDataState.EXPLICIT_BRAND_RULE
            assert it.allowed_manufacturers == ["STMicroelectronics"]
            assert it.is_manufacturer_any is False
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_bom_ingestion_approved_list_rule(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Designator", "Quantity", "MPN", "Approved_Manufacturers"])
        ws.append(["U1", "1", "LM358", "TI, STMicroelectronics, ON Semi"])

        with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        wb.save(path)
        wb.close()

        try:
            ok, msg, res = BOMAuditor.audit_bom(path, inventory=None, mode=ProcurementMode.DATABASE_AWARE)
            assert ok is True
            it = res.items[0]
            assert it.manufacturer_rule == ManufacturerRule.APPROVED_LIST
            assert it.mfg_data_state == ManufacturerDataState.EXPLICIT_BRAND_RULE
            assert it.allowed_manufacturers == ["TI", "STMicroelectronics", "ON Semi"]
            assert it.is_manufacturer_any is False
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_bom_ingestion_explicit_any_rule(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Designator", "Quantity", "MPN", "Manufacturer", "Manufacturer_Rule"])
        ws.append(["R1", "10", "RC0805", "ANY", "ANY"])

        with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        wb.save(path)
        wb.close()

        try:
            ok, msg, res = BOMAuditor.audit_bom(path, inventory=None, mode=ProcurementMode.DATABASE_AWARE)
            assert ok is True
            it = res.items[0]
            assert it.manufacturer_rule == ManufacturerRule.ANY
            assert it.mfg_data_state == ManufacturerDataState.EXPLICIT_ANY
            assert it.allowed_manufacturers is None
            assert it.is_manufacturer_any is True
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_bom_ingestion_missing_manufacturer_data(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Designator", "Quantity", "MPN"])
        ws.append(["C1", "5", "GRM188R71H104KA93D"])

        with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        wb.save(path)
        wb.close()

        try:
            ok, msg, res = BOMAuditor.audit_bom(path, inventory=None, mode=ProcurementMode.DATABASE_AWARE)
            assert ok is True
            it = res.items[0]
            assert it.manufacturer_rule == ManufacturerRule.ANY
            assert it.mfg_data_state == ManufacturerDataState.EXPLICIT_ANY
            assert it.allowed_manufacturers is None
            assert it.is_manufacturer_any is True
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestCandidateEvaluationWithBrandRules:
    """Tests evaluating vendor candidates against different brand rules."""

    def test_candidate_exact_brand_match(self):
        req = ProcurementRequest(
            part_number="STM32F103C8T6",
            required_quantity=10,
            manufacturer="STMicroelectronics",
            allowed_manufacturers=["STMicroelectronics"],
        )
        cand_match = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="STM32F103C8T6",
            product_ref=ProductReference("vendor_lion", "101", "https://lion.ir/101"),
            manufacturer="STMicroelectronics",
            in_stock=True,
            stock_quantity=50,
            can_order=True,
            base_unit_price_irr=150000,
        )
        cand_mismatch = VendorProcurementCandidate(
            vendor_id="vendor_javan",
            part_number="STM32F103C8T6",
            product_ref=ProductReference("vendor_javan", "202", "https://javan.ir/202"),
            manufacturer="Generic / Unknown",
            in_stock=True,
            stock_quantity=50,
            can_order=True,
            base_unit_price_irr=120000,
        )

        eval_match = UniversalProcurementOrchestrator.evaluate_candidate(cand_match, req)
        assert eval_match.is_eligible is True
        assert eval_match.evaluation_state == EvaluationState.ELIGIBLE

        eval_mismatch = UniversalProcurementOrchestrator.evaluate_candidate(cand_mismatch, req)
        assert eval_mismatch.is_eligible is False
        assert eval_mismatch.evaluation_state == EvaluationState.INCOMPATIBLE_MANUFACTURER

    def test_candidate_approved_list_match(self):
        req = ProcurementRequest(
            part_number="LM358",
            required_quantity=5,
            allowed_manufacturers=["Texas Instruments", "STMicroelectronics"],
        )
        cand_ti = VendorProcurementCandidate(
            vendor_id="vendor_lion",
            part_number="LM358",
            product_ref=ProductReference("vendor_lion", "1", "https://lion.ir/1"),
            manufacturer="Texas Instruments",
            in_stock=True,
            stock_quantity=20,
            can_order=True,
            base_unit_price_irr=20000,
        )
        cand_st = VendorProcurementCandidate(
            vendor_id="vendor_javan",
            part_number="LM358",
            product_ref=ProductReference("vendor_javan", "2", "https://javan.ir/2"),
            manufacturer="STMicroelectronics",
            in_stock=True,
            stock_quantity=20,
            can_order=True,
            base_unit_price_irr=18000,
        )
        cand_other = VendorProcurementCandidate(
            vendor_id="vendor_roboeq",
            part_number="LM358",
            product_ref=ProductReference("vendor_roboeq", "3", "https://roboeq.ir/3"),
            manufacturer="Unbranded",
            in_stock=True,
            stock_quantity=20,
            can_order=True,
            base_unit_price_irr=10000,
        )

        assert UniversalProcurementOrchestrator.evaluate_candidate(cand_ti, req).is_eligible is True
        assert UniversalProcurementOrchestrator.evaluate_candidate(cand_st, req).is_eligible is True
        eval_other = UniversalProcurementOrchestrator.evaluate_candidate(cand_other, req)
        assert eval_other.is_eligible is False
        assert eval_other.evaluation_state == EvaluationState.INCOMPATIBLE_MANUFACTURER

    def test_candidate_explicit_any_accepts_all_brands(self):
        req = ProcurementRequest(
            part_number="NE555",
            required_quantity=10,
            is_manufacturer_any=True,
        )
        cand = VendorProcurementCandidate(
            vendor_id="vendor_roboeq",
            part_number="NE555",
            product_ref=ProductReference("vendor_roboeq", "4", "https://roboeq.ir/4"),
            manufacturer="AnyBrand Ltd",
            in_stock=True,
            stock_quantity=100,
            can_order=True,
            base_unit_price_irr=15000,
        )
        eval_res = UniversalProcurementOrchestrator.evaluate_candidate(cand, req)
        assert eval_res.is_eligible is True
        assert eval_res.evaluation_state == EvaluationState.ELIGIBLE
