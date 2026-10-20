"""
Focused test suite for OMNIX Frameless Window Resize Hit-Testing and Cursor Management.

Verifies Task C:
1. Points inside the bottom resize margin are classified correctly.
2. Points inside the bottom-left and bottom-right resize corners are classified correctly.
3. Points safely inside the central content area are not classified as resize boundaries.
4. Entering the central area from the bottom edge restores the normal cursor immediately.
5. A normal checkbox region is not incorrectly classified as a resize boundary.
6. Valid bottom-edge and corner resizing triggers system resize without being blocked by child widgets.
7. Existing title-bar and window-control behavior remains intact.
"""

import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QAbstractButton
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QMouseEvent

from ui.main_window import MainWindow
from core.inventory import resolve_inventory_database_path


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_window(qapp):
    db_path = resolve_inventory_database_path()
    with patch("PyQt6.QtCore.QTimer.singleShot"):
        win = MainWindow(default_file=db_path)
        win.resize(1000, 700)
        win.show()
        qapp.processEvents()
    yield win
    win._is_force_closing = True
    win.close()


class TestWindowResizeCursor:
    """Task C verification suite for frameless window cursor and resize boundaries."""

    def test_case_01_bottom_margin_hit_testing(self, test_window):
        win = test_window
        w = win.width()
        h = win.height()

        # Points on the bottom margin (within 6px)
        p_edge = QPoint(w // 2, h - 2)
        assert win._get_resize_edge(p_edge) == Qt.Edge.BottomEdge

        p_edge_boundary = QPoint(w // 2, h - 6)
        assert win._get_resize_edge(p_edge_boundary) == Qt.Edge.BottomEdge

    def test_case_02_bottom_corners_hit_testing(self, test_window):
        win = test_window
        w = win.width()
        h = win.height()

        # Bottom-left corner
        p_bl = QPoint(2, h - 2)
        assert win._get_resize_edge(p_bl) == (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge)

        # Bottom-right corner
        p_br = QPoint(w - 2, h - 2)
        assert win._get_resize_edge(p_br) == (Qt.Edge.BottomEdge | Qt.Edge.RightEdge)

    def test_case_03_central_content_area_not_classified_as_resize_boundary(self, test_window):
        win = test_window
        w = win.width()
        h = win.height()

        # Safely inside central content area
        assert win._get_resize_edge(QPoint(w // 2, h // 2)) is None

        # Inside status bar body above the 6px margin
        assert win._get_resize_edge(QPoint(w // 2, h - 15)) is None

    def test_case_04_entering_central_area_from_bottom_edge_restores_cursor_immediately(self, test_window, qapp):
        win = test_window
        w = win.width()
        h = win.height()

        # Step 1: Simulate mouse moving at bottom edge (y = h - 2)
        edge_pt = QPoint(w // 2, h - 2)
        gpos_edge = win.mapToGlobal(edge_pt)
        ev_edge = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(edge_pt),
            QPointF(gpos_edge),
            QPointF(gpos_edge),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(win.statusBar(), ev_edge)

        assert win._resize_edge == Qt.Edge.BottomEdge
        assert win.cursor().shape() == Qt.CursorShape.SizeVerCursor

        # Step 2: Simulate mouse moving up into the central area (y = h - 30)
        inner_pt = QPoint(w // 2, h - 30)
        gpos_inner = win.mapToGlobal(inner_pt)
        ev_inner = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(inner_pt),
            QPointF(gpos_inner),
            QPointF(gpos_inner),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(win.centralWidget(), ev_inner)

        # MUST immediately restore normal cursor and clear resize state
        assert win._resize_edge is None
        assert win.cursor().shape() == Qt.CursorShape.ArrowCursor

    def test_case_05_checkbox_region_not_classified_as_resize_boundary(self, test_window, qapp):
        win = test_window
        chk = win.side_stock_policy_enabled_chk
        assert isinstance(chk, QCheckBox)

        # Get checkbox global position and map to window
        chk_center_global = chk.mapToGlobal(QPoint(chk.width() // 2, chk.height() // 2))
        chk_pos_in_win = win.mapFromGlobal(chk_center_global)

        # Checkbox position must NOT be classified as a resize edge
        assert win._get_resize_edge(chk_pos_in_win) is None

        # Moving mouse over checkbox should keep normal arrow cursor
        ev_chk = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(chk.width() // 2, chk.height() // 2),
            QPointF(chk_center_global),
            QPointF(chk_center_global),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(chk, ev_chk)

        assert win._resize_edge is None
        assert chk.cursor().shape() == Qt.CursorShape.ArrowCursor
        assert win.cursor().shape() == Qt.CursorShape.ArrowCursor

    def test_case_06_bottom_edge_and_corner_resizing_triggers_system_resize(self, test_window, qapp):
        win = test_window
        w = win.width()
        h = win.height()

        handle = win.windowHandle()
        assert handle is not None

        with patch.object(handle, "startSystemResize") as mock_resize:
            # Bottom edge click
            edge_pt = QPoint(w // 2, h - 2)
            gpos_edge = win.mapToGlobal(edge_pt)
            ev_press = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(edge_pt),
                QPointF(gpos_edge),
                QPointF(gpos_edge),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            qapp.sendEvent(win.statusBar(), ev_press)

            mock_resize.assert_called_with(Qt.Edge.BottomEdge)

        with patch.object(handle, "startSystemResize") as mock_resize_corner:
            # Bottom-right corner click
            corner_pt = QPoint(w - 2, h - 2)
            gpos_corner = win.mapToGlobal(corner_pt)
            ev_corner = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(corner_pt),
                QPointF(gpos_corner),
                QPointF(gpos_corner),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            qapp.sendEvent(win.statusBar(), ev_corner)

            mock_resize_corner.assert_called_with(Qt.Edge.BottomEdge | Qt.Edge.RightEdge)

    def test_case_07_title_bar_and_window_controls_intact(self, test_window, qapp):
        win = test_window
        btn_close = win.title_bar.btn_close
        assert isinstance(btn_close, QAbstractButton)

        # Title bar buttons must NOT be intercepted as window resize
        handle = win.windowHandle()
        with patch.object(handle, "startSystemResize") as mock_resize:
            btn_center = btn_close.mapToGlobal(QPoint(btn_close.width() // 2, btn_close.height() // 2))
            ev_btn = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(btn_close.width() // 2, btn_close.height() // 2),
                QPointF(btn_center),
                QPointF(btn_center),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            qapp.sendEvent(btn_close, ev_btn)

            # Close button must not trigger resize
            assert not mock_resize.called
