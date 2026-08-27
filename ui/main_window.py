import os
import sys
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QStatusBar, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut, QIcon, QPixmap

from config import APP_NAME, APP_SUBTITLE, get_app_dir, get_bundle_dir
from excel_loader import ExcelDataLoader, find_local_excel_file
from ui.widgets import (
    InventoryTableWidget,
    StatsRibbonWidget,
    FilterBarWidget
)


class MainWindow(QMainWindow):
    """View-Only Excel Database Browser and Instant Search Application."""

    def __init__(self, default_file: str = None):
        super().__init__()
        self.excel = ExcelDataLoader()
        self.current_filtered_rows = []
        self.search_query = ""
        self._is_force_closing = False

        self.setWindowTitle(f"{APP_NAME} | {APP_SUBTITLE}")
        self.resize(1180, 740)
        self.setMinimumSize(900, 580)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Set application icon
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

        # Automatic detection of the Excel database file ONLY strictly next to application
        target_file = default_file
        if not target_file:
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
            self.status_state_lbl.setText("● No Excel file in directory")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")

        QTimer.singleShot(100, self._focus_search)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 14, 16, 10)

        # 1. Header with Logo and Branding
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)

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
        brand_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        brand_sub = QLabel(f"{APP_SUBTITLE} — View Mode")
        brand_sub.setObjectName("brandSubtitle")
        brand_sub.setAlignment(Qt.AlignmentFlag.AlignLeft)
        brand_text_layout.addWidget(brand_title)
        brand_text_layout.addWidget(brand_sub)
        brand_layout.addLayout(brand_text_layout)

        header_layout.addLayout(brand_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # 2. Stats Ribbon
        self.stats_ribbon = StatsRibbonWidget()
        main_layout.addWidget(self.stats_ribbon)

        # 3. Clean Full-Width Live Search Bar
        self.filter_bar = FilterBarWidget()
        self.search_input = self.filter_bar.search_input
        self.filter_bar.searchChanged.connect(self._on_search_changed)
        main_layout.addWidget(self.filter_bar)

        # 4. Main Dynamic Excel Database Table
        self.table = InventoryTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setHighlightSections(False)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        main_layout.addWidget(self.table)

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
        # Slash key [/] to focus search
        slash_sc = QShortcut(QKeySequence(Qt.Key.Key_Slash), self)
        slash_sc.activated.connect(self._focus_search)

        # Ctrl+F to focus search
        ctrl_f = QShortcut(QKeySequence("Ctrl+F"), self)
        ctrl_f.activated.connect(self._focus_search)

        # F5 to reload database file from disk
        f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        f5.activated.connect(self.reload_database)

        # Escape key handler: Deselects / Clears Search, or Prompts Exit on repeat
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.handle_escape_key)

        # Ctrl+Q to close
        ctrl_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        ctrl_q.activated.connect(self.close)

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def handle_escape_key(self):
        """
        Multi-stage Escape key handler:
        1. If search input has text or is focused -> clears search and removes focus.
        2. If table row or cell is selected -> deselects selection.
        3. If state is already completely idle -> prompts confirmation dialog to exit with Yes/No.
        """
        # Step 1: If search input has text or has active focus
        has_search_text = bool(self.search_input.text().strip())
        is_search_focused = self.search_input.hasFocus()

        if has_search_text or is_search_focused:
            if has_search_text:
                self.search_input.clear()
            self.search_input.clearFocus()
            self.table.setFocus()
            return

        # Step 2: If table has any selection or active current item
        has_table_selection = len(self.table.selectedItems()) > 0 or self.table.currentItem() is not None
        if has_table_selection:
            self.table.clearSelection()
            self.table.setCurrentItem(None)
            return

        # Step 3: Idle state -> Prompt confirmation dialog with Yes / No
        self._prompt_exit_confirmation()

    def _prompt_exit_confirmation(self):
        """Show confirmation dialog with Yes / No options."""
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
        """Handle window close event with confirmation dialog."""
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

    def load_excel_file(self, file_path: str):
        """Load and render the first sheet of the Excel workbook."""
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
        """Reload or re-detect the local Excel database file strictly in the app directory."""
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
            self.status_state_lbl.setText("● No Excel file in directory")
            self.status_state_lbl.setStyleSheet("color: #f87171; font-weight: bold;")

    def _on_search_changed(self, query: str):
        self.search_query = query.strip()
        self._filter_and_render()

    def _filter_and_render(self):
        """Filter Excel rows according to query and render to table."""
        self.current_filtered_rows = self.excel.filter_rows(self.search_query)
        self._update_table_display()
        self._update_stats_ribbon()

    def _update_stats_ribbon(self):
        total_rows = self.excel.total_rows
        filtered_rows = len(self.current_filtered_rows)
        total_cols = self.excel.total_columns
        file_name = self.excel.file_name
        self.stats_ribbon.update_stats(total_rows, filtered_rows, total_cols, file_name)

    def _update_table_display(self):
        """Rebuild and populate the QTableWidget with dynamic headers and rows."""
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
            is_filter_active = bool(self.search_query and self.excel.total_rows > 0)
            self.table.update_empty_state(True, is_filter_active=is_filter_active)
            return

        self.table.update_empty_state(False)

        font_data = QFont("Segoe UI", 10)
        font_numbers = QFont("Consolas", 10)

        for visual_row_idx, (orig_idx, row_data) in enumerate(rows):
            for col_idx in range(col_count):
                val_str = row_data[col_idx] if col_idx < len(row_data) else ""
                item = QTableWidgetItem(val_str)
                item.setToolTip(val_str)

                # Alignment and Font
                if val_str.isdigit() or (val_str.replace('.', '', 1).isdigit() and val_str.count('.') < 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFont(font_numbers)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(font_data)

                # Link and exact status highlighting
                lower_val = val_str.lower().strip()
                if lower_val.startswith("http://") or lower_val.startswith("https://"):
                    item.setForeground(QColor("#38bdf8"))  # Neon cyan link
                elif lower_val in ["in_stock", "ok", "available", "موجود"]:
                    item.setForeground(QColor("#34d399"))  # Emerald
                elif lower_val in ["low", "low_stock", "warning", "کسری"]:
                    item.setForeground(QColor("#fbbf24"))  # Amber
                elif lower_val in ["empty", "out_of_stock", "out of stock", "none", "ناموجود"]:
                    item.setForeground(QColor("#f87171"))  # Red
                else:
                    item.setForeground(QColor("#f8fafc"))  # Default clean light text

                self.table.setItem(visual_row_idx, col_idx, item)

        # Header resize modes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Compact index / ID column if detected
        if col_count > 0 and headers[0].lower() in ["id", "#", "row", "index", "ecode"]:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        # Adjust column widths nicely
        for c in range(col_count):
            self.table.resizeColumnToContents(c)
            current_width = self.table.columnWidth(c)
            if current_width < 110:
                self.table.setColumnWidth(c, 110)
            elif current_width > 380:
                self.table.setColumnWidth(c, 380)

        self.table.setSortingEnabled(True)

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
        copy_row_act = menu.addAction("📑 Copy Entire Row (Tab-separated)")
        def _copy_row():
            cols = [self.table.item(row_idx, c).text() if self.table.item(row_idx, c) else "" for c in range(self.table.columnCount())]
            QApplication.clipboard().setText("\t".join(cols))
        copy_row_act.triggered.connect(_copy_row)

        if val.startswith("http://") or val.startswith("https://"):
            menu.addSeparator()
            open_link_act = menu.addAction("🌐 Open Link in Web Browser")
            open_link_act.triggered.connect(lambda: webbrowser.open(val))

        menu.exec(self.table.viewport().mapToGlobal(pos))
