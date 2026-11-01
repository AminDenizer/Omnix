import os
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox

from ui.main_window import MainWindow
from core.inventory import resolve_inventory_database_path


@pytest.fixture
def main_window(qapp):
    db_path = resolve_inventory_database_path()
    with patch.object(MainWindow, "_check_startup_shortages"):
        win = MainWindow(default_file=db_path)
        win.show()
        qapp.processEvents()
        yield win
        win._is_force_closing = True
        win.close()


class TestTab1InventoryView:
    """Test suite verifying Phase 1 Read-Only Inventory and Stock Policy view."""

    def test_database_loads_authoritative_groups(self, main_window):
        win = main_window
        assert win.inventory_repo.is_loaded is True
        assert len(win.inventory_repo.get_all_groups()) == 13

        # Check top table (Stock Policy Groups / Assembly & Stock)
        assert win.table.rowCount() == 13
        assert win.table.columnCount() == 7

        expected_headers = [
            "Category", "Type / Technology", "Value", "Package", "Footprint",
            "Total In Stock", "Matched Products"
        ]
        actual_headers = [win.table.horizontalHeaderItem(c).text() for c in range(win.table.columnCount())]
        assert actual_headers == expected_headers

        # Check dedicated Component Inventory table
        assert hasattr(win, "inventory_components_table")
        assert win.inventory_components_table.columnCount() == 14

    def test_group_selection_updates_associated_products(self, main_window):
        win = main_window

        # Select first row
        win.table.selectRow(0)
        first_group = win.current_filtered_groups[0]
        assert win.products_table.rowCount() == len(first_group.products)

        # Find 100nF group (which has 4 products in Inventory.xlsm)
        target_idx = None
        for idx, g in enumerate(win.current_filtered_groups):
            if g.value == "100nF" and g.package == "0603":
                target_idx = idx
                break

        assert target_idx is not None
        win.table.selectRow(target_idx)
        group_100nf = win.current_filtered_groups[target_idx]
        assert len(group_100nf.products) == 3
        assert win.products_table.rowCount() == 3

        # Verify product row content
        first_prod = group_100nf.products[0]
        assert win.products_table.item(0, 1).text() == first_prod.manufacturer
        assert win.products_table.item(0, 2).text() == first_prod.mpn
        assert win.products_table.item(0, 4).text() == str(first_prod.quantity_in_stock)

    def test_search_filtering_groups_and_products(self, main_window):
        win = main_window

        # Search for "100nF"
        win._on_search_changed("100nF")
        assert len(win.current_filtered_groups) >= 1
        for g in win.current_filtered_groups:
            assert "100nf" in (g.value.lower() + " " + g.description.lower())

        # Clear search
        win._on_search_changed("")
        assert len(win.current_filtered_groups) == 13

    def test_incomplete_records_filter(self, main_window):
        win = main_window

        # Toggle incomplete filter
        win._toggle_incomplete_filter()
        assert win.show_only_incomplete is True

        # Group row 14 has missing min/target stock
        for g in win.current_filtered_groups:
            assert not g.is_complete

        # Toggle back
        win._toggle_incomplete_filter()
        assert win.show_only_incomplete is False
        assert len(win.current_filtered_groups) == 13

    def test_read_only_cell_flags(self, main_window):
        win = main_window

        # All cells in top table must not be editable
        for r in range(win.table.rowCount()):
            for c in range(win.table.columnCount()):
                item = win.table.item(r, c)
                if item:
                    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable), f"Cell ({r}, {c}) is editable"

        # All cells in bottom table must not be editable
        for r in range(win.products_table.rowCount()):
            for c in range(win.products_table.columnCount()):
                item = win.products_table.item(r, c)
                if item:
                    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable), f"Product cell ({r}, {c}) is editable"

    def test_product_panel_collapsed_by_default(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.products_frame.isVisible() is False
        assert win.products_footer_frame.isVisible() is True
        assert win.toggle_products_btn.isVisible() is True
        assert win.toggle_products_btn.isEnabled() is True
        # Reversed arrow mapping: UpArrow when collapsed to indicate action to expand
        assert win.toggle_products_btn.arrowType() == Qt.ArrowType.UpArrow
        assert win.toggle_products_btn.toolTip() == "Expand product details"
        assert win.toggle_products_btn.accessibleName() == "Expand product details"
        assert win.toggle_products_btn.text() == ""

    def test_toggle_centered_and_no_redundant_widgets(self, main_window):
        win = main_window
        footer_layout = win.products_footer_frame.layout()
        assert footer_layout.count() == 3
        # Left and right stretches center the single toggle widget
        assert footer_layout.itemAt(0).spacerItem() is not None
        assert footer_layout.itemAt(1).widget() == win.toggle_products_btn
        assert footer_layout.itemAt(2).spacerItem() is not None

        # Redundant Persian label, group hint, and header close button must be absent
        assert not hasattr(win, "footer_hint_lbl")
        assert not hasattr(win, "close_products_btn")

    def test_footer_toggle_expand_and_collapse(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.products_frame.isVisible() is False
        assert win.toggle_products_btn.arrowType() == Qt.ArrowType.UpArrow
        assert win.toggle_products_btn.toolTip() == "Expand product details"
        assert win.toggle_products_btn.text() == ""

        # Click footer arrow button to expand -> arrow turns DownArrow to indicate collapse
        win.toggle_products_btn.click()
        qapp.processEvents()
        assert win.products_frame.isVisible() is True
        assert win.toggle_products_btn.arrowType() == Qt.ArrowType.DownArrow
        assert win.toggle_products_btn.toolTip() == "Collapse product details"
        assert win.toggle_products_btn.accessibleName() == "Collapse product details"
        assert win.toggle_products_btn.text() == ""
        assert win.inventory_splitter.sizes()[1] > 0

        # Click footer arrow button to collapse -> arrow turns UpArrow to indicate expand
        win.toggle_products_btn.click()
        qapp.processEvents()
        assert win.products_frame.isVisible() is False
        assert win.toggle_products_btn.arrowType() == Qt.ArrowType.UpArrow
        assert win.toggle_products_btn.toolTip() == "Expand product details"
        assert win.toggle_products_btn.accessibleName() == "Expand product details"
        assert win.toggle_products_btn.text() == ""
        assert win.inventory_splitter.sizes()[1] == 0

    def test_selection_preserved_across_expand_and_collapse(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()

        # Find 100nF group (which has 3 products)
        target_idx = None
        for idx, g in enumerate(win.current_filtered_groups):
            if g.value == "100nF" and g.package == "0603":
                target_idx = idx
                break

        assert target_idx is not None
        win.table.selectRow(target_idx)
        qapp.processEvents()

        # Arrow toggle has no text
        assert win.toggle_products_btn.text() == ""

        # Expand panel and verify products
        win.toggle_products_btn.click()
        qapp.processEvents()
        assert win.products_frame.isVisible() is True
        assert win.products_table.rowCount() == 3

        selected_rows = win.table.selectionModel().selectedRows()
        assert len(selected_rows) == 1
        assert selected_rows[0].row() == target_idx

        # Collapse panel and verify selection preserved
        win.toggle_products_btn.click()
        qapp.processEvents()
        assert win.products_frame.isVisible() is False
        selected_rows_after = win.table.selectionModel().selectedRows()
        assert len(selected_rows_after) == 1
        assert selected_rows_after[0].row() == target_idx

    def test_session_panel_height_preserved(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        win._set_products_panel_expanded(True)
        qapp.processEvents()
        assert win.products_frame.isVisible() is True

        # Simulate user adjusting splitter height
        win.inventory_splitter.setSizes([300, 200])
        qapp.processEvents()
        actual_h = win.inventory_splitter.sizes()[1]
        win._on_splitter_moved(300, 1)
        assert win._last_products_panel_height == actual_h

        # Collapse and re-expand
        win._set_products_panel_expanded(False)
        qapp.processEvents()
        assert win.products_frame.isVisible() is False

        win._set_products_panel_expanded(True)
        qapp.processEvents()
        assert win.products_frame.isVisible() is True
        assert win.inventory_splitter.sizes()[1] == actual_h

    def test_quick_order_button_not_in_visible_header(self, main_window):
        win = main_window
        # Obsolete Quick Order and title bar settings are cleanly removed
        assert not hasattr(win, "quick_order_btn")
        assert hasattr(win, "title_bar")
        assert not hasattr(win.title_bar, "settings_btn")
        assert hasattr(win.title_bar, "btn_minimize")

    def test_stock_policy_table_column_widths_responsive_distribution(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        table = win.table

        # At default size
        win.resize(1400, 800)
        qapp.processEvents()
        table.distribute_columns()
        qapp.processEvents()

        vp_w = table.viewport().width()
        total_col_w = sum(table.columnWidth(c) for c in range(table.columnCount()))
        # Columns must absorb available width without a large empty gap
        assert abs(total_col_w - vp_w) <= 2, f"Expected total columns {total_col_w} to match viewport {vp_w}"

        # Resized larger window (1600 width)
        win.resize(1600, 800)
        qapp.processEvents()
        table.distribute_columns()
        qapp.processEvents()

        vp_w_large = table.viewport().width()
        total_col_w_large = sum(table.columnWidth(c) for c in range(table.columnCount()))
        assert abs(total_col_w_large - vp_w_large) <= 2
        assert total_col_w_large > total_col_w

    def test_min_and_target_stock_cell_tooltips_and_styling(self, main_window, qapp):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()
        assert win.inventory_components_table.rowCount() > 0

        # In the modern architecture, Min Stock (col 9) and Target Stock (col 10) are managed per physical component
        min_item = win.inventory_components_table.item(0, 9)
        tgt_item = win.inventory_components_table.item(0, 10)

        assert min_item is not None
        assert tgt_item is not None
        assert "Double-click to edit thresholds" in min_item.toolTip()
        assert "Double-click to edit thresholds" in tgt_item.toolTip()

    def test_inventory_database_path_property_exists_and_resolves(self, main_window):
        win = main_window
        # Must have the attribute/property inventory_database_path without AttributeError
        assert hasattr(win, "inventory_database_path")
        path = win.inventory_database_path
        assert isinstance(path, str) and len(path) > 0
        assert os.path.exists(path)

    def test_double_click_restricted_to_min_and_target_stock_columns(self, main_window, qapp, monkeypatch):
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()
        assert win.inventory_components_table.rowCount() > 0

        win.inventory_components_table.selectRow(0)
        qapp.processEvents()

        called_threshold_comps = []
        monkeypatch.setattr(win, "_open_component_threshold_dialog", lambda comp: called_threshold_comps.append(comp))

        called_stock_adj = []
        monkeypatch.setattr(win, "_open_stock_adjustment_dialog", lambda comp: called_stock_adj.append(comp))

        # 1. Non-threshold columns (e.g. Row 0, Manufacturer 1, MPN 2) must NOT trigger threshold editing
        for col in [0, 1, 2, 3, 4, 5, 6, 7]:
            item = win.inventory_components_table.item(0, col)
            if item:
                win._on_inventory_component_double_clicked(item)
                assert len(called_threshold_comps) == 0

        # 2. Permitted threshold columns: Min Stock (col 9) and Target Stock (col 10)
        item_min = win.inventory_components_table.item(0, 9)
        win._on_inventory_component_double_clicked(item_min)
        assert len(called_threshold_comps) == 1

        item_tgt = win.inventory_components_table.item(0, 10)
        win._on_inventory_component_double_clicked(item_tgt)
        assert len(called_threshold_comps) == 2

        # 3. Column 8 (Quantity in Stock) triggers StockAdjustmentDialog
        item_qty = win.inventory_components_table.item(0, 8)
        win._on_inventory_component_double_clicked(item_qty)
        assert len(called_stock_adj) == 1

    def test_context_menu_restricted_to_min_and_target_stock_columns(self, main_window, qapp, monkeypatch):
        from PyQt6.QtCore import QPoint
        from core.inventory.repository import SqliteInventoryRepository
        win = main_window
        win.show()
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()
        assert win.inventory_components_table.rowCount() > 0

        win.inventory_components_table.selectRow(0)
        qapp.processEvents()

        actions_created = []
        with patch("ui.main_window.isinstance", side_effect=lambda obj, cls: True if cls == SqliteInventoryRepository else isinstance(obj, cls)):
            with patch("ui.main_window.QMenu") as MockMenu:
                instance = MockMenu.return_value
                def fake_add(text):
                    actions_created.append(text)
                    return MagicMock()
                instance.addAction.side_effect = fake_add
                win._show_inventory_component_context_menu(QPoint(10, 10))

        assert any("Edit Stock Thresholds..." in a for a in actions_created)
        assert any("Stock Management..." in a for a in actions_created)
        assert any("Add New Component..." in a for a in actions_created)

    def test_incomplete_status_badge_and_tooltip_visibility(self, main_window):
        win = main_window
        assert win.table.rowCount() > 0

        # Check column minimum widths in Table 2
        table = win.table
        assert table._min_column_widths.get(5, 0) >= 105  # Total In Stock
        assert table._min_column_widths.get(6, 0) >= 140  # Matched Products
        assert table.columnWidth(6) >= 140

        # Check Status column in Component Inventory table (Table 1, col 11)
        comp_table = win.inventory_components_table
        assert comp_table.columnCount() == 14
        assert comp_table.horizontalHeaderItem(11).text() == "Status"
        if comp_table.rowCount() > 0:
            status_item = comp_table.item(0, 11)
            assert status_item is not None
            assert status_item.text() in ("🟢 Normal", "🔴 Low Stock", "⚠️ Out of Stock")

    def test_edit_stock_policy_thresholds_handles_missing_file_gracefully(self, main_window):
        win = main_window
        # Set invalid path
        win.inventory_database_path = "C:/non_existent_path/fake.xlsm"

        with patch("ui.main_window.QMessageBox.critical") as mock_crit:
            # Should not crash with unhandled exception
            win._edit_stock_policy_thresholds(0)
            assert mock_crit.called
            title = mock_crit.call_args[0][1]
            assert "Database File Not Found" in title

    def test_order_low_stock_informational_dialog(self, main_window):
        win = main_window

        # 1. When no shortages exist in current inventory repository
        with patch.object(win, "_get_stock_policy_replenishment_items", return_value=[]):
            with patch("ui.main_window.QMessageBox.information") as mock_info:
                win._open_inventory_order_dialog()
                assert mock_info.called
                title = mock_info.call_args[0][1]
                assert title == "No Shortages Detected"
                message = mock_info.call_args[0][2]
                assert "meet or exceed their configured minimum stock thresholds" in message

        # 2. When shortages exist, opens OrderPreviewDialog
        fake_shortage = [
            {"part_name": "R1", "needed_qty": 5, "shortage_qty": 5, "status": "SHORTAGE", "link": "https://lionelectronic.ir/p/1"}
        ]
        with patch.object(win, "_get_stock_policy_replenishment_items", return_value=fake_shortage):
            with patch("ui.main_window.OrderPreviewDialog.exec") as mock_exec:
                win._open_inventory_order_dialog()
                assert mock_exec.called
