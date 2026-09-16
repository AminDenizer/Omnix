"""
Deterministic Unit Tests for Omnix Universal Discovery Engine & Validator
Governing Specifications:
- docs/DISCOVERY/SITE_MAP_SCHEMA.md
- docs/DISCOVERY/DISCOVERY_METHODOLOGY.md
"""

import os
import json
import pytest
import subprocess
import sys

from core.discovery.models import (
    NodeType,
    RelationshipType,
    SelectorType,
    VerificationStatus,
    VendorTarget,
    EvidenceRecord,
    SiteMapNode,
    SiteMapEdge,
    SelectorDefinition,
    ExtractionDefinition,
    SiteMapGraph,
)
from core.discovery.evidence import EvidenceRecorder
from core.discovery.graph_builder import SiteMapGraphBuilder
from core.discovery.validator import SiteMapGraphValidator, ValidationReport


LION_GRAPH_PATH = os.path.join("docs", "VENDORS", "LION", "SITE_MAP_GRAPH.json")
LION_EVIDENCE_DIR = os.path.join("docs", "VENDORS", "LION", "evidence")

JAVAN_GRAPH_PATH = os.path.join("docs", "VENDORS", "JAVAN", "SITE_MAP_GRAPH.json")
JAVAN_EVIDENCE_DIR = os.path.join("docs", "VENDORS", "JAVAN", "evidence")

ROBOEQ_GRAPH_PATH = os.path.join("docs", "VENDORS", "ROBOEQ", "SITE_MAP_GRAPH.json")
ROBOEQ_EVIDENCE_DIR = os.path.join("docs", "VENDORS", "ROBOEQ", "evidence")


class TestUniversalDiscoveryModels:
    """Verify dataclass serialization, deserialization, and schema fidelity."""

    def test_vendor_target_model(self):
        target = VendorTarget(
            vendor_id="vendor_test",
            vendor_name="Test Electronics",
            base_url="https://test.example.com",
            auth_supported=True,
            description="Test distributor",
        )
        d = target.to_dict()
        assert d["vendor_id"] == "vendor_test"
        assert d["base_url"] == "https://test.example.com"

    def test_evidence_record_serialization(self, tmp_path):
        ev = EvidenceRecord(
            evidence_id="EV-TEST-SRCH-001",
            vendor_id="vendor_test",
            workflow="CATALOG_SEARCH",
            timestamp="2026-09-16T15:00:00Z",
            url="https://test.example.com/search?q=NE555",
            action="Submit search query in #search-box",
            expected_observation="Product card grid rendered",
            actual_observation="Found 40 matching items",
            selector="input#search-box",
            verification_status="VERIFIED",
        )
        ev_file = tmp_path / "EV-TEST-SRCH-001.json"
        ev.save(str(ev_file))

        loaded = EvidenceRecord.load(str(ev_file))
        assert loaded.evidence_id == "EV-TEST-SRCH-001"
        assert loaded.vendor_id == "vendor_test"
        assert loaded.actual_observation == "Found 40 matching items"
        assert loaded.verification_status == "VERIFIED"


class TestEvidenceRecorder:
    """Verify deterministic evidence recording and ID generation."""

    def test_deterministic_evidence_id_generation(self, tmp_path):
        recorder = EvidenceRecorder(vendor_id="vendor_javan", evidence_dir=str(tmp_path))
        id1 = recorder.generate_evidence_id("SRCH")
        assert id1 == "EV-JAVAN-SRCH-001"

        # Record first item
        recorder.record(
            workflow="SEARCH_DISCOVERY",
            action="Test search",
            url="https://example.com",
            expected_observation="Results",
            actual_observation="Found",
            workflow_code="SRCH",
        )

        id2 = recorder.generate_evidence_id("SRCH")
        assert id2 == "EV-JAVAN-SRCH-002"

    def test_list_and_get_evidence(self, tmp_path):
        recorder = EvidenceRecorder(vendor_id="vendor_moulec", evidence_dir=str(tmp_path))
        recorder.record("SEARCH", "Action 1", "https://example.com/1", "Exp 1", "Act 1", workflow_code="SRCH", index=1)
        recorder.record("PDP", "Action 2", "https://example.com/2", "Exp 2", "Act 2", workflow_code="PDP", index=1)

        all_ev = recorder.list_evidence()
        assert len(all_ev) == 2

        ev1 = recorder.get_evidence("EV-MOULEC-SRCH-001")
        assert ev1 is not None
        assert ev1.action == "Action 1"


class TestSiteMapGraphBuilder:
    """Verify programmatic graph construction and reference validation."""

    def test_builder_fluent_api(self):
        builder = SiteMapGraphBuilder(
            vendor_id="vendor_demo",
            vendor_name="Demo Electronics",
            base_url="https://demo.example.com",
        )
        builder.add_selector("sel_home_body", "css", "body", priority=1)
        builder.add_selector("sel_search_input", "id", "search-input", priority=1)
        builder.add_node("node_page_home", "PAGE", "Home Page", "Landing page", selectors=["sel_home_body"])
        builder.add_node("node_input_search", "INPUT", "Search Box", "Input", selectors=["sel_search_input"])
        builder.add_edge("edge_home_contains_search", "node_page_home", "node_input_search", "CONTAINS")
        builder.add_extraction("ext_stock", "stock_qty", "node_page_home", "DOM_TEXT", selector_id="sel_home_body")

        graph = builder.build()
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert len(graph.selectors) == 2
        assert len(graph.extractions) == 1

    def test_builder_rejects_duplicate_node_id(self):
        builder = SiteMapGraphBuilder("vendor_demo", "Demo", "https://demo.example.com")
        builder.add_node("node_1", "PAGE", "P1", "D1")
        with pytest.raises(ValueError, match="Duplicate node ID"):
            builder.add_node("node_1", "PAGE", "P1 duplicate", "D1")

    def test_builder_rejects_edge_to_missing_node(self):
        builder = SiteMapGraphBuilder("vendor_demo", "Demo", "https://demo.example.com")
        builder.add_node("node_1", "PAGE", "P1", "D1")
        with pytest.raises(ValueError, match="Target node 'node_missing' does not exist"):
            builder.add_edge("edge_1", "node_1", "node_missing", "CONTAINS")


class TestSiteMapGraphValidator:
    """Verify 10-point quality assurance validator."""

    def test_lion_reference_graph_passes_all_checks(self):
        assert os.path.exists(LION_GRAPH_PATH), f"Lion graph missing: {LION_GRAPH_PATH}"
        graph = SiteMapGraph.load(LION_GRAPH_PATH)
        report = SiteMapGraphValidator.validate_graph(graph, evidence_dir=LION_EVIDENCE_DIR)

        assert report.passed is True
        assert report.error_count == 0
        assert report.total_checks >= 10

    def test_javan_discovered_graph_passes_all_checks(self):
        assert os.path.exists(JAVAN_GRAPH_PATH), f"Javan graph missing: {JAVAN_GRAPH_PATH}"
        graph = SiteMapGraph.load(JAVAN_GRAPH_PATH)
        report = SiteMapGraphValidator.validate_graph(graph, evidence_dir=JAVAN_EVIDENCE_DIR)

        assert report.passed is True
        assert report.error_count == 0
        assert report.total_checks >= 10
        assert report.vendor_id == "vendor_javan"

    def test_roboeq_discovered_graph_passes_all_checks(self):
        assert os.path.exists(ROBOEQ_GRAPH_PATH), f"RoboEq graph missing: {ROBOEQ_GRAPH_PATH}"
        graph = SiteMapGraph.load(ROBOEQ_GRAPH_PATH)
        report = SiteMapGraphValidator.validate_graph(graph, evidence_dir=ROBOEQ_EVIDENCE_DIR)

        assert report.passed is True
        assert report.error_count == 0
        assert report.total_checks >= 10
        assert report.vendor_id == "vendor_roboeq"

    def test_validator_detects_duplicate_node_ids(self):
        graph = SiteMapGraph(
            metadata={"vendor_id": "v", "vendor_name": "V", "base_url": "https://v.com", "schema_version": "1.0.0"},
            nodes=[
                SiteMapNode("dup_id", "PAGE", "P1", "D1"),
                SiteMapNode("dup_id", "PAGE", "P2", "D2"),
            ],
            edges=[],
            selectors={},
            extractions=[],
        )
        report = SiteMapGraphValidator.validate_graph(graph)
        assert report.passed is False
        assert any(c.check_id == "CHK-UNIQUE-001" and not c.passed for c in report.checks)

    def test_validator_detects_invalid_edge_endpoints(self):
        graph = SiteMapGraph(
            metadata={"vendor_id": "v", "vendor_name": "V", "base_url": "https://v.com", "schema_version": "1.0.0"},
            nodes=[SiteMapNode("node_1", "PAGE", "P1", "D1")],
            edges=[SiteMapEdge("edge_1", "node_1", "node_nonexistent", "CONTAINS")],
            selectors={},
            extractions=[],
        )
        report = SiteMapGraphValidator.validate_graph(graph)
        assert report.passed is False
        assert any(c.check_id == "CHK-TOPOLOGY-001" and not c.passed for c in report.checks)

    def test_validator_detects_missing_selector(self):
        graph = SiteMapGraph(
            metadata={"vendor_id": "v", "vendor_name": "V", "base_url": "https://v.com", "schema_version": "1.0.0"},
            nodes=[SiteMapNode("node_1", "PAGE", "P1", "D1", selectors=["sel_missing"])],
            edges=[],
            selectors={},
            extractions=[],
        )
        report = SiteMapGraphValidator.validate_graph(graph)
        assert report.passed is False
        assert any(c.check_id == "CHK-SELECTOR-001" and not c.passed for c in report.checks)

    def test_validator_detects_core_procurement_leakage(self):
        graph = SiteMapGraph(
            metadata={"vendor_id": "v", "vendor_name": "V", "base_url": "https://v.com", "schema_version": "1.0.0"},
            nodes=[SiteMapNode("node_1", "PAGE", "P1", "D1", properties={"procurement_rule": "mode_a_inventory_shortage"})],
            edges=[],
            selectors={},
            extractions=[],
        )
        report = SiteMapGraphValidator.validate_graph(graph)
        assert report.passed is False
        assert any(c.check_id == "CHK-LEAKAGE-001" and not c.passed for c in report.checks)

    def test_multi_vendor_discovery_neutrality(self):
        """Ensure all 3 vendors (Lion, Javan, RoboEq) validate through generic pipeline."""
        lion_graph = SiteMapGraph.load(LION_GRAPH_PATH)
        javan_graph = SiteMapGraph.load(JAVAN_GRAPH_PATH)
        roboeq_graph = SiteMapGraph.load(ROBOEQ_GRAPH_PATH)

        r_lion = SiteMapGraphValidator.validate_graph(lion_graph, evidence_dir=LION_EVIDENCE_DIR)
        r_javan = SiteMapGraphValidator.validate_graph(javan_graph, evidence_dir=JAVAN_EVIDENCE_DIR)
        r_roboeq = SiteMapGraphValidator.validate_graph(roboeq_graph, evidence_dir=ROBOEQ_EVIDENCE_DIR)

        assert r_lion.passed is True
        assert r_javan.passed is True
        assert r_roboeq.passed is True
        assert r_lion.vendor_id == "vendor_lion"
        assert r_javan.vendor_id == "vendor_javan"
        assert r_roboeq.vendor_id == "vendor_roboeq"


class TestUniversalDiscoveryCLI:
    """Verify CLI interface and exit codes."""

    def test_cli_audit_lion_graph_returns_exit_code_zero(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "audit", LION_GRAPH_PATH]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== SITE MAP GRAPH VALIDATION REPORT: vendor_lion ===" in result.stdout
        assert "Status: PASSED" in result.stdout

    def test_cli_audit_javan_graph_returns_exit_code_zero(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "audit", JAVAN_GRAPH_PATH]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== SITE MAP GRAPH VALIDATION REPORT: vendor_javan ===" in result.stdout
        assert "Status: PASSED" in result.stdout

    def test_cli_audit_roboeq_graph_returns_exit_code_zero(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "audit", ROBOEQ_GRAPH_PATH]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== SITE MAP GRAPH VALIDATION REPORT: vendor_roboeq ===" in result.stdout
        assert "Status: PASSED" in result.stdout

    def test_cli_inspect_evidence_lion(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "inspect-evidence", LION_EVIDENCE_DIR]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== DISCOVERY EVIDENCE INSPECTION:" in result.stdout
        assert "Total Evidence Records: 27" in result.stdout

    def test_cli_inspect_evidence_javan(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "inspect-evidence", JAVAN_EVIDENCE_DIR]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== DISCOVERY EVIDENCE INSPECTION:" in result.stdout
        assert "Total Evidence Records: 16" in result.stdout

    def test_cli_inspect_evidence_roboeq(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "core.discovery.cli", "inspect-evidence", ROBOEQ_EVIDENCE_DIR]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, encoding="utf-8")
        assert result.returncode == 0
        assert "=== DISCOVERY EVIDENCE INSPECTION:" in result.stdout
        assert "Total Evidence Records: 14" in result.stdout
