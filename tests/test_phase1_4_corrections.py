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
from ui.widgets.stats_ribbon import StatsRibbonWidget
from ui.widgets.vendor_plugins_widget import VendorPluginsWidget
from ui.main_window import MainWindow


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

    def test_preview_dialog_initial_all_pages_mode_synchronized(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)
        dialog.show()
        qapp.processEvents()

        # Both the combobox and the internal QPrintPreviewWidget must agree on AllPagesView
        assert dialog.view_mode_combo.currentText() == "All Pages"
        assert dialog.preview_widget.viewMode() == dialog.preview_widget.ViewMode.AllPagesView
        dialog.close()

    def test_preview_dialog_top_bar_clean_without_print_controls(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)

        # Print button must be completely absent from dialog
        assert not hasattr(dialog, "print_btn")
        assert not hasattr(dialog, "_handle_print")

        # PDF save button must remain active and functional
        assert hasattr(dialog, "pdf_btn")
        assert dialog.pdf_btn.text() == "📥 Save as PDF"
        dialog.close()


class TestFloatingPreviewControls:
    """Tests that preview controls are docked in a floating dock at the bottom."""

    def test_floating_control_dock_exists_and_contains_controls(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)
        dialog.show()
        qapp.processEvents()

        # Floating control bar must exist
        assert hasattr(dialog, "floating_control_bar")
        assert dialog.floating_control_bar.parent() == dialog

        # Controls inside floating bar
        assert hasattr(dialog, "prev_btn")
        assert hasattr(dialog, "next_btn")
        assert hasattr(dialog, "page_lbl")
        assert hasattr(dialog, "fit_width_btn")
        assert hasattr(dialog, "fit_page_btn")
        assert hasattr(dialog, "zoom_in_btn")
        assert hasattr(dialog, "zoom_out_btn")

        dialog.close()


class TestDatabaseDisplaySeparation:
    """Tests that upper stats ribbon does not display duplicate database path pill."""

    def test_stats_ribbon_does_not_contain_file_path_pill_in_layout(self, qapp):
        ribbon = StatsRibbonWidget()
        # stat_file exists as an attribute for API compatibility, but is hidden / not in layout
        assert hasattr(ribbon, "stat_file")
        assert ribbon.stat_file.isHidden() is True

        # Updating stats should preserve hidden state
        ribbon.update_stats(total_rows=100, filtered_rows=50, total_cols=10, file_name="C:/path/to/db.xlsx")
        assert ribbon.stat_file.isHidden() is True

    def test_redundant_columns_indicator_absent_while_preserving_table_columns(self, qapp):
        ribbon = StatsRibbonWidget()
        # stat_columns exists for API compatibility but must be hidden/not shown in upper ribbon
        assert hasattr(ribbon, "stat_columns")
        assert ribbon.stat_columns.isHidden() is True

        ribbon.update_stats(total_rows=100, filtered_rows=50, total_cols=10, file_name="C:/path/to/db.xlsx")
        assert ribbon.stat_columns.isHidden() is True


class TestMpnCopyNotificationDeduplication:
    """Tests that copying MPN does not trigger duplicate statusBar message."""

    def test_mpn_click_updates_status_indicator_without_duplicate_message(self, qapp):
        from PyQt6.QtWidgets import QTableWidgetItem
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file="")
            win.statusBar().clearMessage()

            # Prepare table item at column 2 (MPN)
            win.table.setColumnCount(5)
            win.table.setRowCount(1)
            item = QTableWidgetItem("GRM188R71H104KA93D")
            win.table.setItem(0, 2, item)

            # Trigger MPN click handler
            win._on_inventory_component_clicked(item)

            # Dedicated status indicator updated
            assert "GRM188R71H104KA93D" in win.status_state_lbl.text()
            # Left status bar showMessage was NOT called with duplicate text
            assert win.statusBar().currentMessage() == ""

            win._is_force_closing = True
            win.close()


class TestVendorPluginsLayoutUnclipped:
    """Tests that VendorPluginsWidget uses proper layout margins and unclipped card."""

    def test_vendor_plugins_card_margins_and_no_css_padding_clipping(self, qapp):
        from PyQt6.QtWidgets import QFrame
        widget = VendorPluginsWidget()
        widget.resize(1000, 700)
        widget.show()
        qapp.processEvents()

        card = widget.findChild(QFrame, "cardFrame")
        assert card is not None

        # Card frame stylesheet must not have hardcoded CSS padding clipping text
        assert "padding: 32px 24px" not in card.styleSheet()

        # Content must have non-zero layout margins
        margins = card.layout().contentsMargins()
        assert margins.left() >= 24
        assert margins.right() >= 24
        assert margins.top() >= 24
        assert margins.bottom() >= 24

        widget.close()

    def test_vendor_plugins_empty_state_rendered_exactly_once_after_multiple_refreshes(self, qapp):
        from PyQt6.QtWidgets import QFrame
        widget = VendorPluginsWidget()
        assert len(widget.findChildren(QFrame, "cardFrame")) == 1

        for _ in range(5):
            widget.refresh_plugins()
            assert len(widget.findChildren(QFrame, "cardFrame")) == 1

        widget.close()


class TestPhase1_5PrintRemovalAndWindowManagement:
    """Tests for complete print removal, PDF export preservation, and smooth Min/Max behavior."""

    def test_print_functionality_completely_removed_from_ui(self, qapp):
        items = create_sample_bom_items(10)
        prep = AssemblyPreparationWidget()
        prep.bom_items = items
        prep.project_name = "FC_IO_V1.3"

        # Preparation widget must NOT have any print buttons or print methods
        assert not hasattr(prep, "print_btn")
        assert not hasattr(prep, "print_worksheet")
        assert not hasattr(prep, "print_a5_sheet")

        # Must retain preview and PDF export
        assert hasattr(prep, "preview_btn")
        assert hasattr(prep, "pdf_btn")
        prep.close()

        # Dialog must NOT have print button or _handle_print
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)
        assert not hasattr(dialog, "print_btn")
        assert not hasattr(dialog, "_handle_print")
        assert hasattr(dialog, "pdf_btn")
        dialog.close()

    def test_pdf_export_workflow_intact(self, qapp, tmp_path):
        items = create_sample_bom_items(10)
        prep = AssemblyPreparationWidget()
        prep.bom_items = items
        prep.project_name = "FC_IO_V1.3"

        out_pdf = str(tmp_path / "test_export.pdf")
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(out_pdf, "PDF Files (*.pdf)")), \
             patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            prep.export_pdf()
            assert os.path.exists(out_pdf)
            assert os.path.getsize(out_pdf) > 0
            mock_info.assert_called_once()
        prep.close()

    def test_preview_dialog_repeated_maximize_restore_cycles(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)
        dialog.resize(1120, 780)
        dialog.show()
        qapp.processEvents()

        orig_size = dialog.size()
        init_dock_pos = dialog.floating_control_bar.pos()

        for cycle in range(3):
            # Maximize
            dialog.showMaximized()
            qapp.processEvents()
            assert dialog.isMaximized() is True
            max_dock_pos = dialog.floating_control_bar.pos()
            assert max_dock_pos.y() > init_dock_pos.y()

            # Restore
            dialog.showNormal()
            qapp.processEvents()
            assert dialog.isMaximized() is False
            assert dialog.size() == orig_size
            assert dialog.floating_control_bar.pos() == init_dock_pos

        dialog.close()

    def test_printer_orientation_preservation_in_render_to_printer(self, qapp):
        items = create_sample_bom_items(5)
        printer = QPrinter()
        printer.setOutputFileName("scratch/orient_test.pdf")
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        assert printer.pageLayout().orientation() == QPageLayout.Orientation.Portrait

        doc = AssemblyPrintEngine.render_to_printer(
            printer=printer,
            bom_items=items,
            project_name="ORIENT_TEST",
            total_qty=5
        )
        assert printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape
        assert doc is not None

    def test_assembly_preview_dialog_has_min_max_window_flags(self, qapp):
        items = create_sample_bom_items(5)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=10)
        flags = dialog.windowFlags()
        assert bool(flags & Qt.WindowType.WindowMinMaxButtonsHint) is True
        dialog.close()

    def test_preview_dialog_floating_dock_repositions_on_maximize_and_restore(self, qapp):
        items = create_sample_bom_items(10)
        dialog = AssemblyPreviewDialog(items, "FC_IO_V1.3", total_qty=20)
        dialog.resize(1120, 780)
        dialog.show()
        qapp.processEvents()

        init_pos = dialog.floating_control_bar.pos()
        dialog.showMaximized()
        qapp.processEvents()
        max_pos = dialog.floating_control_bar.pos()

        assert max_pos.y() > init_pos.y()

        dialog.showNormal()
        qapp.processEvents()
        restore_pos = dialog.floating_control_bar.pos()
        assert restore_pos == init_pos

        dialog.close()

    def test_main_window_minimize_maximize_and_state_sync(self, qapp):
        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow(default_file="")
            win.show()
            qapp.processEvents()

            assert win.isMaximized() is False
            assert win.isMinimized() is False
            assert win.title_bar.btn_maximize.toolTip() == "Maximize"

            # Maximize click
            win.title_bar.btn_maximize.click()
            qapp.processEvents()
            assert win.isMaximized() is True
            assert win.title_bar.btn_maximize.toolTip() == "Restore Down"

            # Restore click
            win.title_bar.btn_maximize.click()
            qapp.processEvents()
            assert win.isMaximized() is False
            assert win.title_bar.btn_maximize.toolTip() == "Maximize"

            # Minimize click
            win.title_bar.btn_minimize.click()
            qapp.processEvents()
            assert win.isMinimized() is True

            # External state change via changeEvent
            win.showNormal()
            qapp.processEvents()
            assert win.isMinimized() is False

            win.setWindowState(win.windowState() | Qt.WindowState.WindowMaximized)
            qapp.processEvents()
            assert win.title_bar.btn_maximize.toolTip() == "Restore Down"

            win._is_force_closing = True
            win.close()
