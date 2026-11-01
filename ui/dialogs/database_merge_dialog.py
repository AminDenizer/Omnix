"""
Omnix UI — Database Bind/Merge Dialog
Governing Requirement: Phase 3 Database Bind/Merge Specification

Provides a dedicated preview-and-confirmation workflow for safely binding/merging external
inventory databases into the active runtime repository.
"""

import os
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from core.inventory.repository import SqliteInventoryRepository
from core.inventory.merge import DatabaseMergeService, MergeAnalysis
from ui.dark_frame import apply_dark_window_frame


class DatabaseMergeDialog(QDialog):
    """Interactive preview-and-merge modal for external SQLite databases."""

    def __init__(self, repository: SqliteInventoryRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.analysis: Optional[MergeAnalysis] = None

        self.setWindowTitle("Bind & Merge Database — Non-Destructive Reconciliation")
        self.resize(880, 620)
        self.setMinimumSize(720, 500)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QFrame#cardFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton#primaryBtn {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton#primaryBtn:hover { background-color: #0369a1; }
            QPushButton#primaryBtn:disabled { background-color: #334155; color: #64748b; }
            QPushButton#secondaryBtn {
                background-color: #1e293b;
                border: 1px solid #475569;
                color: #94a3b8;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton#secondaryBtn:hover { background-color: #334155; color: #f8fafc; }
            QTableWidget {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #f8fafc;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #334155;
                padding: 4px 6px;
            }
        """)

        self._init_ui()
        apply_dark_window_frame(self)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Title
        title_lbl = QLabel("🔀 Bind / Merge External SQLite Database")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        info_lbl = QLabel(
            "Select an external database to reconcile and merge components into your active inventory. "
            "Only eligible NEW components and their supplier links will be inserted with fresh IDs. "
            "Duplicates, conflicts, and incomplete records are automatically skipped and existing records are never overwritten."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(info_lbl)

        # File Selection Card
        file_card = QFrame()
        file_card.setObjectName("cardFrame")
        file_layout = QHBoxLayout(file_card)
        file_layout.setContentsMargins(12, 10, 12, 10)
        file_layout.setSpacing(10)

        self.file_lbl = QLabel("No external database selected")
        self.file_lbl.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 500;")
        file_layout.addWidget(self.file_lbl, 1)

        self.browse_btn = QPushButton("Browse Database (.db)...")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_btn)

        layout.addWidget(file_card)

        # Summary KPIs Ribbon
        self.kpi_card = QFrame()
        self.kpi_card.setObjectName("cardFrame")
        kpi_layout = QHBoxLayout(self.kpi_card)
        kpi_layout.setContentsMargins(12, 8, 12, 8)
        kpi_layout.setSpacing(10)

        self.pill_new = QLabel("New Records: —")
        self.pill_new.setStyleSheet("background-color: rgba(16, 185, 129, 0.15); border: 1px solid #059669; color: #34d399; border-radius: 6px; padding: 4px 10px; font-weight: bold;")
        kpi_layout.addWidget(self.pill_new)

        self.pill_duplicate = QLabel("Duplicates (Preserved): —")
        self.pill_duplicate.setStyleSheet("background-color: rgba(56, 189, 248, 0.12); border: 1px solid #0284c7; color: #38bdf8; border-radius: 6px; padding: 4px 10px; font-weight: 500;")
        kpi_layout.addWidget(self.pill_duplicate)

        self.pill_conflict = QLabel("Conflicts (Skipped): —")
        self.pill_conflict.setStyleSheet("background-color: rgba(245, 158, 11, 0.12); border: 1px solid #d97706; color: #fbbf24; border-radius: 6px; padding: 4px 10px; font-weight: 500;")
        kpi_layout.addWidget(self.pill_conflict)

        self.pill_incomplete = QLabel("Incomplete: —")
        self.pill_incomplete.setStyleSheet("background-color: rgba(239, 68, 68, 0.12); border: 1px solid #dc2626; color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: 500;")
        kpi_layout.addWidget(self.pill_incomplete)

        kpi_layout.addStretch()
        layout.addWidget(self.kpi_card)

        # Preview Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Action / Status", "Manufacturer", "Part Number (MPN)", "Category",
            "Type", "Package", "Value", "Stock Qty"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.merge_btn = QPushButton("Merge New Records")
        self.merge_btn.setObjectName("primaryBtn")
        self.merge_btn.setEnabled(False)
        self.merge_btn.clicked.connect(self._execute_merge)
        btn_layout.addWidget(self.merge_btn)

        layout.addLayout(btn_layout)

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select External Omnix Database to Merge",
            os.getcwd(),
            "SQLite Database (*.db);;All Files (*)"
        )
        if not file_path:
            return

        self.file_lbl.setText(f"Source: {os.path.basename(file_path)} ({file_path})")
        self._analyze_file(file_path)

    def _analyze_file(self, file_path: str):
        analysis = DatabaseMergeService.analyze_merge(self.repository, file_path)
        self.analysis = analysis

        if not analysis.is_valid:
            QMessageBox.critical(self, "Invalid Database", analysis.validation_error or "Unknown error.")
            self.merge_btn.setEnabled(False)
            return

        # Update KPI pills
        self.pill_new.setText(f"New Components: {len(analysis.new_components)}")
        self.pill_duplicate.setText(f"Duplicates (Preserved): {len(analysis.duplicate_components)}")
        self.pill_conflict.setText(f"Conflicts (Skipped): {len(analysis.conflicting_components)}")
        self.pill_incomplete.setText(f"Incomplete (Skipped): {len(analysis.incomplete_components)}")

        # Render preview rows
        all_preview = []
        for c in analysis.new_components:
            all_preview.append(("NEW", c))
        for c in analysis.conflicting_components:
            all_preview.append(("CONFLICT", c))
        for c in analysis.duplicate_components:
            all_preview.append(("DUPLICATE", c))
        for c in analysis.incomplete_components:
            all_preview.append(("INCOMPLETE", c))

        self.table.setRowCount(len(all_preview))
        font_txt = QFont("Segoe UI", 9)
        font_code = QFont("Consolas", 9)

        for row_idx, (cat_type, c_data) in enumerate(all_preview):
            # 0. Status badge
            status_item = QTableWidgetItem()
            if cat_type == "NEW":
                status_item.setText("✅ INSERT")
                status_item.setForeground(QColor("#34d399"))
            elif cat_type == "CONFLICT":
                status_item.setText("⚠️ CONFLICT (Skip)")
                status_item.setForeground(QColor("#fbbf24"))
                reasons = "; ".join(c_data.get("conflict_reasons", []))
                status_item.setToolTip(f"Conflicting values: {reasons}")
            elif cat_type == "DUPLICATE":
                status_item.setText("ℹ️ DUPLICATE (Skip)")
                status_item.setForeground(QColor("#64748b"))
                status_item.setToolTip("Identical component exists in database.")
            else:
                status_item.setText("❌ INCOMPLETE (Skip)")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip("Missing Manufacturer or MPN.")

            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, status_item)

            self.table.setItem(row_idx, 1, QTableWidgetItem(c_data.get("manufacturer") or "—"))
            item_mpn = QTableWidgetItem(c_data.get("mpn") or "—")
            item_mpn.setFont(font_code)
            self.table.setItem(row_idx, 2, item_mpn)
            self.table.setItem(row_idx, 3, QTableWidgetItem(c_data.get("category") or "—"))
            self.table.setItem(row_idx, 4, QTableWidgetItem(c_data.get("type_technology") or "—"))
            self.table.setItem(row_idx, 5, QTableWidgetItem(c_data.get("package") or "—"))
            self.table.setItem(row_idx, 6, QTableWidgetItem(c_data.get("value") or "—"))
            item_qty = QTableWidgetItem(str(c_data.get("quantity_in_stock", 0)))
            item_qty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 7, item_qty)

        self.merge_btn.setEnabled(analysis.can_merge)

    def _execute_merge(self):
        if not self.analysis or not self.analysis.can_merge:
            return

        count = len(self.analysis.new_components)
        skipped_dups = len(self.analysis.duplicate_components)
        skipped_conflicts = len(self.analysis.conflicting_components)
        skipped_incomplete = len(self.analysis.incomplete_components)
        total_skipped = skipped_dups + skipped_conflicts + skipped_incomplete

        confirm = QMessageBox.question(
            self,
            "Confirm Database Merge",
            f"Are you sure you want to merge {count} new component(s) into your active database?\n\n"
            f"• Only new components with verified references in the target database will be imported.\n"
            f"• {total_skipped} non-eligible component record(s) ({skipped_dups} duplicate, {skipped_conflicts} conflict, {skipped_incomplete} incomplete) will be skipped.\n"
            f"• Reference data (Manufacturers, Categories, Types) will NOT be created automatically.\n"
            f"• An automatic safety backup will be created prior to merging.\n"
            f"• Existing records will NOT be overwritten.\n"
            f"• The external database file will NOT be modified.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ok, msg, meta = DatabaseMergeService.execute_merge(self.repository, self.analysis)
        if ok:
            QMessageBox.information(self, "Merge Successful", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Merge Failed", msg)
