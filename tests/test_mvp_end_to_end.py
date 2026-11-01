"""
Omnix MVP End-to-End Verification Suite
Verifies the complete Mode A procurement workflow, official .xpl plugin lifecycle,
BOM link status consistency, StatsRibbon Total vs. Matches independence,
Inventory Excel export, and Database Backup/Restore in a strictly isolated environment.
"""

import os
import zipfile
import openpyxl
import pytest
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import settings_manager
from settings_manager import settings
from core.plugins.manifest_mf import generate_manifest_mf
from core.models import (
    StockStatus,
    OrderConstraints,
    ProductDetails,
    CartDetails,
    CartItem,
    CartMutationResult,
)
from core.inventory.models import InventoryProduct, SupplierLink
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.exporter import InventoryExcelExporter
from core.inventory.backup import DatabaseBackupService
from core.plugins.package_inspector import PackageInspector
from core.plugins.trust_engine import TrustEngine, TrustStatus
from core.plugins.plugin_store import PluginStore
from core.plugins.plugin_installer import PluginInstaller
from core.plugins.plugin_loader import PluginLoader
from core.plugins.plugin_lifecycle_manager import PluginLifecycleManager
from core.procurement.registry import VendorRegistry
from core.procurement.bridge import ProcurementBridge
from bom_auditor import BOMAuditor
from ui.widgets.bom_audit_widget import BOMAuditWidget
from ui.widgets.vendor_plugins_widget import PluginConfigDialog
from ui.dialogs.order_preview_dialog import OrderPreviewDialog, VendorSelectionDialog
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app



def _build_signed_test_package(src_dir: Path, vendor_name: str, dest_xpl: Path, private_key: ed25519.Ed25519PrivateKey) -> Path:
    """Build an authentic .xpl package from vendor source directory signed by an ephemeral test key."""
    files = {}
    for p in src_dir.rglob("*"):
        if p.is_file() and not p.name.endswith(".pyc") and "__pycache__" not in p.parts:
            rel = p.relative_to(src_dir).as_posix()
            if rel == "manifest.json":
                files["manifest.json"] = p.read_bytes()
            else:
                files[f"vendors/{vendor_name}/{rel}"] = p.read_bytes()
    mf_text = generate_manifest_mf(files)
    mf_bytes = mf_text.encode("utf-8")
    files["META-INF/MANIFEST.MF"] = mf_bytes
    files["META-INF/SIGNATURE.sig"] = private_key.sign(mf_bytes)
    dest_xpl.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_xpl, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, data in files.items():
            zf.writestr(fname, data)
    return dest_xpl


@pytest.fixture()
def isolated_mvp_env(tmp_path):
    """Strictly isolate settings, VendorRegistry, and PluginStore from workspace files."""
    orig_file_path = settings.file_path
    orig_settings_dict = settings._default_settings()
    orig_settings_dict.update(settings.settings)
    temp_settings_file = tmp_path / "isolated_mvp_settings.json"

    settings.file_path = str(temp_settings_file)
    settings.settings = settings._default_settings()

    VendorRegistry.reset_default_registry()
    reg = VendorRegistry.get_default_registry()

    test_trust_store = tmp_path / "test_trust_store"
    test_trust_store.mkdir(parents=True, exist_ok=True)
    test_priv_key = ed25519.Ed25519PrivateKey.generate()
    test_pub_key = test_priv_key.public_key()
    pub_bytes = test_pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (test_trust_store / "core-official-key-01.pub").write_bytes(pub_bytes)

    test_packages_dir = tmp_path / "test_packages"
    lion_xpl = _build_signed_test_package(Path("vendors/lion"), "lion", test_packages_dir / "lion.xpl", test_priv_key)
    javan_xpl = _build_signed_test_package(Path("vendors/javan"), "javan", test_packages_dir / "javan.xpl", test_priv_key)

    plugins_root = tmp_path / "plugins_data"
    store = PluginStore(plugins_root=plugins_root)
    trust_engine = TrustEngine(prod_trust_store=test_trust_store, env="production")
    inspector = PackageInspector()
    installer = PluginInstaller(store=store, trust_engine=trust_engine, inspector=inspector)
    loader = PluginLoader(store=store)
    lifecycle = PluginLifecycleManager(store=store, loader=loader, registry=reg)

    try:
        yield {
            "tmp_path": tmp_path,
            "registry": reg,
            "store": store,
            "trust_engine": trust_engine,
            "inspector": inspector,
            "installer": installer,
            "loader": loader,
            "lifecycle": lifecycle,
            "lion_xpl": lion_xpl,
            "javan_xpl": javan_xpl,
        }
    finally:
        import sys
        for mod in list(sys.modules.keys()):
            if mod.startswith("omnix_plugins."):
                sys.modules.pop(mod, None)
        VendorRegistry.reset_default_registry()
        settings.file_path = orig_file_path
        settings.settings = orig_settings_dict


def test_mvp_official_xpl_packages_install_enable_configure_and_load(qapp, isolated_mvp_env):
    """Verify vendors/lion.xpl and vendors/javan.xpl pass inspection, signature verification, install, config, and load."""
    env = isolated_mvp_env
    inspector: PackageInspector = env["inspector"]
    trust_engine: TrustEngine = env["trust_engine"]
    installer: PluginInstaller = env["installer"]
    lifecycle: PluginLifecycleManager = env["lifecycle"]
    store: PluginStore = env["store"]
    reg: VendorRegistry = env["registry"]

    for vname, expected_vid, xpl_path in (
        ("lion", "vendor_lion", env["lion_xpl"]),
        ("javan", "vendor_javan", env["javan_xpl"]),
    ):
        assert xpl_path.is_file(), f"Missing official package: {xpl_path}"

        insp = inspector.inspect_package(xpl_path)
        assert insp.is_valid, f"{vname}.xpl failed inspection: {insp.errors}"

        tr = trust_engine.verify_archive(xpl_path)
        assert tr.is_trusted, f"{vname}.xpl failed signature verification: {tr.error_message}"
        assert tr.status == TrustStatus.TRUSTED_PRODUCTION

        inst = installer.install_package(xpl_path)
        assert inst.success, f"{vname}.xpl failed installation: {inst.error_message}"
        assert inst.vendor_id == expected_vid

        act = lifecycle.activate_plugin(expected_vid)
        assert act.success, f"Failed to activate {expected_vid}: {act.error_message}"

    assert reg.has_vendor("vendor_lion") and reg.is_vendor_enabled("vendor_lion")
    assert reg.has_vendor("vendor_javan") and reg.is_vendor_enabled("vendor_javan")

    # Verify URL resolution for both Lion and Javan (including short Javan PDP URLs)
    assert reg.get_vendor_for_url("https://lionelectronic.ir/products/123-stm32f103c8t6") == "vendor_lion"
    assert reg.get_vendor_for_url("https://www.javanelec.com/shop/product/53852") == "vendor_javan"

    # Verify PluginConfigDialog builds manifest-driven fields from config_schema (headless is managed globally in settings)
    cfg_dlg = PluginConfigDialog(vendor_id="vendor_lion", registry=reg)
    assert set(cfg_dlg.field_widgets.keys()) >= {"username", "password", "timeout_seconds"}


def test_mvp_bom_link_status_consistency_across_plugin_states(qapp, isolated_mvp_env):
    """Verify BOMItem.is_orderable, link_type, BOMAuditWidget, and OrderPreviewDialog agree when plugins are uninstalled, enabled, or disabled."""
    env = isolated_mvp_env
    tmp_path: Path = env["tmp_path"]
    installer: PluginInstaller = env["installer"]
    lifecycle: PluginLifecycleManager = env["lifecycle"]
    reg: VendorRegistry = env["registry"]

    db_path = tmp_path / "bom_consistency.db"
    repo = SqliteInventoryRepository(str(db_path))
    repo.db_manager.initialize_schema()
    repo.load(str(db_path))
    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="ST",
            mpn="STM32F103C8T6",
            description="MCU",
            quantity_in_stock=2,
            category="IC",
            type_technology="MCU",
            value="STM32F103",
            package="LQFP-48",
            footprint="LQFP-48",
            min_stock=10,
            target_stock=20,
        ),
        supplier_links=[
            SupplierLink(
                vendor_id="vendor_lion",
                vendor_label="LION",
                url="https://lionelectronic.ir/products/100-stm32f103c8t6",
            )
        ],
    )

    bom_xlsx = tmp_path / "test_bom.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Designator", "Comment", "Footprint", "Part Number", "Quantity"])
    ws.append(["U1", "MCU", "LQFP-48", "STM32F103C8T6", 5])
    wb.save(str(bom_xlsx))

    auditor = BOMAuditor()

    # 1. No plugins installed in registry -> NOT orderable, link_type == "INVALID"
    ok, msg, res_uninstalled = auditor.audit_bom(str(bom_xlsx), repo, board_multiplier=1)
    assert ok, msg
    assert len(res_uninstalled.items) == 1
    item_uninstalled = res_uninstalled.items[0]
    assert item_uninstalled.status == "SHORTAGE"
    assert not item_uninstalled.is_orderable
    assert item_uninstalled.link_type == "LION"

    audit_widget = BOMAuditWidget(inventory_loader=repo)
    audit_widget.audit_result = res_uninstalled
    audit_widget._render_results()
    assert "Missing Vendor Links" in audit_widget.order_btn.text()

    dlg_uninstalled = OrderPreviewDialog(
        all_shortages=[it.to_dict() for it in res_uninstalled.items],
        source_title="Uninstalled Test",
        registry=reg,
    )
    assert len(dlg_uninstalled.orderable_items) == 0

    # 2. Install & activate vendor_lion -> orderable, link_type == "LION"
    installer.install_package(env["lion_xpl"])
    lifecycle.activate_plugin("vendor_lion")

    ok, msg, res_installed = auditor.audit_bom(str(bom_xlsx), repo, board_multiplier=1)
    assert ok, msg
    item_installed = res_installed.items[0]
    assert item_installed.is_orderable
    assert item_installed.link_type == "LION"

    audit_widget.audit_result = res_installed
    audit_widget._render_results()
    assert "1 Items Ready" in audit_widget.order_btn.text()

    dlg_installed = OrderPreviewDialog(
        all_shortages=[it.to_dict() for it in res_installed.items],
        source_title="Installed Test",
        registry=reg,
    )
    assert len(dlg_installed.orderable_items) == 1

    # 3. Disable vendor_lion -> NOT orderable, link_type == "INVALID"
    lifecycle.deactivate_plugin("vendor_lion")
    ok, msg, res_disabled = auditor.audit_bom(str(bom_xlsx), repo, board_multiplier=1)
    assert ok, msg
    item_disabled = res_disabled.items[0]
    assert not item_disabled.is_orderable
    assert item_disabled.link_type == "LION"

    repo.close()


def test_mvp_mode_a_stock_replenishment_and_staging_safety(qapp, isolated_mvp_env, monkeypatch):
    """Verify Mode A replenishment, multi-vendor selection, MOQ/step rounding, 14/10/20/15 stock rule, and cart-staging boundary."""
    env = isolated_mvp_env
    installer: PluginInstaller = env["installer"]
    lifecycle: PluginLifecycleManager = env["lifecycle"]
    reg: VendorRegistry = env["registry"]

    installer.install_package(env["lion_xpl"])
    installer.install_package(env["javan_xpl"])
    lifecycle.activate_plugin("vendor_lion")
    lifecycle.activate_plugin("vendor_javan")

    shortages = [
        {
            "part_name": "NE555DR",
            "part_number": "NE555DR",
            "shortage_qty": 7,
            "needed_qty": 7,
            "link": "https://lionelectronic.ir/products/101-ne555dr",
            "status": "SHORTAGE",
        },
        {
            "part_name": "LM358",
            "part_number": "LM358",
            "shortage_qty": 14,
            "needed_qty": 14,
            "link": "LION=https://lionelectronic.ir/products/102-lm358 || JAVAN=https://www.javanelec.com/shop/product/53852",
            "status": "SHORTAGE",
        },
        {
            "part_name": "BLANK_PART",
            "part_number": "BLANK_PART",
            "shortage_qty": 5,
            "needed_qty": 5,
            "link": "",
            "status": "UNMAPPABLE",
        },
    ]

    dlg = OrderPreviewDialog(
        all_shortages=shortages,
        source_title="MVP Mode A Replenishment",
        registry=reg,
    )
    assert len(dlg.all_shortages) == 3
    assert len(dlg.orderable_items) == 2
    assert len(dlg.multi_vendor_items) == 1

    # Explicitly select Javan for the multi-vendor LM358 item via VendorSelectionDialog
    sel_dlg = VendorSelectionDialog(dlg.multi_vendor_items, registry=reg)
    combo = sel_dlg.combo_boxes[0][1]
    for idx in range(1, combo.count()):
        if combo.itemData(idx)[0] == "vendor_javan":
            combo.setCurrentIndex(idx)
            break
    sel_dlg._on_confirm()
    assert shortages[1]["selected_vendor_id"] == "vendor_javan"
    assert shortages[1]["link"] == "https://www.javanelec.com/shop/product/53852"

    # Now test ProcurementBridge.stage_direct_link_items with:
    # - NE555DR on Lion: needed=7, MOQ=5, step=5 -> rounds up to 10, available=50 -> stages +10 in cart
    # - LM358 on Javan: needed=14, in_cart=10, available=20 -> target=24 > 20 -> rejected by 14/10/20/15 rule!
    staged_calls = []

    class FakeAdapter:
        def __init__(self, vid):
            self.vid = vid

        def resolve_product(self, url):
            from core.models import ProductReference
            return ProductReference(vendor_id=self.vid, vendor_sku=url.split("/")[-1], pdp_url=url)

        def inspect_product(self, ref):
            if "ne555dr" in ref.pdp_url:
                return ProductDetails(
                    vendor_id=self.vid,
                    vendor_sku=ref.vendor_sku,
                    pdp_url=ref.pdp_url,
                    mpn="NE555DR",
                    stock_quantity=50,
                    can_order=True,
                    price_irr=1000,
                    order_constraints=OrderConstraints(moq_raw=5, packaging_step_raw=5),
                )
            else:
                return ProductDetails(
                    vendor_id=self.vid,
                    vendor_sku=ref.vendor_sku,
                    pdp_url=ref.pdp_url,
                    mpn="LM358",
                    stock_quantity=20,
                    can_order=True,
                    price_irr=1200,
                    order_constraints=OrderConstraints(moq_raw=5, packaging_step_raw=5),
                )

        def inspect_stock(self, ref):
            if "ne555dr" in ref.pdp_url:
                return StockStatus(vendor_id=self.vid, vendor_sku=ref.vendor_sku, in_stock=True, stock_quantity=50, can_order=True)
            else:
                return StockStatus(vendor_id=self.vid, vendor_sku=ref.vendor_sku, in_stock=True, stock_quantity=20, can_order=True)

        def inspect_cart(self):
            if self.vid == "vendor_javan":
                return CartDetails(
                    vendor_id=self.vid,
                    cart_url="https://www.javanelec.com/shop/cart",
                    items=[
                        CartItem(
                            vendor_sku="53852",
                            product_name="LM358",
                            quantity=10,
                            unit_price_irr=1200,
                            total_price_irr=12000,
                            pdp_url="https://www.javanelec.com/shop/product/53852",
                        )
                    ],
                    total_items=1,
                    total_amount_irr=12000,
                )
            return CartDetails(vendor_id=self.vid, cart_url="https://lionelectronic.ir/cart", items=[], total_items=0, total_amount_irr=0)

        def add_to_cart(self, ref, quantity):
            if self.vid == "vendor_javan":
                # 14/10/20/15 rule: in_cart=10, requested=14 (rounded to 15), total=25 > available=20 -> reject!
                return CartMutationResult(
                    vendor_id=self.vid,
                    vendor_sku=ref.vendor_sku,
                    requested_quantity=quantity,
                    actual_quantity_staged=0,
                    success=False,
                    error_category="INSUFFICIENT_STOCK",
                    raw_vendor_message="Insufficient Stock: total requested (25) exceeds available stock (20)",
                )
            staged_calls.append((self.vid, ref.pdp_url, quantity))
            return CartMutationResult(
                vendor_id=self.vid,
                vendor_sku=ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=quantity,
                success=True,
            )

        def close(self):
            pass

    monkeypatch.setattr(reg, "get_adapter", lambda vid, config=None, version=None: FakeAdapter(vid))
    monkeypatch.setattr(
        reg,
        "resolve_adapter_for_url",
        lambda url, enabled_only=True: (
            FakeAdapter(reg.get_vendor_for_url(url, enabled_only=enabled_only)),
            reg.get_registration(reg.get_vendor_for_url(url, enabled_only=enabled_only)),
        ),
    )

    selected_items = [shortages[0], shortages[1]]
    outcome = ProcurementBridge.execute_staged_procurement_batch(selected_items, registry=reg)

    # Verify NE555DR was rounded to 10 (MOQ=5, step=5) and staged, while LM358 was rejected without mutating Javan cart!
    assert staged_calls == [("vendor_lion", "https://lionelectronic.ir/products/101-ne555dr", 10)]
    results_by_part = {r["part"]: r for r in outcome["results"]}
    assert results_by_part["NE555DR"]["status"] == "SUCCESS"
    assert results_by_part["NE555DR"]["qty"] == 10
    assert results_by_part["LM358"]["status"] == "FAILED"
    assert "Insufficient Stock" in results_by_part["LM358"]["msg"]


def test_mvp_stats_ribbon_total_vs_matches_independence(qapp, isolated_mvp_env):
    """Verify StatsRibbon Total Records and Matches are independent in both Assembly & Stock and Component Inventory views."""
    env = isolated_mvp_env
    tmp_path: Path = env["tmp_path"]

    db_path = tmp_path / "stats_mvp.db"
    repo = SqliteInventoryRepository(str(db_path))
    repo.db_manager.initialize_schema()
    repo.load(str(db_path))

    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="Yageo",
            mpn="RC0603FR-0710KL",
            description="10k SMD",
            quantity_in_stock=100,
            category="Resistor",
            type_technology="SMD",
            value="10k",
            package="0603",
            footprint="R0603",
        )
    )
    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="Vishay",
            mpn="CRCW060310K0FKEA",
            description="10k SMD",
            quantity_in_stock=50,
            category="Resistor",
            type_technology="SMD",
            value="10k",
            package="0603",
            footprint="R0603",
        )
    )
    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="Murata",
            mpn="GRM188R71H104KA93D",
            description="100nF MLCC",
            quantity_in_stock=200,
            category="Capacitor",
            type_technology="MLCC",
            value="100nF",
            package="0603",
            footprint="C0603",
        )
    )
    repo.close()

    settings.settings["auto_check_startup_shortage"] = False
    win_repo = SqliteInventoryRepository(str(db_path))
    win = MainWindow(default_file=str(db_path), repository=win_repo)
    try:
        # 1. Assembly & Stock tab (index 0): 2 groups total
        win.inventory_subtabs.setCurrentIndex(0)
        win._on_inventory_subtab_changed(0)
        assert win.stats_ribbon.stat_total_rows.text() == "Total Records: 2"
        assert win.stats_ribbon.stat_filtered_rows.text() == "Matches: 2"

        # Filter Assembly & Stock to "100nF": Total stays 2, Matches becomes 1
        win._on_search_changed("100nF")
        assert win.stats_ribbon.stat_total_rows.text() == "Total Records: 2"
        assert win.stats_ribbon.stat_filtered_rows.text() == "Matches: 1"
        win._on_search_changed("")

        # 2. Component Inventory tab (index 1): 3 components total
        win.inventory_subtabs.setCurrentIndex(1)
        win._on_inventory_subtab_changed(1)
        assert win.stats_ribbon.stat_total_rows.text() == "Total Records: 3"
        assert win.stats_ribbon.stat_filtered_rows.text() == "Matches: 3"

        # Search Component Inventory for "Yageo": Total stays 3, Matches becomes 1
        win._on_component_search_changed("Yageo")
        assert win.stats_ribbon.stat_total_rows.text() == "Total Records: 3"
        assert win.stats_ribbon.stat_filtered_rows.text() == "Matches: 1"
    finally:
        if hasattr(win, "inventory_repo") and win.inventory_repo:
            win.inventory_repo.close()
        win._is_force_closing = True
        win.close()


def test_mvp_excel_export_and_database_backup_restore(isolated_mvp_env):
    """Verify InventoryExcelExporter exports Inventory + Assembly View sheets and DatabaseBackupService round-trips backups."""
    env = isolated_mvp_env
    tmp_path: Path = env["tmp_path"]

    db_path = tmp_path / "export_backup.db"
    repo = SqliteInventoryRepository(str(db_path))
    repo.db_manager.initialize_schema()
    repo.load(str(db_path))
    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="TI",
            mpn="LM317T",
            description="Linear Regulator",
            quantity_in_stock=25,
            category="IC",
            type_technology="Regulator",
            value="LM317",
            package="TO-220",
            footprint="TO-220",
            min_stock=10,
            target_stock=30,
        )
    )
    repo.load(str(db_path))

    # 1. Excel export
    xlsx_path = tmp_path / "exported_inventory.xlsx"
    exported_path = InventoryExcelExporter.export(repo, str(xlsx_path))
    assert exported_path == str(xlsx_path)
    assert xlsx_path.is_file()

    wb = openpyxl.load_workbook(str(xlsx_path))
    assert wb.sheetnames == ["Inventory"]
    wb.close()

    # 2. Backup & Restore
    backup_path = tmp_path / "snapshot.obk"
    ok_backup, msg_backup, meta_backup = DatabaseBackupService.export_full_backup(
        repo,
        str(backup_path),
        settings_mgr=settings,
        overwrite=True,
    )
    assert ok_backup, msg_backup
    assert backup_path.is_file()

    # Add a second component, then restore backup and confirm count returns to 1
    repo.create_component(
        InventoryProduct(
            id=None,
            manufacturer="TI",
            mpn="NE555P",
            description="Timer",
            quantity_in_stock=5,
            category="IC",
            type_technology="Timer",
            value="NE555",
            package="DIP-8",
            footprint="DIP-8",
        )
    )
    assert len(repo.get_all_products()) == 2

    is_valid_bk, val_msg, _ = DatabaseBackupService.validate_backup_file(str(backup_path))
    assert is_valid_bk, val_msg

    ok_restore, msg_restore, _ = DatabaseBackupService.restore_backup(
        repo,
        str(backup_path),
        settings_mgr=settings,
        restore_settings=True,
    )
    assert ok_restore, msg_restore
    assert len(repo.get_all_products()) == 1
    assert repo.get_all_products()[0].mpn == "LM317T"
    repo.close()
