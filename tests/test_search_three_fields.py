"""
Omnix Automated Tests: Strict Three-Field Search Filtering
Governing Document: Mode A Search Strictness Specification (Section 4)

Verifies:
1. Search strictly filters on:
   - Manufacturer
   - Part Number (MPN)
   - Value
2. Explicitly excludes:
   - Package
   - Footprint
   - Description
   - Category
   - Type / Technology
   - Purchase Links & URLs
   - Stock Quantities & Thresholds
3. Case-insensitive substring matching with whitespace normalization.
4. Applied to both Mode A search boxes:
   - Assembly & Stock View (_filter_and_render)
   - Component Inventory View (_render_inventory_components_table)
5. Search input placeholder text is exactly "Search by MPN, Manufacturer, or Value...".
"""

import pytest
from unittest.mock import patch
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow
from core.inventory.models import InventoryProduct, StockPolicyGroup


@pytest.fixture
def win(qapp):
    with patch.object(MainWindow, "_check_startup_shortages"):
        w = MainWindow()
        w.show()
        qapp.processEvents()
        yield w
        w._is_force_closing = True
        w.close()


class TestSearchThreeFields:
    """Tests strictly verifying search matching across the 3 allowed fields and rejection of others."""

    def test_search_placeholders(self, win):
        """Verifies placeholder text on both search bars matches specification."""
        assert win.filter_bar.search_input.placeholderText() == "Search by MPN, Manufacturer, or Value..."
        assert win.component_search_input.placeholderText() == "Search by MPN, Manufacturer, or Value..."

    def test_assembly_view_mpn_match(self, win):
        """Verifies partial and case-insensitive MPN search matches in Assembly & Stock view."""
        # Search by partial MPN
        win.search_query = "stm32"
        win._filter_and_render()
        assert len(win.current_filtered_groups) > 0
        for group in win.current_filtered_groups:
            mpns = [p.mpn.lower() for p in group.products if p.mpn]
            mfrs = [p.manufacturer.lower() for p in group.products if p.manufacturer]
            vals = [group.value.lower()] + [p.value.lower() for p in group.products if p.value]
            assert any("stm32" in m for m in mpns) or any("stm32" in m for m in mfrs) or any("stm32" in v for v in vals)

    def test_assembly_view_manufacturer_match(self, win):
        """Verifies Manufacturer matching with case insensitivity and whitespace normalization."""
        win.search_query = "   mUrAtA   "
        win._filter_and_render()
        assert len(win.current_filtered_groups) > 0
        for group in win.current_filtered_groups:
            mfrs = [p.manufacturer.lower() for p in group.products if p.manufacturer]
            assert any("murata" in m for m in mfrs)

    def test_assembly_view_value_match(self, win):
        """Verifies Value matching in Assembly & Stock view."""
        win.search_query = "100nF"
        win._filter_and_render()
        assert len(win.current_filtered_groups) > 0
        for group in win.current_filtered_groups:
            vals = [group.value.lower()] + [p.value.lower() for p in group.products if p.value]
            assert any("100nf" in v for v in vals)

    def test_assembly_view_strictly_excludes_package_footprint_description_category_type(self, win):
        """
        Injects a synthetic test group with unique Package, Footprint, Description, Category, Type,
        and verifies none of those fields can match the search query.
        """
        synthetic_product = InventoryProduct(
            manufacturer="AlphaCorp",
            mpn="ALPHA-100",
            category="SuperCapacitors",
            type_technology="PolymerElectrolyte",
            package="PKG_RARE_999",
            footprint="FP_ULTRA_888",
            value="47uF",
            description="High temperature automotive grade",
            quantity_in_stock=10,
        )
        synthetic_group = StockPolicyGroup(
            category="SuperCapacitors",
            type_technology="PolymerElectrolyte",
            value="47uF",
            package="PKG_RARE_999",
            footprint="FP_ULTRA_888",
            current_stock=10,
            min_stock=5,
            target_stock=20,
            description="Synthetic group",
            products=(synthetic_product,),
        )

        all_groups = list(win.inventory_repo.get_all_groups()) + [synthetic_group]
        with patch.object(win.inventory_repo, "get_all_groups", return_value=all_groups):
            # 1. Matching Manufacturer succeeds
            win.search_query = "AlphaCorp"
            win._filter_and_render()
            assert any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 2. Matching MPN succeeds
            win.search_query = "ALPHA-100"
            win._filter_and_render()
            assert any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 3. Matching Value succeeds
            win.search_query = "47uF"
            win._filter_and_render()
            assert any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 4. Searching for Package MUST NOT match
            win.search_query = "PKG_RARE_999"
            win._filter_and_render()
            assert not any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 5. Searching for Footprint MUST NOT match
            win.search_query = "FP_ULTRA_888"
            win._filter_and_render()
            assert not any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 6. Searching for Description MUST NOT match
            win.search_query = "automotive"
            win._filter_and_render()
            assert not any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 7. Searching for Category MUST NOT match
            win.search_query = "SuperCapacitors"
            win._filter_and_render()
            assert not any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

            # 8. Searching for Technology MUST NOT match
            win.search_query = "PolymerElectrolyte"
            win._filter_and_render()
            assert not any(g.package == "PKG_RARE_999" for g in win.current_filtered_groups)

    def test_component_table_strictly_filters_three_fields(self, win):
        """Verifies that Component Inventory table filters strictly on MFR, MPN, Value and excludes others."""
        synthetic_product = InventoryProduct(
            id=9999,
            manufacturer="BetaMfr",
            mpn="BETA-9000",
            category="SensorIC",
            type_technology="MEMSAccelerometer",
            package="LGA-14-SPECIAL",
            footprint="FP-LGA14-CUSTOM",
            value="3.3V-RANGE",
            description="Ultra low power MEMS sensor",
            quantity_in_stock=50,
            purchase_link="https://lionelectronic.ir/p/beta-mems",
        )
        all_prods = list(win.inventory_repo.get_all_products()) + [synthetic_product]
        with patch.object(win.inventory_repo, "get_all_products", return_value=all_prods):
            # Allowed fields:
            win.component_search_query = "beta-9000"
            win._render_inventory_components_table()
            assert any(c.mpn == "BETA-9000" for c in win._current_inventory_components)

            win.component_search_query = "BetaMfr"
            win._render_inventory_components_table()
            assert any(c.mpn == "BETA-9000" for c in win._current_inventory_components)

            win.component_search_query = "3.3V-RANGE"
            win._render_inventory_components_table()
            assert any(c.mpn == "BETA-9000" for c in win._current_inventory_components)

            # Disallowed fields MUST NOT MATCH:
            for forbidden_query in [
                "LGA-14-SPECIAL",      # Package
                "FP-LGA14-CUSTOM",     # Footprint
                "MEMSAccelerometer",   # Technology
                "SensorIC",            # Category
                "Ultra low power",     # Description
                "lionelectronic.ir",   # URL
            ]:
                win.component_search_query = forbidden_query
                win._render_inventory_components_table()
                assert not any(c.mpn == "BETA-9000" for c in win._current_inventory_components), (
                    f"Forbidden query '{forbidden_query}' erroneously matched component!"
                )
