"""
Omnix UI — Vendor & Link Providers Reference Data Dialog
Governing Requirement: Centralized governance of vendor and supplier link providers.
"""

from typing import Optional, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QFrame,
    QMessageBox,
    QFormLayout,
)

from ui.dark_frame import apply_dark_window_frame
from core.inventory.models import (
    ProviderRecord,
    clean_display_string,
    ReferenceDataInUseError,
    DuplicateReferenceError,
    ValidationError,
)
from core.inventory.repository import SqliteInventoryRepository


class ProviderEditDialog(QDialog):
    """Sub-dialog to add or edit a single Vendor / Link Provider."""

    def __init__(
        self,
        provider: Optional[ProviderRecord] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.provider = provider
        self.is_edit = provider is not None
        self.setWindowTitle("Edit Provider" if self.is_edit else "Add Vendor / Link Provider")
        self.setFixedWidth(460)
        self.setStyleSheet("background-color: #0b101b; color: #f8fafc;")
        apply_dark_window_frame(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("e.g. vendor_mouser or generic")
        if self.is_edit and self.provider:
            self.id_input.setText(self.provider.provider_id)
            self.id_input.setEnabled(False)  # Immutable ID in edit
        form_layout.addRow("Provider ID:", self.id_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Mouser Electronics")
        if self.is_edit and self.provider:
            self.name_input.setText(self.provider.name)
        form_layout.addRow("Display Name:", self.name_input)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g. MOUSER")
        if self.is_edit and self.provider:
            self.label_input.setText(self.provider.label)
        form_layout.addRow("Short Label:", self.label_input)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.mouser.com")
        if self.is_edit and self.provider:
            self.url_input.setText(self.provider.base_url)
        form_layout.addRow("Base URL:", self.url_input)

        self.active_chk = QCheckBox("Active for Component Supplier Links")
        self.active_chk.setChecked(self.provider.is_active if self.is_edit and self.provider else True)
        form_layout.addRow("", self.active_chk)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save" if self.is_edit else "Add Provider")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self):
        pid = self.id_input.text().strip()
        name = self.name_input.text().strip()
        label = self.label_input.text().strip()
        if not pid or not name or not label:
            QMessageBox.warning(self, "Validation Error", "Provider ID, Display Name, and Short Label are required.")
            return
        self.accept()

    def get_data(self):
        return {
            "provider_id": self.id_input.text().strip(),
            "name": self.name_input.text().strip(),
            "label": self.label_input.text().strip().upper(),
            "base_url": self.url_input.text().strip(),
            "is_active": self.active_chk.isChecked(),
        }


class ProviderManagementDialog(QDialog):
    """
    Dedicated dialog for viewing, adding, editing, and managing
    Vendor & Link Providers in the SQLite repository.
    """
    providersChanged = pyqtSignal()

    def __init__(
        self,
        repository: SqliteInventoryRepository,
        parent: Optional[QWidget] = None,
        is_embedded: bool = False,
    ):
        super().__init__(parent)
        self.repository = repository
        self.is_embedded = is_embedded
        self.setWindowTitle("Vendor & Link Providers Management")
        self.setMinimumSize(780, 480)
        self.setStyleSheet("background-color: #0b101b; color: #f8fafc;")
        if not is_embedded:
            apply_dark_window_frame(self)

        self._init_ui()
        if self.is_embedded and hasattr(self, "close_btn"):
            self.close_btn.setVisible(False)
        self.refresh()

    def set_repository(self, repository: SqliteInventoryRepository):
        self.repository = repository
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Info Banner
        hdr_layout = QHBoxLayout()
        title_lbl = QLabel("Vendor & Supplier Link Providers")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self.summary_lbl = QLabel("0 providers registered")
        self.summary_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(self.summary_lbl)
        layout.addLayout(hdr_layout)

        desc_lbl = QLabel(
            "Configure recognized supplier vendors and URL prefixes for automated link matching and component registration."
        )
        desc_lbl.setStyleSheet("font-size: 12px; color: #64748b;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Providers Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Provider ID", "Display Name", "Label", "Base URL", "Status"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        # Toolbar Buttons
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Provider")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("✏️ Edit Selected")
        self.edit_btn.setObjectName("secondaryBtn")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self.edit_btn)

        self.toggle_active_btn = QPushButton("Toggle Active")
        self.toggle_active_btn.setObjectName("secondaryBtn")
        self.toggle_active_btn.setEnabled(False)
        self.toggle_active_btn.clicked.connect(self._on_toggle_active)
        btn_row.addWidget(self.toggle_active_btn)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setObjectName("secondaryBtn")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)

        btn_row.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryBtn")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)

    def refresh(self):
        providers = self.repository.get_all_providers(include_inactive=True)
        self.summary_lbl.setText(f"{len(providers)} providers registered")
        self.table.setRowCount(len(providers))

        font_data = QFont("Segoe UI", 9)
        font_code = QFont("Consolas", 9)

        for row_idx, p in enumerate(providers):
            # 0: Provider ID
            it0 = QTableWidgetItem(p.provider_id)
            it0.setFont(font_code)
            it0.setData(Qt.ItemDataRole.UserRole, p.id)
            self.table.setItem(row_idx, 0, it0)

            # 1: Name
            it1 = QTableWidgetItem(p.name)
            it1.setFont(font_data)
            self.table.setItem(row_idx, 1, it1)

            # 2: Label
            it2 = QTableWidgetItem(p.label)
            it2.setFont(font_code)
            it2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 2, it2)

            # 3: Base URL
            it3 = QTableWidgetItem(p.base_url)
            it3.setFont(font_code)
            self.table.setItem(row_idx, 3, it3)

            # 4: Status
            status_text = "Active" if p.is_active else "Inactive"
            it4 = QTableWidgetItem(status_text)
            it4.setFont(font_data)
            it4.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if p.is_active:
                it4.setForeground(QColor("#34d399"))
            else:
                it4.setForeground(QColor("#64748b"))
            self.table.setItem(row_idx, 4, it4)

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(4)
        self._on_selection_changed()

    def _selected_provider(self) -> Optional[ProviderRecord]:
        rows = self.table.selectedItems()
        if not rows:
            return None
        r = self.table.currentRow()
        it = self.table.item(r, 0)
        if not it:
            return None
        pk = it.data(Qt.ItemDataRole.UserRole)
        for p in self.repository.get_all_providers(include_inactive=True):
            if p.id == pk:
                return p
        return None

    def _on_selection_changed(self):
        p = self._selected_provider()
        has_sel = p is not None
        self.edit_btn.setEnabled(has_sel)
        self.toggle_active_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        if p:
            self.toggle_active_btn.setText("Set Inactive" if p.is_active else "Set Active")

    def _on_add(self):
        dlg = ProviderEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.repository.add_provider(
                    provider_id=data["provider_id"],
                    name=data["name"],
                    label=data["label"],
                    base_url=data["base_url"],
                    is_active=data["is_active"],
                )
                self.refresh()
                self.providersChanged.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error Adding Provider", str(e))

    def _on_edit(self):
        p = self._selected_provider()
        if not p:
            return
        dlg = ProviderEditDialog(provider=p, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.repository.update_provider(
                    provider_pk=p.id,
                    name=data["name"],
                    label=data["label"],
                    base_url=data["base_url"],
                    is_active=data["is_active"],
                )
                self.refresh()
                self.providersChanged.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error Updating Provider", str(e))

    def _on_toggle_active(self):
        p = self._selected_provider()
        if not p:
            return
        try:
            self.repository.update_provider(provider_pk=p.id, is_active=not p.is_active)
            self.refresh()
            self.providersChanged.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error Updating Status", str(e))

    def _on_delete(self):
        p = self._selected_provider()
        if not p:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Delete Provider",
            f"Are you sure you want to delete provider '{p.name}' ({p.provider_id})?\n\n"
            f"If components use links with this provider, deletion will be blocked and you should deactivate it instead.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.repository.delete_provider(p.id)
                self.refresh()
                self.providersChanged.emit()
            except Exception as e:
                QMessageBox.critical(self, "Deletion Failed", str(e))
