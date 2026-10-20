"""
Tests for Multi-Vendor Purchase Link Integration for Mode A.
Governing Requirements:
- Section 9.1: Parser Tests (19 scenarios)
- Section 9.2: Single-Link Behavior (bypasses dialog, direct dispatch)
- Section 9.3: Multi-Link Selection (dialog prompt, meaningful display names, cancel safety, selection preservation)
- Section 9.4: Adapter Dispatch & Regression (atomic resolution, combined string isolation, Case D enforcement)
"""

from typing import Any, Dict, List, Optional
import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QDialog

from core.models import AdapterConfig, AdapterStatus, ProductDetails, ProductReference
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import ProcurementMode, ProcurementRequest
from core.procurement.registry import VendorRegistry
from core.procurement.vendor_links import (
    ParsedVendorLinks,
    VendorLinkEntry,
    parse_vendor_links,
)
from core.vendor_interface import IVendorAdapter
from excel_loader import ExcelDataLoader
from ui.dialogs.order_preview_dialog import OrderPreviewDialog, VendorSelectionDialog


# Ensure QApplication instance for Qt-related tests
@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Mock adapters for testing
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
            mpn="NUP2105LT1G",
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
            mpn="NUP2105LT1G",
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
def mock_registry():
    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionAdapter,
        domains=["lionelectronic.ir"],
        display_name="Lion Electronic",
        enabled=True,
        activate=True,
    )
    reg.register_adapter(
        vendor_id="vendor_javan",
        adapter_class=MockJavanAdapter,
        domains=["javanelec.com"],
        display_name="Javan Electronic",
        enabled=True,
        activate=True,
    )
    return reg


# =============================================================================
# 9.1 PARSER TESTS (19 SCENARIOS)
# =============================================================================

class TestVendorLinksParser:
    """Covers all 19 required parsing scenarios from Section 9.1."""

    def test_legacy_plain_lion_url(self, mock_registry):
        url = "https://lionelectronic.ir/products/3775-NUP2105LT1G"
        res = parse_vendor_links(url, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_empty is False
        assert res.is_multi is False
        assert res.count == 1
        assert "vendor_lion" in res.links
        entry = res.get_single_entry()
        assert entry.vendor_id == "vendor_lion"
        assert entry.vendor_label == "LION"
        assert entry.url == url
        assert entry.display_name == "Lion Electronic"

    def test_legacy_plain_javan_url(self, mock_registry):
        url = "https://www.javanelec.com/shop/product/55407/toshiba-corporation/t2n7002bk"
        res = parse_vendor_links(url, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_multi is False
        assert res.count == 1
        assert "vendor_javan" in res.links
        entry = res.get_single_entry()
        assert entry.vendor_id == "vendor_javan"
        assert entry.vendor_label == "JAVAN"
        assert entry.url == url
        assert entry.display_name == "Javan Electronic"

    def test_new_format_single_lion(self, mock_registry):
        raw = "LION=https://lionelectronic.ir/products/3775-NUP2105LT1G"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_multi is False
        assert res.count == 1
        assert "vendor_lion" in res.links
        assert res.get_url("vendor_lion") == "https://lionelectronic.ir/products/3775-NUP2105LT1G"

    def test_new_format_single_javan(self, mock_registry):
        raw = "JAVAN=https://www.javanelec.com/shop/product/55407/toshiba"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_multi is False
        assert res.count == 1
        assert "vendor_javan" in res.links
        assert res.get_url("vendor_javan") == "https://www.javanelec.com/shop/product/55407/toshiba"

    def test_both_vendor_links(self, mock_registry):
        raw = (
            "LION=https://lionelectronic.ir/products/3775-NUP2105LT1G || "
            "JAVAN=https://www.javanelec.com/shop/product/55407/toshiba-corporation/t2n7002bk"
        )
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_multi is True
        assert res.count == 2
        assert res.vendor_ids == ["vendor_javan", "vendor_lion"]
        assert res.get_url("vendor_lion") == "https://lionelectronic.ir/products/3775-NUP2105LT1G"
        assert res.get_url("vendor_javan") == "https://www.javanelec.com/shop/product/55407/toshiba-corporation/t2n7002bk"

    def test_reversed_token_order(self, mock_registry):
        raw1 = "LION=https://lionelectronic.ir/p/1 || JAVAN=https://www.javanelec.com/p/2"
        raw2 = "JAVAN=https://www.javanelec.com/p/2 || LION=https://lionelectronic.ir/p/1"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res1.as_dict() == res2.as_dict()
        assert res2.count == 2
        assert res2.is_multi is True

    def test_mixed_case_vendor_labels(self, mock_registry):
        raw = "lion=https://lionelectronic.ir/p/1 || Javan=https://www.javanelec.com/p/2"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is True
        assert res.count == 2
        assert "vendor_lion" in res.links
        assert "vendor_javan" in res.links

    def test_surrounding_token_whitespace(self, mock_registry):
        raw = "   LION  =   https://lionelectronic.ir/p/1    ||    JAVAN   =   https://www.javanelec.com/p/2   "
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is True
        assert res.get_url("vendor_lion") == "https://lionelectronic.ir/p/1"
        assert res.get_url("vendor_javan") == "https://www.javanelec.com/p/2"

    def test_empty_field(self, mock_registry):
        for empty_val in [None, "", "   ", "\t\n"]:
            res = parse_vendor_links(empty_val, registry=mock_registry)
            assert res.is_empty is True
            assert res.is_valid is True
            assert res.count == 0
            assert res.links == {}

    def test_empty_url_after_equals(self, mock_registry):
        raw1 = "LION="
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        assert res1.is_valid is False
        assert "Empty URL" in str(res1.error_message)

        raw2 = "LION=https://lionelectronic.ir/p/1 || JAVAN="
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.is_valid is False
        assert "Empty URL" in str(res2.error_message)

    def test_missing_equals_sign(self, mock_registry):
        raw1 = "LION https://lionelectronic.ir/p/1 || JAVAN=https://www.javanelec.com/p/2"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        assert res1.is_valid is False
        assert "Missing '='" in str(res1.error_message)

        raw2 = "LION"
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.is_valid is False

    def test_missing_or_malformed_separator(self, mock_registry):
        # Single pipe instead of double pipe
        raw1 = "LION=https://lionelectronic.ir/p/1 | JAVAN=https://www.javanelec.com/p/2"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        assert res1.is_valid is False
        assert "single '|'" in str(res1.error_message)

        # Concatenated without delimiter
        raw2 = "LION=https://lionelectronic.ir/p/1 JAVAN=https://www.javanelec.com/p/2"
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.is_valid is False

        # Trailing delimiter with empty token
        raw3 = "LION=https://lionelectronic.ir/p/1 ||"
        res3 = parse_vendor_links(raw3, registry=mock_registry)
        assert res3.is_valid is False

    def test_duplicate_lion_key(self, mock_registry):
        raw = "LION=https://lionelectronic.ir/p/1 || LION=https://lionelectronic.ir/p/2"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is False
        assert "Duplicate vendor key 'LION'" in str(res.error_message)

    def test_duplicate_javan_key(self, mock_registry):
        raw = "JAVAN=https://www.javanelec.com/p/1 || JAVAN=https://www.javanelec.com/p/2"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is False
        assert "Duplicate vendor key 'JAVAN'" in str(res.error_message)

    def test_unsupported_vendor_key(self, mock_registry):
        raw = "UNKNOWN=https://some-store.com/product/123"
        res = parse_vendor_links(raw, registry=mock_registry)
        assert res.is_valid is False
        assert "Unsupported vendor key 'UNKNOWN'" in str(res.error_message)

    def test_unsupported_or_malformed_url(self, mock_registry):
        # Not a URL
        raw1 = "LION=not_a_valid_url"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        assert res1.is_valid is False
        assert "Invalid URL" in str(res1.error_message)

        # Unsupported protocol (ftp)
        raw2 = "LION=ftp://lionelectronic.ir/p/1"
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.is_valid is False

    def test_vendor_label_vs_url_host_mismatch(self, mock_registry):
        # LION label paired with Javan URL
        raw1 = "LION=https://www.javanelec.com/shop/product/55407"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        assert res1.is_valid is False
        assert "contradicts URL host" in str(res1.error_message)

        # JAVAN label paired with Lion URL
        raw2 = "JAVAN=https://lionelectronic.ir/products/3775"
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.is_valid is False
        assert "contradicts URL host" in str(res2.error_message)

    def test_unknown_legacy_host_behavior(self, mock_registry):
        # Legacy plain URL from unknown domain
        url = "https://unregistered-distributor.com/p/999"
        res = parse_vendor_links(url, registry=mock_registry)
        assert res.is_valid is True
        assert res.is_multi is False
        assert res.count == 0
        assert res.links == {}

    def test_no_accidental_selection_by_token_position(self, mock_registry):
        raw1 = "LION=https://lionelectronic.ir/p/1 || JAVAN=https://www.javanelec.com/p/2"
        res1 = parse_vendor_links(raw1, registry=mock_registry)
        # Exactly two links, no single entry auto-selected
        assert res1.get_single_entry() is None
        assert res1.count == 2

        raw2 = "JAVAN=https://www.javanelec.com/p/2 || LION=https://lionelectronic.ir/p/1"
        res2 = parse_vendor_links(raw2, registry=mock_registry)
        assert res2.get_single_entry() is None
        assert res2.count == 2


# =============================================================================
# 9.2 SINGLE-LINK BEHAVIOR TESTS
# =============================================================================

class TestSingleLinkBehavior:
    """Verifies that items with exactly 1 valid URL bypass selection dialogs completely."""

    def test_legacy_single_url_bypasses_dialog(self, qapp, mock_registry):
        shortage = {
            "part_name": "NE555P",
            "part_number": "NE555P",
            "needed_qty": 10,
            "link": "https://lionelectronic.ir/products/2070-NE555P",
        }
        dlg = OrderPreviewDialog(all_shortages=[shortage], registry=mock_registry)

        # Exactly 1 orderable item in lion_items, 0 multi-vendor items
        assert len(dlg.orderable_items) == 1
        assert len(dlg.multi_vendor_items) == 0
        assert len(dlg.lion_items) == 1

        # Double clicking should NOT trigger VendorSelectionDialog
        with patch.object(VendorSelectionDialog, "exec") as mock_dlg_exec:
            with patch("webbrowser.open") as mock_browser:
                table_item = dlg.table.item(0, 0)
                dlg._on_mode_a_item_double_clicked(table_item)
                mock_dlg_exec.assert_not_called()

    def test_single_labeled_url_bypasses_dialog(self, qapp, mock_registry):
        shortage = {
            "part_name": "T2N7002BK",
            "part_number": "T2N7002BK",
            "needed_qty": 5,
            "link": "JAVAN=https://www.javanelec.com/shop/product/55407/toshiba",
        }
        dlg = OrderPreviewDialog(all_shortages=[shortage], registry=mock_registry)

        assert len(dlg.orderable_items) == 1
        assert len(dlg.multi_vendor_items) == 0
        assert len(dlg.other_vendor_items) == 1

        # Verify that _execute_mode_a_order does NOT pop up VendorSelectionDialog
        with patch.object(VendorSelectionDialog, "exec") as mock_dlg_exec:
            with patch.object(dlg, "worker", create=True):
                # Mock worker thread to prevent actual thread launch
                with patch("ui.dialogs.order_preview_dialog.OrderWorkerThread") as mock_worker_cls:
                    mock_worker_inst = MagicMock()
                    mock_worker_cls.return_value = mock_worker_inst
                    dlg._execute_mode_a_order()
                    mock_dlg_exec.assert_not_called()
                    mock_worker_cls.assert_called_once()

    def test_single_link_item_to_request_direct(self, mock_registry):
        item = {
            "part_number": "NUP2105LT1G",
            "needed_qty": 20,
            "link": "LION=https://lionelectronic.ir/products/3775-NUP2105LT1G",
        }
        req = ProcurementBridge.item_to_request(item, registry=mock_registry)
        assert req.part_number == "NUP2105LT1G"
        assert req.required_quantity == 20
        assert req.explicit_vendor_id == "vendor_lion"
        assert req.explicit_vendor_url == "https://lionelectronic.ir/products/3775-NUP2105LT1G"


# =============================================================================
# 9.3 MULTI-LINK SELECTION TESTS
# =============================================================================

class TestMultiLinkSelection:
    """Verifies vendor selection modal prompt, meaningful names, cancel safety, and Case D."""

    def test_multi_link_triggers_selection_dialog(self, qapp, mock_registry):
        shortage = {
            "part_name": "NUP2105LT1G",
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775-NUP2105LT1G || "
                "JAVAN=https://www.javanelec.com/shop/product/55407/toshiba"
            ),
        }
        dlg = OrderPreviewDialog(all_shortages=[shortage], registry=mock_registry)

        assert len(dlg.multi_vendor_items) == 1
        assert len(dlg.orderable_items) == 1

        def fake_exec(*args, **kwargs):
            shortage["selected_vendor_id"] = "vendor_lion"
            shortage["selected_url"] = "https://lionelectronic.ir/products/3775-NUP2105LT1G"
            return QDialog.DialogCode.Accepted

        with patch.object(VendorSelectionDialog, "exec", side_effect=fake_exec) as mock_exec:
            with patch("ui.dialogs.order_preview_dialog.OrderWorkerThread") as mock_worker_cls:
                mock_worker_inst = MagicMock()
                mock_worker_cls.return_value = mock_worker_inst

                dlg._execute_mode_a_order()
                assert mock_exec.called is True
                assert shortage.get("selected_vendor_id") == "vendor_lion"

    def test_dialog_displays_meaningful_vendor_names_not_raw_url(self, qapp, mock_registry):
        item = {
            "part_name": "NUP2105LT1G",
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "vendor_links": {
                "vendor_lion": "https://lionelectronic.ir/products/3775",
                "vendor_javan": "https://www.javanelec.com/shop/product/55407",
            },
        }
        dlg = VendorSelectionDialog([item], registry=mock_registry)
        assert len(dlg.combo_boxes) == 1
        _, combo = dlg.combo_boxes[0]

        items_text = [combo.itemText(i) for i in range(combo.count())]
        assert "Lion Electronic" in items_text
        assert "Javan Electronic" in items_text
        # Ensure raw combined URLs or raw URLs are never used as display labels
        for txt in items_text:
            assert "https://" not in txt
            assert "||" not in txt

    def test_dialog_cancel_aborts_without_dispatch(self, qapp, mock_registry):
        shortage = {
            "part_name": "NUP2105LT1G",
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775 || "
                "JAVAN=https://www.javanelec.com/shop/product/55407"
            ),
        }
        dlg = OrderPreviewDialog(all_shortages=[shortage], registry=mock_registry)

        with patch.object(VendorSelectionDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            with patch("ui.dialogs.order_preview_dialog.OrderWorkerThread") as mock_worker_cls:
                dlg._execute_mode_a_order()
                # Worker should never be started on cancellation!
                mock_worker_cls.assert_not_called()
                assert dlg.worker is None

    def test_selecting_lion_passes_only_lion_url(self, mock_registry):
        item = {
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775 || "
                "JAVAN=https://www.javanelec.com/shop/product/55407"
            ),
            "selected_vendor_id": "vendor_lion",
        }
        req = ProcurementBridge.item_to_request(item, registry=mock_registry)
        assert req.explicit_vendor_id == "vendor_lion"
        assert req.explicit_vendor_url == "https://lionelectronic.ir/products/3775"
        assert "javanelec" not in req.explicit_vendor_url

    def test_selecting_javan_passes_only_javan_url(self, mock_registry):
        item = {
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775 || "
                "JAVAN=https://www.javanelec.com/shop/product/55407"
            ),
            "selected_vendor_id": "vendor_javan",
        }
        req = ProcurementBridge.item_to_request(item, registry=mock_registry)
        assert req.explicit_vendor_id == "vendor_javan"
        assert req.explicit_vendor_url == "https://www.javanelec.com/shop/product/55407"
        assert "lionelectronic" not in req.explicit_vendor_url

    def test_unselected_multi_link_item_to_request_fails_closed(self, mock_registry):
        # When item has multiple links but no selection was made, item_to_request must raise ValueError
        item = {
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775 || "
                "JAVAN=https://www.javanelec.com/shop/product/55407"
            ),
        }
        with pytest.raises(ValueError, match="multiple vendor links"):
            ProcurementBridge.item_to_request(item, registry=mock_registry)

    def test_case_d_selected_vendor_not_in_mapping_fails_closed(self, mock_registry):
        # Component has LION and JAVAN, but selection is retained as ROBOEQ
        item = {
            "part_number": "NUP2105LT1G",
            "needed_qty": 10,
            "link": (
                "LION=https://lionelectronic.ir/products/3775 || "
                "JAVAN=https://www.javanelec.com/shop/product/55407"
            ),
            "selected_vendor_id": "vendor_roboeq",
        }
        with pytest.raises(ValueError, match="Selected vendor 'vendor_roboeq' has no valid URL"):
            ProcurementBridge.item_to_request(item, registry=mock_registry)


# =============================================================================
# 9.4 ADAPTER DISPATCH AND REGRESSION TESTS
# =============================================================================

class TestAdapterDispatchAndRegression:
    """Verifies atomic adapter resolution, combined string isolation, and Excel loading."""

    def test_atomic_adapter_resolution_for_selected_url(self, mock_registry):
        lion_url = "https://lionelectronic.ir/products/3775-NUP2105LT1G"
        adapter, reg_meta = mock_registry.resolve_adapter_for_url(lion_url, enabled_only=True)
        assert adapter is not None
        assert isinstance(adapter, MockLionAdapter)
        assert reg_meta.vendor_id == "vendor_lion"

        javan_url = "https://www.javanelec.com/shop/product/55407"
        adapter_j, reg_meta_j = mock_registry.resolve_adapter_for_url(javan_url, enabled_only=True)
        assert adapter_j is not None
        assert isinstance(adapter_j, MockJavanAdapter)
        assert reg_meta_j.vendor_id == "vendor_javan"

    def test_combined_string_cannot_resolve_as_storefront_url(self, mock_registry):
        combined = "LION=https://lionelectronic.ir/p/1 || JAVAN=https://www.javanelec.com/p/2"
        adapter, reg_meta = mock_registry.resolve_adapter_for_url(combined, enabled_only=True)
        assert adapter is None
        assert reg_meta is None

    def test_excel_loader_with_multi_vendor_rows(self, tmp_path, mock_registry):
        import openpyxl
        file_path = str(tmp_path / "MultiVendorInventory.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventory"

        headers = [
            "ECODE", "PART NAME", "DISCRIPTION", "Quantity in Stock",
            "FOOTPRINT", "PART NUMBER", "LINK", "Position", "Unit Per length",
            "Min Stock", "Target Stock"
        ]
        rows = [
            # 1. Multi-vendor item
            [None, "NUP2105LT1G", "CAN Bus ESD Protection", 2, "SOT-23", "NUP2105LT1G",
             "LION=https://lionelectronic.ir/products/3775 || JAVAN=https://www.javanelec.com/shop/product/55407",
             "IC-01", None, 10, 50],
            # 2. Legacy single Lion item
            [None, "NE555P", "Precision Timer", 5, "DIP-8", "NE555P",
             "https://lionelectronic.ir/products/2070-NE555P",
             "IC-02", None, 20, 50],
            # 3. Single labeled Javan item
            [None, "T2N7002BK", "N-CH MOSFET", 1, "SOT-23", "T2N7002BK",
             "JAVAN=https://www.javanelec.com/shop/product/55407",
             "TR-01", None, 10, 30],
            # 4. Blank link item
            [None, "ATmega328P", "AVR MCU", 2, "DIP-28", "ATmega328P",
             None,
             "MCU-01", None, 10, 20],
        ]

        ws.append(headers)
        for r in rows:
            ws.append(r)
        wb.save(file_path)
        wb.close()

        loader = ExcelDataLoader()
        ok, msg = loader.load_file(file_path)
        assert ok is True

        shortages = loader.get_shortage_items(registry=mock_registry)
        assert len(shortages) == 4

        # Multi-vendor item checks
        nup = next(s for s in shortages if s["part_name"] == "NUP2105LT1G")
        assert nup["is_multi_vendor"] is True
        assert nup["is_orderable"] is True
        assert nup["link_type"] == "MULTI"
        assert len(nup["vendor_links"]) == 2
        assert "vendor_lion" in nup["vendor_links"]
        assert "vendor_javan" in nup["vendor_links"]

        # Legacy single link checks
        ne555 = next(s for s in shortages if s["part_name"] == "NE555P")
        assert ne555["is_multi_vendor"] is False
        assert ne555["is_orderable"] is True
        assert ne555["link_type"] == "LION"
        assert ne555["vendor_id"] == "vendor_lion"
        assert ne555["link"] == "https://lionelectronic.ir/products/2070-NE555P"

        # Single labeled link checks
        mos = next(s for s in shortages if s["part_name"] == "T2N7002BK")
        assert mos["is_multi_vendor"] is False
        assert mos["is_orderable"] is True
        assert mos["link_type"] == "JAVAN"
        assert mos["vendor_id"] == "vendor_javan"
        assert mos["link"] == "https://www.javanelec.com/shop/product/55407"

        # Blank link checks
        mcu = next(s for s in shortages if s["part_name"] == "ATmega328P")
        assert mcu["is_multi_vendor"] is False
        assert mcu["is_orderable"] is False
        assert mcu["link_type"] == "NONE"

    def test_direct_bom_mode_remains_distinct_from_mode_a(self, mock_registry):
        # Mode B (DIRECT_BOM) operates on part_number without requiring vendor links
        item_mode_b = {
            "mode": ProcurementMode.DIRECT_BOM,
            "part_number": "STM32F401RET6",
            "needed_qty": 5,
            "link": "",
        }
        is_ord, v_id = ProcurementBridge.is_item_orderable(item_mode_b, mock_registry)
        assert is_ord is True
        assert v_id is None

        # Mode A (DATABASE_AWARE) strictly requires vendor link or multi-links
        item_mode_a_blank = {
            "mode": ProcurementMode.DATABASE_AWARE,
            "part_number": "STM32F401RET6",
            "needed_qty": 5,
            "link": "",
        }
        is_ord_a, v_id_a = ProcurementBridge.is_item_orderable(item_mode_a_blank, mock_registry)
        assert is_ord_a is False
        assert v_id_a is None
