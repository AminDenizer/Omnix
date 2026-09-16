"""
Omnix Universal Discovery - Domain Models & Schema Contracts
Governing Specification: docs/DISCOVERY/SITE_MAP_SCHEMA.md (DOC-OMNIX-SCHEMA-001)
Vendor-neutral data structures for Site Map Graph, Nodes, Edges, Selectors, and Evidence.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional
import json
import os


class NodeType(str, Enum):
    PAGE = "PAGE"
    COMPONENT = "COMPONENT"
    FORM = "FORM"
    INPUT = "INPUT"
    BUTTON = "BUTTON"
    LINK = "LINK"
    RESULT = "RESULT"
    PRODUCT = "PRODUCT"
    CART = "CART"
    MODAL = "MODAL"
    ERROR = "ERROR"
    API_ENDPOINT = "API_ENDPOINT"
    DATA_SOURCE = "DATA_SOURCE"
    STATE = "STATE"


class RelationshipType(str, Enum):
    CONTAINS = "CONTAINS"
    TRIGGERS = "TRIGGERS"
    NAVIGATES_TO = "NAVIGATES_TO"
    RETURNS = "RETURNS"
    EXTRACTS = "EXTRACTS"
    UPDATES = "UPDATES"
    FAILS_WITH = "FAILS_WITH"
    RECOVERS_TO = "RECOVERS_TO"
    REQUIRES = "REQUIRES"
    DEPENDS_ON = "DEPENDS_ON"


class SelectorType(str, Enum):
    CSS = "css"
    XPATH = "xpath"
    ID = "id"
    TEXT = "text"
    ATTRIBUTE = "attribute"
    DATA_ATTRIBUTE = "data_attribute"
    URL_PATTERN = "url_pattern"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    OBSERVED = "OBSERVED"
    REPRODUCED = "REPRODUCED"
    VERIFIED = "VERIFIED"


@dataclass
class VendorTarget:
    """Vendor Target descriptor for zero-knowledge onboarding."""
    vendor_id: str
    vendor_name: str
    base_url: str
    auth_supported: bool = True
    description: Optional[str] = None
    extra_properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRecord:
    """Discovery Evidence Record matching DOC-OMNIX-DISC-001."""
    evidence_id: str
    vendor_id: str
    workflow: str
    timestamp: str
    url: str
    action: str
    expected_observation: str
    actual_observation: str
    entry_state: Optional[str] = None
    selector: Optional[str] = None
    network_request: Optional[Dict[str, Any]] = None
    network_response: Optional[Dict[str, Any]] = None
    screenshot_reference: Optional[str] = None
    har_reference: Optional[str] = None
    verification_status: str = "VERIFIED"
    verifier: str = "DevTools & DOM Inspector"
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None or k in ["network_request", "network_response"]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=data.get("evidence_id", ""),
            vendor_id=data.get("vendor_id", ""),
            workflow=data.get("workflow", ""),
            timestamp=data.get("timestamp", ""),
            url=data.get("url", ""),
            action=data.get("action", ""),
            expected_observation=data.get("expected_observation", ""),
            actual_observation=data.get("actual_observation", ""),
            entry_state=data.get("entry_state"),
            selector=data.get("selector"),
            network_request=data.get("network_request"),
            network_response=data.get("network_response"),
            screenshot_reference=data.get("screenshot_reference"),
            har_reference=data.get("har_reference"),
            verification_status=data.get("verification_status", "VERIFIED"),
            verifier=data.get("verifier", "DevTools & DOM Inspector"),
            notes=data.get("notes"),
        )

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "EvidenceRecord":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class SiteMapNode:
    """Site Map Graph Node matching SITE_MAP_SCHEMA.md."""
    id: str
    type: str
    label: str
    description: str
    selectors: List[str] = field(default_factory=list)
    url_pattern: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "description": self.description,
            "selectors": self.selectors,
            "url_pattern": self.url_pattern,
            "properties": self.properties,
            "evidence_ids": self.evidence_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SiteMapNode":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "PAGE"),
            label=data.get("label", ""),
            description=data.get("description", ""),
            selectors=data.get("selectors", []),
            url_pattern=data.get("url_pattern"),
            properties=data.get("properties", {}),
            evidence_ids=data.get("evidence_ids", []),
        )


@dataclass
class SiteMapEdge:
    """Site Map Graph Edge matching SITE_MAP_SCHEMA.md."""
    id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    condition: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relationship_type": self.relationship_type,
            "condition": self.condition,
            "evidence_ids": self.evidence_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SiteMapEdge":
        return cls(
            id=data.get("id", ""),
            source_node_id=data.get("source_node_id", ""),
            target_node_id=data.get("target_node_id", ""),
            relationship_type=data.get("relationship_type", "CONTAINS"),
            condition=data.get("condition"),
            evidence_ids=data.get("evidence_ids", []),
        )


@dataclass
class SelectorDefinition:
    """Site Map Selector Definition matching SITE_MAP_SCHEMA.md."""
    id: str
    type: str
    value: str
    priority: int = 1
    stability: str = "STABLE_CLASS"
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "value": self.value,
            "priority": self.priority,
            "stability": self.stability,
            "evidence_ids": self.evidence_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelectorDefinition":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "css"),
            value=data.get("value", ""),
            priority=data.get("priority", 1),
            stability=data.get("stability", "STABLE_CLASS"),
            evidence_ids=data.get("evidence_ids", []),
        )


@dataclass
class ExtractionDefinition:
    """Site Map Data Extraction Binding matching SITE_MAP_SCHEMA.md."""
    id: str
    field_name: str
    source_node_id: str
    source_type: str
    selector_id: Optional[str] = None
    attribute: Optional[str] = None
    regex: Optional[str] = None
    transform: str = "RAW"
    normalization_rule: Optional[str] = None
    required: bool = True
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "field_name": self.field_name,
            "source_node_id": self.source_node_id,
            "source_type": self.source_type,
            "selector_id": self.selector_id,
            "attribute": self.attribute,
            "regex": self.regex,
            "transform": self.transform,
            "normalization_rule": self.normalization_rule,
            "required": self.required,
            "evidence_ids": self.evidence_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractionDefinition":
        return cls(
            id=data.get("id", ""),
            field_name=data.get("field_name", ""),
            source_node_id=data.get("source_node_id", ""),
            source_type=data.get("source_type", "DOM_TEXT"),
            selector_id=data.get("selector_id"),
            attribute=data.get("attribute"),
            regex=data.get("regex"),
            transform=data.get("transform", "RAW"),
            normalization_rule=data.get("normalization_rule"),
            required=data.get("required", True),
            evidence_ids=data.get("evidence_ids", []),
        )


@dataclass
class SiteMapGraph:
    """Declarative Site Map Graph Root Contract."""
    metadata: Dict[str, Any]
    nodes: List[SiteMapNode] = field(default_factory=list)
    edges: List[SiteMapEdge] = field(default_factory=list)
    selectors: Dict[str, SelectorDefinition] = field(default_factory=dict)
    extractions: List[ExtractionDefinition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "metadata": self.metadata,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "selectors": {k: v.to_dict() for k, v in self.selectors.items()},
            "extractions": [x.to_dict() for x in self.extractions],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SiteMapGraph":
        meta = data.get("metadata", {})
        nodes = [SiteMapNode.from_dict(n) for n in data.get("nodes", [])]
        edges = [SiteMapEdge.from_dict(e) for e in data.get("edges", [])]
        selectors = {k: SelectorDefinition.from_dict(v) for k, v in data.get("selectors", {}).items()}
        extractions = [ExtractionDefinition.from_dict(x) for x in data.get("extractions", [])]
        return cls(metadata=meta, nodes=nodes, edges=edges, selectors=selectors, extractions=extractions)

    @classmethod
    def from_json(cls, json_str: str) -> "SiteMapGraph":
        data = json.loads(json_str)
        return cls.from_dict(data)

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json() + "\n")

    @classmethod
    def load(cls, filepath: str) -> "SiteMapGraph":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
