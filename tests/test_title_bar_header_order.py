"""
Unit tests verifying top-bar branding order in Omnix WindowTitleBar.
Ensures the order is strictly [OMNIX wordmark] [Hamburger / Navigation Toggle],
resting state is transparent/borderless, accessible focus is preserved,
and clicking hamburger toggles the navigation sidebar.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.widgets.title_bar import WindowTitleBar
from core.inventory import resolve_inventory_database_path


@pytest.fixture
def main_window(qapp):
    """Fixture providing a managed MainWindow instance."""
    db_path = resolve_inventory_database_path()
    win = MainWindow(default_file=db_path)
    win.show()
    qapp.processEvents()
    yield win
    win._is_force_closing = True
    win.close()


class TestTitleBarBrandingOrder:
    """Verifies minimal header layout order and hamburger button behavior."""

    def test_wordmark_appears_before_hamburger(self, main_window):
        """The OMNIX wordmark must strictly appear before the hamburger button in the title bar layout."""
        tb = main_window.title_bar
        layout = tb.layout()

        idx_wordmark = layout.indexOf(tb.title_lbl)
        idx_hamburger = layout.indexOf(tb.hamburger_btn)

        assert idx_wordmark != -1, "OMNIX wordmark label not found in title bar layout"
        assert idx_hamburger != -1, "Hamburger toggle button not found in title bar layout"
        assert idx_wordmark < idx_hamburger, (
            f"Expected wordmark (idx {idx_wordmark}) before hamburger (idx {idx_hamburger})"
        )

        # Wordmark content verification
        assert "OMNIX" in tb.title_lbl.text()

        # No duplicate branding or invented icon in title bar
        assert not hasattr(tb, "icon_lbl")
        assert not hasattr(tb, "logo_lbl")

    def test_hamburger_resting_hover_and_focus_styles(self, main_window):
        """Hamburger button must have transparent resting border and accessible focus state."""
        tb = main_window.title_bar
        btn = tb.hamburger_btn
        style = btn.styleSheet()

        # Resting state: transparent background and transparent/none border
        assert "background-color: transparent" in style
        assert "border: 1px solid transparent" in style or "border: none" in style

        # Subtle hover state
        assert "QPushButton#hamburgerBtn:hover" in style
        assert "color: #38bdf8" in style

        # Pressed state
        assert "QPushButton#hamburgerBtn:pressed" in style

        # Accessible keyboard-focus state
        assert "QPushButton#hamburgerBtn:focus" in style
        assert "border: 1px solid rgba(56, 189, 248" in style or "outline:" in style

    def test_hamburger_toggles_sidebar(self, main_window, qapp):
        """Clicking the hamburger button must toggle the navigation sidebar between expanded and collapsed."""
        win = main_window
        sidebar = win.sidebar

        # Initial expanded state
        assert sidebar.is_collapsed() is False
        assert sidebar.width() == sidebar.EXPANDED_WIDTH

        # Click hamburger -> Collapses
        win.title_bar.hamburger_btn.click()
        qapp.processEvents()
        assert sidebar.is_collapsed() is True
        assert sidebar.width() == sidebar.COLLAPSED_WIDTH

        # Click hamburger again -> Expands
        win.title_bar.hamburger_btn.click()
        qapp.processEvents()
        assert sidebar.is_collapsed() is False
        assert sidebar.width() == sidebar.EXPANDED_WIDTH

    def test_window_controls_positioned_at_end(self, main_window):
        """Standard window controls (minimize, maximize, close) must appear after hamburger on the right."""
        tb = main_window.title_bar
        layout = tb.layout()

        idx_hamburger = layout.indexOf(tb.hamburger_btn)
        idx_minimize = layout.indexOf(tb.btn_minimize)
        idx_maximize = layout.indexOf(tb.btn_maximize)
        idx_close = layout.indexOf(tb.btn_close)

        assert idx_hamburger < idx_minimize < idx_maximize < idx_close
