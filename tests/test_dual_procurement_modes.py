"""
Comprehensive Unit & Integration Tests for GAP-01: Canonical Mode A Enforcement
- Mode A: Database-Aware Stock Reconciliation (Sole supported procurement workflow)
- Unsupported procurement modes: Formally rejected fail-closed across all entry points
"""

import os
import openpyxl
import pytest
from tempfile import NamedTemporaryFile

from bom_auditor import BOMAuditor, BOMItem, BOMAuditResult
from core.procurement.models import (
    ProcurementMode,
    ProcurementRequest,
    ManufacturerRule,
    ManufacturerDataState,
)
from core.procurement.bridge import ProcurementBridge
from excel_loader import ExcelDataLoader


@pytest.fixture
def sample_inventory_file():
    """Creates a temporary Inventory.xlsx file with stock and links."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory"
    ws.append(["Part Name", "Part Number", "Description", "Quantity in Stock", "Link"])
    ws.append(["STM32F103C8T6", "STM32F103C8T6", "MCU LQFP-48", "15", "https://lionelectronic.ir/product/101"])
    ws.append(["LM358N", "LM358N", "Dual OpAmp DIP-8", "5", "https://javanelec.com/item/202"])
    ws.append(["NE555P", "NE555P", "Timer DIP-8", "50", "https://roboeq.ir/product/303"])
    
    with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    wb.save(path)
    wb.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_bom_file():
    """Creates a temporary Altium BOM export file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"
    ws.append(["Designator", "Quantity", "Comment", "MPN", "Manufacturer", "Package", "Footprint", "Description"])
    ws.append(["U1", "2", "Microcontroller", "STM32F103C8T6", "STMicroelectronics", "LQFP-48", "LQFP-48", "MCU 32-bit"])
    ws.append(["U2", "10", "OpAmp", "LM358N", "Texas Instruments", "DIP-8", "DIP-8", "Dual OpAmp"])
    ws.append(["U3", "1", "Timer", "NE555P", "TI", "DIP-8", "DIP-8", "Precision Timer"])
    ws.append(["U4", "4", "Sensors", "BME280", "Bosch", "LGA-8", "LGA-8", "Pressure Sensor"])  # Not in DB
    
    with NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    wb.save(path)
    wb.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestDualProcurementModes:
    """Tests evaluating Mode A procurement reconciliation, calculation, and bridge translation."""

    @pytest.fixture(autouse=True)
    def register_test_adapters(self):
        from core.procurement.registry import VendorRegistry
        reg = VendorRegistry.get_default_registry()
        reg.register_default_adapters()
        yield
        reg.clear()

    def test_mode_a_database_aware_reconciliation(self, sample_inventory_file, sample_bom_file):
        inv_loader = ExcelDataLoader()
        inv_loader.load_file(sample_inventory_file)

        # Board multiplier = 2
        # U1 (STM32): need 2 * 2 = 4, stock = 15 -> IN_STOCK (shortage = 0)
        # U2 (LM358N): need 10 * 2 = 20, stock = 5 -> SHORTAGE (shortage = 15)
        # U3 (NE555P): need 1 * 2 = 2, stock = 50 -> IN_STOCK (shortage = 0)
        # U4 (BME280): need 4 * 2 = 8, stock = 0 -> NOT_IN_DB (shortage = 8)
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom_file,
            inventory=inv_loader,
            board_multiplier=2,
            mode=ProcurementMode.DATABASE_AWARE,
        )
        assert ok is True
        assert res is not None
        assert res.mode == ProcurementMode.DATABASE_AWARE
        assert res.total_items_count == 4
        assert res.in_stock_count == 2
        assert res.shortage_count == 1
        assert res.not_in_db_count == 1
        assert res.invalid_count == 0

        # Check U1
        u1 = next(it for it in res.items if it.designator == "U1")
        assert u1.status == "IN_STOCK"
        assert u1.total_needed_qty == 4
        assert u1.db_stock_qty == 15
        assert u1.shortage_qty == 0
        assert u1.link == "https://lionelectronic.ir/product/101"

        # Check U2
        u2 = next(it for it in res.items if it.designator == "U2")
        assert u2.status == "SHORTAGE"
        assert u2.total_needed_qty == 20
        assert u2.db_stock_qty == 5
        assert u2.shortage_qty == 15
        assert u2.link == "https://javanelec.com/item/202"
        assert u2.is_orderable is True

        # Check U4
        u4 = next(it for it in res.items if it.designator == "U4")
        assert u4.status == "NOT_IN_DB"
        assert u4.total_needed_qty == 8
        assert u4.db_stock_qty == 0
        assert u4.shortage_qty == 8
        assert u4.link == ""

    def test_unsupported_mode_rejected_fail_closed(self, sample_bom_file):
        """Unsupported procurement modes must fail-closed with ValueError."""
        with pytest.raises(ValueError, match="sole supported procurement workflow"):
            BOMAuditor.audit_bom(sample_bom_file, mode="UNSUPPORTED_MODE")
        with pytest.raises(ValueError, match="sole supported procurement workflow"):
            BOMAuditor.audit_bom(sample_bom_file, mode="INVALID_MODE")

    def test_mode_a_with_none_inventory_loader(self, sample_bom_file):
        """Mode A with None inventory treats all items as NOT_IN_DB."""
        ok, msg, res = BOMAuditor.audit_bom(
            sample_bom_file,
            inventory=None,
            board_multiplier=1,
            mode=ProcurementMode.DATABASE_AWARE,
        )
        assert ok is True
        assert res is not None
        assert res.mode == ProcurementMode.DATABASE_AWARE
        assert res.total_items_count == 4
        assert res.not_in_db_count == 4

    def test_bridge_mode_a_enforcement_and_unsupported_mode_rejection(self):
        # Mode A item with explicit URL
        item_a = {
            "part_number": "STM32F103C8T6",
            "needed_qty": 5,
            "link": "https://lionelectronic.ir/product/101",
            "mode": ProcurementMode.DATABASE_AWARE,
            "package": "LQFP-48",
            "manufacturer": "STMicroelectronics",
        }
        req_a = ProcurementBridge.item_to_request(item_a)
        assert req_a.mode == ProcurementMode.DATABASE_AWARE
        assert req_a.part_number == "STM32F103C8T6"
        assert req_a.required_quantity == 5
        assert req_a.explicit_vendor_url == "https://lionelectronic.ir/product/101"
        assert req_a.explicit_vendor_id == "vendor_lion"

        # Unsupported modes: rejected fail-closed across all invalid conventions
        for bad_mode in ("UNSUPPORTED_MODE", "INVALID_UNKNOWN", "UNKNOWN"):
            item_bad = {
                "part_number": "STM32F103C8T6",
                "total_needed_qty": 10,
                "link": "https://lionelectronic.ir/product/101",
                "mode": bad_mode,
            }
            with pytest.raises(ValueError, match="sole supported procurement workflow"):
                ProcurementBridge.item_to_request(item_bad)

            # Also ensure is_item_orderable rejects unsupported modes even with valid links
            is_ord, v_id = ProcurementBridge.is_item_orderable(item_bad)
            assert is_ord is False
            assert v_id is None
