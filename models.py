from dataclasses import dataclass, field
from typing import List, Optional, Dict
import json
import datetime


@dataclass
class Component:
    id: Optional[int] = None
    name: str = ""
    value: str = ""
    package: str = "—"
    category: str = "—"
    quantity: int = 0
    min_alert: int = 10
    drawers: str = ""  # Storage format: "1:50, 4:40, 8:0" or legacy "1, 4, 8"
    description: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    _drawer_stocks: Optional[Dict[int, int]] = None

    @property
    def drawer_stocks(self) -> Dict[int, int]:
        """Dictionary mapping drawer number to its item count: {1: 50, 4: 40, 8: 0}."""
        if self._drawer_stocks is not None:
            return self._drawer_stocks

        stocks: Dict[int, int] = {}
        raw = (self.drawers or "").strip()
        if not raw:
            self._drawer_stocks = stocks
            return stocks

        # Check for JSON format
        if raw.startswith("{") and raw.endswith("}"):
            try:
                data = json.loads(raw)
                for k, v in data.items():
                    if str(k).isdigit():
                        stocks[int(k)] = max(0, int(v))
                self._drawer_stocks = stocks
                return stocks
            except Exception:
                pass

        # Check for "1:50, 4:40" or simple "1, 4, 8" format
        parts = raw.replace('،', ',').split(',')
        has_colon = any(':' in p for p in parts)

        if has_colon:
            for p in parts:
                p = p.strip()
                if ':' in p:
                    d_str, q_str = p.split(':', 1)
                    if d_str.strip().isdigit():
                        d_num = int(d_str.strip())
                        qty = int(q_str.strip()) if q_str.strip().isdigit() else 0
                        stocks[d_num] = max(0, qty)
                elif p.isdigit():
                    stocks[int(p)] = 0
        else:
            # Legacy format with only drawer numbers: distribute total quantity
            nums = []
            for p in parts:
                p = p.strip()
                if p.isdigit():
                    nums.append(int(p))
            nums = sorted(list(set(nums)))
            if nums:
                # If only one drawer, assign total quantity to it
                if len(nums) == 1:
                    stocks[nums[0]] = max(0, self.quantity)
                else:
                    # Distribute total quantity across multiple drawers
                    base_qty = self.quantity // len(nums)
                    rem = self.quantity % len(nums)
                    for idx, n in enumerate(nums):
                        stocks[n] = base_qty + (1 if idx < rem else 0)

        self._drawer_stocks = stocks
        return stocks

    @drawer_stocks.setter
    def drawer_stocks(self, value: Dict[int, int]):
        self._drawer_stocks = {int(k): max(0, int(v)) for k, v in value.items()}
        # Update raw drawers string representation
        items = [f"{d}:{q}" for d, q in sorted(self._drawer_stocks.items())]
        self.drawers = ", ".join(items)
        self.quantity = sum(self._drawer_stocks.values())

    @property
    def drawer_list(self) -> List[int]:
        """Sorted list of all drawer numbers assigned to this component."""
        return sorted(list(self.drawer_stocks.keys()))

    def get_drawer_qty(self, drawer_num: int) -> int:
        """Get the specific item count inside a designated drawer."""
        return self.drawer_stocks.get(drawer_num, 0)

    def is_drawer_empty(self, drawer_num: int) -> bool:
        """Check if stock in the specified drawer is zero."""
        return self.drawer_stocks.get(drawer_num, 0) == 0

    @property
    def formatted_drawers(self) -> str:
        """String representation of drawer numbers."""
        nums = self.drawer_list
        if not nums:
            return "—"
        return ", ".join(str(n) for n in nums)

    @property
    def formatted_drawers_detailed(self) -> str:
        """Detailed string representation of drawers with their respective counts."""
        stocks = self.drawer_stocks
        if not stocks:
            return "—"
        parts = []
        for d, q in sorted(stocks.items()):
            if q == 0:
                parts.append(f"{d} (0)")
            else:
                parts.append(f"{d} ({q:,})")
        return ", ".join(parts)

    @property
    def stock_status(self) -> str:
        """Evaluate inventory health status for table highlighting."""
        if self.quantity <= 0:
            return "EMPTY"       # Out of stock (Red)
        elif self.quantity <= self.min_alert:
            return "LOW"         # Low stock alert (Amber)
        else:
            return "OK"          # Normal healthy stock (Green)

    @property
    def status_label(self) -> str:
        status_map = {
            "EMPTY": "ناموجود",
            "LOW": "کسری",
            "OK": "کافی"
        }
        return status_map.get(self.stock_status, "نامشخص")


@dataclass
class StockTransaction:
    id: Optional[int] = None
    component_id: int = 0
    component_name: str = ""
    component_value: str = ""
    change_type: str = "DEDUCT"  # ADD (Stock In / Increase), DEDUCT (Usage / Decrease)
    amount: int = 0
    previous_qty: int = 0
    new_qty: int = 0
    drawer_number: Optional[int] = None  # Specific drawer number involved in the change
    note: str = ""
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
