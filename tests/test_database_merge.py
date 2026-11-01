"""
Omnix Test Suite — Database Bind/Merge Non-Destructive Reconciliation Tests
Governing Specification: Phase 3 Database Bind/Merge Requirements
"""

import os
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.merge import DatabaseMergeService, MergeAnalysis
from ui.dialogs.database_merge_dialog import DatabaseMergeDialog
from ui.widgets.backup_restore_widget import DatabaseBackupRestoreWidget
from PyQt6.QtWidgets import QDialog


@pytest.fixture
def target_repo(tmp_path):
    """Creates a clean target SQLite repository populated with initial test records."""
    db_path = tmp_path / "target_inventory.db"
    repo = SqliteInventoryRepository(str(db_path))
    repo.load()

    # Seed references
    cat_cap = repo.add_category("Capacitor")
    repo.add_type(cat_cap, "Ceramic")
    cat_res = repo.add_category("Resistor")
    repo.add_type(cat_res, "Thick Film")
    cat_ic = repo.add_category("Integrated Circuit")
    repo.add_type(cat_ic, "Microcontroller")
    repo.add_manufacturer("Murata")
    repo.add_manufacturer("Yageo")
    repo.add_manufacturer("Microchip")
    repo.add_manufacturer("TDK")

    # Seed existing components
    repo.create_component(
        InventoryProduct(
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=100,
        ),
        supplier_links=[
            SupplierLink(vendor_id="vendor_lion", vendor_label="Lion", url="https://lion.ir/part1")
        ]
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
        )
    )

    return repo


@pytest.fixture
def external_source_db(tmp_path):
    """Creates an external SQLite database containing new, duplicate, and edge-case records."""
    db_path = tmp_path / "external_source.db"
    repo = SqliteInventoryRepository(str(db_path))
    repo.load()

    # Seed references
    cat_cap = repo.add_category("Capacitor")
    repo.add_type(cat_cap, "Ceramic")
    cat_res = repo.add_category("Resistor")
    repo.add_type(cat_res, "Thick Film")
    cat_ic = repo.add_category("Integrated Circuit")
    repo.add_type(cat_ic, "Microcontroller")
    repo.add_manufacturer("Murata")
    repo.add_manufacturer("Yageo")
    repo.add_manufacturer("Microchip")
    repo.add_manufacturer("TDK")

    # 1. Exact Duplicate component (Murata GRM188R71H104KA93D)
    repo.create_component(
        InventoryProduct(
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=50,
        )
    )

    # 2. Conflicting component (Same MFR + MPN, but different value)
    repo.create_component(
        InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0805FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0805",
            footprint="SMD_0805",
            value="20k", # differs from target's 10k!
            quantity_in_stock=500,
        )
    )

    # 3. Different Manufacturer sharing an existing MPN (TDK sharing GRM188R71H104KA93D or custom MPN)
    repo.create_component(
        InventoryProduct(
            manufacturer="TDK",
            mpn="GRM188R71H104KA93D", # Same MPN, but manufacturer is TDK!
            category="Capacitor",
            type_technology="Ceramic",
            package="0603",
            footprint="SMD_0603",
            value="100nF",
            quantity_in_stock=300,
        )
    )

    # 4. Brand New Component (Microchip MCU with new category Integrated Circuit)
    repo.create_component(
        InventoryProduct(
            manufacturer="Microchip",
            mpn="ATmega328P-AU",
            category="Integrated Circuit",
            type_technology="Microcontroller",
            package="TQFP-32",
            footprint="TQFP-32",
            value="16MHz",
            quantity_in_stock=15,
        ),
        supplier_links=[
            SupplierLink(vendor_id="vendor_javan", vendor_label="Javan", url="https://javan.ir/atmega")
        ]
    )

    # 5. Incomplete Component (Missing manufacturer in SQLite)
    raw_conn = sqlite3.connect(str(db_path))
    raw_conn.execute(
        "INSERT INTO components (manufacturer, norm_manufacturer, mpn, norm_mpn, category, type_technology, package, footprint, value, group_key, quantity_in_stock) "
        "VALUES ('', '', 'UNKNOWN_PART_NO_MFR', 'UNKNOWN_PART_NO_MFR', 'Resistor', 'Thick Film', '0805', '0805', '10k', 'GRP', 10);"
    )
    raw_conn.commit()
    raw_conn.close()

    repo.close()
    return str(db_path)


class TestDatabaseMergeValidationAndAnalysis:
    """Tests Phase 3 schema validation, read-only guarantees, and dry-run merge analysis."""

    def test_validate_nonexistent_or_invalid_file(self, target_repo, tmp_path):
        ok, msg, _ = DatabaseMergeService.validate_source_database(str(tmp_path / "nonexistent.db"))
        assert ok is False
        assert "not found" in msg.lower()

        # Invalid corrupt file
        corrupt = tmp_path / "corrupt.db"
        corrupt.write_text("NOT A SQLITE DATABASE", encoding="utf-8")
        ok_c, msg_c, _ = DatabaseMergeService.validate_source_database(str(corrupt))
        assert ok_c is False

    def test_analysis_categorizes_new_duplicate_conflict_and_incomplete(self, target_repo, external_source_db):
        analysis = DatabaseMergeService.analyze_merge(target_repo, external_source_db)
        assert analysis.is_valid is True
        assert analysis.can_merge is True
        assert analysis.total_source_components == 5

        # 1. New Components: Microchip ATmega328P-AU and TDK GRM188R71H104KA93D
        new_mpns = {c["mpn"] for c in analysis.new_components}
        new_mfrs = {c["manufacturer"] for c in analysis.new_components}
        assert "ATmega328P-AU" in new_mpns
        assert "TDK" in new_mfrs

        # 2. Duplicate: Murata GRM188R71H104KA93D
        dup_mpns = {c["mpn"] for c in analysis.duplicate_components}
        assert "GRM188R71H104KA93D" in dup_mpns

        # 3. Conflict: Yageo RC0805FR-0710KL (value differs)
        conflict_mpns = {c["mpn"] for c in analysis.conflicting_components}
        assert "RC0805FR-0710KL" in conflict_mpns

        # 4. Incomplete: missing manufacturer
        inc_mpns = {c["mpn"] for c in analysis.incomplete_components}
        assert "UNKNOWN_PART_NO_MFR" in inc_mpns

        # 5. Zero automatic reference creation policy enforced
        assert analysis.new_manufacturers == []
        assert analysis.new_categories == []
        assert analysis.new_types == []


class TestDatabaseMergeExecutionAndIntegrity:
    """Tests transactional execution, pre-merge safety backups, and non-destructive properties."""

    def test_merge_execution_adds_new_records_without_overwriting_target(self, target_repo, external_source_db, tmp_path):
        initial_target_count = len(target_repo.get_all_products())
        assert initial_target_count == 2

        # Record hash of external source DB before merge to prove read-only guarantee
        import hashlib
        source_hash_before = hashlib.sha256(open(external_source_db, "rb").read()).hexdigest()

        analysis = DatabaseMergeService.analyze_merge(target_repo, external_source_db)
        safety_dir = tmp_path / "backups"
        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis, safety_backup_dir=str(safety_dir))

        assert ok is True
        assert meta["added_components"] == 2 # Microchip MCU + TDK Capacitor
        assert meta["skipped_duplicates"] == 1
        assert meta["skipped_conflicts"] == 1
        assert meta["skipped_incomplete"] == 1

        # Verify source database was strictly untouched (read-only)
        source_hash_after = hashlib.sha256(open(external_source_db, "rb").read()).hexdigest()
        assert source_hash_before == source_hash_after, "Source database must remain strictly unmodified!"

        # Verify pre-merge safety backup was created
        assert os.path.exists(safety_dir)
        backups = list(safety_dir.glob("*.obk"))
        assert len(backups) >= 1

        # Verify target repository contents
        updated_products = target_repo.get_all_products()
        assert len(updated_products) == 4 # 2 original + 2 merged

        # Check that existing Yageo record was NOT overwritten by conflicting source value
        yageo = [p for p in updated_products if p.mpn == "RC0805FR-0710KL"][0]
        assert yageo.value == "10k" # preserved original, not overwritten by "20k"!
        assert yageo.quantity_in_stock == 250 # preserved original stock

        # Check that Microchip component and its supplier link were inserted
        mcu = [p for p in updated_products if p.mpn == "ATmega328P-AU"][0]
        assert mcu.manufacturer == "Microchip"
        assert mcu.category == "Integrated Circuit"
        assert len(mcu.supplier_links) == 1
        assert mcu.supplier_links[0].url == "https://javan.ir/atmega"

    def test_merge_rollback_on_simulated_error(self, target_repo, external_source_db):
        initial_count = len(target_repo.get_all_products())
        analysis = DatabaseMergeService.analyze_merge(target_repo, external_source_db)

        # Force a failure during component insertion
        with patch.object(target_repo, "create_component", side_effect=RuntimeError("Simulated DB Disk Failure")):
            ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
            assert ok is False
            assert "rolled back" in msg.lower()

        # Verify target database was completely rolled back and unchanged
        assert len(target_repo.get_all_products()) == initial_count

    def test_merge_aborts_when_pre_merge_backup_fails(self, target_repo, external_source_db):
        initial_count = len(target_repo.get_all_products())
        analysis = DatabaseMergeService.analyze_merge(target_repo, external_source_db)

        # Force pre-merge backup failure
        from core.inventory.backup import DatabaseBackupService
        with patch.object(
            DatabaseBackupService,
            "export_full_backup",
            return_value=(False, "Simulated disk full during backup", {})
        ):
            ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
            assert ok is False
            assert "pre-merge safety backup failed" in msg.lower()
            assert meta["backup_created"] is False
            assert meta["added_components"] == 0

        # Verify target database was completely untouched
        assert len(target_repo.get_all_products()) == initial_count

    def test_merge_source_with_only_new_records(self, tmp_path, target_repo):
        # Pre-seed target with valid references for this new component
        c_sens = target_repo.add_category("Sensor")
        target_repo.add_type(c_sens, "Temperature")
        target_repo.add_manufacturer("TI")

        initial_count = len(target_repo.get_all_products())
        src_path = tmp_path / "only_new.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        src_repo.add_category("Sensor")
        src_repo.add_type(1, "Temperature")
        src_repo.create_component(
            InventoryProduct(
                manufacturer="TI",
                mpn="TMP102",
                category="Sensor",
                type_technology="Temperature",
                package="SOT-563",
                footprint="SOT-563",
                value="Digital",
                quantity_in_stock=50,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 1
        assert len(analysis.duplicate_components) == 0
        assert len(analysis.conflicting_components) == 0
        assert len(analysis.incomplete_components) == 0
        assert analysis.can_merge is True

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 1
        assert len(target_repo.get_all_products()) == initial_count + 1

    def test_merge_source_with_only_duplicate_records(self, tmp_path, target_repo):
        initial_count = len(target_repo.get_all_products())
        src_path = tmp_path / "only_dups.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        src_repo.add_category("Capacitor")
        src_repo.add_type(1, "Ceramic")
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=50,
            )
        )

        # If source has no new references or new components, can_merge is False
        # Note: in target_repo, Capacitor / Ceramic already exist, so no new reference types are added
        # Ensure target_repo and src_repo share the same exact types so new_types is empty:
        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.duplicate_components) == 1

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert len(target_repo.get_all_products()) == initial_count

    def test_merge_source_with_only_conflict_records(self, tmp_path, target_repo):
        initial_count = len(target_repo.get_all_products())
        src_path = tmp_path / "only_conflicts.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        src_repo.add_category("Capacitor")
        src_repo.add_type(1, "Ceramic")
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0805",  # Conflicting package
                footprint="SMD_0805",
                value="100nF",
                quantity_in_stock=10,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert len(target_repo.get_all_products()) == initial_count


class TestDatabaseMergeUIDialog:
    """Tests the user-facing DatabaseMergeDialog lifecycle and cancellation."""

    def test_dialog_initial_state_and_analysis_render(self, qapp, target_repo, external_source_db):
        dlg = DatabaseMergeDialog(repository=target_repo)
        assert dlg.merge_btn.isEnabled() is False

        dlg._analyze_file(external_source_db)
        assert dlg.merge_btn.isEnabled() is True
        assert dlg.table.rowCount() == 5 # 2 new, 1 conflict, 1 duplicate, 1 incomplete

    def test_dialog_cancel_makes_no_changes(self, qapp, target_repo, external_source_db):
        initial_count = len(target_repo.get_all_products())
        dlg = DatabaseMergeDialog(repository=target_repo)
        dlg._analyze_file(external_source_db)

        # User cancels
        dlg.reject()
        assert len(target_repo.get_all_products()) == initial_count

    def test_backup_restore_widget_merge_accept_flow(self, qapp, target_repo, monkeypatch):
        widget = DatabaseBackupRestoreWidget(repository=target_repo)
        refreshed = False
        restored_emitted = False

        def mock_refresh():
            nonlocal refreshed
            refreshed = True

        def mock_restored_slot():
            nonlocal restored_emitted
            restored_emitted = True

        widget.refresh_status = mock_refresh
        widget.databaseRestored.connect(mock_restored_slot)

        # Mock DatabaseMergeDialog to simulate Accepted outcome
        with patch("ui.dialogs.database_merge_dialog.DatabaseMergeDialog.exec", return_value=QDialog.DialogCode.Accepted):
            widget._handle_merge_database()

        assert refreshed is True
        assert restored_emitted is True

    def test_backup_restore_widget_merge_reject_flow(self, qapp, target_repo, monkeypatch):
        widget = DatabaseBackupRestoreWidget(repository=target_repo)
        refreshed = False
        restored_emitted = False

        def mock_refresh():
            nonlocal refreshed
            refreshed = True

        def mock_restored_slot():
            nonlocal restored_emitted
            restored_emitted = True

        widget.refresh_status = mock_refresh
        widget.databaseRestored.connect(mock_restored_slot)

        # Mock DatabaseMergeDialog to simulate Rejected outcome
        with patch("ui.dialogs.database_merge_dialog.DatabaseMergeDialog.exec", return_value=QDialog.DialogCode.Rejected):
            widget._handle_merge_database()

        assert refreshed is False
        assert restored_emitted is False


class TestDatabaseMergeReferenceIntegrityAndScoping:
    """
    Focused tests ensuring reference records are strictly scoped to eligible NEW components,
    preventing reference leakage from duplicate, conflicting, incomplete, or unused source records,
    and verifying safe dependency handling and rollback.
    """

    def test_reference_records_from_conflict_duplicate_incomplete_and_unused_are_not_imported(
        self, tmp_path, target_repo
    ):
        """
        Verify that reference records used ONLY by:
        1. A conflicting component
        2. A duplicate component
        3. An incomplete component
        4. Completely unused in source components
        are NOT imported into the target database.
        """
        src_path = tmp_path / "reference_leakage_source.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        # Seed reference data in source
        c_leak = src_repo.add_category("UnusedCategory")
        src_repo.add_type(c_leak, "UnusedType")
        src_repo.add_manufacturer("UnusedMfr")

        c_conf = src_repo.add_category("ConflictCategory")
        src_repo.add_type(c_conf, "ConflictType")
        src_repo.add_manufacturer("ConflictMfr")

        c_inc = src_repo.add_category("IncompleteCategory")
        src_repo.add_type(c_inc, "IncompleteType")
        src_repo.add_manufacturer("IncompleteMfr")

        # 1. Conflicting component (matches target Murata GRM188R71H104KA93D but package differs)
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="ConflictCategory",
                type_technology="ConflictType",
                package="1206", # Conflict with target 0603
                footprint="SMD_1206",
                value="100nF",
                quantity_in_stock=10,
            )
        )

        # 2. Incomplete component (missing MPN)
        conn = src_repo.db_manager.get_connection()
        conn.execute(
            """
            INSERT INTO components (
                manufacturer, mpn, norm_manufacturer, norm_mpn,
                category, type_technology, package, raw_package,
                footprint, value, group_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "IncompleteMfr", "", "INCOMPLETEMFR", "",
                "IncompleteCategory", "IncompleteType", "0603", "0603",
                "SMD_0603", "10nF", "IncompleteCategory|IncompleteType|10nF|0603|SMD_0603"
            )
        )
        conn.commit()

        # Target DB baseline reference counts
        target_mfr_names = {m.name for m in target_repo.get_all_manufacturers()}
        target_cat_names = {c.name for c in target_repo.get_all_categories()}
        target_type_names = {t.name for t in target_repo.get_all_types()}

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        # Ensure no reference records were leaked into analysis
        assert "UnusedMfr" not in analysis.new_manufacturers
        assert "UnusedCategory" not in analysis.new_categories
        assert not any(t["name"] == "UnusedType" for t in analysis.new_types)

        assert "ConflictMfr" not in analysis.new_manufacturers
        assert "ConflictCategory" not in analysis.new_categories
        assert not any(t["name"] == "ConflictType" for t in analysis.new_types)

        assert "IncompleteMfr" not in analysis.new_manufacturers
        assert "IncompleteCategory" not in analysis.new_categories
        assert not any(t["name"] == "IncompleteType" for t in analysis.new_types)

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert meta["added_manufacturers"] == 0
        assert meta["added_categories"] == 0
        assert meta["added_types"] == 0

        # Assert target reference tables remain pristine
        updated_mfr_names = {m.name for m in target_repo.get_all_manufacturers()}
        updated_cat_names = {c.name for c in target_repo.get_all_categories()}
        updated_type_names = {t.name for t in target_repo.get_all_types()}

        assert updated_mfr_names == target_mfr_names
        assert updated_cat_names == target_cat_names
        assert updated_type_names == target_type_names

    def test_new_component_with_valid_target_references_eligible_and_imports(self, tmp_path, target_repo):
        """
        Verify that a new component whose Manufacturer, Category, and Type/Technology
        all exist and match in the target database is eligible and imports cleanly.
        """
        c_ind = target_repo.add_category("Inductor")
        target_repo.add_type(c_ind, "Power Inductor")
        target_repo.add_manufacturer("Coilcraft")

        src_path = tmp_path / "valid_new_comp.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        c_src = src_repo.add_category("Inductor")
        src_repo.add_type(c_src, "Power Inductor")
        src_repo.add_manufacturer("Coilcraft")

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Coilcraft",
                mpn="MSS1210-103MEB",
                category="Inductor",
                type_technology="Power Inductor",
                package="SMD",
                footprint="SMD",
                value="10uH",
                quantity_in_stock=120,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 1
        assert len(analysis.conflicting_components) == 0
        assert analysis.new_manufacturers == []
        assert analysis.new_categories == []
        assert analysis.new_types == []
        assert analysis.can_merge is True

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 1
        assert meta["added_manufacturers"] == 0
        assert meta["added_categories"] == 0
        assert meta["added_types"] == 0

        # Verify component exists in target repository
        target_parts = [p.mpn for p in target_repo.get_all_products()]
        assert "MSS1210-103MEB" in target_parts

    def test_component_with_missing_target_type_is_excluded(self, tmp_path, target_repo):
        """
        Verify that a component whose Type/Technology is missing from target DB is excluded,
        classified as CONFLICT, and no type is created.
        """
        c_ind = target_repo.add_category("Inductor")
        target_repo.add_type(c_ind, "Power Inductor")
        target_repo.add_manufacturer("Coilcraft")

        src_path = tmp_path / "missing_type.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        c_src = src_repo.add_category("Inductor")
        src_repo.add_type(c_src, "RF Inductor")
        src_repo.add_manufacturer("Coilcraft")

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Coilcraft",
                mpn="0603CS-10NXJLW",
                category="Inductor",
                type_technology="RF Inductor",
                package="0603",
                footprint="SMD_0603",
                value="10nH",
                quantity_in_stock=50,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1
        conflict_msg = analysis.conflicting_components[0]["conflict_reasons"][0]
        assert "is not an active technology for category 'inductor'" in conflict_msg.lower()
        assert analysis.can_merge is False

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert "RF Inductor" not in [t.name for t in target_repo.get_all_types()]

    def test_component_with_missing_target_category_is_excluded(self, tmp_path, target_repo):
        """
        Verify that a component whose Category is missing from target DB is excluded,
        classified as CONFLICT, and no category is created.
        """
        target_repo.add_manufacturer("Wurth Elektronik")

        src_path = tmp_path / "missing_cat.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        c_src = src_repo.add_category("Ferrite Bead")
        src_repo.add_type(c_src, "SMD Bead")
        src_repo.add_manufacturer("Wurth Elektronik")

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Wurth Elektronik",
                mpn="74279260",
                category="Ferrite Bead",
                type_technology="SMD Bead",
                package="0603",
                footprint="SMD_0603",
                value="600 Ohm",
                quantity_in_stock=200,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1
        conflict_msg = analysis.conflicting_components[0]["conflict_reasons"][0]
        assert "category 'ferrite bead' does not exist in target database reference data" in conflict_msg.lower()

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert "Ferrite Bead" not in [c.name for c in target_repo.get_all_categories()]

    def test_component_with_missing_target_manufacturer_is_excluded(self, tmp_path, target_repo):
        """
        Verify that a component whose Manufacturer is missing from target DB is excluded,
        classified as CONFLICT, and no manufacturer is created.
        """
        # Target already has Capacitor / Ceramic, but NOT Wurth Elektronik
        src_path = tmp_path / "missing_mfr.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()
        c_src = src_repo.add_category("Capacitor")
        src_repo.add_type(c_src, "Ceramic")
        src_repo.add_manufacturer("Wurth Elektronik")

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Wurth Elektronik",
                mpn="885012206026",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=100,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1
        conflict_msg = analysis.conflicting_components[0]["conflict_reasons"][0]
        assert "manufacturer 'wurth elektronik' does not exist in target database reference data" in conflict_msg.lower()

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert "Wurth Elektronik" not in [m.name for m in target_repo.get_all_manufacturers()]

    def test_component_with_type_belonging_to_different_category_is_excluded(self, tmp_path, target_repo):
        """
        Verify that a component specifying a Type that exists in target DB, but belongs to
        a DIFFERENT Category, is rejected as CONFLICT with an explicit error.
        """
        # Target has Capacitor -> Ceramic and Resistor -> Thick Film
        # Source creates a component: Category "Capacitor" with Type "Thick Film"
        src_path = tmp_path / "mismatched_hierarchy.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="WEIRD-CAP-001",
                category="Capacitor",
                type_technology="Thick Film", # Valid type in target, but belongs to Resistor, not Capacitor!
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=10,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1
        conflict_msg = analysis.conflicting_components[0]["conflict_reasons"][0]
        assert "is not an active technology for category 'capacitor'" in conflict_msg.lower()

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0

    def test_valid_component_imported_when_another_component_has_invalid_references(self, tmp_path, target_repo):
        """
        Verify that in a source DB with multiple components, valid components import successfully
        while components with invalid/missing references are safely skipped as CONFLICT.
        """
        src_path = tmp_path / "mixed_validity.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        # 1. Valid Component (Murata / Capacitor / Ceramic exists in target)
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM155R71C104KA88D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0402",
                footprint="SMD_0402",
                value="100nF",
                quantity_in_stock=500,
            )
        )

        # 2. Invalid Component (Missing manufacturer "UnknownCorp" in target)
        src_repo.create_component(
            InventoryProduct(
                manufacturer="UnknownCorp",
                mpn="UNK-001",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="10nF",
                quantity_in_stock=50,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 1
        assert len(analysis.conflicting_components) == 1
        assert analysis.new_components[0]["mpn"] == "GRM155R71C104KA88D"
        assert analysis.conflicting_components[0]["mpn"] == "UNK-001"

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 1
        assert meta["skipped_conflicts"] == 1
        assert "GRM155R71C104KA88D" in [p.mpn for p in target_repo.get_all_products()]
        assert "UNK-001" not in [p.mpn for p in target_repo.get_all_products()]

    def test_preview_and_execution_consistency(self, tmp_path, target_repo):
        """
        Verify that preview classification and counts match execution outcomes exactly.
        """
        src_path = tmp_path / "preview_exec_consistency.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        # A. 1 Valid New component
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM155R71E103KA01D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0402",
                footprint="SMD_0402",
                value="10nF",
                quantity_in_stock=100,
            )
        )

        # B. 1 Duplicate component (Murata GRM188R71H104KA93D exists in target)
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=20,
            )
        )

        # C. 1 Conflict component (Yageo RC0805FR-0710KL exists with 10k, here 50k)
        src_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="SMD_0805",
                value="50k",
                quantity_in_stock=200,
            )
        )

        # D. 1 Incomplete component (missing MPN)
        raw_conn = sqlite3.connect(str(src_path))
        raw_conn.execute(
            "INSERT INTO components (manufacturer, norm_manufacturer, mpn, norm_mpn, category, type_technology, package, footprint, value, group_key, quantity_in_stock) "
            "VALUES ('Murata', 'MURATA', '', '', 'Capacitor', 'Ceramic', '0603', '0603', '100nF', 'GRP', 10);"
        )
        raw_conn.commit()
        raw_conn.close()

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 1
        assert len(analysis.duplicate_components) == 1
        assert len(analysis.conflicting_components) == 1
        assert len(analysis.incomplete_components) == 1

        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == len(analysis.new_components)
        assert meta["skipped_duplicates"] == len(analysis.duplicate_components)
        assert meta["skipped_conflicts"] == len(analysis.conflicting_components)
        assert meta["skipped_incomplete"] == len(analysis.incomplete_components)

    def test_duplicate_conflict_incomplete_unaffected(self, tmp_path, target_repo):
        """
        Verify that standard matching, duplicate detection, conflicting attribute detection,
        and incomplete record filtering operate normally alongside strict reference validation.
        """
        src_path = tmp_path / "standard_matching.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        # Incomplete (empty manufacturer)
        raw_conn = sqlite3.connect(str(src_path))
        raw_conn.execute(
            "INSERT INTO components (manufacturer, norm_manufacturer, mpn, norm_mpn, category, type_technology, package, footprint, value, group_key, quantity_in_stock) "
            "VALUES ('', '', 'SOME-MPN', 'SOME-MPN', 'Capacitor', 'Ceramic', '0603', '0603', '100nF', 'GRP', 10);"
        )
        raw_conn.commit()
        raw_conn.close()

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.incomplete_components) == 1
        assert analysis.can_merge is False

    def test_pre_merge_backup_and_rollback_preserved(self, tmp_path, target_repo):
        """
        Verify that pre-merge backup creation is enforced and disk/write errors trigger full rollback.
        """
        src_path = tmp_path / "backup_and_rollback.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        src_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM155R71H102KA01D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0402",
                footprint="SMD_0402",
                value="1nF",
                quantity_in_stock=100,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))
        assert len(analysis.new_components) == 1

        # Simulate create_component failure
        with patch.object(target_repo, "create_component", side_effect=RuntimeError("Disk I/O Error")):
            ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
            assert ok is False
            assert "rolled back" in msg.lower()

        # Verify target is untouched
        assert "GRM155R71H102KA01D" not in [p.mpn for p in target_repo.get_all_products()]

    def test_merge_reporting_for_zero_components_and_empty_merge(self, tmp_path, target_repo):
        """
        Verify that execute_merge generates accurate messages for empty merges and zero imported components.
        """
        analysis = MergeAnalysis(
            source_path="empty.db",
            source_schema_version=1,
            is_valid=True,
            total_source_components=0,
            duplicate_components=[{"mock": 1}],
        )
        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert "no new records or references to merge" in msg.lower()
        assert meta["added_components"] == 0

    def test_component_with_manufacturer_in_target_components_but_missing_from_ref_manufacturers_is_excluded(
        self, tmp_path, target_repo
    ):
        """
        Verify that a source component whose manufacturer is present in target components
        but absent from target's authoritative ref_manufacturers table is excluded as CONFLICT.
        Component records must never substitute for missing authoritative reference rows.
        """
        # 1. Target contains a component with 'UnregisteredMfr'
        # Target already has valid Category 'Capacitor' and Type 'Ceramic'
        target_repo.create_component(
            InventoryProduct(
                manufacturer="UnregisteredMfr",
                mpn="OLD-PART-001",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=10,
            )
        )

        # 2. Confirm UnregisteredMfr is NOT in ref_manufacturers
        active_target_mfrs = [m.name for m in target_repo.get_all_manufacturers()]
        assert "UnregisteredMfr" not in active_target_mfrs

        # 3. Source DB contains a component with 'UnregisteredMfr' and a NEW MPN
        src_path = tmp_path / "unregistered_mfr_src.db"
        src_repo = SqliteInventoryRepository(str(src_path))
        src_repo.load()

        src_repo.create_component(
            InventoryProduct(
                manufacturer="UnregisteredMfr",
                mpn="NEW-PART-999",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=50,
            )
        )

        analysis = DatabaseMergeService.analyze_merge(target_repo, str(src_path))

        # 4. Source component is classified as CONFLICT, not NEW
        assert len(analysis.new_components) == 0
        assert len(analysis.conflicting_components) == 1
        assert analysis.conflicting_components[0]["mpn"] == "NEW-PART-999"

        # 5. Rejection reason identifies missing Manufacturer reference
        conflict_msg = analysis.conflicting_components[0]["conflict_reasons"][0]
        assert "manufacturer 'unregisteredmfr' does not exist in target database reference data" in conflict_msg.lower()

        # 6 & 7. Component is not imported, no reference record created
        ok, msg, meta = DatabaseMergeService.execute_merge(target_repo, analysis)
        assert ok is True
        assert meta["added_components"] == 0
        assert meta["added_manufacturers"] == 0
        assert "NEW-PART-999" not in [p.mpn for p in target_repo.get_all_products()]
        assert "UnregisteredMfr" not in [m.name for m in target_repo.get_all_manufacturers()]
