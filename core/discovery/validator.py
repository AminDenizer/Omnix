"""
Omnix Universal Discovery - Automated Site Map Graph Validator
Performs rigorous structural, topological, and boundary verification of Site Map Graphs.
Governing Specification: docs/DISCOVERY/SITE_MAP_SCHEMA.md
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from core.discovery.models import SiteMapGraph, NodeType, RelationshipType, SelectorType


@dataclass
class ValidationCheck:
    check_id: str
    name: str
    passed: bool
    severity: str  # "ERROR", "WARNING", "INFO"
    message: str
    affected_object: Optional[str] = None
    evidence_id: Optional[str] = None


@dataclass
class ValidationReport:
    vendor_id: str
    passed: bool
    total_checks: int
    error_count: int
    warning_count: int
    checks: List[ValidationCheck] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checks": [
                {
                    "check_id": c.check_id,
                    "name": c.name,
                    "passed": c.passed,
                    "severity": c.severity,
                    "message": c.message,
                    "affected_object": c.affected_object,
                }
                for c in self.checks
            ],
        }

    def summary_text(self) -> str:
        status_str = "PASSED" if self.passed else "FAILED"
        lines = [
            f"=== SITE MAP GRAPH VALIDATION REPORT: {self.vendor_id} ===",
            f"Status: {status_str} (Errors: {self.error_count}, Warnings: {self.warning_count}, Total Checks: {self.total_checks})",
            "----------------------------------------------------------",
        ]
        for c in self.checks:
            mark = "[PASS]" if c.passed else f"[{c.severity}]"
            obj_str = f" ({c.affected_object})" if c.affected_object else ""
            lines.append(f"{mark} {c.check_id}: {c.name} - {c.message}{obj_str}")
        return "\n".join(lines)


class SiteMapGraphValidator:
    """
    Automated 10-Point Quality Assurance Auditor for Vendor Site Maps.
    """

    MANDATORY_WORKFLOW_NODE_TYPES = [
        "PAGE",
        "INPUT",
        "RESULT",
        "BUTTON",
    ]

    CORE_LEAKAGE_TERMS = [
        "mode_a", "shortage_calc", "bom_parsing",
        "pricing_rank", "procurement_optimization", "ceil("
    ]

    @classmethod
    def validate_graph(
        cls,
        graph: SiteMapGraph,
        evidence_dir: Optional[str] = None,
    ) -> ValidationReport:
        checks: List[ValidationCheck] = []
        vendor_id = graph.metadata.get("vendor_id", "unknown")

        # 1. Metadata Check
        req_meta = ["vendor_id", "vendor_name", "base_url", "schema_version"]
        missing_meta = [m for m in req_meta if not graph.metadata.get(m)]
        if missing_meta:
            checks.append(ValidationCheck("CHK-SCHEMA-001", "Metadata Completeness", False, "ERROR", f"Missing metadata fields: {missing_meta}"))
        else:
            checks.append(ValidationCheck("CHK-SCHEMA-001", "Metadata Completeness", True, "INFO", "Metadata complete"))

        # 2. Unique Node IDs
        node_ids = [n.id for n in graph.nodes]
        dup_nodes = [x for x in set(node_ids) if node_ids.count(x) > 1]
        if dup_nodes:
            checks.append(ValidationCheck("CHK-UNIQUE-001", "Node ID Uniqueness", False, "ERROR", f"Duplicate node IDs found: {dup_nodes}"))
        else:
            checks.append(ValidationCheck("CHK-UNIQUE-001", "Node ID Uniqueness", True, "INFO", f"All {len(node_ids)} node IDs are unique"))

        # 3. Unique Edge IDs
        edge_ids = [e.id for e in graph.edges]
        dup_edges = [x for x in set(edge_ids) if edge_ids.count(x) > 1]
        if dup_edges:
            checks.append(ValidationCheck("CHK-UNIQUE-002", "Edge ID Uniqueness", False, "ERROR", f"Duplicate edge IDs found: {dup_edges}"))
        else:
            checks.append(ValidationCheck("CHK-UNIQUE-002", "Edge ID Uniqueness", True, "INFO", f"All {len(edge_ids)} edge IDs are unique"))

        # 4. Topology Validity (Source & Target Nodes Exist)
        node_id_set = set(node_ids)
        invalid_edges = []
        for e in graph.edges:
            if e.source_node_id not in node_id_set:
                invalid_edges.append(f"{e.id} (invalid source: {e.source_node_id})")
            if e.target_node_id not in node_id_set:
                invalid_edges.append(f"{e.id} (invalid target: {e.target_node_id})")

        if invalid_edges:
            checks.append(ValidationCheck("CHK-TOPOLOGY-001", "Edge Topology Validity", False, "ERROR", f"Invalid edge endpoints: {invalid_edges}"))
        else:
            checks.append(ValidationCheck("CHK-TOPOLOGY-001", "Edge Topology Validity", True, "INFO", "All edge endpoints resolve to existing nodes"))

        # 5. Orphan Node Detection
        sources = {e.source_node_id for e in graph.edges}
        targets = {e.target_node_id for e in graph.edges}
        connected = sources | targets
        orphans = [nid for nid in node_ids if nid not in connected and nid != "node_page_home"]
        if orphans:
            checks.append(ValidationCheck("CHK-ORPHAN-001", "Orphan Node Detection", False, "WARNING", f"Detected orphan nodes without edges: {orphans}"))
        else:
            checks.append(ValidationCheck("CHK-ORPHAN-001", "Orphan Node Detection", True, "INFO", "Zero orphan nodes detected"))

        # 6. Selector Integrity
        selector_keys = set(graph.selectors.keys())
        missing_selectors = []
        for n in graph.nodes:
            for s in n.selectors:
                if s not in selector_keys:
                    missing_selectors.append(f"Node {n.id} references missing selector '{s}'")
        for x in graph.extractions:
            if x.selector_id and x.selector_id not in selector_keys:
                missing_selectors.append(f"Extraction {x.id} references missing selector '{x.selector_id}'")

        if missing_selectors:
            checks.append(ValidationCheck("CHK-SELECTOR-001", "Selector Reference Integrity", False, "ERROR", f"Missing selectors: {missing_selectors}"))
        else:
            checks.append(ValidationCheck("CHK-SELECTOR-001", "Selector Reference Integrity", True, "INFO", f"All {len(selector_keys)} selectors resolved cleanly"))

        # 7. Extraction Integrity
        invalid_extractions = []
        for x in graph.extractions:
            if x.source_node_id not in node_id_set:
                invalid_extractions.append(f"Extraction {x.id} references missing node '{x.source_node_id}'")

        if invalid_extractions:
            checks.append(ValidationCheck("CHK-EXTRACTION-001", "Extraction Integrity", False, "ERROR", f"Invalid extractions: {invalid_extractions}"))
        else:
            checks.append(ValidationCheck("CHK-EXTRACTION-001", "Extraction Integrity", True, "INFO", f"All {len(graph.extractions)} extractions bind to valid nodes"))

        # 8. Evidence File Traceability (if directory provided)
        if evidence_dir and os.path.exists(evidence_dir):
            existing_ev_files = {f.replace(".json", "") for f in os.listdir(evidence_dir) if f.endswith(".json")}
            referenced_evs = set()
            for n in graph.nodes:
                referenced_evs.update(n.evidence_ids)
            for e in graph.edges:
                referenced_evs.update(e.evidence_ids)
            for s in graph.selectors.values():
                referenced_evs.update(s.evidence_ids)
            for x in graph.extractions:
                referenced_evs.update(x.evidence_ids)

            missing_evs = [ev for ev in referenced_evs if ev not in existing_ev_files]
            if missing_evs:
                checks.append(ValidationCheck("CHK-EVIDENCE-001", "Evidence Traceability", False, "WARNING", f"Referenced evidence files not found on disk: {missing_evs}"))
            else:
                checks.append(ValidationCheck("CHK-EVIDENCE-001", "Evidence Traceability", True, "INFO", f"All {len(referenced_evs)} referenced evidence IDs exist on disk"))
        else:
            checks.append(ValidationCheck("CHK-EVIDENCE-001", "Evidence Traceability", True, "INFO", "Evidence directory check skipped (path not provided)"))

        # 9. Workflow Completeness Check
        node_types_in_graph = {n.type for n in graph.nodes}
        missing_wf_types = [t for t in cls.MANDATORY_WORKFLOW_NODE_TYPES if t not in node_types_in_graph]
        if missing_wf_types:
            checks.append(ValidationCheck("CHK-WORKFLOW-001", "Workflow Completeness", False, "WARNING", f"Missing expected workflow node types: {missing_wf_types}"))
        else:
            checks.append(ValidationCheck("CHK-WORKFLOW-001", "Workflow Completeness", True, "INFO", "All mandatory workflow node types present"))

        # 10. Core Procurement Leakage Detection
        leakages = []
        for n in graph.nodes:
            props_str = str(n.properties).lower()
            for term in cls.CORE_LEAKAGE_TERMS:
                if term in props_str:
                    leakages.append(f"Node {n.id} property contains Core term '{term}'")

        if leakages:
            checks.append(ValidationCheck("CHK-LEAKAGE-001", "Core Leakage Guard", False, "ERROR", f"Core procurement logic leaked into graph: {leakages}"))
        else:
            checks.append(ValidationCheck("CHK-LEAKAGE-001", "Core Leakage Guard", True, "INFO", "Zero Core procurement leakage detected in graph properties"))

        error_count = sum(1 for c in checks if not c.passed and c.severity == "ERROR")
        warning_count = sum(1 for c in checks if not c.passed and c.severity == "WARNING")
        passed = error_count == 0

        return ValidationReport(
            vendor_id=vendor_id,
            passed=passed,
            total_checks=len(checks),
            error_count=error_count,
            warning_count=warning_count,
            checks=checks,
        )
