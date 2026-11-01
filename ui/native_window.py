"""
Omnix UI — Native Windows 11 Desktop Window Manager (DWM) Integration
Governing Specifications:
- Microsoft Learn: DwmExtendFrameIntoClientArea (DWM Desktop Composition)
- Microsoft Learn: WM_NCCALCSIZE (Client Area Calculation & 8px Overshoot Adjustment)
- Microsoft Learn: WM_NCHITTEST (HTMAXBUTTON for Windows 11 Snap Layouts & Native Resizing)
- Microsoft Learn: WM_GETMINMAXINFO (Native Sizing Constraints)

Provides genuine Windows 11 native window behavior:
- Fluent system-managed minimize, maximize, restore, and resize transitions.
- Native hardware-accelerated resize cursors and edge snapping.
- Windows 11 Snap Layouts flyout on hover over the maximize button.
- High-DPI physical-to-logical coordinate scaling.
- Graceful cross-platform fallback for non-Windows environments.
"""

from typing import Optional, Tuple
import sys
from PyQt6.QtCore import QPoint, Qt, QRect
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QMainWindow, QWidget


if sys.platform == "win32":
    import ctypes
    from ctypes import (
        Structure,
        c_int,
        c_long,
        c_short,
        c_void_p,
        byref,
        sizeof,
        windll,
    )
    from ctypes.wintypes import HWND, RECT, POINT, DWORD, MSG

    user32 = getattr(windll, "user32", None)
    dwmapi = getattr(windll, "dwmapi", None)

    # Win32 Window Messages
    WM_GETMINMAXINFO = 0x0024
    WM_WINDOWPOSCHANGING = 0x0046
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    WM_NCLBUTTONDOWN = 0x00A1
    WM_NCLBUTTONUP = 0x00A2
    WM_SYSCOMMAND = 0x0112
    WM_NCMOUSEMOVE = 0x00A0
    WM_NCMOUSELEAVE = 0x02A2
    WM_NCMOUSEHOVER = 0x02A0

    # Win32 Hit-Test Result Codes (LRESULT)
    HTCLIENT = 1
    HTCAPTION = 2
    HTMINBUTTON = 8
    HTMAXBUTTON = 9
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    HTCLOSE = 20

    # Win32 Window Styles
    GWL_STYLE = -16
    WS_POPUP = 0x80000000
    WS_THICKFRAME = 0x00040000
    WS_CAPTION = 0x00C00000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_SYSMENU = 0x00080000

    # SetWindowPos Flags
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020

    # Monitor info
    MONITOR_DEFAULTTONEAREST = 2

    # DWM Window Attributes
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_USE_IMMERSIVE_DARK_MODE_FALLBACK = 19
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2

    class MARGINS(Structure):
        _fields_ = [
            ("cxLeftWidth", c_int),
            ("cxRightWidth", c_int),
            ("cyTopHeight", c_int),
            ("cyBottomHeight", c_int),
        ]

    class NCCALCSIZE_PARAMS(Structure):
        _fields_ = [
            ("rgrc", RECT * 3),
            ("lppos", c_void_p),
        ]

    class MINMAXINFO(Structure):
        _fields_ = [
            ("ptReserved", POINT),
            ("ptMaxSize", POINT),
            ("ptMaxPosition", POINT),
            ("ptMinTrackSize", POINT),
            ("ptMaxTrackSize", POINT),
        ]

    class MONITORINFO(Structure):
        _fields_ = [
            ("cbSize", DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", DWORD),
        ]

    class NativeWindowHandler:
        """
        Handles Win32 native messages for a QMainWindow to enable native DWM
        frameless window management, Snap Layouts, and smooth transitions.
        """

        def __init__(
            self,
            window: QMainWindow,
            border_margin: int = 8,
            min_width: int = 960,
            min_height: int = 620,
            min_track_width: int = 330,
            min_track_height: int = 240,
        ):
            self.window = window
            self.border_margin = border_margin
            self.min_width = min_width
            self.min_height = min_height
            self.min_track_width = min_track_width
            self.min_track_height = min_track_height

        def handle_native_event(self, event_type, message) -> Tuple[bool, int]:
            if not user32 or not dwmapi or not self.window:
                return False, 0

            try:
                msg = MSG.from_address(int(message))
            except Exception:
                return False, 0

            hwnd = msg.hWnd

            # 0. Non-Client Mouse Tracking — Pass to DwmDefWindowProc and DefWindowProcW so DWM tracks caption hover states and Snap Layouts
            if msg.message == WM_NCMOUSELEAVE:
                title_bar = getattr(self.window, "title_bar", None)
                if title_bar:
                    btn_max = getattr(title_bar, "btn_maximize", None)
                    if btn_max and hasattr(btn_max, "setHovered"):
                        btn_max.setHovered(False)
                lres = c_void_p(0)
                if dwmapi.DwmDefWindowProc(hwnd, msg.message, msg.wParam, msg.lParam, byref(lres)):
                    return True, lres.value or 0
                res = user32.DefWindowProcW(hwnd, msg.message, msg.wParam, msg.lParam)
                return True, res

            elif msg.message in (WM_NCMOUSEMOVE, WM_NCMOUSEHOVER):
                lres = c_void_p(0)
                if dwmapi.DwmDefWindowProc(hwnd, msg.message, msg.wParam, msg.lParam, byref(lres)):
                    return True, lres.value or 0
                res = user32.DefWindowProcW(hwnd, msg.message, msg.wParam, msg.lParam)
                return True, res

            # 1. WM_NCCALCSIZE — Remove standard frame while preserving DWM composition & fix 8px maximize overshoot
            elif msg.message == WM_NCCALCSIZE:
                if msg.wParam:
                    if user32.IsZoomed(hwnd):
                        # Compensate for Windows 8px maximized overshoot
                        params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                        h_mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
                        if h_mon:
                            mi = MONITORINFO()
                            mi.cbSize = sizeof(MONITORINFO)
                            if user32.GetMonitorInfoW(h_mon, byref(mi)):
                                params.rgrc[0].left = mi.rcWork.left
                                params.rgrc[0].top = mi.rcWork.top
                                params.rgrc[0].right = mi.rcWork.right
                                params.rgrc[0].bottom = mi.rcWork.bottom
                    return True, 0

            # 2. WM_NCHITTEST — High-DPI coordinate scaling, border resizing, and Snap Layouts
            elif msg.message == WM_NCHITTEST:
                # 0. Give DWM first opportunity to hit-test (e.g., Snap Layouts flyout menu zones)
                lres = c_void_p(0)
                if dwmapi.DwmDefWindowProc(hwnd, msg.message, msg.wParam, msg.lParam, byref(lres)):
                    return True, lres.value or 0

                # Physical screen coordinates from lParam (signed 16-bit)
                raw_x = c_short(msg.lParam & 0xFFFF).value
                raw_y = c_short((msg.lParam >> 16) & 0xFFFF).value

                dpr = self.window.devicePixelRatio()
                if dpr <= 0:
                    dpr = 1.0

                logical_x = int(round(raw_x / dpr))
                logical_y = int(round(raw_y / dpr))
                screen_pt = QPoint(logical_x, logical_y)
                c_pos = QCursor.pos()

                title_bar = getattr(self.window, "title_bar", None)

                # 1. Caption Buttons take absolute precedence over perimeter resize borders (HTTOP / HTRIGHT)
                if title_bar and title_bar.isVisible():
                    # Maximize button: Return HTMAXBUTTON across 100% of button area to trigger Windows 11 Snap Layouts flyout
                    btn_max = getattr(title_bar, "btn_maximize", None)
                    if btn_max and btn_max.isVisible():
                        max_geo = QRect(btn_max.mapToGlobal(QPoint(0, 0)), btn_max.size())
                        if max_geo.contains(screen_pt) or max_geo.contains(c_pos):
                            if hasattr(btn_max, "setHovered"):
                                btn_max.setHovered(True)
                            return True, HTMAXBUTTON
                        elif hasattr(btn_max, "setHovered"):
                            btn_max.setHovered(False)

                    # Minimize, Close, and Navigation controls: Return HTCLIENT for Qt mouse interactions and styling
                    btn_min = getattr(title_bar, "btn_minimize", None)
                    if btn_min and btn_min.isVisible():
                        min_geo = QRect(btn_min.mapToGlobal(QPoint(0, 0)), btn_min.size())
                        if min_geo.contains(screen_pt) or min_geo.contains(c_pos):
                            return True, HTCLIENT

                    btn_close = getattr(title_bar, "btn_close", None)
                    if btn_close and btn_close.isVisible():
                        close_geo = QRect(btn_close.mapToGlobal(QPoint(0, 0)), btn_close.size())
                        if close_geo.contains(screen_pt) or close_geo.contains(c_pos):
                            return True, HTCLIENT

                    hamburger = getattr(title_bar, "hamburger_btn", None)
                    if hamburger and hamburger.isVisible():
                        ham_geo = QRect(hamburger.mapToGlobal(QPoint(0, 0)), hamburger.size())
                        if ham_geo.contains(screen_pt) or ham_geo.contains(c_pos):
                            return True, HTCLIENT

                # Convert physical coordinates to window client coordinates via Win32 ScreenToClient
                pt = POINT(raw_x, raw_y)
                user32.ScreenToClient(hwnd, byref(pt))
                lx = int(round(pt.x / dpr))
                ly = int(round(pt.y / dpr))
                w, h = self.window.width(), self.window.height()

                # 2. Window perimeter resizing (when not maximized)
                if not self.window.isMaximized():
                    margin = self.border_margin
                    top = ly < margin
                    bottom = ly >= h - margin
                    left = lx < margin
                    right = lx >= w - margin

                    if top and left:
                        return True, HTTOPLEFT
                    if top and right:
                        return True, HTTOPRIGHT
                    if bottom and left:
                        return True, HTBOTTOMLEFT
                    if bottom and right:
                        return True, HTBOTTOMRIGHT
                    if top:
                        return True, HTTOP
                    if bottom:
                        return True, HTBOTTOM
                    if left:
                        return True, HTLEFT
                    if right:
                        return True, HTRIGHT

                # 3. Title Bar Draggable Space & Child Controls
                if title_bar and title_bar.isVisible():
                    tb_geo = title_bar.geometry()
                    if tb_geo.contains(QPoint(lx, ly)):
                        tb_local_pos = title_bar.mapFrom(self.window, QPoint(lx, ly))
                        child = title_bar.childAt(tb_local_pos)
                        if child is not None and child is not title_bar:
                            return True, HTCLIENT
                        # Empty title bar draggable space: Native dragging, double-click maximize, Aero Snap
                        return True, HTCAPTION

                return True, HTCLIENT

            # 3. WM_NCLBUTTONDOWN / WM_NCLBUTTONUP — Handle clicks on HTMAXBUTTON
            elif msg.message == WM_NCLBUTTONDOWN:
                if msg.wParam == HTMAXBUTTON:
                    lres = c_void_p(0)
                    if dwmapi.DwmDefWindowProc(hwnd, msg.message, msg.wParam, msg.lParam, byref(lres)):
                        return True, lres.value or 0
                    res = user32.DefWindowProcW(hwnd, msg.message, msg.wParam, msg.lParam)
                    return True, res

            elif msg.message == WM_NCLBUTTONUP:
                if msg.wParam == HTMAXBUTTON:
                    lres = c_void_p(0)
                    if dwmapi.DwmDefWindowProc(hwnd, msg.message, msg.wParam, msg.lParam, byref(lres)):
                        return True, lres.value or 0
                    title_bar = getattr(self.window, "title_bar", None)
                    if title_bar and hasattr(title_bar, "_toggle_maximize"):
                        title_bar._toggle_maximize()
                    return True, 0

            # 4. WM_GETMINMAXINFO — Enforce native window sizing constraints in physical pixels
            elif msg.message == WM_GETMINMAXINFO:
                dpr = self.window.devicePixelRatio()
                if dpr <= 0:
                    dpr = 1.0
                mmi = MINMAXINFO.from_address(msg.lParam)
                # Respect Microsoft recommendation for Windows 11 Snap Layouts:
                # ptMinTrackSize must be small enough (<= 330-500 effective pixels) so DWM
                # can slot the window into fractional screen zones (1/2, 1/3, 1/4 layout zones).
                mmi.ptMinTrackSize.x = int(self.min_track_width * dpr)
                mmi.ptMinTrackSize.y = int(self.min_track_height * dpr)
                return True, 0

            return False, 0


def is_windows_11_or_greater() -> bool:
    """Returns True if running on Windows 11 or greater (NT kernel 10.0 with build >= 22000)."""
    if sys.platform != "win32":
        return False
    try:
        ver = sys.getwindowsversion()
        return ver.major >= 10 and ver.build >= 22000
    except Exception:
        return False


def is_windows_10_or_greater() -> bool:
    """Returns True if running on Windows 10 or greater (NT kernel 10.0 with build >= 10240)."""
    if sys.platform != "win32":
        return False
    try:
        ver = sys.getwindowsversion()
        return ver.major >= 10
    except Exception:
        return False


def setup_native_window(window: QMainWindow) -> Optional["NativeWindowHandler"]:
    """
    Initializes Windows 11 native DWM non-client frame attributes, window styles,
    and returns a NativeWindowHandler instance.
    Silently no-ops and returns None on non-Windows platforms.
    """
    if sys.platform != "win32":
        return None

    try:
        from ui.dark_frame import apply_dark_window_frame

        apply_dark_window_frame(window)

        hwnd = int(window.winId())
        if not hwnd or not user32 or not dwmapi:
            return None

        # Add WS_THICKFRAME, WS_CAPTION, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU
        # Strip WS_POPUP bit so DWM and Windows Shell treat the window as a standard overlapped application frame
        # while preserving frameless rendering via WM_NCCALCSIZE
        cur_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        cur_unsigned = cur_style & 0xFFFFFFFF
        new_unsigned = (cur_unsigned & ~WS_POPUP) | WS_THICKFRAME | WS_CAPTION | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        user32.SetWindowLongW(hwnd, GWL_STYLE, c_long(new_unsigned).value)

        # Trigger frame recalculation
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        )

        # Extend DWM frame into client area
        margins = MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))

        # Windows 11 Rounded corners (guarded for Windows 11 build >= 22000 compatibility)
        if is_windows_11_or_greater():
            try:
                corner_pref = c_int(DWMWCP_ROUND)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, byref(corner_pref), sizeof(corner_pref)
                )
            except Exception:
                pass

        handler = NativeWindowHandler(window)
        return handler
    except Exception:
        return None


def native_maximize(window: Optional[QMainWindow] = None) -> bool:
    """
    Maximizes the window natively using Win32 ShowWindow(SW_MAXIMIZE = 3).
    Ensures user32.IsZoomed(hwnd) becomes True and DWM executes native zoom animation.
    """
    if sys.platform != "win32" or window is None or not user32:
        return False
    try:
        hwnd = int(window.winId())
        if not hwnd:
            return False
        SW_MAXIMIZE = 3
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return True
    except Exception:
        return False


def native_restore(window: Optional[QMainWindow] = None) -> bool:
    """
    Restores the window natively using Win32 ShowWindow(SW_RESTORE = 9).
    Ensures user32.IsZoomed(hwnd) becomes False and DWM executes native restore animation.
    """
    if sys.platform != "win32" or window is None or not user32:
        return False
    try:
        hwnd = int(window.winId())
        if not hwnd:
            return False
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        return True
    except Exception:
        return False


def native_toggle_maximize(window: Optional[QMainWindow] = None) -> bool:
    """
    Toggles the window state between maximized and restored using native Win32 ShowWindow.
    """
    if sys.platform != "win32" or window is None or not user32:
        return False
    try:
        hwnd = int(window.winId())
        if not hwnd:
            return False
        is_zoomed = bool(user32.IsZoomed(hwnd))
        if is_zoomed or window.isMaximized():
            return native_restore(window)
        else:
            return native_maximize(window)
    except Exception:
        return False
