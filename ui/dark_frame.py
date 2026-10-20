"""
Omnix UI — Native Windows Dark Window Frame Helper
Governing Requirement: Dark dialog title bars and consistent window chrome across Windows 10/11.

Uses the Windows Desktop Window Manager (DWM) API via ctypes to set the immersive
dark mode title bar attribute (DWMWA_USE_IMMERSIVE_DARK_MODE = 20, fallback 19)
and rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33).
"""

import sys
from typing import Optional
from PyQt6.QtWidgets import QWidget


def apply_dark_window_frame(widget: Optional[QWidget]) -> None:
    """
    Applies the native Windows immersive dark mode title bar and styling
    to the given top-level QWidget or QDialog on Windows 10/11.
    Silently no-ops on non-Windows platforms or if DWM calls fail.
    """
    if sys.platform != "win32" or widget is None:
        return

    try:
        import ctypes
        from ctypes import c_int, byref, sizeof

        # Ensure the native window handle is instantiated
        hwnd = int(widget.winId())
        if not hwnd:
            return

        dwmapi = getattr(ctypes.windll, "dwmapi", None)
        if not dwmapi:
            return

        # DWMWA_USE_IMMERSIVE_DARK_MODE
        # 20 is the official attribute on Windows 10 (build 19041+) and Windows 11.
        # 19 was the undocumented attribute used on Windows 10 1809 - 1909.
        dark_enabled = c_int(1)
        res = dwmapi.DwmSetWindowAttribute(
            hwnd, 20, byref(dark_enabled), sizeof(dark_enabled)
        )
        if res != 0:
            dwmapi.DwmSetWindowAttribute(
                hwnd, 19, byref(dark_enabled), sizeof(dark_enabled)
            )

        # DWMWA_WINDOW_CORNER_PREFERENCE (Windows 11 build 22000+)
        # 33: DWMWCP_ROUND (2)
        corner_round = c_int(2)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 33, byref(corner_round), sizeof(corner_round)
        )
    except Exception:
        # Graceful fallback: do not crash if Windows DWM is unavailable or restricted
        pass
