"""
Unit tests for standardized minimal outline sidebar icons in Omnix.
Verifies consistent outline icon rendering, collapsed/expanded states,
active styling, tooltip preservation, and legacy emoji compatibility.
"""

import pytest
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QApplication

from ui.widgets.sidebar import (
    CollapsibleSidebar,
    SidebarNavButton,
    SIDEBAR_ICON_SVGS,
    LEGACY_EMOJI_MAP,
    render_outline_pixmap,
)


@pytest.fixture
def sidebar(qapp):
    """Fixture providing an instance of CollapsibleSidebar."""
    sb = CollapsibleSidebar()
    sb.show()
    qapp.processEvents()
    yield sb
    sb.close()


class TestSidebarIcons:
    """Verifies minimal outline sidebar icon consistency, layout, and behavior."""

    def test_all_pages_have_defined_outline_svgs(self):
        """All navigation pages must map to a standardized outline SVG with matching stroke."""
        expected_pages = [
            "assembly_view",
            "component_inventory",
            "bom_audit",
            "assembly_prep",
            "vendor_plugins",
            "settings",
            "general_settings",
            "reference_data",
            "provider_management",
            "backup_restore",
            "about",
            "chevron_right",
            "chevron_down",
        ]
        for page_id in expected_pages:
            assert page_id in SIDEBAR_ICON_SVGS, f"Missing SVG definition for {page_id}"
            svg = SIDEBAR_ICON_SVGS[page_id]
            assert 'viewBox="0 0 24 24"' in svg, f"Invalid viewBox in {page_id}"
            assert 'stroke-width="1.8"' in svg, f"Mismatched stroke-width in {page_id}"
            assert 'fill="none"' in svg, f"Must be outline icon (fill=none) in {page_id}"

    def test_sidebar_buttons_have_valid_non_null_icons(self, sidebar):
        """Every button in the sidebar must have a valid non-null outline QIcon."""
        assert len(sidebar.PAGES) == 6
        for page_id, label, icon_key in sidebar.PAGES:
            btn = sidebar._buttons[page_id]
            assert not btn.icon().isNull(), f"Icon for {page_id} is null"
            assert btn.iconSize() == QSize(18, 18)
            assert btn.toolTip() == label

    def test_no_emoji_in_sidebar_button_text(self, sidebar):
        """Button text and icons must not contain raw Unicode emoji characters."""
        emojis = ["📊", "🏷️", "📑", "📚", "⚙️", "🌐", "💾"]
        for page_id, btn in sidebar._buttons.items():
            for emoji in emojis:
                assert emoji not in btn.text(), f"Found emoji {emoji} in expanded text of {page_id}"

    def test_expanded_mode_shows_label_with_icon(self, sidebar):
        """In expanded mode, buttons display full label and retain icon."""
        sidebar.set_collapsed(False)
        assert sidebar.width() == sidebar.EXPANDED_WIDTH
        for page_id, label, _ in sidebar.PAGES:
            btn = sidebar._buttons[page_id]
            assert label in btn.text()
            assert not btn.icon().isNull()

    def test_collapsed_mode_clears_text_and_retains_icon_and_tooltip(self, sidebar):
        """In collapsed mode, button text is cleared to center the icon, preserving tooltip."""
        sidebar.set_collapsed(True)
        assert sidebar.is_collapsed() is True
        assert sidebar.width() == sidebar.COLLAPSED_WIDTH
        for page_id, label, _ in sidebar.PAGES:
            btn = sidebar._buttons[page_id]
            assert btn.text() == "", f"Collapsed button {page_id} must have empty text"
            assert not btn.icon().isNull()
            assert btn.toolTip() == label

    def test_active_button_state_and_navigation(self, sidebar):
        """Clicking or setting active page updates selection and emits pageChanged signal."""
        emitted_pages = []
        sidebar.pageChanged.connect(lambda pid: emitted_pages.append(pid))

        sidebar.set_active_page("bom_audit")
        assert sidebar.active_page() == "bom_audit"
        assert sidebar._buttons["bom_audit"]._is_active is True
        assert sidebar._buttons["assembly_view"]._is_active is False

        # Click settings
        sidebar._buttons["settings"].click()
        assert sidebar.active_page() == "settings"
        assert "settings" in emitted_pages

    def test_legacy_emoji_mapping_compatibility(self):
        """Passing legacy emoji string gracefully maps to the correct outline SVG pixmap."""
        for emoji, canonical_key in LEGACY_EMOJI_MAP.items():
            pm = render_outline_pixmap(emoji, "#94a3b8")
            assert not pm.isNull(), f"Failed to render outline icon for legacy emoji {emoji}"
            assert pm.width() > 0 and pm.height() > 0

    def test_pixmap_caching(self):
        """Subsequent requests for the same icon, color, and size return the cached pixmap."""
        pm1 = render_outline_pixmap("assembly_view", "#38bdf8", 36)
        pm2 = render_outline_pixmap("assembly_view", "#38bdf8", 36)
        assert pm1 is pm2
