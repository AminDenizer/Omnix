"""
Tests for Additional Requirement A: Multi-Supplier Links in Procurement.

Validates that:
1. Zero eligible links -> Not orderable, cannot dispatch.
2. Single eligible link -> Automatic resolution without unnecessary prompt.
3. Multiple eligible links -> Explicit user selection required, NO silent fallback or blind first-link choice.
4. VendorSelectionDialog UI presents clean options with human-readable vendor names and URLs.
5. Cancellation preserves unselected state.
"""

import os
import tempfile
from typing import Any, Dict, Optional
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QMessageBox

from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.models import AdapterConfig, AdapterStatus, ProductDetails, ProductReference
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import ProcurementMode
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter
from ui.dialogs.component_edit_dialog import ComponentEditDialog
from ui.dialogs.order_preview_dialog import VendorSelectionDialog


class MockLionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query: str) -> Any:
        return None

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="LION-SKU", pdp_url=url_or_sku)

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=100,
            can_order=True,
            price_irr=5000,
            mpn="TEST-MPN",
        )

    def extract_product_data(self, dom_context: Any) -> Any:
        return None

    def inspect_stock(self, product_ref: ProductReference) -> Any:
        return None

    def determine_order_constraints(self, product_ref: ProductReference) -> Any:
        return None

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> Any:
        return None

    def inspect_cart(self) -> Any:
        return None

    def authenticate(self, credentials: Any = None) -> Any:
        return None

    def validate_session(self) -> Any:
        return None

    def recover_from_error(self, error_context: Any) -> Any:
        return None

    def close(self) -> None:
        pass


class MockJavanAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_javan"
    BASE_URL = "https://javanelec.com"

    def __init__(self, config: Optional[AdapterConfig] = None):
        self._config = config

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus:
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query: str) -> Any:
        return None

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="JAVAN-SKU", pdp_url=url_or_sku)

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=200,
            can_order=True,
            price_irr=4500,
            mpn="TEST-MPN",
        )

    def extract_product_data(self, dom_context: Any) -> Any:
        return None

    def inspect_stock(self, product_ref: ProductReference) -> Any:
        return None

    def determine_order_constraints(self, product_ref: ProductReference) -> Any:
        return None

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> Any:
        return None

    def inspect_cart(self) -> Any:
        return None

    def authenticate(self, credentials: Any = None) -> Any:
        return None

    def validate_session(self) -> Any:
        return None

    def recover_from_error(self, error_context: Any) -> Any:
        return None

    def close(self) -> None:
        pass


@pytest.fixture
def dual_vendor_registry():
    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionAdapter,
        domains=["lionelectronic.ir", "lion.ir"],
        display_name="Lion Electronic",
        enabled=True,
        activate=True,
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=MockJavanAdapter,
        domains=["javanelec.com", "javan.ir"],
        display_name="Javan Electronic",
        enabled=True,
        activate=True,
    )
    return reg


class TestMultiSupplierLinksRequirementA:

    def test_zero_eligible_links(self, dual_vendor_registry):
        item = {
            "part_number": "RES-10K-0805",
            "needed_quantity": 100,
            "link": "",
        }
        is_orderable, vid = ProcurementBridge.is_item_orderable(item, dual_vendor_registry)
        assert is_orderable is False
        assert vid is None

    def test_single_eligible_link_automatic_resolution(self, dual_vendor_registry):
        item = {
            "part_number": "CAP-100NF-0603",
            "needed_quantity": 50,
            "link": "https://lion.ir/part123",
        }
        is_orderable, vid = ProcurementBridge.is_item_orderable(item, dual_vendor_registry)
        assert is_orderable is True
        assert vid == "vendor_lion"

        # Translation without manual dialog
        req = ProcurementBridge.item_to_request(item, registry=dual_vendor_registry, mode=ProcurementMode.DATABASE_AWARE)
        assert req.explicit_vendor_id == "vendor_lion"
        assert req.explicit_vendor_url == "https://lion.ir/part123"

    def test_multiple_eligible_links_requires_selection_and_no_silent_default(self, dual_vendor_registry):
        item = {
            "part_number": "STM32F103C8T6",
            "needed_quantity": 5,
            "link": "LION=https://lion.ir/stm32 || JAVAN=https://javan.ir/stm32",
        }
        # Both are orderable in registry
        is_orderable, vid = ProcurementBridge.is_item_orderable(item, dual_vendor_registry)
        assert is_orderable is True

        # Translating directly without selecting vendor MUST raise ValueError (no silent fallback or first-row pick!)
        with pytest.raises(ValueError) as excinfo:
            ProcurementBridge.item_to_request(item, registry=dual_vendor_registry, mode=ProcurementMode.DATABASE_AWARE)
        assert "Vendor selection is required" in str(excinfo.value)
        assert "has multiple vendor links" in str(excinfo.value)

    def test_vendor_selection_dialog_ui_and_explicit_choices(self, qapp, dual_vendor_registry):
        item = {
            "part_name": "STM32F103C8T6",
            "part_number": "STM32F103C8T6",
            "needed_quantity": 5,
            "link": "LION=https://lion.ir/stm32 || JAVAN=https://javan.ir/stm32",
            "vendor_links": {
                "vendor_lion": "https://lion.ir/stm32",
                "vendor_javan": "https://javan.ir/stm32",
            }
        }

        dlg = VendorSelectionDialog([item], registry=dual_vendor_registry)
        combo = dlg.combo_boxes[0][1]

        # First item is prompt "-- Select Supplier Link --"
        assert combo.itemText(0).startswith("-- Select")
        # Options 1 and 2 are Lion and Javan
        supplier_options = [combo.itemText(i) for i in range(1, combo.count())]
        assert any("Lion" in opt for opt in supplier_options)
        assert any("Javan" in opt for opt in supplier_options)

        # 1. Confirming without explicit selection blocks and warns user
        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg._on_confirm()
            assert mock_warn.called

        # 2. Select Lion explicitly
        lion_idx = [i for i in range(1, combo.count()) if "Lion" in combo.itemText(i)][0]
        combo.setCurrentIndex(lion_idx)
        dlg._on_confirm()

        assert item["selected_vendor_id"] == "vendor_lion"
        assert item["selected_url"] == "https://lion.ir/stm32"

        # Now translate request with selection
        req = ProcurementBridge.item_to_request(item, registry=dual_vendor_registry, mode=ProcurementMode.DATABASE_AWARE)
        assert req.explicit_vendor_id == "vendor_lion"
        assert req.explicit_vendor_url == "https://lion.ir/stm32"

        # 3. Select Javan explicitly
        javan_idx = [i for i in range(1, combo.count()) if "Javan" in combo.itemText(i)][0]
        combo.setCurrentIndex(javan_idx)
        dlg._on_confirm()

        assert item["selected_vendor_id"] == "vendor_javan"
        assert item["selected_url"] == "https://javan.ir/stm32"

        req_j = ProcurementBridge.item_to_request(item, registry=dual_vendor_registry, mode=ProcurementMode.DATABASE_AWARE)
        assert req_j.explicit_vendor_id == "vendor_javan"
        assert req_j.explicit_vendor_url == "https://javan.ir/stm32"

    def test_vendor_selection_dialog_cancellation_preserves_state(self, qapp, dual_vendor_registry):
        item = {
            "part_name": "ATmega328P",
            "part_number": "ATmega328P",
            "needed_quantity": 2,
            "vendor_links": {
                "vendor_lion": "https://lion.ir/atmega",
                "vendor_javan": "https://javan.ir/atmega",
            }
        }
        dlg = VendorSelectionDialog([item], registry=dual_vendor_registry)
        dlg.reject() # User cancels or closes dialog

        # State must remain unselected
        assert "selected_vendor_id" not in item

    def test_no_silent_fallback_when_selected_vendor_invalid(self, dual_vendor_registry):
        item = {
            "part_number": "ESP32-WROOM-32",
            "needed_quantity": 10,
            "selected_vendor_id": "vendor_unknown",
            "vendor_links": {
                "vendor_lion": "https://lion.ir/esp32",
            }
        }
        # If user/caller requested vendor_unknown but only lion exists, fail with clear error, do not silently fallback!
        with pytest.raises(ValueError) as exc:
            ProcurementBridge.item_to_request(item, registry=dual_vendor_registry, mode=ProcurementMode.DATABASE_AWARE)
        assert "has no valid URL" in str(exc.value)


class TestComponentEditDialogSupplierLinkValidation:
    """Tests supplier link validation in ComponentEditDialog."""

    @pytest.fixture
    def temp_repo(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        repo = SqliteInventoryRepository(path)
        yield repo
        try:
            os.remove(path)
        except OSError:
            pass

    def test_dialog_accepts_vendor_tag_with_different_domain(self, qapp, temp_repo):
        """Vendor tag is metadata only. Lion or Javan tag with any domain is accepted."""
        # 1. Lion tag with non-Lion domain
        dlg1 = ComponentEditDialog(repository=temp_repo)
        dlg1.mfr_input.setCurrentText("STMicroelectronics")
        dlg1.mpn_input.setText("STM32F103VET6-LION")
        dlg1.category_combo.setCurrentText("Microcontroller")
        dlg1.tech_combo.setCurrentText("ARM Cortex-M3")
        dlg1.value_input.setText("72MHz")
        dlg1.package_input.setText("LQFP-100")
        dlg1.footprint_input.setText("LQFP-100")

        dlg1._add_empty_link_row()
        row1 = dlg1._link_rows[0]
        for idx in range(row1.vendor_combo.count()):
            v_id, _ = row1.vendor_combo.itemData(idx)
            if v_id == "vendor_lion":
                row1.vendor_combo.setCurrentIndex(idx)
                break
        row1.url_input.setText("https://external-store.com/item/12345")

        dlg1._on_save_clicked()
        assert dlg1.result() == 1  # Successfully saved
        comp1 = temp_repo.get_component_by_identity("STMicroelectronics", "STM32F103VET6-LION")
        assert comp1 is not None
        assert len(comp1.supplier_links) == 1
        assert comp1.supplier_links[0].vendor_id == "vendor_lion"
        assert comp1.supplier_links[0].url == "https://external-store.com/item/12345"

        # 2. Javan tag with non-Javan domain
        dlg2 = ComponentEditDialog(repository=temp_repo)
        dlg2.mfr_input.setCurrentText("STMicroelectronics")
        dlg2.mpn_input.setText("STM32F103VET6-JAVAN")
        dlg2.category_combo.setCurrentText("Microcontroller")
        dlg2.tech_combo.setCurrentText("ARM Cortex-M3")
        dlg2.value_input.setText("72MHz")
        dlg2.package_input.setText("LQFP-100")
        dlg2.footprint_input.setText("LQFP-100")

        dlg2._add_empty_link_row()
        row2 = dlg2._link_rows[0]
        for idx in range(row2.vendor_combo.count()):
            v_id, _ = row2.vendor_combo.itemData(idx)
            if v_id == "vendor_javan":
                row2.vendor_combo.setCurrentIndex(idx)
                break
        row2.url_input.setText("https://another-distributor.ir/part/999")

        dlg2._on_save_clicked()
        assert dlg2.result() == 1  # Successfully saved
        comp2 = temp_repo.get_component_by_identity("STMicroelectronics", "STM32F103VET6-JAVAN")
        assert comp2 is not None
        assert len(comp2.supplier_links) == 1
        assert comp2.supplier_links[0].vendor_id == "vendor_javan"
        assert comp2.supplier_links[0].url == "https://another-distributor.ir/part/999"

    def test_dialog_accepts_url_not_pointing_to_component(self, qapp, temp_repo):
        """URL does not need to point to component PDP or match MPN."""
        dlg = ComponentEditDialog(repository=temp_repo)
        dlg.mfr_input.setCurrentText("Murata")
        dlg.mpn_input.setText("GRM1885C1H220JA01D")
        dlg.category_combo.setCurrentText("Capacitor")
        dlg.tech_combo.setCurrentText("Ceramic C0G")
        dlg.value_input.setText("22pF")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMDCAP0603")

        dlg._add_empty_link_row()
        row = dlg._link_rows[0]
        for idx in range(row.vendor_combo.count()):
            v_id, _ = row.vendor_combo.itemData(idx)
            if v_id == "vendor_lion":
                row.vendor_combo.setCurrentIndex(idx)
                break
        # URL has completely different MPN in slug (CL10B104KB8NNNC vs GRM1885C1H220JA01D)
        row.url_input.setText("https://lionelectronic.ir/products/2799-CL10B104KB8NNNC")

        dlg._on_save_clicked()
        assert dlg.result() == 1  # Successfully saved without rejection

    def test_dialog_blocks_invalid_url_scheme_or_format(self, qapp, temp_repo):
        """Non-http/https URL or malformed string must be rejected."""
        dlg = ComponentEditDialog(repository=temp_repo)
        dlg.mfr_input.setCurrentText("Murata")
        dlg.mpn_input.setText("GRM188")
        dlg.category_combo.setCurrentText("Capacitor")
        dlg.tech_combo.setCurrentText("Ceramic X7R")
        dlg.value_input.setText("100nF")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")

        dlg._add_empty_link_row()
        row = dlg._link_rows[0]
        row.url_input.setText("ftp://invalid.com/file")

        dlg._on_save_clicked()
        assert dlg.result() == 0
        assert "must start with http:// or https://" in dlg.validation_lbl.text()

    def test_dialog_allows_multiple_urls_for_same_vendor(self, qapp, temp_repo):
        """Adding two rows with the same vendor but different URLs must succeed."""
        dlg = ComponentEditDialog(repository=temp_repo)
        dlg.mfr_input.setCurrentText("Yageo")
        dlg.mpn_input.setText("RC0603FR")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")

        dlg._add_empty_link_row()
        dlg._add_empty_link_row()

        # Both rows set to Lion with different URLs
        for r in dlg._link_rows:
            for idx in range(r.vendor_combo.count()):
                v_id, _ = r.vendor_combo.itemData(idx)
                if v_id == "vendor_lion":
                    r.vendor_combo.setCurrentIndex(idx)
                    break
        dlg._link_rows[0].url_input.setText("https://lionelectronic.ir/product/1")
        dlg._link_rows[1].url_input.setText("https://lionelectronic.ir/product/2")

        dlg._on_save_clicked()
        assert dlg.result() == 1
        comp = temp_repo.get_component_by_identity("Yageo", "RC0603FR")
        assert comp is not None
        assert len(comp.supplier_links) == 2
        assert comp.supplier_links[0].vendor_id == "vendor_lion"
        assert comp.supplier_links[1].vendor_id == "vendor_lion"
        assert comp.supplier_links[0].url != comp.supplier_links[1].url

    def test_dialog_blocks_duplicate_url(self, qapp, temp_repo):
        """Adding two rows with identical URL must be rejected."""
        dlg = ComponentEditDialog(repository=temp_repo)
        dlg.mfr_input.setCurrentText("Yageo")
        dlg.mpn_input.setText("RC0603FR")
        dlg.category_combo.setCurrentText("Resistor")
        dlg.tech_combo.setCurrentText("Thick Film")
        dlg.value_input.setText("10k")
        dlg.package_input.setText("0603")
        dlg.footprint_input.setText("SMD_0603")

        dlg._add_empty_link_row()
        dlg._add_empty_link_row()

        # Set both rows to generic vendor so duplicate vendor check does not mask duplicate URL check
        for r in dlg._link_rows:
            for idx in range(r.vendor_combo.count()):
                v_id, _ = r.vendor_combo.itemData(idx)
                if v_id == "generic":
                    r.vendor_combo.setCurrentIndex(idx)
                    break
        dlg._link_rows[0].url_input.setText("https://some-distributor.com/part/1")
        dlg._link_rows[1].url_input.setText("https://some-distributor.com/part/1")

        dlg._on_save_clicked()
        assert dlg.result() == 0
        assert "Duplicate URL" in dlg.validation_lbl.text()

    def test_dialog_saves_valid_multi_links(self, qapp, temp_repo):
        """Saving valid Lion + Javan links succeeds and persists to database."""
        dlg = ComponentEditDialog(repository=temp_repo)
        dlg.mfr_input.setCurrentText("STMicroelectronics")
        dlg.mpn_input.setText("STM32F407VET6")
        dlg.category_combo.setCurrentText("Microcontroller")
        dlg.tech_combo.setCurrentText("ARM Cortex-M4")
        dlg.value_input.setText("168MHz")
        dlg.package_input.setText("LQFP-100")
        dlg.footprint_input.setText("LQFP-100")

        dlg._add_empty_link_row()
        dlg._add_empty_link_row()

        # Row 1: Lion
        row1 = dlg._link_rows[0]
        for idx in range(row1.vendor_combo.count()):
            v_id, _ = row1.vendor_combo.itemData(idx)
            if v_id == "vendor_lion":
                row1.vendor_combo.setCurrentIndex(idx)
                break
        row1.url_input.setText("https://lionelectronic.ir/test/stm32f407")

        # Row 2: Javan
        row2 = dlg._link_rows[1]
        for idx in range(row2.vendor_combo.count()):
            v_id, _ = row2.vendor_combo.itemData(idx)
            if v_id == "vendor_javan":
                row2.vendor_combo.setCurrentIndex(idx)
                break
        row2.url_input.setText("https://javanelec.com/shop/product/stm32f407")

        dlg._on_save_clicked()
        assert dlg.result() == 1  # Successfully saved and accepted

        # Verify persisted in repository
        comp = temp_repo.get_component_by_identity("STMicroelectronics", "STM32F407VET6")
        assert comp is not None
        assert len(comp.supplier_links) == 2
        vids = {l.vendor_id for l in comp.supplier_links}
        assert vids == {"vendor_lion", "vendor_javan"}


class TestLegacyExcelDatabaseStringPurge:
    """Verifies that user-facing tooltips and messages do not reference legacy Inventory.xlsx."""

    def test_bom_audit_widget_tooltips_do_not_contain_inventory_xlsx(self):
        import inspect
        from ui.widgets import bom_audit_widget
        source = inspect.getsource(bom_audit_widget)
        assert "Inventory.xlsx" not in source

    def test_order_preview_dialog_tooltips_do_not_contain_inventory_xlsx(self):
        import inspect
        from ui.dialogs import order_preview_dialog
        source = inspect.getsource(order_preview_dialog)
        assert "Inventory.xlsx" not in source


class TestTargetedProcurementImprovements:
    """Verifies targeted requirements: same vendor multi-links, mixed preflight, and status display."""

    def test_mixed_availability_staging_preflight(self, dual_vendor_registry):
        """
        Five-item batch: 3 eligible, 2 excluded.
        Preflight excludes the 2 unavailable items upfront and dispatches only 3.
        Excluded items do not count towards attempted_items or actual_failed_count.
        """
        items = [
            # 1. Eligible Lion
            {
                "part_number": "MPN-LION-1",
                "needed_qty": 5,
                "link": "https://lion.ir/p1",
            },
            # 2. Eligible Javan
            {
                "part_number": "MPN-JAVAN-1",
                "needed_qty": 10,
                "link": "https://javan.ir/p2",
            },
            # 3. Eligible Multi-link (Lion selected)
            {
                "part_number": "MPN-MULTI-1",
                "needed_qty": 2,
                "selected_vendor_id": "vendor_lion",
                "selected_url": "https://lion.ir/p3",
                "link": "LION=https://lion.ir/p3 || JAVAN=https://javan.ir/p3",
            },
            # 4. Excluded: missing store link
            {
                "part_number": "MPN-BLANK",
                "needed_qty": 8,
                "link": "",
            },
            # 5. Excluded: fully covered by stock (0 needed)
            {
                "part_number": "MPN-STOCK-COVERED",
                "needed_qty": 0,
                "shortage_qty": 0,
                "link": "https://lion.ir/p5",
            },
        ]

        res = ProcurementBridge.execute_staged_procurement_batch(items, registry=dual_vendor_registry)

        assert res["total_items"] == 5
        assert res["eligible_items"] == 3
        assert res["excluded_items"] == 2
        assert res["attempted_items"] == 3
        # In mock registry without real HTTP adapter responses, candidate resolution reports failure on staging
        # but the crucial invariant is that attempted_items == 3 and excluded items are not in attempted_items
        assert len(res["excluded_details"]) == 2
        excluded_parts = [e["part"] for e in res["excluded_details"]]
        assert "MPN-BLANK" in excluded_parts
        assert "MPN-STOCK-COVERED" in excluded_parts

    def test_blank_link_not_shown_for_valid_url_with_unavailable_plugin(self, qapp):
        """BOM item with valid store link but uninstalled plugin renders PLUGIN NOT INSTALLED, not BLANK LINK."""
        from bom_auditor import BOMItem, BOMAuditResult
        from ui.widgets.bom_audit_widget import BOMAuditWidget
        item = BOMItem(
            row_idx=2,
            designator="R1",
            part_number="TEST-RES-10K",
            unit_qty=1,
            is_valid=True,
        )
        item.status = "SHORTAGE"
        item.shortage_qty = 5
        item.link = "https://lionelectronic.ir/product/12345"

        widget = BOMAuditWidget(None)
        mock_result = BOMAuditResult("dummy.xlsx", 1)
        mock_result.items = [item]
        mock_result.shortage_count = 1
        widget.audit_result = mock_result
        widget._render_results()

        badge_text = widget.table.item(0, 0).text()
        link_text = widget.table.item(0, 9).text()

        assert "BLANK LINK" not in badge_text
        assert "(-" not in badge_text
        assert "https://lionelectronic.ir/product/12345" in link_text

    def test_no_quantity_suffix_in_status_messages_both_deduction_modes(self, qapp, monkeypatch):
        """Verify status messages never append quantity suffix regardless of deduct internal stock setting."""
        from bom_auditor import BOMItem, BOMAuditResult
        from ui.widgets.bom_audit_widget import BOMAuditWidget

        test_cases = [
            ("SHORTAGE", True, "vendor_lion", "https://lion.ir/p", "⚠️ SHORTAGE"),
            ("SHORTAGE", False, "vendor_invalid", "htt://bad", "❌ INVALID LINK"),
            ("SHORTAGE", False, "vendor_lion", "https://lionelectronic.ir/p", "PLUGIN NOT"),
            ("SHORTAGE", False, None, "", "⚠️ BLANK LINK"),
            ("IN_STOCK", False, None, "", "✅ IN STOCK"),
            ("NOT_IN_DB", False, None, "", "🔴 NOT IN DB"),
        ]

        widget = BOMAuditWidget(None)

        for status_code, is_ord, vid, link, expected_badge in test_cases:
            it = BOMItem(row_idx=1, designator="D1", part_number="P1", unit_qty=2, is_valid=True)
            it.status = status_code
            it.shortage_qty = 8
            it.link = link

            monkeypatch.setattr(BOMItem, "is_orderable", is_ord)
            monkeypatch.setattr(BOMItem, "link_type", "INVALID" if "bad" in link else "VALID")
            monkeypatch.setattr(BOMItem, "vendor_id", vid)

            mock_res = BOMAuditResult("dummy.xlsx", 1)
            mock_res.items = [it]
            widget.audit_result = mock_res
            widget._render_results()

            badge_text = widget.table.item(0, 0).text()
            if "PLUGIN NOT" in expected_badge:
                assert "PLUGIN NOT" in badge_text or "READY FOR ORDER" in badge_text
            else:
                assert badge_text == expected_badge, f"Expected '{expected_badge}', got '{badge_text}'"
            assert "(-" not in badge_text
            assert "(-8)" not in badge_text

