"""
Unit & Integration Tests for Omnix SQLite Database Foundation & Inventory Repository
Governing Document: Phase 1 Master Architecture Specification & Stage 1 Implementation
"""

import os
import sqlite3
import pytest

from core.inventory.models import (
    InventoryProduct,
    StockPolicyGroup,
    SupplierLink,
    StockPolicyRecord,
    ManufacturerRecord,
    CategoryRecord,
    TypeRecord,
    normalize_identity_part,
    clean_display_string,
    normalize_package,
    build_group_key,
    format_supplier_links_as_string,
    InventoryDatabaseError,
    ComponentConflictError,
    ComponentNotFoundError,
    ReferenceDataInUseError,
    ReferenceDataNotFoundError,
    DuplicateReferenceError,
    ValidationError,
)
from core.inventory.database import (
    DatabaseManager,
    resolve_database_path,
    CURRENT_SCHEMA_VERSION,
)
from core.inventory.repository import (
    SqliteInventoryRepository,
)


@pytest.fixture
def temp_db_path(tmp_path):
    """Provides a fresh isolated database file path inside pytest's temporary directory."""
    return str(tmp_path / "test_omnix_inventory.db")


@pytest.fixture
def repo(temp_db_path):
    """Provides an initialized SqliteInventoryRepository backed by a temp database."""
    r = SqliteInventoryRepository(temp_db_path)
    yield r
    r.close()


@pytest.fixture
def populated_repo(repo):
    """Provides a repository pre-populated with standard reference data."""
    # Manufacturers
    repo.add_manufacturer("Texas Instruments")
    repo.add_manufacturer("Yageo")
    repo.add_manufacturer("Murata")
    repo.add_manufacturer("STMicroelectronics")
    repo.add_manufacturer("Walsin")

    # Categories & Types
    cat_res = repo.add_category("Resistor")
    repo.add_type(cat_res, "Thick Film")
    repo.add_type(cat_res, "Thin Film")

    cat_cap = repo.add_category("Capacitor")
    repo.add_type(cat_cap, "Ceramic")
    repo.add_type(cat_cap, "Tantalum")

    cat_ic = repo.add_category("Integrated Circuit")
    repo.add_type(cat_ic, "Microcontroller")
    repo.add_type(cat_ic, "Linear Regulator")
    repo.add_type(cat_ic, "Logic")

    return repo


# =============================================================================
# 1. Database Lifecycle, Schema & Integrity Tests
# =============================================================================

class TestDatabaseLifecycle:
    def test_schema_initialization(self, temp_db_path):
        db = DatabaseManager(temp_db_path)
        version = db.initialize_schema()
        assert version == CURRENT_SCHEMA_VERSION
        assert db.get_schema_version() == CURRENT_SCHEMA_VERSION

        # Verify PRAGMA foreign keys
        conn = db.get_connection()
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1

        # Verify WAL mode on disk
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert jm.lower() == "wal"

        db.close()

    def test_reopen_database_preserves_data(self, temp_db_path):
        db1 = DatabaseManager(temp_db_path)
        db1.initialize_schema()
        repo1 = SqliteInventoryRepository(db1)
        repo1.add_manufacturer("Samsung")
        db1.close()

        # Reopen
        db2 = DatabaseManager(temp_db_path)
        repo2 = SqliteInventoryRepository(db2)
        mfr = repo2.get_manufacturer_by_name("Samsung")
        assert mfr is not None
        assert mfr.name == "Samsung"
        db2.close()

    def test_transaction_rollback_on_error(self, temp_db_path):
        db = DatabaseManager(temp_db_path)
        db.initialize_schema()
        conn = db.get_connection()

        # Insert a valid category
        with db.transaction():
            conn.execute("INSERT INTO ref_categories (name, norm_name) VALUES (?, ?);", ("Diode", "DIODE"))

        # Block that throws an exception
        with pytest.raises(RuntimeError):
            with db.transaction():
                conn.execute("INSERT INTO ref_categories (name, norm_name) VALUES (?, ?);", ("Inductor", "INDUCTOR"))
                raise RuntimeError("Intentional error to trigger rollback")

        # "Diode" should exist, "Inductor" should NOT exist
        row_diode = conn.execute("SELECT id FROM ref_categories WHERE norm_name = 'DIODE';").fetchone()
        assert row_diode is not None
        row_ind = conn.execute("SELECT id FROM ref_categories WHERE norm_name = 'INDUCTOR';").fetchone()
        assert row_ind is None
        db.close()

    def test_repeated_schema_initialization_does_not_erase_data(self, temp_db_path):
        db = DatabaseManager(temp_db_path)
        assert db.initialize_schema() == CURRENT_SCHEMA_VERSION

        repo = SqliteInventoryRepository(db)
        mfr_id = repo.add_manufacturer("Bourns")
        cat_id = repo.add_category("Inductor")
        type_id = repo.add_type(cat_id, "Power Inductor")
        comp = repo.create_component(
            InventoryProduct(
                manufacturer="Bourns",
                mpn="SRR1260-100M",
                category="Inductor",
                type_technology="Power Inductor",
                package="SMD",
                footprint="IND_12x12",
                value="10uH",
                quantity_in_stock=45,
            )
        )
        repo.add_supplier_link(comp.id, "lion", "Lion", "https://lion.ir/ind1")
        repo.set_policy(comp.group_key, min_stock=20, target_stock=60)

        # Call initialize_schema repeatedly
        assert db.initialize_schema() == CURRENT_SCHEMA_VERSION
        assert db.initialize_schema() == CURRENT_SCHEMA_VERSION

        # Verify all data remains 100% intact
        assert repo.get_manufacturer(mfr_id).name == "Bourns"
        assert repo.get_category(cat_id).name == "Inductor"
        assert repo.get_type(type_id).name == "Power Inductor"
        fetched_comp = repo.get_component_by_id(comp.id)
        assert fetched_comp is not None
        assert fetched_comp.quantity_in_stock == 45
        assert len(fetched_comp.supplier_links) == 1
        pol = repo.get_policy(comp.group_key)
        assert pol is not None
        assert pol.min_stock == 20
        assert pol.target_stock == 60
        db.close()

    def test_future_schema_version_rejected(self, temp_db_path):
        db = DatabaseManager(temp_db_path)
        conn = db.get_connection()
        conn.execute("PRAGMA user_version = 99;")
        with pytest.raises(InventoryDatabaseError) as exc:
            db.initialize_schema()
        assert "newer than supported" in str(exc.value)
        db.close()

    def test_hot_backup(self, temp_db_path, tmp_path):
        repo = SqliteInventoryRepository(temp_db_path)
        repo.add_manufacturer("Microchip")
        backup_path = str(tmp_path / "backup.db")

        success = repo.backup(backup_path)
        assert success is True
        assert os.path.exists(backup_path)

        # Connect to backup and verify data
        backup_db = DatabaseManager(backup_path)
        backup_repo = SqliteInventoryRepository(backup_db)
        mfr = backup_repo.get_manufacturer_by_name("Microchip")
        assert mfr is not None
        assert mfr.name == "Microchip"
        backup_repo.close()
        repo.close()

    def test_path_resolution_priority(self, tmp_path, monkeypatch):
        # 1. Explicit
        p1 = resolve_database_path(":memory:")
        assert p1 == ":memory:"

        custom_path = str(tmp_path / "custom.db")
        p2 = resolve_database_path(custom_path)
        assert p2 == os.path.abspath(custom_path)

        # 2. Env Var
        env_path = str(tmp_path / "env.db")
        monkeypatch.setenv("OMNIX_DATABASE_PATH", env_path)
        assert resolve_database_path() == os.path.abspath(env_path)

        # 3. Default fallback
        monkeypatch.delenv("OMNIX_DATABASE_PATH", raising=False)
        default_path = resolve_database_path()
        assert default_path.endswith("omnix_inventory.db")


# =============================================================================
# 2. Component Identity Normalization & Conflict Detection Tests
# =============================================================================

class TestComponentIdentity:
    def test_case_and_whitespace_normalization(self, populated_repo):
        prod = InventoryProduct(
            manufacturer="  Texas Instruments  ",
            mpn="  ne555p ",
            category="Integrated Circuit",
            type_technology="Linear Regulator",
            package="DIP-8",
            footprint="DIP8_W",
            value="NE555",
            quantity_in_stock=25,
        )
        created = populated_repo.create_component(prod)
        assert created.norm_manufacturer == "TEXAS INSTRUMENTS"
        assert created.norm_mpn == "NE555P"
        # Display casing must be preserved with stripped outer whitespace
        assert created.manufacturer == "Texas Instruments"
        assert created.mpn == "ne555p"

    def test_duplicate_component_raises_conflict_error(self, populated_repo):
        prod1 = InventoryProduct(
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="SMD_0603",
            value="10k",
            quantity_in_stock=100,
        )
        populated_repo.create_component(prod1)

        # Duplicate with different casing and whitespace
        prod2 = InventoryProduct(
            manufacturer="  yageo  ",
            mpn="  rc0603fr-0710kl  ",
            category="Resistor",
            type_technology="Thick Film",
            package="0603",
            footprint="SMD_0603",
            value="10k",
            quantity_in_stock=50,
        )

        with pytest.raises(ComponentConflictError) as exc_info:
            populated_repo.create_component(prod2)

        err = exc_info.value
        assert "already exists in database" in str(err)
        assert err.existing_component is not None
        assert err.existing_component.norm_mpn == "RC0603FR-0710KL"
        # Confirm stock was NOT silently added together
        fetched = populated_repo.get_component_by_identity("Yageo", "RC0603FR-0710KL")
        assert fetched.quantity_in_stock == 100

    def test_update_identity_conflict(self, populated_repo):
        prod1 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71H104KA93D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=200,
            )
        )
        prod2 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM188R71C105KA12D",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="1uF",
                quantity_in_stock=50,
            )
        )

        # Attempting to rename prod2 to prod1's identity must raise ComponentConflictError
        with pytest.raises(ComponentConflictError):
            populated_repo.update_component(prod2.id, mpn="grm188r71h104ka93d")

    def test_blank_manufacturer_or_mpn_rejected(self, populated_repo):
        with pytest.raises(ValidationError):
            populated_repo.create_component(
                InventoryProduct(
                    manufacturer="",
                    mpn="VALID-MPN",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                )
            )

        with pytest.raises(ValidationError):
            populated_repo.create_component(
                InventoryProduct(
                    manufacturer="Valid Mfr",
                    mpn="   ",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="10k",
                )
            )


# =============================================================================
# 3. Component CRUD & Validation Tests
# =============================================================================

class TestComponentCRUD:
    def test_create_and_read_component(self, populated_repo):
        prod = InventoryProduct(
            manufacturer="STMicroelectronics",
            mpn="STM32F401RET6",
            category="Integrated Circuit",
            type_technology="Microcontroller",
            package="LQFP-64",
            footprint="LQFP64_10x10",
            value="STM32F401RE",
            description="ARM Cortex-M4 MCU with 512KB Flash",
            quantity_in_stock=10,
        )
        created = populated_repo.create_component(prod)
        assert created.id is not None
        assert created.id > 0

        # Read by ID
        by_id = populated_repo.get_component_by_id(created.id)
        assert by_id is not None
        assert by_id.mpn == "STM32F401RET6"
        assert by_id.quantity_in_stock == 10

        # Read by identity (case-insensitive)
        by_ident = populated_repo.get_component_by_identity("stmicroelectronics", "stm32f401ret6")
        assert by_ident is not None
        assert by_ident.id == created.id

    def test_zero_stock_allowed_negative_rejected(self, populated_repo):
        # 0 stock allowed
        prod_zero = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805FR-07100RL",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="SMD_0805",
                value="100R",
                quantity_in_stock=0,
            )
        )
        assert prod_zero.quantity_in_stock == 0

        # Negative stock rejected on create
        with pytest.raises(ValidationError):
            populated_repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="RC0805FR-07200RL",
                    category="Resistor",
                    type_technology="Thick Film",
                    package="0805",
                    footprint="SMD_0805",
                    value="200R",
                    quantity_in_stock=-5,
                )
            )

        # Negative stock rejected on update
        with pytest.raises(ValidationError):
            populated_repo.update_component(prod_zero.id, quantity_in_stock=-1)

    def test_update_component_fields(self, populated_repo):
        created = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Texas Instruments",
                mpn="LM317T",
                category="Integrated Circuit",
                type_technology="Linear Regulator",
                package="TO-220",
                footprint="TO220_V",
                value="LM317",
                description="Adjustable regulator",
                quantity_in_stock=15,
            )
        )

        updated = populated_repo.update_component(
            created.id,
            description="Updated 1.5A adjustable regulator",
            quantity_in_stock=35,
        )
        assert updated.description == "Updated 1.5A adjustable regulator"
        assert updated.quantity_in_stock == 35

    def test_delete_component(self, populated_repo):
        created = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Texas Instruments",
                mpn="SN74HC595N",
                category="Integrated Circuit",
                type_technology="Logic",
                package="DIP-16",
                footprint="DIP16_W",
                value="74HC595",
                quantity_in_stock=40,
            )
        )
        assert populated_repo.delete_component(created.id) is True
        assert populated_repo.get_component_by_id(created.id) is None
        # Deleting non-existent returns False
        assert populated_repo.delete_component(created.id) is False

    def test_search_components(self, populated_repo):
        populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-071KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="1k",
                description="Precision 1k resistor",
                quantity_in_stock=100,
            )
        )
        populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                description="Precision 10k resistor",
                quantity_in_stock=200,
            )
        )

        results = populated_repo.search_components("Yageo 10k")
        assert len(results) == 1
        assert results[0].mpn == "RC0603FR-0710KL"


# =============================================================================
# 4. Supplier Links (One-to-Many) Tests
# =============================================================================

class TestSupplierLinks:
    def test_multiple_supplier_links_and_cascade_delete(self, populated_repo):
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="STMicroelectronics",
                mpn="STM32F103C8T6",
                category="Integrated Circuit",
                type_technology="Microcontroller",
                package="LQFP-48",
                footprint="LQFP48",
                value="STM32F103C8",
                quantity_in_stock=12,
            )
        )

        # Add two supplier links
        link1 = populated_repo.add_supplier_link(
            component_id=comp.id,
            vendor_id="lion",
            vendor_label="Lion",
            url="https://lionelectronic.ir/p/123",
            display_name="Lion STM32",
        )
        link2 = populated_repo.add_supplier_link(
            component_id=comp.id,
            vendor_id="javan",
            vendor_label="Javan",
            url="https://javanelec.com/product/456",
            display_name="Javan STM32",
        )

        links = populated_repo.get_supplier_links(comp.id)
        assert len(links) == 2
        assert {l.vendor_id for l in links} == {"lion", "javan"}

        # Check component includes links
        fetched = populated_repo.get_component_by_id(comp.id)
        assert len(fetched.supplier_links) == 2
        assert "lionelectronic.ir" in fetched.purchase_link
        assert "javanelec.com" in fetched.purchase_link

        # Delete component -> Cascade delete must remove links from supplier_links table
        populated_repo.delete_component(comp.id)
        conn = populated_repo.db_manager.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM supplier_links WHERE component_id = ?;", (comp.id,)).fetchone()[0]
        assert count == 0

    def test_set_supplier_links_atomic_replacement(self, populated_repo):
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Texas Instruments",
                mpn="NE555DR",
                category="Integrated Circuit",
                type_technology="Linear Regulator",
                package="SOIC-8",
                footprint="SOIC8",
                value="NE555",
                quantity_in_stock=50,
            )
        )
        populated_repo.add_supplier_link(comp.id, "lion", "Lion", "https://lion.ir/1")

        new_links = [
            SupplierLink(vendor_id="javan", vendor_label="Javan", url="https://javan.ir/new1"),
            SupplierLink(vendor_id="generic", vendor_label="LINK", url="https://generic.com/item"),
        ]
        replaced = populated_repo.set_supplier_links(comp.id, new_links)
        assert len(replaced) == 2
        assert {l.vendor_id for l in replaced} == {"javan", "generic"}

    def test_create_component_with_formatted_purchase_link(self, populated_repo):
        # Provide multiple links in string format (e.g. from Excel or UI)
        link_str = "[Lion]: https://lionelectronic.ir/p/1 | [Javan]: https://javanelec.com/p/2"
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="GRM21BR71E105KA99L",
                category="Capacitor",
                type_technology="Ceramic",
                package="0805",
                footprint="SMD_0805",
                value="1uF",
                quantity_in_stock=100,
                purchase_link=link_str,
            )
        )

        links = populated_repo.get_supplier_links(comp.id)
        assert len(links) >= 1
        assert any("lionelectronic.ir" in l.url for l in links)


# =============================================================================
# 5. Canonical Reference Data Management Tests
# =============================================================================

class TestReferenceData:
    def test_manufacturer_duplicate_rejected(self, repo):
        repo.add_manufacturer("Samsung")
        with pytest.raises(DuplicateReferenceError):
            repo.add_manufacturer("  samsung  ")

    def test_manufacturer_delete_prevented_when_in_use(self, populated_repo):
        mfr = populated_repo.get_manufacturer_by_name("Texas Instruments")
        assert mfr is not None

        # Create component using this manufacturer
        populated_repo.create_component(
            InventoryProduct(
                manufacturer="Texas Instruments",
                mpn="TPS5430DDA",
                category="Integrated Circuit",
                type_technology="Linear Regulator",
                package="SO-8",
                footprint="SOIC8_EP",
                value="TPS5430",
                quantity_in_stock=15,
            )
        )

        # Deletion must be rejected with ReferenceDataInUseError
        with pytest.raises(ReferenceDataInUseError) as exc:
            populated_repo.delete_manufacturer(mfr.id)
        assert "in use" in str(exc.value)

        # Deactivation should succeed
        assert populated_repo.deactivate_manufacturer(mfr.id) is True
        mfr_updated = populated_repo.get_manufacturer(mfr.id)
        assert mfr_updated.is_active is False

    def test_manufacturer_rename_updates_components(self, populated_repo):
        mfr_id = populated_repo.add_manufacturer("Walsin Technology")
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Walsin Technology",
                mpn="WR06X1002FTL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=500,
            )
        )

        populated_repo.update_manufacturer(mfr_id, name="Walsin Tech Corp")
        updated_comp = populated_repo.get_component_by_id(comp.id)
        assert updated_comp.manufacturer == "Walsin Tech Corp"
        assert updated_comp.norm_manufacturer == "WALSIN TECH CORP"

    def test_category_and_type_hierarchy_and_constraints(self, repo):
        cat_id = repo.add_category("Connector")
        t_id1 = repo.add_type(cat_id, "Header")
        t_id2 = repo.add_type(cat_id, "Terminal Block")

        types = repo.get_types_for_category(cat_id)
        assert len(types) == 2
        assert {t.name for t in types} == {"Header", "Terminal Block"}

        # Cannot delete category with child types
        with pytest.raises(ReferenceDataInUseError):
            repo.delete_category(cat_id)

        # Delete types first
        repo.delete_type(t_id1)
        repo.delete_type(t_id2)
        # Now category can be deleted
        assert repo.delete_category(cat_id) is True

    def test_manufacturer_display_casing_rename_propagates_to_components(self, populated_repo):
        mfr_id = populated_repo.add_manufacturer("kemet")
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="kemet",
                mpn="C0603C104K5RACTU",
                category="Capacitor",
                type_technology="Ceramic",
                package="0603",
                footprint="SMD_0603",
                value="100nF",
                quantity_in_stock=50,
            )
        )
        assert comp.manufacturer == "kemet"

        # Update display casing only (norm remains "KEMET")
        populated_repo.update_manufacturer(mfr_id, name="KEMET")
        updated_comp = populated_repo.get_component_by_id(comp.id)
        assert updated_comp.manufacturer == "KEMET"
        assert updated_comp.norm_manufacturer == "KEMET"

    def test_manufacturer_rename_collision_raises_component_conflict_error(self, populated_repo):
        mfr_a_id = populated_repo.add_manufacturer("Mfr Alpha")
        mfr_b_id = populated_repo.add_manufacturer("Mfr Beta")

        comp_a = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Mfr Alpha",
                mpn="SHARED-MPN-1",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            )
        )
        comp_b = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Mfr Beta",
                mpn="SHARED-MPN-1",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            )
        )

        # 1. Reference table prevents renaming to an existing manufacturer
        with pytest.raises(DuplicateReferenceError):
            populated_repo.update_manufacturer(mfr_b_id, name="Mfr Alpha")

        # 2. Updating component directly to an existing (manufacturer, MPN) identity raises ComponentConflictError
        with pytest.raises(ComponentConflictError):
            populated_repo.update_component(comp_b.id, manufacturer="Mfr Alpha")

        # 3. Confirm quantities were NOT silently merged and identities remain intact
        fresh_a = populated_repo.get_component_by_id(comp_a.id)
        fresh_b = populated_repo.get_component_by_id(comp_b.id)
        assert fresh_a.manufacturer == "Mfr Alpha"
        assert fresh_b.manufacturer == "Mfr Beta"

    def test_category_rename_updates_components_and_stock_policies_and_group_key(self, populated_repo):
        cat_id = populated_repo.add_category("Potentiometer")
        t_id = populated_repo.add_type(cat_id, "Trimmer")

        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="PV36W103C01B00",
                category="Potentiometer",
                type_technology="Trimmer",
                package="Through Hole",
                footprint="TRIM_36W",
                value="10k",
                quantity_in_stock=25,
            )
        )
        old_key = comp.group_key
        assert old_key == "Potentiometer|Trimmer|10k|Through Hole|TRIM_36W"

        # Create a stock policy for this group
        pol = populated_repo.set_policy(old_key, min_stock=10, target_stock=30)
        assert pol.category == "Potentiometer"

        # Rename Category from "Potentiometer" to "Variable Resistor"
        populated_repo.update_category(cat_id, name="Variable Resistor")

        # 1. Component category and group_key must be updated
        updated_comp = populated_repo.get_component_by_id(comp.id)
        assert updated_comp.category == "Variable Resistor"
        new_key = "Variable Resistor|Trimmer|10k|Through Hole|TRIM_36W"
        assert updated_comp.group_key == new_key

        # 2. Stock policy category and group_key must be updated
        updated_pol = populated_repo.get_policy(new_key)
        assert updated_pol is not None
        assert updated_pol.category == "Variable Resistor"
        assert updated_pol.min_stock == 10
        assert updated_pol.target_stock == 30
        assert populated_repo.get_policy(old_key) is None

        # 3. Aggregation across get_all_groups() reflects the new group key
        all_groups = populated_repo.get_all_groups()
        assert any(g.group_key == new_key for g in all_groups)
        assert not any(g.group_key == old_key for g in all_groups)

    def test_type_rename_is_scoped_to_category_and_does_not_mutate_other_categories(self, populated_repo):
        # Category 1: Resistor has Type "Film"
        cat_res = populated_repo.get_category_by_name("Resistor").id
        t_res_film = populated_repo.add_type(cat_res, "Film")

        # Category 2: Capacitor has Type "Film"
        cat_cap = populated_repo.get_category_by_name("Capacitor").id
        t_cap_film = populated_repo.add_type(cat_cap, "Film")

        comp_res = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RES-FILM-1",
                category="Resistor",
                type_technology="Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
            )
        )
        comp_cap = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Murata",
                mpn="CAP-FILM-1",
                category="Capacitor",
                type_technology="Film",
                package="0603",
                footprint="SMD_0603",
                value="10nF",
            )
        )

        # Rename Type "Film" under Resistor to "Metal Film"
        populated_repo.update_type(t_res_film, name="Metal Film")

        # Resistor component must be updated
        up_res = populated_repo.get_component_by_id(comp_res.id)
        assert up_res.type_technology == "Metal Film"
        assert up_res.group_key == "Resistor|Metal Film|10k|0603|SMD_0603"

        # Capacitor component MUST REMAIN UNTOUCHED
        up_cap = populated_repo.get_component_by_id(comp_cap.id)
        assert up_cap.type_technology == "Film"
        assert up_cap.group_key == "Capacitor|Film|10nF|0603|SMD_0603"

    def test_type_move_with_in_use_components_raises_reference_in_use_error(self, populated_repo):
        cat_res = populated_repo.get_category_by_name("Resistor").id
        cat_cap = populated_repo.get_category_by_name("Capacitor").id
        t_thick = next(t for t in populated_repo.get_types_for_category(cat_res) if t.name == "Thick Film")

        # Create component using this type under Resistor
        populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0402FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0402",
                footprint="SMD_0402",
                value="10k",
            )
        )

        # Attempt to move "Thick Film" type to Capacitor category must be rejected
        with pytest.raises(ReferenceDataInUseError) as exc:
            populated_repo.update_type(t_thick.id, category_id=cat_cap)
        assert "in use" in str(exc.value)

    def test_component_creation_and_update_validates_category_and_technology(self, populated_repo):
        # 1. Non-existent category
        with pytest.raises(ReferenceDataNotFoundError):
            populated_repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="TEST-UNKNOWN-CAT",
                    category="UnknownCategory",
                    type_technology="Thick Film",
                    package="0603",
                    footprint="SMD_0603",
                    value="1k",
                )
            )

        # 2. Mismatched category + type (Resistor + Ceramic)
        with pytest.raises(ValidationError) as exc:
            populated_repo.create_component(
                InventoryProduct(
                    manufacturer="Yageo",
                    mpn="TEST-MISMATCH",
                    category="Resistor",
                    type_technology="Ceramic",
                    package="0603",
                    footprint="SMD_0603",
                    value="1k",
                )
            )
        assert "not an active technology for category" in str(exc.value)

        # 3. Valid creation, followed by invalid update
        valid_comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="VALID-R1",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="1k",
            )
        )
        with pytest.raises(ValidationError):
            populated_repo.update_component(valid_comp.id, type_technology="Ceramic")


# =============================================================================
# 6. Aggregation & Stock Policy Persistence Tests
# =============================================================================

class TestStockAggregationAndPolicies:
    def test_five_field_grouping_and_package_normalization(self, populated_repo):
        # Two components that normalize to the same package (603 and 0603)
        c1 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        c2 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Walsin",
                mpn="WR06X1002FTL",
                category="Resistor",
                type_technology="Thick Film",
                package="603",  # Numeric package that normalizes to 0603
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=150,
            )
        )

        assert c1.group_key == c2.group_key
        assert c1.group_key == "Resistor|Thick Film|10k|0603|SMD_0603"

        # Check aggregation
        group = populated_repo.get_group(c1.group_key)
        assert group is not None
        assert group.current_stock == 250
        assert len(group.products) == 2

    def test_footprint_participates_in_grouping(self, populated_repo):
        # Same Cat/Tech/Val/Pkg but different Footprint must form separate groups
        c1 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805_FP1",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="FOOTPRINT_A",
                value="1k",
                quantity_in_stock=50,
            )
        )
        c2 = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0805_FP2",
                category="Resistor",
                type_technology="Thick Film",
                package="0805",
                footprint="FOOTPRINT_B",
                value="1k",
                quantity_in_stock=75,
            )
        )

        assert c1.group_key != c2.group_key
        assert populated_repo.get_group(c1.group_key).current_stock == 50
        assert populated_repo.get_group(c2.group_key).current_stock == 75

    def test_policy_upsert_validation_and_persistence(self, populated_repo, temp_db_path):
        key = "Capacitor|Ceramic|100nF|0603|SMD_0603"

        # Invalid: Target < Min
        with pytest.raises(ValidationError):
            populated_repo.set_policy(key, min_stock=100, target_stock=50)

        # Invalid: Negative min stock
        with pytest.raises(ValidationError):
            populated_repo.set_policy(key, min_stock=-10, target_stock=50)

        # Valid policy
        pol = populated_repo.set_policy(
            key,
            min_stock=200,
            target_stock=500,
            description="100nF decoupling capacitor policy",
        )
        assert pol.min_stock == 200
        assert pol.target_stock == 500

        # Close and reopen database: policy must persist
        populated_repo.close()
        reopened_repo = SqliteInventoryRepository(temp_db_path)
        persisted_pol = reopened_repo.get_policy(key)
        assert persisted_pol is not None
        assert persisted_pol.min_stock == 200
        assert persisted_pol.target_stock == 500
        reopened_repo.close()

    def test_policy_only_group_preservation_with_zero_stock(self, populated_repo):
        # A policy for a group with NO physical components in database
        key = "Integrated Circuit|Microcontroller|ATmega328P|TQFP-32|TQFP32"
        populated_repo.set_policy(
            key,
            min_stock=50,
            target_stock=100,
            category="Integrated Circuit",
            type_technology="Microcontroller",
            value="ATmega328P",
            package="TQFP-32",
            footprint="TQFP32",
            description="Main MCU policy",
        )

        all_groups = populated_repo.get_all_groups()
        atmega_group = next((g for g in all_groups if g.group_key == key), None)
        assert atmega_group is not None
        assert atmega_group.current_stock == 0
        assert len(atmega_group.products) == 0
        assert atmega_group.min_stock == 50
        assert atmega_group.target_stock == 100
        assert atmega_group.is_under_stocked is True
        assert atmega_group.shortage_to_min == 50

    def test_get_group_for_non_existent_key(self, populated_repo):
        assert populated_repo.get_group("NonExistent|Group|Key|0000|FP") is None

    def test_individual_five_field_updates_update_group_key_and_preserve_policies(self, populated_repo):
        # Initial component
        comp = populated_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603FR-TEST",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="SMD_0603",
                value="10k",
                quantity_in_stock=100,
            )
        )
        init_key = "Resistor|Thick Film|10k|0603|SMD_0603"
        assert comp.group_key == init_key

        # Establish policy on initial group
        populated_repo.set_policy(init_key, min_stock=50, target_stock=200)

        # 1. Update Value (10k -> 20k)
        u_val = populated_repo.update_component(comp.id, value="20k")
        key_val = "Resistor|Thick Film|20k|0603|SMD_0603"
        assert u_val.group_key == key_val
        # Old group policy preserved as policy-only group with stock 0
        old_grp = populated_repo.get_group(init_key)
        assert old_grp is not None
        assert old_grp.current_stock == 0
        assert old_grp.min_stock == 50
        # New group has 100 stock
        new_grp = populated_repo.get_group(key_val)
        assert new_grp.current_stock == 100

        # 2. Update Package with leading zeroes normalization (e.g. 805 -> '0805')
        u_pkg = populated_repo.update_component(comp.id, package="805")
        key_pkg = "Resistor|Thick Film|20k|0805|SMD_0603"
        assert u_pkg.package == "0805"
        assert u_pkg.group_key == key_pkg

        # 3. Update Footprint (SMD_0603 -> SMD_0805_CUSTOM)
        u_fp = populated_repo.update_component(comp.id, footprint="SMD_0805_CUSTOM")
        key_fp = "Resistor|Thick Film|20k|0805|SMD_0805_CUSTOM"
        assert u_fp.footprint == "SMD_0805_CUSTOM"
        assert u_fp.group_key == key_fp

        # 4. Update Type/Technology (Thick Film -> Thin Film)
        u_tech = populated_repo.update_component(comp.id, type_technology="Thin Film")
        key_tech = "Resistor|Thin Film|20k|0805|SMD_0805_CUSTOM"
        assert u_tech.type_technology == "Thin Film"
        assert u_tech.group_key == key_tech

        # 5. Update Category (Resistor -> Capacitor, with valid type Ceramic)
        u_cat = populated_repo.update_component(comp.id, category="Capacitor", type_technology="Ceramic")
        key_cat = "Capacitor|Ceramic|20k|0805|SMD_0805_CUSTOM"
        assert u_cat.category == "Capacitor"
        assert u_cat.group_key == key_cat
