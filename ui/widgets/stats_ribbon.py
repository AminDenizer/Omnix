from typing import Optional
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal


class StatsRibbonWidget(QFrame):
    """Status ribbon displaying quick overview pills for the loaded Excel database."""

    orderShortagesRequested = pyqtSignal()
    incompleteFilterRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ribbonFrame")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._is_incomplete_active = False
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

        # Incomplete Records Button
        self.stat_incomplete_btn = QPushButton("⚠️ Incomplete (0)")
        self.stat_incomplete_btn.setObjectName("secondaryBtn")
        self.stat_incomplete_btn.setToolTip("Click to filter records with missing fields or '?' values")
        self.stat_incomplete_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #64748b;
                border-radius: 6px;
                padding: 4px 10px;
                color: #94a3b8;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.stat_incomplete_btn.clicked.connect(self.incompleteFilterRequested.emit)
        ribbon_layout.addWidget(self.stat_incomplete_btn)

        ribbon_layout.addStretch()

        self.order_shortages_btn = QPushButton("🛒 Order Low Stock (0)")
        self.order_shortages_btn.setObjectName("secondaryBtn")
        self.order_shortages_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 4px 12px;
                color: #38bdf8;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #0f172a;
                border-color: #334155;
                color: #64748b;
            }
        """)
        self.order_shortages_btn.clicked.connect(self.orderShortagesRequested.emit)
        self.order_shortages_btn.setEnabled(False)
        ribbon_layout.addWidget(self.order_shortages_btn)

        self.stat_file = QLabel("Database: No File Found")
        self.stat_file.setProperty("class", "statPill")
        self.stat_file.setToolTip("Active Excel Database")
        ribbon_layout.addWidget(self.stat_file)

    def set_incomplete_active(self, is_active: bool):
        self._is_incomplete_active = is_active

    def update_stats(
        self,
        total_rows: int,
        filtered_rows: int,
        total_cols: int,
        file_name: str,
        shortage_count: int = 0,
        incomplete_count: int = 0
    ):
        """Update ribbon pills from current dataset state."""
        self.stat_total_rows.setText(f"Total Records: {total_rows:,}")
        self.stat_filtered_rows.setText(f"Matches: {filtered_rows:,}")
        self.stat_columns.setText(f"Columns: {total_cols:,}")

        # Incomplete records pill update
        if incomplete_count > 0:
            self.stat_incomplete_btn.setEnabled(True)
            if self._is_incomplete_active:
                self.stat_incomplete_btn.setText(f"🔍 Showing Incomplete ({incomplete_count}) [Clear]")
                self.stat_incomplete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f59e0b;
                        border: 1.5px solid #d97706;
                        border-radius: 6px;
                        padding: 4px 10px;
                        color: #0f172a;
                        font-weight: bold;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #d97706;
                        color: #ffffff;
                    }
                """)
            else:
                self.stat_incomplete_btn.setText(f"⚠️ Incomplete: {incomplete_count}")
                self.stat_incomplete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(245, 158, 11, 0.15);
                        border: 1.5px solid #f59e0b;
                        border-radius: 6px;
                        padding: 4px 10px;
                        color: #fbbf24;
                        font-weight: 600;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #f59e0b;
                        color: #0f172a;
                    }
                """)
        else:
            self.stat_incomplete_btn.setEnabled(False)
            self.stat_incomplete_btn.setText("✅ Records Complete")
            self.stat_incomplete_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(16, 185, 129, 0.1);
                    border: 1px solid rgba(16, 185, 129, 0.25);
                    border-radius: 6px;
                    padding: 4px 10px;
                    color: #34d399;
                    font-weight: 500;
                    font-size: 11px;
                }
            """)

        # Shortages button update
        if shortage_count > 0:
            self.order_shortages_btn.setEnabled(True)
            self.order_shortages_btn.setText(f"⚠️ Order Low Stock ({shortage_count})")
            self.order_shortages_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(245, 158, 11, 0.18);
                    border: 1.5px solid #f59e0b;
                    border-radius: 6px;
                    padding: 4px 12px;
                    color: #fbbf24;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #f59e0b;
                    color: #0f172a;
                }
            """)
        else:
            self.order_shortages_btn.setEnabled(False)
            self.order_shortages_btn.setText("✅ All Stock OK")
            self.order_shortages_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(16, 185, 129, 0.12);
                    border: 1px solid rgba(16, 185, 129, 0.35);
                    border-radius: 6px;
                    padding: 4px 12px;
                    color: #34d399;
                    font-weight: 600;
                    font-size: 11px;
                }
            """)

        display_name = file_name if file_name else "No File Found"
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        self.stat_file.setText(f"📊 {display_name}")
        self.stat_file.setToolTip(file_name or "No active database file")

