"""
Omnix Universal Discovery - Evidence Recorder & Manager
Provides deterministic ID generation, structured evidence JSON serialization, and disk storage.
Governing Specification: docs/DISCOVERY/DISCOVERY_METHODOLOGY.md (DOC-OMNIX-DISC-001)
"""

import os
import re
import json
import datetime
from typing import Optional, Dict, Any, List

from core.discovery.models import EvidenceRecord


class EvidenceRecorder:
    """
    Manages deterministic collection, serialization, and querying of Discovery Evidence Records.
    """

    def __init__(self, vendor_id: str, evidence_dir: Optional[str] = None):
        self.vendor_id = vendor_id
        if evidence_dir is not None:
            self.evidence_dir = evidence_dir
        else:
            # Default to docs/VENDORS/{VENDOR_UPPER}/evidence
            vendor_folder = vendor_id.replace("vendor_", "").upper()
            self.evidence_dir = os.path.join("docs", "VENDORS", vendor_folder, "evidence")
        os.makedirs(self.evidence_dir, exist_ok=True)

    def generate_evidence_id(self, workflow_code: str, index: Optional[int] = None) -> str:
        """
        Generate deterministic Evidence ID conforming to EV-{VENDOR_SHORT}-{WORKFLOW}-{INDEX:03d}.
        """
        vendor_tag = self.vendor_id.replace("vendor_", "").upper()
        wf_tag = workflow_code.upper()

        if index is not None:
            return f"EV-{vendor_tag}-{wf_tag}-{index:03d}"

        # Determine next index automatically
        existing = self.list_evidence()
        matching_indices = []
        pattern = re.compile(rf"^EV-{vendor_tag}-{wf_tag}-(\d+)$", re.IGNORECASE)
        for ev in existing:
            m = pattern.match(ev.evidence_id)
            if m:
                matching_indices.append(int(m.group(1)))

        next_idx = max(matching_indices, default=0) + 1
        return f"EV-{vendor_tag}-{wf_tag}-{next_idx:03d}"

    def record(
        self,
        workflow: str,
        action: str,
        url: str,
        expected_observation: str,
        actual_observation: str,
        workflow_code: Optional[str] = None,
        index: Optional[int] = None,
        entry_state: Optional[str] = None,
        selector: Optional[str] = None,
        network_request: Optional[Dict[str, Any]] = None,
        network_response: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
        har_path: Optional[str] = None,
        verification_status: str = "VERIFIED",
        verifier: str = "DevTools & DOM Inspector",
        notes: Optional[str] = None,
    ) -> EvidenceRecord:
        """
        Create, persist, and return a new typed EvidenceRecord.
        """
        wf_code = workflow_code or workflow.split("_")[0][:4].upper()
        ev_id = self.generate_evidence_id(wf_code, index=index)
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        record = EvidenceRecord(
            evidence_id=ev_id,
            vendor_id=self.vendor_id,
            workflow=workflow,
            timestamp=now_ts,
            url=url,
            action=action,
            expected_observation=expected_observation,
            actual_observation=actual_observation,
            entry_state=entry_state,
            selector=selector,
            network_request=network_request,
            network_response=network_response,
            screenshot_reference=screenshot_path,
            har_reference=har_path,
            verification_status=verification_status,
            verifier=verifier,
            notes=notes,
        )

        filename = f"{ev_id}.json"
        target_path = os.path.join(self.evidence_dir, filename)
        record.save(target_path)
        return record

    def list_evidence(self) -> List[EvidenceRecord]:
        """Load and return all evidence records from the evidence directory."""
        records: List[EvidenceRecord] = []
        if not os.path.exists(self.evidence_dir):
            return records

        for item in sorted(os.listdir(self.evidence_dir)):
            if item.endswith(".json") and item.startswith("EV-"):
                try:
                    p = os.path.join(self.evidence_dir, item)
                    records.append(EvidenceRecord.load(p))
                except Exception:
                    pass
        return records

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceRecord]:
        """Retrieve a specific evidence record by ID."""
        filename = f"{evidence_id}.json"
        target_path = os.path.join(self.evidence_dir, filename)
        if os.path.exists(target_path):
            return EvidenceRecord.load(target_path)
        return None
