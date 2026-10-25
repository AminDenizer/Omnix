"""
Tests for OMNIX Mode A Stock-Policy Shortage Replenishment Workflow.
Governing GAP: Phase 3 Activation of Stock Policy Replenishment & Mode A Handoff.

Validates:
1. Below-minimum stock threshold detection (g.is_low_stock).
2. Replenishment quantity calculation (target_stock - current_stock).
3. Supplier product link mapping without guessing or substituting.
4. Safe unmappable component handling with exact reasons.
5. Mode A handoff to OrderPreviewDialog with dual report export lifecycle.
6. Zero database / inventory mutations during replenishment workflow.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.inventory.repository import SqliteInventoryRepository
from core.inventory.models import (
    StockPolicyGroup,
    InventoryProduct,
    SupplierLink,
    StockPolicyRecord,
    build_group_key,
)
from core.procurement.models import (
    SupplierOutcomeStatus,
    SupplierItemResult,
    OrderConstraints,
)
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter
from core.models import AdapterStatus, ProductReference, ProductDetails, StockStatus
from ui.dialogs.order_preview_dialog import OrderPreviewDialog


class MockLionStagingAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    BASE_URL = "https://lionelectronic.ir"

    def __init__(self, config=None):
        self._config = config
        self.dispatched_items = []

    @property
    def vendor_id(self) -> str:
        return self.VENDOR_ID

    @property
    def base_url(self) -> str:
        return self.BASE_URL

    def initialize(self, config=None):
        return AdapterStatus(vendor_id=self.VENDOR_ID, is_ready=True, is_authenticated=True)

    def search_part(self, query):
        return None

    def resolve_product(self, url_or_sku):
        return ProductReference(vendor_id=self.VENDOR_ID, vendor_sku="LION-SKU-1", pdp_url=url_or_sku)

    def inspect_product(self, product_ref):
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=100,
            can_order=True,
            price_irr=10000,
            mpn="CL10B104KB8NNNC",
            manufacturer="Samsung",
        )

    def extract_product_data(self, dom_context):
        return None

    def inspect_stock(self, product_ref):
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=100,
            in_stock=True,
            can_order=True,
        )

    def determine_order_constraints(self, product_ref):
        return OrderConstraints(
            moq_raw=1,
            packaging_step_raw=1,
        )

    def add_to_cart(self, product_ref, quantity: int) -> bool:
        self.dispatched_items.append((product_ref.pdp_url, quantity))
        return True

    def inspect_cart(self):
        return None

    def get_cart_url(self):
        return "https://lionelectronic.ir/cart"

    def authenticate(self, credentials=None):
        return None

    def validate_session(self):
        return None

    def recover_from_error(self, error_context):
        return None

    def close(self):
        pass


@pytest.fixture
def test_repo(tmp_path):
    """Creates a temporary SQLite repository with realistic stock policy groups."""
    db_path = str(tmp_path / "test_replenishment.db")
    repo = SqliteInventoryRepository(db_path)

    # 1. Add categories, types, manufacturers
    cat_cap = repo.add_category("Capacitor")
    repo.add_type(cat_cap, "Ceramic")
    repo.add_manufacturer("Samsung")

    cat_res = repo.add_category("Resistor")
    repo.add_type(cat_res, "Thick Film")
    repo.add_manufacturer("Yageo")

    cat_ic = repo.add_category("IC")
    repo.add_type(cat_ic, "Timer")
    repo.add_type(cat_ic, "OpAmp")
    repo.add_manufacturer("TI")

    # 2. Add Component with stored supplier link (Low Stock: stock=12, min=30, target=100)
    p1 = InventoryProduct(
        manufacturer="Samsung",
        mpn="CL10B104KB8NNNC",
        category="Capacitor",
        type_technology="Ceramic",
        package="0603",
        footprint="C0603",
        value="100nF",
        quantity_in_stock=12,
        min_stock=30,
        target_stock=100,
        description="0603 100nF 50V",
    )
    link1 = SupplierLink(
        vendor_id="vendor_lion",
        vendor_label="Lion",
        url="https://lionelectronic.ir/product/100nf-0603",
    )
    repo.create_component(p1, supplier_links=[link1])
    repo.set_policy(
        group_key=p1.group_key,
        min_stock=30,
        target_stock=100,
        description="Standard 100nF decoupling",
    )

    # 3. Add Component WITHOUT supplier links (Low Stock: stock=5, min=20, target=50)
    p2 = InventoryProduct(
        manufacturer="Yageo",
        mpn="RC0603JR-0710KL",
        category="Resistor",
        type_technology="Thick Film",
        package="0603",
        footprint="R0603",
        value="10k",
        quantity_in_stock=5,
        min_stock=20,
        target_stock=50,
        description="0603 10k 5%",
    )
    repo.create_component(p2, supplier_links=[])
    repo.set_policy(
        group_key=p2.group_key,
        min_stock=20,
        target_stock=50,
        description="Standard 10k pullup",
    )

    # 4. Add Component with Sufficient Stock (stock=500, min=100, target=500) -> NOT low stock
    p3 = InventoryProduct(
        manufacturer="TI",
        mpn="NE555DR",
        category="IC",
        type_technology="Timer",
        package="SOIC-8",
        footprint="SOIC-8",
        value="NE555",
        quantity_in_stock=500,
        min_stock=100,
        target_stock=500,
        description="Precision Timer",
    )
    repo.create_component(p3, supplier_links=[])
    repo.set_policy(
        group_key=p3.group_key,
        min_stock=100,
        target_stock=500,
        description="Timer IC",
    )

    # 5. Policy-only group with zero products (current=0, min=10, target=40)
    opamp_key = build_group_key("IC", "OpAmp", "LM358", "SOIC-8", "SOIC-8")
    repo.set_policy(
        group_key=opamp_key,
        min_stock=10,
        target_stock=40,
        description="Dual OpAmp",
    )

    return repo


@pytest.fixture
def mock_registry():
    reg = VendorRegistry()
    reg.register_adapter(
        vendor_id="vendor_lion",
        adapter_class=MockLionStagingAdapter,
        domains=["lionelectronic.ir"],
        display_name="Lion Electronic",
        enabled=True,
        activate=True,
    )
    return reg


class TestStockPolicyReplenishment:
    """Test suite covering the 5 key requirements of stock policy replenishment."""

    def test_below_minimum_detection(self, test_repo):
        """1. Detects low stock groups strictly when current_stock < min_stock."""
        groups = test_repo.get_all_groups()
        assert len(groups) == 4

        low_groups = [g for g in groups if g.is_low_stock]
        # Groups: 100nF (12 < 30), 10k (5 < 20), LM358 (0 < 10) are low
        # NE555 (500 >= 100) is NOT low
        assert len(low_groups) == 3

        low_keys = {g.value for g in low_groups}
        assert "100nF" in low_keys
        assert "10k" in low_keys
        assert "LM358" in low_keys
        assert "NE555" not in low_keys

    def test_target_stock_replenishment_calculation(self, test_repo):
        """2. Calculates replenishment quantity = target_stock - current_stock."""
        groups = {g.value: g for g in test_repo.get_all_groups()}

        g_cap = groups["100nF"]
        # current=12, target=100 -> shortage = 88
        assert g_cap.shortage_to_target == 88

        g_res = groups["10k"]
        # current=5, target=50 -> shortage = 45
        assert g_res.shortage_to_target == 45

        g_opamp = groups["LM358"]
        # current=0, target=40 -> shortage = 40
        assert g_opamp.shortage_to_target == 40

        g_ne555 = groups["NE555"]
        # current=500, target=500 -> shortage = 0
        assert g_ne555.shortage_to_target == 0

    def test_supplier_mapping_and_unmappable_handling(self, test_repo):
        """3 & 4. Maps stored supplier links; records exact unmappable reasons safely without guessing."""
        from ui.main_window import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = test_repo

        items = win._get_stock_policy_replenishment_items()
        assert len(items) == 3

        items_by_val = {it.get("part_name", ""): it for it in items}

        # Item 1: CL10B104KB8NNNC has stored Lion link
        cap_item = items_by_val.get("CL10B104KB8NNNC")
        assert cap_item is not None
        assert cap_item["needed_qty"] == 88
        assert cap_item["current_stock"] == 12
        assert "lionelectronic.ir" in cap_item["link"]
        assert cap_item["status"] == "SHORTAGE"
        assert cap_item["is_stock_policy"] is True

        # Item 2: RC0603JR-0710KL has NO supplier link -> marked UNMAPPABLE safely
        res_item = items_by_val.get("RC0603JR-0710KL")
        assert res_item is not None
        assert res_item["needed_qty"] == 45
        assert res_item["current_stock"] == 5
        assert res_item["link"] == ""
        assert res_item["status"] == "UNMAPPABLE"
        assert "No stored supplier link" in res_item["reason"]

        # Item 3: LM358 has no physical components -> marked UNMAPPABLE safely
        opamp_item = [it for it in items if "LM358" in it["part_name"]][0]
        assert opamp_item is not None
        assert opamp_item["needed_qty"] == 40
        assert opamp_item["current_stock"] == 0
        assert opamp_item["link"] == ""
        assert opamp_item["status"] == "UNMAPPABLE"
        assert "No physical products linked" in opamp_item["reason"]

    def test_mode_a_order_preview_handoff(self, qapp, test_repo, mock_registry):
        """5. Feeds mapped replenishment items into OrderPreviewDialog Mode A with proper selection and export lifecycle."""
        from ui.main_window import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = test_repo

        items = win._get_stock_policy_replenishment_items()
        assert len(items) == 3

        dlg = OrderPreviewDialog(
            all_shortages=items,
            source_title="Stock Policy Replenishment (3 Items)",
            registry=mock_registry,
        )

        # Mode A confirmation preview
        assert dlg.is_mode_b_preview is False
        assert len(dlg.all_shortages) == 3
        # Exactly 1 item has valid Lion link -> orderable
        assert len(dlg.orderable_items) == 1
        assert dlg.orderable_items[0]["part_name"] == "CL10B104KB8NNNC"
        # 2 items are invalid/blank links -> unorderable
        assert len(dlg.invalid_items) == 2

        # Orderable item is checked by default
        assert dlg.orderable_items[0]["_selected"] is True

        # Single direct Export Staging Results action exists (disabled until staging)
        assert hasattr(dlg, "export_btn")
        assert hasattr(dlg, "export_post_operation_btn")
        assert not hasattr(dlg, "export_pre_order_btn")
        assert not hasattr(dlg, "export_menu")
        assert dlg.export_post_operation_btn.isEnabled() is False
        assert "Export Staging Results (.xlsx)" in dlg.export_post_operation_btn.text()

    def test_zero_inventory_mutations(self, qapp, test_repo, mock_registry):
        """6. Strictly verifies zero inventory stock mutations occur during replenishment staging."""
        # Initial stock check
        p1_before = test_repo.get_component_by_identity("Samsung", "CL10B104KB8NNNC").quantity_in_stock
        p2_before = test_repo.get_component_by_identity("Yageo", "RC0603JR-0710KL").quantity_in_stock
        assert p1_before == 12
        assert p2_before == 5

        from ui.main_window import MainWindow
        win = MainWindow.__new__(MainWindow)
        win.inventory_repo = test_repo

        items = win._get_stock_policy_replenishment_items()
        dlg = OrderPreviewDialog(
            all_shortages=items,
            source_title="Stock Policy Replenishment (3 Items)",
            registry=mock_registry,
        )

        # Mock staging completion
        staging_data = {
            "success": True,
            "successful_count": 1,
            "failed_count": 0,
            "results": [
                {
                    "part": "CL10B104KB8NNNC",
                    "status": "SUCCESS",
                    "qty": 88,
                    "msg": "Added 88 pcs to Lion cart",
                    "vendor_id": "vendor_lion",
                    "status_code": SupplierOutcomeStatus.ADDED_TO_CART,
                }
            ],
        }
        with patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"), \
             patch("webbrowser.open"):
            dlg._on_mode_a_order_finished(staging_data)

        # Post-operation results export is now enabled
        assert dlg.export_post_operation_btn.isEnabled() is True

        # VERIFY ZERO STOCK MUTATIONS in the database!
        p1_after = test_repo.get_component_by_identity("Samsung", "CL10B104KB8NNNC").quantity_in_stock
        p2_after = test_repo.get_component_by_identity("Yageo", "RC0603JR-0710KL").quantity_in_stock
        assert p1_after == p1_before == 12
        assert p2_after == p2_before == 5


class TestSettingsNavigation:
    """Verifies Task 2: Settings navigation routes to proper page without popup dialog."""

    def test_open_settings_routing(self, qapp, test_repo):
        from ui.main_window import MainWindow

        with patch.object(MainWindow, "_check_startup_shortages"):
            win = MainWindow()
            try:
                # 1. Routing to vendor plugins
                win._open_settings("plugins")
                assert win.content_stack.currentWidget() == win.settings_page
                assert win.settings_tabs.currentIndex() == 1
                assert win.sidebar.active_page() == "settings"

                # 2. Routing to about
                win._open_settings("about")
                assert win.content_stack.currentWidget() == win.settings_page
                assert win.settings_tabs.currentIndex() == 2
                assert win.sidebar.active_page() == "settings"

                # 3. Routing to general settings
                win._open_settings("general")
                assert win.content_stack.currentWidget() == win.settings_page
                assert win.settings_tabs.currentIndex() == 0
                assert win.sidebar.active_page() == "settings"

                # 4. Default routing
                win._open_settings()
                assert win.content_stack.currentWidget() == win.settings_page
                assert win.settings_tabs.currentIndex() == 0
                assert win.sidebar.active_page() == "settings"
            finally:
                win._is_force_closing = True
                win.close()
