import os
import sys
import webbrowser
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QStatusBar, QMenu, QMessageBox, QDialog,
    QTabWidget, QPushButton, QSplitter, QFrame, QToolButton
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut, QIcon, QPixmap

from config import APP_NAME, APP_SUBTITLE, get_app_dir, get_bundle_dir
from excel_loader import ExcelDataLoader, find_local_excel_file, normalize_string
from core.inventory import (
    ExcelInventoryRepository,
    StockPolicyGroup,
    InventoryProduct,
    resolve_inventory_database_path,
)
from settings_manager import settings
from ui.widgets import (
    InventoryTableWidget,
    StockCellDelegate,
    StatsRibbonWidget,
    FilterBarWidget,
    BOMAuditWidget,
    AssemblyPreparationWidget
)
from ui.dialogs import (
    SettingsDialog,
    OrderPreviewDialog,
    QuickOrderDialog,
    PolicyEditDialog,
)


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
        self.inventory_repo = ExcelInventoryRepository()
        self.current_filtered_groups: list[StockPolicyGroup] = []
        self.current_filtered_rows = []
        self.search_query = ""
        self.show_only_incomplete = False
        self._is_force_closing = False
        self._is_updating_table = False
        self._last_products_panel_height = 220
        self._last_splitter_sizes: Optional[list[int]] = None
        self._inventory_database_path: Optional[str] = None

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

        # Automatic detection of the Inventory database file
        if default_file == "":
            target_file = None
        else:
            target_file = default_file or resolve_inventory_database_path()

        if target_file and os.path.exists(target_file):
            self._inventory_database_path = target_file
            self.load_inventory_database(target_file)
        else:
            legacy_file = find_local_excel_file(get_app_dir())
            if legacy_file and os.path.exists(legacy_file):
                self.load_excel_file(legacy_file)
            else:
                self.excel.file_path = None
                self.excel.file_name = ""
                self.excel.headers = []
                self.excel.rows = []
                self.excel._normalized_rows = []
                self.current_filtered_rows = []
                self.current_filtered_groups = []
                self._update_table_display()
                self._update_stats_ribbon()
                self.status_state_lbl.setText("● No inventory database found")
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

        # Quick Order Button (preserved for keyboard shortcuts and test compatibility; removed from header)
        self.quick_order_btn = QPushButton("⚡ Quick Order")
        self.quick_order_btn.setVisible(False)
        self.quick_order_btn.clicked.connect(self._open_quick_order)

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

        # Splitter with Policy Groups (top) and Associated Physical Products (bottom)
        self.inventory_splitter = QSplitter(Qt.Orientation.Vertical)
        self.inventory_splitter.setChildrenCollapsible(False)

        # Top section: Stock Policy Groups
        self.policy_frame = QFrame()
        policy_layout = QVBoxLayout(self.policy_frame)
        policy_layout.setContentsMargins(0, 0, 0, 0)
        policy_layout.setSpacing(4)

        policy_hdr_layout = QHBoxLayout()
        self.policy_title_lbl = QLabel("📊 Stock Policy Groups (Authoritative Group & Stock Source)")
        self.policy_title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        policy_hdr_layout.addWidget(self.policy_title_lbl)
        policy_hdr_layout.addStretch()
        policy_layout.addLayout(policy_hdr_layout)

        self.table = InventoryTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_group_selection_changed)
        self.table.itemChanged.connect(self._on_table_cell_changed)
        policy_layout.addWidget(self.table)

        self.inventory_splitter.addWidget(self.policy_frame)

        # Bottom section: Associated Physical Products (Inventory)
        self.products_frame = QFrame()
        products_layout = QVBoxLayout(self.products_frame)
        products_layout.setContentsMargins(0, 4, 0, 0)
        products_layout.setSpacing(4)

        prods_hdr_layout = QHBoxLayout()
        self.products_title_lbl = QLabel("📦 Associated Physical Products (Inventory)")
        self.products_title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #94a3b8;")
        prods_hdr_layout.addWidget(self.products_title_lbl)
        prods_hdr_layout.addStretch()
        products_layout.addLayout(prods_hdr_layout)

        self.products_table = QTableWidget()
        self.products_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.products_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.products_table.verticalHeader().setVisible(False)
        self.products_table.verticalHeader().setDefaultSectionSize(30)
        self.products_table.setShowGrid(True)
        self.products_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.products_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.products_table.itemDoubleClicked.connect(self._on_product_double_clicked)
        products_layout.addWidget(self.products_table)

        self.inventory_splitter.addWidget(self.products_frame)
        self.inventory_splitter.setStretchFactor(0, 3)
        self.inventory_splitter.setStretchFactor(1, 2)
        self.inventory_splitter.splitterMoved.connect(self._on_splitter_moved)

        inv_layout.addWidget(self.inventory_splitter)

        # Footer strip: compact, centered arrow toggle control for Physical Products panel
        self.products_footer_frame = QFrame()
        self.products_footer_frame.setObjectName("productsFooterFrame")
        self.products_footer_frame.setStyleSheet("""
            QFrame#productsFooterFrame {
                background-color: #0b101b;
                border-top: 1px solid #1e293b;
                border-bottom: none;
                border-left: none;
                border-right: none;
                max-height: 26px;
                min-height: 26px;
            }
        """)
        footer_layout = QHBoxLayout(self.products_footer_frame)
        footer_layout.setContentsMargins(0, 2, 0, 2)
        footer_layout.setSpacing(0)

        self.toggle_products_btn = QToolButton()
        self.toggle_products_btn.setObjectName("toggleProductsBtn")
        self.toggle_products_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_products_btn.setFixedSize(36, 20)
        self.toggle_products_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.toggle_products_btn.setToolTip("Expand product details")
        self.toggle_products_btn.setAccessibleName("Expand product details")
        self.toggle_products_btn.setStyleSheet("""
            QToolButton#toggleProductsBtn {
                background-color: #131d31;
                border: 1px solid #22324e;
                border-radius: 4px;
                color: #38bdf8;
            }
            QToolButton#toggleProductsBtn:hover {
                background-color: #1e293b;
                border-color: #38bdf8;
                color: #38bdf8;
            }
            QToolButton#toggleProductsBtn:disabled {
                background-color: transparent;
                border-color: #1e293b;
                color: #475569;
            }
        """)
        self.toggle_products_btn.clicked.connect(self._toggle_products_panel)

        footer_layout.addStretch()
        footer_layout.addWidget(self.toggle_products_btn)
        footer_layout.addStretch()

        inv_layout.addWidget(self.products_footer_frame)

        # Product details panel is collapsed by default on startup
        self.products_frame.setVisible(False)

        self.tabs.addTab(self.inventory_tab, "📦 Inventory && Stock Control")

        # Tab 2: Altium BOM Project Assembly Auditor
        self.bom_audit_widget = BOMAuditWidget(self.excel, self)
        self.tabs.addTab(self.bom_audit_widget, "📋 Altium BOM Project Auditor")

        # Tab 3: Assembly & BOM Preparation
        self.assembly_widget = AssemblyPreparationWidget(self)
        self.tabs.addTab(self.assembly_widget, "🔧 Assembly && BOM Preparation")

        # Wire BOM lifecycle synchronization between Tab 2 and Tab 3
        self.bom_audit_widget.bomLoaded.connect(self.assembly_widget.set_bom_data)
        self.bom_audit_widget.bomUnloaded.connect(self.assembly_widget.clear_bom)
        self.assembly_widget.bomFileRequested.connect(self.bom_audit_widget.load_bom_file)

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

        ctrl_shift_o = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        ctrl_shift_o.activated.connect(self._open_quick_order)

        ctrl_o = QShortcut(QKeySequence("Ctrl+O"), self)
        ctrl_o.activated.connect(self._open_quick_order)

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

    def _open_quick_order(self):
        dlg = QuickOrderDialog(
            inventory_loader=self.excel,
            on_stock_updated=self._on_stock_incremented_callback,
            parent=self,
        )
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

    @property
    def inventory_database_path(self) -> str:
        """
        Returns the canonical, resolved path to the Inventory.xlsm database.
        Establishes one single source of truth aligned with ExcelInventoryRepository and settings.
        """
        if getattr(self, "_inventory_database_path", None):
            return self._inventory_database_path
        if hasattr(self, "inventory_repo") and self.inventory_repo and self.inventory_repo.get_file_path():
            return self.inventory_repo.get_file_path()
        resolved = resolve_inventory_database_path(settings.get("inventory_database_path"))
        self._inventory_database_path = resolved
        return resolved

    @inventory_database_path.setter
    def inventory_database_path(self, val: str):
        self._inventory_database_path = val

    def load_inventory_database(self, file_path: str):
        """Loads and indexes the read-only Inventory.xlsm workbook via ExcelInventoryRepository."""
        try:
            self._inventory_database_path = file_path
            self.inventory_repo.load(file_path)
            self.search_query = ""
            self.search_input.clear()
            self._filter_and_render()

            file_name = os.path.basename(file_path)
            self.status_state_lbl.setText(f"● Database: {file_name}")
            self.status_state_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")
        except Exception as e:
            self.status_state_lbl.setText(f"● Error: {e}")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")
            self._update_table_display()

    def load_excel_file(self, file_path: str):
        if file_path.lower().endswith(".xlsm"):
            self.load_inventory_database(file_path)
            return

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
        target_file = resolve_inventory_database_path()
        if target_file and os.path.exists(target_file):
            self.load_inventory_database(target_file)
            return

        legacy_file = find_local_excel_file(get_app_dir())
        if legacy_file and os.path.exists(legacy_file):
            self.load_excel_file(legacy_file)
        else:
            self.excel.file_path = None
            self.excel.file_name = ""
            self.excel.headers = []
            self.excel.rows = []
            self.excel._normalized_rows = []
            self.current_filtered_rows = []
            self.current_filtered_groups = []
            self._update_table_display()
            self._update_stats_ribbon()
            self._update_footer_toggle_label()
            self.status_state_lbl.setText("● No inventory database found")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")

    def _on_search_changed(self, query: str):
        self.search_query = query.strip()
        self._filter_and_render()

    def _toggle_incomplete_filter(self):
        self.show_only_incomplete = not self.show_only_incomplete
        self.stats_ribbon.set_incomplete_active(self.show_only_incomplete)
        self._filter_and_render()

    def _filter_and_render(self):
        if self.inventory_repo.is_loaded:
            all_groups = self.inventory_repo.get_all_groups()
            if self.show_only_incomplete:
                filtered = [g for g in all_groups if not g.is_complete]
            else:
                filtered = list(all_groups)

            if self.search_query:
                terms = [normalize_string(t) for t in self.search_query.split() if t.strip()]
                matched_groups = []
                for group in filtered:
                    group_text_parts = [
                        group.category,
                        group.type_technology,
                        group.value,
                        group.package,
                        group.footprint,
                    ]
                    for p in group.products:
                        group_text_parts.extend([p.manufacturer, p.mpn, p.description])
                    searchable_str = " ".join(normalize_string(val) for val in group_text_parts if val)
                    if all(term in searchable_str for term in terms):
                        matched_groups.append(group)
                self.current_filtered_groups = matched_groups
            else:
                self.current_filtered_groups = filtered

            self._update_table_display()
            self._update_stats_ribbon()
            return

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
        if self.inventory_repo.is_loaded:
            all_groups = self.inventory_repo.get_all_groups()
            total_groups = len(all_groups)
            filtered_groups = len(self.current_filtered_groups)
            total_cols = 10
            file_name = os.path.basename(self.inventory_repo.file_path) if self.inventory_repo.file_path else "Inventory.xlsm"
            shortage_count = sum(1 for g in all_groups if g.is_low_stock)
            incomplete_count = sum(1 for g in all_groups if not g.is_complete)
            self.stats_ribbon.update_stats(
                total_groups,
                filtered_groups,
                total_cols,
                file_name,
                shortage_count=shortage_count,
                incomplete_count=incomplete_count
            )
            return

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
        if self.inventory_repo.is_loaded:
            shortages = [g for g in self.inventory_repo.get_all_groups() if g.is_low_stock]
            if not shortages:
                QMessageBox.information(
                    self,
                    "No Shortages Detected",
                    "All inventory stock policy groups currently meet or exceed their configured minimum stock thresholds."
                )
                return
            QMessageBox.information(
                self,
                "Stock Policy Shortages Detected",
                f"{len(shortages)} Stock Policy group(s) are currently below minimum stock threshold.\n\n"
                f"Procurement and ordering workflows will be enabled in Phase 2."
            )
            return

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
        """Dispatches to the modern Stock Policy Groups view if loaded, else legacy view."""
        if self.inventory_repo.is_loaded:
            self._update_policy_groups_display()
        else:
            self._update_legacy_table_display()

    def _update_policy_groups_display(self):
        """Populate the top table with authoritative Stock Policy Groups."""
        self._is_updating_table = True
        headers = [
            "Category", "Type / Technology", "Value", "Package", "Footprint",
            "Total In Stock", "Min Stock", "Target Stock", "Matched Products", "Status"
        ]
        col_count = len(headers)

        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels(headers)

        groups = self.current_filtered_groups
        group_count = len(groups)
        self.table.setRowCount(group_count)

        # Clear any column delegates that might have been set in legacy mode
        for c in range(col_count):
            self.table.setItemDelegateForColumn(c, None)

        if group_count == 0:
            is_filter_active = bool(
                (self.search_query or self.show_only_incomplete) and
                len(self.inventory_repo.get_all_groups()) > 0
            )
            self.table.update_empty_state(True, is_filter_active=is_filter_active)
            self._render_products_table(None)
            self._is_updating_table = False
            return

        self.table.update_empty_state(False)

        font_data = QFont("Segoe UI", 10)
        font_numbers = QFont("Consolas", 10)

        for visual_row_idx, group in enumerate(groups):
            stock_str = f"{group.current_stock:g}" if group.current_stock is not None else "⚠️ Missing"
            min_str = f"{group.min_stock:g}" if group.min_stock is not None else "⚠️ Missing"
            tgt_str = f"{group.target_stock:g}" if group.target_stock is not None else "⚠️ Missing"
            prods_count_str = str(len(group.products))

            if not group.is_complete:
                status_str = "⚠️ Incomplete"
            elif group.is_low_stock:
                status_str = "🔴 Low Stock"
            else:
                status_str = "🟢 Normal"

            row_cells = [
                group.category,
                group.type_technology,
                group.value,
                group.package,
                group.footprint,
                stock_str,
                min_str,
                tgt_str,
                prods_count_str,
                status_str
            ]

            for col_idx, cell_text in enumerate(row_cells):
                item = QTableWidgetItem(cell_text)
                item.setToolTip(cell_text)
                item.setData(Qt.ItemDataRole.UserRole, visual_row_idx)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if col_idx in [5, 6, 7, 8]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                elif col_idx == 9:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_data)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                if col_idx == 5:
                    if group.current_stock is None:
                        item.setForeground(QColor("#fbbf24"))
                        item.setBackground(QColor(245, 158, 11, 35))
                        item.setToolTip("Current Stock: Missing or unreadable in Stock Policy sheet")
                    elif group.is_low_stock:
                        item.setForeground(QColor("#f87171"))
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setToolTip(f"Current Stock: {group.current_stock} (Below Min Stock threshold: {group.min_stock})")
                    else:
                        item.setForeground(QColor("#34d399"))
                        item.setToolTip(f"Current Stock: {group.current_stock}")
                elif col_idx in [6, 7]:
                    col_name = "Min Stock" if col_idx == 6 else "Target Stock"
                    if "Missing" in cell_text:
                        item.setForeground(QColor("#fbbf24"))
                        item.setBackground(QColor(245, 158, 11, 35))
                        item.setToolTip(f"{col_name}: Missing or unconfigured in Stock Policy sheet\nDouble-click to set policy thresholds")
                    else:
                        item.setForeground(QColor("#38bdf8"))
                        item.setBackground(QColor(56, 189, 248, 25))
                        item.setToolTip(f"Double-click to edit {col_name} & Target Stock policy thresholds (Current: {cell_text})")
                elif col_idx == 8:
                    item.setForeground(QColor("#38bdf8"))
                    item.setToolTip(f"Matched physical products in Inventory sheet: {len(group.products)}")
                elif col_idx == 9:
                    if "Incomplete" in cell_text:
                        item.setForeground(QColor("#fbbf24"))
                        item.setBackground(QColor(245, 158, 11, 40))
                        missing_desc = ", ".join(f.replace("_", " ").title() for f in group.missing_fields) if group.missing_fields else "Required thresholds"
                        item.setToolTip(f"Status: Incomplete Stock Policy\nMissing required fields: {missing_desc}")
                    elif "Low Stock" in cell_text:
                        item.setForeground(QColor("#f87171"))
                        item.setBackground(QColor(248, 113, 113, 40))
                        item.setToolTip(f"Status: Low Stock\nCurrent stock ({group.current_stock}) is at or below Min Stock ({group.min_stock})")
                    else:
                        item.setForeground(QColor("#34d399"))
                        item.setBackground(QColor(52, 211, 153, 30))
                        item.setToolTip("Status: Normal\nStock level meets or exceeds policy thresholds")
                else:
                    item.setForeground(QColor("#f8fafc"))

                self.table.setItem(visual_row_idx, col_idx, item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        policy_min_widths = {
            0: 110,  # Category
            1: 130,  # Type / Technology
            2: 100,  # Value
            3: 85,   # Package
            4: 115,  # Footprint
            5: 105,  # Total In Stock
            6: 115,  # Min Stock
            7: 115,  # Target Stock
            8: 140,  # Matched Products
            9: 135,  # Status
        }
        self.table.configure_column_distribution(
            min_widths=policy_min_widths,
            flexible_columns=[0, 1, 2, 4],
        )

        self.table.setSortingEnabled(True)
        self._is_updating_table = False

        if group_count > 0:
            self.table.selectRow(0)
            self._render_products_table(groups[0])
        else:
            self._render_products_table(None)
        self._update_footer_toggle_label()

    def _get_selected_policy_group(self) -> Optional[StockPolicyGroup]:
        """Returns the currently selected StockPolicyGroup from self.table, if any."""
        if not self.inventory_repo.is_loaded:
            return None
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            visual_row = selected_rows[0].row()
            item = self.table.item(visual_row, 0)
            if item:
                group_idx = item.data(Qt.ItemDataRole.UserRole)
                if group_idx is not None and 0 <= group_idx < len(self.current_filtered_groups):
                    return self.current_filtered_groups[group_idx]
        return None

    def _on_group_selection_changed(self):
        if not self.inventory_repo.is_loaded:
            return
        selected_group = self._get_selected_policy_group()
        self._render_products_table(selected_group)
        self._update_footer_toggle_label()

    def _toggle_products_panel(self):
        """Toggle the visibility of the Associated Physical Products panel."""
        self._set_products_panel_expanded(not self.products_frame.isVisible())

    def _set_products_panel_expanded(self, expand: bool):
        """Expand or collapse the Physical Products panel, preserving height and splitter proportions."""
        if expand:
            if not self.products_frame.isVisible():
                self.products_frame.setVisible(True)
                if self._last_splitter_sizes and sum(self._last_splitter_sizes) > 0 and self._last_splitter_sizes[1] > 40:
                    self.inventory_splitter.setSizes(self._last_splitter_sizes)
                else:
                    total_h = self.inventory_splitter.height()
                    if total_h < 200:
                        total_h = 500
                    panel_h = getattr(self, "_last_products_panel_height", 220)
                    top_h = max(120, total_h - panel_h)
                    self.inventory_splitter.setSizes([top_h, panel_h])
        else:
            if self.products_frame.isVisible():
                sizes = self.inventory_splitter.sizes()
                if len(sizes) == 2 and sizes[1] > 40:
                    self._last_splitter_sizes = sizes
                    self._last_products_panel_height = sizes[1]
                self.products_frame.setVisible(False)

        self._update_footer_toggle_label()

    def _on_splitter_moved(self, pos: int, index: int):
        """Record manual splitter sizing during session."""
        if self.products_frame.isVisible():
            sizes = self.inventory_splitter.sizes()
            if len(sizes) == 2 and sizes[1] > 40:
                self._last_splitter_sizes = sizes
                self._last_products_panel_height = sizes[1]

    def _update_footer_toggle_label(self):
        """Update footer toggle arrow and English tooltip/accessible name based on panel state."""
        if not hasattr(self, "toggle_products_btn"):
            return

        if not self.inventory_repo.is_loaded:
            self.toggle_products_btn.setArrowType(Qt.ArrowType.UpArrow)
            self.toggle_products_btn.setToolTip("Expand product details")
            self.toggle_products_btn.setAccessibleName("Expand product details")
            self.toggle_products_btn.setEnabled(False)
            return

        self.toggle_products_btn.setEnabled(True)
        is_expanded = self.products_frame.isVisible()

        if is_expanded:
            self.toggle_products_btn.setArrowType(Qt.ArrowType.DownArrow)
            self.toggle_products_btn.setToolTip("Collapse product details")
            self.toggle_products_btn.setAccessibleName("Collapse product details")
        else:
            self.toggle_products_btn.setArrowType(Qt.ArrowType.UpArrow)
            self.toggle_products_btn.setToolTip("Expand product details")
            self.toggle_products_btn.setAccessibleName("Expand product details")

    def _render_products_table(self, group: Optional[StockPolicyGroup]):
        """Renders physical product records associated with the selected Stock Policy Group (or all products)."""
        headers = [
            "Row", "Manufacturer", "Part Number (MPN)", "Description",
            "Quantity", "Category", "Type / Tech", "Value", "Package", "Footprint", "Purchase Link"
        ]
        col_count = len(headers)

        self.products_table.setSortingEnabled(False)
        self.products_table.clear()
        self.products_table.setColumnCount(col_count)
        self.products_table.setHorizontalHeaderLabels(headers)

        if not self.inventory_repo.is_loaded:
            self.products_table.setRowCount(0)
            self.products_title_lbl.setText("📦 Associated Physical Products (Inventory)")
            return

        if group is not None:
            products = group.products
            desc = f"{group.category} | {group.type_technology} | {group.value} | {group.package} | {group.footprint}"
            self.products_title_lbl.setText(f"📦 Associated Physical Products for [{desc}] ({len(products)} items)")
        else:
            products = self.inventory_repo.get_all_products()
            self.products_title_lbl.setText(f"📦 All Physical Products (Inventory — {len(products)} items)")

        prod_count = len(products)
        self.products_table.setRowCount(prod_count)

        font_data = QFont("Segoe UI", 9)
        font_numbers = QFont("Consolas", 9)

        for row_idx, prod in enumerate(products):
            qty_str = f"{prod.quantity_in_stock}" if prod.quantity_in_stock is not None else ""
            cells = [
                str(row_idx + 1),
                prod.manufacturer,
                prod.mpn,
                prod.description,
                qty_str,
                prod.category,
                prod.type_technology,
                prod.value,
                prod.package,
                prod.footprint,
                prod.purchase_link or ""
            ]

            for col_idx, cell_text in enumerate(cells):
                item = QTableWidgetItem(cell_text)
                item.setToolTip(cell_text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if col_idx in [0, 4]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                if col_idx == 0:
                    item.setForeground(QColor("#64748b"))
                elif col_idx == 2:
                    item.setFont(font_numbers)
                    item.setForeground(QColor("#f8fafc"))
                elif col_idx == 4:
                    item.setForeground(QColor("#34d399"))
                elif col_idx == 10 and cell_text:
                    item.setForeground(QColor("#38bdf8"))
                    item.setToolTip(f"Double-click to open purchase link: {cell_text}")
                else:
                    item.setForeground(QColor("#cbd5e1"))

                self.products_table.setItem(row_idx, col_idx, item)

        header = self.products_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for c in range(col_count):
            self.products_table.resizeColumnToContents(c)
            w = self.products_table.columnWidth(c)
            if w < 70:
                self.products_table.setColumnWidth(c, 70)
            elif w > 300:
                self.products_table.setColumnWidth(c, 300)

        # Distribute excess viewport space to Description (col 3) and Purchase Link (col 10)
        vp_w = self.products_table.viewport().width()
        total_w = sum(self.products_table.columnWidth(c) for c in range(col_count))
        if vp_w > total_w and col_count > 10:
            diff = vp_w - total_w
            self.products_table.setColumnWidth(3, self.products_table.columnWidth(3) + diff // 2)
            self.products_table.setColumnWidth(10, self.products_table.columnWidth(10) + diff - (diff // 2))

        self.products_table.setSortingEnabled(True)

    def _on_product_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        val = item.text().strip()
        if val.startswith("http://") or val.startswith("https://"):
            webbrowser.open(val)
            return
        row = item.row()
        link_item = self.products_table.item(row, 10)
        if link_item:
            link_val = link_item.text().strip()
            if link_val.startswith("http://") or link_val.startswith("https://"):
                webbrowser.open(link_val)

    def _update_legacy_table_display(self):
        """Populate the QTableWidget with dynamic headers and editable threshold cells (legacy Inventory.xlsx)."""
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

                if col_idx in [min_stock_idx, target_stock_idx]:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(QColor(56, 189, 248, 25))
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if val_str.isdigit() or (val_str.replace('.', '', 1).isdigit() and val_str.count('.') < 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                lower_val = val_str.lower().strip()
                if lower_val in ["?", "؟"]:
                    item.setText("⚠️ Missing")
                    item.setForeground(QColor("#fbbf24"))
                    item.setBackground(QColor(245, 158, 11, 40))
                    item.setToolTip(f"Column '{headers[col_idx] if col_idx < len(headers) else ''}': Missing or unknown value (?)")
                elif lower_val.startswith("http://") or lower_val.startswith("https://"):
                    item.setForeground(QColor("#38bdf8"))
                elif col_idx == stock_idx and stock_idx is not None:
                    try:
                        cur_stk = float(val_str) if val_str else 0.0
                        min_stk_str = row_data[min_stock_idx] if min_stock_idx is not None and min_stock_idx < len(row_data) else "0"
                        min_stk = float(min_stk_str) if min_stk_str else 0.0
                        if min_stk > 0 and cur_stk <= min_stk:
                            item.setForeground(QColor("#f87171"))
                        else:
                            item.setForeground(QColor("#34d399"))
                    except ValueError:
                        item.setForeground(QColor("#fbbf24"))
                else:
                    item.setForeground(QColor("#f8fafc"))

                self.table.setItem(visual_row_idx, col_idx, item)

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
        """Automatically saves edited cell value back to Excel in legacy mode."""
        if self._is_updating_table or not item:
            return
        if self.inventory_repo.is_loaded:
            # Strictly read-only in Phase 1
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

    def _is_policy_threshold_column(self, col_idx: int) -> bool:
        """Check if col_idx corresponds to an editable policy threshold column ('Min Stock' or 'Target Stock')."""
        if col_idx < 0 or col_idx >= self.table.columnCount():
            return False
        header_item = self.table.horizontalHeaderItem(col_idx)
        if not header_item:
            return False
        return header_item.text().strip().lower() in ["min stock", "target stock"]

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        val = item.text().strip()
        if val.startswith("http://") or val.startswith("https://"):
            webbrowser.open(val)
            return

        if self.inventory_repo.is_loaded:
            if not self._is_policy_threshold_column(item.column()):
                return
            group_idx = item.data(Qt.ItemDataRole.UserRole)
            if group_idx is None:
                row_item = self.table.item(item.row(), 0)
                if row_item:
                    group_idx = row_item.data(Qt.ItemDataRole.UserRole)
            if group_idx is None:
                group_idx = item.row()
            self._edit_stock_policy_thresholds(group_idx)

    def _edit_stock_policy_thresholds(self, group_idx: int):
        """Open the PolicyEditDialog for the group at group_idx."""
        if not self.inventory_repo.is_loaded:
            return
        if group_idx < 0 or group_idx >= len(self.current_filtered_groups):
            return

        group = self.current_filtered_groups[group_idx]
        try:
            inv_path = self.inventory_database_path
            if not inv_path or not os.path.exists(inv_path):
                QMessageBox.critical(
                    self,
                    "Database File Not Found",
                    f"The inventory database workbook could not be located at:\n{inv_path or 'No path configured'}"
                )
                return

            dlg = PolicyEditDialog(
                group=group,
                inventory_path=inv_path,
                parent=self,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                cur_key = group.group_key
                self.load_inventory_database(inv_path)
                # Restore selection to the modified group
                for row in range(self.table.rowCount()):
                    it = self.table.item(row, 0)
                    if it:
                        idx = it.data(Qt.ItemDataRole.UserRole)
                        if idx is not None and 0 <= idx < len(self.current_filtered_groups):
                            if self.current_filtered_groups[idx].group_key == cur_key:
                                self.table.selectRow(row)
                                break
                self.status_state_lbl.setText("● Policy Saved")
                db_name = os.path.basename(inv_path)
                QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {db_name}"))
        except Exception as e:
            QMessageBox.critical(
                self,
                "Policy Edit Error",
                f"An unexpected error occurred while editing stock policy:\n{e}"
            )

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

        if self.inventory_repo.is_loaded and self._is_policy_threshold_column(item.column()):
            group_idx = item.data(Qt.ItemDataRole.UserRole)
            if group_idx is None:
                row_item = self.table.item(row_idx, 0)
                if row_item:
                    group_idx = row_item.data(Qt.ItemDataRole.UserRole)
            if group_idx is None:
                group_idx = row_idx
            menu.addSeparator()
            edit_policy_act = menu.addAction("✏️ Edit Min / Target Stock Thresholds")
            edit_policy_act.triggered.connect(lambda: self._edit_stock_policy_thresholds(group_idx))

        if val.startswith("http://") or val.startswith("https://"):
            menu.addSeparator()
            open_link_act = menu.addAction("🌐 Open Link in Web Browser")
            open_link_act.triggered.connect(lambda: webbrowser.open(val))

        menu.exec(self.table.viewport().mapToGlobal(pos))
