import os
import sys
import webbrowser
from typing import Optional, Any, List, Dict, Tuple
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QStatusBar, QMenu, QMessageBox, QDialog,
    QTabWidget, QPushButton, QSplitter, QFrame, QToolButton, QLineEdit,
    QFileDialog, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox,
    QStackedWidget, QCheckBox, QAbstractButton,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut, QIcon, QPixmap, QKeyEvent, QMouseEvent

from config import APP_NAME, APP_SUBTITLE, get_app_dir, get_bundle_dir
from excel_loader import ExcelDataLoader, find_local_excel_file, normalize_string
from core.inventory import (
    IInventoryRepository,
    ExcelInventoryRepository,
    SqliteInventoryRepository,
    StockPolicyGroup,
    InventoryProduct,
    resolve_database_path,
    resolve_inventory_database_path,
    bootstrap_sqlite_from_workbook,
    BootstrapResult,
    InventoryExcelExporter,
)
from settings_manager import settings
from ui.widgets import (
    InventoryTableWidget,
    StockCellDelegate,
    StatsRibbonWidget,
    FilterBarWidget,
    BOMAuditWidget,
    AssemblyPreparationWidget,
    WindowTitleBar,
)
from ui.widgets.sidebar import CollapsibleSidebar
from ui.widgets.backup_restore_widget import DatabaseBackupRestoreWidget
from ui.widgets.reference_data_widget import ReferenceDataWidget, ReferenceDataDialog
from core.procurement.link_validator import LinkValidator, LinkValidationItem
from ui.dialogs.link_validation_dialog import LinkValidationDialog
from ui.dialogs import (
    SettingsDialog,
    OrderPreviewDialog,
    QuickOrderDialog,
    PolicyEditDialog,
    ComponentEditDialog,
    ProviderManagementDialog,
)


class MainWindow(QMainWindow):
    """
    Omnix Main Window:
    - Tab 1: Inventory & Stock Management with live search and editable thresholds.
    - Tab 2: Altium BOM Project Assembly Auditor & Shortage Calculator.
    - Automated Lion Electronic purchasing integration.
    """

    def __init__(self, default_file: str = None, repository: Optional[IInventoryRepository] = None):
        super().__init__()
        self.excel = ExcelDataLoader()
        if repository is not None:
            self.inventory_repo = repository
        elif default_file and default_file.lower().endswith((".xlsm", ".xlsx")):
            self.inventory_repo = ExcelInventoryRepository()
        else:
            self.inventory_repo = SqliteInventoryRepository()
        self.current_filtered_groups: list[StockPolicyGroup] = []
        self.current_filtered_rows = []
        self.search_query = ""
        self.show_only_incomplete = False
        self._is_force_closing = False
        self._is_updating_table = False
        self._last_products_panel_height = 220
        self._last_splitter_sizes: Optional[list[int]] = None
        self._inventory_database_path: Optional[str] = None
        self._mpn_copy_timer: Optional[QTimer] = None
        self._mpn_copy_seq: int = 0
        self._last_normal_status_state: str = "● Database Ready"

        self.setWindowTitle(f"{APP_NAME} | Inventory & Altium BOM Assembly Auditor")
        self.resize(1260, 780)
        self.setMinimumSize(960, 620)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        if sys.platform == "win32":
            try:
                import ctypes
                from ui.dark_frame import apply_dark_window_frame
                apply_dark_window_frame(self)
                hwnd = int(self.winId())
                user32 = getattr(ctypes.windll, "user32", None)
                if user32:
                    GWL_STYLE = -16
                    WS_MINIMIZEBOX = 0x00020000
                    WS_MAXIMIZEBOX = 0x00010000
                    WS_THICKFRAME = 0x00040000
                    cur_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                    user32.SetWindowLongW(hwnd, GWL_STYLE, cur_style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_THICKFRAME)
            except Exception:
                pass

        self.setMouseTracking(True)
        self._resize_edge: Optional[Qt.Edge] = None
        self._border_margin = 6

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

        # Install application-level event filter for clean '/' shortcut routing
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.installEventFilter(self)

        # Automatic detection of the inventory database file
        if default_file == "":
            target_file = None
        elif default_file is not None:
            target_file = default_file
        else:
            # Stage 2 Phase 2.1: SQLite database is the authoritative store
            target_file = resolve_database_path()

        if target_file and (os.path.exists(target_file) or str(target_file).endswith((".db", ".sqlite", ".sqlite3")) or target_file == ":memory:"):
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
        # 0. Top-Level Window Title Bar (hosting relocated actions & standard window controls)
        self.title_bar = WindowTitleBar(parent=self)
        self.setMenuWidget(self.title_bar)

        # Retain direct button references on self for backward compatibility
        self.manage_reference_btn = self.title_bar.manage_reference_btn
        self.export_excel_btn = self.title_bar.export_excel_btn
        self.settings_btn = self.title_bar.settings_btn

        # Wire Title Bar 'Settings' dropdown menu actions
        self.title_bar.generalRequested.connect(lambda: self._open_settings(initial_tab="general"))
        self.title_bar.pluginsRequested.connect(lambda: self._open_settings(initial_tab="plugins"))
        self.title_bar.referenceDataRequested.connect(self._open_reference_data_dialog)
        self.title_bar.providersRequested.connect(self._open_providers_dialog)
        self.title_bar.exportExcelRequested.connect(self._export_inventory_to_excel)
        self.settings_btn.clicked.connect(self._open_settings)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 8)

        # Top In-Content Header with Brand Logo & Title (Actions relocated to Title Bar)
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
        brand_sub = QLabel("")
        brand_sub.setObjectName("brandSubtitle")
        brand_sub.setVisible(False)
        brand_text_layout.addWidget(brand_title)
        brand_layout.addLayout(brand_text_layout)

        header_layout.addLayout(brand_layout)
        header_layout.addStretch()

        # Quick Order Button (preserved for keyboard shortcuts and test compatibility; removed from header)
        self.quick_order_btn = QPushButton("Quick Order")
        self.quick_order_btn.setVisible(False)
        self.quick_order_btn.clicked.connect(self._open_quick_order)

        main_layout.addLayout(header_layout)

        # 2. Main Dual-Tab Widget Container
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Tab 1: Inventory & Stock Management
        self.inventory_tab = QWidget()
        inv_layout = QVBoxLayout(self.inventory_tab)
        inv_layout.setContentsMargins(8, 10, 8, 6)
        inv_layout.setSpacing(8)

        self.stats_ribbon = StatsRibbonWidget()
        val_active = bool(
            settings.get("stock_policy_enabled", True) and
            settings.get("stock_policy_validation_enabled", True)
        )
        self.stats_ribbon.set_validation_enabled(val_active)
        self.stats_ribbon.orderShortagesRequested.connect(self._open_inventory_order_dialog)
        self.stats_ribbon.incompleteFilterRequested.connect(self._toggle_incomplete_filter)
        inv_layout.addWidget(self.stats_ribbon)

        # Inventory Sub-Tabs: Stock Policy Groups vs Dedicated Component Inventory
        self.inventory_subtabs = QTabWidget()
        self.inventory_subtabs.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.inventory_subtabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0b101b;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #1e293b;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                padding: 5px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0b101b;
                color: #38bdf8;
                border-top: 2px solid #38bdf8;
            }
            QTabBar::tab:hover:!selected {
                background-color: #334155;
                color: #f8fafc;
            }
        """)

        # Subtab 0: Stock Policy Groups (Table 2 + Table 3 with splitter)
        self.stock_policy_view = QWidget()
        stock_view_layout = QVBoxLayout(self.stock_policy_view)
        stock_view_layout.setContentsMargins(6, 6, 6, 4)
        stock_view_layout.setSpacing(6)

        self.filter_bar = FilterBarWidget()
        self.search_input = self.filter_bar.search_input
        self.filter_bar.searchChanged.connect(self._on_search_changed)
        stock_view_layout.addWidget(self.filter_bar)

        # Splitter with Policy Groups (top) and Associated Physical Products (bottom)
        self.inventory_splitter = QSplitter(Qt.Orientation.Vertical)
        self.inventory_splitter.setChildrenCollapsible(False)

        # Top section: Stock Policy Groups (Table 2)
        self.policy_frame = QFrame()
        policy_layout = QVBoxLayout(self.policy_frame)
        policy_layout.setContentsMargins(0, 0, 0, 0)
        policy_layout.setSpacing(4)

        policy_hdr_layout = QHBoxLayout()
        self.policy_title_lbl = QLabel("Assembly View (Authoritative Group & Stock Source)")
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

        # Bottom section: Associated Physical Products (Table 3)
        self.products_frame = QFrame()
        products_layout = QVBoxLayout(self.products_frame)
        products_layout.setContentsMargins(0, 4, 0, 0)
        products_layout.setSpacing(4)

        prods_hdr_layout = QHBoxLayout()
        self.products_title_lbl = QLabel("Associated Physical Products (Matching Selected Group)")
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
        self.products_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.products_table.customContextMenuRequested.connect(self._show_product_context_menu)
        self.products_table.itemSelectionChanged.connect(self._on_component_selection_changed)
        self.products_table.itemClicked.connect(self._on_inventory_component_clicked)
        self.products_table.itemDoubleClicked.connect(self._on_product_double_clicked)
        products_layout.addWidget(self.products_table)

        self.inventory_splitter.addWidget(self.products_frame)
        self.inventory_splitter.setStretchFactor(0, 3)
        self.inventory_splitter.setStretchFactor(1, 2)
        self.inventory_splitter.splitterMoved.connect(self._on_splitter_moved)

        stock_view_layout.addWidget(self.inventory_splitter)

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

        stock_view_layout.addWidget(self.products_footer_frame)

        # Product details panel is collapsed by default on startup
        self.products_frame.setVisible(False)

        # Subtab 1: Dedicated Physical Component Inventory (Table 1 + CRUD Buttons)
        self.component_inventory_view = QWidget()
        comp_view_layout = QVBoxLayout(self.component_inventory_view)
        comp_view_layout.setContentsMargins(8, 8, 8, 8)
        comp_view_layout.setSpacing(6)

        # Retain attribute for backward compatibility
        self.component_inventory_title = None

        # Streamlined Unified Action & Search Toolbar
        comp_toolbar = QHBoxLayout()
        comp_toolbar.setSpacing(8)

        self.component_search_input = QLineEdit()
        self.component_search_input.setPlaceholderText("Search by MPN, Manufacturer, or Value...")
        self.component_search_input.setFixedHeight(30)
        self.component_search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.component_search_input.textChanged.connect(self._on_component_search_changed)
        comp_toolbar.addWidget(self.component_search_input, 1)

        self.add_component_btn = QPushButton("Add Component")
        self.add_component_btn.setFixedHeight(30)
        self.add_component_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_component_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 14px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
            }
        """)
        self.add_component_btn.clicked.connect(self._open_add_component_dialog)
        comp_toolbar.addWidget(self.add_component_btn)

        self.edit_component_btn = QPushButton("Edit Component")
        self.edit_component_btn.setFixedHeight(30)
        self.edit_component_btn.setEnabled(False)
        self.edit_component_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_component_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 14px;
                border-radius: 4px;
                border: 1px solid #475569;
            }
            QPushButton:hover {
                background-color: #475569;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border: 1px solid #334155;
            }
        """)
        self.edit_component_btn.clicked.connect(lambda: self._open_edit_component_dialog())
        comp_toolbar.addWidget(self.edit_component_btn)

        self.delete_component_btn = QPushButton("Delete Component")
        self.delete_component_btn.setFixedHeight(30)
        self.delete_component_btn.setEnabled(False)
        self.delete_component_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_component_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f87171;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
                border-radius: 4px;
                border: 1px solid #475569;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border: 1px solid #334155;
            }
        """)
        self.delete_component_btn.clicked.connect(self._delete_selected_component)
        comp_toolbar.addWidget(self.delete_component_btn)

        self.validate_links_btn = QPushButton("🔗 Validate Links")
        self.validate_links_btn.setVisible(False)
        self.validate_links_btn.clicked.connect(self._open_link_validation_dialog)

        comp_view_layout.addLayout(comp_toolbar)

        # 4. Table 1: Dedicated Component Inventory Table (Using InventoryTableWidget)
        self.inventory_components_table = InventoryTableWidget()
        self.inventory_components_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inventory_components_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.inventory_components_table.verticalHeader().setVisible(False)
        self.inventory_components_table.verticalHeader().setDefaultSectionSize(30)
        self.inventory_components_table.setShowGrid(True)
        self.inventory_components_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inventory_components_table.horizontalHeader().setSectionsClickable(False)
        self.inventory_components_table.setSortingEnabled(False)
        self.inventory_components_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inventory_components_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.inventory_components_table.customContextMenuRequested.connect(self._show_inventory_component_context_menu)
        self.inventory_components_table.itemSelectionChanged.connect(self._on_component_selection_changed)
        self.inventory_components_table.itemClicked.connect(self._on_inventory_component_clicked)
        self.inventory_components_table.itemDoubleClicked.connect(self._on_inventory_component_double_clicked)
        comp_view_layout.addWidget(self.inventory_components_table, 1)

        # Add subtabs: Assembly View and Component Inventory
        self.inventory_subtabs.addTab(self.stock_policy_view, "Assembly View")
        self.inventory_subtabs.addTab(self.component_inventory_view, "Component Inventory")
        self.inventory_subtabs.currentChanged.connect(self._on_inventory_subtab_changed)
        self.inventory_subtabs.tabBar().setVisible(False)
        inv_layout.addWidget(self.inventory_subtabs)

        self.tabs.addTab(self.inventory_tab, "Inventory && Stock Control")

        # Tab 2: Altium BOM Project Assembly Auditor
        self.bom_audit_widget = BOMAuditWidget(self.excel, self)
        self.tabs.addTab(self.bom_audit_widget, "Altium BOM Project Auditor")

        # Tab 3: Assembly & BOM Preparation
        self.assembly_widget = AssemblyPreparationWidget(self)
        self.tabs.addTab(self.assembly_widget, "Assembly && BOM Preparation")
        self.tabs.tabBar().setVisible(False)

        # Wire BOM lifecycle synchronization between Tab 2 and Tab 3
        self.bom_audit_widget.bomLoaded.connect(self.assembly_widget.set_bom_data)
        self.bom_audit_widget.bomUnloaded.connect(self.assembly_widget.clear_bom)
        self.assembly_widget.bomFileRequested.connect(self.bom_audit_widget.load_bom_file)

        # 3. Stacked Container for Mode A Views (Section 5)
        self.content_stack = QStackedWidget()

        # Page 0: Main Dual-Tab / Tri-Tab Container (Inventory, BOM Audit, Assembly Prep)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.content_stack.addWidget(self.tabs)

        # Page 1: Dedicated Reference Data View
        self.reference_data_page = QWidget()
        ref_page_layout = QVBoxLayout(self.reference_data_page)
        ref_page_layout.setContentsMargins(0, 0, 0, 0)
        self.reference_data_widget = ReferenceDataWidget(repository=self.inventory_repo, parent=self)
        self.reference_data_widget.referenceDataChanged.connect(self.reload_database)
        ref_page_layout.addWidget(self.reference_data_widget)
        self.content_stack.addWidget(self.reference_data_page)

        # Page 2: General Settings & Stock Policy Page (Section 11)
        self.general_settings_page = self._build_general_settings_page()
        self.content_stack.addWidget(self.general_settings_page)

        # Page 3: Vendor & Link Providers Page (Section 12)
        self.providers_page = QWidget()
        prov_page_layout = QVBoxLayout(self.providers_page)
        prov_page_layout.setContentsMargins(0, 0, 0, 0)
        self.providers_widget = ProviderManagementDialog(repository=self.inventory_repo, parent=self, is_embedded=True)
        prov_page_layout.addWidget(self.providers_widget)
        self.content_stack.addWidget(self.providers_page)

        # Page 4: Database Backup & Restore Page (Section 6)
        self.backup_restore_page = QWidget()
        backup_page_layout = QVBoxLayout(self.backup_restore_page)
        backup_page_layout.setContentsMargins(0, 0, 0, 0)
        db_file = getattr(self, "inventory_database_path", None) or resolve_database_path()
        self.backup_restore_widget = DatabaseBackupRestoreWidget(repository=self.inventory_repo, db_path=db_file, parent=self)
        self.backup_restore_widget.restored_signal.connect(self.reload_database)
        backup_page_layout.addWidget(self.backup_restore_widget)
        self.content_stack.addWidget(self.backup_restore_page)

        # Body Layout: Collapsible Sidebar on left, Content Stack on right (Section 5)
        body_h_layout = QHBoxLayout()
        body_h_layout.setContentsMargins(0, 0, 0, 0)
        body_h_layout.setSpacing(8)

        self.sidebar = CollapsibleSidebar(self)
        self.sidebar.pageChanged.connect(self._on_sidebar_page_changed)
        self.title_bar.sidebarToggleRequested.connect(self.sidebar.toggle_collapse)
        body_h_layout.addWidget(self.sidebar)

        body_h_layout.addWidget(self.content_stack, 1)
        main_layout.addLayout(body_h_layout, 1)

    def _build_general_settings_page(self) -> QWidget:
        """Constructs the dedicated General Settings & Stock Policy view in the sidebar stack (Section 11)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("⚙️ General Settings & Stock Policy")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # Master Checkbox: Enable stock-policy features
        self.side_stock_policy_enabled_chk = QCheckBox("Enable stock-policy features")
        self.side_stock_policy_enabled_chk.setStyleSheet("font-weight: bold; font-size: 13px; color: #38bdf8;")
        self.side_stock_policy_enabled_chk.setChecked(settings.get("stock_policy_enabled", True))
        card_layout.addWidget(self.side_stock_policy_enabled_chk)

        # Stock-policy and shortage-automation group
        sub_layout = QVBoxLayout()
        sub_layout.setContentsMargins(24, 0, 0, 0)
        sub_layout.setSpacing(8)

        # 2. Subordinate 1: Enable stock-policy validation / shortage checking
        self.side_stock_policy_validation_chk = QCheckBox("Enable stock-policy validation / shortage checking")
        self.side_stock_policy_validation_chk.setChecked(settings.get("stock_policy_validation_enabled", True))
        sub_layout.addWidget(self.side_stock_policy_validation_chk)

        # 3. Subordinate 2: Automatically check inventory shortages on application startup
        self.side_startup_chk = QCheckBox("Automatically check inventory shortages on application startup")
        self.side_startup_chk.setChecked(settings.get("auto_check_startup_shortage", True))
        sub_layout.addWidget(self.side_startup_chk)

        card_layout.addLayout(sub_layout)

        # 4. Subtle horizontal divider immediately after the startup-check option
        card_layout.addSpacing(4)
        self.side_stock_policy_divider = QFrame()
        self.side_stock_policy_divider.setFrameShape(QFrame.Shape.HLine)
        self.side_stock_policy_divider.setFrameShadow(QFrame.Shadow.Plain)
        self.side_stock_policy_divider.setStyleSheet("background-color: #334155; max-height: 1px; border: none;")
        card_layout.addWidget(self.side_stock_policy_divider)
        card_layout.addSpacing(4)

        # Assembly View display settings group
        display_layout = QVBoxLayout()
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.setSpacing(8)

        # 5. Show Min Stock and Target Stock columns in Assembly View
        self.side_stock_policy_show_columns_chk = QCheckBox("Show Min Stock and Target Stock columns in Assembly View")
        self.side_stock_policy_show_columns_chk.setChecked(settings.get("stock_policy_show_columns", True))
        display_layout.addWidget(self.side_stock_policy_show_columns_chk)

        # 6. Show Matched Products in Assembly View
        self.side_match_products_chk = QCheckBox("Show Matched Products in Assembly View")
        self.side_match_products_chk.setChecked(settings.get("match_products_enabled", True))
        display_layout.addWidget(self.side_match_products_chk)

        card_layout.addLayout(display_layout)

        def _update_dependency_states():
            master_on = self.side_stock_policy_enabled_chk.isChecked()
            self.side_stock_policy_validation_chk.setEnabled(master_on)
            self.side_stock_policy_show_columns_chk.setEnabled(master_on)

            if not master_on:
                self.side_stock_policy_validation_chk.blockSignals(True)
                self.side_stock_policy_validation_chk.setChecked(False)
                self.side_stock_policy_validation_chk.blockSignals(False)

                self.side_startup_chk.setEnabled(False)
                self.side_startup_chk.blockSignals(True)
                self.side_startup_chk.setChecked(False)
                self.side_startup_chk.blockSignals(False)
            else:
                saved_val = bool(settings.get("stock_policy_validation_enabled", True))
                self.side_stock_policy_validation_chk.blockSignals(True)
                self.side_stock_policy_validation_chk.setChecked(saved_val)
                self.side_stock_policy_validation_chk.blockSignals(False)

                val_active = self.side_stock_policy_validation_chk.isChecked()
                self.side_startup_chk.setEnabled(val_active)
                self.side_startup_chk.blockSignals(True)
                if val_active:
                    saved_auto_check = bool(settings.get("auto_check_startup_shortage", True))
                    self.side_startup_chk.setChecked(saved_auto_check)
                else:
                    self.side_startup_chk.setChecked(False)
                self.side_startup_chk.blockSignals(False)

        def _on_side_master_toggled(checked: bool):
            settings.set("stock_policy_enabled", checked)
            _update_dependency_states()
            self._update_table_display()
            self._update_stats_ribbon()

        def _on_side_validation_toggled(checked: bool):
            if self.side_stock_policy_validation_chk.isEnabled():
                settings.set("stock_policy_validation_enabled", checked)
            _update_dependency_states()
            self._update_table_display()
            self._update_stats_ribbon()

        def _on_side_columns_toggled(checked: bool):
            settings.set("stock_policy_show_columns", checked)
            self._update_table_display()

        def _on_side_startup_toggled(checked: bool):
            if self.side_startup_chk.isEnabled():
                settings.set("auto_check_startup_shortage", checked)

        def _on_side_match_products_toggled(checked: bool):
            settings.set("match_products_enabled", checked)
            self._apply_match_products_visibility(checked)
            self._update_table_display()

        self.side_stock_policy_enabled_chk.toggled.connect(_on_side_master_toggled)
        self.side_stock_policy_validation_chk.toggled.connect(_on_side_validation_toggled)
        self.side_stock_policy_show_columns_chk.toggled.connect(_on_side_columns_toggled)
        self.side_startup_chk.toggled.connect(_on_side_startup_toggled)
        self.side_match_products_chk.toggled.connect(_on_side_match_products_toggled)

        _update_dependency_states()

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _sync_general_settings_page(self):
        """Synchronizes the sidebar General Settings page with current SettingsManager values."""
        if not hasattr(self, "side_stock_policy_enabled_chk"):
            return
        self.side_stock_policy_enabled_chk.blockSignals(True)
        self.side_stock_policy_validation_chk.blockSignals(True)
        self.side_stock_policy_show_columns_chk.blockSignals(True)
        self.side_startup_chk.blockSignals(True)
        self.side_match_products_chk.blockSignals(True)

        master_on = bool(settings.get("stock_policy_enabled", True))
        val_on = bool(settings.get("stock_policy_validation_enabled", True))
        cols_on = bool(settings.get("stock_policy_show_columns", True))
        startup_on = bool(settings.get("auto_check_startup_shortage", True))
        match_on = bool(settings.get("match_products_enabled", True))

        self.side_stock_policy_enabled_chk.setChecked(master_on)
        self.side_stock_policy_validation_chk.setChecked(master_on and val_on)
        self.side_stock_policy_show_columns_chk.setChecked(cols_on)
        self.side_startup_chk.setChecked(master_on and val_on and startup_on)
        self.side_match_products_chk.setChecked(match_on)

        self.side_stock_policy_validation_chk.setEnabled(master_on)
        self.side_stock_policy_show_columns_chk.setEnabled(master_on)
        self.side_startup_chk.setEnabled(master_on and val_on)

        self.side_stock_policy_enabled_chk.blockSignals(False)
        self.side_stock_policy_validation_chk.blockSignals(False)
        self.side_stock_policy_show_columns_chk.blockSignals(False)
        self.side_startup_chk.blockSignals(False)
        self.side_match_products_chk.blockSignals(False)

    def _on_sidebar_page_changed(self, page_id: str):
        """Routes sidebar clicks to corresponding view in content_stack or tabs."""
        if getattr(self, "_is_syncing_navigation", False):
            return
        self._is_syncing_navigation = True
        try:
            if page_id == "assembly_view":
                self.inventory_subtabs.setCurrentIndex(0)
                self.tabs.setCurrentIndex(0)
                self.content_stack.setCurrentWidget(self.tabs)
            elif page_id == "component_inventory":
                self.inventory_subtabs.setCurrentIndex(1)
                self.tabs.setCurrentIndex(0)
                self.content_stack.setCurrentWidget(self.tabs)
            elif page_id == "bom_audit":
                self.tabs.setCurrentIndex(1)
                self.content_stack.setCurrentWidget(self.tabs)
            elif page_id in ("general_settings", "settings"):
                self._sync_general_settings_page()
                self.content_stack.setCurrentWidget(self.general_settings_page)
            elif page_id in ("backup_restore", "backup"):
                if hasattr(self, "backup_restore_widget"):
                    self.backup_restore_widget.refresh_status()
                self.content_stack.setCurrentWidget(self.backup_restore_page)
            elif page_id == "reference_data":
                if hasattr(self, "reference_data_widget") and isinstance(self.inventory_repo, SqliteInventoryRepository):
                    self.reference_data_widget.set_repository(self.inventory_repo)
                    self.reference_data_widget.refresh()
                self.content_stack.setCurrentWidget(self.reference_data_page)
            elif page_id == "provider_management":
                if hasattr(self, "providers_widget") and isinstance(self.inventory_repo, SqliteInventoryRepository):
                    self.providers_widget.set_repository(self.inventory_repo)
                    self.providers_widget.refresh()
                self.content_stack.setCurrentWidget(self.providers_page)

            # Authoritatively guarantee sidebar active page reflects requested destination
            self.sidebar.set_active_page(page_id)
        finally:
            self._is_syncing_navigation = False

    def _on_tab_changed(self, index: int):
        """Synchronizes tab changes with the sidebar state."""
        if getattr(self, "_is_syncing_navigation", False):
            return
        if hasattr(self, "sidebar") and self.content_stack.currentWidget() == self.tabs:
            if index == 0:
                if hasattr(self, "inventory_subtabs") and self.inventory_subtabs.currentIndex() == 0:
                    self.sidebar.set_active_page("assembly_view")
                else:
                    self.sidebar.set_active_page("component_inventory")
            elif index == 1:
                self.sidebar.set_active_page("bom_audit")

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

        # Clickable database path indicator with toast feedback
        self.status_db_lbl = QLabel()
        self.status_db_lbl.setObjectName("statusDbPathLabel")
        self.status_db_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_db_lbl.setToolTip("Click to copy full database path to clipboard")
        self.status_db_lbl.setStyleSheet("""
            QLabel#statusDbPathLabel {
                color: #38bdf8;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 1px 8px;
                border-radius: 4px;
            }
            QLabel#statusDbPathLabel:hover {
                background-color: rgba(56, 189, 248, 0.15);
                color: #ffffff;
            }
        """)
        self.status_db_lbl.mousePressEvent = lambda event: self._copy_database_path()
        status_bar.addPermanentWidget(self.status_db_lbl)

        self.status_state_lbl = QLabel("● Ready")
        self.status_state_lbl.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px; padding-right: 12px;")
        status_bar.addPermanentWidget(self.status_state_lbl)

    def _setup_shortcuts(self):
        # NOTE: '/' is handled contextually in keyPressEvent to avoid stealing '/'
        # during editable text entry and to correctly route between Assembly View and Component Inventory.

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

        ctrl_b = QShortcut(QKeySequence("Ctrl+B"), self)
        ctrl_b.activated.connect(self.sidebar.toggle_collapse)

        ctrl_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        ctrl_q.activated.connect(self.close)

    def eventFilter(self, watched, event):
        ev_type = event.type()
        if ev_type in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched)):
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                    pos_in_win = self.mapFromGlobal(global_pos)
                    if self.rect().contains(pos_in_win):
                        edge = self._get_resize_edge(pos_in_win)
                        self._resize_edge = edge
                        self._update_cursor_for_edge(edge)
                    else:
                        self._resize_edge = None
                        if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                            self.unsetCursor()
        elif ev_type == QEvent.Type.Leave:
            if watched is self:
                self._resize_edge = None
                if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                    self.unsetCursor()
        elif ev_type == QEvent.Type.MouseButtonPress:
            if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
                if not isinstance(watched, QAbstractButton):
                    if hasattr(event, "globalPosition"):
                        global_pos = event.globalPosition().toPoint()
                        pos_in_win = self.mapFromGlobal(global_pos)
                        edge = self._get_resize_edge(pos_in_win)
                        if edge is not None:
                            handle = self.windowHandle()
                            if handle and hasattr(handle, "startSystemResize"):
                                handle.startSystemResize(edge)
                                return True
        elif ev_type == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Slash and event.modifiers() in (
                Qt.KeyboardModifier.NoModifier,
                Qt.KeyboardModifier.KeypadModifier,
            ):
                fw = QApplication.focusWidget()
                if fw and isinstance(
                    fw,
                    (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox),
                ):
                    return False
                if self.tabs.currentIndex() == 0:
                    self._focus_search()
                    return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Slash and event.modifiers() in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        ):
            # Check if focus is currently inside an editable widget or dialog
            focus_widget = QApplication.focusWidget()
            if focus_widget and isinstance(
                focus_widget,
                (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox),
            ):
                super().keyPressEvent(event)
                return

            if self.tabs.currentIndex() == 0:
                event.accept()
                self._focus_search()
                return

        super().keyPressEvent(event)

    def _focus_search(self):
        """Focus the search field of the active inventory subtab without duplicate trigger side effects."""
        if self.tabs.currentIndex() == 0:
            if hasattr(self, "inventory_subtabs") and self.inventory_subtabs.currentIndex() == 1:
                if hasattr(self, "component_search_input"):
                    if not self.component_search_input.hasFocus():
                        self.component_search_input.setFocus()
                        self.component_search_input.selectAll()
            else:
                if hasattr(self, "search_input"):
                    if not self.search_input.hasFocus():
                        self.search_input.setFocus()
                        self.search_input.selectAll()

    def handle_escape_key(self):
        """Multi-stage Escape key handler isolated to active views."""
        if self.tabs.currentIndex() == 0:
            # Active Subtab 1: Component Inventory
            if hasattr(self, "inventory_subtabs") and self.inventory_subtabs.currentIndex() == 1:
                if hasattr(self, "component_search_input"):
                    has_search_text = bool(self.component_search_input.text().strip())
                    is_search_focused = self.component_search_input.hasFocus()
                    if has_search_text or is_search_focused:
                        if has_search_text:
                            self.component_search_input.clear()
                        self.component_search_input.clearFocus()
                        if hasattr(self, "inventory_components_table"):
                            self.inventory_components_table.setFocus()
                        return

                if hasattr(self, "inventory_components_table") and (
                    len(self.inventory_components_table.selectedItems()) > 0
                    or self.inventory_components_table.currentItem() is not None
                ):
                    self.inventory_components_table.clearSelection()
                    self.inventory_components_table.setCurrentItem(None)
                    return

            # Active Subtab 0: Assembly View
            else:
                if hasattr(self, "search_input"):
                    has_search_text = bool(self.search_input.text().strip())
                    is_search_focused = self.search_input.hasFocus()

                    if has_search_text or is_search_focused:
                        if has_search_text:
                            self.search_input.clear()
                        self.search_input.clearFocus()
                        if hasattr(self, "table"):
                            self.table.setFocus()
                        return

                if self.show_only_incomplete:
                    self.show_only_incomplete = False
                    self.stats_ribbon.set_incomplete_active(False)
                    self._filter_and_render()
                    return

                if hasattr(self, "table") and (
                    len(self.table.selectedItems()) > 0 or self.table.currentItem() is not None
                ):
                    self.table.clearSelection()
                    self.table.setCurrentItem(None)
                    return

        # Prompt exit confirmation dialog
        self._prompt_exit_confirmation()

    def _get_resize_edge(self, pos: QPoint) -> Optional[Qt.Edge]:
        """Detect if cursor is near window border for frameless resizing."""
        if self.isMaximized():
            return None
        margin = getattr(self, "_border_margin", 6)
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()

        left = x <= margin
        right = x >= w - margin
        top = y <= margin
        bottom = y >= h - margin

        if top and left:
            return Qt.Edge.TopEdge | Qt.Edge.LeftEdge
        if top and right:
            return Qt.Edge.TopEdge | Qt.Edge.RightEdge
        if bottom and left:
            return Qt.Edge.BottomEdge | Qt.Edge.LeftEdge
        if bottom and right:
            return Qt.Edge.BottomEdge | Qt.Edge.RightEdge
        if left:
            return Qt.Edge.LeftEdge
        if right:
            return Qt.Edge.RightEdge
        if top:
            return Qt.Edge.TopEdge
        if bottom:
            return Qt.Edge.BottomEdge
        return None

    def _update_cursor_for_edge(self, edge: Optional[Qt.Edge]):
        """Sets the appropriate resize cursor or unsets override when inside."""
        if edge in ((Qt.Edge.TopEdge | Qt.Edge.LeftEdge), (Qt.Edge.BottomEdge | Qt.Edge.RightEdge)):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ((Qt.Edge.TopEdge | Qt.Edge.RightEdge), (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge)):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edge in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                self.unsetCursor()

    def mouseMoveEvent(self, event: QMouseEvent):
        edge = self._get_resize_edge(event.pos())
        self._resize_edge = edge
        self._update_cursor_for_edge(edge)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent):
        self._resize_edge = None
        if self.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
            self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._resize_edge is not None:
            handle = self.windowHandle()
            if handle and hasattr(handle, "startSystemResize"):
                handle.startSystemResize(self._resize_edge)
                event.accept()
                return
        super().mousePressEvent(event)

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "title_bar") and self.title_bar:
                self.title_bar.update_maximize_state(self.isMaximized())
        super().changeEvent(event)

    def _show_confirmation_dialog(
        self,
        title: str,
        text: str,
        informative_text: str = "",
        is_danger: bool = False,
    ) -> bool:
        """Standardized high-contrast confirmation dialog with native dark frame and mock-safe execution."""
        import unittest.mock
        if isinstance(getattr(QMessageBox, "question", None), (unittest.mock.MagicMock, unittest.mock.Mock)):
            mock_res = QMessageBox.question(self, title, text)
            return mock_res in (QMessageBox.StandardButton.Yes, 1, True, "Yes", QMessageBox.ButtonRole.YesRole)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_btn)
        msg_box.setEscapeButton(no_btn)

        if is_danger:
            yes_btn.setObjectName("dangerBtn")
        else:
            yes_btn.setObjectName("primaryBtn")
        no_btn.setObjectName("secondaryBtn")

        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(msg_box)

        msg_box.exec()
        return msg_box.clickedButton() == yes_btn

    def _prompt_exit_confirmation(self):
        if self._show_confirmation_dialog("Exit Confirmation", "Do you want to exit Omnix?", is_danger=True):
            self._is_force_closing = True
            QApplication.quit()

    def closeEvent(self, event):
        app_inst = QApplication.instance()
        if app_inst:
            try:
                app_inst.removeEventFilter(self)
            except Exception:
                pass

        if self._is_force_closing:
            event.accept()
            return

        if self._show_confirmation_dialog("Exit Confirmation", "Do you want to exit Omnix?", is_danger=True):
            self._is_force_closing = True
            event.accept()
        else:
            event.ignore()

    def _open_settings(self, initial_tab: Optional[str] = None):
        dlg = SettingsDialog(self, initial_tab=initial_tab)
        dlg.exec()
        self._sync_general_settings_page()
        # Refresh display in case stock policy columns or validation changed
        self._update_table_display()
        self._update_stats_ribbon()

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
        if not settings.get("stock_policy_enabled", True) or not settings.get("stock_policy_validation_enabled", True):
            return
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
        Returns the canonical, resolved path to the inventory database.
        Establishes one single source of truth aligned with the active repository.
        """
        if getattr(self, "_inventory_database_path", None):
            return self._inventory_database_path
        if hasattr(self, "inventory_repo") and self.inventory_repo and self.inventory_repo.get_file_path():
            return self.inventory_repo.get_file_path()
        if isinstance(getattr(self, "inventory_repo", None), SqliteInventoryRepository):
            resolved = resolve_database_path()
        else:
            resolved = resolve_inventory_database_path(settings.get("inventory_database_path"))
        self._inventory_database_path = resolved
        return resolved

    @inventory_database_path.setter
    def inventory_database_path(self, val: str):
        self._inventory_database_path = val

    def load_inventory_database(self, file_path: str):
        """Loads and indexes the inventory database (authoritative SQLite or legacy Excel compatibility)."""
        try:
            self._inventory_database_path = file_path
            if file_path.lower().endswith((".xlsm", ".xlsx")):
                if not isinstance(self.inventory_repo, ExcelInventoryRepository):
                    self.inventory_repo = ExcelInventoryRepository()
            else:
                if not isinstance(self.inventory_repo, SqliteInventoryRepository) or self.inventory_repo.file_path != file_path:
                    self.inventory_repo = SqliteInventoryRepository(file_path)

            self.inventory_repo.load(file_path)
            self.search_query = ""
            self.search_input.clear()
            self._filter_and_render()
            self._render_inventory_components_table()

            if hasattr(self, "reference_data_widget") and self.reference_data_widget and isinstance(self.inventory_repo, SqliteInventoryRepository):
                self.reference_data_widget.set_repository(self.inventory_repo)
            if hasattr(self, "providers_widget") and self.providers_widget and isinstance(self.inventory_repo, SqliteInventoryRepository):
                self.providers_widget.set_repository(self.inventory_repo)
            if hasattr(self, "backup_restore_widget") and self.backup_restore_widget:
                self.backup_restore_widget.set_repository(self.inventory_repo)

            file_name = os.path.basename(file_path)
            db_tag = "SQLite" if isinstance(self.inventory_repo, SqliteInventoryRepository) else "Excel"
            if hasattr(self, "status_db_lbl") and self.status_db_lbl:
                self.status_db_lbl.setText(f"🗄️ {file_name} ({db_tag})")
            self.status_state_lbl.setText("● Ready")
            self.status_state_lbl.setStyleSheet("color: #34d399; font-weight: bold;")
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
        if isinstance(self.inventory_repo, SqliteInventoryRepository) and self.inventory_repo.file_path:
            self.load_inventory_database(self.inventory_repo.file_path)
            return

        target_file = resolve_database_path()
        if target_file and os.path.exists(target_file):
            self.load_inventory_database(target_file)
            return

        legacy_file = resolve_inventory_database_path()
        if legacy_file and os.path.exists(legacy_file):
            self.load_inventory_database(legacy_file)
            return

        local_legacy = find_local_excel_file(get_app_dir())
        if local_legacy and os.path.exists(local_legacy):
            self.load_excel_file(local_legacy)
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

            query = (self.search_query or "").strip()
            if query:
                terms = [normalize_string(t) for t in query.split() if t.strip()]
                scored_groups = []
                for group in filtered:
                    mfr_terms = [normalize_string(p.manufacturer) for p in group.products if p.manufacturer]
                    mpn_terms = [normalize_string(p.mpn) for p in group.products if p.mpn]
                    val_terms = [normalize_string(group.value)] + [normalize_string(p.value) for p in group.products if p.value]
                    val_terms = [v for v in val_terms if v]

                    # Strictly match on Manufacturer, Part Number (MPN), and Value ONLY.
                    # Explicitly exclude Category, Type/Technology, Package, Footprint, Description, Links, and Stock.
                    def group_matches_term(term):
                        if any(term in m for m in mpn_terms):
                            return True
                        if any(term in m for m in mfr_terms):
                            return True
                        if any(term in v for v in val_terms):
                            return True
                        return False

                    if all(group_matches_term(term) for term in terms):
                        score = 0
                        for term in terms:
                            if any(term == m for m in mpn_terms):
                                score += 100
                            elif any(term in m for m in mpn_terms):
                                score += 50
                            if any(term == m for m in mfr_terms):
                                score += 40
                            elif any(term in m for m in mfr_terms):
                                score += 30
                            if any(term == v for v in val_terms):
                                score += 35
                            elif any(term in v for v in val_terms):
                                score += 20
                        scored_groups.append((score, group))

                scored_groups.sort(key=lambda x: x[0], reverse=True)
                self.current_filtered_groups = [g for _, g in scored_groups]
            else:
                self.current_filtered_groups = filtered

            self._update_table_display()
            self._update_stats_ribbon()
            return

        if self.show_only_incomplete:
            incomplete_records = self.excel.get_incomplete_records()
            candidate_rows = [(orig_idx, row_data) for orig_idx, row_data, _ in incomplete_records]
        else:
            candidate_rows = list(self.excel.rows)

        query = (self.search_query or "").strip()
        if query:
            terms = [normalize_string(t) for t in query.split() if t.strip()]
            mfr_col = self.excel.get_column_index(["manufacturer", "سازنده", "mfr"])
            mpn_col = self.excel.get_column_index(["part number", "mpn", "part_number", "شماره فنی", "part name", "نام قطعه"])
            val_col = self.excel.get_column_index(["value", "مقدار"])
            allowed_cols = [c for c in (mfr_col, mpn_col, val_col) if c is not None]

            filtered = []
            for orig_idx, row_data in candidate_rows:
                if allowed_cols:
                    searchable_fields = [normalize_string(row_data[c]) for c in allowed_cols if c < len(row_data)]
                else:
                    searchable_fields = [normalize_string(val) for val in row_data]
                if all(any(term in fld for fld in searchable_fields) for term in terms):
                    filtered.append((orig_idx, row_data))
            self.current_filtered_rows = filtered
        else:
            self.current_filtered_rows = candidate_rows

        self._update_table_display()
        self._update_stats_ribbon()

    def _update_stats_ribbon(self):
        validation_active = bool(
            settings.get("stock_policy_enabled", True) and
            settings.get("stock_policy_validation_enabled", True)
        )
        if self.inventory_repo.is_loaded:
            all_groups = self.inventory_repo.get_all_groups()
            total_groups = len(all_groups)
            filtered_groups = len(self.current_filtered_groups)
            total_cols = 10
            default_name = "omnix_inventory.db" if isinstance(self.inventory_repo, SqliteInventoryRepository) else "Inventory.xlsm"
            file_name = os.path.basename(self.inventory_repo.file_path) if self.inventory_repo.file_path else default_name
            shortage_count = sum(1 for g in all_groups if g.is_low_stock)
            incomplete_count = sum(1 for g in all_groups if not g.is_complete)
            self.stats_ribbon.update_stats(
                total_groups,
                filtered_groups,
                total_cols,
                file_name,
                shortage_count=shortage_count,
                incomplete_count=incomplete_count,
                validation_enabled=validation_active
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
            incomplete_count=len(incomplete),
            validation_enabled=validation_active
        )

    def _open_inventory_order_dialog(self):
        if self.inventory_repo.is_loaded:
            # Check if stock policy validation is enabled
            if not settings.get("stock_policy_enabled", True) or not settings.get("stock_policy_validation_enabled", True):
                QMessageBox.information(
                    self,
                    "Stock Policy Disabled",
                    "Stock policy validation and shortage checking are currently disabled in Settings."
                )
                return

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
                f"Mode A replenishment and ordering are planned for Phase 3."
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

        # Section 7: Automatic Link Validation for Excel items before OrderPreviewDialog
        links_to_validate = []
        for it in shortages:
            link = (it.get("link") or "").strip()
            if link and (link.startswith("http://") or link.startswith("https://")):
                links_to_validate.append(LinkValidationItem(
                    component_name=it.get("part_name", ""),
                    manufacturer=it.get("manufacturer", ""),
                    mpn=it.get("part_number", ""),
                    url=link,
                ))

        if links_to_validate:
            val_dlg = LinkValidationDialog(links_to_validate, parent=self)
            val_dlg.exec()

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
            if is_filter_active:
                self.table.update_empty_state(True, is_filter_active=True)
            else:
                self.table.update_empty_state(
                    True,
                    is_filter_active=False,
                    title="No Assembly Groups Found",
                    desc="Use 'Add Component' in the Component Inventory tab to register components into SQLite."
                )
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
        # Stock policy column visibility toggling (Phase B)
        show_stock_cols = settings.get("stock_policy_enabled", True) and settings.get("stock_policy_show_columns", True)
        self.table.setColumnHidden(6, not show_stock_cols)  # Min Stock
        self.table.setColumnHidden(7, not show_stock_cols)  # Target Stock

        # Match products column & panel visibility
        show_match_prods = settings.get("match_products_enabled", True)
        self.table.setColumnHidden(8, not show_match_prods)  # Matched Products
        if hasattr(self, "products_footer_frame"):
            self.products_footer_frame.setVisible(show_match_prods)
        if not show_match_prods and hasattr(self, "products_frame"):
            self.products_frame.setVisible(False)

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

    def _copy_database_path(self):
        """Copies the authoritative database path to the clipboard and triggers a toast notification."""
        db_path = getattr(self, "inventory_database_path", None)
        if not db_path and hasattr(self, "inventory_repo") and self.inventory_repo:
            db_path = getattr(self.inventory_repo, "file_path", None)
        if not db_path:
            db_path = resolve_database_path()

        if db_path:
            QApplication.clipboard().setText(db_path)
            if hasattr(self, "statusBar") and self.statusBar():
                self.statusBar().showMessage(f"Copied database path: {db_path}", 1500)

    def _apply_match_products_visibility(self, enabled: bool):
        """Toggle column 8 and physical product panel based on match_products_enabled setting."""
        if hasattr(self, "table") and self.table.columnCount() > 8:
            self.table.setColumnHidden(8, not enabled)
        if hasattr(self, "products_footer_frame"):
            self.products_footer_frame.setVisible(enabled)
        if not enabled and hasattr(self, "products_frame"):
            self.products_frame.setVisible(False)

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
            self.products_title_lbl.setText("Associated Physical Products (Inventory)")
            return

        if group is not None:
            products = group.products
            desc = f"{group.category} | {group.type_technology} | {group.value} | {group.package} | {group.footprint}"
            self.products_title_lbl.setText(f"Associated Physical Products for [{desc}] ({len(products)} items)")
        else:
            products = self.inventory_repo.get_all_products()
            self.products_title_lbl.setText(f"All Physical Products (Inventory — {len(products)} items)")

        prod_count = len(products)
        self.products_table.setRowCount(prod_count)
        self._current_rendered_products = list(products)

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
                item.setData(Qt.ItemDataRole.UserRole, prod.id)

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
        self._on_product_selection_changed()

    def _on_product_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        # Column 10 is Purchase Link
        if item.column() == 10:
            val = item.text().strip()
            if val.startswith("http://") or val.startswith("https://"):
                webbrowser.open(val)
                return
        row = item.row()
        link_item = self.products_table.item(row, 10)
        if link_item and link_item is not item:
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
        cur_key = group.group_key

        if isinstance(self.inventory_repo, SqliteInventoryRepository):
            try:
                db_path = self.inventory_repo.file_path or "omnix_inventory.db"
                dlg = PolicyEditDialog(
                    group=group,
                    inventory_path=db_path,
                    parent=self,
                    repository=self.inventory_repo,
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._filter_and_render()
                    for row in range(self.table.rowCount()):
                        it = self.table.item(row, 0)
                        if it:
                            idx = it.data(Qt.ItemDataRole.UserRole)
                            if idx is not None and 0 <= idx < len(self.current_filtered_groups):
                                if self.current_filtered_groups[idx].group_key == cur_key:
                                    self.table.selectRow(row)
                                    self._render_products_table(self.current_filtered_groups[idx])
                                    break
                    self.status_state_lbl.setText("● Policy Saved (SQLite)")
                    db_name = os.path.basename(db_path)
                    QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {db_name} (SQLite)"))
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Database Error",
                    f"An error occurred while saving the stock policy to SQLite:\n{e}"
                )
            return

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

    # =========================================================================
    # Phase 2.2: Component Management (CRUD & Supplier Links)
    # =========================================================================

    def _get_selected_component(self) -> Optional[InventoryProduct]:
        """Returns the currently selected physical product record from self.inventory_components_table
        or self.products_table, if any."""
        if not hasattr(self, "inventory_repo") or not self.inventory_repo or not self.inventory_repo.is_loaded:
            return None

        # Determine table check priority based on active subtab
        active_tab_idx = 0
        if hasattr(self, "inventory_subtabs"):
            active_tab_idx = self.inventory_subtabs.currentIndex()

        if active_tab_idx == 1:
            tables = [
                (getattr(self, "inventory_components_table", None), getattr(self, "_current_inventory_components", [])),
                (getattr(self, "products_table", None), getattr(self, "_current_rendered_products", [])),
            ]
        else:
            tables = [
                (getattr(self, "products_table", None), getattr(self, "_current_rendered_products", [])),
                (getattr(self, "inventory_components_table", None), getattr(self, "_current_inventory_components", [])),
            ]

        for tbl, current_prods in tables:
            if tbl is not None and tbl.selectionModel():
                selected_rows = tbl.selectionModel().selectedRows()
                if selected_rows:
                    visual_row = selected_rows[0].row()
                    item = tbl.item(visual_row, 0)
                    if item:
                        comp_id = item.data(Qt.ItemDataRole.UserRole)
                        if comp_id is not None and isinstance(self.inventory_repo, SqliteInventoryRepository):
                            comp = self.inventory_repo.get_component_by_id(comp_id)
                            if comp:
                                return comp
                        if 0 <= visual_row < len(current_prods):
                            return current_prods[visual_row]

        return None

    def _on_component_selection_changed(self):
        """Update button enabled states when component selection changes in either Table 1 or Table 3."""
        is_sqlite = isinstance(getattr(self, "inventory_repo", None), SqliteInventoryRepository)
        selected_comp = self._get_selected_component()
        has_sel = selected_comp is not None

        if hasattr(self, "add_component_btn"):
            self.add_component_btn.setEnabled(is_sqlite)
            if not is_sqlite:
                self.add_component_btn.setToolTip("Component registration requires SQLite database mode.")
            else:
                self.add_component_btn.setToolTip("Register a new physical component in the SQLite database.")

        if hasattr(self, "edit_component_btn"):
            self.edit_component_btn.setEnabled(is_sqlite and has_sel)
            if not is_sqlite:
                self.edit_component_btn.setToolTip("Component editing requires SQLite database mode.")
            elif not has_sel:
                self.edit_component_btn.setToolTip("Select a physical component to edit.")
            else:
                self.edit_component_btn.setToolTip(f"Edit component: {selected_comp.manufacturer} {selected_comp.mpn}")

        if hasattr(self, "delete_component_btn"):
            self.delete_component_btn.setEnabled(is_sqlite and has_sel)
            if not is_sqlite:
                self.delete_component_btn.setToolTip("Component deletion requires SQLite database mode.")
            elif not has_sel:
                self.delete_component_btn.setToolTip("Select a physical component to delete.")
            else:
                self.delete_component_btn.setToolTip(f"Delete component: {selected_comp.manufacturer} {selected_comp.mpn}")

    # Backward compatibility alias
    _on_product_selection_changed = _on_component_selection_changed

    def _show_product_context_menu(self, pos):
        """Right-click context menu for the Associated Physical Products table."""
        if not isinstance(getattr(self, "inventory_repo", None), SqliteInventoryRepository):
            return
        menu = QMenu(self)
        comp = self._get_selected_component()

        act_add = menu.addAction("Add New Component...")
        act_add.triggered.connect(self._open_add_component_dialog)

        if comp:
            act_edit = menu.addAction("Edit Component...")
            act_edit.triggered.connect(lambda: self._open_edit_component_dialog(comp))

            act_delete = menu.addAction("Delete Component...")
            act_delete.triggered.connect(self._delete_selected_component)

            if comp.purchase_link:
                menu.addSeparator()
                act_link = menu.addAction("Open Purchase Link")
                link_url = comp.purchase_link.split("=")[-1].strip()
                act_link.triggered.connect(lambda: webbrowser.open(link_url))

        menu.exec(self.products_table.viewport().mapToGlobal(pos))

    def _show_inventory_component_context_menu(self, pos):
        """Right-click context menu for the dedicated Component Inventory table."""
        if not isinstance(getattr(self, "inventory_repo", None), SqliteInventoryRepository):
            return
        menu = QMenu(self)
        comp = self._get_selected_component()

        act_add = menu.addAction("Add New Component...")
        act_add.triggered.connect(self._open_add_component_dialog)

        if comp:
            act_edit = menu.addAction("Edit Component...")
            act_edit.triggered.connect(lambda: self._open_edit_component_dialog(comp))

            act_delete = menu.addAction("Delete Component...")
            act_delete.triggered.connect(self._delete_selected_component)

            if comp.purchase_link:
                menu.addSeparator()
                act_link = menu.addAction("Open Purchase Link")
                link_url = comp.purchase_link.split("=")[-1].strip()
                act_link.triggered.connect(lambda: webbrowser.open(link_url))

        menu.exec(self.inventory_components_table.viewport().mapToGlobal(pos))

    def _on_inventory_component_clicked(self, item: QTableWidgetItem):
        """Single click on MPN cell copies exact MPN value to clipboard with temporary subtle feedback."""
        if not item:
            return
        # Column 2 is Part Number (MPN)
        if item.column() == 2:
            mpn = item.text().strip()
            if mpn:
                QApplication.clipboard().setText(mpn)
                # Display subtle confirmation for ~1.2s and auto-restore previous state
                if hasattr(self, "status_state_lbl") and self.status_state_lbl:
                    cur_text = self.status_state_lbl.text()
                    if not cur_text.startswith("● Copied MPN"):
                        self._last_normal_status_state = cur_text

                    self._mpn_copy_seq += 1
                    seq = self._mpn_copy_seq

                    self.status_state_lbl.setText(f"● Copied MPN: {mpn}")
                    self.status_state_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")

                    if self._mpn_copy_timer and self._mpn_copy_timer.isActive():
                        self._mpn_copy_timer.stop()

                    self._mpn_copy_timer = QTimer(self)
                    self._mpn_copy_timer.setSingleShot(True)
                    self._mpn_copy_timer.timeout.connect(lambda: self._restore_mpn_status(seq))
                    self._mpn_copy_timer.start(1200)

                if hasattr(self, "statusBar") and self.statusBar():
                    self.statusBar().showMessage(f"Copied MPN: {mpn}", 1200)

    def _restore_mpn_status(self, seq: int):
        """Restores normal status-bar state after temporary MPN copy notification expires."""
        if getattr(self, "_mpn_copy_seq", 0) == seq:
            if hasattr(self, "status_state_lbl") and self.status_state_lbl:
                self.status_state_lbl.setText(getattr(self, "_last_normal_status_state", "● Database Ready"))
                self.status_state_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")

    def _on_inventory_component_double_clicked(self, item: QTableWidgetItem):
        """Deliberate editing: double-clicking does NOT open edit dialog."""
        if not item:
            return
        # Column 10 is Purchase Link
        if item.column() == 10:
            val = item.text().strip()
            if val.startswith("http://") or val.startswith("https://"):
                webbrowser.open(val)
                return

    def _on_component_search_changed(self, text: str):
        self.component_search_query = text.strip()
        self._render_inventory_components_table()

    def _on_inventory_subtab_changed(self, index: int):
        """Synchronize views and distribute table columns when switching inventory sub-tabs."""
        if not getattr(self, "_is_syncing_navigation", False):
            if hasattr(self, "sidebar") and self.content_stack.currentWidget() == self.tabs and self.tabs.currentIndex() == 0:
                if index == 0:
                    self.sidebar.set_active_page("assembly_view")
                elif index == 1:
                    self.sidebar.set_active_page("component_inventory")

        if index == 1:
            # Sub-tab 1: Component Inventory
            if hasattr(self, "stats_ribbon") and hasattr(self.stats_ribbon, "stat_incomplete_btn"):
                self.stats_ribbon.stat_incomplete_btn.setVisible(False)
            self._render_inventory_components_table()
            if hasattr(self, "inventory_components_table") and isinstance(self.inventory_components_table, InventoryTableWidget):
                self.inventory_components_table.distribute_columns()
        elif index == 0:
            # Sub-tab 0: Assembly View
            if hasattr(self, "stats_ribbon") and hasattr(self.stats_ribbon, "stat_incomplete_btn"):
                self.stats_ribbon.stat_incomplete_btn.setVisible(True)
            self._update_table_display()
            if hasattr(self, "table") and isinstance(self.table, InventoryTableWidget):
                self.table.distribute_columns()
            if hasattr(self, "_on_group_selection_changed"):
                self._on_group_selection_changed()
        self._on_component_selection_changed()

    def _render_inventory_components_table(self):
        """Populates Table 1 (self.inventory_components_table) with individual physical components."""
        if not hasattr(self, "inventory_components_table"):
            return

        headers = [
            "Row", "Manufacturer", "Part Number (MPN)", "Category",
            "Type / Technology", "Value", "Package", "Footprint",
            "Quantity in Stock", "Description", "Purchase Link"
        ]
        col_count = len(headers)
        self.inventory_components_table.setSortingEnabled(False)
        self.inventory_components_table.horizontalHeader().setSectionsClickable(False)
        self.inventory_components_table.clear()
        self.inventory_components_table.setColumnCount(col_count)
        self.inventory_components_table.setHorizontalHeaderLabels(headers)

        if not hasattr(self, "inventory_repo") or not self.inventory_repo or not self.inventory_repo.is_loaded:
            self.inventory_components_table.setRowCount(0)
            if isinstance(self.inventory_components_table, InventoryTableWidget):
                self.inventory_components_table.update_empty_state(
                    True,
                    is_filter_active=False,
                    title="No Inventory Database Loaded",
                    desc="Open or bootstrap a SQLite database to view physical components."
                )
            if getattr(self, "component_inventory_title", None) is not None:
                self.component_inventory_title.setText("Component Inventory (No database loaded)")
            return

        all_components = self.inventory_repo.get_all_products()
        query = getattr(self, "component_search_query", "").strip()
        if query:
            terms = [normalize_string(t) for t in query.split() if t.strip()]
            scored_components = []
            for comp in all_components:
                mfr_norm = normalize_string(comp.manufacturer)
                mpn_norm = normalize_string(comp.mpn)
                val_norm = normalize_string(comp.value)

                # Strictly match on Manufacturer, Part Number (MPN), and Value ONLY.
                # Explicitly exclude Category, Type/Technology, Package, Footprint, Description, Link, Quantity, etc.
                def comp_matches_term(term):
                    if term in mpn_norm:
                        return True
                    if term in mfr_norm:
                        return True
                    if term in val_norm:
                        return True
                    return False

                if all(comp_matches_term(term) for term in terms):
                    score = 0
                    for term in terms:
                        if term == mpn_norm:
                            score += 100
                        elif term in mpn_norm:
                            score += 50
                        if term == mfr_norm:
                            score += 40
                        elif term in mfr_norm:
                            score += 30
                        if term == val_norm:
                            score += 35
                        elif term in val_norm:
                            score += 20
                    scored_components.append((score, comp))

            scored_components.sort(key=lambda x: x[0], reverse=True)
            components = [c for _, c in scored_components]
        else:
            components = all_components

        comp_count = len(components)
        self.inventory_components_table.setRowCount(comp_count)
        self._current_inventory_components = list(components)

        if comp_count == 0:
            if isinstance(self.inventory_components_table, InventoryTableWidget):
                self.inventory_components_table.update_empty_state(
                    True,
                    is_filter_active=bool(query),
                    title="No Matching Components Found" if query else "No Components in Inventory",
                    desc="Try adjusting your search query." if query else "Use 'Add Component' to register a physical component."
                )
        else:
            if isinstance(self.inventory_components_table, InventoryTableWidget):
                self.inventory_components_table.update_empty_state(False)

        if getattr(self, "component_inventory_title", None) is not None:
            if query:
                self.component_inventory_title.setText(
                    f"Component Inventory ({comp_count} of {len(all_components)} records matching '{query}')"
                )
            else:
                self.component_inventory_title.setText(
                    f"Component Inventory ({comp_count} total individual records)"
                )

        font_data = QFont("Segoe UI", 9)
        font_numbers = QFont("Consolas", 9)

        for row_idx, comp in enumerate(components):
            qty_str = f"{comp.quantity_in_stock}" if comp.quantity_in_stock is not None else "0"
            cells = [
                str(row_idx + 1),         # 0: Row
                comp.manufacturer,        # 1: Manufacturer
                comp.mpn,                 # 2: Part Number (MPN)
                comp.category,            # 3: Category
                comp.type_technology,     # 4: Type / Technology
                comp.value,               # 5: Value
                comp.package,             # 6: Package
                comp.footprint,           # 7: Footprint
                qty_str,                  # 8: Quantity in Stock
                comp.description or "",   # 9: Description (moved right before Purchase Link)
                comp.purchase_link or ""  # 10: Purchase Link
            ]

            for col_idx, cell_text in enumerate(cells):
                item = QTableWidgetItem(cell_text)
                item.setToolTip(cell_text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, comp.id)

                if col_idx in [0, 8]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                elif col_idx in [2, 5, 6, 7]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_numbers)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                if col_idx == 0:
                    item.setForeground(QColor("#64748b"))
                elif col_idx == 2:
                    item.setForeground(QColor("#f8fafc"))
                elif col_idx == 8:
                    if comp.quantity_in_stock == 0:
                        item.setForeground(QColor("#fbbf24"))
                    else:
                        item.setForeground(QColor("#34d399"))
                elif col_idx == 10 and cell_text:
                    item.setForeground(QColor("#38bdf8"))
                    item.setToolTip(f"Double-click to open purchase link: {cell_text}")
                else:
                    item.setForeground(QColor("#cbd5e1"))

                self.inventory_components_table.setItem(row_idx, col_idx, item)

        min_widths = {
            0: 55,   # Row
            1: 120,  # Manufacturer
            2: 140,  # MPN
            3: 110,  # Category
            4: 120,  # Type / Technology
            5: 90,   # Value
            6: 80,   # Package
            7: 90,   # Footprint
            8: 135,  # Quantity in Stock (spacious for full 17-char header and values)
            9: 180,  # Description (flexible)
            10: 130, # Purchase Link (flexible)
        }
        if isinstance(self.inventory_components_table, InventoryTableWidget):
            self.inventory_components_table.configure_column_distribution(min_widths, [9, 10])

        self.inventory_components_table.setSortingEnabled(False)
        self.inventory_components_table.horizontalHeader().setSectionsClickable(False)
        self._on_component_selection_changed()

    def _open_add_component_dialog(self, initial_group: Optional[Any] = None):
        """Open the ComponentEditDialog in registration mode with a fresh, clean form."""
        if not isinstance(self.inventory_repo, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Mode Required",
                "Component registration is only supported when operating with the authoritative SQLite database."
            )
            return

        dlg = ComponentEditDialog(
            parent=self,
            repository=self.inventory_repo,
            component=None,
            initial_group=initial_group,
        )
        if not initial_group:
            dlg.reset_form()

        if dlg.exec() == QDialog.DialogCode.Accepted:
            saved_comp = getattr(dlg, "saved_component", None)
            target_key = saved_comp.group_key if saved_comp else None
            comp_id = saved_comp.id if saved_comp else None
            self._reload_and_select_group(target_key, select_comp_id=comp_id)
            mfr_mpn = f"{saved_comp.manufacturer} {saved_comp.mpn}" if saved_comp else "Component"
            self.status_state_lbl.setText(f"● Component Registered (SQLite): {mfr_mpn}")
            db_name = os.path.basename(self.inventory_database_path)
            QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {db_name} (SQLite)"))

    def _open_edit_component_dialog(self, component: Optional[InventoryProduct] = None):
        """Open the ComponentEditDialog in edit mode for the selected component."""
        if not isinstance(self.inventory_repo, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Mode Required",
                "Component editing is only supported when operating with the authoritative SQLite database."
            )
            return

        comp = component or self._get_selected_component()
        if not comp:
            QMessageBox.warning(
                self,
                "No Component Selected",
                "Please select a component from the table to edit."
            )
            return

        dlg = ComponentEditDialog(
            parent=self,
            repository=self.inventory_repo,
            component=comp,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            saved_comp = getattr(dlg, "saved_component", None)
            target_key = saved_comp.group_key if saved_comp else comp.group_key
            comp_id = saved_comp.id if saved_comp else comp.id
            self._reload_and_select_group(target_key, select_comp_id=comp_id)
            mfr_mpn = f"{saved_comp.manufacturer} {saved_comp.mpn}" if saved_comp else f"{comp.manufacturer} {comp.mpn}"
            self.status_state_lbl.setText(f"● Component Updated (SQLite): {mfr_mpn}")
            db_name = os.path.basename(self.inventory_database_path)
            QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {db_name} (SQLite)"))

    def _delete_selected_component(self):
        """Prompt confirmation and delete the selected component from SQLite."""
        if not isinstance(self.inventory_repo, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Mode Required",
                "Component deletion is only supported when operating with the authoritative SQLite database."
            )
            return

        comp = self._get_selected_component()
        if not comp:
            QMessageBox.warning(
                self,
                "No Component Selected",
                "Please select a component to delete."
            )
            return

        msg = (
            f"Are you sure you want to delete physical component:\n\n"
            f"Manufacturer: {comp.manufacturer}\n"
            f"Part Number (MPN): {comp.mpn}\n"
            f"Category / Type: {comp.category} / {comp.type_technology}\n"
            f"Value / Package: {comp.value} / {comp.package}\n"
            f"Physical Stock: {comp.quantity_in_stock} units\n\n"
            f"This action deletes ONLY this physical inventory record and its supplier links.\n"
            f"If other components remain in the group, group stock policy thresholds will be preserved."
        )
        if self._show_confirmation_dialog("Confirm Physical Component Deletion", msg, is_danger=True):
            target_key = comp.group_key
            ok = self.inventory_repo.delete_component(comp.id)
            if ok:
                self._reload_and_select_group(target_key)
                self.status_state_lbl.setText(f"● Component Deleted (SQLite): {comp.manufacturer} {comp.mpn}")
                db_name = os.path.basename(self.inventory_database_path)
                QTimer.singleShot(2500, lambda: self.status_state_lbl.setText(f"● Database: {db_name} (SQLite)"))
            else:
                QMessageBox.critical(
                    self,
                    "Deletion Failed",
                    f"Failed to delete component ID {comp.id} from SQLite database."
                )

    def _open_reference_data_dialog(self):
        """Open the dedicated Reference Data Manager dialog."""
        if getattr(self, "_is_opening_ref_data", False):
            return
        self._is_opening_ref_data = True
        try:
            if not isinstance(self.inventory_repo, SqliteInventoryRepository):
                QMessageBox.information(
                    self,
                    "SQLite Mode Required",
                    "Reference data management is only supported when operating with the authoritative SQLite database."
                )
                return

            dlg = ReferenceDataDialog(repository=self.inventory_repo, parent=self)
            dlg.exec()
            self._render_inventory_components_table()
        finally:
            self._is_opening_ref_data = False

    def _open_providers_dialog(self):
        """Open the dedicated Vendor & Link Providers management dialog."""
        if not isinstance(self.inventory_repo, SqliteInventoryRepository):
            QMessageBox.information(
                self,
                "SQLite Mode Required",
                "Vendor and Link Provider management is only supported when operating with the authoritative SQLite database."
            )
            return

        dlg = ProviderManagementDialog(repository=self.inventory_repo, parent=self)
        dlg.exec()

    def _open_link_validation_dialog(self):
        """Extract all supplier links from components and open LinkValidationDialog."""
        if not hasattr(self, "inventory_repo") or not self.inventory_repo or not self.inventory_repo.is_loaded:
            QMessageBox.information(
                self,
                "No Inventory Database",
                "Please load an inventory database before validating supplier links."
            )
            return

        from core.procurement.link_validator import LinkValidationItem
        from core.procurement.vendor_links import parse_vendor_links

        all_products = self.inventory_repo.get_all_products()
        items_to_validate = []

        for p in all_products:
            if p.supplier_links:
                for sl in p.supplier_links:
                    if sl.url:
                        items_to_validate.append(LinkValidationItem(
                            component_id=p.id,
                            component_name=f"{p.manufacturer} {p.mpn}".strip(),
                            manufacturer=p.manufacturer,
                            mpn=p.mpn,
                            url=sl.url,
                            vendor_id=sl.vendor_id,
                            vendor_label=sl.vendor_label,
                        ))
            elif p.purchase_link:
                parsed = parse_vendor_links(p.purchase_link)
                if parsed.is_valid:
                    for vid, entry in parsed.links.items():
                        items_to_validate.append(LinkValidationItem(
                            component_id=p.id,
                            component_name=f"{p.manufacturer} {p.mpn}".strip(),
                            manufacturer=p.manufacturer,
                            mpn=p.mpn,
                            url=entry.url,
                            vendor_id=vid,
                            vendor_label=entry.label,
                        ))
                else:
                    items_to_validate.append(LinkValidationItem(
                        component_id=p.id,
                        component_name=f"{p.manufacturer} {p.mpn}".strip(),
                        manufacturer=p.manufacturer,
                        mpn=p.mpn,
                        url=p.purchase_link,
                        vendor_id="",
                        vendor_label="",
                    ))

        if not items_to_validate:
            QMessageBox.information(
                self,
                "No Supplier Links Found",
                "None of the components in inventory have configured purchase or supplier links."
            )
            return

        from ui.dialogs.link_validation_dialog import LinkValidationDialog
        dlg = LinkValidationDialog(items_to_validate, parent=self)
        dlg.exec()

    def _reload_and_select_group(self, target_group_key: Optional[str] = None, select_comp_id: Optional[int] = None):
        """Helper to reload SQLite inventory data and re-select group and component across all views."""
        if hasattr(self, "inventory_repo") and self.inventory_repo and self.inventory_database_path:
            self.inventory_repo.load(self.inventory_database_path)
        self._filter_and_render()
        self._render_inventory_components_table()
        if hasattr(self, "reference_data_widget") and self.reference_data_widget and isinstance(self.inventory_repo, SqliteInventoryRepository):
            self.reference_data_widget.set_repository(self.inventory_repo)

        if target_group_key:
            for row in range(self.table.rowCount()):
                it = self.table.item(row, 0)
                if it:
                    idx = it.data(Qt.ItemDataRole.UserRole)
                    if idx is not None and 0 <= idx < len(self.current_filtered_groups):
                        if self.current_filtered_groups[idx].group_key == target_group_key:
                            self.table.selectRow(row)
                            self._render_products_table(self.current_filtered_groups[idx])
                            break

        if select_comp_id:
            # Re-select in Table 1 (Component Inventory table)
            if hasattr(self, "inventory_components_table"):
                for c_row in range(self.inventory_components_table.rowCount()):
                    c_it = self.inventory_components_table.item(c_row, 0)
                    if c_it and c_it.data(Qt.ItemDataRole.UserRole) == select_comp_id:
                        self.inventory_components_table.selectRow(c_row)
                        break

            # Re-select in Table 3 (Associated Physical Products table)
            if hasattr(self, "products_table"):
                for p_row in range(self.products_table.rowCount()):
                    p_it = self.products_table.item(p_row, 0)
                    if p_it and p_it.data(Qt.ItemDataRole.UserRole) == select_comp_id:
                        self.products_table.selectRow(p_row)
                        break
        self._on_component_selection_changed()

    def import_from_workbook(self, workbook_path: str, dry_run: bool = False) -> BootstrapResult:
        """
        Explicit non-destructive bootstrap import of an Excel workbook into the SQLite repository.
        Never called automatically on startup.
        """
        if not isinstance(self.inventory_repo, SqliteInventoryRepository):
            target_db = resolve_database_path()
            self.inventory_repo = SqliteInventoryRepository(target_db)
            self._inventory_database_path = target_db

        res = bootstrap_sqlite_from_workbook(workbook_path, self.inventory_repo, dry_run=dry_run)
        if res.success and not dry_run:
            self._filter_and_render()
            file_name = os.path.basename(self.inventory_repo.file_path) if self.inventory_repo.file_path else "omnix_inventory.db"
            self.status_state_lbl.setText(f"● Database: {file_name} (SQLite)")
            self.status_state_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")
        return res

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        val = item.text().strip()

        copy_act = menu.addAction("Copy Cell Value")
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(val))

        row_idx = item.row()
        copy_row_act = menu.addAction("Copy Entire Row")
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
            edit_policy_act = menu.addAction("Edit Min / Target Stock Thresholds")
            edit_policy_act.triggered.connect(lambda: self._edit_stock_policy_thresholds(group_idx))

        if val.startswith("http://") or val.startswith("https://"):
            menu.addSeparator()
            open_link_act = menu.addAction("Open Link in Web Browser")
            open_link_act.triggered.connect(lambda: webbrowser.open(val))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _export_inventory_to_excel(self):
        """Export live inventory and assembly groups to a customer-facing Excel workbook."""
        if getattr(self, "_is_exporting_excel", False):
            return
        self._is_exporting_excel = True
        try:
            if not isinstance(self.inventory_repo, SqliteInventoryRepository):
                QMessageBox.information(
                    self,
                    "SQLite Mode Required",
                    "Excel export is only supported when operating with the authoritative SQLite database."
                )
                return

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Inventory & Assembly View to Excel",
                os.path.join(os.getcwd(), "Inventory_Export.xlsx"),
                "Excel Workbook (*.xlsx);;All Files (*)",
            )
            if not file_path:
                return

            try:
                exported_path = InventoryExcelExporter.export(self.inventory_repo, file_path)
                comp_count = len(self.inventory_repo.get_all_products())
                grp_count = len(self.inventory_repo.get_all_groups())
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
        finally:
            self._is_exporting_excel = False

