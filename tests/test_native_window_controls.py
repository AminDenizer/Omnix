"""
Tests for Additional Requirement B: Native Windows Controls & Window Behavior.

Validates that:
1. Window minimize button invokes showMinimized() on the window.
2. Window maximize/restore toggle button toggles window between maximized and normal.
3. changeEvent(WindowStateChange) synchronizes title bar glyph and tooltip.
4. Title bar double click toggles maximize state.
5. Title bar close button invokes close() on the window.
"""

from unittest.mock import MagicMock, patch
import sys
import ctypes
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt, QPoint
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.main_window import MainWindow
from ui.widgets.title_bar import WindowTitleBar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestNativeWindowControlsRequirementB:

    def test_title_bar_controls_exist_and_styled(self, qapp):
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)

        assert tb.btn_minimize is not None
        assert tb.btn_maximize is not None
        assert tb.btn_close is not None

        # Modern vector caption buttons have zero tooltips per Requirement A
        assert tb.btn_minimize.toolTip() == ""
        assert tb.btn_maximize.toolTip() == ""
        assert tb.btn_close.toolTip() == ""

        # Accessible names are set for screen reader and keyboard support
        assert tb.btn_minimize.accessibleName() == "Minimize"
        assert tb.btn_maximize.accessibleName() == "Maximize"
        assert tb.btn_close.accessibleName() == "Close"

        # Roles match requirements
        assert tb.btn_minimize.role == "minimize"
        assert tb.btn_maximize.role == "maximize"
        assert tb.btn_close.role == "close"

    def test_minimize_button_action(self, qapp):
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)
        with patch.object(win, "showMinimized") as mock_min:
            tb.btn_minimize.click()
            assert mock_min.called

    def test_maximize_restore_toggle_actions(self, qapp):
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)

        # 1. When window is normal, clicking maximize calls showMaximized
        with patch.object(win, "isMaximized", return_value=False), \
             patch.object(win, "showMaximized") as mock_max:
            tb.btn_maximize.click()
            assert mock_max.called
            assert tb.btn_maximize.role == "restore"
            assert tb.btn_maximize.accessibleName() == "Restore Down"
            assert tb.btn_maximize.toolTip() == ""

        # 2. When window is maximized, clicking maximize calls showNormal
        with patch.object(win, "isMaximized", return_value=True), \
             patch.object(win, "showNormal") as mock_norm:
            tb.btn_maximize.click()
            assert mock_norm.called
            assert tb.btn_maximize.role == "maximize"
            assert tb.btn_maximize.accessibleName() == "Maximize"
            assert tb.btn_maximize.toolTip() == ""

    def test_title_bar_double_click_toggles_maximize(self, qapp):
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)

        with patch.object(win, "isMaximized", return_value=False), \
             patch.object(win, "showMaximized") as mock_max:
            event = QMouseEvent(
                QEvent.Type.MouseButtonDblClick,
                QPointF(50, 10),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            tb.mouseDoubleClickEvent(event)
            assert mock_max.called

    def test_close_button_action(self, qapp):
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)
        with patch.object(win, "close") as mock_close:
            tb.btn_close.click()
            assert mock_close.called

    def test_main_window_window_state_change_event_synchronization(self, qapp):
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            qapp.processEvents()
            try:
                # Simulate WindowStateChange event when window becomes maximized
                with patch.object(win, "isMaximized", return_value=True):
                    evt = QEvent(QEvent.Type.WindowStateChange)
                    win.changeEvent(evt)
                    assert win.title_bar.btn_maximize.role == "restore"
                    assert win.title_bar.btn_maximize.accessibleName() == "Restore Down"
                    assert win.title_bar.btn_maximize.toolTip() == ""

                # Simulate WindowStateChange event when window becomes restored
                with patch.object(win, "isMaximized", return_value=False):
                    evt = QEvent(QEvent.Type.WindowStateChange)
                    win.changeEvent(evt)
                    assert win.title_bar.btn_maximize.role == "maximize"
                    assert win.title_bar.btn_maximize.accessibleName() == "Maximize"
                    assert win.title_bar.btn_maximize.toolTip() == ""
            finally:
                win._is_force_closing = True
                win.close()

    def test_window_geometry_persistence_across_sessions(self, qapp):
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")
        qt_settings.remove("geometry")
        qt_settings.remove("isMaximized")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win1 = MainWindow()
            win1._allow_test_geometry_save = True
            try:
                win1.resize(1100, 700)
                win1.move(150, 150)
                qapp.processEvents()

                # Trigger close and save
                win1._is_force_closing = True
                win1.close()
                saved_geom = qt_settings.value("geometry")
                assert saved_geom is not None

                # Create second window and verify restored geometry
                win2 = MainWindow()
                try:
                    qapp.processEvents()
                    assert win2.width() == 1100
                    assert win2.height() == 700
                finally:
                    win2._is_force_closing = True
                    win2.close()
            finally:
                qt_settings.remove("geometry")
                qt_settings.remove("isMaximized")

    def test_minimized_window_does_not_overwrite_saved_geometry(self, qapp):
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")
        qt_settings.setValue("geometry", b"valid_saved_geometry")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            win._allow_test_geometry_save = True
            try:
                with patch.object(win, "isMinimized", return_value=True):
                    win._is_force_closing = True
                    win.close()
                    # Value in settings should not be overwritten
                    assert qt_settings.value("geometry") == b"valid_saved_geometry"
            finally:
                win._is_force_closing = True
                win.close()
                qt_settings.remove("geometry")

    def test_offscreen_geometry_safely_repositioned(self, qapp):
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            try:
                # Move way off-screen
                win.setGeometry(50000, 50000, 1000, 700)
                saved = win.saveGeometry()
                qt_settings.setValue("geometry", saved)

                # Restoring should detect off-screen and reposition onto available screen
                win._restore_window_geometry()
                screens = qapp.screens()
                if screens:
                    primary = qapp.primaryScreen()
                    avail = primary.availableGeometry()
                    frame = win.frameGeometry()
                    assert avail.intersects(frame)
                    assert frame.x() < 50000
            finally:
                win._is_force_closing = True
                qt_settings.remove("geometry")

    def test_corrupt_saved_geometry_graceful_fallback(self, qapp):
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")
        qt_settings.setValue("geometry", b"not_a_valid_qbytearray_geometry")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            try:
                screens = qapp.screens()
                if screens:
                    primary = qapp.primaryScreen()
                    avail = primary.availableGeometry()
                    frame = win.frameGeometry()
                    assert avail.intersects(frame)
            finally:
                win._is_force_closing = True
                win.close()
                qt_settings.remove("geometry")





@pytest.mark.skipif(sys.platform != "win32", reason="Win32 DWM Native tests run on Windows")
class TestWin32DwmNativeWindowHandler:

    def test_setup_native_window_instantiates_handler(self, qapp):
        win = QMainWindow()
        win.resize(1000, 700)
        from ui.native_window import setup_native_window, NativeWindowHandler
        handler = setup_native_window(win)
        assert handler is not None
        assert isinstance(handler, NativeWindowHandler)
        assert handler.min_width == 960
        assert handler.min_height == 620
        win.close()

    def test_wm_nccalcsize_handling(self, qapp):
        win = QMainWindow()
        win.resize(1000, 700)
        from ui.native_window import NativeWindowHandler, WM_NCCALCSIZE
        handler = NativeWindowHandler(win)

        # Create synthetic MSG
        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCCALCSIZE
        msg.wParam = 1
        msg.lParam = 0

        # Pass address of msg
        handled, result = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert result == 0
        win.close()

    def test_wm_nchittest_corner_and_edges(self, qapp):
        from ui.native_window import (
            NativeWindowHandler, WM_NCHITTEST,
            HTTOPLEFT, HTBOTTOMRIGHT, HTLEFT, HTRIGHT, HTTOP, HTBOTTOM, HTCLIENT
        )
        win = QMainWindow()
        win.resize(1000, 700)
        win.show()
        qapp.processEvents()

        handler = NativeWindowHandler(win, border_margin=8)

        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCHITTEST

        dpr = win.devicePixelRatio()

        # Top-left corner: physical screen pos corresponding to (2, 2) in win
        pt_tl = win.mapToGlobal(win.rect().topLeft())
        screen_x = int((pt_tl.x() + 2) * dpr)
        screen_y = int((pt_tl.y() + 2) * dpr)
        msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == HTTOPLEFT

        # Bottom-right corner: (w - 2, h - 2)
        pt_br = win.mapToGlobal(win.rect().bottomRight())
        screen_x = int((pt_br.x() - 2) * dpr)
        screen_y = int((pt_br.y() - 2) * dpr)
        msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == HTBOTTOMRIGHT

        win.close()

    def test_wm_nchittest_titlebar_maximize_button_and_caption(self, qapp):
        from ui.native_window import (
            NativeWindowHandler, WM_NCHITTEST,
            HTMAXBUTTON, HTCAPTION, HTCLIENT
        )
        from ui.widgets.title_bar import WindowTitleBar

        win = QMainWindow()
        win.resize(1000, 700)
        tb = WindowTitleBar(parent=win)
        win.title_bar = tb
        win.setMenuWidget(tb)
        win.show()
        qapp.processEvents()

        handler = NativeWindowHandler(win, border_margin=8)
        dpr = win.devicePixelRatio()

        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCHITTEST

        # Over maximize button
        max_btn = tb.btn_maximize
        btn_center_in_win = tb.mapTo(win, max_btn.geometry().center())
        btn_center_global = win.mapToGlobal(btn_center_in_win)
        screen_x = int(btn_center_global.x() * dpr)
        screen_y = int(btn_center_global.y() * dpr)
        msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == HTMAXBUTTON

        # Over empty space in title bar (between hamburger and right buttons)
        empty_in_win = tb.mapTo(win, QPoint(200, 18))
        empty_global = win.mapToGlobal(empty_in_win)
        screen_x = int(empty_global.x() * dpr)
        screen_y = int(empty_global.y() * dpr)
        msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == HTCAPTION

        # Over close button: should return HTCLIENT so Qt handles click/hover
        close_btn = tb.btn_close
        close_center_in_win = tb.mapTo(win, close_btn.geometry().center())
        close_center_global = win.mapToGlobal(close_center_in_win)
        screen_x = int(close_center_global.x() * dpr)
        screen_y = int(close_center_global.y() * dpr)
        msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == HTCLIENT

        win.close()

    def test_wm_getminmaxinfo_enforces_track_size(self, qapp):
        from ui.native_window import (
            NativeWindowHandler, WM_GETMINMAXINFO, MINMAXINFO
        )
        win = QMainWindow()
        win.resize(1000, 700)
        handler = NativeWindowHandler(win, min_width=960, min_height=620)
        dpr = win.devicePixelRatio()

        mmi = MINMAXINFO()
        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_GETMINMAXINFO
        msg.lParam = ctypes.addressof(mmi)

        handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
        assert handled is True
        assert res == 0
        # Windows 11 Snap Layouts specification requires ptMinTrackSize to accommodate
        # fractional screen zones (halves, thirds, quarters) per Microsoft guidelines.
        assert mmi.ptMinTrackSize.x == int(handler.min_track_width * dpr)
        assert mmi.ptMinTrackSize.y == int(handler.min_track_height * dpr)
        win.close()

    def test_wm_nclbuttonup_toggles_maximize_on_htmaxbutton(self, qapp):
        from ui.native_window import (
            NativeWindowHandler, WM_NCLBUTTONUP, HTMAXBUTTON
        )
        from ui.widgets.title_bar import WindowTitleBar

        win = QMainWindow()
        tb = WindowTitleBar(parent=win)
        win.title_bar = tb

        handler = NativeWindowHandler(win)

        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCLBUTTONUP
        msg.wParam = HTMAXBUTTON

        with patch.object(tb, "_toggle_maximize") as mock_toggle:
            handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
            assert handled is True
            assert res == 0
            assert mock_toggle.called
        win.close()

    def test_main_window_native_show_maximized_and_show_normal_agreement(self, qapp):
        from ui.main_window import MainWindow
        import ctypes
        user32 = ctypes.windll.user32

        with patch.object(MainWindow, "_check_startup_shortages"), patch("PyQt6.QtCore.QTimer.singleShot"):
            win = MainWindow()
            win.resize(1000, 700)
            win.show()
            qapp.processEvents()

            hwnd = int(win.winId())
            init_w = win.width()
            init_h = win.height()

            # Maximize
            win.showMaximized()
            qapp.processEvents()
            assert win.isMaximized() is True
            assert bool(user32.IsZoomed(hwnd)) is True
            assert win.title_bar.btn_maximize.text() == "\U0001f5d7"

            # Restore
            win.showNormal()
            qapp.processEvents()
            assert win.isMaximized() is False
            assert bool(user32.IsZoomed(hwnd)) is False
            assert win.title_bar.btn_maximize.text() == "\U0001f5d6"
            assert abs(win.width() - init_w) <= 2
            assert abs(win.height() - init_h) <= 2

            # Title bar button click toggle
            win.title_bar.btn_maximize.click()
            qapp.processEvents()
            assert win.isMaximized() is True
            assert bool(user32.IsZoomed(hwnd)) is True

            win.title_bar.btn_maximize.click()
            qapp.processEvents()
            assert win.isMaximized() is False
            assert bool(user32.IsZoomed(hwnd)) is False

            # Verify minimize still works as before
            win.title_bar.btn_minimize.click()
            qapp.processEvents()
            assert win.isMinimized() is True
            assert bool(user32.IsIconic(hwnd)) is True

            win.showNormal()
            qapp.processEvents()
            assert win.isMinimized() is False

            win._is_force_closing = True
            win.close()
    def test_wm_nchittest_maximize_button_100_percent_coverage(self, qapp):
        """Confirm that 100% of maximize button (including top edge y=0) returns HTMAXBUTTON."""
        from ui.native_window import NativeWindowHandler, WM_NCHITTEST, HTMAXBUTTON
        from ui.widgets.title_bar import WindowTitleBar

        win = QMainWindow()
        win.resize(1000, 700)
        tb = WindowTitleBar(parent=win)
        win.title_bar = tb
        win.setMenuWidget(tb)
        win.show()
        qapp.processEvents()

        handler = NativeWindowHandler(win, border_margin=8)
        dpr = win.devicePixelRatio()
        btn = tb.btn_maximize

        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCHITTEST

        # Test corners and center of btn_maximize
        test_points = [
            QPoint(0, 0),                       # Top-left corner
            QPoint(btn.width() - 1, 0),         # Top-right corner
            QPoint(btn.width() // 2, 0),        # Top edge center
            QPoint(btn.width() // 2, btn.height() // 2),  # Center
            QPoint(0, btn.height() - 1),        # Bottom-left corner
            QPoint(btn.width() - 1, btn.height() - 1),    # Bottom-right corner
        ]

        for pt in test_points:
            gp = btn.mapToGlobal(pt)
            screen_x = int(round(gp.x() * dpr))
            screen_y = int(round(gp.y() * dpr))
            msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)
            handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
            assert handled is True
            assert res == HTMAXBUTTON, f"Failed at button offset {pt}: got {res} instead of HTMAXBUTTON (9)"

        win.close()

    def test_wm_nchittest_close_button_never_swallowed_by_httop(self, qapp):
        """Confirm that top and right edges of close button return HTCLIENT for clean clicking."""
        from ui.native_window import NativeWindowHandler, WM_NCHITTEST, HTCLIENT
        from ui.widgets.title_bar import WindowTitleBar

        win = QMainWindow()
        win.resize(1000, 700)
        tb = WindowTitleBar(parent=win)
        win.title_bar = tb
        win.setMenuWidget(tb)
        win.show()
        qapp.processEvents()

        handler = NativeWindowHandler(win, border_margin=8)
        dpr = win.devicePixelRatio()
        btn = tb.btn_close

        from ctypes.wintypes import MSG
        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCHITTEST

        # Test top edge and right edge of close button
        test_points = [
            QPoint(0, 0),
            QPoint(btn.width() - 1, 0),
            QPoint(btn.width() // 2, 0),
            QPoint(btn.width() - 1, btn.height() // 2),
        ]

        for pt in test_points:
            gp = btn.mapToGlobal(pt)
            screen_x = int(round(gp.x() * dpr))
            screen_y = int(round(gp.y() * dpr))
            msg.lParam = (screen_y << 16) | (screen_x & 0xFFFF)
            handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
            assert handled is True
            assert res == HTCLIENT, f"Failed at close button offset {pt}: got {res} instead of HTCLIENT (1)"

        win.close()

    def test_fresh_startup_centering_within_available_geometry(self, qapp):
        """Confirm that a fresh startup with no saved geometry centers within availableGeometry."""
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")
        qt_settings.remove("geometry")
        qt_settings.remove("isMaximized")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            try:
                win.show()
                qapp.processEvents()
                avail = qapp.primaryScreen().availableGeometry()
                frame = win.geometry()
                expected_x = avail.x() + max(0, (avail.width() - frame.width()) // 2)
                expected_y = avail.y() + max(0, (avail.height() - frame.height()) // 2)
                assert frame.x() == expected_x
                assert frame.y() == expected_y
                assert frame.right() <= avail.right()
                assert frame.bottom() <= avail.bottom()
            finally:
                win._is_force_closing = True
                win.close()
                qt_settings.remove("geometry")
                qt_settings.remove("isMaximized")

    def test_startup_geometry_restoration_clamps_to_work_area(self, qapp):
        """Confirm that if saved geometry hung off-screen, startup clamps it so all corners fit within availableGeometry."""
        from PyQt6.QtCore import QSettings
        qt_settings = QSettings("Omnix", "Omnix")
        qt_settings.remove("geometry")
        qt_settings.remove("isMaximized")

        with patch.object(MainWindow, "_check_startup_shortages"):
            win1 = MainWindow()
            try:
                # Save an off-center geometry that extends beyond typical screen bounds
                win1.setGeometry(1200, 800, 1000, 700)
                saved = win1.saveGeometry()
                qt_settings.setValue("geometry", saved)
                qt_settings.setValue("isMaximized", False)

                win2 = MainWindow()
                try:
                    win2.show()
                    qapp.processEvents()
                    avail = qapp.primaryScreen().availableGeometry()
                    geo = win2.geometry()
                    # All corners must be within work area
                    assert geo.left() >= avail.left()
                    assert geo.top() >= avail.top()
                    assert geo.right() <= avail.right() + 1
                    assert geo.bottom() <= avail.bottom() + 1
                finally:
                    win2._is_force_closing = True
                    win2.close()
            finally:
                win1._is_force_closing = True
                win1.close()
                qt_settings.remove("geometry")
                qt_settings.remove("isMaximized")

    def test_caption_button_tooltip_removal_on_all_four_states(self, qapp):
        """Verify that tooltips are completely removed across all 4 caption states."""
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)

        # Minimize
        assert tb.btn_minimize.toolTip() == ""
        assert tb.btn_minimize.accessibleName() == "Minimize"

        # Maximize (normal)
        assert tb.btn_maximize.role == "maximize"
        assert tb.btn_maximize.toolTip() == ""
        assert tb.btn_maximize.accessibleName() == "Maximize"

        # Restore (maximized)
        tb.update_maximize_state(True)
        assert tb.btn_maximize.role == "restore"
        assert tb.btn_maximize.toolTip() == ""
        assert tb.btn_maximize.accessibleName() == "Restore Down"

        # Close
        assert tb.btn_close.toolTip() == ""
        assert tb.btn_close.accessibleName() == "Close"

    def test_caption_button_vector_painting_and_hover_control(self, qapp):
        """Verify that modern vector caption buttons render cleanly and respond to hover control."""
        win = QMainWindow()
        tb = WindowTitleBar(parent=win)
        win.show()
        qapp.processEvents()

        # Test hover state manipulation for DWM integration
        assert tb.btn_maximize._is_hovered is False
        tb.btn_maximize.setHovered(True)
        assert tb.btn_maximize._is_hovered is True
        tb.btn_maximize.setHovered(False)
        assert tb.btn_maximize._is_hovered is False

        # Verify repaint executes without exception across all roles
        for btn in (tb.btn_minimize, tb.btn_maximize, tb.btn_close):
            btn.repaint()

        tb.update_maximize_state(True)
        tb.btn_maximize.repaint()

        win.hide()

    def test_windows_compatibility_guards(self):
        """Verify that Windows 10/11 version detection correctly identifies environment without crashing."""
        import sys
        if sys.platform == "win32":
            from ui.native_window import is_windows_11_or_greater, is_windows_10_or_greater
            ver = sys.getwindowsversion()
            assert is_windows_10_or_greater() is (ver.major >= 10)
            assert is_windows_11_or_greater() is (ver.major >= 10 and ver.build >= 22000)

    def test_ws_popup_stripped_and_overlapped_styles_applied(self, qapp):
        """Verify that setup_native_window strips WS_POPUP and applies WS_OVERLAPPEDWINDOW styles for Snap Layouts."""
        if sys.platform != "win32":
            pytest.skip("Win32-only test")

        import ctypes
        from ui.native_window import setup_native_window, WS_POPUP, WS_THICKFRAME, WS_CAPTION, WS_MAXIMIZEBOX

        win = QMainWindow()
        win.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        win.show()
        qapp.processEvents()

        handler = setup_native_window(win)
        assert handler is not None

        hwnd = int(win.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF

        # WS_POPUP (0x80000000) must be stripped so Windows recognizes it as standard overlapped window
        assert (style & WS_POPUP) == 0, f"Expected WS_POPUP to be stripped, got style: {hex(style)}"
        # Native frame and box styles must be present for DWM Snap Layouts flyout
        assert (style & WS_THICKFRAME) != 0
        assert (style & WS_CAPTION) != 0
        assert (style & WS_MAXIMIZEBOX) != 0

        win.close()

    def test_wm_nchittest_delegates_to_dwm_first(self, qapp):
        """Verify that WM_NCHITTEST queries DwmDefWindowProc first to allow Snap Layouts flyout interaction."""
        if sys.platform != "win32":
            pytest.skip("Win32-only test")

        from ui.native_window import NativeWindowHandler, WM_NCHITTEST
        from ctypes.wintypes import MSG

        win = QMainWindow()
        win.resize(800, 500)
        handler = NativeWindowHandler(win)

        msg = MSG()
        msg.hWnd = int(win.winId())
        msg.message = WM_NCHITTEST
        msg.lParam = 0

        with patch("ctypes.windll.dwmapi.DwmDefWindowProc", return_value=1) as mock_dwm:
            handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
            assert handled is True
            assert mock_dwm.called

        win.close()

    def test_wm_ncmouse_messages_delegate_to_defwindowproc(self, qapp):
        """Verify that WM_NCMOUSEMOVE and WM_NCMOUSEHOVER pass to DefWindowProcW when unhandled by DWM."""
        if sys.platform != "win32":
            pytest.skip("Win32-only test")

        from ui.native_window import NativeWindowHandler, WM_NCMOUSEMOVE, WM_NCMOUSEHOVER, HTMAXBUTTON
        from ctypes.wintypes import MSG

        win = QMainWindow()
        handler = NativeWindowHandler(win)

        for wm_msg in (WM_NCMOUSEMOVE, WM_NCMOUSEHOVER):
            msg = MSG()
            msg.hWnd = int(win.winId())
            msg.message = wm_msg
            msg.wParam = HTMAXBUTTON
            msg.lParam = 0

            with patch("ctypes.windll.dwmapi.DwmDefWindowProc", return_value=0), \
                 patch("ctypes.windll.user32.DefWindowProcW", return_value=42) as mock_def:
                handled, res = handler.handle_native_event(b"windows_generic_MSG", ctypes.addressof(msg))
                assert handled is True
                assert res == 42
                assert mock_def.called

        win.close()
