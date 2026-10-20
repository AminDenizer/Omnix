"""
Omnix Automated Tests for Mode A Deterministic Link Validation Service
Governing Document: Phase G & H Link Validation Specification
"""

import pytest
from unittest.mock import MagicMock

from core.procurement.link_validator import (
    LinkValidator,
    LinkValidationItem,
    LinkValidationStatus,
    LinkValidationResult,
)
from core.models import CanonicalComponentDraft
from core.procurement.registry import VendorRegistry


class DummyAdapter:
    def __init__(self, mpn="RC0603FR-0710KL", manufacturer="Yageo", package="0603"):
        self._mpn = mpn
        self._manufacturer = manufacturer
        self._package = package

    def extract_product_data(self, html):
        return CanonicalComponentDraft(
            vendor_id="vendor_lion",
            vendor_sku="123",
            mpn=self._mpn,
            manufacturer=self._manufacturer,
            package=self._package,
            description="Resistor",
            specs={},
        )


class TestLinkValidatorDeterministicRules:
    """Verifies deterministic matching and classification rules of LinkValidator."""

    def test_invalid_url_classification(self):
        validator = LinkValidator()
        res = validator.validate_item(LinkValidationItem(url=""))
        assert res.status == LinkValidationStatus.INVALID_URL

        res2 = validator.validate_item(LinkValidationItem(url="not-a-url"))
        assert res2.status == LinkValidationStatus.INVALID_URL

    def test_unsupported_vendor_classification(self):
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = False
        registry.list_vendors.return_value = []
        validator = LinkValidator(registry=registry)

        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Murata",
                mpn="GRM188",
                url="https://unknown-distributor-store.xyz/p/123",
            )
        )
        assert res.status == LinkValidationStatus.UNSUPPORTED_VENDOR

    def test_http_error_classification(self):
        adapter = DummyAdapter()
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = True
        registry.get_adapter.return_value = adapter

        def failing_fetcher(url, timeout):
            raise ConnectionError("Connection timed out")

        validator = LinkValidator(registry=registry, fetcher=failing_fetcher)
        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                url="https://lionelectronic.ir/p/123",
            )
        )
        assert res.status == LinkValidationStatus.HTTP_ERROR
        assert "Connection timed out" in res.message

    def test_http_status_non_200_classification(self):
        adapter = DummyAdapter()
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = True
        registry.get_adapter.return_value = adapter

        def status_404_fetcher(url, timeout):
            return 404, "<html>Page Not Found</html>"

        validator = LinkValidator(registry=registry, fetcher=status_404_fetcher)
        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                url="https://lionelectronic.ir/p/123",
            )
        )
        assert res.status == LinkValidationStatus.HTTP_ERROR
        assert res.status_code == 404

    def test_verified_match_classification(self):
        adapter = DummyAdapter(mpn="RC0603FR-0710KL", manufacturer="Yageo")
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = True
        registry.get_adapter.return_value = adapter

        def ok_fetcher(url, timeout):
            return 200, "<html>Specs</html>"

        validator = LinkValidator(registry=registry, fetcher=ok_fetcher)
        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                url="https://lionelectronic.ir/p/123",
            )
        )
        assert res.status == LinkValidationStatus.VERIFIED_MATCH
        assert res.is_verified is True
        assert res.extracted_mpn == "RC0603FR-0710KL"
        assert res.extracted_manufacturer == "Yageo"

    def test_identity_mismatch_classification(self):
        # Local record expects NE555P from TI, but remote product is LM358 from ST
        adapter = DummyAdapter(mpn="LM358N", manufacturer="STMicroelectronics")
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = True
        registry.get_adapter.return_value = adapter

        def ok_fetcher(url, timeout):
            return 200, "<html>Specs</html>"

        validator = LinkValidator(registry=registry, fetcher=ok_fetcher)
        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Texas Instruments",
                mpn="NE555P",
                url="https://lionelectronic.ir/p/999",
            )
        )
        assert res.status == LinkValidationStatus.IDENTITY_MISMATCH
        assert res.is_mismatch is True
        assert "LM358N" in res.message
        assert "NE555P" in res.message

    def test_not_verifiable_classification(self):
        # Adapter cannot extract MPN or Manufacturer from HTML
        adapter = DummyAdapter(mpn=None, manufacturer=None)
        registry = MagicMock(spec=VendorRegistry)
        registry.has_vendor.return_value = True
        registry.get_adapter.return_value = adapter

        def ok_fetcher(url, timeout):
            return 200, "<html>Blank page without technical specs</html>"

        validator = LinkValidator(registry=registry, fetcher=ok_fetcher)
        res = validator.validate_item(
            LinkValidationItem(
                manufacturer="Yageo",
                mpn="RC0603FR-0710KL",
                url="https://lionelectronic.ir/p/123",
            )
        )
        assert res.status == LinkValidationStatus.NOT_VERIFIABLE
