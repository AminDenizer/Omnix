"""
Omnix Test Suite — Phase 7 Independent Page Counts & Phase 8 Order Action Placement
Governing Specifications:
- Phase 7 Independent Page Counts (Total Record & Match Record isolation)
- Phase 8 Order Action Placement (Order button on Component Inventory, removed from Assembly View)
"""

import os
import pytest
from PyQt6.QtWidgets import QApplication
from unittest.mock import patch

from core.inventory.models import InventoryProduct
from core.inventory.repository import SqliteInventoryRepository
from ui.main_window import MainWindow


@pytest.fixture
def repo_with_diverse_components(tmp_path):
    """Creates a repo where group count (1) is strictly different from component count (3)."""
    db_p = tmp_path / "counts_test.db"
    repo = SqliteInventoryRepository(str(db_p))
    repo.load()

    # 3 physical components belonging to the SAME assembly group (Capacitor Ceramic 100nF 0603 SMD_0603)
    repo.create_component(
        InventoryProduct(
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=100,
        )
    )
    repo.create_component(
        InventoryProduct(
            manufacturer="TDK",
            mpn="C1608X7R1H104K080AA",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=200,
        )
    )
    repo.create_component(
        InventoryProduct(
            manufacturer="Taiyo Yuden",
            mpn="EMK107B7104KA-T",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=300,
        )
    )

    return repo


class TestIndependentPageCountsAndOrderPlacement:
    """Verifies that Assembly View and Component Inventory never leak counts or order actions."""

    def test_independent_counts_and_isolation(self, qapp, repo_with_diverse_components):
        repo = repo_with_diverse_components
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file=repo.file_path, repository=repo)
            qapp.processEvents()

            try:
                # 1. Component Inventory is active by default (Sub-tab 1)
                assert win.inventory_subtabs.currentIndex() == 1
                assert "Total Records: 3" in win.stats_ribbon.stat_total_rows.text()
                assert "Matches: 3" in win.stats_ribbon.stat_filtered_rows.text()
                assert not win.stats_ribbon.order_shortages_btn.isHidden()
                assert win.stats_ribbon.stat_incomplete_btn.isHidden()

                # Filter Component Inventory by 'Murata'
                win.component_search_input.setText("Murata")
                qapp.processEvents()
                assert "Total Records: 3" in win.stats_ribbon.stat_total_rows.text()
                assert "Matches: 1" in win.stats_ribbon.stat_filtered_rows.text()

                # 2. Switch to Sub-tab 0 (Assembly View)
                win.inventory_subtabs.setCurrentIndex(0)
                qapp.processEvents()
                # Assembly View has exactly 1 group (Capacitor Ceramic 100nF 0603)
                assert "Total Records: 1" in win.stats_ribbon.stat_total_rows.text()
                assert "Matches: 1" in win.stats_ribbon.stat_filtered_rows.text()
                # Order button MUST be hidden on Assembly View per Phase 8
                assert win.stats_ribbon.order_shortages_btn.isHidden()
                assert not win.stats_ribbon.stat_incomplete_btn.isHidden()

                # Search box in Assembly View must be independent
                assert win.search_input.text() == ""
                win.search_input.setText("NonExistent")
                qapp.processEvents()
                assert "Matches: 0" in win.stats_ribbon.stat_filtered_rows.text()

                # 3. Switch back to Sub-tab 1 (Component Inventory)
                win.inventory_subtabs.setCurrentIndex(1)
                qapp.processEvents()
                # Component search 'Murata' was preserved, matches must be 1, total 3 (no leakage from Assembly View!)
                assert "Total Records: 3" in win.stats_ribbon.stat_total_rows.text()
                assert "Matches: 1" in win.stats_ribbon.stat_filtered_rows.text()
                # Order button must be visible again
                assert not win.stats_ribbon.order_shortages_btn.isHidden()
                assert win.stats_ribbon.stat_incomplete_btn.isHidden()

                # Clear component search
                win.component_search_input.setText("")
                qapp.processEvents()
                assert "Matches: 3" in win.stats_ribbon.stat_filtered_rows.text()

            finally:
                win._is_force_closing = True
                win.close()
