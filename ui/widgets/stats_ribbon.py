from typing import Dict, Any, Optional
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class StatsRibbonWidget(QFrame):
    """Status ribbon displaying quick warehouse overview pills (total types, items, active drawers, status counts)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ribbonFrame")
        self._init_ui()

    def _init_ui(self):
        ribbon_layout = QHBoxLayout(self)
        ribbon_layout.setContentsMargins(8, 4, 8, 4)
        ribbon_layout.setSpacing(8)

        self.stat_types_pill = QLabel("قطعات: ۰ قلم")
        self.stat_types_pill.setProperty("class", "statPill")
        ribbon_layout.addWidget(self.stat_types_pill)

        self.stat_items_pill = QLabel("موجودی کل: ۰ عدد")
        self.stat_items_pill.setProperty("class", "statPill")
        ribbon_layout.addWidget(self.stat_items_pill)

        self.stat_drawers_pill = QLabel("کشوهای فعال: ۰")
        self.stat_drawers_pill.setProperty("class", "statPill")
        ribbon_layout.addWidget(self.stat_drawers_pill)

        ribbon_layout.addStretch()

        self.stat_instock_pill = QLabel("موجودی کافی: ۰")
        self.stat_instock_pill.setProperty("class", "statPillSuccess")
        ribbon_layout.addWidget(self.stat_instock_pill)

        self.stat_low_pill = QLabel("کسری انبار: ۰")
        self.stat_low_pill.setProperty("class", "statPillWarning")
        ribbon_layout.addWidget(self.stat_low_pill)

        self.stat_empty_pill = QLabel("ناموجود: ۰")
        self.stat_empty_pill.setProperty("class", "statPillDanger")
        ribbon_layout.addWidget(self.stat_empty_pill)

    def update_stats(self, stats: Dict[str, Any]):
        """Update ribbon pills from database statistics dictionary."""
        self.stat_types_pill.setText(f"قطعات: {stats['total_types']:,} قلم")
        self.stat_items_pill.setText(f"موجودی کل: {stats['total_items']:,} عدد")
        self.stat_drawers_pill.setText(f"کشوهای فعال: {stats['total_drawers']:,}")
        self.stat_instock_pill.setText(f"موجودی کافی: {stats['in_stock_count']:,}")
        self.stat_low_pill.setText(f"کسری انبار: {stats['low_stock_count']:,}")
        self.stat_empty_pill.setText(f"ناموجود: {stats['empty_count']:,}")
