"""
Omnix Automated Tests for Vendor & Link Providers Reference Data
Governing Document: Phase F Specification
"""

import pytest
from PyQt6.QtWidgets import QApplication

from core.inventory.repository import SqliteInventoryRepository
from core.inventory.models import (
    ProviderRecord,
    DuplicateReferenceError,
    ReferenceDataInUseError,
    ValidationError,
    InventoryProduct,
    SupplierLink,
)
from ui.dialogs.provider_dialog import ProviderManagementDialog, ProviderEditDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_repo(tmp_path):
    db_path = str(tmp_path / "providers_test.db")
    repo = SqliteInventoryRepository(db_path)
    yield repo
    repo.close()


class TestProviderReferenceDataCRUD:
    """Verifies ref_providers table and repository CRUD."""

    def test_default_seeded_providers(self, clean_repo):
        providers = clean_repo.get_all_providers(include_inactive=True)
        # Should have seeded default providers: Lion, Javan, RoboEq, Generic
        p_ids = {p.provider_id for p in providers}
        assert "vendor_lion" in p_ids
        assert "vendor_javan" in p_ids
        assert "vendor_roboeq" in p_ids
        assert "generic" in p_ids

    def test_add_custom_provider(self, clean_repo):
        p = clean_repo.add_provider(
            provider_id="vendor_mouser",
            name="Mouser Electronics",
            label="MOUSER",
            base_url="https://www.mouser.com",
            is_active=True,
        )
        assert p.id is not None
        assert p.provider_id == "vendor_mouser"
        assert p.label == "MOUSER"

        fetched = clean_repo.get_provider("vendor_mouser")
        assert fetched is not None
        assert fetched.name == "Mouser Electronics"
        assert fetched.base_url == "https://www.mouser.com"

    def test_prevent_duplicate_provider_id_or_name(self, clean_repo):
        with pytest.raises(DuplicateReferenceError):
            clean_repo.add_provider(
                provider_id="vendor_lion",  # Duplicate ID
                name="Lion New",
                label="LION_NEW",
            )

        with pytest.raises(DuplicateReferenceError):
            clean_repo.add_provider(
                provider_id="vendor_lion_2",
                name="Lion Electronic (LION)",  # Duplicate name
                label="LION2",
            )

    def test_update_provider_details(self, clean_repo):
        p = clean_repo.add_provider("vendor_digikey", "DigiKey", "DIGIKEY")
        updated = clean_repo.update_provider(
            provider_pk=p.id,
            name="DigiKey Electronics",
            base_url="https://www.digikey.com",
            is_active=False,
        )
        assert updated is not None
        assert updated.name == "DigiKey Electronics"
        assert updated.base_url == "https://www.digikey.com"
        assert updated.is_active is False

        # Inactive providers excluded by default
        active_ids = {x.provider_id for x in clean_repo.get_all_providers(include_inactive=False)}
        assert "vendor_digikey" not in active_ids

        all_ids = {x.provider_id for x in clean_repo.get_all_providers(include_inactive=True)}
        assert "vendor_digikey" in all_ids

    def test_delete_provider_in_use_blocked(self, clean_repo):
        clean_repo.add_category("Resistor")
        clean_repo.add_type(1, "Thick Film")
        comp = clean_repo.create_component(
            InventoryProduct(
                manufacturer="Yageo",
                mpn="RC0603-TEST",
                category="Resistor",
                type_technology="Thick Film",
                package="0603",
                footprint="R_0603",
                value="10k",
            )
        )
        clean_repo.set_supplier_links(
            comp.id,
            [SupplierLink(vendor_id="vendor_lion", vendor_label="LION", url="https://lionelectronic.ir/p/1")]
        )

        lion_provider = clean_repo.get_provider("vendor_lion")
        assert lion_provider is not None

        # Attempting to delete vendor_lion when linked to a component raises ReferenceDataInUseError
        with pytest.raises(ReferenceDataInUseError):
            clean_repo.delete_provider(lion_provider.id)

    def test_provider_management_dialog_ui(self, qapp, clean_repo):
        dlg = ProviderManagementDialog(repository=clean_repo)
        dlg.show()
        qapp.processEvents()

        assert dlg.table.rowCount() >= 4
        assert dlg.add_btn.isEnabled() is True
        assert dlg.edit_btn.isEnabled() is False

        # Select a row
        dlg.table.selectRow(0)
        qapp.processEvents()
        assert dlg.edit_btn.isEnabled() is True
        assert dlg.toggle_active_btn.isEnabled() is True
        assert dlg.delete_btn.isEnabled() is True

        dlg.close()
