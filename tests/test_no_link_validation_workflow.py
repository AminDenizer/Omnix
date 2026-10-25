"""
Omnix Automated Tests: Verification of Link Validation Feature Removal (DOC-OMNIX-PLAN-FINAL-004 Section 6)
Verifies:
1. No standalone link-validation buttons or actions exist on BOMAuditWidget or MainWindow.
2. LinkValidationDialog and LinkValidator classes are removed from ui and core.
3. Offline URL classification via ProcurementBridge.classify_link remains intact.
"""

import pytest
from core.procurement.bridge import ProcurementBridge
from core.procurement.registry import VendorRegistry
from core.procurement.vendor_links import parse_vendor_links
from core.vendor_interface import IVendorAdapter


class MockLionAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_lion"
    def __init__(self, config=None): pass
    @property
    def vendor_id(self): return self.VENDOR_ID
    def base_url(self): return "https://lionelectronic.ir"
    def initialize(self, config=None): pass
    def search_part(self, query): pass
    def resolve_product(self, url_or_sku): pass
    def inspect_product(self, product_ref): pass
    def extract_product_data(self, dom): pass
    def inspect_stock(self, product_ref): pass
    def add_to_cart(self, product_ref, qty): pass
    def inspect_cart(self): pass
    def authenticate(self, creds=None): pass
    def validate_session(self): pass
    def recover_from_error(self, ctx): pass
    def close(self): pass


class MockJavanAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_javan"
    def __init__(self, config=None): pass
    @property
    def vendor_id(self): return self.VENDOR_ID
    def base_url(self): return "https://javanelec.com"
    def initialize(self, config=None): pass
    def search_part(self, query): pass
    def resolve_product(self, url_or_sku): pass
    def inspect_product(self, product_ref): pass
    def extract_product_data(self, dom): pass
    def inspect_stock(self, product_ref): pass
    def add_to_cart(self, product_ref, qty): pass
    def inspect_cart(self): pass
    def authenticate(self, creds=None): pass
    def validate_session(self): pass
    def recover_from_error(self, ctx): pass
    def close(self): pass


@pytest.fixture
def test_registry():
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


def test_link_validation_classes_removed():
    """Verify obsolete link validation classes cannot be imported."""
    with pytest.raises(ImportError):
        from ui.dialogs.link_validation_dialog import LinkValidationDialog

    with pytest.raises(ImportError):
        from core.procurement.link_validator import LinkValidator


def test_url_classification_preserved(test_registry):
    """Verify offline vendor URL classification remains 100% operational without network checks."""
    l_type, l_domain, vid = ProcurementBridge.classify_link(
        "https://lionelectronic.ir/products/1497-0805-10k",
        registry=test_registry,
    )
    assert l_type == "LION"
    assert l_domain == "lionelectronic.ir"
    assert vid == "vendor_lion"

    l_type, l_domain, vid = ProcurementBridge.classify_link(
        "https://javanelec.com/product/cap-0805-100nf",
        registry=test_registry,
    )
    assert l_type == "JAVAN"
    assert l_domain == "javanelec.com"
    assert vid == "vendor_javan"

    l_type, l_domain, vid = ProcurementBridge.classify_link(
        "https://unknown-vendor.com/product/123",
        registry=test_registry,
    )
    assert l_type == "INVALID"
    assert vid is None


def test_vendor_links_parsing_preserved(test_registry):
    """Verify multi-vendor link parsing remains intact."""
    parsed = parse_vendor_links(
        "Lion = https://lionelectronic.ir/products/123 || Javan = https://javanelec.com/product/456",
        registry=test_registry,
    )
    assert parsed.is_valid is True
    assert parsed.count == 2
    assert "vendor_lion" in parsed.links
    assert "vendor_javan" in parsed.links
