import os
import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QMenu, QFileDialog, QApplication
)
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut, QMouseEvent, QKeyEvent, QIcon, QPixmap

from models import Component
from database import Database
from export_utils import export_to_excel, export_to_csv
from backup_manager import BackupManager
from config import APP_NAME, APP_SUBTITLE
from ui.component_dialog import ComponentDialog
from ui.bulk_stock_dialog import BulkStockDialog
from ui.drawer_view import DrawerViewDialog
from ui.dialog_utils import ask_persian_confirmation
from ui.category_settings_dialog import CategorySettingsDialog
from ui.widgets import (
    auto_detect_text_direction,
    DrawerChipsWidget,
    InventoryTableWidget
)


class MainWindow(QMainWindow):
    """Main window for electronic component inventory and drawer management."""

    def __init__(self, db: Database = None):
        super().__init__()
        self.db = db or Database()
        self.current_components = []
        self.drawer_widgets = {}
        self.expanded_rows = set()

        self.setWindowTitle(f"{APP_SUBTITLE} | {APP_NAME}")
        self.resize(1180, 740)
        self.setMinimumSize(950, 600)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # Set application window icon
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self._init_ui()
        self._setup_shortcuts()
        self.refresh_data()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 14, 16, 12)

        # 1. Brand header and main action buttons
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 6)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(10)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Graphic logo in header
        logo_lbl = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path).scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(logo_pix)
        brand_layout.addWidget(logo_lbl)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setSpacing(2)
        brand_title = QLabel(APP_NAME)
        brand_title.setObjectName("brandTitle")
        brand_sub = QLabel(APP_SUBTITLE)
        brand_sub.setObjectName("brandSubtitle")
        brand_text_layout.addWidget(brand_title)
        brand_text_layout.addWidget(brand_sub)
        brand_layout.addLayout(brand_text_layout)

        header_layout.addLayout(brand_layout)

        header_layout.addStretch()

        # Main action buttons
        self.add_btn = QPushButton("+ ثبت قطعه جدید")
        self.add_btn.setToolTip("ثبت قطعه جدید در انبار (Ctrl+N)")
        self.add_btn.clicked.connect(self._open_add_dialog)
        header_layout.addWidget(self.add_btn)

        self.drawer_view_btn = QPushButton("بازرسی کشوها")
        self.drawer_view_btn.setObjectName("secondaryBtn")
        self.drawer_view_btn.setToolTip("مشاهده تمام قطعات یک کشوی خاص (Ctrl+D)")
        self.drawer_view_btn.clicked.connect(self._open_drawer_view)
        header_layout.addWidget(self.drawer_view_btn)

        self.more_btn = QPushButton("ابزارها")
        self.more_btn.setObjectName("secondaryBtn")
        self._setup_more_menu()
        header_layout.addWidget(self.more_btn)

        main_layout.addLayout(header_layout)

        # 2. Status ribbon pills
        ribbon_frame = QFrame()
        ribbon_frame.setObjectName("ribbonFrame")
        ribbon_layout = QHBoxLayout(ribbon_frame)
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

        main_layout.addWidget(ribbon_frame)

        # 3. Search and filters bar
        filter_card = QFrame()
        filter_card.setObjectName("cardFrame")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجوی پارت‌نامبر، مقدار (10k)، نام، پکیج یا شماره کشو... (کلید /)")
        self.search_input.textChanged.connect(self._on_filter_changed)
        self.search_input.returnPressed.connect(self._on_enter_pressed)
        filter_layout.addWidget(self.search_input, 3)

        self.category_filter = QComboBox()
        self._populate_category_filter()
        self.category_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.category_filter, 1)

        self.stock_filter = QComboBox()
        self.stock_filter.addItem("همه وضعیت‌ها")
        self.stock_filter.addItem("موجود (کافی)")
        self.stock_filter.addItem("کسری موجودی")
        self.stock_filter.addItem("ناموجود (صفر)")
        self.stock_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.stock_filter, 1)

        self.reset_filter_btn = QPushButton("پاکسازی فیلترها")
        self.reset_filter_btn.setObjectName("secondaryBtn")
        self.reset_filter_btn.setToolTip("پاک کردن فیلترها و جستجو (Escape)")
        self.reset_filter_btn.clicked.connect(self._reset_filters)
        filter_layout.addWidget(self.reset_filter_btn)

        main_layout.addWidget(filter_card)

        # 4. Components table
        self.table = InventoryTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "نام قطعه", "پارت‌نامبر / مقدار", "پکیج / فوت‌پرینت",
            "دسته‌بندی", "کشوها", "موجودی", "وضعیت", "عملیات سریع"
        ])
        self.table.setColumnHidden(0, True)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.rowExpandRequested.connect(self._toggle_row_expansion)
        self.table.rowDeselectRequested.connect(self._collapse_all_rows)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(5, 150)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(8, 150)

        main_layout.addWidget(self.table)

        # 5. Smart status bar
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)

        self.status_state_lbl = QLabel("● آماده به کار")
        self.status_state_lbl.setObjectName("statusBarState")
        self.status_state_lbl.setStyleSheet(
            "color: #34d399; font-weight: 600; font-size: 11px; margin-right: 10px; margin-left: 12px;"
        )
        status_bar.addWidget(self.status_state_lbl)

        self.shortcuts_guide_lbl = QLabel("[ / جستجو ]    [ Enter انتخاب / بازکردن ]    [ Ctrl+N قطعه جدید ]    [ + / - موجودی ]    [ Esc لغو ]")
        self.shortcuts_guide_lbl.setObjectName("statusBarShortcuts")
        self.shortcuts_guide_lbl.setStyleSheet(
            "color: #64748b; font-size: 11px; margin-left: 12px; margin-right: 10px;"
        )
        status_bar.addPermanentWidget(self.shortcuts_guide_lbl)

    def _setup_more_menu(self):
        more_menu = QMenu(self)

        act_cats = more_menu.addAction("⚙️ مدیریت دسته‌بندی‌ها و پکیج‌ها...")
        act_cats.triggered.connect(self._open_category_settings)

        more_menu.addSeparator()

        act_backup_std = more_menu.addAction("💾 ایجاد پشتیبان استاندارد (قطعات و انبار)...")
        act_backup_std.triggered.connect(lambda: self._backup_db(advanced=False))

        act_backup_adv = more_menu.addAction("🔒 ایجاد پشتیبان پیشرفته (جامع با تنظیمات)...")
        act_backup_adv.triggered.connect(lambda: self._backup_db(advanced=True))

        act_restore = more_menu.addAction("📥 بازیابی اطلاعات از فایل پشتیبان...")
        act_restore.triggered.connect(self._restore_backup)

        more_menu.addSeparator()

        act_excel = more_menu.addAction("📊 خروجی استاندارد اکسل (Excel)...")
        act_excel.triggered.connect(self._export_excel)

        act_csv = more_menu.addAction("📑 خروجی فایل متنی (CSV)...")
        act_csv.triggered.connect(self._export_csv)

        self.more_btn.setMenu(more_menu)

    def _populate_category_filter(self):
        curr = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("همه دسته‌ها")
        categories = self.db.get_categories()
        for cat in categories:
            if cat != "—":
                self.category_filter.addItem(cat)
        
        idx = self.category_filter.findText(curr)
        if idx >= 0:
            self.category_filter.setCurrentIndex(idx)
        else:
            self.category_filter.setCurrentIndex(0)
        self.category_filter.blockSignals(False)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._open_add_dialog)
        QShortcut(QKeySequence("Ctrl+D"), self, self._open_drawer_view)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_input.setFocus())
        QShortcut(QKeySequence("/"), self, lambda: (self.search_input.setFocus(), self.search_input.selectAll()))
        QShortcut(QKeySequence("Escape"), self, self._reset_filters)
        QShortcut(QKeySequence("+"), self, self._quick_increment_selected)
        QShortcut(QKeySequence("="), self, self._quick_increment_selected)
        QShortcut(QKeySequence("-"), self, self._quick_decrement_selected)

    def refresh_data(self):
        query = self.search_input.text().strip()
        category = self.category_filter.currentText()
        stock_text = self.stock_filter.currentText()

        stock_map = {
            "همه وضعیت‌ها": "ALL",
            "موجود (کافی)": "IN_STOCK",
            "کسری موجودی": "LOW_STOCK",
            "ناموجود (صفر)": "EMPTY"
        }
        stock_filter = stock_map.get(stock_text, "ALL")

        self.current_components = self.db.search_components(
            query=query,
            category=category,
            stock_filter=stock_filter
        )

        self._populate_table(self.current_components)
        self._update_stats()

    def _populate_table(self, components):
        self.drawer_widgets.clear()
        self.expanded_rows.clear()
        self.table.setRowCount(0)
        self.table.setRowCount(len(components))

        mono_font = QFont("Consolas", 10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setBold(True)

        for row, comp in enumerate(components):
            self.table.setRowHeight(row, 46)

            # 0: ID
            self.table.setItem(row, 0, QTableWidgetItem(str(comp.id)))

            # 1: Component name (Center-aligned)
            name_item = QTableWidgetItem(comp.name)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, name_item)

            # 2: Part number / Value
            val_item = QTableWidgetItem(comp.value)
            val_item.setFont(mono_font)
            val_item.setForeground(QColor("#ffffff"))
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, val_item)

            # 3: Package / Footprint
            pkg_item = QTableWidgetItem(comp.package or "—")
            pkg_item.setFont(QFont("Consolas", 9))
            pkg_item.setForeground(QColor("#94a3b8"))
            pkg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, pkg_item)

            # 4: Category
            cat_item = QTableWidgetItem(comp.category)
            cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            cat_item.setForeground(QColor("#cbd5e1"))
            self.table.setItem(row, 4, cat_item)

            # 5: Drawers
            drawer_widget = DrawerChipsWidget(
                component=comp,
                on_click_filter=self._filter_by_drawer,
                on_toggle_expand=lambda r=row: self._toggle_row_expansion(r)
            )
            self.table.setCellWidget(row, 5, drawer_widget)
            self.drawer_widgets[row] = (drawer_widget, len(comp.drawer_list))

            # 6: Total quantity
            qty_item = QTableWidgetItem(f"{comp.quantity:,}")
            qty_item.setFont(mono_font)
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, qty_item)

            # 7: Stock status
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if comp.stock_status == "OK":
                status_item.setText("کافی")
                status_item.setForeground(QColor("#34d399"))
            elif comp.stock_status == "LOW":
                status_item.setText("کسری")
                status_item.setForeground(QColor("#fbbf24"))
            else:
                status_item.setText("ناموجود")
                status_item.setForeground(QColor("#f87171"))
            self.table.setItem(row, 7, status_item)

            # 8: Quick action buttons
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)
            act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_plus = QPushButton("+")
            btn_plus.setProperty("class", "ghostActionBtn ghostActionBtnPlus")
            btn_plus.setToolTip("افزایش موجودی (+1)")
            btn_plus.clicked.connect(lambda _, c=comp, b=btn_plus: self._quick_increment_component(c, b))
            act_layout.addWidget(btn_plus)

            btn_minus = QPushButton("−")
            btn_minus.setProperty("class", "ghostActionBtn ghostActionBtnMinus")
            btn_minus.setToolTip("کاهش موجودی (−1)")
            btn_minus.clicked.connect(lambda _, c=comp, b=btn_minus: self._quick_decrement_component(c, b))
            act_layout.addWidget(btn_minus)

            btn_stock = QPushButton("⇄")
            btn_stock.setProperty("class", "ghostActionBtn ghostActionBtnStock")
            btn_stock.setToolTip("کسر / افزایش کلی موجودی با تفکیک کشوها...")
            btn_stock.clicked.connect(lambda _, c=comp: self._open_bulk_stock_dialog(c))
            act_layout.addWidget(btn_stock)

            btn_edit = QPushButton("✎")
            btn_edit.setProperty("class", "ghostActionBtn ghostActionBtnEdit")
            btn_edit.setToolTip("ویرایش مشخصات قطعه")
            btn_edit.clicked.connect(lambda _, c=comp: self._open_edit_dialog(c))
            act_layout.addWidget(btn_edit)

            btn_del = QPushButton("✕")
            btn_del.setProperty("class", "ghostActionBtn ghostActionBtnDelete")
            btn_del.setToolTip("حذف قطعه از انبار")
            btn_del.clicked.connect(lambda _, c=comp: self._delete_component(c))
            act_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 8, act_widget)

    def _filter_by_drawer(self, drawer_num: int):
        self.search_input.setText(f"{drawer_num}")

    def _update_stats(self):
        stats = self.db.get_statistics()
        self.stat_types_pill.setText(f"قطعات: {stats['total_types']:,} قلم")
        self.stat_items_pill.setText(f"موجودی کل: {stats['total_items']:,} عدد")
        self.stat_drawers_pill.setText(f"کشوهای فعال: {stats['total_drawers']:,}")
        self.stat_instock_pill.setText(f"موجودی کافی: {stats['in_stock_count']:,}")
        self.stat_low_pill.setText(f"کسری انبار: {stats['low_stock_count']:,}")
        self.stat_empty_pill.setText(f"ناموجود: {stats['empty_count']:,}")

    def _on_filter_changed(self):
        text = self.search_input.text().strip()
        auto_detect_text_direction(self.search_input, text)
        self.refresh_data()

    def _on_enter_pressed(self):
        if self.current_components:
            self.table.selectRow(0)
            self._toggle_row_expansion(0)

    def _reset_filters(self):
        self.table.clearSelection()
        self._collapse_all_rows()
        self.search_input.clear()
        self.category_filter.setCurrentIndex(0)
        self.stock_filter.setCurrentIndex(0)
        self.refresh_data()

    def _get_selected_component(self) -> Optional[Component]:
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        id_item = self.table.item(row, 0)
        if id_item:
            comp_id = int(id_item.text())
            return self.db.get_component(comp_id)
        return None

    def _toggle_row_expansion(self, row: int):
        if row not in self.drawer_widgets:
            return

        widget, drawer_count = self.drawer_widgets[row]
        if drawer_count <= 3:
            return

        if row in self.expanded_rows:
            self.expanded_rows.remove(row)
            widget.rebuild(expanded=False)
            self.table.setRowHeight(row, 46)
        else:
            self.expanded_rows.add(row)
            widget.rebuild(expanded=True)
            chunks_count = (drawer_count + 2) // 3
            self.table.setRowHeight(row, 46 + (chunks_count - 1) * 26)

    def _collapse_all_rows(self):
        for row in list(self.expanded_rows):
            if row in self.drawer_widgets:
                widget, _ = self.drawer_widgets[row]
                widget.rebuild(expanded=False)
                self.table.setRowHeight(row, 46)
        self.expanded_rows.clear()

    def _on_row_double_clicked(self, item):
        comp = self._get_selected_component()
        if comp:
            self._open_edit_dialog(comp)

    # ================= Quick Increment / Decrement Logic =================

    def _quick_increment_selected(self):
        comp = self._get_selected_component()
        if comp:
            self._quick_increment_component(comp)

    def _quick_decrement_selected(self):
        comp = self._get_selected_component()
        if comp:
            self._quick_decrement_component(comp)

    def _quick_increment_component(self, comp: Component, trigger_btn: QWidget = None):
        """Increment stock by +1: direct adjust for single-drawer or open drawer picker for multi-drawer."""
        drawers = comp.drawer_list
        if len(drawers) <= 1:
            d_num = drawers[0] if drawers else 1
            self._do_single_drawer_adjust(comp, d_num, 1)
            return

        # Open target drawer selection popup menu
        menu = QMenu(self)
        title_act = menu.addAction(f"افزایش ۱+ عدد «{comp.value}» در کدام کشو؟")
        title_act.setEnabled(False)
        menu.addSeparator()

        for d in drawers:
            cur_qty = comp.get_drawer_qty(d)
            act = menu.addAction(f"کشو شماره {d} (موجودی فعلی: {cur_qty:,} عدد)")
            act.triggered.connect(lambda _, d_num=d: self._do_single_drawer_adjust(comp, d_num, 1))

        pos = trigger_btn.mapToGlobal(QPoint(0, trigger_btn.height())) if trigger_btn else self.cursor().pos()
        menu.exec(pos)

    def _quick_decrement_component(self, comp: Component, trigger_btn: QWidget = None):
        """Decrement stock by -1: direct adjust for single-drawer or open drawer picker with empty drawers disabled."""
        if comp.quantity <= 0:
            self.show_status_message(f"قطعه «{comp.value}» ناموجود است و قابل کسر نیست", color="#f87171")
            return

        drawers = comp.drawer_list
        if len(drawers) <= 1:
            d_num = drawers[0] if drawers else 1
            self._do_single_drawer_adjust(comp, d_num, -1)
            return

        # Open target drawer selection popup menu
        menu = QMenu(self)
        title_act = menu.addAction(f"کاهش ۱− عدد «{comp.value}» از کدام کشو؟")
        title_act.setEnabled(False)
        menu.addSeparator()

        for d in drawers:
            cur_qty = comp.get_drawer_qty(d)
            is_empty = (cur_qty == 0)
            text = f"کشو شماره {d} (موجودی: {cur_qty:,} عدد)" if not is_empty else f"کشو شماره {d} (خالی / ۰ عدد)"
            act = menu.addAction(text)
            if is_empty:
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda _, d_num=d: self._do_single_drawer_adjust(comp, d_num, -1))

        pos = trigger_btn.mapToGlobal(QPoint(0, trigger_btn.height())) if trigger_btn else self.cursor().pos()
        menu.exec(pos)

    def _do_single_drawer_adjust(self, comp: Component, drawer_num: int, delta: int):
        new_total = self.db.adjust_single_drawer_stock(comp.id, drawer_num, delta)
        if new_total is None:
            self.show_status_message(f"خطا در تغییر موجودی کشو {drawer_num}", color="#f87171")
            return

        self.refresh_data()
        updated_comp = self.db.get_component(comp.id)
        new_drawer_qty = updated_comp.get_drawer_qty(drawer_num) if updated_comp else 0

        if delta > 0:
            self.show_status_message(
                f"موجودی کشو {drawer_num} قطعه «{comp.value}» ۱+ افزایش یافت (موجودی کشو: {new_drawer_qty:,} | کل: {new_total:,})",
                color="#34d399"
            )
        else:
            self.show_status_message(
                f"موجودی کشو {drawer_num} قطعه «{comp.value}» ۱− کاهش یافت (موجودی کشو: {new_drawer_qty:,} | کل: {new_total:,})",
                color="#fbbf24"
            )

    # ================= Dialogs =================

    def _open_bulk_stock_dialog(self, comp: Component):
        dlg = BulkStockDialog(self, component=comp)
        if dlg.exec() == BulkStockDialog.DialogCode.Accepted:
            is_deduct, total_amount, breakdown = dlg.get_result()
            new_total = self.db.adjust_drawer_stocks(comp.id, breakdown, is_deduct)
            if new_total is not None:
                self.refresh_data()
                op_word = "کسر" if is_deduct else "افزایش"
                color = "#fbbf24" if is_deduct else "#34d399"
                self.show_status_message(
                    f"تعداد {total_amount:,} عدد با موفقیت {op_word} شد (موجودی فعلی کل: {new_total:,} عدد)",
                    color=color
                )

    def _open_add_dialog(self):
        dlg = ComponentDialog(self, db=self.db)
        if dlg.exec() == ComponentDialog.DialogCode.Accepted:
            new_comp = dlg.get_component_data()
            comp_id = self.db.add_component(new_comp)
            self.refresh_data()
            self.show_status_message(f"قطعه «{new_comp.value}» با موفقیت ثبت شد", color="#34d399")

    def _open_edit_dialog(self, comp: Component):
        dlg = ComponentDialog(self, component=comp, db=self.db)
        if dlg.exec() == ComponentDialog.DialogCode.Accepted:
            updated_comp = dlg.get_component_data()
            self.db.update_component(updated_comp)
            self.refresh_data()
            self.show_status_message(f"مشخصات قطعه «{updated_comp.value}» به‌روزرسانی شد")

    def _open_drawer_view(self):
        dlg = DrawerViewDialog(self, db=self.db)
        dlg.exec()
        self.refresh_data()

    def _open_category_settings(self):
        dlg = CategorySettingsDialog(self, db=self.db)
        if dlg.exec() == CategorySettingsDialog.DialogCode.Accepted:
            self._populate_category_filter()
            self.refresh_data()
            self.show_status_message("تنظیمات دسته‌بندی‌ها و پکیج‌ها با موفقیت اعمال شد", color="#34d399")

    def _delete_component(self, comp: Component):
        confirmed = ask_persian_confirmation(
            self, "تایید حذف قطعه",
            f"آیا از حذف قطعه «{comp.value}» ({comp.name}) از انبار اطمینان دارید؟"
        )
        if confirmed:
            self.db.delete_component(comp.id)
            self.refresh_data()
            self.show_status_message(f"قطعه «{comp.value}» حذف شد", color="#f87171")

    def _show_context_menu(self, pos):
        comp = self._get_selected_component()
        if not comp:
            return

        menu = QMenu(self)

        act_inc = menu.addAction("افزایش موجودی (+1)...")
        act_inc.triggered.connect(lambda: self._quick_increment_component(comp))

        act_dec = menu.addAction("کاهش موجودی (−1)...")
        act_dec.triggered.connect(lambda: self._quick_decrement_component(comp))

        act_stock = menu.addAction("کسر / افزایش کلی موجودی...")
        act_stock.triggered.connect(lambda: self._open_bulk_stock_dialog(comp))

        menu.addSeparator()

        act_copy = menu.addAction("کپی مقدار / پارت‌نامبر")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(comp.value))

        if comp.drawer_list:
            act_same_drawer = menu.addAction(f"مشاهده تمام قطعات کشو {comp.drawer_list[0]}")
            act_same_drawer.triggered.connect(lambda: self._filter_by_drawer(comp.drawer_list[0]))

        menu.addSeparator()

        act_edit = menu.addAction("ویرایش مشخصات قطعه")
        act_edit.triggered.connect(lambda: self._open_edit_dialog(comp))

        act_del = menu.addAction("حذف قطعه از انبار")
        act_del.triggered.connect(lambda: self._delete_component(comp))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _export_excel(self):
        components = self.db.get_all_components()
        if not components:
            QMessageBox.information(self, "گزارش اکسل", "هیچ قطعه‌ای برای خروجی وجود ندارد.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره خروجی اکسل", "Electronic_Inventory.xlsx", "Excel Files (*.xlsx)"
        )
        if file_path:
            out = export_to_excel(components, file_path)
            QMessageBox.information(self, "خروجی موفق", f"فایل اکسل با موفقیت ذخیره شد:\n{out}")

    def _export_csv(self):
        components = self.db.get_all_components()
        if not components:
            QMessageBox.information(self, "گزارش CSV", "هیچ قطعه‌ای برای خروجی وجود ندارد.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره خروجی CSV", "Electronic_Inventory.csv", "CSV Files (*.csv)"
        )
        if file_path:
            out = export_to_csv(components, file_path)
            QMessageBox.information(self, "خروجی موفق", f"فایل CSV با موفقیت ذخیره شد:\n{out}")

    def _backup_db(self, advanced: bool = False):
        mode_tag = "advanced" if advanced else "standard"
        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"omnix_backup_{mode_tag}_{now_tag}.omnixbak"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "ذخیره فایل پشتیبان پیشرفته" if advanced else "ذخیره فایل پشتیبان عادی",
            default_name,
            "Omnix Backup (*.omnixbak *.elecbak);;JSON Backup (*.json)"
        )
        if file_path:
            success, msg = BackupManager.create_backup(self.db, file_path, is_advanced=advanced)
            if success:
                QMessageBox.information(self, "پشتیبان‌گیری موفق", msg)
                self.show_status_message("فایل پشتیبان با موفقیت ایجاد گردید", color="#34d399")
            else:
                QMessageBox.critical(self, "خطا در پشتیبان‌گیری", msg)

    def _restore_backup(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب و بارگذاری فایل پشتیبان Omnix",
            "",
            "Omnix Backup (*.omnixbak *.elecbak *.json);;All Files (*.*)"
        )
        if not file_path:
            return

        is_valid, reason, info = BackupManager.verify_backup_file(file_path)
        if not is_valid or not info:
            QMessageBox.critical(self, "خطای اعتبارسنجی فایل پشتیبان", reason)
            return

        confirm_msg = (
            f"مشخصات فایل پشتیبان تاییدشده:\n\n"
            f"• نوع پشتیبان: {info['backup_type']}\n"
            f"• تاریخ تهیه فایل: {info['created_at']}\n"
            f"• تعداد قطعات: {info['total_components']:,} قلم\n\n"
            f"⚠️ هشدار: با بازیابی این فایل، داده‌های فعلی انبار با اطلاعات این فایل جایگزین خواهند شد.\n\n"
            f"آیا از بارگذاری و بازیابی این فایل پشتیبان اطمینان کامل دارید؟"
        )

        confirmed = ask_persian_confirmation(self, "تایید بازیابی فایل پشتیبان", confirm_msg)
        if confirmed:
            success, res_msg = BackupManager.restore_backup(self.db, file_path)
            if success:
                self._populate_category_filter()
                self.refresh_data()
                QMessageBox.information(self, "بازیابی موفقیت‌آمیز", res_msg)
                self.show_status_message("اطلاعات انبار با موفقیت بازیابی شد", color="#34d399")
            else:
                QMessageBox.critical(self, "خطا در بازیابی", res_msg)

    def show_status_message(self, message: str, color: str = "#94a3b8", timeout_ms: int = 4000):
        self.status_state_lbl.setText(f"● {message}")
        self.status_state_lbl.setStyleSheet(
            f"color: {color}; font-weight: 600; font-size: 11px; margin-right: 10px; margin-left: 12px;"
        )
        QTimer.singleShot(timeout_ms, self._reset_status_state)

    def _reset_status_state(self):
        self.status_state_lbl.setText("● آماده به کار")
        self.status_state_lbl.setStyleSheet(
            "color: #34d399; font-weight: 600; font-size: 11px; margin-right: 10px; margin-left: 12px;"
        )
