import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QButtonGroup, QFrame, QListWidget, QLineEdit, QPushButton,
    QMessageBox, QListWidgetItem, QWidget, QStackedWidget
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from database import Database, DEFAULT_CATEGORIES, DEFAULT_PACKAGES
from ui.dialog_utils import ask_persian_confirmation


class CategorySettingsDialog(QDialog):
    """Configuration dialog for managing categories and packages with a modern segmented switcher."""

    def __init__(self, parent=None, db: Database = None):
        super().__init__(parent)
        self.db = db or Database()
        self.setWindowTitle("تنظیمات دسته‌بندی‌ها و پکیج‌ها")
        self.resize(540, 600)
        self.setMinimumWidth(480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self._init_ui()
        self._load_current_state()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        # Header title
        title_lbl = QLabel("مدیریت دسته‌بندی‌ها و پکیج‌های قطعات")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #38bdf8;")
        layout.addWidget(title_lbl)

        # Modern Segmented Pill Switcher
        switcher_frame = QFrame()
        switcher_frame.setObjectName("segmentedSwitcher")
        switcher_frame.setStyleSheet("""
            QFrame#segmentedSwitcher {
                background-color: #0b111e;
                border: 1.5px solid #233352;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        switcher_layout = QHBoxLayout(switcher_frame)
        switcher_layout.setContentsMargins(4, 4, 4, 4)
        switcher_layout.setSpacing(6)

        self.tab_btn_cats = QPushButton("دسته‌بندی قطعات")
        self.tab_btn_cats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_btn_cats.clicked.connect(lambda: self._set_active_tab(0))
        switcher_layout.addWidget(self.tab_btn_cats, 1)

        self.tab_btn_pkgs = QPushButton("پکیج و فوت‌پرینت‌ها")
        self.tab_btn_pkgs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_btn_pkgs.clicked.connect(lambda: self._set_active_tab(1))
        switcher_layout.addWidget(self.tab_btn_pkgs, 1)

        layout.addWidget(switcher_frame)

        # Content pages (QStackedWidget)
        self.stack = QStackedWidget()

        # Page 1: Categories
        self.cat_page = QWidget()
        self._setup_categories_page(self.cat_page)
        self.stack.addWidget(self.cat_page)

        # Page 2: Packages
        self.pkg_page = QWidget()
        self._setup_packages_page(self.pkg_page)
        self.stack.addWidget(self.pkg_page)

        layout.addWidget(self.stack)

        # Save and cancel action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        btn_save = QPushButton("ذخیره و اعمال تنظیمات")
        btn_save.setObjectName("successBtn")
        btn_save.clicked.connect(self._save_settings)
        actions_layout.addWidget(btn_save, 2)

        btn_close = QPushButton("بستن")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.reject)
        actions_layout.addWidget(btn_close, 1)

        layout.addLayout(actions_layout)

        # Activate the first tab by default
        self._set_active_tab(0)

    def _set_active_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        active_style = """
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border-radius: 6px;
                padding: 7px 16px;
                border: 1px solid #38bdf8;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                font-weight: 600;
                font-size: 13px;
                border-radius: 6px;
                padding: 7px 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #162440;
                color: #38bdf8;
            }
        """
        if index == 0:
            self.tab_btn_cats.setStyleSheet(active_style)
            self.tab_btn_pkgs.setStyleSheet(inactive_style)
        else:
            self.tab_btn_cats.setStyleSheet(inactive_style)
            self.tab_btn_pkgs.setStyleSheet(active_style)

    def _setup_categories_page(self, page: QWidget):
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 4, 0, 4)

        mode_card = QFrame()
        mode_card.setObjectName("cardFrame")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setSpacing(8)

        lbl_title = QLabel("حالت فعال دسته‌بندی:")
        lbl_title.setStyleSheet("font-weight: 700; color: #38bdf8;")
        mode_layout.addWidget(lbl_title)

        self.cat_btn_group = QButtonGroup(self)
        self.radio_cat_default = QRadioButton("دسته‌بندی‌های استاندارد انگلیسی (پیش‌فرض)")
        self.cat_btn_group.addButton(self.radio_cat_default)
        mode_layout.addWidget(self.radio_cat_default)

        self.radio_cat_custom = QRadioButton("دسته‌بندی‌های پیشرفته و سفارشی کارگاه")
        self.cat_btn_group.addButton(self.radio_cat_custom)
        mode_layout.addWidget(self.radio_cat_custom)

        self.radio_cat_default.toggled.connect(self._refresh_cat_list)
        layout.addWidget(mode_card)

        # Full-width selection list widget
        self.cat_list_widget = QListWidget()
        layout.addWidget(self.cat_list_widget)

        # Add/delete management tools in custom mode
        self.cat_tools = QWidget()
        tools_layout = QVBoxLayout(self.cat_tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)

        add_layout = QHBoxLayout()
        self.new_cat_input = QLineEdit()
        self.new_cat_input.setPlaceholderText("نام دسته جدید (مثلاً: Optical / Photodiode)...")
        self.new_cat_input.returnPressed.connect(self._add_custom_category)
        add_layout.addWidget(self.new_cat_input, 3)

        btn_add = QPushButton("+ افزودن دسته")
        btn_add.setObjectName("successBtn")
        btn_add.clicked.connect(self._add_custom_category)
        add_layout.addWidget(btn_add, 1)
        tools_layout.addLayout(add_layout)

        del_layout = QHBoxLayout()
        del_layout.addStretch()
        btn_delete = QPushButton("✕ حذف دسته انتخاب‌شده")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.clicked.connect(self._delete_selected_category)
        del_layout.addWidget(btn_delete)
        tools_layout.addLayout(del_layout)

        layout.addWidget(self.cat_tools)

    def _setup_packages_page(self, page: QWidget):
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 4, 0, 4)

        mode_card = QFrame()
        mode_card.setObjectName("cardFrame")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setSpacing(8)

        lbl_title = QLabel("حالت فعال پکیج‌ها / فوت‌پرینت:")
        lbl_title.setStyleSheet("font-weight: 700; color: #38bdf8;")
        mode_layout.addWidget(lbl_title)

        self.pkg_btn_group = QButtonGroup(self)
        self.radio_pkg_default = QRadioButton("پکیج‌های استاندارد بین‌المللی (پیش‌فرض)")
        self.pkg_btn_group.addButton(self.radio_pkg_default)
        mode_layout.addWidget(self.radio_pkg_default)

        self.radio_pkg_custom = QRadioButton("پکیج‌های پیشرفته و سفارشی کارگاه")
        self.pkg_btn_group.addButton(self.radio_pkg_custom)
        mode_layout.addWidget(self.radio_pkg_custom)

        self.radio_pkg_default.toggled.connect(self._refresh_pkg_list)
        layout.addWidget(mode_card)

        # Full-width selection list widget
        self.pkg_list_widget = QListWidget()
        layout.addWidget(self.pkg_list_widget)

        # Add/delete management tools in custom mode
        self.pkg_tools = QWidget()
        tools_layout = QVBoxLayout(self.pkg_tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)

        add_layout = QHBoxLayout()
        self.new_pkg_input = QLineEdit()
        self.new_pkg_input.setPlaceholderText("نام پکیج جدید (مثلاً: SOP-8 یا LQFP-64)...")
        self.new_pkg_input.returnPressed.connect(self._add_custom_package)
        add_layout.addWidget(self.new_pkg_input, 3)

        btn_add = QPushButton("+ افزودن پکیج")
        btn_add.setObjectName("successBtn")
        btn_add.clicked.connect(self._add_custom_package)
        add_layout.addWidget(btn_add, 1)
        tools_layout.addLayout(add_layout)

        del_layout = QHBoxLayout()
        del_layout.addStretch()
        btn_delete = QPushButton("✕ حذف پکیج انتخاب‌شده")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.clicked.connect(self._delete_selected_package)
        del_layout.addWidget(btn_delete)
        tools_layout.addLayout(del_layout)

        layout.addWidget(self.pkg_tools)

    def _load_current_state(self):
        # Load category active mode
        cat_mode = self.db.get_category_mode()
        if cat_mode == "CUSTOM":
            self.radio_cat_custom.setChecked(True)
        else:
            self.radio_cat_default.setChecked(True)
        self._refresh_cat_list()

        # Load package active mode
        pkg_mode = self.db.get_package_mode()
        if pkg_mode == "CUSTOM":
            self.radio_pkg_custom.setChecked(True)
        else:
            self.radio_pkg_default.setChecked(True)
        self._refresh_pkg_list()

    def _refresh_cat_list(self):
        self.cat_list_widget.clear()
        is_custom = self.radio_cat_custom.isChecked()
        self.cat_tools.setVisible(is_custom)

        if is_custom:
            custom_cats = self.db.get_custom_categories()
            if not custom_cats:
                for c in DEFAULT_CATEGORIES:
                    if c != "—":
                        self.db.add_custom_category(c)
                custom_cats = self.db.get_custom_categories()
            for cat in custom_cats:
                self.cat_list_widget.addItem(QListWidgetItem(cat))
        else:
            for cat in DEFAULT_CATEGORIES:
                self.cat_list_widget.addItem(QListWidgetItem(cat))

    def _refresh_pkg_list(self):
        self.pkg_list_widget.clear()
        is_custom = self.radio_pkg_custom.isChecked()
        self.pkg_tools.setVisible(is_custom)

        if is_custom:
            custom_pkgs = self.db.get_custom_packages()
            if not custom_pkgs:
                for p in DEFAULT_PACKAGES:
                    if p != "—":
                        self.db.add_custom_package(p)
                custom_pkgs = self.db.get_custom_packages()
            for pkg in custom_pkgs:
                self.pkg_list_widget.addItem(QListWidgetItem(pkg))
        else:
            for pkg in DEFAULT_PACKAGES:
                self.pkg_list_widget.addItem(QListWidgetItem(pkg))

    def _add_custom_category(self):
        name = self.new_cat_input.text().strip()
        if not name or name == "—":
            return
        success = self.db.add_custom_category(name)
        if success:
            self.new_cat_input.clear()
            self._refresh_cat_list()
        else:
            QMessageBox.warning(self, "خطا", f"دسته «{name}» از قبل وجود دارد.")

    def _delete_selected_category(self):
        selected = self.cat_list_widget.selectedItems()
        if not selected:
            QMessageBox.information(self, "راهنما", "لطفاً ابتدا یک دسته را از لیست انتخاب فرمایید.")
            return

        cat_text = selected[0].text().strip()
        if cat_text == "—":
            QMessageBox.warning(self, "خطا", "امکان حذف علامت پیش‌فرض وجود ندارد.")
            return

        confirmed = ask_persian_confirmation(
            self, "تایید حذف دسته",
            f"آیا از حذف دسته سفارشی «{cat_text}» اطمینان دارید؟"
        )
        if confirmed:
            self.db.delete_custom_category(cat_text)
            self._refresh_cat_list()

    def _add_custom_package(self):
        name = self.new_pkg_input.text().strip()
        if not name or name == "—":
            return
        success = self.db.add_custom_package(name)
        if success:
            self.new_pkg_input.clear()
            self._refresh_pkg_list()
        else:
            QMessageBox.warning(self, "خطا", f"پکیج «{name}» از قبل وجود دارد.")

    def _delete_selected_package(self):
        selected = self.pkg_list_widget.selectedItems()
        if not selected:
            QMessageBox.information(self, "راهنما", "لطفاً ابتدا یک پکیج را از لیست انتخاب فرمایید.")
            return

        pkg_text = selected[0].text().strip()
        if pkg_text == "—":
            QMessageBox.warning(self, "خطا", "امکان حذف علامت پیش‌فرض وجود ندارد.")
            return

        confirmed = ask_persian_confirmation(
            self, "تایید حذف پکیج",
            f"آیا از حذف پکیج سفارشی «{pkg_text}» اطمینان دارید؟"
        )
        if confirmed:
            self.db.delete_custom_package(pkg_text)
            self._refresh_pkg_list()

    def _save_settings(self):
        cat_mode = "CUSTOM" if self.radio_cat_custom.isChecked() else "DEFAULT"
        pkg_mode = "CUSTOM" if self.radio_pkg_custom.isChecked() else "DEFAULT"
        self.db.set_category_mode(cat_mode)
        self.db.set_package_mode(pkg_mode)
        self.accept()
