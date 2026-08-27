import pytest
from models import Component
from database import Database, DEFAULT_CATEGORIES, DEFAULT_PACKAGES


class TestDatabaseCRUD:
    """Test database creation, component CRUD operations, and constraint handling."""

    def test_database_initialization(self, temp_db):
        assert temp_db is not None
        assert temp_db.get_category_mode() == "DEFAULT"
        assert temp_db.get_package_mode() == "DEFAULT"

    def test_add_and_get_component(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        assert comp_id is not None
        assert comp_id > 0

        fetched = temp_db.get_component(comp_id)
        assert fetched is not None
        assert fetched.id == comp_id
        assert fetched.name == sample_component.name
        assert fetched.value == sample_component.value
        assert fetched.quantity == 50
        assert fetched.drawers == "1:25, 4:25"

    def test_get_nonexistent_component(self, temp_db):
        assert temp_db.get_component(99999) is None

    def test_update_component(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        comp = temp_db.get_component(comp_id)
        
        comp.value = "22k 5%"
        comp.quantity = 80
        comp.drawers = "1:40, 4:40"
        ok = temp_db.update_component(comp)
        assert ok is True

        updated = temp_db.get_component(comp_id)
        assert updated.value == "22k 5%"
        assert updated.quantity == 80
        assert updated.drawers == "1:40, 4:40"

    def test_delete_component(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        assert temp_db.get_component(comp_id) is not None

        ok = temp_db.delete_component(comp_id)
        assert ok is True
        assert temp_db.get_component(comp_id) is None


class TestDatabaseStockAdjustments:
    """Test stock adjustments, drawer-level math, transaction history, and inventory stats."""

    def test_adjust_single_drawer_stock_add(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        # Original: 1:25, 4:25 (total 50)
        new_total = temp_db.adjust_single_drawer_stock(comp_id, 1, delta=10, note="Restock drawer 1")
        assert new_total == 60

        comp = temp_db.get_component(comp_id)
        assert comp.quantity == 60
        assert comp.get_drawer_qty(1) == 35
        assert comp.get_drawer_qty(4) == 25

    def test_adjust_single_drawer_stock_deduct(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        # Original: 1:25, 4:25 (total 50)
        new_total = temp_db.adjust_single_drawer_stock(comp_id, 4, delta=-15, note="Used in project")
        assert new_total == 35

        comp = temp_db.get_component(comp_id)
        assert comp.quantity == 35
        assert comp.get_drawer_qty(4) == 10

    def test_adjust_single_drawer_stock_floor_at_zero(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        # Deduct more than drawer has (drawer 1 has 25, deduct 50)
        new_total = temp_db.adjust_single_drawer_stock(comp_id, 1, delta=-50)
        assert new_total == 25  # Drawer 1 becomes 0, Drawer 4 remains 25

        comp = temp_db.get_component(comp_id)
        assert comp.get_drawer_qty(1) == 0
        assert comp.get_drawer_qty(4) == 25

    def test_adjust_drawer_stocks_bulk(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        # Deduct 10 from Drawer 1 and 20 from Drawer 4
        new_total = temp_db.adjust_drawer_stocks(comp_id, {1: 10, 4: 20}, is_deduct=True, note="Bulk production")
        assert new_total == 20

        comp = temp_db.get_component(comp_id)
        assert comp.quantity == 20
        assert comp.get_drawer_qty(1) == 15
        assert comp.get_drawer_qty(4) == 5

    def test_stock_history_recording(self, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        temp_db.adjust_single_drawer_stock(comp_id, 1, delta=5, note="Check history")
        
        history = temp_db.get_stock_history(comp_id)
        assert len(history) >= 2  # 1 initial insert + 1 adjust
        last_tx = history[0]
        assert last_tx["component_id"] == comp_id
        assert last_tx["amount"] == 5


class TestDatabaseSearchAndFilters:
    """Test multi-criteria search and filter queries."""

    def test_search_by_text(self, sample_db_with_data):
        # Search by value "10k"
        results = sample_db_with_data.search_components(query="10k")
        assert len(results) == 1
        assert results[0].value == "10k 1%"

        # Search by component name
        results2 = sample_db_with_data.search_components(query="خازن")
        assert len(results2) == 1
        assert results2[0].name == "خازن سرامیکی"

    def test_search_by_category(self, sample_db_with_data):
        results = sample_db_with_data.search_components(category="Capacitor")
        assert len(results) == 1
        assert results[0].category == "Capacitor"

    def test_search_by_status(self, sample_db_with_data):
        # Out of stock filter
        empty_results = sample_db_with_data.search_components(stock_filter="EMPTY")
        assert len(empty_results) == 1
        assert empty_results[0].quantity == 0

        # Normal healthy stock filter
        ok_results = sample_db_with_data.search_components(stock_filter="IN_STOCK")
        assert len(ok_results) >= 2


class TestCustomCategoriesAndPackages:
    """Test dynamic category and package list management."""

    def test_category_mode_toggle(self, temp_db):
        assert temp_db.get_category_mode() == "DEFAULT"
        temp_db.set_category_mode("CUSTOM")
        assert temp_db.get_category_mode() == "CUSTOM"

    def test_custom_categories_crud(self, temp_db):
        ok = temp_db.add_custom_category("Optocoupler")
        assert ok is True
        assert "Optocoupler" in temp_db.get_custom_categories()

        # Duplicate addition prevention
        ok2 = temp_db.add_custom_category("Optocoupler")
        assert ok2 is False

        # Delete category
        del_ok = temp_db.delete_custom_category("Optocoupler")
        assert del_ok is True
        assert "Optocoupler" not in temp_db.get_custom_categories()

    def test_package_mode_and_crud(self, temp_db):
        assert temp_db.get_package_mode() == "DEFAULT"
        temp_db.set_package_mode("CUSTOM")
        assert temp_db.get_package_mode() == "CUSTOM"

        ok = temp_db.add_custom_package("LQFP-64")
        assert ok is True
        assert "LQFP-64" in temp_db.get_custom_packages()

        temp_db.delete_custom_package("LQFP-64")
        assert "LQFP-64" not in temp_db.get_custom_packages()


class TestDrawerQueriesAndStats:
    """Test active drawers retrieval and overall warehouse statistics."""

    def test_active_drawers_and_contents(self, sample_db_with_data):
        drawers = sample_db_with_data.get_all_used_drawers()
        # Drawers assigned in fixture: 1, 4, 7, 12
        assert 1 in drawers
        assert 4 in drawers
        assert 12 in drawers

        # Get components inside drawer 12
        d12_comps = sample_db_with_data.get_components_by_drawer(12)
        assert len(d12_comps) == 1
        assert d12_comps[0].value == "STM32F103C8T6"

    def test_get_statistics(self, sample_db_with_data):
        stats = sample_db_with_data.get_statistics()
        assert stats["total_types"] == 3
        assert stats["total_items"] == 90  # 50 + 40 + 0
        assert stats["total_drawers"] >= 3
        assert stats["empty_count"] == 1    # 1 capacitor with 0 qty
