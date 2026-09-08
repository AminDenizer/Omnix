import os
import sys
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QStatusBar, QMenu, QMessageBox,
    QTabWidget, QPushButton
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut, QIcon, QPixmap

from config import APP_NAME, APP_SUBTITLE, get_app_dir, get_bundle_dir
from excel_loader import ExcelDataLoader, find_local_excel_file, normalize_string
from settings_manager import settings
from ui.widgets import (
    InventoryTableWidget,
    StockCellDelegate,
    StatsRibbonWidget,
    FilterBarWidget,
    BOMAuditWidget
)
from ui.dialogs import SettingsDialog, OrderPreviewDialog


class MainWindow(QMainWindow):
    """
    Omnix Main Window:
    - Tab 1: Inventory & Stock Management with live search and editable thresholds.
    - Tab 2: Altium BOM Project Assembly Auditor & Shortage Calculator.
    - Automated Lion Electronic purchasing integration.
    """

    def __init__(self, default_file: str = None):
        super().__init__()
        self.excel = ExcelDataLoader()
        self.current_filtered_rows = []
        self.search_query = ""
        self.show_only_incomplete = False
        self._is_force_closing = False
        self._is_updating_table = False

        self.setWindowTitle(f"{APP_NAME} | Inventory & Altium BOM Assembly Auditor")
        self.resize(1260, 780)
        self.setMinimumSize(960, 620)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Set application window icon
        icons_dir = os.path.join(get_bundle_dir(), "ui", "icons")
        ico_path = os.path.join(icons_dir, "app_logo.ico")
        png_path = os.path.join(icons_dir, "app_logo.png")
        win_icon = QIcon()
        if os.path.exists(ico_path):
            win_icon.addFile(ico_path)
        if os.path.exists(png_path):
            win_icon.addFile(png_path)
        if not win_icon.isNull():
            self.setWindowIcon(win_icon)

        self._init_ui()
        self._setup_shortcuts()
        self._setup_statusbar()

        # Automatic detection of the Excel database file in the app directory
        target_file = default_file or find_local_excel_file(get_app_dir())
        if target_file and os.path.exists(target_file):
            self.load_excel_file(target_file)
        else:
            self.excel.file_path = None
            self.excel.file_name = ""
            self.excel.headers = []
            self.excel.rows = []
            self.excel._normalized_rows = []
            self.current_filtered_rows = []
            self._update_table_display()
            self._update_stats_ribbon()
            self.status_state_lbl.setText("● No Excel file in directory")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")

        # Focus search and trigger startup shortage audit
        QTimer.singleShot(150, self._focus_search)
        QTimer.singleShot(700, self._check_startup_shortages)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 8)

        # 1. Top Header with Logo, Title, and Settings Button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 2)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(10)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        logo_lbl = QLabel()
        logo_path = os.path.join(get_bundle_dir(), "ui", "icons", "app_logo.png")
        if os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path).scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(logo_pix)
        brand_layout.addWidget(logo_lbl)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setSpacing(2)
        brand_text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        brand_title = QLabel(APP_NAME)
        brand_title.setObjectName("brandTitle")
        brand_sub = QLabel("Electronic Components Database & Altium BOM Assembly Auditor")
        brand_sub.setObjectName("brandSubtitle")
        brand_text_layout.addWidget(brand_title)
        brand_text_layout.addWidget(brand_sub)
        brand_layout.addLayout(brand_text_layout)

        header_layout.addLayout(brand_layout)
        header_layout.addStretch()

        # Settings Button
        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setObjectName("secondaryBtn")
        self.settings_btn.clicked.connect(self._open_settings)
        header_layout.addWidget(self.settings_btn)

        main_layout.addLayout(header_layout)

        # 2. Main Dual-Tab Widget Container
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Tab 1: Inventory & Stock Management
        self.inventory_tab = QWidget()
        inv_layout = QVBoxLayout(self.inventory_tab)
        inv_layout.setContentsMargins(8, 10, 8, 6)
        inv_layout.setSpacing(10)

        self.stats_ribbon = StatsRibbonWidget()
        self.stats_ribbon.orderShortagesRequested.connect(self._open_inventory_order_dialog)
        self.stats_ribbon.incompleteFilterRequested.connect(self._toggle_incomplete_filter)
        inv_layout.addWidget(self.stats_ribbon)

        self.filter_bar = FilterBarWidget()
        self.search_input = self.filter_bar.search_input
        self.filter_bar.searchChanged.connect(self._on_search_changed)
        inv_layout.addWidget(self.filter_bar)

        self.table = InventoryTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.itemChanged.connect(self._on_table_cell_changed)
        inv_layout.addWidget(self.table)

        self.tabs.addTab(self.inventory_tab, "📦 Inventory & Stock Control")

        # Tab 2: Altium BOM Project Assembly Auditor
        self.bom_audit_widget = BOMAuditWidget(self.excel, self)
        self.tabs.addTab(self.bom_audit_widget, "📋 Altium BOM Project Auditor")

        main_layout.addWidget(self.tabs)

    def _setup_statusbar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.status_shortcuts_lbl = QLabel(
            "<b>[/]</b> Search &nbsp;&nbsp;|&nbsp;&nbsp; "
            "<b>[Esc]</b> Deselect / Clear &nbsp;&nbsp;|&nbsp;&nbsp; "
            "<b>[F5]</b> Reload Database &nbsp;&nbsp;|&nbsp;&nbsp; "
            "<b>[Ctrl+Q]</b> Exit"
        )
        self.status_shortcuts_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.status_shortcuts_lbl.setStyleSheet("color: #64748b; font-size: 11px; padding-left: 8px;")
        status_bar.addWidget(self.status_shortcuts_lbl, 1)

        self.status_state_lbl = QLabel("● Ready")
        self.status_state_lbl.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px; padding-right: 12px;")
        status_bar.addPermanentWidget(self.status_state_lbl)

    def _setup_shortcuts(self):
        slash_sc = QShortcut(QKeySequence(Qt.Key.Key_Slash), self)
        slash_sc.activated.connect(self._focus_search)

        ctrl_f = QShortcut(QKeySequence("Ctrl+F"), self)
        ctrl_f.activated.connect(self._focus_search)

        f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        f5.activated.connect(self.reload_database)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.handle_escape_key)

        ctrl_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        ctrl_q.activated.connect(self.close)

    def _focus_search(self):
        if self.tabs.currentIndex() == 0:
            self.search_input.setFocus()
            self.search_input.selectAll()

    def handle_escape_key(self):
        """Multi-stage Escape key handler."""
        # 1. If search input has text or focus in Tab 1
        if self.tabs.currentIndex() == 0:
            has_search_text = bool(self.search_input.text().strip())
            is_search_focused = self.search_input.hasFocus()

            if has_search_text or is_search_focused:
                if has_search_text:
                    self.search_input.clear()
                self.search_input.clearFocus()
                self.table.setFocus()
                return

            # 2. If incomplete filter is currently active
            if self.show_only_incomplete:
                self.show_only_incomplete = False
                self.stats_ribbon.set_incomplete_active(False)
                self._filter_and_render()
                return

            # 3. If table row is selected
            if len(self.table.selectedItems()) > 0 or self.table.currentItem() is not None:
                self.table.clearSelection()
                self.table.setCurrentItem(None)
                return

        # 4. Prompt exit confirmation dialog
        self._prompt_exit_confirmation()

    def _prompt_exit_confirmation(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Exit Confirmation")
        msg_box.setText("Do you want to exit Omnix?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_btn)

        yes_btn.setObjectName("dangerBtn")
        no_btn.setObjectName("secondaryBtn")

        msg_box.exec()
        if msg_box.clickedButton() == yes_btn:
            self._is_force_closing = True
            QApplication.quit()

    def closeEvent(self, event):
        if self._is_force_closing:
            event.accept()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Exit Confirmation")
        msg_box.setText("Do you want to exit Omnix?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_btn)

        yes_btn.setObjectName("dangerBtn")
        no_btn.setObjectName("secondaryBtn")

        msg_box.exec()
        if msg_box.clickedButton() == yes_btn:
            self._is_force_closing = True
            event.accept()
        else:
            event.ignore()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_stock_incremented_callback(self):
        """Callback when order payment is confirmed and inventory is incremented."""
        self._filter_and_render()

    def _check_startup_shortages(self):
        """Check if any inventory items are below minimum threshold on startup and alert the user."""
        if not settings.get("auto_check_startup_shortage", True):
            return
        if self.excel.total_rows == 0:
            return

        shortages = self.excel.get_shortage_items()
        if shortages:
            dlg = OrderPreviewDialog(
                orderable_items=shortages,
                source_title=f"Startup Inventory Shortage Alert ({len(shortages)} Items Low)",
                inventory_loader=self.excel,
                on_stock_updated=self._on_stock_incremented_callback,
                parent=self
            )
            dlg.exec()

    def load_excel_file(self, file_path: str):
        success, msg = self.excel.load_file(file_path)
        if not success:
            self.status_state_lbl.setText(f"● Error: {msg}")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")
            self._update_table_display()
            return

        self.search_query = ""
        self.search_input.clear()
        self._filter_and_render()

        self.status_state_lbl.setText(f"● Database: {self.excel.file_name}")
        self.status_state_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")

    def reload_database(self):
        target_file = find_local_excel_file(get_app_dir())
        if target_file and os.path.exists(target_file):
            self.load_excel_file(target_file)
        else:
            self.excel.file_path = None
            self.excel.file_name = ""
            self.excel.headers = []
            self.excel.rows = []
            self.excel._normalized_rows = []
            self.current_filtered_rows = []
            self._update_table_display()
            self._update_stats_ribbon()
            self.status_state_lbl.setText("● Inventory.xlsx not found")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")

    def _on_search_changed(self, query: str):
        self.search_query = query.strip()
        self._filter_and_render()

    def _toggle_incomplete_filter(self):
        self.show_only_incomplete = not self.show_only_incomplete
        self.stats_ribbon.set_incomplete_active(self.show_only_incomplete)
        self._filter_and_render()

    def _filter_and_render(self):
        if self.show_only_incomplete:
            incomplete_records = self.excel.get_incomplete_records()
            incomplete_rows = [(orig_idx, row_data) for orig_idx, row_data, _ in incomplete_records]
            if self.search_query:
                terms = [normalize_string(t) for t in self.search_query.split() if t.strip()]
                filtered = []
                for orig_idx, row_data in incomplete_rows:
                    searchable_str = " ".join(normalize_string(val) for val in row_data)
                    if all(term in searchable_str for term in terms):
                        filtered.append((orig_idx, row_data))
                self.current_filtered_rows = filtered
            else:
                self.current_filtered_rows = incomplete_rows
        else:
            self.current_filtered_rows = self.excel.filter_rows(self.search_query)

        self._update_table_display()
        self._update_stats_ribbon()

    def _update_stats_ribbon(self):
        total_rows = self.excel.total_rows
        filtered_rows = len(self.current_filtered_rows)
        total_cols = self.excel.total_columns
        file_name = self.excel.file_name
        shortages = self.excel.get_shortage_items() if total_rows > 0 else []
        incomplete = self.excel.get_incomplete_records() if total_rows > 0 else []
        self.stats_ribbon.update_stats(
            total_rows,
            filtered_rows,
            total_cols,
            file_name,
            shortage_count=len(shortages),
            incomplete_count=len(incomplete)
        )

    def _open_inventory_order_dialog(self):
        if self.excel.total_rows == 0:
            return
        shortages = self.excel.get_shortage_items()
        if not shortages:
            QMessageBox.information(
                self,
                "No Shortages Detected",
                "All inventory items currently meet or exceed their configured minimum stock thresholds."
            )
            return

        dlg = OrderPreviewDialog(
            orderable_items=shortages,
            source_title=f"Inventory Shortage Purchase ({len(shortages)} Low Stock Items)",
            inventory_loader=self.excel,
            on_stock_updated=self._on_stock_incremented_callback,
            parent=self
        )
        dlg.exec()

    def _update_table_display(self):
        """Populate the QTableWidget with dynamic headers and editable threshold cells."""
        self._is_updating_table = True
        headers = self.excel.headers
        col_count = len(headers)

        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels(headers)

        rows = self.current_filtered_rows
        row_count = len(rows)
        self.table.setRowCount(row_count)

        if not headers or row_count == 0:
            is_filter_active = bool((self.search_query or self.show_only_incomplete) and self.excel.total_rows > 0)
            self.table.update_empty_state(True, is_filter_active=is_filter_active)
            self._is_updating_table = False
            return

        self.table.update_empty_state(False)

        font_data = QFont("Segoe UI", 10)
        font_numbers = QFont("Consolas", 10)

        # Detect editable column indexes (Min Stock and Target Stock)
        min_stock_idx = self.excel.get_column_index(["min stock", "min_stock", "حد کسر"])
        target_stock_idx = self.excel.get_column_index(["target stock", "target_stock", "تعداد سفارش"])
        stock_idx = self.excel.get_column_index(["quantity in stock", "stock", "quantity", "موجودی"])

        if min_stock_idx is not None:
            self.table.setItemDelegateForColumn(min_stock_idx, StockCellDelegate(self.table))
        if target_stock_idx is not None:
            self.table.setItemDelegateForColumn(target_stock_idx, StockCellDelegate(self.table))

        for visual_row_idx, (orig_row_idx, row_data) in enumerate(rows):
            for col_idx in range(col_count):
                val_str = row_data[col_idx] if col_idx < len(row_data) else ""
                item = QTableWidgetItem(val_str)
                item.setToolTip(val_str)
                item.setData(Qt.ItemDataRole.UserRole, orig_row_idx)

                # Editable flags for Min Stock and Target Stock
                if col_idx in [min_stock_idx, target_stock_idx]:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(QColor("rgba(56, 189, 248, 0.08)"))  # Soft cyan tint for editable cells
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Alignment and Font
                if val_str.isdigit() or (val_str.replace('.', '', 1).isdigit() and val_str.count('.') < 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                # Color Highlights & Warning Badges
                lower_val = val_str.lower().strip()
                if lower_val in ["?", "؟"]:
                    item.setText("⚠️ Missing")
                    item.setForeground(QColor("#fbbf24"))  # Warning amber
                    item.setBackground(QColor("rgba(245, 158, 11, 0.15)"))
                    item.setToolTip(f"Column '{headers[col_idx] if col_idx < len(headers) else ''}': Missing or unknown value (?)")
                elif lower_val.startswith("http://") or lower_val.startswith("https://"):
                    item.setForeground(QColor("#38bdf8"))  # Neon cyan link
                elif col_idx == stock_idx and stock_idx is not None:
                    # Check stock vs min stock
                    try:
                        cur_stk = float(val_str) if val_str else 0.0
                        min_stk_str = row_data[min_stock_idx] if min_stock_idx is not None and min_stock_idx < len(row_data) else "0"
                        min_stk = float(min_stk_str) if min_stk_str else 0.0
                        if min_stk > 0 and cur_stk <= min_stk:
                            item.setForeground(QColor("#f87171"))  # Red warning for low stock
                        else:
                            item.setForeground(QColor("#34d399"))  # Normal stock green
                    except ValueError:
                        item.setForeground(QColor("#fbbf24"))
                else:
                    item.setForeground(QColor("#f8fafc"))

                self.table.setItem(visual_row_idx, col_idx, item)

        # Header resize modes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        for c in range(col_count):
            self.table.resizeColumnToContents(c)
            current_width = self.table.columnWidth(c)
            if current_width < 100:
                self.table.setColumnWidth(c, 100)
            elif current_width > 360:
                self.table.setColumnWidth(c, 360)

        self.table.setSortingEnabled(True)
        self._is_updating_table = False

    def _on_table_cell_changed(self, item: QTableWidgetItem):
        """Automatically saves edited cell value (Min Stock / Target Stock) back to Excel on disk."""
        if self._is_updating_table or not item:
            return

        col_idx = item.column()
        orig_row_idx = item.data(Qt.ItemDataRole.UserRole)
        new_val = item.text().strip()

        if orig_row_idx is not None:
            ok = self.excel.save_cell_value(orig_row_idx, col_idx, new_val)
            if ok:
                self._update_stats_ribbon()
                self.status_state_lbl.setText("● Saved to Excel")
                self.status_state_lbl.setStyleSheet("color: #34d399; font-weight: bold;")
                QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {self.excel.file_name}"))

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        val = item.text().strip()
        if val.startswith("http://") or val.startswith("https://"):
            webbrowser.open(val)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        val = item.text().strip()

        copy_act = menu.addAction("📋 Copy Cell Value")
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(val))

        row_idx = item.row()
        copy_row_act = menu.addAction("📑 Copy Entire Row")
        def _copy_row():
            cols = [self.table.item(row_idx, c).text() if self.table.item(row_idx, c) else "" for c in range(self.table.columnCount())]
            QApplication.clipboard().setText("\t".join(cols))
        copy_row_act.triggered.connect(_copy_row)

        if val.startswith("http://") or val.startswith("https://"):
            menu.addSeparator()
            open_link_act = menu.addAction("🌐 Open Link in Web Browser")
            open_link_act.triggered.connect(lambda: webbrowser.open(val))

        menu.exec(self.table.viewport().mapToGlobal(pos))
