import pytest
from models import Component, StockTransaction


class TestComponentModel:
    """Test suite for Component dataclass, drawer parsing, status calculations, and formatting."""

    def test_default_initialization(self):
        comp = Component()
        assert comp.id is None
        assert comp.name == ""
        assert comp.value == ""
        assert comp.package == "—"
        assert comp.category == "—"
        assert comp.quantity == 0
        assert comp.min_alert == 10
        assert comp.drawers == ""
        assert comp.drawer_stocks == {}
        assert comp.drawer_list == []
        assert comp.stock_status == "EMPTY"
        assert comp.status_label == "ناموجود"

    def test_drawer_stocks_parsing_modern_format(self):
        # Format: "1:25, 4:25, 8:0"
        comp = Component(quantity=50, drawers="1:25, 4:25, 8:0")
        stocks = comp.drawer_stocks
        assert stocks == {1: 25, 4: 25, 8: 0}
        assert comp.drawer_list == [1, 4, 8]
        assert comp.get_drawer_qty(1) == 25
        assert comp.get_drawer_qty(4) == 25
        assert comp.get_drawer_qty(8) == 0
        assert comp.is_drawer_empty(8) is True
        assert comp.is_drawer_empty(1) is False

    def test_drawer_stocks_parsing_json_format(self):
        # JSON format: '{"1": 30, "5": 20}'
        comp = Component(quantity=50, drawers='{"1": 30, "5": 20}')
        assert comp.drawer_stocks == {1: 30, 5: 20}
        assert comp.drawer_list == [1, 5]

    def test_drawer_stocks_parsing_legacy_single_drawer(self):
        # Single drawer legacy: "12"
        comp = Component(quantity=40, drawers="12")
        assert comp.drawer_stocks == {12: 40}
        assert comp.drawer_list == [12]

    def test_drawer_stocks_parsing_legacy_multi_drawer(self):
        # Multiple drawers without quantities: "1, 4"
        comp = Component(quantity=50, drawers="1, 4")
        # 50 split between 1 and 4 -> 25 each
        assert comp.drawer_stocks == {1: 25, 4: 25}

    def test_drawer_stocks_setter(self):
        comp = Component(quantity=0, drawers="")
        comp.drawer_stocks = {1: 100, 3: 50}
        assert comp.quantity == 150
        assert comp.drawers == "1:100, 3:50"
        assert comp.get_drawer_qty(1) == 100
        assert comp.get_drawer_qty(3) == 50

    def test_formatted_drawers_display(self):
        comp = Component(quantity=50, drawers="1:25, 4:25")
        assert comp.formatted_drawers == "1, 4"
        assert comp.formatted_drawers_detailed == "1 (25), 4 (25)"

        empty_comp = Component(drawers="")
        assert empty_comp.formatted_drawers == "—"
        assert empty_comp.formatted_drawers_detailed == "—"

        zero_drawer_comp = Component(quantity=0, drawers="7:0")
        assert zero_drawer_comp.formatted_drawers_detailed == "7 (0)"

    def test_stock_status_levels(self):
        # Out of stock
        c_empty = Component(quantity=0, min_alert=10)
        assert c_empty.stock_status == "EMPTY"
        assert c_empty.status_label == "ناموجود"

        # Low stock (at or below alert threshold)
        c_low = Component(quantity=10, min_alert=10)
        assert c_low.stock_status == "LOW"
        assert c_low.status_label == "کسری"

        c_low2 = Component(quantity=5, min_alert=10)
        assert c_low2.stock_status == "LOW"
        assert c_low2.status_label == "کسری"

        # Normal healthy stock (strictly above min_alert)
        c_ok = Component(quantity=11, min_alert=10)
        assert c_ok.stock_status == "OK"
        assert c_ok.status_label == "کافی"


class TestStockTransactionModel:
    """Test suite for StockTransaction model."""

    def test_stock_transaction_initialization(self):
        tx = StockTransaction(
            id=1,
            component_id=5,
            component_name="Resistor",
            change_type="ADD",
            amount=20,
            previous_qty=30,
            new_qty=50,
            drawer_number=1,
            note="Restock batch",
            timestamp="2026-08-27 10:00:00"
        )
        assert tx.id == 1
        assert tx.component_id == 5
        assert tx.change_type == "ADD"
        assert tx.amount == 20
        assert tx.previous_qty == 30
        assert tx.new_qty == 50
        assert tx.drawer_number == 1
        assert tx.note == "Restock batch"
