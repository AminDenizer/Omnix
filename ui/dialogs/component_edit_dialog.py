"""
Omnix UI — Component Registration and Edit Dialog
Governing Document: Phase 2.2 / Phase 2.2.1 Specification

Modal interface for registering new physical components and editing existing ones.
Provides:
- Exact duplicate identity detection at UI, repository, and database levels.
- User-friendly duplicate notification in English.
- Multi-vendor supplier link management (Add, Edit, Remove).
- Real-time field validation with clean feedback.
- Category / Type canonical reference alignment with category-dependent filtering.
- Complete form reset and lifecycle isolation (zero state leakage).
- Fixed bottom action buttons with scrollable form body.
"""

import os
from typing import List, Optional, Tuple, Any
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject, QEvent
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QPen, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QToolButton,
    QFrame,
    QScrollArea,
    QMessageBox,
    QInputDialog,
    QCompleter,
    QAbstractSpinBox,
)

from ui.dark_frame import apply_dark_window_frame

from config import get_bundle_dir
from core.inventory.models import (
    InventoryProduct,
    SupplierLink,
    normalize_package,
    build_group_key,
    normalize_identity_part,
    clean_display_string,
    ComponentConflictError,
    ValidationError,
    ReferenceDataNotFoundError,
)
from core.procurement.vendor_links import (
    KNOWN_VENDOR_LABELS,
    DEFAULT_VENDOR_NAMES,
)

VENDOR_CHOICES: List[Tuple[str, str, str]] = [
    ("vendor_lion", "LION", "Lion Electronic (LION)"),
    ("vendor_javan", "JAVAN", "Javan Electronic (JAVAN)"),
    ("vendor_roboeq", "ROBOEQ", "RoboEq (ROBOEQ)"),
    ("generic", "OTHER", "Other / Generic"),
]


def _get_combo_chevron_urls() -> Tuple[str, str]:
    """Ensure downward chevron icon assets exist and return normalized paths for QSS."""
    icons_dir = os.path.join(get_bundle_dir(), "ui", "icons")
    try:
        os.makedirs(icons_dir, exist_ok=True)
    except Exception:
        pass
    chevron_p = os.path.join(icons_dir, "combo_chevron_down.png")
    chevron_h_p = os.path.join(icons_dir, "combo_chevron_down_hover.png")
    try:
        if not (os.path.exists(chevron_p) and os.path.exists(chevron_h_p)):
            def make_chevron(color="#94a3b8", size=16):
                pm = QPixmap(size, size)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                pen = QPen(QColor(color), 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.drawLine(4, 6, 8, 10)
                p.drawLine(8, 10, 12, 6)
                p.end()
                return pm
            make_chevron("#94a3b8", 16).save(chevron_p)
            make_chevron("#38bdf8", 16).save(chevron_h_p)
    except Exception:
        pass
    return chevron_p.replace("\\", "/"), chevron_h_p.replace("\\", "/")


class WheelScrollForwarder(QObject):
    """
    Event filter that intercepts wheel events on child inputs (combos, spinboxes,
    line edits, frames) and forwards the wheel delta directly to the parent
    QScrollArea vertical scrollbar, ensuring smooth scrolling without changing values.
    """

    def __init__(self, scroll_area: QScrollArea, parent: Optional[QObject] = None):
        super().__init__(parent or scroll_area)
        self.scroll_area = scroll_area

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            v_bar = self.scroll_area.verticalScrollBar()
            if v_bar and v_bar.isVisible():
                delta = event.angleDelta().y()
                if delta != 0:
                    steps = delta / 120.0
                    scroll_amount = int(steps * v_bar.singleStep() * 3)
                    if scroll_amount == 0:
                        scroll_amount = 1 if delta > 0 else -1
                    v_bar.setValue(v_bar.value() - scroll_amount)
                    return True
        return super().eventFilter(watched, event)


class CompleterKeyFilter(QObject):
    """
    Event filter installed on editable QComboBox line edits and their QCompleter popups.
    Intercepts:
    - Arrow Down / Up: navigates available suggestions in the popup list.
    - Tab / Backtab: commits highlighted suggestion or validated exact match, closes popup, advances focus.
    - Enter / Return: commits highlighted suggestion or validated exact match and closes popup.
    - Escape: closes popup without committing or discarding entered text.
    - FocusOut: commits exact match if valid, preserves entered text without coercion or accidental erasure.
    """

    def __init__(self, combo: QComboBox, parent: Optional[QObject] = None):
        super().__init__(parent or combo)
        self.combo = combo

    def _resolve_candidate(self, is_tab_or_enter: bool = False) -> Optional[str]:
        """
        Determines the candidate reference value to commit based on deterministic selection rules:
        Rule 1: If exactly one valid suggestion matches (unique match), commit that suggestion immediately.
        Rule 2: If multiple suggestions match and a suggestion is explicitly active/highlighted, commit it.
        Rule 3: If multiple suggestions match and none is explicitly selected, do NOT arbitrarily commit.
                Ambiguous matches must not cause unintended selection. Preserve user draft text.
        Rule 4: If no valid matches exist (arbitrary text), return None without coercion.
        FocusOut (blur): Exact case-insensitive matches or unambiguous unique prefix matches normalize;
                         otherwise preserve draft text without coercion.
        """
        le = self.combo.lineEdit()
        cur_txt = (le.text() if le else self.combo.currentText()).strip()
        if not cur_txt:
            return None

        cur_lower = cur_txt.lower()
        items = [self.combo.itemText(i).strip() for i in range(self.combo.count()) if self.combo.itemText(i).strip()]

        # 1. Exact case-insensitive match against reference list items
        for it in items:
            if it.lower() == cur_lower:
                return it

        comp = self.combo.completer()
        popup = comp.popup() if comp else None
        popup_visible = popup is not None and popup.isVisible()

        # 2. Rule 2: Explicitly highlighted suggestion in the popup
        if popup_visible and popup is not None:
            curr_idx = popup.currentIndex()
            if curr_idx.isValid():
                val = curr_idx.data(Qt.ItemDataRole.DisplayRole)
                if val:
                    return str(val)

        # 3. Visible popup narrowed to exactly one suggestion
        if popup_visible and popup is not None and popup.model() and popup.model().rowCount() == 1:
            val = popup.model().index(0, 0).data(Qt.ItemDataRole.DisplayRole)
            if val:
                return str(val)

        # 4. Matching database-backed suggestions with prefix priority
        prefix_matches = [it for it in items if it.lower().startswith(cur_lower)]
        contains_matches = [it for it in items if cur_lower in it.lower()]

        # On FocusOut (blur):
        if not is_tab_or_enter:
            # If there is an unambiguous unique prefix match (e.g. 'ftd' -> 'FTDI'), normalize to canonical value
            if len(prefix_matches) == 1:
                return prefix_matches[0]
            # Otherwise, preserve user draft text without arbitrary coercion
            return None

        # On Tab or Enter:
        if is_tab_or_enter:
            # Unique prefix match takes priority (e.g. 'tex' -> 'Texas Instruments', 'd' -> 'Diode', 'np' -> 'NPN')
            if len(prefix_matches) == 1:
                return prefix_matches[0]

            # If multiple prefix matches exist, it is ambiguous -> do NOT commit arbitrarily
            if len(prefix_matches) > 1:
                return None

            # If no prefix matches exist, fall back to unique substring match (e.g. 'transceiver' -> 'RF Transceiver')
            if len(contains_matches) == 1:
                return contains_matches[0]

            # Ambiguous (multiple contains matches) or no matches -> preserve user draft text
            return None

        # Rule 4: Do NOT silently coerce arbitrary text
        return None

    def _commit(self, text_to_commit: str):
        c_idx = self.combo.findText(text_to_commit, Qt.MatchFlag.MatchFixedString)
        if c_idx != -1:
            self.combo.setCurrentIndex(c_idx)
        self.combo.setEditText(text_to_commit)
        if self.combo.lineEdit():
            self.combo.lineEdit().setText(text_to_commit)
        dlg = self.combo.window()
        if hasattr(dlg, "_clear_field_error"):
            dlg._clear_field_error(self.combo)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        comp = self.combo.completer()
        popup = comp.popup() if comp else None
        popup_visible = popup is not None and popup.isVisible()

        if event.type() == QEvent.Type.ShortcutOverride:
            key_event = event
            key = key_event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.accept()
                return True

        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            key = key_event.key()

            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                if popup_visible and popup is not None and popup.model():
                    total_rows = popup.model().rowCount()
                    if total_rows > 0:
                        curr = popup.currentIndex()
                        if not curr.isValid():
                            target_row = 0 if key == Qt.Key.Key_Down else total_rows - 1
                        else:
                            if key == Qt.Key.Key_Down:
                                target_row = min(curr.row() + 1, total_rows - 1)
                            else:
                                target_row = max(curr.row() - 1, 0)
                        popup.setCurrentIndex(popup.model().index(target_row, 0))
                        return True

            elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                text_to_commit = self._resolve_candidate(is_tab_or_enter=True)
                if text_to_commit:
                    self._commit(text_to_commit)

                if popup_visible:
                    popup.hide()

                if key == Qt.Key.Key_Tab:
                    self.combo.focusNextChild()
                else:
                    self.combo.focusPreviousChild()
                return True

            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                text_to_commit = self._resolve_candidate(is_tab_or_enter=True)
                if text_to_commit:
                    self._commit(text_to_commit)

                if popup_visible:
                    popup.hide()
                return True

            elif key == Qt.Key.Key_Escape:
                if popup_visible:
                    popup.hide()
                    return True

        elif event.type() == QEvent.Type.FocusOut:
            if popup and popup.isVisible():
                popup.hide()
            text_to_commit = self._resolve_candidate(is_tab_or_enter=False)
            if text_to_commit:
                self._commit(text_to_commit)
            # Notify dialog to validate field on focus out without erasing entered text
            dlg = self.combo.window()
            if hasattr(dlg, "_on_combo_focus_out"):
                dlg._on_combo_focus_out(self.combo)

        return super().eventFilter(watched, event)


class SupplierLinkRow(QWidget):
    """A single editable supplier link row with Vendor picker, URL edit, and remove button."""
    removeRequested = pyqtSignal(object)

    def __init__(
        self,
        link: Optional[SupplierLink] = None,
        parent: Optional[QWidget] = None,
        combo_style: Optional[str] = None,
        vendor_choices: Optional[List[Tuple[str, str, str]]] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        choices = vendor_choices or VENDOR_CHOICES

        # Vendor Selector
        self.vendor_combo = QComboBox()
        self.vendor_combo.setFont(QFont("Segoe UI", 9))
        self.vendor_combo.setFixedHeight(32)
        self.vendor_combo.setMinimumWidth(160)
        self.vendor_combo.wheelEvent = lambda event: event.ignore()
        if combo_style:
            self.vendor_combo.setStyleSheet(combo_style)
        for vendor_id, vendor_label, display_text in choices:
            self.vendor_combo.addItem(display_text, (vendor_id, vendor_label))

        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setFont(QFont("Consolas", 9))
        self.url_input.setPlaceholderText("https://supplier-store.com/item/...")
        self.url_input.setFixedHeight(32)

        # Remove Button
        self.remove_btn = QToolButton()
        self.remove_btn.setText("✕")
        self.remove_btn.setToolTip("Remove this supplier link")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setStyleSheet("""
            QToolButton {
                background-color: #334155;
                color: #f87171;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
        """)
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self))

        layout.addWidget(self.vendor_combo)
        layout.addWidget(self.url_input, 1)
        layout.addWidget(self.remove_btn)

        if link:
            self.set_link(link)

    def set_link(self, link: SupplierLink):
        # Match vendor
        for idx in range(self.vendor_combo.count()):
            v_id, v_lbl = self.vendor_combo.itemData(idx)
            if v_id == link.vendor_id or v_lbl.upper() == link.vendor_label.upper():
                self.vendor_combo.setCurrentIndex(idx)
                break
        self.url_input.setText(link.url or "")

    def get_link(self) -> Optional[SupplierLink]:
        url = self.url_input.text().strip()
        if not url:
            return None
        v_data = self.vendor_combo.currentData()
        vendor_id, vendor_label = v_data if v_data else ("generic", "OTHER")
        disp_name = DEFAULT_VENDOR_NAMES.get(vendor_id, vendor_label)
        return SupplierLink(
            vendor_id=vendor_id,
            vendor_label=vendor_label,
            url=url,
            display_name=disp_name,
        )


class ComponentEditDialog(QDialog):
    """
    Dedicated modal dialog for:
    - Registering new physical electronic components.
    - Editing existing physical electronic components.
    - Handling duplicate normalized Manufacturer + MPN detection.
    - Managing multi-vendor supplier purchase links.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        repository: Optional[Any] = None,
        component: Optional[InventoryProduct] = None,
        initial_group: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.component = component
        self.initial_group = initial_group
        self.mode = "edit" if component is not None else "create"
        self._link_rows: List[SupplierLinkRow] = []

        self.setWindowTitle(
            f"Edit Component — {component.manufacturer} {component.mpn}"
            if self.mode == "edit"
            else "Register Component"
        )
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(600)
        self.setFont(QFont("Segoe UI", 10))

        self._init_ui()
        self._load_reference_data()

        if self.mode == "edit":
            self._populate_from_component(self.component)
        elif self.initial_group:
            self._populate_from_group(self.initial_group)
        else:
            self.reset_form()

        apply_dark_window_frame(self)

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_window_frame(self)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 16, 18, 16)

        # 1. Header Banner
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #0d1527;
                border: 1px solid #1a2744;
                border-radius: 6px;
                padding: 10px 14px;
            }
        """)
        hdr_layout = QVBoxLayout(header_frame)
        hdr_layout.setContentsMargins(6, 4, 6, 4)
        hdr_layout.setSpacing(3)

        title_text = "Edit Component" if self.mode == "edit" else "Register Component"
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        sub_text = (
            "Update component parameters, physical stock, and supplier links in SQLite."
            if self.mode == "edit"
            else "Add an individual physical component record with enforced identity uniqueness."
        )
        self.sub_lbl = QLabel(sub_text)
        self.sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hdr_layout.addWidget(self.title_lbl)
        hdr_layout.addWidget(self.sub_lbl)
        main_layout.addWidget(header_frame)

        # 2. Duplicate Detection Alert Banner (hidden by default)
        self.duplicate_frame = QFrame()
        self.duplicate_frame.setVisible(False)
        self.duplicate_frame.setStyleSheet("""
            QFrame {
                background-color: #451a03;
                border: 1px solid #b45309;
                border-radius: 6px;
                padding: 10px 14px;
            }
        """)
        dup_layout = QVBoxLayout(self.duplicate_frame)
        dup_layout.setContentsMargins(8, 6, 8, 6)
        dup_layout.setSpacing(6)

        # User-facing English duplicate notification message
        self.dup_title_lbl = QLabel("This component is already registered.")
        self.dup_title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #fbbf24;")
        dup_layout.addWidget(self.dup_title_lbl)

        self.dup_details_lbl = QLabel()
        self.dup_details_lbl.setStyleSheet("font-size: 11px; color: #fde68a;")
        self.dup_details_lbl.setWordWrap(True)
        dup_layout.addWidget(self.dup_details_lbl)

        dup_btn_layout = QHBoxLayout()
        dup_btn_layout.setSpacing(8)
        dup_btn_layout.addStretch()

        self.edit_existing_btn = QPushButton("Open Existing Record for Editing")
        self.edit_existing_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_existing_btn.setStyleSheet("""
            QPushButton {
                background-color: #d97706;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
                padding: 4px 12px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #b45309;
            }
        """)
        self.edit_existing_btn.clicked.connect(self._on_switch_to_existing_component)
        dup_btn_layout.addWidget(self.edit_existing_btn)
        dup_layout.addLayout(dup_btn_layout)

        main_layout.addWidget(self.duplicate_frame)

        # 3. Form Content (Scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        self._wheel_filter = WheelScrollForwarder(scroll, parent=self)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 20)  # Generous bottom breathing margin
        form_layout.setSpacing(10)

        chev_url, chev_hover_url = _get_combo_chevron_urls()

        # Cohesive single container surface replacing fragmented individual cards
        form_surface = QFrame()
        form_surface.setObjectName("formSurface")
        form_surface.setStyleSheet("""
            QFrame#formSurface {
                background-color: #111a2e;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 14px 16px;
            }
        """)
        surface_layout = QVBoxLayout(form_surface)
        surface_layout.setContentsMargins(14, 14, 14, 14)
        surface_layout.setSpacing(12)

        lbl_sec_style = "font-size: 11px; font-weight: 700; color: #cbd5e1; letter-spacing: 0.5px;"
        lbl_field_style = "font-size: 11px; font-weight: 600; color: #94a3b8;"
        LABEL_COL_WIDTH = 145

        def make_section_divider():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setStyleSheet("background-color: #1e293b; max-height: 1px; border: none; margin: 4px 0;")
            return line

        input_style = f"""
            QLineEdit, QSpinBox {{
                background-color: #0b101b;
                color: #f8fafc;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:hover, QSpinBox:hover {{
                border-color: #334155;
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border-color: #38bdf8;
                background-color: #090e18;
            }}
            QComboBox {{
                background-color: #0b101b;
                color: #f8fafc;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 4px 8px;
                padding-right: 28px;
                font-size: 11px;
            }}
            QComboBox:hover {{
                border-color: #334155;
            }}
            QComboBox:focus {{
                border-color: #38bdf8;
                background-color: #090e18;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #1e293b;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                background-color: #131d31;
            }}
            QComboBox::drop-down:hover {{
                background-color: #1e293b;
            }}
            QComboBox::down-arrow {{
                image: url('{chev_url}');
                width: 12px;
                height: 12px;
            }}
            QComboBox::down-arrow:hover {{
                image: url('{chev_hover_url}');
            }}
            QComboBox QAbstractItemView {{
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px;
            }}
        """
        self._input_style = input_style

        # Section A: Component Identity
        lbl_id_sec = QLabel("A. Component Identity")
        lbl_id_sec.setStyleSheet(lbl_sec_style)
        surface_layout.addWidget(lbl_id_sec)

        id_grid = QGridLayout()
        id_grid.setSpacing(8)
        id_grid.setContentsMargins(0, 0, 0, 0)

        lbl_mfr = QLabel("Manufacturer: *")
        lbl_mfr.setFixedWidth(LABEL_COL_WIDTH)
        lbl_mfr.setStyleSheet(lbl_field_style)
        self.mfr_input = QComboBox()
        self.mfr_input.setEditable(True)
        self.mfr_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.mfr_input.setFont(QFont("Segoe UI", 10))
        self.mfr_input.setFixedHeight(32)
        self.mfr_input.setStyleSheet(input_style)
        self.mfr_input.wheelEvent = lambda event: event.ignore()
        self.mfr_input.installEventFilter(self._wheel_filter)
        id_grid.addWidget(lbl_mfr, 0, 0)
        id_grid.addWidget(self.mfr_input, 0, 1)

        # Removed from registration form layout (kept as hidden dummy for backward compatibility)
        self.add_mfr_btn = QToolButton()
        self.add_mfr_btn.setVisible(False)

        lbl_mpn = QLabel("Part Number (MPN): *")
        lbl_mpn.setFixedWidth(LABEL_COL_WIDTH)
        lbl_mpn.setStyleSheet(lbl_field_style)
        self.mpn_input = QLineEdit()
        self.mpn_input.setFont(QFont("Consolas", 10))
        self.mpn_input.setFixedHeight(32)
        self.mpn_input.setStyleSheet(input_style)
        self.mpn_input.installEventFilter(self._wheel_filter)
        id_grid.addWidget(lbl_mpn, 1, 0)
        id_grid.addWidget(self.mpn_input, 1, 1)

        surface_layout.addLayout(id_grid)

        # Divider between Section A and Section B
        surface_layout.addWidget(make_section_divider())

        # Section B: Classification & Physical Properties
        lbl_grp_sec = QLabel("B. Classification & Physical Properties")
        lbl_grp_sec.setStyleSheet(lbl_sec_style)
        surface_layout.addWidget(lbl_grp_sec)

        grp_grid = QGridLayout()
        grp_grid.setSpacing(8)
        grp_grid.setContentsMargins(0, 0, 0, 0)

        lbl_cat = QLabel("Category: *")
        lbl_cat.setFixedWidth(LABEL_COL_WIDTH)
        lbl_cat.setStyleSheet(lbl_field_style)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_combo.setFont(QFont("Segoe UI", 10))
        self.category_combo.setFixedHeight(32)
        self.category_combo.setStyleSheet(input_style)
        self.category_combo.wheelEvent = lambda event: event.ignore()
        self.category_combo.installEventFilter(self._wheel_filter)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self.category_input = self.category_combo
        grp_grid.addWidget(lbl_cat, 0, 0)
        grp_grid.addWidget(self.category_combo, 0, 1)

        self.add_cat_btn = QToolButton()
        self.add_cat_btn.setVisible(False)

        lbl_tech = QLabel("Type / Technology: *")
        lbl_tech.setFixedWidth(LABEL_COL_WIDTH)
        lbl_tech.setStyleSheet(lbl_field_style)
        self.tech_combo = QComboBox()
        self.tech_combo.setEditable(True)
        self.tech_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tech_combo.setFont(QFont("Segoe UI", 10))
        self.tech_combo.setFixedHeight(32)
        self.tech_combo.setStyleSheet(input_style)
        self.tech_combo.wheelEvent = lambda event: event.ignore()
        self.tech_combo.installEventFilter(self._wheel_filter)
        self.type_input = self.tech_combo
        grp_grid.addWidget(lbl_tech, 1, 0)
        grp_grid.addWidget(self.tech_combo, 1, 1)

        self.add_type_btn = QToolButton()
        self.add_type_btn.setVisible(False)

        lbl_val = QLabel("Value: *")
        lbl_val.setFixedWidth(LABEL_COL_WIDTH)
        lbl_val.setStyleSheet(lbl_field_style)
        self.value_input = QLineEdit()
        self.value_input.setFont(QFont("Consolas", 10))
        self.value_input.setPlaceholderText("e.g. 100nF, 10k, 3.3V, NE555")
        self.value_input.setFixedHeight(32)
        self.value_input.setStyleSheet(input_style)
        self.value_input.installEventFilter(self._wheel_filter)
        grp_grid.addWidget(lbl_val, 2, 0)
        grp_grid.addWidget(self.value_input, 2, 1)

        lbl_pkg = QLabel("Package: *")
        lbl_pkg.setFixedWidth(LABEL_COL_WIDTH)
        lbl_pkg.setStyleSheet(lbl_field_style)
        self.package_input = QLineEdit()
        self.package_input.setFont(QFont("Consolas", 10))
        self.package_input.setPlaceholderText("e.g. 0603, 0805, SOIC-8, SOT-23")
        self.package_input.setFixedHeight(32)
        self.package_input.setStyleSheet(input_style)
        self.package_input.installEventFilter(self._wheel_filter)
        grp_grid.addWidget(lbl_pkg, 3, 0)
        grp_grid.addWidget(self.package_input, 3, 1)

        lbl_fp = QLabel("Footprint: *")
        lbl_fp.setFixedWidth(LABEL_COL_WIDTH)
        lbl_fp.setStyleSheet(lbl_field_style)
        self.footprint_input = QLineEdit()
        self.footprint_input.setFont(QFont("Consolas", 10))
        self.footprint_input.setPlaceholderText("e.g. R_0603, C_0805, SO-8")
        self.footprint_input.setFixedHeight(32)
        self.footprint_input.setStyleSheet(input_style)
        self.footprint_input.installEventFilter(self._wheel_filter)
        grp_grid.addWidget(lbl_fp, 4, 0)
        grp_grid.addWidget(self.footprint_input, 4, 1)

        surface_layout.addLayout(grp_grid)

        # Divider between Section B and Section C
        surface_layout.addWidget(make_section_divider())

        # Section C: Inventory
        lbl_det_sec = QLabel("C. Inventory")
        lbl_det_sec.setStyleSheet(lbl_sec_style)
        surface_layout.addWidget(lbl_det_sec)

        det_grid = QGridLayout()
        det_grid.setSpacing(8)
        det_grid.setContentsMargins(0, 0, 0, 0)

        lbl_qty = QLabel("Quantity in Stock: *")
        lbl_qty.setFixedWidth(LABEL_COL_WIDTH)
        lbl_qty.setStyleSheet(lbl_field_style)

        qty_stepper_layout = QHBoxLayout()
        qty_stepper_layout.setSpacing(4)
        qty_stepper_layout.setContentsMargins(0, 0, 0, 0)

        self.qty_spin = QSpinBox()
        self.qty_spin.setFont(QFont("Consolas", 10))
        self.qty_spin.setRange(0, 10000000)
        self.qty_spin.setValue(0)
        self.qty_spin.setFixedHeight(32)
        self.qty_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.qty_spin.setStyleSheet(input_style)
        self.qty_spin.wheelEvent = lambda event: event.ignore()
        self.qty_spin.installEventFilter(self._wheel_filter)
        qty_stepper_layout.addWidget(self.qty_spin, 1)

        qty_btn_layout = QVBoxLayout()
        qty_btn_layout.setSpacing(1)
        qty_btn_layout.setContentsMargins(0, 0, 0, 0)

        stepper_btn_style = """
            QToolButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 3px;
                color: #94a3b8;
            }
            QToolButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
                color: #38bdf8;
            }
            QToolButton:pressed {
                background-color: #0284c7;
                color: #ffffff;
            }
        """

        self.qty_up_btn = QToolButton()
        self.qty_up_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.qty_up_btn.setFixedSize(26, 15)
        self.qty_up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.qty_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qty_up_btn.setToolTip("Increase Quantity in Stock")
        self.qty_up_btn.setAutoRepeat(True)
        self.qty_up_btn.setAutoRepeatDelay(350)
        self.qty_up_btn.setAutoRepeatInterval(80)
        self.qty_up_btn.setStyleSheet(stepper_btn_style)
        self.qty_up_btn.clicked.connect(self.qty_spin.stepUp)

        self.qty_down_btn = QToolButton()
        self.qty_down_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.qty_down_btn.setFixedSize(26, 15)
        self.qty_down_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.qty_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qty_down_btn.setToolTip("Decrease Quantity in Stock")
        self.qty_down_btn.setAutoRepeat(True)
        self.qty_down_btn.setAutoRepeatDelay(350)
        self.qty_down_btn.setAutoRepeatInterval(80)
        self.qty_down_btn.setStyleSheet(stepper_btn_style)
        self.qty_down_btn.clicked.connect(self.qty_spin.stepDown)

        qty_btn_layout.addWidget(self.qty_up_btn)
        qty_btn_layout.addWidget(self.qty_down_btn)
        qty_stepper_layout.addLayout(qty_btn_layout)

        det_grid.addWidget(lbl_qty, 0, 0)
        det_grid.addLayout(qty_stepper_layout, 0, 1)

        surface_layout.addLayout(det_grid)

        # Divider between Section C and Section D
        surface_layout.addWidget(make_section_divider())

        # Section D: Additional Information & Supplier Links
        lbl_extra_sec = QLabel("D. Additional Information & Supplier Links")
        lbl_extra_sec.setStyleSheet(lbl_sec_style)
        surface_layout.addWidget(lbl_extra_sec)

        desc_grid = QGridLayout()
        desc_grid.setSpacing(8)
        desc_grid.setContentsMargins(0, 0, 0, 0)
        lbl_desc = QLabel("Description: (Optional)")
        lbl_desc.setFixedWidth(LABEL_COL_WIDTH)
        lbl_desc.setStyleSheet(lbl_field_style)
        self.desc_input = QLineEdit()
        self.desc_input.setFont(QFont("Segoe UI", 10))
        self.desc_input.setPlaceholderText("Technical description or application notes")
        self.desc_input.setFixedHeight(32)
        self.desc_input.setStyleSheet(input_style)
        self.desc_input.installEventFilter(self._wheel_filter)
        desc_grid.addWidget(lbl_desc, 0, 0)
        desc_grid.addWidget(self.desc_input, 0, 1)
        surface_layout.addLayout(desc_grid)

        links_hdr = QHBoxLayout()
        lbl_links_sec = QLabel("Supplier Purchase Links (0 or more)")
        lbl_links_sec.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        links_hdr.addWidget(lbl_links_sec)
        links_hdr.addStretch()

        self.add_link_btn = QPushButton("+ Add Supplier Link")
        self.add_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_link_btn.setFixedHeight(28)
        self.add_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
                border: 1px solid #334155;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.add_link_btn.clicked.connect(self._add_empty_link_row)
        links_hdr.addWidget(self.add_link_btn)
        surface_layout.addLayout(links_hdr)

        self.links_container = QVBoxLayout()
        self.links_container.setSpacing(6)
        surface_layout.addLayout(self.links_container)

        # Backwards compatibility layout reference
        self.links_layout = surface_layout

        form_layout.addWidget(form_surface)

        scroll.setWidget(form_container)
        main_layout.addWidget(scroll, 1)

        # 4. Fixed Validation feedback label
        self.validation_lbl = QLabel("")
        self.validation_lbl.setWordWrap(True)
        self.validation_lbl.setStyleSheet("font-size: 11px; color: #f87171; min-height: 20px;")
        main_layout.addWidget(self.validation_lbl)

        # 5. Fixed Bottom Dialog Actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        save_txt = "Save Changes" if self.mode == "edit" else "Register Component"
        self.save_btn = QPushButton(save_txt)
        self.save_btn.setFixedSize(160, 36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

    def reset_form(self):
        """Resets the dialog into a completely clean registration form with zero state leakage."""
        self.component = None
        self.saved_component = None
        self.mode = "create"
        self.setWindowTitle("Register Component")
        if hasattr(self, "title_lbl"):
            self.title_lbl.setText("Register Component")
        if hasattr(self, "sub_lbl"):
            self.sub_lbl.setText("Add an individual physical component record with enforced identity uniqueness.")
        if hasattr(self, "save_btn"):
            self.save_btn.setText("Register Component")

        if hasattr(self, "mfr_input"):
            self.mfr_input.blockSignals(True)
            self.mfr_input.setCurrentIndex(-1)
            self.mfr_input.setEditText("")
            self.mfr_input.blockSignals(False)

        if hasattr(self, "mpn_input"):
            self.mpn_input.clear()

        if hasattr(self, "category_combo"):
            self.category_combo.blockSignals(True)
            self.category_combo.setCurrentIndex(-1)
            self.category_combo.setEditText("")
            self.category_combo.blockSignals(False)

        if hasattr(self, "tech_combo"):
            self.tech_combo.blockSignals(True)
            self.tech_combo.clear()
            self.tech_combo.setCurrentIndex(-1)
            self.tech_combo.setEditText("")
            self.tech_combo.blockSignals(False)

        if hasattr(self, "value_input"):
            self.value_input.clear()
        if hasattr(self, "package_input"):
            self.package_input.clear()
        if hasattr(self, "footprint_input"):
            self.footprint_input.clear()
        if hasattr(self, "desc_input"):
            self.desc_input.clear()
        if hasattr(self, "qty_spin"):
            self.qty_spin.setValue(0)

        self._clear_all_link_rows()

        if hasattr(self, "duplicate_frame"):
            self.duplicate_frame.setVisible(False)
        if hasattr(self, "dup_details_lbl"):
            self.dup_details_lbl.setText("")
        if hasattr(self, "validation_lbl"):
            self.validation_lbl.setText("")
        if hasattr(self, "_set_field_error"):
            if hasattr(self, "mfr_input"):
                self._set_field_error(self.mfr_input, False)
            if hasattr(self, "category_combo"):
                self._set_field_error(self.category_combo, False)
            if hasattr(self, "tech_combo"):
                self._set_field_error(self.tech_combo, False)

    def _set_field_error(self, widget: QWidget, is_error: bool):
        """Toggle red error border and subtle error background styling on input fields."""
        chev_url, chev_hover_url = _get_combo_chevron_urls()
        border_color = "#ef4444" if is_error else "#1e293b"
        bg_color = "#180e14" if is_error else "#0b101b"
        focus_border = "#f87171" if is_error else "#38bdf8"

        style = f"""
            QComboBox {{
                background-color: {bg_color};
                color: #f8fafc;
                border: 1px solid {border_color};
                border-radius: 5px;
                padding: 4px 8px;
                padding-right: 28px;
                font-size: 11px;
            }}
            QComboBox:hover {{
                border-color: {focus_border};
            }}
            QComboBox:focus {{
                border-color: {focus_border};
                background-color: #090e18;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {border_color};
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                background-color: #131d31;
            }}
            QComboBox::drop-down:hover {{
                background-color: #1e293b;
            }}
            QComboBox::down-arrow {{
                image: url('{chev_url}');
                width: 12px;
                height: 12px;
            }}
            QComboBox::down-arrow:hover {{
                image: url('{chev_hover_url}');
            }}
            QComboBox QAbstractItemView {{
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px;
            }}
        """
        widget.setStyleSheet(style)
        widget.setProperty("_has_validation_error", is_error)

    def _clear_field_error(self, widget: QWidget):
        """Clear error border styling from an input field."""
        if widget.property("_has_validation_error"):
            self._set_field_error(widget, False)
            if hasattr(self, "validation_lbl"):
                self.validation_lbl.setText("")

    def _on_combo_focus_out(self, combo: QComboBox):
        """Validate reference fields when user finishes typing and leaves the field."""
        if not self.repository:
            return

        txt = clean_display_string(combo.currentText())
        if not txt:
            self._clear_field_error(combo)
            return

        if combo is getattr(self, "mfr_input", None):
            has_ref = False
            try:
                mfrs = self.repository.get_all_manufacturers()
                has_ref = len(mfrs) > 0
            except Exception:
                has_ref = False

            if has_ref:
                mfr_rec = self.repository.get_manufacturer_by_name(txt)
                if not mfr_rec:
                    self._set_field_error(combo, True)
                    self.validation_lbl.setText(
                        f"Manufacturer '{txt}' is not in canonical reference data. Please select an existing manufacturer from Reference Data."
                    )
                else:
                    self._set_field_error(combo, False)
                    if self.validation_lbl.text().startswith("Manufacturer '"):
                        self.validation_lbl.setText("")

        elif combo is getattr(self, "category_combo", None):
            has_ref = False
            try:
                cats = self.repository.get_all_categories()
                has_ref = len(cats) > 0
            except Exception:
                has_ref = False

            if has_ref:
                cat_rec = self.repository.get_category_by_name(txt)
                if not cat_rec:
                    self._set_field_error(combo, True)
                    self.validation_lbl.setText(
                        f"Category '{txt}' is not in canonical reference data. Please select an existing category from Reference Data."
                    )
                else:
                    self._set_field_error(combo, False)
                    if self.validation_lbl.text().startswith("Category '"):
                        self.validation_lbl.setText("")

        elif combo is getattr(self, "tech_combo", None):
            cat = clean_display_string(self.category_combo.currentText()) if hasattr(self, "category_combo") else ""
            if not cat:
                self._set_field_error(combo, True)
                self.validation_lbl.setText("Please select a Category before choosing Type/Technology.")
                return

            cat_rec = self.repository.get_category_by_name(cat)
            if not cat_rec:
                self._set_field_error(combo, True)
                self.validation_lbl.setText(
                    f"Category '{cat}' is not in canonical reference data."
                )
                return

            if not self.repository.validate_category_type(cat, txt):
                self._set_field_error(combo, True)
                self.validation_lbl.setText(
                    f"Type/Technology '{txt}' is not valid for category '{cat}'. Please select an existing type from Reference Data."
                )
            else:
                self._set_field_error(combo, False)
                if self.validation_lbl.text().startswith("Type/Technology '"):
                    self.validation_lbl.setText("")

    def _configure_combo_autocomplete(self, combo: QComboBox):
        """Configure clean popup autocomplete on an editable combo box with Tab / Enter commit and Esc dismiss."""
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        comp = combo.completer()
        if comp:
            comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            popup = comp.popup()
            if popup:
                popup.setStyleSheet("""
                    QListView {
                        background-color: #0f172a;
                        color: #f8fafc;
                        selection-background-color: #0284c7;
                        selection-color: #ffffff;
                        border: 1px solid #334155;
                        border-radius: 4px;
                        padding: 4px;
                        font-size: 11px;
                    }
                """)
                if not getattr(popup, "_tab_filter_installed", False):
                    tab_filter = CompleterKeyFilter(combo, parent=popup)
                    popup.installEventFilter(tab_filter)
                    popup._tab_filter_installed = True

            if not getattr(comp, "_activated_connected", False):
                def _on_activated(text: str, cb=combo):
                    c_idx = cb.findText(text, Qt.MatchFlag.MatchFixedString)
                    if c_idx != -1:
                        cb.setCurrentIndex(c_idx)
                    cb.setEditText(text)
                    if cb.lineEdit():
                        cb.lineEdit().setText(text)
                    self._clear_field_error(cb)
                comp.activated.connect(_on_activated)
                comp._activated_connected = True

        if not getattr(combo, "_tab_filter_installed", False):
            tab_filter = CompleterKeyFilter(combo, parent=combo)
            combo.installEventFilter(tab_filter)
            combo._tab_filter_installed = True

        le = combo.lineEdit()
        if le:
            le.wheelEvent = lambda event: event.ignore()
            if hasattr(self, "_wheel_filter") and self._wheel_filter:
                le.installEventFilter(self._wheel_filter)
            if not getattr(le, "_tab_filter_installed", False):
                tab_filter = CompleterKeyFilter(combo, parent=le)
                le.installEventFilter(tab_filter)
                le._tab_filter_installed = True
            # Prevent auto-selection of entire text upon focus gain
            le.focusInEvent = lambda event, target=le: (
                QLineEdit.focusInEvent(target, event),
                QTimer.singleShot(0, target.deselect)
            )
            if not getattr(le, "_text_changed_connected", False):
                def _on_le_text_changed(txt, cb=combo):
                    self._clear_field_error(cb)
                le.textChanged.connect(_on_le_text_changed)
                le._text_changed_connected = True

    def refresh_reference_data(self):
        """Dynamically reload Manufacturer, Category, and Type data from repository without hardcoding."""
        curr_mfr = self.mfr_input.currentText()
        curr_cat = self.category_combo.currentText()
        curr_tech = self.tech_combo.currentText()

        self.mfr_input.blockSignals(True)
        self.category_combo.blockSignals(True)
        self.mfr_input.clear()
        self.category_combo.clear()

        if self.repository:
            try:
                for m in self.repository.get_all_manufacturers():
                    self.mfr_input.addItem(m.name)
            except Exception:
                pass

            try:
                for c in self.repository.get_all_categories():
                    self.category_combo.addItem(c.name)
            except Exception:
                pass

        self.mfr_input.setEditText(curr_mfr)
        self.category_combo.setEditText(curr_cat)
        self.mfr_input.blockSignals(False)
        self.category_combo.blockSignals(False)

        self._configure_combo_autocomplete(self.mfr_input)
        self._configure_combo_autocomplete(self.category_combo)

        # Refresh dependent types
        self._on_category_changed(curr_cat)
        if curr_tech:
            self.tech_combo.setEditText(curr_tech)

    def _load_reference_data(self):
        """Populate Manufacturer and Category combo boxes from repository if available."""
        self._configure_combo_autocomplete(self.mfr_input)
        self._configure_combo_autocomplete(self.category_combo)
        self._configure_combo_autocomplete(self.tech_combo)

        if not self.repository:
            return

        self.refresh_reference_data()

    def _on_category_changed(self, cat_name: str):
        """Refresh Type/Technology combo box dynamically filtered by the selected Category."""
        clean_cat = clean_display_string(cat_name)
        current_tech = clean_display_string(self.tech_combo.currentText())

        self.tech_combo.blockSignals(True)
        self.tech_combo.clear()

        if not self.repository or not clean_cat:
            if current_tech:
                self.tech_combo.setEditText(current_tech)
            else:
                self.tech_combo.setCurrentIndex(-1)
                self.tech_combo.setEditText("")
            self.tech_combo.blockSignals(False)
            self._configure_combo_autocomplete(self.tech_combo)
            return

        cat_rec = self.repository.get_category_by_name(clean_cat)
        valid_tech_names = []
        if cat_rec:
            try:
                types = self.repository.get_types_for_category(cat_rec.id)
                for t in types:
                    self.tech_combo.addItem(t.name)
                    valid_tech_names.append(t.name)
            except Exception:
                pass

        # Clear or revalidate an incompatible Type selection
        if current_tech and current_tech in valid_tech_names:
            self.tech_combo.setCurrentText(current_tech)
        elif not cat_rec:
            # User might be typing category name; do not erase their entered tech text prematurely
            self.tech_combo.setEditText(current_tech)
        else:
            self.tech_combo.setCurrentIndex(-1)
            self.tech_combo.setEditText("")

        self.tech_combo.blockSignals(False)
        self._configure_combo_autocomplete(self.tech_combo)

    def _on_add_manufacturer_clicked(self):
        """Explicitly add a new canonical manufacturer to SQLite reference data."""
        if not self.repository:
            return
        name, ok = QInputDialog.getText(self, "Add Manufacturer", "New Manufacturer Name:")
        if not ok or not name or not name.strip():
            return
        clean_name = clean_display_string(name)
        existing = self.repository.get_manufacturer_by_name(clean_name)
        if existing:
            self.mfr_input.setCurrentText(existing.name)
            return
        try:
            self.repository.add_manufacturer(clean_name)
            if self.mfr_input.findText(clean_name) == -1:
                self.mfr_input.addItem(clean_name)
            self.mfr_input.setCurrentText(clean_name)
        except Exception as e:
            QMessageBox.warning(self, "Error Adding Manufacturer", str(e))

    def _on_add_category_clicked(self):
        """Explicitly add a new canonical category to SQLite reference data."""
        if not self.repository:
            return
        name, ok = QInputDialog.getText(self, "Add Category", "New Category Name:")
        if not ok or not name or not name.strip():
            return
        clean_name = clean_display_string(name)
        existing = self.repository.get_category_by_name(clean_name)
        if existing:
            self.category_combo.setCurrentText(existing.name)
            return
        try:
            self.repository.add_category(clean_name)
            if self.category_combo.findText(clean_name) == -1:
                self.category_combo.addItem(clean_name)
            self.category_combo.setCurrentText(clean_name)
        except Exception as e:
            QMessageBox.warning(self, "Error Adding Category", str(e))

    def _on_add_type_clicked(self):
        """Explicitly add a new canonical type/technology associated with the selected category."""
        if not self.repository:
            return
        cat_name = clean_display_string(self.category_combo.currentText())
        if not cat_name:
            QMessageBox.warning(self, "Category Required", "Please select a Category before adding a Type / Technology.")
            return
        cat_rec = self.repository.get_category_by_name(cat_name)
        if not cat_rec:
            QMessageBox.warning(
                self,
                "Unknown Category",
                f"Category '{cat_name}' must be saved in reference data before adding types."
            )
            return
        name, ok = QInputDialog.getText(
            self, "Add Type / Technology", f"New Type for Category '{cat_name}':"
        )
        if not ok or not name or not name.strip():
            return
        clean_name = clean_display_string(name)
        if self.repository.validate_category_type(cat_name, clean_name):
            self.tech_combo.setCurrentText(clean_name)
            return
        try:
            self.repository.add_type(cat_rec.id, clean_name)
            if self.tech_combo.findText(clean_name) == -1:
                self.tech_combo.addItem(clean_name)
            self.tech_combo.setCurrentText(clean_name)
        except Exception as e:
            QMessageBox.warning(self, "Error Adding Type", str(e))

    def _load_vendor_choices(self) -> List[Tuple[str, str, str]]:
        if self.repository and hasattr(self.repository, "get_all_providers"):
            try:
                db_providers = self.repository.get_all_providers(include_inactive=False)
                if db_providers:
                    return [(p.provider_id, p.label, p.name) for p in db_providers]
            except Exception:
                pass
        return list(VENDOR_CHOICES)

    def _add_empty_link_row(self, link: Optional[SupplierLink] = None):
        row = SupplierLinkRow(
            link=link,
            combo_style=getattr(self, "_input_style", None),
            vendor_choices=self._load_vendor_choices(),
        )
        if hasattr(self, "_wheel_filter") and self._wheel_filter:
            row.vendor_combo.installEventFilter(self._wheel_filter)
            row.url_input.installEventFilter(self._wheel_filter)
        row.removeRequested.connect(self._remove_link_row)
        self.links_container.addWidget(row)
        self._link_rows.append(row)

    def _remove_link_row(self, row: SupplierLinkRow):
        if row in self._link_rows:
            self._link_rows.remove(row)
            self.links_container.removeWidget(row)
            row.deleteLater()

    def _clear_all_link_rows(self):
        for r in list(self._link_rows):
            self._link_rows.remove(r)
            self.links_container.removeWidget(r)
            r.deleteLater()

    def _populate_from_component(self, comp: InventoryProduct):
        self.mode = "edit"
        self.component = comp
        self.setWindowTitle(f"Edit Component — {comp.manufacturer} {comp.mpn}")
        self.title_lbl.setText("Edit Component")
        self.sub_lbl.setText(f"Update component parameters, physical stock, and supplier links for {comp.manufacturer} {comp.mpn}.")
        self.save_btn.setText("Save Changes")
        if hasattr(self, "_set_field_error"):
            self._set_field_error(self.mfr_input, False)
            self._set_field_error(self.category_combo, False)
            self._set_field_error(self.tech_combo, False)
        if hasattr(self, "validation_lbl"):
            self.validation_lbl.setText("")

        self.mfr_input.setCurrentText(comp.manufacturer)
        self.mpn_input.setText(comp.mpn)

        self.category_combo.blockSignals(True)
        self.category_combo.setCurrentText(comp.category)
        self.category_combo.blockSignals(False)

        self._on_category_changed(comp.category)
        self.tech_combo.setCurrentText(comp.type_technology)

        self.value_input.setText(comp.value)
        self.package_input.setText(comp.package)
        self.footprint_input.setText(comp.footprint)
        self.desc_input.setText(comp.description or "")
        self.qty_spin.setValue(int(comp.quantity_in_stock or 0))

        self._clear_all_link_rows()

        links = comp.supplier_links
        if not links and self.repository:
            try:
                links = tuple(self.repository.get_supplier_links(comp.id))
            except Exception:
                pass

        if links:
            for l in links:
                self._add_empty_link_row(l)

    def _populate_from_group(self, group: Any):
        if hasattr(group, "category") and group.category:
            self.category_combo.setCurrentText(group.category)
            self._on_category_changed(group.category)
        if hasattr(group, "type_technology") and group.type_technology:
            self.tech_combo.setCurrentText(group.type_technology)
        if hasattr(group, "value") and group.value:
            self.value_input.setText(group.value)
        if hasattr(group, "package") and group.package:
            self.package_input.setText(group.package)
        if hasattr(group, "footprint") and group.footprint:
            self.footprint_input.setText(group.footprint)

    def _on_switch_to_existing_component(self):
        """User clicked button to edit the detected existing duplicate component."""
        mfr = self.mfr_input.currentText().strip()
        mpn = self.mpn_input.text().strip()
        if not self.repository:
            return
        existing = self.repository.get_component_by_identity(mfr, mpn)
        if existing:
            self.duplicate_frame.setVisible(False)
            self.validation_lbl.setText("")
            self._populate_from_component(existing)

    def _collect_supplier_links(self) -> List[SupplierLink]:
        links: List[SupplierLink] = []
        for r in self._link_rows:
            l = r.get_link()
            if l:
                links.append(l)
        return links

    def _on_save_clicked(self):
        """Validates all inputs, enforces identity uniqueness, and persists via repository."""
        self.validation_lbl.setText("")
        self.duplicate_frame.setVisible(False)
        self._set_field_error(self.mfr_input, False)
        self._set_field_error(self.category_combo, False)
        self._set_field_error(self.tech_combo, False)

        mfr = clean_display_string(self.mfr_input.currentText())
        mpn = clean_display_string(self.mpn_input.text())
        cat = clean_display_string(self.category_combo.currentText())
        tech = clean_display_string(self.tech_combo.currentText())
        val = clean_display_string(self.value_input.text())
        raw_pkg = clean_display_string(self.package_input.text())
        pkg = normalize_package(raw_pkg)
        fp = clean_display_string(self.footprint_input.text())
        desc = clean_display_string(self.desc_input.text())
        qty = self.qty_spin.value()

        # 1. Field validation
        if not mfr or not mpn:
            self.validation_lbl.setText("Manufacturer and Part Number (MPN) are required fields.")
            if not mfr:
                self._set_field_error(self.mfr_input, True)
            return

        if not cat or not tech:
            self.validation_lbl.setText("Category and Type/Technology are required fields.")
            if not cat:
                self._set_field_error(self.category_combo, True)
            if not tech:
                self._set_field_error(self.tech_combo, True)
            return

        if not val or not pkg or not fp:
            self.validation_lbl.setText("Value, Package, and Footprint are required grouping fields.")
            return

        if qty < 0:
            self.validation_lbl.setText("Physical Quantity in Stock cannot be negative.")
            return

        # Canonical reference validation if repository has populated reference data
        if self.repository:
            # Validate Manufacturer against reference data
            has_mfr_ref = False
            try:
                mfrs = self.repository.get_all_manufacturers()
                has_mfr_ref = len(mfrs) > 0
            except Exception:
                has_mfr_ref = False

            if has_mfr_ref:
                mfr_rec = self.repository.get_manufacturer_by_name(mfr)
                if not mfr_rec:
                    self.validation_lbl.setText(
                        f"Manufacturer '{mfr}' is not in canonical reference data. Please select an existing manufacturer from Reference Data."
                    )
                    self._set_field_error(self.mfr_input, True)
                    return
                mfr = mfr_rec.name

            # Validate Category and Type
            has_ref = False
            try:
                cats = self.repository.get_all_categories()
                has_ref = len(cats) > 0
            except Exception:
                has_ref = False

            if has_ref:
                cat_rec = self.repository.get_category_by_name(cat)
                if not cat_rec:
                    self.validation_lbl.setText(
                        f"Category '{cat}' is not in canonical reference data. Please select an existing category from Reference Data."
                    )
                    self._set_field_error(self.category_combo, True)
                    return
                cat = cat_rec.name

                if not self.repository.validate_category_type(cat, tech):
                    self.validation_lbl.setText(
                        f"Type/Technology '{tech}' is not valid for category '{cat}'. Please select an existing type from Reference Data."
                    )
                    self._set_field_error(self.tech_combo, True)
                    return
                type_rec = self.repository.get_type_by_name(cat_rec.id, tech)
                if type_rec:
                    tech = type_rec.name

        supplier_links = self._collect_supplier_links()

        # 2. Duplicate pre-check
        if self.repository:
            existing = self.repository.get_component_by_identity(mfr, mpn)
            if self.mode == "create" and existing is not None:
                self._show_duplicate_alert(existing)
                return

            if self.mode == "edit" and existing is not None and existing.id != self.component.id:
                self.validation_lbl.setText(
                    f"Conflict: Another component with identity '{mfr} {mpn}' already exists (ID {existing.id})."
                )
                self._show_duplicate_alert(existing)
                return

        # 3. Save via repository
        try:
            if self.mode == "create":
                new_prod = InventoryProduct(
                    manufacturer=mfr,
                    mpn=mpn,
                    category=cat,
                    type_technology=tech,
                    package=pkg,
                    raw_package=raw_pkg,
                    footprint=fp,
                    value=val,
                    description=desc,
                    quantity_in_stock=qty,
                    supplier_links=tuple(supplier_links),
                )
                if self.repository:
                    self.saved_component = self.repository.create_component(
                        new_prod, supplier_links=supplier_links
                    )
                else:
                    self.saved_component = new_prod
            else:
                if self.repository:
                    self.saved_component = self.repository.update_component(
                        self.component.id,
                        manufacturer=mfr,
                        mpn=mpn,
                        category=cat,
                        type_technology=tech,
                        package=pkg,
                        raw_package=raw_pkg,
                        footprint=fp,
                        value=val,
                        description=desc,
                        quantity_in_stock=qty,
                        supplier_links=supplier_links,
                    )
                else:
                    self.saved_component = self.component

            self.accept()
        except ComponentConflictError as e:
            # Multi-layer defense: Caught at repo/database level
            if e.existing_component:
                self._show_duplicate_alert(e.existing_component)
            else:
                self.validation_lbl.setText(f"Conflict error: {e}")
        except ValidationError as e:
            self.validation_lbl.setText(f"Validation error: {e}")
        except ReferenceDataNotFoundError as e:
            self.validation_lbl.setText(f"Reference data error: {e}")
        except Exception as e:
            self.validation_lbl.setText(f"Failed to save component: {e}")

    def _show_duplicate_alert(self, existing: InventoryProduct):
        """Displays the duplicate warning banner with English message and existing record summary."""
        self.dup_title_lbl.setText("This component is already registered.")
        details_text = (
            f"Manufacturer: {existing.manufacturer}\n"
            f"Part Number (MPN): {existing.mpn}\n"
            f"Category / Type: {existing.category} / {existing.type_technology}\n"
            f"Value / Package: {existing.value} / {existing.package}\n"
            f"Current Stock: {existing.quantity_in_stock} units"
        )
        self.dup_details_lbl.setText(details_text)
        self.duplicate_frame.setVisible(True)
        if self.mode == "edit":
            self.validation_lbl.setText(f"Conflict: Identity '{existing.manufacturer} {existing.mpn}' is already in use by another component.")
        else:
            self.validation_lbl.setText("Registration blocked: Duplicate component identity detected.")
