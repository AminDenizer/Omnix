import pytest
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow


class TestMainWindow:
    """Test suite for Omnix main application window and interactions."""

    def test_main_window_initialization_and_branding(self, qapp, sample_db_with_data):
        win = MainWindow(db=sample_db_with_data)
        assert win is not None
        assert "Omnix" in win.windowTitle()
        assert win.layoutDirection() == Qt.LayoutDirection.RightToLeft
        
        # Verify table row count matches components in DB
        assert win.table.rowCount() == 3

        # Verify status bar layout
        assert win.status_state_lbl is not None
        assert "آماده به کار" in win.status_state_lbl.text()
        assert win.shortcuts_guide_lbl is not None
        assert "[ / جستجو ]" in win.shortcuts_guide_lbl.text()
        win.close()

    def test_main_window_search_filtering(self, qapp, sample_db_with_data):
        win = MainWindow(db=sample_db_with_data)
        
        # Filter search for "STM32"
        win.search_input.setText("STM32")
        win._on_filter_changed()
        assert win.table.rowCount() == 1

        # Clear search
        win.search_input.setText("")
        win._on_filter_changed()
        assert win.table.rowCount() == 3
        win.close()

    def test_main_window_category_filter(self, qapp, sample_db_with_data):
        win = MainWindow(db=sample_db_with_data)
        
        # Select "Capacitor" in category filter
        idx = win.category_filter.findText("Capacitor")
        if idx >= 0:
            win.category_filter.setCurrentIndex(idx)
            win._on_filter_changed()
            assert win.table.rowCount() == 1
        win.close()

    def test_main_window_status_filter(self, qapp, sample_db_with_data):
        win = MainWindow(db=sample_db_with_data)
        
        # Filter by out of stock state
        idx = win.stock_filter.findText("ناموجود (صفر)")
        if idx >= 0:
            win.stock_filter.setCurrentIndex(idx)
            win._on_filter_changed()
            assert win.table.rowCount() == 1
        win.close()

    def test_quick_stock_adjustments(self, qapp, sample_db_with_data):
        win = MainWindow(db=sample_db_with_data)
        comps = sample_db_with_data.get_all_components()
        comp = comps[0]
        initial_qty = comp.quantity

        # Test quick increment
        win._quick_increment_component(comp)
        updated = sample_db_with_data.get_component(comp.id)
        assert updated.quantity == initial_qty + 1

        # Test quick decrement
        win._quick_decrement_component(updated)
        reverted = sample_db_with_data.get_component(comp.id)
        assert reverted.quantity == initial_qty
        win.close()
