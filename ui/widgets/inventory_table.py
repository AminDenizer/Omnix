from typing import Optional
from PyQt6.QtWidgets import (
    QTableWidget, QWidget, QVBoxLayout, QLabel, QFrame, QLineEdit, QStyledItemDelegate
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent, QFont


class EmptyStateOverlay(QWidget):
    """Clean, centered placeholder shown when table has no data or no search matches."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._is_filter_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)

        # Center card container
        self.card = QFrame()
        self.card.setObjectName("emptyStateCard")
        self.card.setMinimumWidth(480)
        self.card.setMaximumWidth(580)
        self.card.setStyleSheet(
            "QFrame#emptyStateCard {"
            "   background-color: rgba(15, 23, 42, 0.95);"
            "   border: 1px dashed rgba(56, 189, 248, 0.40);"
            "   border-radius: 12px;"
            "}"
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(8)

        # 1. Icon badge
        self.icon_lbl = QLabel("📊")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size: 40px; background: transparent; border: none;")
        card_layout.addWidget(self.icon_lbl)
        card_layout.addSpacing(4)

        # 2. Main Title
        self.title_lbl = QLabel("Inventory.xlsx Database Not Found")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f8fafc; background: transparent; border: none;"
        )
        card_layout.addWidget(self.title_lbl)

        # 3. Description / Guidance
        self.desc_lbl = QLabel("Please place 'Inventory.xlsx' in the application directory and press [F5] to reload.")
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none;"
        )
        card_layout.addWidget(self.desc_lbl)

        layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

    def set_state(self, is_filter_mode: bool, title: Optional[str] = None, desc: Optional[str] = None):
        self._is_filter_mode = is_filter_mode
        if title:
            self.icon_lbl.setText("🔍" if is_filter_mode else "📦")
            self.title_lbl.setText(title)
            self.desc_lbl.setText(desc or "")
        elif is_filter_mode:
            self.icon_lbl.setText("🔍")
            self.title_lbl.setText("No Matching Records Found")
            self.desc_lbl.setText("Try adjusting your search keywords or press [Esc] to clear.")
        else:
            self.icon_lbl.setText("📊")
            self.title_lbl.setText("Inventory.xlsx Database Not Found")
            self.desc_lbl.setText("Please place 'Inventory.xlsx' in the application directory and press [F5] to reload.")


class InventoryTableWidget(QTableWidget):
    """Dynamic table widget supporting sorting, empty state overlay, and responsive column distribution."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.empty_overlay = EmptyStateOverlay(self.viewport())
        self.empty_overlay.hide()
        self._min_column_widths = {}
        self._flexible_columns = []
        self._is_distributing_columns = False

    def configure_column_distribution(
        self,
        min_widths: dict,
        flexible_columns: Optional[list] = None,
    ):
        """Set base column widths and identify flexible columns that absorb extra viewport space."""
        self._min_column_widths = dict(min_widths)
        if flexible_columns is not None:
            self._flexible_columns = list(flexible_columns)
        else:
            self._flexible_columns = list(min_widths.keys())
        self.distribute_columns()

    def distribute_columns(self):
        """Distribute available viewport width across columns to prevent unused space on the right."""
        col_count = self.columnCount()
        if col_count == 0 or self._is_distributing_columns:
            return

        vp_width = self.viewport().width()
        if vp_width <= 50:
            return

        self._is_distributing_columns = True
        try:
            visible_cols = [c for c in range(col_count) if not self.isColumnHidden(c)]
            if not visible_cols:
                return

            base_widths = {}
            for c in visible_cols:
                base_widths[c] = self._min_column_widths.get(c, 100)

            total_base = sum(base_widths.values())
            flex_cols = [c for c in self._flexible_columns if c in visible_cols]
            if not flex_cols:
                flex_cols = list(visible_cols)

            if vp_width > total_base:
                excess = vp_width - total_base
                add_each = excess // len(flex_cols)
                rem = excess % len(flex_cols)

                for c in visible_cols:
                    extra = 0
                    if c in flex_cols:
                        idx_in_flex = flex_cols.index(c)
                        extra = add_each + (1 if idx_in_flex < rem else 0)
                    target_w = base_widths[c] + extra
                    if self.columnWidth(c) != target_w:
                        self.setColumnWidth(c, target_w)
            elif vp_width < total_base:
                deficit = total_base - vp_width
                sub_each = deficit // len(flex_cols)
                rem = deficit % len(flex_cols)
                for c in visible_cols:
                    shrink = 0
                    if c in flex_cols:
                        idx_in_flex = flex_cols.index(c)
                        shrink = sub_each + (1 if idx_in_flex < rem else 0)
                    target_w = max(30, base_widths[c] - shrink)
                    if self.columnWidth(c) != target_w:
                        self.setColumnWidth(c, target_w)
            else:
                for c in visible_cols:
                    target_w = base_widths[c]
                    if self.columnWidth(c) != target_w:
                        self.setColumnWidth(c, target_w)
        finally:
            self._is_distributing_columns = False

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.empty_overlay.setGeometry(0, 0, self.viewport().width(), self.viewport().height())
        win = self.window()
        if win and win.isMinimized():
            return
        if event.oldSize() == event.size():
            return
        self.distribute_columns()

    def update_empty_state(
        self,
        is_empty: bool,
        is_filter_active: bool = False,
        title: Optional[str] = None,
        desc: Optional[str] = None,
    ):
        """Show or hide the empty state placeholder overlay."""
        if is_empty:
            self.empty_overlay.set_state(is_filter_active, title=title, desc=desc)
            self.empty_overlay.setGeometry(0, 0, self.viewport().width(), self.viewport().height())
            self.empty_overlay.show()
        else:
            self.empty_overlay.hide()


class StockCellDelegate(QStyledItemDelegate):
    """
    Custom delegate for editable numeric cells (Min Stock & Target Stock).
    Provides a spacious, centered editor with comfortable height and rounded borders.
    """
    def createEditor(self, parent: QWidget, option, index):
        editor = QLineEdit(parent)
        editor.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setStyleSheet("""
            QLineEdit {
                background-color: #0c182e;
                color: #38bdf8;
                border: 2px solid #38bdf8;
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 13px;
                font-weight: bold;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
        """)
        return editor

    def updateEditorGeometry(self, editor: QWidget, option, index):
        rect = option.rect
        h = min(30, rect.height() - 4)
        y = rect.y() + (rect.height() - h) // 2
        w = rect.width() - 8
        x = rect.x() + 4
        editor.setGeometry(x, y, w, h)

