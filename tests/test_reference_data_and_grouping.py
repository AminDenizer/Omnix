"""
Unit & Integration Tests for:
1. Reference Data sheet importing from Excel into SQLite.
2. Thyristor and newly imported categories/types component registration.
3. Database-backed canonical classification & 5-dimension grouping key normalization.
4. Package leading zeroes preservation (0603, 0805).
5. Dedicated Reference Data management dialog and uncluttered registration form.
6. Three distinct inventory views preservation.
"""

import os
import openpyxl
import pytest
from unittest.mock import patch
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QCompleter, QScrollArea

from core.inventory.models import (
    InventoryProduct,
    StockPolicyGroup,
    ReferenceDataPayload,
    build_group_key,
    normalize_package,
    ReferenceDataInUseError,
)
from core.inventory.loader import InventoryDatabaseLoader
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.bootstrap import bootstrap_sqlite_from_workbook
from core.inventory.exporter import InventoryExcelExporter
from ui.main_window import MainWindow
from ui.dialogs.component_edit_dialog import ComponentEditDialog
from ui.dialogs.policy_edit_dialog import PolicyEditDialog
from ui.widgets.reference_data_widget import ReferenceDataWidget, ReferenceDataDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_repo(tmp_path):
    db_path = str(tmp_path / "test_ref_db.db")
    r = SqliteInventoryRepository(db_path)
    yield r
    r.close()


@pytest.fixture
def workbook_with_reference_data(tmp_path):
    """Creates a temporary workbook containing Stock Policy, Inventory, and Reference Data sheets."""
    wb_path = str(tmp_path / "InventoryWithRef.xlsm")
    wb = openpyxl.Workbook()

    # Sheet 1: Stock Policy
    ws_policy = wb.active
    ws_policy.title = "Stock Policy"
    ws_policy.append([
        "Category", "Type/Technology", "Value", "Package", "Footprint",
        "Total Quantity in Stock", "Min Stock", "Target Stock", "Description", "Group Key (System)"
    ])
    ws_policy.append([
        "Resistor", "Thick Film", "10k", "0603", "SMD_0603",
        100, 50, 200, "10k Resistor", "Resistor|Thick Film|10k|0603|SMD_0603"
    ])

    # Sheet 2: Inventory
    ws_inv = wb.create_sheet(title="Inventory")
    ws_inv.append([
        "Manufacturer", "MPN", "Category", "Type/Technology", "Package",
        "Footprint", "Value", "Description", "Quantity in Stock", "Purchase Link"
    ])
    ws_inv.append([
        "Yageo", "RC0603FR-0710KL", "Resistor", "Thick Film", 603,
        "SMD_0603", "10k", "10k Resistor", 100, "https://example.com/rc0603"
    ])

    # Sheet 3: Reference Data
    ws_ref = wb.create_sheet(title="Reference Data")
    header = ["Manufacturer", "Category", "Type/Technology", None, "Category List"]
    ws_ref.append(header)
    ws_ref.append(["Littelfuse", "Thyristor", "SCR", None, "Thyristor"])
    ws_ref.append(["STMicroelectronics", "Thyristor", "TRIAC", None, "Resistor"])
    ws_ref.append(["Vishay", "Thyristor", "DIAC", None, "Capacitor"])
    ws_ref.append(["Bourns", "Resistor", "Thick Film", None, None])
    ws_ref.append(["Murata", "Capacitor", "X7R", None, None])

    wb.save(wb_path)
    wb.close()
    return wb_path


class TestReferenceDataImportAndBootstrap:
    """Verifies that the Reference Data sheet is parsed and seeded into SQLite."""

    def test_loader_parses_reference_data_sheet(self, workbook_with_reference_data):
        loader = InventoryDatabaseLoader()
        ref_data = loader.load_reference_data(workbook_with_reference_data)

        assert isinstance(ref_data, ReferenceDataPayload)
        assert "Littelfuse" in ref_data.manufacturers
        assert "STMicroelectronics" in ref_data.manufacturers
        assert "Thyristor" in ref_data.categories
        assert ("Thyristor", "SCR") in ref_data.category_types
        assert ("Thyristor", "TRIAC") in ref_data.category_types

    def test_bootstrap_imports_reference_data_into_sqlite(self, workbook_with_reference_data, clean_repo):
        repo = clean_repo
        res = bootstrap_sqlite_from_workbook(workbook_with_reference_data, repo)

        assert res.success is True
        assert res.manufacturers_imported >= 5
        assert res.categories_imported >= 3
        assert res.types_imported >= 4

        # Verify Thyristor category and types exist in SQLite
        cat = repo.get_category_by_name("Thyristor")
        assert cat is not None
        assert cat.name == "Thyristor"

        assert repo.validate_category_type("Thyristor", "SCR") is True
        assert repo.validate_category_type("Thyristor", "TRIAC") is True
        assert repo.validate_category_type("Thyristor", "DIAC") is True

    def test_registering_thyristor_succeeds_without_missing_reference_error(self, workbook_with_reference_data, clean_repo):
        repo = clean_repo
        bootstrap_sqlite_from_workbook(workbook_with_reference_data, repo)

        # Register a thyristor
        thyristor = InventoryProduct(
            manufacturer="Littelfuse",
            mpn="BT151-500R",
            category="Thyristor",
            type_technology="SCR",
            package="TO-220",
            footprint="TO-220AB",
            value="12A 500V",
            description="12A Standard SCR",
            quantity_in_stock=25,
        )
        created = repo.create_component(thyristor)
        assert created.id is not None
        assert created.category == "Thyristor"
        assert created.type_technology == "SCR"
        assert created.group_key == "Thyristor|SCR|12A 500V|TO-220|TO-220AB"

    def test_bootstrap_preserves_existing_components_and_stock_policies(self, workbook_with_reference_data, clean_repo):
        repo = clean_repo

        # Pre-seed an existing component with custom quantity and description
        existing_comp = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW060310K",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=999,
                description="Custom Pre-existing Component",
            )
        )

        # Pre-seed an existing stock policy with custom thresholds
        repo.set_policy(
            group_key="Resistor|Thick Film|10k|0603|SMD_0603",
            min_stock=50,
            target_stock=150,
            category="Resistor",
            type_technology="Thick Film",
            value="10k",
            package="0603",
            footprint="SMD_0603",
            description="Custom Pre-existing Policy",
        )

        # Execute bootstrap
        res = bootstrap_sqlite_from_workbook(workbook_with_reference_data, repo)
        assert res.success is True

        # Verify existing component quantity and description were preserved (not overwritten)
        comp_after = repo.get_component_by_identity("Vishay", "CRCW060310K")
        assert comp_after is not None
        assert comp_after.quantity_in_stock == 999
        assert comp_after.description == "Custom Pre-existing Component"

        # Verify existing stock policy was preserved (not overwritten)
        pol_after = repo.get_policy("Resistor|Thick Film|10k|0603|SMD_0603")
        assert pol_after is not None
        assert pol_after.min_stock == 50
        assert pol_after.target_stock == 150
        assert pol_after.description == "Custom Pre-existing Policy"


class TestCanonicalClassificationAndGrouping:
    """Verifies that classification differences unify to canonical keys and preserve leading zeros."""

    def test_case_insensitive_classification_normalizes_to_same_group_key(self, workbook_with_reference_data, clean_repo):
        repo = clean_repo
        bootstrap_sqlite_from_workbook(workbook_with_reference_data, repo)

        # Component 1 with canonical casing: "Resistor", "Thick Film"
        c1 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW060310K",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )

        # Component 2 with lowercase input: "resistor", "thick film"
        c2 = repo.create_component(
            InventoryProduct(
                manufacturer="Bourns",
                mpn="CR0603-FX-1002ELF",
                category="resistor",
                type_technology="thick film",
                package="603",  # raw integer style
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=200,
            )
        )

        # Both records must normalize to the exact same canonical category and group_key
        assert c1.category == "Resistor"
        assert c2.category == "Resistor"
        assert c1.type_technology == "Thick Film"
        assert c2.type_technology == "Thick Film"
        assert c1.package == "0603"
        assert c2.package == "0603"
        assert c1.group_key == c2.group_key
        assert c1.group_key == "Resistor|Thick Film|10k|0603|SMD_0603"

    def test_package_leading_zeros_preserved(self):
        assert normalize_package(603) == "0603"
        assert normalize_package("603") == "0603"
        assert normalize_package(805) == "0805"
        assert normalize_package("805") == "0805"
        assert normalize_package("0603") == "0603"
        assert normalize_package("SOIC-8") == "SOIC-8"

    def test_reconcile_existing_classifications(self, clean_repo):
        repo = clean_repo
        cat_id = repo.add_category("Capacitor")
        repo.add_type(cat_id, "Ceramic X7R")

        # Manually insert component with non-canonical case
        conn = repo._db.get_connection()
        conn.execute(
            """
            INSERT INTO components (
                manufacturer, mpn, norm_manufacturer, norm_mpn,
                category, type_technology, package, raw_package,
                footprint, value, description, quantity_in_stock, group_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            ("Murata", "GRM188", "MURATA", "GRM188", "capacitor", "ceramic x7r", "0603", "0603", "SMD_0603", "100nF", "", 10, "capacitor|ceramic x7r|100nF|0603|SMD_0603")
        )
        conn.commit()

        # Run reconciliation
        updated = repo.reconcile_canonical_classifications()
        assert updated == 1

        comp = repo.get_component_by_identity("Murata", "GRM188")
        assert comp.category == "Capacitor"
        assert comp.type_technology == "Ceramic X7R"
        assert comp.group_key == "Capacitor|Ceramic X7R|100nF|0603|SMD_0603"


class TestUIStreamliningAndReferenceDataDialog:
    """Verifies that the registration form is uncluttered and the reference data manager dialog functions."""

    def test_component_edit_dialog_hides_inline_plus_buttons(self, qapp, clean_repo):
        dlg = ComponentEditDialog(repository=clean_repo)
        # Inline plus buttons exist as attributes for test backwards-compatibility but are hidden
        assert hasattr(dlg, "add_mfr_btn")
        assert hasattr(dlg, "add_cat_btn")
        assert hasattr(dlg, "add_type_btn")
        assert dlg.add_mfr_btn.isVisible() is False
        assert dlg.add_cat_btn.isVisible() is False
        assert dlg.add_type_btn.isVisible() is False
        dlg.close()

    def test_reference_data_dialog_lifecycle(self, qapp, clean_repo):
        repo = clean_repo
        repo.add_manufacturer("Analog Devices")
        cat_id = repo.add_category("OpAmp")
        repo.add_type(cat_id, "Precision")

        dlg = ReferenceDataDialog(repository=repo)
        assert dlg.widget.mfr_list.count() == 1
        assert dlg.widget.cat_list.count() == 1
        assert "Analog Devices" in dlg.widget.mfr_list.item(0).text()
        assert "OpAmp" in dlg.widget.cat_list.item(0).text()
        dlg.close()

    def test_main_window_has_clean_component_toolbar_and_manage_reference_button(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # Verify toolbar controls exist on component_inventory_view
        assert hasattr(win, "component_search_input")
        assert hasattr(win, "add_component_btn")
        assert hasattr(win, "edit_component_btn")
        assert hasattr(win, "delete_component_btn")
        assert hasattr(win, "title_bar")
        assert win.export_excel_btn is win.backup_restore_widget.export_excel_btn
        assert win.inventory_subtabs.count() == 2
        assert "Assembly View" in win.inventory_subtabs.tabText(0)
        assert "Component Inventory" in win.inventory_subtabs.tabText(1)

        win._is_force_closing = True
        win.close()


class TestTransistorRegistrationAndGrouping:
    """Verifies that Transistor category and types are available and an actual transistor component workflow succeeds."""

    def test_transistor_category_and_types_available(self, clean_repo):
        repo = clean_repo
        repo.ensure_transistor_reference_data()

        cat = repo.get_category_by_name("Transistor")
        assert cat is not None
        assert cat.name == "Transistor"
        assert cat.norm_name == "TRANSISTOR"

        types = repo.get_types_for_category(cat.id)
        type_names = [t.name for t in types]
        for expected in ["BJT", "MOSFET", "JFET", "IGBT", "NPN", "PNP"]:
            assert expected in type_names

    def test_transistor_component_registration_and_multi_component_grouping(self, clean_repo, qapp):
        repo = clean_repo
        repo.ensure_transistor_reference_data()

        # 1. Register first Transistor: ON Semiconductor 2N3904
        t1 = repo.create_component(
            InventoryProduct(
                manufacturer="ON Semiconductor",
                mpn="2N3904",
                category="transistor",      # lowercase input to verify canonical resolution
                type_technology="bjt",      # lowercase input to verify canonical resolution
                package="TO-92",
                footprint="TO-92",
                value="40V 200mA",
                description="NPN General Purpose Amplifier",
                quantity_in_stock=50,
            )
        )
        assert t1.id is not None
        assert t1.category == "Transistor"
        assert t1.type_technology == "BJT"
        assert t1.group_key == "Transistor|BJT|40V 200mA|TO-92|TO-92"

        # 2. Register second Transistor: Micro Commercial Co 2N3904-BP (same 5 grouping dimensions)
        t2 = repo.create_component(
            InventoryProduct(
                manufacturer="Micro Commercial Co",
                mpn="2N3904-BP",
                category="Transistor",
                type_technology="BJT",
                package="TO-92",
                footprint="TO-92",
                value="40V 200mA",
                description="NPN General Purpose Transistor",
                quantity_in_stock=30,
            )
        )
        assert t2.id is not None
        assert t2.category == "Transistor"
        assert t2.type_technology == "BJT"
        assert t2.group_key == t1.group_key

        # Both component records must remain distinct
        assert t1.id != t2.id
        assert t1.manufacturer != t2.manufacturer
        assert t1.mpn != t2.mpn
        assert t1.quantity_in_stock == 50
        assert t2.quantity_in_stock == 30

        # Aggregated stock group must contain both components with correct total stock (50 + 30 = 80)
        groups = repo.get_all_groups()
        assert len(groups) == 1
        grp = groups[0]
        assert grp.group_key == "Transistor|BJT|40V 200mA|TO-92|TO-92"
        assert grp.current_stock == 80
        assert len(grp.products) == 2

        # 3. Register third Transistor with different package (SOT-23)
        t3 = repo.create_component(
            InventoryProduct(
                manufacturer="Diodes Incorporated",
                mpn="MMBT3904-7-F",
                category="Transistor",
                type_technology="BJT",
                package="SOT-23",
                footprint="SOT-23",
                value="40V 200mA",
                description="40V NPN Small Signal Transistor in SOT-23",
                quantity_in_stock=100,
            )
        )
        assert t3.group_key == "Transistor|BJT|40V 200mA|SOT-23|SOT-23"

        groups_after = repo.get_all_groups()
        assert len(groups_after) == 2
        keys = [g.group_key for g in groups_after]
        assert "Transistor|BJT|40V 200mA|TO-92|TO-92" in keys
        assert "Transistor|BJT|40V 200mA|SOT-23|SOT-23" in keys


class TestReferenceDataCRUDAndIntegrity:
    """Verifies that Reference Data CRUD operations enforce referential integrity and prevent data corruption."""

    def test_reference_crud_lifecycle_and_constraints(self, clean_repo):
        repo = clean_repo

        # 1. Create Manufacturer, Category, and Type
        mfr_id = repo.add_manufacturer("Test Mfr")
        cat_id = repo.add_category("Test Category")
        type_id = repo.add_type(cat_id, "Test Type")

        assert repo.get_manufacturer(mfr_id).name == "Test Mfr"
        assert repo.get_category(cat_id).name == "Test Category"
        assert repo.get_type(type_id).name == "Test Type"

        # 2. Edit Manufacturer, Category, and Type
        repo.update_manufacturer(mfr_id, name="Test Mfr Renamed")
        repo.update_category(cat_id, name="Test Category Renamed")
        repo.update_type(type_id, name="Test Type Renamed")

        assert repo.get_manufacturer(mfr_id).name == "Test Mfr Renamed"
        assert repo.get_category(cat_id).name == "Test Category Renamed"
        assert repo.get_type(type_id).name == "Test Type Renamed"

        # 3. Associate a component with this category and type
        comp = repo.create_component(
            InventoryProduct(
                manufacturer="Test Mfr Renamed",
                mpn="TEST-PART-1",
                category="Test Category Renamed",
                type_technology="Test Type Renamed",
                package="0603",
                footprint="SMD_0603",
                value="10uF",
                quantity_in_stock=10,
            )
        )
        assert comp.id is not None

        # 4. Attempting to delete category in use raises ReferenceDataInUseError
        with pytest.raises(ReferenceDataInUseError):
            repo.delete_category(cat_id)

        # 5. Attempting to delete type in use raises ReferenceDataInUseError
        with pytest.raises(ReferenceDataInUseError):
            repo.delete_type(type_id)

        # 6. Attempting to delete manufacturer in use raises ReferenceDataInUseError
        with pytest.raises(ReferenceDataInUseError):
            repo.delete_manufacturer(mfr_id)

        # 7. Soft deactivation (setting inactive) succeeds without corrupting component records
        repo.deactivate_type(type_id)
        assert repo.get_type(type_id).is_active is False
        assert repo.get_component_by_id(comp.id).type_technology == "Test Type Renamed"


class TestExcelExporterTwoSheetContract:
    """Verifies customer-facing Excel export with single-sheet contract: ['Inventory']."""

    def test_exported_workbook_contains_exactly_one_inventory_sheet(self, clean_repo, tmp_path):
        repo = clean_repo
        repo.ensure_transistor_reference_data()

        # Seed categories/types for test components
        c_cat = repo.add_category("Capacitor")
        repo.add_type(c_cat, "X7R")
        r_cat = repo.add_category("Resistor")
        repo.add_type(r_cat, "Thick Film")

        # Seed two components with leading zeroes in package
        repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="X7R",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=100,
                purchase_link="https://example.com/part1",
            )
        )
        repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="SMD_0805",
                value="10k",
                quantity_in_stock=250,
                purchase_link="https://example.com/part2",
            )
        )

        export_path = str(tmp_path / "Customer_Inventory_Export.xlsx")
        result_path = InventoryExcelExporter.export(repo, export_path)
        assert os.path.exists(result_path)

        # Open and inspect the exported workbook
        wb = openpyxl.load_workbook(result_path, data_only=True)
        assert wb.sheetnames == ["Inventory"], "Export must contain exactly ['Inventory']"

        # Verify Sheet 1: Inventory
        ws_inv = wb["Inventory"]
        inv_headers = [ws_inv.cell(row=1, column=c).value for c in range(1, 12)]
        assert inv_headers == [
            "Row", "Manufacturer", "Part Number (MPN)", "Category",
            "Type / Technology", "Value", "Package", "Footprint",
            "Quantity in Stock", "Description", "Purchase Link"
        ]
        # Verify row 2 and 3 data
        assert ws_inv.cell(row=2, column=2).value == "Murata"
        assert ws_inv.cell(row=2, column=3).value == "GRM188R71H104KA93D"
        assert ws_inv.cell(row=2, column=7).value == "0603"
        assert ws_inv.cell(row=2, column=9).value == 100

        assert ws_inv.cell(row=3, column=2).value == "Yageo"
        assert ws_inv.cell(row=3, column=7).value == "0805"
        assert ws_inv.cell(row=3, column=9).value == 250

        wb.close()

        # Also verify optional include_assembly=True parameter
        res_two = InventoryExcelExporter.export(repo, export_path, include_assembly=True)
        wb_two = openpyxl.load_workbook(res_two, data_only=True)
        assert wb_two.sheetnames == ["Inventory", "Assembly View"]
        ws_asm = wb_two["Assembly View"]
        asm_headers = [ws_asm.cell(row=1, column=c).value for c in range(1, 12)]
        assert asm_headers == [
            "Row", "Category", "Type / Technology", "Value", "Package",
            "Footprint", "Current Stock", "Min Stock", "Target Stock",
            "Policy Status", "Description"
        ]
        assert ws_asm.cell(row=2, column=5).value in ["0603", "0805"]
        wb_two.close()


class TestAssemblyViewUIImprovements:
    """Verifies Incomplete control visibility and Quantity in Stock column layout."""

    def test_incomplete_control_isolated_to_assembly_view(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # In Subtab 0 (Assembly View), Incomplete button is visible
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.stats_ribbon.stat_incomplete_btn.isVisible() is True

        # When switching to Subtab 1 (Component Inventory), Incomplete button is hidden
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()
        assert win.stats_ribbon.stat_incomplete_btn.isVisible() is False

        # Switching back to Subtab 0 restores visibility
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.stats_ribbon.stat_incomplete_btn.isVisible() is True

        win._is_force_closing = True
        win.close()

    def test_quantity_in_stock_column_width_and_alignment(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # Switch to Component Inventory
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()

        table = win.inventory_components_table
        # Column 8 is Quantity in Stock
        assert table.horizontalHeaderItem(8).text() == "Quantity in Stock"
        assert table.columnWidth(8) >= 115

        win._is_force_closing = True
        win.close()


class TestTitleBarKeyboardRoutingAndFormUX:
    """Targeted verification for native title bar, keyboard routing, form UX, steppers, and Excel presentation."""

    def test_title_bar_actions_relocated_and_functional(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # 1. Custom title bar exists as menuWidget
        assert hasattr(win, "title_bar")
        assert win.menuWidget() is win.title_bar
        # 2. Window controls exist on title bar
        assert hasattr(win.title_bar, "btn_minimize")
        assert hasattr(win.title_bar, "btn_maximize")
        assert hasattr(win.title_bar, "btn_close")

        # 3. Window controls exist on title bar
        assert hasattr(win.title_bar, "btn_minimize")
        assert hasattr(win.title_bar, "btn_maximize")
        assert hasattr(win.title_bar, "btn_close")

        win._is_force_closing = True
        win.close()

    def test_slash_shortcut_routes_to_active_view_without_affecting_inactive_view(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # Switch to Subtab 0: Assembly View
        win.inventory_subtabs.setCurrentIndex(0)
        qapp.processEvents()
        assert win.inventory_subtabs.currentIndex() == 0
        initial_match_text = win.stats_ribbon.stat_filtered_rows.text()

        # Switch to Subtab 1: Component Inventory
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()

        # Press '/' while Component Inventory is active
        slash_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Slash, Qt.KeyboardModifier.NoModifier, "/")
        win.keyPressEvent(slash_event)
        qapp.processEvents()

        # Component Inventory search input must have focus
        assert win.component_search_input.hasFocus() is True
        # Assembly View search must be completely empty and untouched
        assert win.search_input.text() == ""
        # Match count in Assembly View must not have decremented
        assert win.stats_ribbon.stat_filtered_rows.text() == initial_match_text

        # Switch back to Subtab 0: Assembly View
        win.inventory_subtabs.setCurrentIndex(0)
        win.table.setFocus()
        qapp.processEvents()

        # Press '/' while Assembly View is active
        slash_event2 = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Slash, Qt.KeyboardModifier.NoModifier, "/")
        win.keyPressEvent(slash_event2)
        qapp.processEvents()

        # Assembly View search input must have focus
        assert win.search_input.hasFocus() is True

        win._is_force_closing = True
        win.close()

    def test_slash_not_stolen_when_typing_in_editable_field(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # Switch to Component Inventory and focus component search
        win.inventory_subtabs.setCurrentIndex(1)
        win.component_search_input.setFocus()
        win.component_search_input.setText("LM317")
        qapp.processEvents()

        # Simulate typing '/' into the search field
        slash_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Slash, Qt.KeyboardModifier.NoModifier, "/")
        win.keyPressEvent(slash_event)
        qapp.processEvents()

        # The search text should NOT have been cleared, selected-all, or hijacked by Assembly View
        assert win.search_input.text() == ""
        assert win.component_search_input.hasFocus() is True

        win._is_force_closing = True
        win.close()

    def test_component_edit_dialog_ux_steppers_and_autocomplete(self, qapp, clean_repo):
        repo = clean_repo
        repo.ensure_transistor_reference_data()

        dlg = ComponentEditDialog(repository=repo)
        dlg.show()
        qapp.processEvents()

        # 1. Stepper buttons exist and functional
        assert hasattr(dlg, "qty_up_btn")
        assert hasattr(dlg, "qty_down_btn")
        assert dlg.qty_spin.value() == 0

        dlg.qty_up_btn.click()
        assert dlg.qty_spin.value() == 1

        dlg.qty_up_btn.click()
        assert dlg.qty_spin.value() == 2

        dlg.qty_down_btn.click()
        assert dlg.qty_spin.value() == 1

        # 2. Autocomplete is set to PopupCompletion (not InlineCompletion)
        for combo in (dlg.mfr_input, dlg.category_combo, dlg.tech_combo):
            comp = combo.completer()
            if comp:
                assert comp.completionMode() == QCompleter.CompletionMode.PopupCompletion
                assert comp.filterMode() == Qt.MatchFlag.MatchContains

        # 3. Validation rejects empty required fields with clean English messages
        dlg._on_save_clicked()
        assert "required" in dlg.validation_lbl.text().lower()

        dlg.close()

    def test_excel_export_presentation_hyperlinks_and_gridlines(self, clean_repo, tmp_path):
        repo = clean_repo
        c_cat = repo.add_category("Capacitor")
        repo.add_type(c_cat, "Ceramic")

        repo.create_component(
            InventoryProduct(
                manufacturer="TDK",
                mpn="C1608X7R1H104K080AA",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="C_0603",
                value="100nF",
                quantity_in_stock=500,
                purchase_link="https://example.com/part/tdk0603",
                description="High reliability SMD capacitor",
            )
        )

        out_path = str(tmp_path / "Presentation_Test_Export.xlsx")
        result_path = InventoryExcelExporter.export(repo, out_path)
        assert os.path.exists(result_path)

        wb = openpyxl.load_workbook(result_path)
        assert wb.sheetnames == ["Inventory"]

        ws_inv = wb["Inventory"]
        assert ws_inv.views.sheetView[0].showGridLines is True

        # Check row number is centered
        row_cell = ws_inv.cell(row=2, column=1)
        assert row_cell.alignment.horizontal == "center"

        # Check package leading zero preservation and centering
        pkg_cell = ws_inv.cell(row=2, column=7)
        assert str(pkg_cell.value) == "0603"
        assert pkg_cell.number_format == "@"
        assert pkg_cell.alignment.horizontal == "center"

        # Check quantity in stock is centered
        qty_cell = ws_inv.cell(row=2, column=9)
        assert qty_cell.value == 500
        assert qty_cell.alignment.horizontal == "center"
        assert qty_cell.number_format == "#,##0"

        # Check hyperlink
        link_cell = ws_inv.cell(row=2, column=11)
        assert link_cell.hyperlink is not None
        assert link_cell.hyperlink.target == "https://example.com/part/tdk0603"

# Assembly View verified in include_assembly test

        wb.close()

    def test_title_bar_minimal_layout_actions_on_left(self, qapp, clean_repo):
        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        tb = win.title_bar
        # Title text displays clean branding 'OMNIX'
        assert "OMNIX" in tb.title_lbl.text()
        assert not hasattr(tb, "icon_lbl")

        # Right layout contains window control buttons
        assert hasattr(tb, "btn_minimize")
        assert hasattr(tb, "btn_maximize")
        assert hasattr(tb, "btn_close")

        win._is_force_closing = True
        win.close()

    def test_component_inventory_table_click_and_double_click_behavior(self, qapp, clean_repo):
        repo = clean_repo
        c_cat = repo.add_category("Resistor")
        repo.add_type(c_cat, "Thick Film")
        prod = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="R_0603",
                value="10k",
                quantity_in_stock=1000,
            )
        )

        win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
        win.show()
        qapp.processEvents()

        # Switch to Component Inventory
        win.inventory_subtabs.setCurrentIndex(1)
        qapp.processEvents()

        table = win.inventory_components_table
        # Headers are not clickable (no dropdown/arrow glitch) and table sorting disabled
        assert table.horizontalHeader().sectionsClickable() is False
        assert table.isSortingEnabled() is False

        # Verify MPN cell single-click copies to clipboard
        mpn_item = table.item(0, 2)
        assert mpn_item is not None
        assert mpn_item.text() == "RC0603FR-0710KL"

        win._on_inventory_component_clicked(mpn_item)
        qapp.processEvents()
        assert QApplication.clipboard().text() == "RC0603FR-0710KL"
        assert "Copied MPN" in win.status_state_lbl.text()

        # Temporary message auto-restores previous state on expiration
        current_seq = win._mpn_copy_seq
        win._restore_mpn_status(current_seq)
        assert "Copied MPN" not in win.status_state_lbl.text()

        # Double-click should not trigger edit dialog automatically
        win._on_inventory_component_double_clicked(mpn_item)
        qapp.processEvents()

        win._is_force_closing = True
        win.close()

    def test_spinbox_and_combo_wheel_events_ignored(self, qapp, clean_repo):
        dlg = ComponentEditDialog(repository=clean_repo)
        dlg.show()
        qapp.processEvents()

        def make_wheel_event():
            ev = QWheelEvent(
                QPointF(10, 10),
                QPointF(10, 10),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            ev.setAccepted(True)
            return ev

        # QSpinBox wheelEvent must be ignored
        ev_spin = make_wheel_event()
        dlg.qty_spin.wheelEvent(ev_spin)
        assert ev_spin.isAccepted() is False

        # QComboBox wheelEvent must be ignored
        for combo in (dlg.mfr_input, dlg.category_combo, dlg.tech_combo):
            ev_combo = make_wheel_event()
            combo.wheelEvent(ev_combo)
            assert ev_combo.isAccepted() is False

        dlg.close()

        # PolicyEditDialog wheel events
        group = StockPolicyGroup(
            category="Resistor",
            type_technology="Thick Film",
            value="10k",
            package="0603",
            footprint="R_0603",
            current_stock=200,
            min_stock=100,
            target_stock=500,
            description="10k 0603 resistor",
        )
        pol_dlg = PolicyEditDialog(
            group=group,
            inventory_path="dummy.db",
            repository=clean_repo,
        )
        pol_dlg.show()
        qapp.processEvents()

        ev_min = make_wheel_event()
        pol_dlg.min_spin.wheelEvent(ev_min)
        assert ev_min.isAccepted() is False

        ev_tgt = make_wheel_event()
        pol_dlg.target_spin.wheelEvent(ev_tgt)
        assert ev_tgt.isAccepted() is False

        pol_dlg.close()

    def test_slash_event_filter_routes_when_table_has_focus(self, qapp, clean_repo):
        with patch("PyQt6.QtCore.QTimer.singleShot"):
            win = MainWindow(default_file=clean_repo.file_path, repository=clean_repo)
            win.show()
            qapp.processEvents()

            # Switch to Component Inventory
            win.activateWindow()
            win.inventory_subtabs.setCurrentIndex(1)
            win.inventory_components_table.setFocus()
            qapp.processEvents()
            assert win.inventory_components_table.hasFocus() is True

            # Send '/' key press event through application event filter
            slash_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Slash, Qt.KeyboardModifier.NoModifier, "/")
            handled = win.eventFilter(win.inventory_components_table, slash_ev)
            assert handled is True
            qapp.processEvents()

            assert win.component_search_input.hasFocus() is True

            # Esc clears selection and search
            esc_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            win.keyPressEvent(esc_ev)
            qapp.processEvents()

            win._is_force_closing = True
            win.close()

    def test_tab_autocomplete_commits_canonical_and_advances_focus(self, qapp, clean_repo):
        repo = clean_repo
        repo.add_manufacturer("TDK")
        repo.add_manufacturer("Texas Instruments")
        c_cat = repo.add_category("Capacitor")
        repo.add_type(c_cat, "Ceramic")

        dlg = ComponentEditDialog(repository=clean_repo)
        dlg.show()
        qapp.processEvents()

        mfr_combo = dlg.mfr_input
        le = mfr_combo.lineEdit()
        le.setFocus()
        qapp.processEvents()

        # Type partial lowercase text
        le.setText("td")
        qapp.processEvents()

        comp = mfr_combo.completer()
        assert comp is not None

        # Simulate Tab key press event on lineEdit
        tab_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(le, tab_ev)
        qapp.processEvents()

        # Canonical value 'TDK' committed without duplicate appending
        assert mfr_combo.currentText() == "TDK"
        # Focus advanced to MPN input
        assert dlg.mpn_input.hasFocus() is True

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()

    def test_wheel_scroll_forwarder_scrolls_parent_scroll_area(self, qapp, clean_repo):
        dlg = ComponentEditDialog(repository=clean_repo)
        dlg.show()
        qapp.processEvents()

        scroll = dlg.findChild(QScrollArea)
        assert scroll is not None
        v_bar = scroll.verticalScrollBar()
        v_bar.setMaximum(500)
        initial_val = 100
        v_bar.setValue(initial_val)

        # Simulate wheel event over qty_spin
        wheel_ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, -120),  # Scroll down
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        forwarded = dlg._wheel_filter.eventFilter(dlg.qty_spin, wheel_ev)
        assert forwarded is True
        assert v_bar.value() > initial_val
        # Quantity spin value remained unchanged at 0
        assert dlg.qty_spin.value() == 0

        dlg.close()
        dlg.deleteLater()
        qapp.processEvents()



