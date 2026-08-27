from typing import Optional, List
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QComboBox, QPushButton, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from ui.widgets.custom_inputs import auto_detect_text_direction


class FilterBarWidget(QFrame):
    """Search and multi-criteria filter bar for inventory filtering."""

    filterChanged = pyqtSignal()
    enterPressed = pyqtSignal()
    resetRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self._init_ui()

    def _init_ui(self):
        filter_layout = QHBoxLayout(self)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجوی پارت‌نامبر، مقدار (10k)، نام، پکیج یا شماره کشو... (کلید /)")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self.enterPressed.emit)
        filter_layout.addWidget(self.search_input, 3)

        self.category_filter = QComboBox()
        self.category_filter.addItem("همه دسته‌ها")
        self.category_filter.currentIndexChanged.connect(lambda: self.filterChanged.emit())
        filter_layout.addWidget(self.category_filter, 1)

        self.stock_filter = QComboBox()
        self.stock_filter.addItem("همه وضعیت‌ها")
        self.stock_filter.addItem("موجود (کافی)")
        self.stock_filter.addItem("کسری موجودی")
        self.stock_filter.addItem("ناموجود (صفر)")
        self.stock_filter.currentIndexChanged.connect(lambda: self.filterChanged.emit())
        filter_layout.addWidget(self.stock_filter, 1)

        self.reset_filter_btn = QPushButton("پاکسازی فیلترها")
        self.reset_filter_btn.setObjectName("secondaryBtn")
        self.reset_filter_btn.setToolTip("پاک کردن فیلترها و جستجو (Escape)")
        self.reset_filter_btn.clicked.connect(self.resetRequested.emit)
        filter_layout.addWidget(self.reset_filter_btn)

    def _on_search_text_changed(self, text: str):
        auto_detect_text_direction(self.search_input, text)
        self.filterChanged.emit()

    def set_categories(self, categories: List[str]):
        curr = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("همه دسته‌ها")
        for cat in categories:
            if cat != "—":
                self.category_filter.addItem(cat)

        idx = self.category_filter.findText(curr)
        if idx >= 0:
            self.category_filter.setCurrentIndex(idx)
        else:
            self.category_filter.setCurrentIndex(0)
        self.category_filter.blockSignals(False)

    def reset(self):
        self.search_input.clear()
        self.category_filter.setCurrentIndex(0)
        self.stock_filter.setCurrentIndex(0)
