"""
Omnix Test Suite — Phase 6 BOM Upload Link Statuses and Blank Link Filtering
Governing Specification: Phase 6 BOM Upload Link Statuses
"""

import os
import openpyxl
import pytest
from PyQt6.QtGui import QColor

from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter
from bom_auditor import BOMAuditor, ProcurementMode
from ui.widgets.bom_audit_widget import BOMAuditWidget


class MockLionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lion.ir"


@pytest.fixture(autouse=True)
def setup_mock_vendor():
    reg = VendorRegistry.get_default_registry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionAdapter,
        domains=["lion.ir"],
        display_name="Lion",
        enabled=True,
        activate=True,
    )
    yield
    reg.unregister_adapter("vendor_lion")


@pytest.fixture
def test_repo_with_links(tmp_path):
    """Repo with: 1 valid link item, 1 blank link item, 1 item with insufficient stock."""
    db_p = tmp_path / "bom_status_test.db"
    repo = SqliteInventoryRepository(str(db_p))
    repo.load()

    # 1. Component with valid link
    repo.create_component(
        InventoryProduct(
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=10,
        ),
        supplier_links=[SupplierLink(vendor_id="vendor_lion", vendor_label="Lion", url="https://lion.ir/part1")]
    )

    # 2. Component in DB but with BLANK store link
    repo.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0805FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0805",
            footprint="SMD_0805",
            value="10k",
            quantity_in_stock=5, # Shortage if 20 needed
        )
    )

    return repo


@pytest.fixture
def sample_bom_file(tmp_path):
    """BOM containing: 1 valid link part, 1 blank link part, 1 not-in-db part."""
    bom_p = tmp_path / "sample_bom.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"
    ws.append(["Designator", "Part Number", "Description", "Footprint", "Quantity", "Manufacturer"])
    ws.append(["C1", "GRM188R71H104KA93D", "100nF Ceramic", "0603", 50, "Murata"]) # Shortage of 40, valid link
    ws.append(["R1", "RC0805FR-0710KL", "10k Resistor", "0805", 20, "Yageo"])      # Shortage of 15, blank link
    ws.append(["U1", "STM32F407VGT6", "ARM Cortex-M4", "LQFP100", 2, "STMicroelectronics"]) # NOT IN DB
    wb.save(str(bom_p))
    wb.close()
    return str(bom_p)


class TestBOMUploadLinkStatuses:
    """Verifies that BOM items clearly distinguish Valid Link, Blank Link, and Not in DB."""

    def test_audit_distinguishes_valid_blank_and_not_in_db(self, test_repo_with_links, sample_bom_file):
        ok, msg, res = BOMAuditor.audit_bom(sample_bom_file, inventory=test_repo_with_links)
        assert ok is True
        assert res.total_items_count == 3
        assert res.shortage_count == 2
        assert res.not_in_db_count == 1
        assert res.blank_link_count == 1

        items = res.items
        # Item 0: C1 -> Shortage, valid link
        assert items[0].part_number == "GRM188R71H104KA93D"
        assert items[0].status == "SHORTAGE"
        assert items[0].is_orderable is True

        # Item 1: R1 -> Shortage, BLANK LINK (Not 'NOT_IN_DB'!)
        assert items[1].part_number == "RC0805FR-0710KL"
        assert items[1].status == "SHORTAGE"
        assert items[1].is_orderable is False
        assert (not items[1].link or not items[1].link.strip())
        assert items[1].status != "NOT_IN_DB", "Missing link must NOT be labeled as NOT_IN_DB!"

        # Item 2: U1 -> NOT IN DB
        assert items[2].part_number == "STM32F407VGT6"
        assert items[2].status == "NOT_IN_DB"

    def test_widget_orange_styling_and_blank_link_filtering(self, qapp, test_repo_with_links, sample_bom_file):
        widget = BOMAuditWidget(inventory_loader=test_repo_with_links)
        widget.load_bom_file(sample_bom_file)

        # Verify KPI counts
        assert widget.pill_total.text() == "Total BOM Items: 3"
        assert widget.pill_shortage.text() == "⚠️ Shortages: 2"
        assert widget.pill_not_in_db.text() == "🔴 Not in Database: 1"
        assert widget.pill_missing_link.text() == "⚠️ Missing Links: 1"

        # Row 1 is R1 (blank link): verify orange visual treatment (#f97316)
        status_item = widget.table.item(1, 0)
        assert "BLANK LINK" in status_item.text()
        assert status_item.foreground().color() == QColor("#f97316")

        store_link_item = widget.table.item(1, 9)
        assert "Blank Store Link" in store_link_item.text()
        assert store_link_item.foreground().color() == QColor("#f97316")

        # Row 2 is U1 (not in DB): verify red treatment
        not_in_db_item = widget.table.item(2, 0)
        assert "NOT IN DB" in not_in_db_item.text()
        assert not_in_db_item.foreground().color() == QColor("#f87171")

        # Test clicking missing link pill triggers filtering
        assert widget.table.isRowHidden(0) is False
        assert widget.table.isRowHidden(1) is False
        assert widget.table.isRowHidden(2) is False

        # Toggle filter ON
        widget.pill_missing_link.click()
        assert widget.table.isRowHidden(0) is True  # C1 hidden
        assert widget.table.isRowHidden(1) is False # R1 (blank link) VISIBLE
        assert widget.table.isRowHidden(2) is True  # U1 hidden

        # Toggle filter OFF
        widget.pill_missing_link.click()
        assert widget.table.isRowHidden(0) is False
        assert widget.table.isRowHidden(1) is False
        assert widget.table.isRowHidden(2) is False
