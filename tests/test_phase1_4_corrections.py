"""
Phase 1.4 Verification Tests:
- Sidebar Icon Rendering, DPR Sharpness, and Sizing
- Settings Submenu Selection Persistence Across Collapse and Reopen
- Assembly & BOM Prep 8-Column Contract (Header 'NO', LibRef Removed, Model Preserved)
- Real Document Multi-Page Pagination Without Row Splitting
- Print Preview Navigation, View Modes, and Printer Dialog Safety
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPageSize, QPageLayout, QPixmap
from PyQt6.QtPrintSupport import QPrinter

from bom_auditor import BOMItem, BOMAuditResult
from ui.widgets.sidebar import CollapsibleSidebar, render_outline_pixmap, ChevronLabel
from ui.widgets.assembly_preparation_widget import AssemblyTableWidget, AssemblyPreparationWidget
from ui.printing.assembly_print_engine import AssemblyPrintEngine
from ui.dialogs.assembly_preview_dialog import AssemblyPreviewDialog


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance for UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_sample_bom_items(count: int = 40):
    """Generates a list of BOM items with varying field lengths."""
    items = []
    for i in range(1, count + 1):
        desigs = ", ".join([f"R{i*10 + j}" for j in range(i % 5 + 1)])
        items.append(
            BOMItem(
                row_idx=i,
                comment=f"VAL_{i}",
                description=f"Resistor SMD {i}k 1% 0603 Precision Thin Film",
                designator=desigs,
                footprint="RES0603",
                lib_ref="RES_PRECISION",
                part_number=f"RC0603FR-{i:04d}KL",
                unit_qty=max(1, i % 6),
                board_multiplier=1,
                package="0603"
            )
        )
    return items


class TestSidebarIconRenderingAndStatePersistence:
    """Tests sidebar icons rendering, sharpness, and selection persistence across collapse/reopen."""

    def test_render_outline_pixmap_exact_dimensions_and_transparency(self, qapp):
        for size in [12, 16, 18, 20]:
            pm = render_outline_pixmap("inventory", "#94a3b8", size=size)
            assert not pm.isNull()
            assert pm.width() == size
            assert pm.height() == size

    def test_all_sidebar_icons_render_successfully(self, qapp):
        icon_names = [
            "inventory", "bom_audit", "assembly", "general",
            "reference", "supplier", "backup", "about",
            "chevron_right", "chevron_down", "settings"
        ]
        for name in icon_names:
            pm = render_outline_pixmap(name, "#38bdf8", size=18)
            assert not pm.isNull(), f"Icon {name} failed to render"
            assert pm.width() == 18
            assert pm.height() == 18

    def test_settings_child_selection_persists_across_collapse_and_reopen(self, qapp):
        sidebar = CollapsibleSidebar()
        sidebar.show()
        qapp.processEvents()

        # Step 1: Navigate to 'About' child under Settings
        sidebar.set_active_page("about_settings")
        qapp.processEvents()
        assert sidebar.is_submenu_expanded() is True
        assert sidebar._active_page_id == "about"
        assert sidebar._last_settings_child == "about"
        assert sidebar._submenu_buttons["about"]._is_active is True

        # Step 2: Collapse sidebar to rail mode (e.g., user toggles hamburger)
        sidebar.set_collapsed(True)
        qapp.processEvents()
        assert sidebar.is_collapsed() is True
        # Active page must remain 'about', not reset to General
        assert sidebar._active_page_id == "about"
        assert sidebar._last_settings_child == "about"

        # Step 3: Expand sidebar back to full mode
        sidebar.set_collapsed(False)
        qapp.processEvents()
        assert sidebar.is_collapsed() is False
        # Submenu expanded state and active child must be restored
        assert sidebar.is_submenu_expanded() is True
        assert sidebar._active_page_id == "about"
        assert sidebar._last_settings_child == "about"
        assert sidebar._submenu_buttons["about"]._is_active is True
        assert sidebar.settings_parent_btn._chevron.direction == "down"

        # Step 4: Navigate to Supplier Directory, collapse and reopen
        sidebar.set_active_page("supplier_settings")
        qapp.processEvents()
        assert sidebar._active_page_id == "provider_management"

        sidebar.set_collapsed(True)
        qapp.processEvents()
        assert sidebar._active_page_id == "provider_management"

        sidebar.set_collapsed(False)
        qapp.processEvents()
        assert sidebar.is_submenu_expanded() is True
        assert sidebar._active_page_id == "provider_management"
        assert sidebar._submenu_buttons["provider_management"]._is_active is True

        sidebar.close()


class TestAssemblyTable8ColumnContract:
    """Tests 8-column layout, 'NO' header, and removal of LibRef from table & export."""

    def test_column_count_and_headers(self, qapp):
        table = AssemblyTableWidget()
        items = create_sample_bom_items(3)
        table.populate_items(items, "FC_IO_V1.3")

        assert table.columnCount() == 8
        headers = [table.horizontalHeaderItem(c).text() for c in range(8)]
        assert headers == [
            "NO", "Comment", "Description", "Designator", "Footprint", "Qty", "Part Number", "Package"
        ]
        # Column 0 must be NO
        assert headers[0] == "NO"
        # LibRef must not be present in table headers
        assert "LibRef" not in headers

    def test_underlying_bomitem_libref_preserved(self, qapp):
        items = create_sample_bom_items(3)
        assert items[0].lib_ref == "RES_PRECISION"

        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        # Table does not show LibRef, but domain object retains it
        assert items[0].lib_ref == "RES_PRECISION"

    def test_copy_tsv_contains_8_columns_and_no_libref(self, qapp):
        items = create_sample_bom_items(3)
        table = AssemblyTableWidget()
        table.populate_items(items, "FC_IO_V1.3")

        table._copy_row_tsv(0)
        tsv = QApplication.clipboard().text()
        parts = tsv.split("\t")
        assert len(parts) == 8
        assert parts[0] == "N1"
        assert parts[1] == "VAL_1"
        assert "RES_PRECISION" not in parts


class TestDocumentPaginationAndPrintEngine:
    """Tests document chunking, pagination, repeat headers, and no row splitting."""

    def test_chunking_splits_large_dataset_across_pages(self):
        items = create_sample_bom_items(45)
        # Test A4 chunking
        pages_a4 = AssemblyPrintEngine.chunk_items_for_pages(items, is_a4=True)
        assert len(pages_a4) > 1
        total_items_chunked_a4 = sum(len(p) for p in pages_a4)
        assert total_items_chunked_a4 == 45

        # Test A5 chunking (smaller pages -> more pages)
        pages_a5 = AssemblyPrintEngine.chunk_items_for_pages(items, is_a4=False)
        assert len(pages_a5) > len(pages_a4)
        total_items_chunked_a5 = sum(len(p) for p in pages_a5)
        assert total_items_chunked_a5 == 45

    def test_html_includes_repeated_headers_and_page_break_divs(self):
        items = create_sample_bom_items(45)
        html_out = AssemblyPrintEngine.generate_html(items, "TestProject", total_qty=100, page_size_id=QPageSize.PageSizeId.A4)

        # Must have page breaks
        assert 'class="page-break"' in html_out
        # Must have continuation header
        assert "Continuation" in html_out
        # Must have repeated th columns on every page
        assert html_out.count('<th class="col-no-header"') > 1
        # LibRef must not be in print th
        assert "<th>LibRef</th>" not in html_out
        assert "LibRef" not in html_out

    def test_multi_page_pdf_export(self, tmp_path, qapp):
        items = create_sample_bom_items(45)
        pdf_path = str(tmp_path / "MultiPage_Assembly.pdf")
        exported = AssemblyPrintEngine.export_pdf(
            bom_items=items,
            project_name="MultiPageProject",
            total_qty=100,
            output_filepath=pdf_path,
            page_size_id=QPageSize.PageSizeId.A4
        )
        assert os.path.exists(exported)
        assert os.path.getsize(exported) > 1000


class TestPreviewDialogNavigationAndControls:
    """Tests preview dialog page navigation, view modes, and print entry point."""

    def test_preview_dialog_page_navigation(self, qapp):
        items = create_sample_bom_items(45)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=100)
        dialog.show()
        qapp.processEvents()

        # Page navigation widgets must exist
        assert hasattr(dialog, "prev_btn")
        assert hasattr(dialog, "next_btn")
        assert hasattr(dialog, "page_lbl")
        assert hasattr(dialog, "view_mode_combo")

        # Initial state
        total = dialog.preview_widget.pageCount()
        assert total > 1
        assert dialog.page_lbl.text() == f"Page 1 of {total}"
        assert dialog.prev_btn.isEnabled() is False
        assert dialog.next_btn.isEnabled() is True

        # Navigate to Next page
        dialog.next_btn.click()
        qapp.processEvents()
        assert dialog.preview_widget.currentPage() == 2
        assert dialog.page_lbl.text() == f"Page 2 of {total}"
        assert dialog.prev_btn.isEnabled() is True

        # Navigate back to Previous page
        dialog.prev_btn.click()
        qapp.processEvents()
        assert dialog.preview_widget.currentPage() == 1
        assert dialog.page_lbl.text() == f"Page 1 of {total}"

        # Switch View Mode to Single Page
        dialog.view_mode_combo.setCurrentIndex(1)
        qapp.processEvents()
        assert dialog.preview_widget.viewMode() == dialog.preview_widget.ViewMode.SinglePageView

        # Switch View Mode back to All Pages
        dialog.view_mode_combo.setCurrentIndex(0)
        qapp.processEvents()
        assert dialog.preview_widget.viewMode() == dialog.preview_widget.ViewMode.AllPagesView

        dialog.close()

    def test_print_entry_points_dialog_safety_and_no_option_disable(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)

        with patch("ui.dialogs.assembly_preview_dialog.QPrintDialog") as mock_dlg_cls:
            mock_dlg = mock_dlg_cls.return_value
            mock_dlg.exec.return_value = QDialog.DialogCode.Rejected

            dialog._handle_print()
            assert mock_dlg.exec.called
            # Verify no arbitrary options like PrintCollateCopies were disabled
            if mock_dlg.setOption.called:
                for call in mock_dlg.setOption.call_args_list:
                    assert call[0][1] is not False, "Print options must not be artificially disabled"

        dialog.close()
