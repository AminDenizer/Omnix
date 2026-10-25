"""
Tests for Component-Level Min Stock & Target Stock Inventory Management (Option B).
Governing Document: Option B - Independent Stock Thresholds per Component.

Validates:
1. Transactional SQLite Schema Migration (v1 -> v2) with threshold seeding from stock_policies.
2. Independent component threshold ownership (two components in same group have independent thresholds).
3. Validation rules (min_stock >= 0, target_stock >= min_stock, type enforcement).
4. Component-level shortage calculation and Mode A replenishment handoff with exact quantities.
5. Safe handling of unmappable low-stock components without links.
6. Zero inventory quantity mutations during replenishment planning or threshold updates.
7. UI table rendering (Min Stock, Target Stock columns) and dialog lifecycles.
"""

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import Qt

from core.inventory.database import DatabaseManager, CURRENT_SCHEMA_VERSION, resolve_database_path
from core.inventory.models import (
    InventoryProduct,
    SupplierLink,
    StockPolicyGroup,
    StockPolicyRecord,
    ValidationError,
    ComponentNotFoundError,
    build_group_key,
)
from core.inventory.repository import SqliteInventoryRepository
from ui.dialogs.component_threshold_dialog import ComponentThresholdDialog
from ui.dialogs.component_edit_dialog import ComponentEditDialog
from ui.dialogs.policy_edit_dialog import PolicyEditDialog
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestSchemaMigrationV1ToV2:
    """Validates transactional SQLite schema migration from Version 1 to Version 2."""

    def test_fresh_database_has_version_2_schema(self, tmp_path):
        db_path = str(tmp_path / "fresh_v2.db")
        db = DatabaseManager(db_path)
        ver = db.initialize_schema()
        assert ver == 2
        assert db.get_schema_version() == 2

        conn = db.get_connection()
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(components);").fetchall()]
        assert "min_stock" in cols
        assert "target_stock" in cols
        db.close()

    def test_migration_from_v1_seeds_thresholds_from_stock_policies(self, tmp_path):
        db_path = str(tmp_path / "legacy_v1.db")
        conn = sqlite3.connect(db_path)

        # Build pure V1 schema
        conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT NOT NULL
            );
            CREATE TABLE ref_manufacturers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                norm_name TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ref_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                norm_name TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ref_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES ref_categories(id),
                name TEXT NOT NULL,
                norm_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (category_id, norm_name)
            );
            CREATE TABLE ref_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                norm_name TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                base_url TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manufacturer TEXT NOT NULL,
                mpn TEXT NOT NULL,
                norm_manufacturer TEXT NOT NULL,
                norm_mpn TEXT NOT NULL,
                category TEXT NOT NULL,
                type_technology TEXT NOT NULL,
                package TEXT NOT NULL,
                raw_package TEXT DEFAULT '',
                footprint TEXT NOT NULL,
                value TEXT NOT NULL,
                description TEXT DEFAULT '',
                quantity_in_stock INTEGER NOT NULL DEFAULT 0,
                group_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_component_identity UNIQUE (norm_manufacturer, norm_mpn)
            );
            CREATE TABLE supplier_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
                vendor_id TEXT NOT NULL,
                vendor_label TEXT NOT NULL,
                url TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE stock_policies (
                group_key TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                type_technology TEXT NOT NULL,
                value TEXT NOT NULL,
                package TEXT NOT NULL,
                footprint TEXT NOT NULL,
                min_stock INTEGER,
                target_stock INTEGER,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            PRAGMA user_version = 1;
            INSERT INTO schema_version (version, description) VALUES (1, 'V1 Schema');
        """)

        # Insert V1 legacy data:
        # Group 1 has policy: Min = 25, Target = 100
        grp1_key = build_group_key("Resistor", "Thick Film", "10k", "0603", "R0603")
        conn.execute(
            "INSERT INTO stock_policies VALUES (?, 'Resistor', 'Thick Film', '10k', '0603', 'R0603', 25, 100, 'Legacy group policy', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);",
            (grp1_key,)
        )
        # Component 1 belongs to Group 1
        conn.execute(
            """INSERT INTO components (manufacturer, mpn, norm_manufacturer, norm_mpn, category, type_technology, package, footprint, value, quantity_in_stock, group_key)
            VALUES ('Yageo', 'RC0603JR-0710KL', 'YAGEO', 'RC0603JR-0710KL', 'Resistor', 'Thick Film', '0603', 'R0603', '10k', 10, ?);""",
            (grp1_key,)
        )
        # Component 2 belongs to Group 2 with NO policy
        grp2_key = build_group_key("Capacitor", "Ceramic", "100nF", "0603", "C0603")
        conn.execute(
            """INSERT INTO components (manufacturer, mpn, norm_manufacturer, norm_mpn, category, type_technology, package, footprint, value, quantity_in_stock, group_key)
            VALUES ('Samsung', 'CL10B104KB8NNNC', 'SAMSUNG', 'CL10B104KB8NNNC', 'Capacitor', 'Ceramic', '0603', 'C0603', '100nF', 50, ?);""",
            (grp2_key,)
        )
        conn.commit()
        conn.close()

        # Run migration via DatabaseManager
        db = DatabaseManager(db_path)
        new_version = db.initialize_schema()
        assert new_version == 2
        assert db.get_schema_version() == 2

        # Verify components table has columns and populated thresholds
        migrated_conn = db.get_connection()
        migrated_rows = {
            r["mpn"]: r for r in migrated_conn.execute("SELECT mpn, min_stock, target_stock, quantity_in_stock FROM components;").fetchall()
        }

        # Component 1 must have inherited Group 1 policy thresholds
        c1 = migrated_rows["RC0603JR-0710KL"]
        assert c1["min_stock"] == 25
        assert c1["target_stock"] == 100
        assert c1["quantity_in_stock"] == 10

        # Component 2 had no policy -> must default to 0
        c2 = migrated_rows["CL10B104KB8NNNC"]
        assert c2["min_stock"] == 0
        assert c2["target_stock"] == 0
        assert c2["quantity_in_stock"] == 50

        # Verify schema_version audit trail
        audit_rows = migrated_conn.execute("SELECT version, description FROM schema_version ORDER BY version ASC;").fetchall()
        assert len(audit_rows) == 2
        assert audit_rows[1]["version"] == 2
        assert "Migrate min_stock and target_stock" in audit_rows[1]["description"]

        db.close()


class TestIndependentComponentThresholds:
    """Validates Option B: each component possesses independent min_stock and target_stock."""

    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test_option_b.db")
        r = SqliteInventoryRepository(db_path)
        cat_id = r.add_category("Resistor")
        r.add_type(cat_id, "Thick Film")
        r.add_manufacturer("Yageo")
        r.add_manufacturer("Vishay")
        r.add_manufacturer("Panasonic")
        yield r
        r.close()

    def test_independent_thresholds_for_components_in_same_group(self, repo):
        """Two components sharing identical 5-dimension group key must maintain independent thresholds."""
        # Component 1 (Yageo)
        p1 = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603JR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R0603",
            value="10k",
            quantity_in_stock=10,
            min_stock=15,
            target_stock=30,
        )
        c1 = repo.create_component(p1)

        # Component 2 (Vishay) in the same group key
        p2 = InventoryProduct(
            manufacturer="Vishay",
            mpn="CRCW060310K0FKEA",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R0603",
            value="10k",
            quantity_in_stock=5,
            min_stock=50,
            target_stock=100,
        )
        c2 = repo.create_component(p2)

        assert c1.group_key == c2.group_key

        # Verify initial independent thresholds
        c1_read = repo.get_component_by_id(c1.id)
        c2_read = repo.get_component_by_id(c2.id)
        assert c1_read.min_stock == 15
        assert c1_read.target_stock == 30
        assert c2_read.min_stock == 50
        assert c2_read.target_stock == 100

        # Update c1 thresholds independently using update_component_thresholds
        updated_c1 = repo.update_component_thresholds(c1.id, min_stock=25, target_stock=60)
        assert updated_c1.min_stock == 25
        assert updated_c1.target_stock == 60

        # Verify c2 remains completely unaltered
        c2_after = repo.get_component_by_id(c2.id)
        assert c2_after.min_stock == 50
        assert c2_after.target_stock == 100

        # Update c2 thresholds independently
        updated_c2 = repo.update_component_thresholds(c2.id, min_stock=80, target_stock=200)
        assert updated_c2.min_stock == 80
        assert updated_c2.target_stock == 200

        # Verify c1 remains unchanged
        c1_after = repo.get_component_by_id(c1.id)
        assert c1_after.min_stock == 25
        assert c1_after.target_stock == 60

    def test_threshold_validation_rules(self, repo):
        """Enforces min_stock >= 0 and target_stock >= min_stock."""
        p = InventoryProduct(
            manufacturer="Panasonic",
            mpn="ERJ-3GEYJ103V",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="R0603",
            value="10k",
            quantity_in_stock=20,
        )
        c = repo.create_component(p)

        # 1. Negative min_stock rejected
        with pytest.raises(ValidationError, match="min_stock must be non-negative"):
            repo.update_component_thresholds(c.id, min_stock=-5, target_stock=10)

        # 2. Target stock less than min stock rejected
        with pytest.raises(ValidationError, match="target_stock .* cannot be less than min_stock"):
            repo.update_component_thresholds(c.id, min_stock=30, target_stock=20)

        # 3. Non-integer rejected
        with pytest.raises(ValidationError, match="must be an integer"):
            repo.update_component_thresholds(c.id, min_stock="ten", target_stock=20)

        # 4. Valid edge case: min_stock == target_stock is permitted
        updated = repo.update_component_thresholds(c.id, min_stock=40, target_stock=40)
        assert updated.min_stock == 40
        assert updated.target_stock == 40

        # 5. Valid edge case: min_stock == 0, target_stock == 0 (thresholds disabled)
        updated_zero = repo.update_component_thresholds(c.id, min_stock=0, target_stock=0)
        assert updated_zero.min_stock == 0
        assert updated_zero.target_stock == 0


class TestComponentLevelShortageReplenishment:
    """Validates Mode A shortage calculation and replenishment handoff based on component thresholds."""

    @pytest.fixture
    def replenishment_repo(self, tmp_path):
        db_path = str(tmp_path / "test_replenishment_option_b.db")
        r = SqliteInventoryRepository(db_path)
        cat_id = r.add_category("Passive Components")
        r.add_type(cat_id, "Resistor")
        r.add_type(cat_id, "Capacitor")
        r.add_manufacturer("Yageo")
        r.add_manufacturer("Samsung")
        r.add_manufacturer("Murata")

        # Component 1: Low Stock with Lion link (current=8, min=20, target=50 -> shortage = 42)
        p1 = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603JR-0710KL",
            category="Passive Components",
            type_technology="Resistor",
            package="0603",
            footprint="R0603",
            value="10k",
            quantity_in_stock=8,
            min_stock=20,
            target_stock=50,
            description="10k Pullup",
        )
        l1 = SupplierLink(
            vendor_id="vendor_lion",
            vendor_label="Lion",
            url="https://lionelectronic.ir/product/10k-0603",
        )
        r.create_component(p1, supplier_links=[l1])

        # Component 2: Same group, Sufficient Stock (current=60, min=20, target=50 -> NOT low stock)
        p2 = InventoryProduct(
            manufacturer="Murata",
            mpn="MUR-10K-0603",
            category="Passive Components",
            type_technology="Resistor",
            package="0603",
            footprint="R0603",
            value="10k",
            quantity_in_stock=60,
            min_stock=20,
            target_stock=50,
            description="Murata 10k",
        )
        r.create_component(p2, supplier_links=[])

        # Component 3: Low Stock WITHOUT link -> UNMAPPABLE (current=2, min=15, target=40 -> shortage = 38)
        p3 = InventoryProduct(
            manufacturer="Samsung",
            mpn="CL10B104KB8NNNC",
            category="Passive Components",
            type_technology="Capacitor",
            package="0603",
            footprint="C0603",
            value="100nF",
            quantity_in_stock=2,
            min_stock=15,
            target_stock=40,
            description="100nF Decoupling",
        )
        r.create_component(p3, supplier_links=[])

        # Component 4: Thresholds disabled (min=0, target=0, current=0 -> NOT low stock)
        p4 = InventoryProduct(
            manufacturer="Samsung",
            mpn="CL10A106KP8NNNC",
            category="Passive Components",
            type_technology="Capacitor",
            package="0603",
            footprint="C0603",
            value="10uF",
            quantity_in_stock=0,
            min_stock=0,
            target_stock=0,
        )
        r.create_component(p4, supplier_links=[])

        yield r
        r.close()

    def test_replenishment_evaluates_individual_components(self, replenishment_repo):
        """Mode A replenishment evaluates each component independently without masking low-stock items."""
        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = replenishment_repo

        items = win._get_stock_policy_replenishment_items()
        assert len(items) == 2  # Only p1 and p3 are low stock; p2 and p4 must NOT be included

        items_by_mpn = {it["part_number"]: it for it in items}

        # Verify Component 1 (Yageo 10k)
        assert "RC0603JR-0710KL" in items_by_mpn
        it1 = items_by_mpn["RC0603JR-0710KL"]
        assert it1["needed_qty"] == 42  # 50 - 8
        assert it1["current_stock"] == 8
        assert it1["min_stock"] == 20
        assert it1["target_stock"] == 50
        assert it1["status"] == "SHORTAGE"
        assert "lionelectronic.ir" in it1["link"]

        # Verify Component 3 (Samsung 100nF without link)
        assert "CL10B104KB8NNNC" in items_by_mpn
        it3 = items_by_mpn["CL10B104KB8NNNC"]
        assert it3["needed_qty"] == 38  # 40 - 2
        assert it3["current_stock"] == 2
        assert it3["min_stock"] == 15
        assert it3["target_stock"] == 40
        assert it3["status"] == "UNMAPPABLE"
        assert "No stored supplier link" in it3["reason"]

        # Murata (p2) is in the SAME group as Yageo (p1), but has 60 stock >= 20 min -> must NOT be in replenishment
        assert "MUR-10K-0603" not in items_by_mpn

        # Samsung 10uF (p4) has min_stock=0 -> must NOT be in replenishment
        assert "CL10A106KP8NNNC" not in items_by_mpn

    def test_zero_inventory_mutation_during_replenishment(self, replenishment_repo):
        """Replenishment evaluation must strictly NOT alter physical on-hand quantities."""
        initial_products = {p.id: p.quantity_in_stock for p in replenishment_repo.get_all_products()}

        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = replenishment_repo

        # Execute replenishment calculation multiple times
        for _ in range(5):
            _ = win._get_stock_policy_replenishment_items()

        # Verify all quantities remain perfectly identical
        after_products = {p.id: p.quantity_in_stock for p in replenishment_repo.get_all_products()}
        assert initial_products == after_products


class TestUIComponentThresholdsIntegration:
    """Validates Component Inventory table rendering and threshold editing dialogs."""

    @pytest.fixture
    def ui_repo(self, tmp_path):
        db_path = str(tmp_path / "test_ui_thresholds.db")
        r = SqliteInventoryRepository(db_path)
        cat_id = r.add_category("ICs")
        r.add_type(cat_id, "Microcontroller")
        r.add_manufacturer("STMicroelectronics")

        p = InventoryProduct(
            manufacturer="STMicroelectronics",
            mpn="STM32F401RET6",
            category="ICs",
            type_technology="Microcontroller",
            package="LQFP-64",
            footprint="LQFP-64",
            value="STM32F401",
            quantity_in_stock=5,
            min_stock=10,
            target_stock=25,
            description="ARM Cortex-M4 MCU",
        )
        r.create_component(p)
        yield r
        r.close()

    def test_component_threshold_dialog_lifecycle(self, qapp, ui_repo):
        """ComponentThresholdDialog displays current thresholds, validates, and updates repository."""
        comp = ui_repo.get_all_products()[0]
        dlg = ComponentThresholdDialog(component=comp, repository=ui_repo)

        # 1. Initial values from component
        assert dlg.min_spin.value() == 10
        assert dlg.target_spin.value() == 25
        assert dlg.save_btn.isEnabled() is True

        # 2. Modify to invalid thresholds: target (15) < min (30)
        dlg.min_spin.setValue(30)
        dlg.target_spin.setValue(15)
        dlg._on_threshold_changed()
        assert dlg.save_btn.isEnabled() is False
        assert "Target Stock (15) cannot be less than Min Stock (30)" in dlg.status_banner.text()

        # 3. Correct to valid thresholds: min = 20, target = 60
        dlg.min_spin.setValue(20)
        dlg.target_spin.setValue(60)
        dlg._on_threshold_changed()
        assert dlg.save_btn.isEnabled() is True
        assert "Low Stock" in dlg.status_banner.text()  # 5 on-hand < 20 min

        # 4. Save and verify repository update
        dlg._on_save()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.saved_component is not None
        assert dlg.saved_component.min_stock == 20
        assert dlg.saved_component.target_stock == 60

        # Verify database record
        updated_in_db = ui_repo.get_component_by_id(comp.id)
        assert updated_in_db.min_stock == 20
        assert updated_in_db.target_stock == 60

        dlg.close()

    def test_component_edit_dialog_persists_thresholds(self, qapp, ui_repo):
        """ComponentEditDialog Section C accepts and persists min_stock and target_stock."""
        dlg = ComponentEditDialog(repository=ui_repo, component=None)
        dlg.reset_form()

        # Fill required fields
        dlg.mfr_input.setEditText("STMicroelectronics")
        dlg.mpn_input.setText("STM32F411CEU6")
        dlg.category_combo.setCurrentText("ICs")
        dlg.tech_combo.setCurrentText("Microcontroller")
        dlg.value_input.setText("STM32F411")
        dlg.package_input.setText("UFQFPN-48")
        dlg.footprint_input.setText("UFQFPN-48")
        dlg.qty_spin.setValue(12)

        # Set thresholds
        dlg.min_stock_spin.setValue(25)
        dlg.target_stock_spin.setValue(75)

        # Save and verify
        dlg._on_save_clicked()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.saved_component is not None
        assert dlg.saved_component.min_stock == 25
        assert dlg.saved_component.target_stock == 75

        # Verify in DB
        created_in_db = ui_repo.get_component_by_identity("STMicroelectronics", "STM32F411CEU6")
        assert created_in_db is not None
        assert created_in_db.min_stock == 25
        assert created_in_db.target_stock == 75

        dlg.close()


class TestFocusedThresholdIntegrityFixes:
    """
    Focused verification tests for:
    1. Editing a legacy group policy cannot overwrite independent component thresholds.
    2. Components with intentionally zero thresholds remain zero in group aggregation.
    3. Legacy group policies cannot override existing component-level values when their aggregate is zero.
    4. Components with Min Stock = 0 do not enter Replenishment, including when Target Stock > 0 and quantity is zero.
    5. Components with nonzero Min Stock continue to follow existing Replenishment rules.
    6. Inventory quantities remain unchanged during threshold editing, aggregation, and Replenishment preview.
    """

    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test_focused_integrity.db")
        r = SqliteInventoryRepository(db_path)
        cat_id = r.add_category("Passive Components")
        r.add_type(cat_id, "Resistor")
        r.add_type(cat_id, "Capacitor")
        r.add_manufacturer("Yageo")
        r.add_manufacturer("Vishay")
        r.add_manufacturer("Samsung")
        yield r
        r.close()

    def test_legacy_set_policy_does_not_overwrite_component_thresholds(self, repo):
        """repo.set_policy() updates stock_policies only and NEVER cascades or overwrites component thresholds."""
        # Create Component 1 with min=10, target=30
        c1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603-10K",
                category="Passive Components",
                type_technology="Resistor",
                package="0603",
                footprint="R0603",
                value="10k",
                quantity_in_stock=25,
                min_stock=10,
                target_stock=30,
            )
        )

        # Create Component 2 in same group with min=40, target=90
        c2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW0603-10K",
                category="Passive Components",
                type_technology="Resistor",
                package="0603",
                footprint="R0603",
                value="10k",
                quantity_in_stock=50,
                min_stock=40,
                target_stock=90,
            )
        )
        assert c1.group_key == c2.group_key
        group_key = c1.group_key

        # Now execute legacy set_policy with completely different thresholds
        pol = repo.set_policy(
            group_key=group_key,
            min_stock=200,
            target_stock=600,
            category="Passive Components",
            type_technology="Resistor",
            value="10k",
            package="0603",
            footprint="R0603",
        )
        assert pol.min_stock == 200
        assert pol.target_stock == 600

        # Component 1 thresholds in database must be completely unaltered
        refetched_c1 = repo.get_component_by_id(c1.id)
        assert refetched_c1.min_stock == 10
        assert refetched_c1.target_stock == 30

        # Component 2 thresholds in database must be completely unaltered
        refetched_c2 = repo.get_component_by_id(c2.id)
        assert refetched_c2.min_stock == 40
        assert refetched_c2.target_stock == 90

    def test_zero_component_thresholds_remain_zero_in_group_aggregation(self, repo):
        """Components with intentionally zero thresholds aggregate to 0 and never fall back to stock_policies."""
        # Set a legacy group policy with high thresholds
        group_key = build_group_key("Passive Components", "Resistor", "100k", "0603", "R0603")
        repo.set_policy(
            group_key=group_key,
            min_stock=150,
            target_stock=450,
            category="Passive Components",
            type_technology="Resistor",
            value="100k",
            package="0603",
            footprint="R0603",
        )

        # Create two physical components in that group, both with intentional min_stock=0, target_stock=0
        c1 = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603-100K",
                category="Passive Components",
                type_technology="Resistor",
                package="0603",
                footprint="R0603",
                value="100k",
                quantity_in_stock=100,
                min_stock=0,
                target_stock=0,
            )
        )
        c2 = repo.create_component(
            InventoryProduct(
                manufacturer="Vishay",
                mpn="CRCW0603-100K",
                category="Passive Components",
                type_technology="Resistor",
                package="0603",
                footprint="R0603",
                value="100k",
                quantity_in_stock=150,
                min_stock=0,
                target_stock=0,
            )
        )
        assert c1.group_key == group_key

        # Aggregation in get_group() must report min_stock=0, target_stock=0 (NOT 150 or 450)
        grp = repo.get_group(group_key)
        assert grp is not None
        assert grp.min_stock == 0
        assert grp.target_stock == 0
        assert grp.current_stock == 250  # 100 + 150

        # Aggregation in get_all_groups() must also report min_stock=0, target_stock=0
        all_grps = {g.group_key: g for g in repo.get_all_groups()}
        assert group_key in all_grps
        assert all_grps[group_key].min_stock == 0
        assert all_grps[group_key].target_stock == 0

    def test_policy_edit_dialog_read_only_when_group_contains_components(self, qapp, repo):
        """PolicyEditDialog opens in read-only mode when group has physical components."""
        c = repo.create_component(
            InventoryProduct(
                manufacturer="Samsung",
                mpn="CL10B104KB8NNNC",
                category="Passive Components",
                type_technology="Capacitor",
                package="0603",
                footprint="C0603",
                value="100nF",
                quantity_in_stock=50,
                min_stock=20,
                target_stock=50,
            )
        )
        group = repo.get_group(c.group_key)
        assert len(group.products) == 1

        dlg = PolicyEditDialog(group=group, repository=repo)
        assert dlg.is_read_only is True
        assert dlg.min_spin.isReadOnly() is True
        assert dlg.target_spin.isReadOnly() is True
        assert dlg.min_up_btn.isEnabled() is False
        assert dlg.target_up_btn.isEnabled() is False
        assert dlg.save_btn.isVisible() is False
        assert dlg.cancel_btn.text() == "Close"

        # Attempting save must be a complete NO-OP
        dlg._on_save_clicked()
        assert dlg.result() != QDialog.DialogCode.Accepted

        # Unaltered in DB
        db_comp = repo.get_component_by_id(c.id)
        assert db_comp.min_stock == 20
        assert db_comp.target_stock == 50
        dlg.close()

    def test_min_stock_zero_strictly_excluded_from_replenishment(self, repo):
        """Components with min_stock == 0 must not enter Replenishment, even if target_stock > 0 and stock == 0."""
        # Component 1: target_stock = 100, current = 0, but min_stock = 0
        p1 = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603-0MIN-TGT",
            category="Passive Components",
            type_technology="Resistor",
            package="0603",
            footprint="R0603",
            value="1k",
            quantity_in_stock=0,
            min_stock=0,
            target_stock=100,
        )
        l1 = SupplierLink(vendor_id="vendor_lion", vendor_label="Lion", url="https://lion.ir/1k")
        repo.create_component(p1, supplier_links=[l1])

        # Component 2: min_stock = 0, target_stock = 0, current = 0
        p2 = InventoryProduct(
            manufacturer="Vishay",
            mpn="CRCW-0MIN-0TGT",
            category="Passive Components",
            type_technology="Resistor",
            package="0603",
            footprint="R0603",
            value="1k",
            quantity_in_stock=0,
            min_stock=0,
            target_stock=0,
        )
        l2 = SupplierLink(vendor_id="vendor_lion", vendor_label="Lion", url="https://lion.ir/1k-v")
        repo.create_component(p2, supplier_links=[l2])

        # Verify domain model properties
        assert p1.is_low_stock is False
        assert p1.shortage_to_target == 0
        assert p1.shortage_to_min == 0
        assert p2.is_low_stock is False
        assert p2.shortage_to_target == 0

        # Verify in Replenishment workflow
        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = repo
        shortages = win._get_stock_policy_replenishment_items()
        assert len(shortages) == 0

    def test_nonzero_min_stock_enters_replenishment_normally(self, repo):
        """Components with min_stock > 0 follow normal Replenishment rules."""
        p = InventoryProduct(
            manufacturer="Samsung",
            mpn="CL10B-REPLENISH",
            category="Passive Components",
            type_technology="Capacitor",
            package="0603",
            footprint="C0603",
            value="10uF",
            quantity_in_stock=3,
            min_stock=15,
            target_stock=40,
        )
        link = SupplierLink(vendor_id="vendor_lion", vendor_label="Lion", url="https://lion.ir/10uf")
        repo.create_component(p, supplier_links=[link])

        assert p.is_low_stock is True
        assert p.shortage_to_target == 37  # 40 - 3
        assert p.shortage_to_min == 12     # 15 - 3

        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = repo
        shortages = win._get_stock_policy_replenishment_items()
        assert len(shortages) == 1
        assert shortages[0]["part_number"] == "CL10B-REPLENISH"
        assert shortages[0]["needed_qty"] == 37
        assert shortages[0]["status"] == "SHORTAGE"

    def test_zero_inventory_quantity_mutation_across_all_operations(self, repo):
        """Physical on-hand inventory quantities remain completely immutable during threshold operations."""
        c = repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="IMMUTABLE-01",
                category="Passive Components",
                type_technology="Resistor",
                package="0603",
                footprint="R0603",
                value="2.2k",
                quantity_in_stock=77,
                min_stock=50,
                target_stock=150,
            )
        )
        assert c.quantity_in_stock == 77

        # 1. Update thresholds
        repo.update_component_thresholds(c.id, min_stock=80, target_stock=200)
        assert repo.get_component_by_id(c.id).quantity_in_stock == 77

        # 2. Group aggregation
        _ = repo.get_group(c.group_key)
        _ = repo.get_all_groups()
        assert repo.get_component_by_id(c.id).quantity_in_stock == 77

        # 3. Replenishment calculation
        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = repo
        for _ in range(3):
            _ = win._get_stock_policy_replenishment_items()
        assert repo.get_component_by_id(c.id).quantity_in_stock == 77
