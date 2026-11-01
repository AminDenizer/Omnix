"""
Omnix UI — Database Backup & Restore Management View
Governing Requirement: Section 4 — Backup & Restore Implementation (DOC-OMNIX-MPS-001)
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
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QDialog,
)

from core.inventory.repository import SqliteInventoryRepository
from core.inventory.backup import (
    DatabaseBackupService,
    get_default_starter_backup_path,
    BACKUP_TYPE_STARTER,
)
from core.inventory.exporter import InventoryExcelExporter
from settings_manager import settings


class DatabaseBackupRestoreWidget(QWidget):
    """Dedicated management page for database backups, restorations, and starter baselines."""

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
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # Header Title
        title_lbl = QLabel("Backup, Restore & Data Management")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        main_layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Export inventory to Excel, create portable versioned backups (.obk, .db), "
            "restore historical application environments safely, or initialize approved baseline reference data."
        )
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        main_layout.addWidget(sub_lbl)

        # 1. Current Active Database Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("statusCard")
        self.status_card.setStyleSheet("""
            QFrame#statusCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
            QFrame#statusCard QLabel {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """)
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(6)

        status_hdr = QLabel("Active Database Status")
        status_hdr.setStyleSheet("font-weight: bold; color: #f1f5f9; font-size: 12px;")
        status_layout.addWidget(status_hdr)

        self.db_path_lbl = QLabel()
        self.db_path_lbl.setStyleSheet("color: #38bdf8; font-family: 'Consolas', monospace; font-size: 11px;")
        self.db_path_lbl.setWordWrap(True)
        status_layout.addWidget(self.db_path_lbl)

        self.db_stats_lbl = QLabel()
        self.db_stats_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        status_layout.addWidget(self.db_stats_lbl)

        main_layout.addWidget(self.status_card)

        # 2. Operations Grid (2x2 Grid for balanced layout)
        ops_grid = QGridLayout()
        ops_grid.setSpacing(14)
        ops_grid.setRowStretch(0, 1)
        ops_grid.setRowStretch(1, 1)
        ops_grid.setColumnStretch(0, 1)
        ops_grid.setColumnStretch(1, 1)

        card_style = """
            QFrame[card="operation"] {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QFrame[card="operation"] QLabel {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """

        # Card 1: Excel Export Card
        excel_card = QFrame()
        excel_card.setProperty("card", "operation")
        excel_card.setStyleSheet(card_style)
        excel_card.setMinimumHeight(210)
        excel_layout = QVBoxLayout(excel_card)
        excel_layout.setContentsMargins(16, 16, 16, 16)
        excel_layout.setSpacing(10)

        excel_title = QLabel("📊 Export to Excel")
        excel_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
        excel_layout.addWidget(excel_title)

        excel_desc = QLabel(
            "Export the authoritative SQLite inventory to a customer-facing Excel workbook (.xlsx).\n\n"
            "• Generates exactly one worksheet: 'Inventory'\n"
            "• Preserves MPN leading zeroes, groupings, and stock policies\n"
            "• Strictly independent of application backups; safe read-only snapshot"
        )
        excel_desc.setWordWrap(True)
        excel_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.45;")
        excel_layout.addWidget(excel_desc)

        excel_layout.addStretch(1)

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

        ops_grid.addWidget(excel_card, 0, 0)

        # Card 2: Export Application Backup Card
        export_card = QFrame()
        export_card.setProperty("card", "operation")
        export_card.setStyleSheet(card_style)
        export_card.setMinimumHeight(210)
        exp_layout = QVBoxLayout(export_card)
        exp_layout.setContentsMargins(16, 16, 16, 16)
        exp_layout.setSpacing(10)

        exp_title = QLabel("💾 Export Application Backup")
        exp_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        exp_layout.addWidget(exp_title)

        exp_desc = QLabel(
            "Create a versioned Omnix Backup Archive (.obk) containing all database entities.\n\n"
            "• Preserves components, policies, supplier links, and reference data\n"
            "• Application settings and credentials remain independent of backups\n"
            "• Supports backward-compatible SQLite database export (.db)"
        )
        exp_desc.setWordWrap(True)
        exp_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.45;")
        exp_layout.addWidget(exp_desc)

        exp_layout.addStretch(1)

        self.export_btn = QPushButton("Export Backup...")
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

        ops_grid.addWidget(export_card, 0, 1)

        # Card 3: Restore Application Backup Card
        restore_card = QFrame()
        restore_card.setProperty("card", "operation")
        restore_card.setStyleSheet(card_style)
        restore_card.setMinimumHeight(210)
        res_layout = QVBoxLayout(restore_card)
        res_layout.setContentsMargins(16, 16, 16, 16)
        res_layout.setSpacing(10)

        res_title = QLabel("♻️ Restore Application Backup")
        res_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        res_layout.addWidget(res_title)

        res_desc = QLabel(
            "Safely restore an Omnix environment from a backup package (.obk, .zip) or legacy database (.db).\n\n"
            "• Deep structural and integrity verification before replacing data\n"
            "• Automatic pre-restore safety snapshot created with zero data loss guarantee\n"
            "• Automatic rollback to safety snapshot if verification fails"
        )
        res_desc.setWordWrap(True)
        res_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.45;")
        res_layout.addWidget(res_desc)

        res_layout.addStretch(1)

        self.restore_btn = QPushButton("Restore Backup...")
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

        ops_grid.addWidget(restore_card, 1, 0)

        # Card 4: Starter Reference Data Card
        starter_card = QFrame()
        starter_card.setProperty("card", "operation")
        starter_card.setStyleSheet(card_style)
        starter_card.setMinimumHeight(210)
        starter_layout = QVBoxLayout(starter_card)
        starter_layout.setContentsMargins(16, 16, 16, 16)
        starter_layout.setSpacing(10)

        starter_title = QLabel("🚀 Starter Reference Data")
        starter_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #818cf8;")
        starter_layout.addWidget(starter_title)

        starter_desc = QLabel(
            "Initialize or merge approved baseline reference data (categories, types, manufacturers, providers).\n\n"
            "• Safe Merge: Adds missing reference records without altering existing inventory\n"
            "• Clean Reset: Replaces database with clean baseline (empty inventory)\n"
            "• Applied only through explicit action; never re-imports on launch"
        )
        starter_desc.setWordWrap(True)
        starter_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.45;")
        starter_layout.addWidget(starter_desc)

        starter_layout.addStretch(1)

        self.starter_btn = QPushButton("Apply Starter Baseline...")
        self.starter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.starter_btn.setFixedHeight(34)
        self.starter_btn.setStyleSheet("""
            QPushButton {
                background-color: #4f46e5;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 6px 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #4338ca;
            }
        """)
        self.starter_btn.clicked.connect(self._handle_apply_starter)
        starter_layout.addWidget(self.starter_btn)

        ops_grid.addWidget(starter_card, 1, 1)

        # Card 5: Bind / Merge Database Card
        merge_card = QFrame()
        merge_card.setProperty("card", "operation")
        merge_card.setStyleSheet(card_style)
        merge_card.setMinimumHeight(210)
        merge_layout = QVBoxLayout(merge_card)
        merge_layout.setContentsMargins(16, 16, 16, 16)
        merge_layout.setSpacing(10)

        merge_title = QLabel("🔀 Bind / Merge Database")
        merge_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
        merge_layout.addWidget(merge_title)

        merge_desc = QLabel(
            "Non-destructively bind and reconcile an external SQLite database into active inventory.\n\n"
            "• Imports only verified NEW components and their supplier links with fresh IDs\n"
            "• Safely skips duplicate, conflicting, and incomplete components without overwriting existing data\n"
            "• Mandates pre-merge safety backup and guarantees atomic rollback on error"
        )
        merge_desc.setWordWrap(True)
        merge_desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.45;")
        merge_layout.addWidget(merge_desc)

        merge_layout.addStretch(1)

        self.merge_db_btn = QPushButton("Bind / Merge Database...")
        self.merge_db_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.merge_db_btn.setFixedHeight(34)
        self.merge_db_btn.setStyleSheet("""
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
                background-color: #10b981;
            }
        """)
        self.merge_db_btn.clicked.connect(self._handle_merge_database)
        merge_layout.addWidget(self.merge_db_btn)

        ops_grid.addWidget(merge_card, 2, 0)

        main_layout.addLayout(ops_grid, 1)

        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area, 1)

        self.refresh_status()

    def refresh_status(self):
        """Update active database details and record statistics."""
        if not self.repository or not self.repository.is_loaded:
            self.db_path_lbl.setText("No active database loaded.")
            self.db_stats_lbl.setText("Please open or initialize a database.")
            self.export_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            if hasattr(self, "starter_btn"):
                self.starter_btn.setEnabled(False)
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
            if hasattr(self, "starter_btn"):
                self.starter_btn.setEnabled(True)
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
            "Export Inventory to Excel",
            suggested_path,
            "Excel Workbook (*.xlsx);;All Files (*)",
        )
        if not file_path:
            return

        try:
            exported_path = InventoryExcelExporter.export(self.repository, file_path)
            comp_count = len(self.repository.get_all_products())
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {comp_count} individual components to worksheet 'Inventory'.\n\n"
                f"Saved to: {exported_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export workbook:\n{e}")

    def _handle_export_backup(self):
        """Export a portable Omnix Backup Archive (.obk) or SQLite snapshot (.db)."""
        if not self.repository or not self.repository.is_loaded:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_path = os.path.join(os.getcwd(), f"omnix_backup_{timestamp}.obk")

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Omnix Backup",
            suggested_path,
            "Omnix Backup Archive (*.obk);;SQLite Database Backup (*.db *.sqlite);;All Files (*)",
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".db", ".sqlite"):
            success, msg, meta = DatabaseBackupService.export_backup(
                self.repository.db_manager,
                file_path,
                overwrite=True,
            )
        else:
            # Ensure .obk extension if none provided
            if not ext:
                file_path = f"{file_path}.obk"
            success, msg, meta = DatabaseBackupService.export_full_backup(
                self.repository,
                file_path,
                overwrite=True,
                description="Omnix User Application Backup",
            )

        if success:
            comp_cnt = meta.get("components", 0)
            policy_cnt = meta.get("stock_policies", 0)
            prov_cnt = meta.get("ref_providers", 0)
            size_kb = meta.get("file_size_bytes", 0) / 1024.0
            b_type = meta.get("backup_type", "full")

            QMessageBox.information(
                self,
                "Backup Successful",
                f"Omnix backup created successfully!\n\n"
                f"• Format: {b_type.upper()}\n"
                f"• Components: {comp_cnt}\n"
                f"• Stock Policies: {policy_cnt}\n"
                f"• Providers: {prov_cnt}\n"
                f"• Size: {size_kb:.1f} KB\n\n"
                f"Destination: {file_path}",
            )
        else:
            QMessageBox.critical(self, "Backup Failed", f"Failed to export backup:\n{msg}")

    def _handle_restore_backup(self):
        """Restore an Omnix Backup Archive (.obk, .zip) or legacy SQLite backup (.db)."""
        if not self.repository or not self.repository.is_loaded:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Omnix Backup to Restore",
            os.getcwd(),
            "Omnix Backup (*.obk *.zip *.db *.sqlite);;Omnix Backup Archive (*.obk *.zip);;SQLite Database Backup (*.db *.sqlite);;All Files (*)",
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
        b_type = meta.get("backup_type", "full")

        confirm_msg = (
            f"Are you sure you want to restore this backup?\n\n"
            f"Backup Summary:\n"
            f"• Backup Type: {b_type.upper()}\n"
            f"• Components to restore: {comp_cnt}\n"
            f"• Stock Policies: {policy_cnt}\n"
            f"• Providers: {prov_cnt}\n\n"
            f"Note: An automatic safety snapshot of the active database will be created before restoring.\n"
            f"Current database data will be replaced. Local application settings and credentials remain unchanged."
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
        success, msg, res_meta = DatabaseBackupService.restore_backup(
            self.repository,
            file_path,
        )
        if success:
            self.refresh_status()
            self.databaseRestored.emit()

            safety_p = res_meta.get("safety_snapshot_path", "")
            safety_note = f"\nSafety snapshot saved to:\n{safety_p}\n" if safety_p else ""

            QMessageBox.information(
                self,
                "Restore Successful",
                f"Backup restored successfully from '{os.path.basename(file_path)}'!\n\n"
                f"• Restored Components: {res_meta.get('components', 0)}\n"
                f"• Restored Policies: {res_meta.get('stock_policies', 0)}\n"
                f"{safety_note}\nAll views have been refreshed.",
            )
        else:
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore backup:\n\n{msg}",
            )

    def _handle_apply_starter(self):
        """Apply approved baseline reference data for fresh installations or merging."""
        if not self.repository or not self.repository.is_loaded:
            return

        starter_path = get_default_starter_backup_path()
        if not starter_path or not os.path.exists(starter_path):
            starter_path, _ = QFileDialog.getOpenFileName(
                self,
                "Locate Starter Reference Data Archive",
                os.getcwd(),
                "Omnix Backup Archive (*.obk *.zip *.db);;All Files (*)",
            )
            if not starter_path:
                return

        # Pre-validate
        is_valid, val_msg, meta = DatabaseBackupService.validate_backup_file(starter_path)
        if not is_valid:
            QMessageBox.critical(
                self,
                "Invalid Starter Backup",
                f"The starter baseline archive failed validation:\n\n{val_msg}",
            )
            return

        mfr_cnt = meta.get("ref_manufacturers", 0)
        cat_cnt = meta.get("ref_categories", 0)
        type_cnt = meta.get("ref_types", 0)
        prov_cnt = meta.get("ref_providers", 0)

        # Strategy Selection Dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Apply Starter Reference Data")
        msg_box.setText("Choose how you would like to apply the baseline electronics reference data:")
        msg_box.setInformativeText(
            f"Baseline Package Contains:\n"
            f"• {mfr_cnt} Manufacturers\n"
            f"• {cat_cnt} Categories\n"
            f"• {type_cnt} Technology Types\n"
            f"• {prov_cnt} Providers\n\n"
            f"1. 'Merge Reference' (Safe): Adds missing reference categories, types, and manufacturers without modifying your inventory or stock policies.\n\n"
            f"2. 'Clean Reset' (Destructive): Replaces active database with a clean baseline, wiping all inventory components and stock policies."
        )
        msg_box.setIcon(QMessageBox.Icon.Question)
        merge_btn = msg_box.addButton("Merge Reference (Safe)", QMessageBox.ButtonRole.AcceptRole)
        reset_btn = msg_box.addButton("Clean Reset (Destructive)", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(merge_btn)
        msg_box.setEscapeButton(cancel_btn)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == cancel_btn or clicked is None:
            return

        strategy = "merge_reference"
        if clicked == reset_btn:
            confirm_reply = QMessageBox.warning(
                self,
                "Confirm Clean Baseline Reset",
                "WARNING: Clean Reset will delete all current inventory components and stock policies in the active database!\n\n"
                "A pre-restore safety snapshot will be created before resetting.\n\n"
                "Are you sure you want to proceed with Clean Reset?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm_reply != QMessageBox.StandardButton.Yes:
                return
            strategy = "clean_reset"

        success, msg, res_meta = DatabaseBackupService.apply_starter_backup(
            self.repository,
            starter_path=starter_path,
            strategy=strategy,
        )

        if success:
            self.refresh_status()
            self.databaseRestored.emit()
            if strategy == "merge_reference":
                info_msg = (
                    f"Starter baseline reference data merged successfully!\n\n"
                    f"• Added Manufacturers: {res_meta.get('added_manufacturers', 0)}\n"
                    f"• Added Categories: {res_meta.get('added_categories', 0)}\n"
                    f"• Added Types: {res_meta.get('added_types', 0)}\n"
                    f"• Added Providers: {res_meta.get('added_providers', 0)}\n\n"
                    f"Existing inventory components and policies remain intact."
                )
            else:
                info_msg = (
                    f"Clean starter baseline restored successfully!\n\n"
                    f"• Active database reset to approved reference baseline.\n"
                    f"• Safety snapshot saved to: {res_meta.get('safety_snapshot_path', 'safety_backups')}"
                )
            QMessageBox.information(self, "Starter Baseline Applied", info_msg)
        else:
            QMessageBox.critical(self, "Failed to Apply Starter Baseline", f"Operation failed:\n\n{msg}")

    def _handle_merge_database(self):
        """Open DatabaseMergeDialog to non-destructively merge external SQLite database."""
        if not self.repository or not isinstance(self.repository, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Database Required",
                "Database merge requires an active SQLite inventory repository."
            )
            return

        from ui.dialogs.database_merge_dialog import DatabaseMergeDialog
        dlg = DatabaseMergeDialog(repository=self.repository, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_status()
            self.databaseRestored.emit()
