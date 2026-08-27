from typing import Optional
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt


class StatsRibbonWidget(QFrame):
    """Status ribbon displaying quick overview pills for the loaded Excel database."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ribbonFrame")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        ribbon_layout = QHBoxLayout(self)
        ribbon_layout.setContentsMargins(10, 5, 10, 5)
        ribbon_layout.setSpacing(10)

        self.stat_total_rows = QLabel("Total Records: 0")
        self.stat_total_rows.setProperty("class", "statPill")
        ribbon_layout.addWidget(self.stat_total_rows)

        self.stat_filtered_rows = QLabel("Matches: 0")
        self.stat_filtered_rows.setProperty("class", "statPillSuccess")
        ribbon_layout.addWidget(self.stat_filtered_rows)

        self.stat_columns = QLabel("Columns: 0")
        self.stat_columns.setProperty("class", "statPill")
        ribbon_layout.addWidget(self.stat_columns)

        ribbon_layout.addStretch()

        self.stat_file = QLabel("Database: No File Found")
        self.stat_file.setProperty("class", "statPill")
        self.stat_file.setToolTip("Active Excel Database")
        ribbon_layout.addWidget(self.stat_file)

    def update_stats(self, total_rows: int, filtered_rows: int, total_cols: int, file_name: str):
        """Update ribbon pills from current dataset state."""
        self.stat_total_rows.setText(f"Total Records: {total_rows:,}")
        self.stat_filtered_rows.setText(f"Matches: {filtered_rows:,}")
        self.stat_columns.setText(f"Columns: {total_cols:,}")

        display_name = file_name if file_name else "No File Found"
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        self.stat_file.setText(f"📊 {display_name}")
        self.stat_file.setToolTip(file_name or "No active database file")
