"""
Omnix Universal Discovery - Site Map Graph Builder
Constructs, validates, and serializes declarative Site Map Graphs conforming to SITE_MAP_SCHEMA.md.
"""

from typing import Dict, Any, List, Optional
import datetime

from core.discovery.models import (
    SiteMapGraph,
    SiteMapNode,
    SiteMapEdge,
    SelectorDefinition,
    ExtractionDefinition,
    NodeType,
    RelationshipType,
    SelectorType,
)


class SiteMapGraphBuilder:
    """
    Programmatic builder for creating structured Site Map Graphs.
    """

    def __init__(
        self,
        vendor_id: str,
        vendor_name: str,
        base_url: str,
        schema_version: str = "1.0.0",
        discovery_version: str = "1.0.0",
    ):
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.metadata: Dict[str, Any] = {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "base_url": base_url,
            "schema_version": schema_version,
            "discovery_version": discovery_version,
            "created_at": now_ts,
            "updated_at": now_ts,
            "last_verified": now_ts,
            "verification_status": "VERIFIED",
        }
        self.nodes: Dict[str, SiteMapNode] = {}
        self.edges: Dict[str, SiteMapEdge] = {}
        self.selectors: Dict[str, SelectorDefinition] = {}
        self.extractions: Dict[str, ExtractionDefinition] = {}

    def add_node(
        self,
        id: str,
        type: str,
        label: str,
        description: str,
        selectors: Optional[List[str]] = None,
        url_pattern: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        evidence_ids: Optional[List[str]] = None,
    ) -> "SiteMapGraphBuilder":
        if id in self.nodes:
            raise ValueError(f"Duplicate node ID: {id}")
        self.nodes[id] = SiteMapNode(
            id=id,
            type=type,
            label=label,
            description=description,
            selectors=selectors or [],
            url_pattern=url_pattern,
            properties=properties or {},
            evidence_ids=evidence_ids or [],
        )
        return self

    def add_edge(
        self,
        id: str,
        source_node_id: str,
        target_node_id: str,
        relationship_type: str,
        condition: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
    ) -> "SiteMapGraphBuilder":
        if id in self.edges:
            raise ValueError(f"Duplicate edge ID: {id}")
        if source_node_id not in self.nodes:
            raise ValueError(f"Source node '{source_node_id}' does not exist in graph")
        if target_node_id not in self.nodes:
            raise ValueError(f"Target node '{target_node_id}' does not exist in graph")

        self.edges[id] = SiteMapEdge(
            id=id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            condition=condition,
            evidence_ids=evidence_ids or [],
        )
        return self

    def add_selector(
        self,
        id: str,
        type: str,
        value: str,
        priority: int = 1,
        stability: str = "STABLE_CLASS",
        evidence_ids: Optional[List[str]] = None,
    ) -> "SiteMapGraphBuilder":
        if id in self.selectors:
            raise ValueError(f"Duplicate selector ID: {id}")
        self.selectors[id] = SelectorDefinition(
            id=id,
            type=type,
            value=value,
            priority=priority,
            stability=stability,
            evidence_ids=evidence_ids or [],
        )
        return self

    def add_extraction(
        self,
        id: str,
        field_name: str,
        source_node_id: str,
        source_type: str,
        selector_id: Optional[str] = None,
        attribute: Optional[str] = None,
        regex: Optional[str] = None,
        transform: str = "RAW",
        normalization_rule: Optional[str] = None,
        required: bool = True,
        evidence_ids: Optional[List[str]] = None,
    ) -> "SiteMapGraphBuilder":
        if id in self.extractions:
            raise ValueError(f"Duplicate extraction ID: {id}")
        if source_node_id not in self.nodes:
            raise ValueError(f"Extraction source node '{source_node_id}' does not exist")
        if selector_id and selector_id not in self.selectors:
            raise ValueError(f"Extraction selector '{selector_id}' does not exist")

        self.extractions[id] = ExtractionDefinition(
            id=id,
            field_name=field_name,
            source_node_id=source_node_id,
            source_type=source_type,
            selector_id=selector_id,
            attribute=attribute,
            regex=regex,
            transform=transform,
            normalization_rule=normalization_rule,
            required=required,
            evidence_ids=evidence_ids or [],
        )
        return self

    def build(self) -> SiteMapGraph:
        """Construct and return the complete SiteMapGraph instance."""
        return SiteMapGraph(
            metadata=self.metadata,
            nodes=list(self.nodes.values()),
            edges=list(self.edges.values()),
            selectors=self.selectors,
            extractions=list(self.extractions.values()),
        )
