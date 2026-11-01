"""
Omnix Universal Discovery - Command Line Interface
Unified CLI tool for validating Site Map Graphs and inspecting discovery evidence.
Usage:
    python -m core.discovery.cli validate <SITE_MAP_GRAPH.json> [--evidence-dir <dir>]
    python -m core.discovery.cli audit <SITE_MAP_GRAPH.json> [--evidence-dir <dir>]
    python -m core.discovery.cli inspect-evidence <evidence_dir>
"""

import sys
import os
import argparse
import json

from core.discovery.models import SiteMapGraph
from core.discovery.validator import SiteMapGraphValidator
from core.discovery.evidence import EvidenceRecorder


def cmd_validate(args):
    """Validate a Site Map Graph JSON file."""
    graph_path = args.graph_file
    if not os.path.exists(graph_path):
        print(f"ERROR: Graph file not found: {graph_path}", file=sys.stderr)
        return 1

    try:
        graph = SiteMapGraph.load(graph_path)
    except Exception as e:
        print(f"ERROR: Failed to load JSON graph: {str(e)}", file=sys.stderr)
        return 1

    ev_dir = args.evidence_dir
    if not ev_dir:
        # Check if adjacent evidence folder exists
        parent_dir = os.path.dirname(graph_path)
        candidate_ev_dir = os.path.join(parent_dir, "evidence")
        if os.path.exists(candidate_ev_dir):
            ev_dir = candidate_ev_dir

    report = SiteMapGraphValidator.validate_graph(graph, evidence_dir=ev_dir)
    print(report.summary_text())

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))

    return 0 if report.passed else 1


def cmd_inspect_evidence(args):
    """Inspect all evidence JSON files in a directory."""
    ev_dir = args.evidence_dir
    if not os.path.exists(ev_dir):
        print(f"ERROR: Evidence directory not found: {ev_dir}", file=sys.stderr)
        return 1

    recorder = EvidenceRecorder(vendor_id="generic", evidence_dir=ev_dir)
    records = recorder.list_evidence()

    print(f"=== DISCOVERY EVIDENCE INSPECTION: {ev_dir} ===")
    print(f"Total Evidence Records: {len(records)}")
    print("--------------------------------------------------")
    for r in records:
        print(f"[{r.verification_status}] {r.evidence_id}: {r.workflow} -> {r.action}")
        print(f"    URL: {r.url}")
        print(f"    Observed: {r.actual_observation}")
        if r.selector:
            print(f"    Selector: {r.selector}")
        print()

    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="python -m core.discovery.cli",
        description="Omnix Universal Vendor Discovery & Site Map CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Validate / Audit command
    val_parser = subparsers.add_parser("validate", aliases=["audit"], help="Validate Site Map Graph against schema")
    val_parser.add_argument("graph_file", help="Path to SITE_MAP_GRAPH.json")
    val_parser.add_argument("--evidence-dir", help="Optional path to evidence/ directory")
    val_parser.add_argument("--json-output", action="store_true", help="Print output as JSON")

    # Inspect Evidence command
    ev_parser = subparsers.add_parser("inspect-evidence", help="Inspect evidence directory")
    ev_parser.add_argument("evidence_dir", help="Path to evidence/ directory")

    args = parser.parse_args()

    if args.command in ["validate", "audit"]:
        sys.exit(cmd_validate(args))
    elif args.command == "inspect-evidence":
        sys.exit(cmd_inspect_evidence(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
