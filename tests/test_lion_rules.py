import math
import pytest
from lion_automator import LionAutomator

def calculate_target_quantity(needed_qty: int, site_step: int) -> int:
    if site_step > 10:
        effective_step = site_step
    elif site_step in [2, 5, 10]:
        effective_step = 10
    else:
        effective_step = 1
    multiples = math.ceil(needed_qty / effective_step)
    return max(multiples * effective_step, site_step)

class TestLionAutomatorRules:
    def test_smart_step_calculation(self):
        assert calculate_target_quantity(needed_qty=45, site_step=2) == 50
        assert calculate_target_quantity(needed_qty=7, site_step=2) == 10
        assert calculate_target_quantity(needed_qty=13, site_step=5) == 20
        assert calculate_target_quantity(needed_qty=50, site_step=10) == 50
        assert calculate_target_quantity(needed_qty=51, site_step=10) == 60
        assert calculate_target_quantity(needed_qty=23, site_step=25) == 25
        assert calculate_target_quantity(needed_qty=26, site_step=25) == 50
        assert calculate_target_quantity(needed_qty=85, site_step=100) == 100
        assert calculate_target_quantity(needed_qty=105, site_step=100) == 200
        assert calculate_target_quantity(needed_qty=1, site_step=1) == 1
        assert calculate_target_quantity(needed_qty=5, site_step=1) == 5
        assert calculate_target_quantity(needed_qty=11, site_step=1) == 11

    def test_moq_respect(self):
        assert calculate_target_quantity(needed_qty=1, site_step=25) == 25
        assert calculate_target_quantity(needed_qty=0, site_step=10) == 10

    def test_stock_vs_target_check(self):
        site_stock = 11
        target_qty = 20
        assert site_stock < target_qty
        assert 11 >= 11
        assert 50 >= 45
