"""
Omnix UI — Custom Desktop Window Title Bar
Governing Requirement: Clean Native Title Bar with 'OMNIX | Settings ▾' Menu

Provides a top-level custom title bar for the application window containing:
- Application branding text 'OMNIX'.
- Subtle separator '|'.
- Navigation Toggle hamburger button.
- Modern window management controls (Minimize, Maximize / Restore, Close) with clean vector icons.
- Native system window dragging via startSystemMove() and double-click maximize toggle.
"""

from typing import Optional
import os
from PyQt6.QtCore import Qt, QPoint, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QMouseEvent, QFont, QColor, QAction, QPainter, QPen
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QMenu,
    QApplication,
    QMainWindow,
)


class CaptionButton(QToolButton):
    """
    Modern minimal line-based window caption button:
    - Minimize: crisp horizontal stroke (10px).
    - Maximize: crisp square frame (10x10px).
    - Restore: dual overlapping square frames (distinct from Maximize).
    - Close: crisp diagonal cross (10x10px) with restrained dark crimson hover.
    Provides accessible naming, zero tooltips, and external hover state control for Win32 DWM.
    """

    def __init__(self, role: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.role = role  # "minimize", "maximize", "restore", "close"
        self._is_hovered = False
        self._is_pressed = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("")

        if role == "close":
            self.setObjectName("titleBarCloseBtn")
            self.setFixedSize(46, 36)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif role == "minimize":
            self.setObjectName("titleBarMinimizeBtn")
            self.setFixedSize(40, 36)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setObjectName("titleBarMaximizeBtn")
            self.setFixedSize(40, 36)
            self.setCursor(Qt.CursorShape.ArrowCursor)

        self._update_accessibility()

    def set_role(self, role: str):
        """Update button role (e.g. between maximize and restore)."""
        if self.role != role:
            self.role = role
            self._update_accessibility()
            self.update()

    def _update_accessibility(self):
        names = {
            "minimize": "Minimize",
            "maximize": "Maximize",
            "restore": "Restore Down",
            "close": "Close",
        }
        self.setAccessibleName(names.get(self.role, ""))

    def text(self) -> str:
        """Standard Unicode glyph fallback for backward compatibility with tests."""
        symbols = {
            "minimize": "—",
            "maximize": "🗖",
            "restore": "🗗",
            "close": "✕",
        }
        return symbols.get(self.role, "")

    def setHovered(self, hovered: bool):
        """Allow native hit-testing to drive hover styling (e.g. for HTMAXBUTTON)."""
        if self._is_hovered != hovered:
            self._is_hovered = hovered
            self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        is_hover = self._is_hovered or self.underMouse()
        is_press = self._is_pressed or self.isDown()

        # 1. Background rendering
        if self.role == "close":
            if is_press:
                painter.fillRect(0, 0, w, h, QColor("#991b1b"))  # Restrained dark crimson pressed
            elif is_hover:
                painter.fillRect(0, 0, w, h, QColor("#c42b1c"))  # Modern Windows 11 restrained close hover
        else:
            if is_press:
                painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 36))
            elif is_hover:
                painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 20))

        # 2. Icon Stroke Color
        if is_hover or is_press or (self.role == "close" and is_hover):
            icon_color = QColor("#ffffff")
        else:
            icon_color = QColor("#94a3b8")

        pen = QPen(icon_color, 1.0)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)

        # 3. Vector Icon Geometry
        if self.role == "minimize":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy))

        elif self.role == "maximize":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.drawRect(QRectF(cx - 5.0, cy - 5.0, 10.0, 10.0))

        elif self.role == "restore":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            # Back square (top-right, showing top & right edges)
            painter.drawLine(QPointF(cx - 2.0, cy - 5.0), QPointF(cx + 5.0, cy - 5.0))
            painter.drawLine(QPointF(cx + 5.0, cy - 5.0), QPointF(cx + 5.0, cy + 2.0))
            painter.drawLine(QPointF(cx + 3.0, cy + 2.0), QPointF(cx + 5.0, cy + 2.0))
            painter.drawLine(QPointF(cx - 2.0, cy - 5.0), QPointF(cx - 2.0, cy - 3.0))

            # Front square (bottom-left)
            front_rect = QRectF(cx - 5.0, cy - 3.0, 8.0, 8.0)
            # Fill front square with current background color to cleanly occlude the back square
            if self.role == "close":
                bg_color = QColor("#c42b1c") if is_hover else QColor("#0b101b")
            else:
                bg_color = QColor(255, 255, 255, 20) if is_hover else QColor("#0b101b")
            painter.fillRect(front_rect, bg_color)
            painter.drawRect(front_rect)

        elif self.role == "close":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen.setWidthF(1.1)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            painter.drawLine(QPointF(cx - 4.5, cy + 4.5), QPointF(cx + 4.5, cy - 4.5))

        painter.end()


class WindowTitleBar(QFrame):
    """
    Top-level desktop window title bar hosting 'OMNIX | Settings ▾' menu alongside
    minimize, maximize/restore, and close controls.
    """

    sidebarToggleRequested = pyqtSignal()

    def __init__(self, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.setObjectName("customTitleBar")
        self.setFixedHeight(36)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._drag_pos: Optional[QPoint] = None

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Branding: OMNIX Wordmark
        self.title_lbl = QLabel(
            "<span style='font-weight: 800; font-size: 11px; color: #f1f5f9; letter-spacing: 0.8px;'>OMNIX</span>"
        )
        self.title_lbl.setObjectName("titleBarBrandLabel")
        self.title_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.title_lbl.setFont(QFont("Segoe UI", 9))
        layout.addWidget(self.title_lbl)

        # Subtle separator '|'
        self.sep = QLabel("<span style='color: #475569; font-size: 11px;'>|</span>")
        self.sep.setObjectName("titleBarSeparator")
        layout.addWidget(self.sep)

        # 2. Transparent borderless hamburger control: [OMNIX wordmark] | [Hamburger / Navigation Toggle]
        hamburger_style = """
            QPushButton#hamburgerBtn {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                font-size: 15px;
                font-weight: bold;
                padding: 1px 7px;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }
            QPushButton#hamburgerBtn:hover {
                background-color: rgba(255, 255, 255, 0.08);
                color: #38bdf8;
            }
            QPushButton#hamburgerBtn:pressed {
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }
            QPushButton#hamburgerBtn:focus {
                outline: none;
                color: #38bdf8;
            }
        """

        self.hamburger_btn = QPushButton("☰")
        self.hamburger_btn.setObjectName("hamburgerBtn")
        self.hamburger_btn.setToolTip("Toggle Navigation Sidebar (Ctrl+B)")
        self.hamburger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hamburger_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.hamburger_btn.setStyleSheet(hamburger_style)
        self.hamburger_btn.clicked.connect(self.sidebarToggleRequested.emit)
        layout.addWidget(self.hamburger_btn)

        layout.addStretch(1)

        # 3. Standard Window Controls (Rightmost)
        self.btn_minimize = CaptionButton("minimize", parent=self)
        self.btn_minimize.clicked.connect(self._on_minimize_clicked)
        layout.addWidget(self.btn_minimize)

        self.btn_maximize = CaptionButton("maximize", parent=self)
        self.btn_maximize.clicked.connect(self._on_maximize_clicked)
        layout.addWidget(self.btn_maximize)

        self.btn_close = CaptionButton("close", parent=self)
        self.btn_close.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.btn_close)

        self.setStyleSheet("""
            QFrame#customTitleBar {
                background-color: #0b101b;
                border-bottom: 1px solid #1e293b;
            }
        """)

    def _on_minimize_clicked(self):
        win = self.window()
        if win:
            win.showMinimized()

    def _on_maximize_clicked(self):
        self._toggle_maximize()

    def _on_close_clicked(self):
        win = self.window()
        if win:
            win.close()

    def _toggle_maximize(self):
        win = self.window()
        if not win:
            return
        if win.isMaximized():
            win.showNormal()
            self.update_maximize_state(False)
        else:
            win.showMaximized()
            self.update_maximize_state(True)

    def update_maximize_state(self, is_maximized: bool):
        """Update maximize button state and glyph according to window state."""
        if is_maximized:
            self.btn_maximize.set_role("restore")
        else:
            self.btn_maximize.set_role("maximize")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win:
                # Use native system move if windowHandle is available
                handle = win.windowHandle()
                if handle and hasattr(handle, "startSystemMove") and not win.isMaximized():
                    handle.startSystemMove()
                    event.accept()
                    return
                self._drag_pos = event.globalPosition().toPoint() - win.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win and not win.isMaximized():
                win.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
