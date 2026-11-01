"""
Unit tests for Universal Procurement Bridge layer.

Verifies deterministic translation, URL classification, orderability detection,
and staged batch execution across multiple vendors without live browser dependencies.
"""

from typing import Any, Dict, List, Optional
import pytest

from core.models import (
    AdapterConfig,
    AdapterStatus,
    AuthCredentials,
    AuthResult,
    CanonicalComponentDraft,
    CartDetails,
    CartMutationResult,
    OrderConstraints,
    ProductDetails,
    ProductReference,
    RecoveryResult,
    SearchItem,
    SearchResultSet,
    SessionStatus,
    StockStatus,
)
from core.errors import OmnixVendorError
from core.procurement.bridge import ProcurementBridge
from core.procurement.models import ProcurementRequest
from core.procurement.registry import VendorRegistry
from core.vendor_interface import IVendorAdapter


class MockTestAdapter(IVendorAdapter):
    """Mock adapter for deterministic bridge execution testing."""

    VENDOR_ID = "vendor_mock"
    BASE_URL = "https://mockstore.com"
    staged_calls: List[Any] = []

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

    def search_part(self, query: str) -> SearchResultSet:
        return SearchResultSet(
            vendor_id=self.VENDOR_ID,
            query=query,
            total_matches=0,
            is_exact_match=False,
            items=[],
        )

    def resolve_product(self, url_or_sku: str) -> ProductReference:
        sku = url_or_sku.rstrip("/").split("/")[-1]
        return ProductReference(
            vendor_id=self.VENDOR_ID,
            vendor_sku=sku,
            pdp_url=url_or_sku if url_or_sku.startswith("http") else f"{self.BASE_URL}/p/{url_or_sku}",
        )

    def inspect_product(self, product_ref: ProductReference) -> ProductDetails:
        mpn_map = {
            "item-a": "PART-A",
            "item-b": "PART-B",
            "item-c": "PART-C",
            "fail-item": "PART-D",
        }
        mpn = mpn_map.get(product_ref.vendor_sku, product_ref.vendor_sku)
        return ProductDetails(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            pdp_url=product_ref.pdp_url,
            stock_quantity=100,
            can_order=True,
            price_irr=1000,
            mpn=mpn,
        )

    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft:
        return CanonicalComponentDraft(
            vendor_id=self.VENDOR_ID,
            vendor_sku="MOCK-SKU",
        )

    def inspect_stock(self, product_ref: ProductReference) -> StockStatus:
        return StockStatus(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            stock_quantity=100,
            in_stock=True,
            can_order=True,
        )

    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints:
        return OrderConstraints(packaging_step_raw=1, moq_raw=1)

    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult:
        MockTestAdapter.staged_calls.append((product_ref.pdp_url, quantity))
        if "fail" in product_ref.pdp_url:
            return CartMutationResult(
                vendor_id=self.VENDOR_ID,
                vendor_sku=product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=0,
                success=False,
                error_category="SIMULATED_FAILURE",
                raw_vendor_message="Simulated staging failure",
            )
        return CartMutationResult(
            vendor_id=self.VENDOR_ID,
            vendor_sku=product_ref.vendor_sku,
            requested_quantity=quantity,
            actual_quantity_staged=quantity,
            success=True,
            raw_vendor_message="Added to cart",
        )

    def inspect_cart(self) -> CartDetails:
        return CartDetails(vendor_id=self.VENDOR_ID, cart_url=f"{self.BASE_URL}/cart", total_items=0)

    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult:
        return AuthResult(vendor_id=self.VENDOR_ID, success=True, message="Auth OK")

    def validate_session(self) -> SessionStatus:
        return SessionStatus(vendor_id=self.VENDOR_ID, is_authenticated=True, session_valid=True)

    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult:
        return RecoveryResult(vendor_id=self.VENDOR_ID, recovered=True, action_taken="NOOP", message="OK")

    def translate_error(self, raw_error: Any) -> OmnixVendorError:
        return OmnixVendorError(str(raw_error))

    def close(self) -> None:
        pass


class TestProcurementBridgeClassification:
    """Tests URL classification and vendor resolution via ProcurementBridge."""

    @pytest.fixture(autouse=True)
    def register_test_adapters(self):
        reg = VendorRegistry.get_default_registry()
        reg.register_default_adapters()
        yield
        reg.clear()

    def test_classify_lion_link(self):
        link = "https://lionelectronic.ir/products/2070-NE555P"
        l_type, domain, vendor_id = ProcurementBridge.classify_link(link)
        assert l_type == "LION"
        assert domain == "lionelectronic.ir"
        assert vendor_id == "vendor_lion"

    def test_classify_javan_link(self):
        link = "https://javanelec.com/product/12345/resistor"
        l_type, domain, vendor_id = ProcurementBridge.classify_link(link)
        assert l_type == "JAVAN"
        assert domain == "javanelec.com"
        assert vendor_id == "vendor_javan"

    def test_classify_roboeq_link(self):
        link = "https://roboeq.ir/products/detail/0101001/"
        l_type, domain, vendor_id = ProcurementBridge.classify_link(link)
        assert l_type == "INVALID"
        assert domain == "roboeq.ir"
        assert vendor_id is None

    def test_classify_unsupported_link(self):
        link = "https://www.digikey.com/en/products/detail/1234"
        l_type, domain, vendor_id = ProcurementBridge.classify_link(link)
        assert l_type == "INVALID"
        assert domain == "digikey.com"
        assert vendor_id is None

    def test_classify_empty_link(self):
        l_type, domain, vendor_id = ProcurementBridge.classify_link("")
        assert l_type == "NONE"
        assert domain == ""
        assert vendor_id is None

        l_type, domain, vendor_id = ProcurementBridge.classify_link("   ")
        assert l_type == "NONE"
        assert domain == ""
        assert vendor_id is None

    def test_is_item_orderable(self):
        item_lion = {"link": "https://lionelectronic.ir/products/2070-NE555P"}
        ok, vendor = ProcurementBridge.is_item_orderable(item_lion)
        assert ok is True
        assert vendor == "vendor_lion"

        item_javan = {"link": "https://javanelec.com/product/123"}
        ok, vendor = ProcurementBridge.is_item_orderable(item_javan)
        assert ok is True
        assert vendor == "vendor_javan"

        item_robo = {"link": "https://roboeq.ir/products/detail/100/"}
        ok, vendor = ProcurementBridge.is_item_orderable(item_robo)
        assert ok is False
        assert vendor is None

        item_invalid = {"link": "https://unknownstore.ir/product/1"}
        ok, vendor = ProcurementBridge.is_item_orderable(item_invalid)
        assert ok is False
        assert vendor is None

        item_blank = {"link": ""}
        ok, vendor = ProcurementBridge.is_item_orderable(item_blank)
        assert ok is False
        assert vendor is None


class TestProcurementBridgeRequestTranslation:
    """Tests translation of legacy shortage dicts into immutable ProcurementRequests."""

    @pytest.fixture(autouse=True)
    def register_test_adapters(self):
        reg = VendorRegistry.get_default_registry()
        reg.register_default_adapters()
        yield
        reg.clear()

    def test_item_to_request_bom_shortage(self):
        item = {
            "row_idx": 4,
            "designator": "U1, U2",
            "part_name": "LM358N",
            "part_number": "LM358N",
            "comment": "Dual Op-Amp",
            "footprint": "DIP-8",
            "description": "General Purpose Op-Amp",
            "needed_qty": 10,
            "current_stock": 2,
            "link": "https://lionelectronic.ir/products/1932-LM358N",
        }

        req = ProcurementBridge.item_to_request(item)
        assert req.part_number == "LM358N"
        assert req.required_quantity == 10
        assert req.explicit_vendor_url == "https://lionelectronic.ir/products/1932-LM358N"
        assert req.explicit_vendor_id == "vendor_lion"
        assert req.source == "bom_row_4"
        assert req.description == "General Purpose Op-Amp"
        assert req.metadata["designator"] == "U1, U2"
        assert req.metadata["footprint"] == "DIP-8"

    def test_item_to_request_inventory_shortage(self):
        item = {
            "orig_row_idx": 15,
            "part_name": "NE555P",
            "part_number": "NE555P",
            "description": "Timer IC DIP-8",
            "current_stock": 5,
            "min_stock": 20,
            "target_stock": 50,
            "needed_qty": 45,
            "link": "https://javanelec.com/product/555",
        }

        req = ProcurementBridge.item_to_request(item)
        assert req.part_number == "NE555P"
        assert req.required_quantity == 45
        assert req.explicit_vendor_url == "https://javanelec.com/product/555"
        assert req.explicit_vendor_id == "vendor_javan"
        assert req.source == "inv_row_15"
        assert req.metadata["min_stock"] == 20
        assert req.metadata["target_stock"] == 50


class TestProcurementBridgeBatchExecution:
    """Tests batch execution logic with progress feedback and error containment."""

    def test_execute_empty_batch(self):
        res = ProcurementBridge.execute_staged_procurement_batch([])
        assert res["success"] is True
        assert res["successful_count"] == 0
        assert res["failed_count"] == 0
        assert len(res["results"]) == 0

    def test_execute_batch_with_custom_registry(self):
        MockTestAdapter.staged_calls.clear()
        reg = VendorRegistry()
        reg.register_adapter(
            vendor_id="vendor_mock",
            adapter_class=MockTestAdapter,
            display_name="Mock Store",
            domains=["mockstore.com"],
        )

        items = [
            {
                "orig_row_idx": 1,
                "part_name": "Part A",
                "part_number": "PART-A",
                "needed_qty": 5,
                "link": "https://mockstore.com/item-a",
            },
            {
                "orig_row_idx": 2,
                "part_name": "Part B",
                "part_number": "PART-B",
                "needed_qty": 12,
                "link": "https://mockstore.com/item-b",
            },
            {
                "orig_row_idx": 3,
                "part_name": "Part C",
                "part_number": "PART-C",
                "needed_qty": 8,
                "link": "https://unknownstore.com/item-c",  # Unsupported
            },
            {
                "orig_row_idx": 4,
                "part_name": "Part D",
                "part_number": "PART-D",
                "needed_qty": 3,
                "link": "https://mockstore.com/fail-item",  # Simulates staging failure
            },
        ]

        progress_events = []

        def callback(cur, tot, name, qty, msg):
            progress_events.append((cur, tot, name, qty, msg))

        res = ProcurementBridge.execute_staged_procurement_batch(
            items, progress_callback=callback, registry=reg
        )

        assert res["successful_count"] == 2
        assert res["failed_count"] == 2
        assert res["success"] is True

        # Check item outcomes
        assert items[0]["order_success"] is True
        assert items[0]["actual_ordered_qty"] == 5

        assert items[1]["order_success"] is True
        assert items[1]["actual_ordered_qty"] == 12

        assert items[2]["order_success"] is False
        assert items[2]["actual_ordered_qty"] == 0

        assert items[3]["order_success"] is False
        assert items[3]["actual_ordered_qty"] == 0

        # Check adapter received staged calls
        assert len(MockTestAdapter.staged_calls) == 3  # Part A, Part B, Part D
        assert ("https://mockstore.com/item-a", 5) in MockTestAdapter.staged_calls
        assert ("https://mockstore.com/item-b", 12) in MockTestAdapter.staged_calls

        # Progress callbacks were emitted
        assert len(progress_events) > 0
