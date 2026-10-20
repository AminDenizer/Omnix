"""
Omnix UI — Dedicated Reference Data Management Widget
Governing Document: Phase 2.3 Reference Data Architecture

Dedicated management interface for canonical reference entities:
- Manufacturers / Brands
- Categories
- Types / Technologies (associated with Category)
Keeps the component registration form uncluttered and provides centralized
governance of inventory classifications with full CRUD and data integrity.
"""

from typing import Optional, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QMessageBox,
    QInputDialog,
    QSplitter,
    QMenu,
)

from core.inventory.models import (
    ManufacturerRecord,
    CategoryRecord,
    TypeRecord,
    clean_display_string,
    ReferenceDataInUseError,
    DuplicateReferenceError,
    ValidationError,
)
from core.inventory.repository import SqliteInventoryRepository


class ReferenceDataWidget(QWidget):
    """
    Dedicated view for inspecting, searching, and managing canonical reference data:
    Manufacturers, Categories, and Type/Technologies.
    Supports complete CRUD (Add, Edit, Delete, Deactivate/Activate) with data integrity.
    """
    referenceDataChanged = pyqtSignal()

    def __init__(self, repository: Optional[SqliteInventoryRepository] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repository = repository
        self._selected_category_id: Optional[int] = None
        self._selected_category_name: Optional[str] = None
        self._setup_ui()

    def set_repository(self, repository: SqliteInventoryRepository):
        self.repository = repository
        self.refresh()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header Info Banner
        hdr_layout = QHBoxLayout()
        title_lbl = QLabel("Canonical Reference Data Management")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self.summary_lbl = QLabel("0 manufacturers | 0 categories | 0 types")
        self.summary_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(self.summary_lbl)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(26)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        refresh_btn.clicked.connect(self.refresh)
        hdr_layout.addWidget(refresh_btn)
        main_layout.addLayout(hdr_layout)

        # 3-Column Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1e293b;
                width: 2px;
            }
        """)

        # Column 1: Manufacturers
        mfr_panel = self._create_panel(
            title="1. Manufacturers",
            search_placeholder="Search manufacturers...",
            add_btn_text="Add",
            on_add=self._on_add_manufacturer,
            on_edit=self._on_edit_manufacturer,
            on_delete=self._on_delete_manufacturer,
            on_search=self._on_mfr_search_changed,
            on_context_menu=self._on_mfr_context_menu,
        )
        self.mfr_list: QListWidget = mfr_panel["list"]
        self.mfr_search: QLineEdit = mfr_panel["search"]
        self.mfr_count_lbl: QLabel = mfr_panel["count_lbl"]
        self.mfr_add_btn: QPushButton = mfr_panel["add_btn"]
        self.mfr_edit_btn: QPushButton = mfr_panel["edit_btn"]
        self.mfr_del_btn: QPushButton = mfr_panel["del_btn"]
        splitter.addWidget(mfr_panel["widget"])

        # Column 2: Categories
        cat_panel = self._create_panel(
            title="2. Categories",
            search_placeholder="Search categories...",
            add_btn_text="Add",
            on_add=self._on_add_category,
            on_edit=self._on_edit_category,
            on_delete=self._on_delete_category,
            on_search=self._on_cat_search_changed,
            on_context_menu=self._on_cat_context_menu,
        )
        self.cat_list: QListWidget = cat_panel["list"]
        self.cat_search: QLineEdit = cat_panel["search"]
        self.cat_count_lbl: QLabel = cat_panel["count_lbl"]
        self.cat_add_btn: QPushButton = cat_panel["add_btn"]
        self.cat_edit_btn: QPushButton = cat_panel["edit_btn"]
        self.cat_del_btn: QPushButton = cat_panel["del_btn"]
        self.cat_list.itemSelectionChanged.connect(self._on_category_selected)
        splitter.addWidget(cat_panel["widget"])

        # Column 3: Types / Technologies (associated with Category)
        type_panel = self._create_panel(
            title="3. Types / Technologies",
            search_placeholder="Search types for category...",
            add_btn_text="Add",
            on_add=self._on_add_type,
            on_edit=self._on_edit_type,
            on_delete=self._on_delete_type,
            on_search=self._on_type_search_changed,
            on_context_menu=self._on_type_context_menu,
        )
        self.type_list: QListWidget = type_panel["list"]
        self.type_search: QLineEdit = type_panel["search"]
        self.type_count_lbl: QLabel = type_panel["count_lbl"]
        self.type_add_btn: QPushButton = type_panel["add_btn"]
        self.type_edit_btn: QPushButton = type_panel["edit_btn"]
        self.type_del_btn: QPushButton = type_panel["del_btn"]
        self.type_add_btn.setEnabled(False)
        self.type_list.itemSelectionChanged.connect(self._on_type_selection_changed)
        splitter.addWidget(type_panel["widget"])

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        main_layout.addWidget(splitter, 1)

    def _create_panel(
        self,
        title: str,
        search_placeholder: str,
        add_btn_text: str,
        on_add,
        on_edit,
        on_delete,
        on_search,
        on_context_menu,
    ) -> dict:
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        hdr_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #f8fafc;")
        count_lbl = QLabel("0 records")
        count_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch()
        hdr_row.addWidget(count_lbl)
        layout.addLayout(hdr_row)

        search_input = QLineEdit()
        search_input.setPlaceholderText(search_placeholder)
        search_input.setFixedHeight(28)
        search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        search_input.textChanged.connect(on_search)
        layout.addWidget(search_input)

        item_list = QListWidget()
        item_list.setStyleSheet("""
            QListWidget {
                background-color: #0b101b;
                border: 1px solid #1e293b;
                border-radius: 4px;
                color: #f8fafc;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #1e293b;
            }
            QListWidget::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QListWidget::item:hover:!selected {
                background-color: #1e293b;
            }
        """)
        item_list.itemDoubleClicked.connect(on_edit)
        item_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        item_list.customContextMenuRequested.connect(on_context_menu)
        layout.addWidget(item_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        add_btn = QPushButton(add_btn_text)
        add_btn.setFixedHeight(28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
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
        add_btn.clicked.connect(on_add)
        btn_row.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(28)
        edit_btn.setEnabled(False)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 4px;
                border: 1px solid #475569;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #334155;
            }
        """)
        edit_btn.clicked.connect(on_edit)
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(28)
        del_btn.setEnabled(False)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #f87171;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
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
                border-color: #334155;
            }
        """)
        del_btn.clicked.connect(on_delete)
        btn_row.addWidget(del_btn)

        # Wire selection changed to enable/disable edit and delete buttons
        def _update_button_states():
            has_selection = len(item_list.selectedItems()) > 0
            edit_btn.setEnabled(has_selection)
            del_btn.setEnabled(has_selection)

        item_list.itemSelectionChanged.connect(_update_button_states)

        layout.addLayout(btn_row)

        return {
            "widget": panel,
            "list": item_list,
            "search": search_input,
            "count_lbl": count_lbl,
            "add_btn": add_btn,
            "edit_btn": edit_btn,
            "del_btn": del_btn,
        }

    def refresh(self):
        if not self.repository or not isinstance(self.repository, SqliteInventoryRepository):
            return
        self._refresh_manufacturers()
        self._refresh_categories()
        self._refresh_types()
        self._update_summary()

    def _update_summary(self):
        if not self.repository:
            return
        mfrs = self.repository.get_all_manufacturers(include_inactive=True)
        cats = self.repository.get_all_categories(include_inactive=True)
        total_types = 0
        for c in cats:
            total_types += len(self.repository.get_types_for_category(c.id, include_inactive=True))
        self.summary_lbl.setText(f"{len(mfrs)} manufacturers | {len(cats)} categories | {total_types} types")

    def _refresh_manufacturers(self):
        if not self.repository:
            return
        query = self.mfr_search.text().strip().upper()
        mfrs = self.repository.get_all_manufacturers(include_inactive=True)
        self.mfr_list.clear()
        count = 0
        for m in sorted(mfrs, key=lambda x: x.name.lower()):
            if query and query not in m.name.upper():
                continue
            item = QListWidgetItem(m.name)
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            if not m.is_active:
                item.setForeground(QColor("#64748b"))
                item.setText(f"{m.name} (inactive)")
            self.mfr_list.addItem(item)
            count += 1
        self.mfr_count_lbl.setText(f"{count} records")
        self.mfr_edit_btn.setEnabled(False)
        self.mfr_del_btn.setEnabled(False)

    def _refresh_categories(self):
        if not self.repository:
            return
        query = self.cat_search.text().strip().upper()
        cats = self.repository.get_all_categories(include_inactive=True)
        self.cat_list.clear()
        count = 0
        selected_row = -1
        for idx, c in enumerate(sorted(cats, key=lambda x: x.name.lower())):
            if query and query not in c.name.upper():
                continue
            item = QListWidgetItem(c.name)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            if not c.is_active:
                item.setForeground(QColor("#64748b"))
                item.setText(f"{c.name} (inactive)")
            self.cat_list.addItem(item)
            if self._selected_category_id == c.id:
                selected_row = self.cat_list.count() - 1
            count += 1
        self.cat_count_lbl.setText(f"{count} records")
        if selected_row >= 0:
            self.cat_list.setCurrentRow(selected_row)
        elif self.cat_list.count() > 0 and self._selected_category_id is None:
            self.cat_list.setCurrentRow(0)
        else:
            self.cat_edit_btn.setEnabled(False)
            self.cat_del_btn.setEnabled(False)

    def _refresh_types(self):
        if not self.repository or self._selected_category_id is None:
            self.type_list.clear()
            self.type_count_lbl.setText("0 records")
            self.type_add_btn.setEnabled(False)
            self.type_edit_btn.setEnabled(False)
            self.type_del_btn.setEnabled(False)
            return

        self.type_add_btn.setEnabled(True)
        query = self.type_search.text().strip().upper()
        types = self.repository.get_types_for_category(self._selected_category_id, include_inactive=True)
        self.type_list.clear()
        count = 0
        for t in sorted(types, key=lambda x: x.name.lower()):
            if query and query not in t.name.upper():
                continue
            item = QListWidgetItem(t.name)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            if not t.is_active:
                item.setForeground(QColor("#64748b"))
                item.setText(f"{t.name} (inactive)")
            self.type_list.addItem(item)
            count += 1
        cat_name = self._selected_category_name or "Category"
        self.type_count_lbl.setText(f"{count} types for '{cat_name}'")
        self.type_edit_btn.setEnabled(False)
        self.type_del_btn.setEnabled(False)

    def _on_mfr_search_changed(self):
        self._refresh_manufacturers()

    def _on_cat_search_changed(self):
        self._refresh_categories()

    def _on_type_search_changed(self):
        self._refresh_types()

    def _on_category_selected(self):
        items = self.cat_list.selectedItems()
        if not items:
            self._selected_category_id = None
            self._selected_category_name = None
            self.cat_edit_btn.setEnabled(False)
            self.cat_del_btn.setEnabled(False)
        else:
            self._selected_category_id = items[0].data(Qt.ItemDataRole.UserRole)
            self._selected_category_name = items[0].text().replace(" (inactive)", "")
            self.cat_edit_btn.setEnabled(True)
            self.cat_del_btn.setEnabled(True)
        self._refresh_types()

    def _on_type_selection_changed(self):
        has_sel = len(self.type_list.selectedItems()) > 0
        self.type_edit_btn.setEnabled(has_sel)
        self.type_del_btn.setEnabled(has_sel)

    # -------------------------------------------------------------------------
    # Manufacturer CRUD Operations
    # -------------------------------------------------------------------------
    def _on_add_manufacturer(self):
        if not self.repository:
            return
        name, ok = QInputDialog.getText(self, "Add Manufacturer", "Manufacturer Name:")
        if ok and name.strip():
            clean_name = clean_display_string(name)
            try:
                self.repository.add_manufacturer(clean_name)
                self._refresh_manufacturers()
                self._update_summary()
                self.referenceDataChanged.emit()
            except Exception as e:
                QMessageBox.warning(self, "Add Manufacturer Failed", f"Could not add manufacturer '{clean_name}': {e}")

    def _on_edit_manufacturer(self):
        if not self.repository:
            return
        items = self.mfr_list.selectedItems()
        if not items:
            return
        mfr_id = items[0].data(Qt.ItemDataRole.UserRole)
        mfr = self.repository.get_manufacturer(mfr_id)
        if not mfr:
            return
        new_name, ok = QInputDialog.getText(self, "Edit Manufacturer", "Manufacturer Name:", text=mfr.name)
        if ok and new_name.strip() and new_name.strip() != mfr.name:
            clean_name = clean_display_string(new_name)
            try:
                self.repository.update_manufacturer(mfr_id, name=clean_name)
                self.repository.reconcile_canonical_classifications()
                self._refresh_manufacturers()
                self._update_summary()
                self.referenceDataChanged.emit()
            except DuplicateReferenceError as e:
                QMessageBox.warning(self, "Duplicate Manufacturer", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Edit Manufacturer Failed", str(e))

    def _on_delete_manufacturer(self):
        if not self.repository:
            return
        items = self.mfr_list.selectedItems()
        if not items:
            return
        mfr_id = items[0].data(Qt.ItemDataRole.UserRole)
        mfr = self.repository.get_manufacturer(mfr_id)
        if not mfr:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Manufacturer",
            f"Are you sure you want to delete manufacturer '{mfr.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.repository.delete_manufacturer(mfr_id)
                self._refresh_manufacturers()
                self._update_summary()
                self.referenceDataChanged.emit()
            except ReferenceDataInUseError as e:
                QMessageBox.warning(self, "Cannot Delete Manufacturer", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Delete Manufacturer Failed", str(e))

    def _on_toggle_mfr_active(self):
        if not self.repository:
            return
        items = self.mfr_list.selectedItems()
        if not items:
            return
        mfr_id = items[0].data(Qt.ItemDataRole.UserRole)
        mfr = self.repository.get_manufacturer(mfr_id)
        if not mfr:
            return
        try:
            self.repository.update_manufacturer(mfr_id, is_active=not mfr.is_active)
            self._refresh_manufacturers()
            self.referenceDataChanged.emit()
        except Exception as e:
            QMessageBox.warning(self, "Toggle Status Failed", str(e))

    def _on_mfr_context_menu(self, pos):
        items = self.mfr_list.selectedItems()
        if not items:
            return
        mfr_id = items[0].data(Qt.ItemDataRole.UserRole)
        mfr = self.repository.get_manufacturer(mfr_id) if self.repository else None
        if not mfr:
            return
        menu = QMenu(self)
        edit_act = menu.addAction("Edit Name...")
        edit_act.triggered.connect(self._on_edit_manufacturer)
        status_text = "Set Inactive" if mfr.is_active else "Set Active"
        toggle_act = menu.addAction(status_text)
        toggle_act.triggered.connect(self._on_toggle_mfr_active)
        menu.addSeparator()
        del_act = menu.addAction("Delete Manufacturer")
        del_act.triggered.connect(self._on_delete_manufacturer)
        menu.exec(self.mfr_list.mapToGlobal(pos))

    # -------------------------------------------------------------------------
    # Category CRUD Operations
    # -------------------------------------------------------------------------
    def _on_add_category(self):
        if not self.repository:
            return
        name, ok = QInputDialog.getText(self, "Add Category", "Category Name:")
        if ok and name.strip():
            clean_name = clean_display_string(name)
            try:
                cat_id = self.repository.add_category(clean_name)
                self._selected_category_id = cat_id
                self._selected_category_name = clean_name
                self._refresh_categories()
                self._update_summary()
                self.referenceDataChanged.emit()
            except Exception as e:
                QMessageBox.warning(self, "Add Category Failed", f"Could not add category '{clean_name}': {e}")

    def _on_edit_category(self):
        if not self.repository:
            return
        items = self.cat_list.selectedItems()
        if not items:
            return
        cat_id = items[0].data(Qt.ItemDataRole.UserRole)
        cat = self.repository.get_category(cat_id)
        if not cat:
            return
        new_name, ok = QInputDialog.getText(self, "Edit Category", "Category Name:", text=cat.name)
        if ok and new_name.strip() and new_name.strip() != cat.name:
            clean_name = clean_display_string(new_name)
            try:
                self.repository.update_category(cat_id, name=clean_name)
                self.repository.reconcile_canonical_classifications()
                self._selected_category_name = clean_name
                self._refresh_categories()
                self._update_summary()
                self.referenceDataChanged.emit()
            except DuplicateReferenceError as e:
                QMessageBox.warning(self, "Duplicate Category", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Edit Category Failed", str(e))

    def _on_delete_category(self):
        if not self.repository:
            return
        items = self.cat_list.selectedItems()
        if not items:
            return
        cat_id = items[0].data(Qt.ItemDataRole.UserRole)
        cat = self.repository.get_category(cat_id)
        if not cat:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Category",
            f"Are you sure you want to delete category '{cat.name}'?\n(Categories in use or containing types cannot be deleted).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.repository.delete_category(cat_id)
                self._selected_category_id = None
                self._selected_category_name = None
                self._refresh_categories()
                self._update_summary()
                self.referenceDataChanged.emit()
            except ReferenceDataInUseError as e:
                QMessageBox.warning(self, "Cannot Delete Category", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Delete Category Failed", str(e))

    def _on_toggle_cat_active(self):
        if not self.repository:
            return
        items = self.cat_list.selectedItems()
        if not items:
            return
        cat_id = items[0].data(Qt.ItemDataRole.UserRole)
        cat = self.repository.get_category(cat_id)
        if not cat:
            return
        try:
            self.repository.update_category(cat_id, is_active=not cat.is_active)
            self._refresh_categories()
            self.referenceDataChanged.emit()
        except Exception as e:
            QMessageBox.warning(self, "Toggle Status Failed", str(e))

    def _on_cat_context_menu(self, pos):
        items = self.cat_list.selectedItems()
        if not items:
            return
        cat_id = items[0].data(Qt.ItemDataRole.UserRole)
        cat = self.repository.get_category(cat_id) if self.repository else None
        if not cat:
            return
        menu = QMenu(self)
        edit_act = menu.addAction("Edit Name...")
        edit_act.triggered.connect(self._on_edit_category)
        status_text = "Set Inactive" if cat.is_active else "Set Active"
        toggle_act = menu.addAction(status_text)
        toggle_act.triggered.connect(self._on_toggle_cat_active)
        menu.addSeparator()
        del_act = menu.addAction("Delete Category")
        del_act.triggered.connect(self._on_delete_category)
        menu.exec(self.cat_list.mapToGlobal(pos))

    # -------------------------------------------------------------------------
    # Type / Technology CRUD Operations
    # -------------------------------------------------------------------------
    def _on_add_type(self):
        if not self.repository or self._selected_category_id is None:
            QMessageBox.information(self, "Select Category", "Please select a Category first to add a Type.")
            return
        cat_name = self._selected_category_name or "selected category"
        name, ok = QInputDialog.getText(self, "Add Type / Technology", f"Type / Technology for '{cat_name}':")
        if ok and name.strip():
            clean_name = clean_display_string(name)
            try:
                self.repository.add_type(self._selected_category_id, clean_name)
                self._refresh_types()
                self._update_summary()
                self.referenceDataChanged.emit()
            except Exception as e:
                QMessageBox.warning(self, "Add Type Failed", f"Could not add type '{clean_name}': {e}")

    def _on_edit_type(self):
        if not self.repository or self._selected_category_id is None:
            return
        items = self.type_list.selectedItems()
        if not items:
            return
        type_id = items[0].data(Qt.ItemDataRole.UserRole)
        t = self.repository.get_type(type_id)
        if not t:
            return
        new_name, ok = QInputDialog.getText(self, "Edit Type / Technology", "Type / Technology Name:", text=t.name)
        if ok and new_name.strip() and new_name.strip() != t.name:
            clean_name = clean_display_string(new_name)
            try:
                self.repository.update_type(type_id, name=clean_name)
                self.repository.reconcile_canonical_classifications()
                self._refresh_types()
                self._update_summary()
                self.referenceDataChanged.emit()
            except DuplicateReferenceError as e:
                QMessageBox.warning(self, "Duplicate Type", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Edit Type Failed", str(e))

    def _on_delete_type(self):
        if not self.repository or self._selected_category_id is None:
            return
        items = self.type_list.selectedItems()
        if not items:
            return
        type_id = items[0].data(Qt.ItemDataRole.UserRole)
        t = self.repository.get_type(type_id)
        if not t:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Type",
            f"Are you sure you want to delete type '{t.name}' under category '{t.category_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.repository.delete_type(type_id)
                self._refresh_types()
                self._update_summary()
                self.referenceDataChanged.emit()
            except ReferenceDataInUseError as e:
                QMessageBox.warning(self, "Cannot Delete Type", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Delete Type Failed", str(e))

    def _on_toggle_type_active(self):
        if not self.repository or self._selected_category_id is None:
            return
        items = self.type_list.selectedItems()
        if not items:
            return
        type_id = items[0].data(Qt.ItemDataRole.UserRole)
        t = self.repository.get_type(type_id)
        if not t:
            return
        try:
            self.repository.update_type(type_id, is_active=not t.is_active)
            self._refresh_types()
            self.referenceDataChanged.emit()
        except Exception as e:
            QMessageBox.warning(self, "Toggle Status Failed", str(e))

    def _on_type_context_menu(self, pos):
        items = self.type_list.selectedItems()
        if not items:
            return
        type_id = items[0].data(Qt.ItemDataRole.UserRole)
        t = self.repository.get_type(type_id) if self.repository else None
        if not t:
            return
        menu = QMenu(self)
        edit_act = menu.addAction("Edit Name...")
        edit_act.triggered.connect(self._on_edit_type)
        status_text = "Set Inactive" if t.is_active else "Set Active"
        toggle_act = menu.addAction(status_text)
        toggle_act.triggered.connect(self._on_toggle_type_active)
        menu.addSeparator()
        del_act = menu.addAction("Delete Type")
        del_act.triggered.connect(self._on_delete_type)
        menu.exec(self.type_list.mapToGlobal(pos))


class ReferenceDataDialog(QDialog):
    """Dedicated modal dialog for managing canonical reference data."""
    def __init__(self, repository: SqliteInventoryRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Canonical Reference Data Management")
        self.setMinimumSize(850, 550)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b101b;
                color: #f8fafc;
            }
        """)

        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.widget = ReferenceDataWidget(repository=repository, parent=self)
        layout.addWidget(self.widget, 1)

        self.widget.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        from ui.dark_frame import apply_dark_window_frame
        apply_dark_window_frame(self)
