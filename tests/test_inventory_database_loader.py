"""
Unit & Contract Tests for Omnix Inventory Database Loader & Repository
Governing Document: Phase 1 Master Architecture Specification
"""

import os
import hashlib
import tempfile
import pytest
import openpyxl

from core.inventory.models import (
    InventoryProduct,
    StockPolicyGroup,
    normalize_package,
    build_group_key,
)
from core.inventory.loader import (
    InventoryDatabaseLoader,
    MissingWorksheetError,
    WorkbookAccessError,
    resolve_inventory_database_path,
)
from core.inventory.repository import (
    ExcelInventoryRepository,
)


@pytest.fixture
def sample_workbook_path(tmp_path):
    """Create a temporary valid workbook with Stock Policy and Inventory sheets."""
    wb_path = str(tmp_path / "TestInventory.xlsm")
    wb = openpyxl.Workbook()

    # Sheet 1: Stock Policy (index 0)
    ws_policy = wb.active
    ws_policy.title = "Stock Policy"
    ws_policy.append([
        "Category", "Type/Technology", "Value", "Package", "Footprint",
        "Total Quantity in Stock", "Min Stock", "Target Stock", "Description", "Group Key (System)"
    ])
    ws_policy.append([
        "Resistor", "Thick Film", "10k", "0603", "SMD_0603",
        150, 100, 300, "10k 1% 0603 Resistor", "Resistor|Thick Film|10k|0603|SMD_0603"
    ])
    ws_policy.append([
        "Capacitor", "X7R", "100nF", "0603", "SMD_0603",
        50, 100, 200, "100nF 50V MLCC", "Capacitor|X7R|100nF|0603|SMD_0603"
    ])

    # Sheet 2: Inventory (index 1)
    ws_inv = wb.create_sheet(title="Inventory")
    ws_inv.append([
        "Manufacturer", "MPN", "Category", "Type/Technology", "Package",
        "Footprint", "Value", "Description", "Quantity in Stock", "Purchase Link"
    ])
    # Product 1: package given as numeric 603
    ws_inv.append([
        "Yageo", "RC0603FR-0710KL", "Resistor", "Thick Film", 603,
        "SMD_0603", "10k", "10k Resistor", 100, "https://lionelectronic.ir/p/1"
    ])
    # Product 2: alternative part matching same group, package string "0603"
    ws_inv.append([
        "Samsung", "RC1608F103CS", "Resistor", "Thick Film", "0603",
        "SMD_0603", "10k", "10k Resistor Alt", 50, "https://javanelec.com/p/2"
    ])
    # Product 3: capacitor part
    ws_inv.append([
        "Murata", "GRM188R71H104KA93D", "Capacitor", "X7R", "0603",
        "SMD_0603", "100nF", "100nF Cap", 50, "https://lionelectronic.ir/p/3"
    ])

    # Sheet 3: Unrelated extra sheet
    wb.create_sheet(title="Reference Data")

    wb.save(wb_path)
    wb.close()
    return wb_path


class TestPackageNormalizationAndKey:
    """Test package normalization and canonical group key generation."""

    def test_numeric_package_normalization(self):
        assert normalize_package(603) == "0603"
        assert normalize_package("603") == "0603"
        assert normalize_package("0603") == "0603"
        assert normalize_package(805) == "0805"
        assert normalize_package("805") == "0805"
        assert normalize_package(402) == "0402"

    def test_textual_and_none_package(self):
        assert normalize_package("D Case") == "D Case"
        assert normalize_package("LQFP-100") == "LQFP-100"
        assert normalize_package(None) == ""
        assert normalize_package("") == ""

    def test_canonical_group_key_order(self):
        k = build_group_key("Resistor", "Thick Film", "10k", 603, "SMD_0603")
        assert k == "Resistor|Thick Film|10k|0603|SMD_0603"


class TestInventoryDatabaseLoader:
    """Test strictly read-only loading and verification of workbook data."""

    def test_explicit_named_sheet_reading_and_matching(self, sample_workbook_path):
        loader = InventoryDatabaseLoader()
        groups, products, warnings = loader.load_workbook(sample_workbook_path)

        assert len(groups) == 2
        assert len(products) == 3

        # Resistor group: 2 matched products (Yageo and Samsung)
        res_grp = next(g for g in groups if g.category == "Resistor")
        assert res_grp.package == "0603"
        assert res_grp.current_stock == 150
        assert res_grp.min_stock == 100
        assert res_grp.target_stock == 300
        assert res_grp.is_low_stock is False
        assert len(res_grp.products) == 2

        mpns = {p.mpn for p in res_grp.products}
        assert mpns == {"RC0603FR-0710KL", "RC1608F103CS"}

        # Capacitor group: 1 matched product
        cap_grp = next(g for g in groups if g.category == "Capacitor")
        assert cap_grp.current_stock == 50
        assert cap_grp.min_stock == 100
        assert cap_grp.is_low_stock is True  # 50 < 100
        assert len(cap_grp.products) == 1
        assert cap_grp.products[0].mpn == "GRM188R71H104KA93D"

    def test_missing_sheet_raises_error(self, tmp_path):
        bad_wb_path = str(tmp_path / "BadWorkbook.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "OnlySheet"
        wb.save(bad_wb_path)
        wb.close()

        loader = InventoryDatabaseLoader()
        with pytest.raises(MissingWorksheetError) as exc_info:
            loader.load_workbook(bad_wb_path)
        assert "Stock Policy" in str(exc_info.value)

    def test_worksheet_order_independence(self, tmp_path):
        """Ensure loading succeeds even if Inventory is first and Stock Policy is second."""
        rev_wb_path = str(tmp_path / "Reversed.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: Inventory first
        ws_inv = wb.active
        ws_inv.title = "Inventory"
        ws_inv.append(["Manufacturer", "MPN", "Category", "Type/Technology", "Package", "Footprint", "Value", "Description", "Quantity in Stock", "Purchase Link"])
        ws_inv.append(["BrandA", "MPN1", "Diode", "Schottky", "SOD-123", "SOD123", "1A", "Diode 1A", 20, "https://test.com/d1"])

        # Sheet 2: Stock Policy second
        ws_pol = wb.create_sheet(title="Stock Policy")
        ws_pol.append(["Category", "Type/Technology", "Value", "Package", "Footprint", "Total Quantity in Stock", "Min Stock", "Target Stock", "Description", "Group Key (System)"])
        ws_pol.append(["Diode", "Schottky", "1A", "SOD-123", "SOD123", 20, 10, 50, "Diode group", "Diode|Schottky|1A|SOD-123|SOD123"])

        wb.save(rev_wb_path)
        wb.close()

        loader = InventoryDatabaseLoader()
        groups, products, _ = loader.load_workbook(rev_wb_path)
        assert len(groups) == 1
        assert len(products) == 1
        assert len(groups[0].products) == 1
        assert groups[0].products[0].mpn == "MPN1"

    def test_missing_and_unusable_required_values(self, tmp_path):
        """Verify handling of missing/unusable formula totals and thresholds."""
        wb_path = str(tmp_path / "UnusableValues.xlsx")
        wb = openpyxl.Workbook()

        ws_pol = wb.active
        ws_pol.title = "Stock Policy"
        ws_pol.append(["Category", "Type/Technology", "Value", "Package", "Footprint", "Total Quantity in Stock", "Min Stock", "Target Stock", "Description", "Group Key (System)"])
        # Row with missing current_stock and invalid min_stock
        ws_pol.append(["Resistor", "Thick Film", "1k", "0805", "SMD_0805", None, "invalid_number", 50, "1k Resistor", ""])

        ws_inv = wb.create_sheet(title="Inventory")
        ws_inv.append(["Manufacturer", "MPN", "Category", "Type/Technology", "Package", "Footprint", "Value", "Description", "Quantity in Stock", "Purchase Link"])
        ws_inv.append(["Yageo", "RC0805-1K", "Resistor", "Thick Film", "0805", "SMD_0805", "1k", "1k", 10, None])

        wb.save(wb_path)
        wb.close()

        loader = InventoryDatabaseLoader()
        groups, products, warnings = loader.load_workbook(wb_path)
        assert len(groups) == 1
        grp = groups[0]

        assert grp.current_stock is None
        assert grp.min_stock is None
        assert grp.target_stock == 50
        assert grp.is_complete is False
        assert "current_stock" in grp.missing_fields
        assert "min_stock" in grp.missing_fields
        assert len(warnings) >= 2

    def test_workbook_immutability(self, sample_workbook_path):
        """Verify that loading does not modify or save the source workbook."""
        with open(sample_workbook_path, "rb") as f:
            hash_before = hashlib.sha256(f.read()).hexdigest()

        loader = InventoryDatabaseLoader()
        loader.load_workbook(sample_workbook_path)

        with open(sample_workbook_path, "rb") as f:
            hash_after = hashlib.sha256(f.read()).hexdigest()

        assert hash_before == hash_after, "Source workbook was mutated by loader!"


class TestExcelInventoryRepository:
    """Test repository abstraction over Excel workbook."""

    def test_repository_interface_and_queries(self, sample_workbook_path):
        repo = ExcelInventoryRepository()
        ok, msg = repo.load(sample_workbook_path)

        assert ok is True
        assert repo.is_loaded is True
        assert len(repo.get_all_groups()) == 2
        assert len(repo.get_all_products()) == 3

        res_group_key = "Resistor|Thick Film|10k|0603|SMD_0603"
        grp = repo.get_group(res_group_key)
        assert grp is not None
        assert grp.category == "Resistor"

        prods = repo.get_products_for_group(res_group_key)
        assert len(prods) == 2


class TestRealInventoryWorkbookIntegration:
    """Integration test with the actual repository workbook autom/atom/Inventory.xlsm."""

    def test_real_workbook_loads_expected_13_groups_and_19_products(self):
        real_path = resolve_inventory_database_path()
        if not os.path.isfile(real_path):
            pytest.skip(f"Real workbook not found at {real_path}")

        with open(real_path, "rb") as f:
            hash_before = hashlib.sha256(f.read()).hexdigest()

        repo = ExcelInventoryRepository()
        ok, msg = repo.load(real_path)

        assert ok is True, f"Failed to load real workbook: {msg}"
        groups = repo.get_all_groups()
        products = repo.get_all_products()

        # Verified schema assertions
        assert len(groups) == 13, f"Expected 13 policy groups, got {len(groups)}"
        assert len(products) == 19, f"Expected 19 physical products, got {len(products)}"

        # Verify all products have exactly one purchase link or None, and valid MPN
        for p in products:
            assert p.mpn, "Product missing MPN"
            assert p.group_key, "Product missing group_key"

        # Verify that 100% of products are matched to a group
        matched_count = sum(len(g.products) for g in groups)
        assert matched_count == 19, f"Expected 19 matched products across groups, got {matched_count}"

        # Verify package normalization for 603
        norm_603_groups = [g for g in groups if g.package == "0603"]
        assert len(norm_603_groups) > 0

        # Verify hash immutability on real file
        with open(real_path, "rb") as f:
            hash_after = hashlib.sha256(f.read()).hexdigest()
        assert hash_before == hash_after, "Real Inventory.xlsm was mutated!"
