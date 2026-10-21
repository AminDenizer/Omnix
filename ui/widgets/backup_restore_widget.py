"""
Omnix UI — Database Backup & Restore Management View
Governing Requirement: Section 6 Desktop Specification
"""

import os
import datetime
from typing import Optional, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QMessageBox,
    QScrollArea,
)

from core.inventory.repository import SqliteInventoryRepository
from core.inventory.backup import DatabaseBackupService
from core.inventory.exporter import InventoryExcelExporter


class DatabaseBackupRestoreWidget(QWidget):
    """Dedicated management page for database backups and safe restorations."""

    databaseRestored = pyqtSignal()
    restored_signal = databaseRestored

    def __init__(
        self,
        repository: Optional[Any] = None,
        parent: Optional[QWidget] = None,
        db_path: Optional[str] = None,
    ):
        super().__init__(parent)
        if isinstance(repository, str) and db_path is None:
            db_path = repository
            repository = None
        if repository is None and db_path:
            repo = SqliteInventoryRepository(db_path)
            try:
                repo.load()
            except Exception:
                pass
            repository = repo
        self.repository = repository
        self._init_ui()

    def set_repository(self, repository: Optional[Any] = None, db_path: Optional[str] = None):
        if isinstance(repository, str) and db_path is None:
            db_path = repository
            repository = None
        if repository is None and db_path:
            repo = SqliteInventoryRepository(db_path)
            try:
                repo.load()
            except Exception:
                pass
            repository = repo
        self.repository = repository
        self.refresh_status()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # Header Title
        title_lbl = QLabel("Export & Database Backup")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        main_layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Export inventory to Excel, or manage consistent, atomic backups of the authoritative SQLite store. "
            "Data includes components, stock policies, supplier links, and reference data."
        )
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        main_layout.addWidget(sub_lbl)

        # 1. Current Active Database Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("cardFrame")
        self.status_card.setStyleSheet("""
            QFrame#cardFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setSpacing(6)

        status_hdr = QLabel("Active Database Status")
        status_hdr.setStyleSheet("font-weight: bold; color: #f1f5f9; font-size: 12px;")
        status_layout.addWidget(status_hdr)

        self.db_path_lbl = QLabel()
        self.db_path_lbl.setStyleSheet("color: #38bdf8; font-family: 'Consolas', monospace; font-size: 11px;")
        status_layout.addWidget(self.db_path_lbl)

        self.db_stats_lbl = QLabel()
        self.db_stats_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        status_layout.addWidget(self.db_stats_lbl)

        main_layout.addWidget(self.status_card)

        # 2. Operations Grid (Excel Export, DB Backup, and DB Restore Cards)
        ops_layout = QHBoxLayout()
        ops_layout.setSpacing(14)

        # Card 1: Excel Export Card
        excel_card = QFrame()
        excel_card.setStyleSheet("""
            QFrame {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 14px;
            }
        """)
        excel_layout = QVBoxLayout(excel_card)
        excel_layout.setSpacing(10)

        excel_title = QLabel("📊 Export to Excel")
        excel_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
        excel_layout.addWidget(excel_title)

        excel_desc = QLabel(
            "Export the authoritative SQLite inventory and assembly groups to a customer-facing Excel workbook (.xlsx).\n\n"
            "• Generates exactly two worksheets: 'Inventory' & 'Assembly View'\n"
            "• Preserves MPN leading zeroes, groupings, and stock policies\n"
            "• Safe, read-only snapshot without altering database state"
        )
        excel_desc.setWordWrap(True)
        excel_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        excel_layout.addWidget(excel_desc)

        excel_layout.addStretch()

        self.export_excel_btn = QPushButton("Export to Excel...")
        self.export_excel_btn.setObjectName("exportToExcelBtn")
        self.export_excel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_excel_btn.setFixedHeight(34)
        self.export_excel_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 6px 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.export_excel_btn.clicked.connect(self._handle_export_excel)
        excel_layout.addWidget(self.export_excel_btn)

        ops_layout.addWidget(excel_card, 1)

        # Card 2: Export Database Backup Card
        export_card = QFrame()
        export_card.setStyleSheet("""
            QFrame {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 14px;
            }
        """)
        exp_layout = QVBoxLayout(export_card)
        exp_layout.setSpacing(10)

        exp_title = QLabel("💾 Export Database Backup")
        exp_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        exp_layout.addWidget(exp_title)

        exp_desc = QLabel(
            "Create an atomic, verified snapshot of all inventory records, stock policies, "
            "canonical reference data, and supplier links.\n\n"
            "• Preserves exact schema version and foreign key integrity\n"
            "• Excludes external Excel workbooks and session secrets\n"
            "• Safe to create while application is active"
        )
        exp_desc.setWordWrap(True)
        exp_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        exp_layout.addWidget(exp_desc)

        exp_layout.addStretch()

        self.export_btn = QPushButton("Export Database Backup...")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setFixedHeight(34)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 6px 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.export_btn.clicked.connect(self._handle_export_backup)
        exp_layout.addWidget(self.export_btn)

        ops_layout.addWidget(export_card, 1)

        # Restore Card
        restore_card = QFrame()
        restore_card.setStyleSheet("""
            QFrame {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 14px;
            }
        """)
        res_layout = QVBoxLayout(restore_card)
        res_layout.setSpacing(10)

        res_title = QLabel("♻️ Restore Database Backup")
        res_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        res_layout.addWidget(res_title)

        res_desc = QLabel(
            "Safely restore inventory data from an earlier Omnix backup file.\n\n"
            "• Deep structural and integrity verification before restore\n"
            "• Automatic pre-restore safety snapshot created before replacing data\n"
            "• Automatic rollback to safety snapshot if verification fails\n"
            "• Re-indexes and refreshes all active UI tables"
        )
        res_desc.setWordWrap(True)
        res_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        res_layout.addWidget(res_desc)

        res_layout.addStretch()

        self.restore_btn = QPushButton("Restore Database Backup...")
        self.restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_btn.setFixedHeight(34)
        self.restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #b45309;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 6px 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        self.restore_btn.clicked.connect(self._handle_restore_backup)
        res_layout.addWidget(self.restore_btn)

        ops_layout.addWidget(restore_card, 1)

        main_layout.addLayout(ops_layout)
        main_layout.addStretch()

        self.refresh_status()

    def refresh_status(self):
        """Update active database details and record statistics."""
        if not self.repository or not self.repository.is_loaded:
            self.db_path_lbl.setText("No active database loaded.")
            self.db_stats_lbl.setText("Please open or initialize a database.")
            self.export_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            if hasattr(self, "export_excel_btn"):
                self.export_excel_btn.setEnabled(False)
            return

        db_path = self.repository.file_path or "Unknown"
        self.db_path_lbl.setText(f"File: {db_path}")

        try:
            prod_cnt = len(self.repository.get_all_products())
            grp_cnt = len(self.repository.get_all_groups())
            prov_cnt = len(self.repository.get_all_providers(include_inactive=True))
            size_kb = os.path.getsize(db_path) / 1024.0 if os.path.exists(db_path) else 0

            self.db_stats_lbl.setText(
                f"● {prod_cnt} Components  |  "
                f"● {grp_cnt} Stock Policy Groups  |  "
                f"● {prov_cnt} Providers  |  "
                f"Size: {size_kb:.1f} KB"
            )
            self.export_btn.setEnabled(True)
            self.restore_btn.setEnabled(True)
            if hasattr(self, "export_excel_btn"):
                self.export_excel_btn.setEnabled(True)
        except Exception as e:
            self.db_stats_lbl.setText(f"Status check error: {e}")

    def _handle_export_excel(self):
        """Export live inventory and assembly groups to a customer-facing Excel workbook (.xlsx)."""
        if not self.repository or not isinstance(self.repository, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Database Required",
                "Excel export is only supported when operating with an active SQLite inventory database."
            )
            return

        suggested_path = os.path.join(os.getcwd(), "Inventory_Export.xlsx")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Inventory & Assembly View to Excel",
            suggested_path,
            "Excel Workbook (*.xlsx);;All Files (*)",
        )
        if not file_path:
            return

        try:
            exported_path = InventoryExcelExporter.export(self.repository, file_path)
            comp_count = len(self.repository.get_all_products())
            grp_count = len(self.repository.get_all_groups())
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {comp_count} individual components and "
                f"{grp_count} assembly groups with exactly 2 worksheets:\n"
                f"1. 'Inventory'\n"
                f"2. 'Assembly View'\n\n"
                f"Saved to: {exported_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export workbook:\n{e}")

    def _handle_export_backup(self):
        if not self.repository or not self.repository.is_loaded:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"omnix_backup_{timestamp}.db"
        suggested_path = os.path.join(os.getcwd(), default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Omnix Database Backup",
            suggested_path,
            "SQLite Database Backup (*.db *.sqlite);;All Files (*)",
        )
        if not file_path:
            return

        success, msg, meta = DatabaseBackupService.export_backup(
            self.repository.db_manager,
            file_path,
            overwrite=True,
        )

        if success:
            comp_cnt = meta.get("components", 0)
            policy_cnt = meta.get("stock_policies", 0)
            prov_cnt = meta.get("ref_providers", 0)
            size_kb = meta.get("file_size_bytes", 0) / 1024.0

            QMessageBox.information(
                self,
                "Backup Successful",
                f"Database backup created successfully!\n\n"
                f"• Components: {comp_cnt}\n"
                f"• Stock Policies: {policy_cnt}\n"
                f"• Providers: {prov_cnt}\n"
                f"• Size: {size_kb:.1f} KB\n\n"
                f"Destination: {file_path}",
            )
        else:
            QMessageBox.critical(self, "Backup Failed", f"Failed to export database backup:\n{msg}")

    def _handle_restore_backup(self):
        if not self.repository or not self.repository.is_loaded:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Omnix Database Backup to Restore",
            os.getcwd(),
            "SQLite Database Backup (*.db *.sqlite);;All Files (*)",
        )
        if not file_path:
            return

        # 1. Pre-validation
        is_valid, val_msg, meta = DatabaseBackupService.validate_backup_file(file_path)
        if not is_valid:
            QMessageBox.critical(
                self,
                "Invalid Backup File",
                f"The selected file cannot be restored:\n\n{val_msg}",
            )
            return

        # 2. Confirmation Dialog
        comp_cnt = meta.get("components", 0)
        policy_cnt = meta.get("stock_policies", 0)
        prov_cnt = meta.get("ref_providers", 0)

        confirm_msg = (
            f"Are you sure you want to restore this database backup?\n\n"
            f"Backup Summary:\n"
            f"• Components to restore: {comp_cnt}\n"
            f"• Stock Policies: {policy_cnt}\n"
            f"• Providers: {prov_cnt}\n\n"
            f"Note: An automatic safety snapshot of the active database will be created before restoring.\n"
            f"Current database data will be replaced."
        )

        reply = QMessageBox.question(
            self,
            "Confirm Database Restore",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 3. Apply Restore
        success, msg, res_meta = DatabaseBackupService.restore_backup(self.repository, file_path)
        if success:
            self.refresh_status()
            self.databaseRestored.emit()

            safety_p = res_meta.get("safety_snapshot_path", "")
            safety_note = f"\nSafety snapshot saved to:\n{safety_p}\n" if safety_p else ""

            QMessageBox.information(
                self,
                "Restore Successful",
                f"Database restored successfully from '{os.path.basename(file_path)}'!\n\n"
                f"• Restored Components: {res_meta.get('components', 0)}\n"
                f"• Restored Policies: {res_meta.get('stock_policies', 0)}\n"
                f"{safety_note}\nAll views have been refreshed.",
            )
        else:
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore database backup:\n\n{msg}",
            )
