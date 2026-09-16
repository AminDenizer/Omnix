# UNIVERSAL VENDOR DISCOVERY → SITE MAP → ADAPTER PIPELINE
## Architectural Refactoring & Engineering Process Hardening Plan

**Document Reference:** `DOC-OMNIX-PLAN-DISC-001`  
**Version:** `1.0.0`  
**Date:** 2026-09-16  
**Status:** PROPOSED ARCHITECTURAL PLAN (AWAITING HUMAN REVIEW)  
**Workspace:** `d:\management-elecutomtom` (Branch: `Auto`)  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/VENDORS/LION/SITE_MAP_GRAPH.json` (Phase 5 Approved Graph)
- `docs/VENDORS/LION/ADAPTER_SPECIFICATION.md` (DOC-OMNIX-SPEC-LION-001)
- `docs/VENDORS/LION/PHASE7_5_INTEGRATION_AUDIT.md` (DOC-OMNIX-AUDIT-INT-LION-001)

---

## 1. EXECUTIVE SUMMARY & MISSION

The objective of this engineering refactor is to establish a **permanent, deterministic, vendor-neutral onboarding capability** for the Omnix platform.

Rather than treating vendor discovery and adapter creation as an ad-hoc or vendor-specific manual task, Omnix formalizes a repeatable, evidence-backed engineering pipeline:

```
┌────────────────────────────────────────────────────────────────────────┐
│               UNIVERSAL VENDOR ONBOARDING PIPELINE                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 1. Zero-Knowledge Vendor Target
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 1: CHROME-BASED EMPIRICAL DISCOVERY                  │
│  • Headless / Interactive Chrome Browser Session                       │
│  • Live DOM Traversal, Form & Input Interception                       │
│  • AJAX / XHR / REST Network Request & Cookie Capture                  │
│  • Visual & Modal Error Triggering (Negative Probing)                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 2. Evidence Records (`EV-{VENDOR}-*`)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 2: TYPED EVIDENCE COLLECTION & AUDIT                 │
│  • Structured Evidence JSON Files (`evidence/EV-*.json`)               │
│  • Screenshots & HAR Traces Storage (`evidence/har/`, `screenshots/`)  │
│  • Verification Status Tagging (`VERIFIED` vs `DEFENSIVE`)             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 3. State & Node Synthesis
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 3: DECLARATIVE SITE MAP GRAPH SYNTHESIS              │
│  • 14 Supported Node Types (`PAGE`, `COMPONENT`, `INPUT`, etc.)        │
│  • 10 Directed Relationship Edges (`CONTAINS`, `TRIGGERS`, etc.)       │
│  • Unified Selector Catalog & Priority Fallbacks                       │
│  • Raw Extraction Bindings (Zero Core Math Leaked)                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 4. Automated Graph Validation Gate
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 4: SITE MAP VALIDATION & AUDIT GATE                  │
│  • Graph Schema Conformance (`SITE_MAP_SCHEMA.md`)                     │
│  • Edge Topology Check (No Orphan Nodes, No Undefined Edges)           │
│  • Selector-to-Evidence Traceability Verification                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 5. Formal Contract Derivation
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 5: VENDOR ADAPTER FORMAL SPECIFICATION               │
│  • Mapping Graph to 13 Conceptual `IVendorAdapter` Operations          │
│  • Normalized Data Contract Mapping (`SearchResultSet`, etc.)         │
│  • 13-Category Normalized Error Taxonomy Translation Table             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 6. Implementation Readiness Review
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 6: IMPLEMENTATION READINESS GATE (GATE 6.5)          │
│  • Core / Adapter Boundary Zero-Leakage Sign-off                       │
│  • Verification of Raw Quantity Step Rules (No Piecewise Rounding)     │
│  • Browser AJAX Settle Time & Cookie Precondition Verification         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 7. Adapter Code Generation / Impl
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 7: VENDOR ADAPTER IMPLEMENTATION                     │
│  • Implementation of `vendors/{vendor}/adapter.py`                     │
│  • Selector Isolation in `vendors/{vendor}/selectors.py`               │
│  • Error Translation in `vendors/{vendor}/errors.py`                   │
│  • Session & Driver Harness in `vendors/{vendor}/session.py`           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 8. Deterministic Unit & Live Tests
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 8: REGRESSION, INTEGRATION & SMOKE AUDIT             │
│  • 100% Passing Unit & Contract Mock Tests                             │
│  • Non-Destructive Live Storefront Smoke Test                          │
│  • Zero-Regression Verification on Existing Production Core/BOM        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 9. Atomic Engineering Boundary
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 9: ATOMIC GIT COMMIT & FINAL GATE SIGNOFF            │
│  • Logical Unit Verification (`git diff --check`, clean status)        │
│  • Standardized Conventional Commit Message Formatting                 │
└────────────────────────────────────────────────────────────────────────┘
```

**Core Principle:** **Lion Electronic (`vendor_lion`) is the first validated reference implementation, NOT an architectural special case.**

---

## 2. CURRENT ARCHITECTURE & COUPLING AUDIT

### 2.1 Current Strengths
1. **Approved Documentation Framework:**
   - `docs/MASTER_PROJECT_SPECIFICATION.md` establishes clear Core vs Adapter boundaries.
   - `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` defines the 12-phase discovery methodology.
   - `docs/DISCOVERY/SITE_MAP_SCHEMA.md` specifies the formal directed graph JSON schema.
2. **Clean Core Interface & Models:**
   - `core/vendor_interface.py` defines `IVendorAdapter` (13 conceptual operations).
   - `core/models.py` defines canonical typed data models.
   - `core/errors.py` defines 13 normalized error exceptions.
3. **Working Reference Implementation:**
   - `vendors/lion/` cleanly implements `LionVendorAdapter`.
   - `tests/test_lion_adapter.py` provides 23 deterministic unit tests.

### 2.2 Discovered Coupling & Gaps
1. **Ad-Hoc Tooling Gap:**
   - The tools used to probe Lion Electronic, capture evidence, validate graph integrity, and check adapter contracts were written as temporary scratch scripts (`lion_probe.py`, `audit_lion_artifacts.py`, `build_phase7_modules.py`).
   - There is no permanent, reusable Python module in `core/discovery/` that an engineer or automated agent can invoke on a new vendor URL (e.g. `python -m core.discovery.cli probe --url ...`).
2. **Missing Programmatic Schema Validator:**
   - While `SITE_MAP_SCHEMA.md` exists as markdown documentation, there is no Python class (`SiteMapGraphValidator`) to programmatically validate `SITE_MAP_GRAPH.json` against the schema, detect orphan nodes, verify edge references, and validate selector-to-evidence bindings.
3. **Missing Automated Evidence Generator:**
   - Discovery evidence records (`EV-*.json`) were constructed via one-off scripts. There is no standard `EvidenceRecorder` class that captures screenshots, HAR logs, DOM contexts, and writes typed evidence JSON files.
4. **Implicit Git Practices:**
   - Git commits have previously been performed ad-hoc rather than strictly gated at predefined atomic engineering milestones.

---

## 3. PROPOSED REUSABLE DISCOVERY ARCHITECTURE

To eliminate these gaps, we propose introducing a vendor-neutral discovery package: **`core/discovery/`**.

```
autom/atom/
├── core/
│   ├── __init__.py
│   ├── models.py                   # Canonical data contracts
│   ├── errors.py                   # 13 normalized error classes
│   ├── vendor_interface.py         # IVendorAdapter contract
│   │
│   └── discovery/                  # [NEW] Reusable Universal Discovery Engine
│       ├── __init__.py             # Exports DiscoveryEngine, GraphValidator, EvidenceRecorder
│       ├── models.py               # Typed dataclasses for Node, Edge, Selector, Evidence, Target
│       ├── session.py              # Universal Chrome observation driver with HAR & screenshot capture
│       ├── evidence.py             # EvidenceRecorder for creating & managing EV-{VENDOR}-*.json
│       ├── graph_builder.py        # Programmatic builder for SITE_MAP_GRAPH.json
│       ├── validator.py            # Automated audit engine verifying SiteMapGraph & Evidence
│       ├── spec_scaffolder.py      # Generates template ADAPTER_SPECIFICATION.md from graph
│       └── cli.py                  # Command-line interface for discovery workflows
│
├── docs/
│   ├── MASTER_PROJECT_SPECIFICATION.md
│   ├── DISCOVERY/
│   │   ├── DISCOVERY_METHODOLOGY.md
│   │   ├── SITE_MAP_SCHEMA.md
│   │   └── UNIVERSAL_DISCOVERY_REFACTOR_PLAN.md
│   └── VENDORS/
│       └── LION/                   # Reference Vendor Artifacts (Migrated & Validated)
│           ├── SITE_MAP_GRAPH.json
│           ├── evidence/
│           ├── ADAPTER_SPECIFICATION.md
│           ├── PHASE5_AUDIT_REPORT.md
│           ├── PHASE6_5_IMPLEMENTATION_READINESS.md
│           ├── PHASE7_IMPLEMENTATION_REPORT.md
│           └── PHASE7_5_INTEGRATION_AUDIT.md
│
├── vendors/
│   ├── __init__.py
│   └── lion/                       # Lion Reference Adapter
│       ├── __init__.py
│       ├── adapter.py
│       ├── errors.py
│       ├── selectors.py
│       └── session.py
│
└── tests/
    ├── test_bom_auditor.py
    ├── test_dialog_and_edge_cases.py
    ├── test_excel_loader.py
    ├── test_lion_adapter.py
    ├── test_lion_rules.py
    ├── test_settings_and_config.py
    └── test_universal_discovery.py # [NEW] Unit tests for the discovery engine & validator
```

---

## 4. DETAILED SPECIFICATION OF GENERIC COMPONENTS

### 4.1 Discovery Data Models (`core/discovery/models.py`)
Defines strictly typed Python dataclasses matching `SITE_MAP_SCHEMA.md`:
- `VendorTarget`: `vendor_id: str`, `vendor_name: str`, `base_url: str`, `auth_supported: bool`
- `EvidenceRecord`: `evidence_id: str`, `vendor_id: str`, `workflow: str`, `timestamp: str`, `url: str`, `action: str`, `expected_observation: str`, `actual_observation: str`, `selector: Optional[str]`, `screenshot_reference: Optional[str]`, `har_reference: Optional[str]`, `verification_status: str`, `verifier: str`, `notes: str`
- `SiteMapNode`: `id: str`, `type: NodeType` (enum of 14 types), `label: str`, `description: str`, `selectors: List[str]`, `url_pattern: Optional[str]`, `properties: Dict[str, Any]`, `evidence_ids: List[str]`
- `SiteMapEdge`: `id: str`, `source_node_id: str`, `target_node_id: str`, `relationship_type: RelationshipType` (enum of 10 types), `condition: Optional[str]`, `evidence_ids: List[str]`
- `SelectorDefinition`: `id: str`, `type: SelectorType` (`css`, `xpath`, `id`, `text`, `attribute`), `value: str`, `priority: int`, `stability: str`, `evidence_ids: List[str]`
- `ExtractionDefinition`: `id: str`, `field_name: str`, `source_node_id: str`, `source_type: str`, `selector_id: str`, `regex: Optional[str]`, `transform: str`, `normalization_rule: Optional[str]`, `required: bool`, `evidence_ids: List[str]`
- `SiteMapGraph`: `metadata: Dict[str, Any]`, `nodes: List[SiteMapNode]`, `edges: List[SiteMapEdge]`, `selectors: Dict[str, SelectorDefinition]`, `extractions: List[ExtractionDefinition]`

### 4.2 Browser Observation Engine (`core/discovery/session.py`)
- Standardized Selenium Chrome harness with CDP (Chrome DevTools Protocol) listeners.
- Captures network requests, response bodies, response headers, cookies, and console logs.
- Automatic full-page screenshot capture upon state changes.
- Safe rate-limiting and configurable request throttling (default 1.0–2.0s).

### 4.3 Evidence Recorder (`core/discovery/evidence.py`)
- Deterministic ID generator (`EV-{VENDOR_CODE}-{WORKFLOW_CODE}-{INDEX:03d}`).
- Writes typed JSON files to `docs/VENDORS/{VENDOR_ID}/evidence/`.
- Validates that every evidence file meets mandatory schema fields.

### 4.4 Graph Validator Engine (`core/discovery/validator.py`)
Performs 10 automated structural audit checks on any `SITE_MAP_GRAPH.json`:
1. **Schema Check:** All required metadata, nodes, edges, selectors, and extractions present.
2. **Node ID Uniqueness:** Zero duplicate node IDs.
3. **Edge Topology:** All `source_node_id` and `target_node_id` must reference valid existing nodes.
4. **Orphan Node Detection:** Every node (except root `node_page_home`) must have at least one incoming or outgoing edge.
5. **Selector Integrity:** Every selector referenced in a node or extraction must exist in the `selectors` dictionary.
6. **Evidence Traceability:** Every `evidence_ids` reference must resolve to an existing `EV-*.json` file on disk.
7. **Extraction Integrity:** Every extraction must reference an existing node and selector.
8. **Required Workflows:** Verifies presence of mandatory nodes (`node_page_home`, `node_input_search_query`, `node_page_search_results`, `node_page_pdp`, `node_input_quantity`, `node_btn_add_to_cart`).
9. **Verification Level Consistency:** Ensures `verification_status` reflects underlying evidence tags.
10. **Zero Core Logic Leaks:** Verifies node/edge properties contain no BOM math or procurement keywords.

---

## 5. UNIVERSAL 10-STAGE VENDOR ONBOARDING WORKFLOW

```
┌───────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│ TARGET│ ──> │ DISCOVERY    │ ──> │ EVIDENCE     │ ──> │ SITE MAP GRAPH │
│ CONFIG│     │ (Chrome Obs) │     │ RECORDING    │     │ SYNTHESIS      │
└───────┘     └──────────────┘     └──────────────┘     └───────┬────────┘
                                                                │
                                                                ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│ ATOMIC   │ <── │ INTEGRATION  │ <── │ ADAPTER      │ <── │ GRAPH AUDIT │
│ COMMIT   │     │ & REGRESSION │     │ IMPLEMENT    │     │ & SPEC GATE │
└──────────┘     └──────────────┘     └──────────────┘     └─────────────┘
```

When onboarding ANY future vendor (e.g. `vendor_javan`, `vendor_moulec`), the engineer/agent executes:

1. **`VendorTarget` Declaration:** Declare vendor ID, name, base URL in `docs/VENDORS/{VENDOR}/`.
2. **Chrome Observation Run:** Run `core.discovery` harness to observe homepage, search query, PDP, quantity step, cart mutation, and login.
3. **Evidence Generation:** Generate structured `EV-{VENDOR}-*.json` records.
4. **Site Map Graph Compilation:** Compile `docs/VENDORS/{VENDOR}/SITE_MAP_GRAPH.json`.
5. **Automated Graph Validation:** Run `python -m core.discovery.validator docs/VENDORS/{VENDOR}/SITE_MAP_GRAPH.json`.
6. **Adapter Formal Specification:** Compile `docs/VENDORS/{VENDOR}/ADAPTER_SPECIFICATION.md`.
7. **Implementation Readiness Review:** Run Phase 6.5 gate check.
8. **Adapter Implementation:** Implement `vendors/{vendor}/adapter.py`, `selectors.py`, `errors.py`, `session.py`.
9. **Deterministic Unit & Smoke Tests:** Implement `tests/test_{vendor}_adapter.py` and run live smoke test.
10. **Atomic Git Commit:** Review `git diff` and commit at verified boundary.

---

## 6. LION REFERENCE MIGRATION STRATEGY

To validate the universal discovery engine, **Lion Electronic** will be used as the primary benchmark:
1. Run `core.discovery.validator` against `docs/VENDORS/LION/SITE_MAP_GRAPH.json` and its 27 evidence records.
2. Confirm 100% validation pass rate.
3. Verify that the existing `vendors/lion/` adapter and 36 automated tests remain 100% green without modification.
4. Prove that Lion is fully compliant with the generic pipeline without any special-casing.

---

## 7. GIT ATOMIC COMMIT BOUNDARIES & CHANGE MANAGEMENT

Git commits must occur **only** at verified, logical boundaries:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   APPROVED ATOMIC COMMIT BOUNDARIES                    │
├─────┬──────────────────────────────────────────────────────────────────┤
│ C01 │ feat(discovery): introduce universal discovery models & schema   │
│ C02 │ feat(discovery): add automated graph validator and CLI           │
│ C03 │ test(discovery): add unit tests for discovery engine & validator │
│ C04 │ docs(discovery): add universal discovery pipeline guide          │
│ C05 │ refactor(lion): validate lion reference artifacts against engine │
└─────┴──────────────────────────────────────────────────────────────────┘
```

### Mandatory Pre-Commit Checklist:
- [ ] `git status` shows only intended files.
- [ ] `git diff --check` has zero whitespace or syntax errors.
- [ ] `python -m pytest tests -v` passes 100%.
- [ ] Zero changes to existing production code (`main.py`, `bom_auditor.py`, `excel_loader.py`, `Inventory.xlsx`).
- [ ] Commit message conforms to Conventional Commits format.

---

## 8. RISK ASSESSMENT & MITIGATION

| Risk ID | Risk Description | Severity | Mitigation Strategy |
|---|---|:---:|---|
| **R01** | Breaking existing Lion adapter during refactoring | HIGH | Keep `core/discovery/` completely decoupled from runtime `core/models.py`. Lion runtime code is not altered. |
| **R02** | Schema divergence between markdown and Python validator | MEDIUM | Derive `core/discovery/models.py` strictly from `docs/DISCOVERY/SITE_MAP_SCHEMA.md`. |
| **R03** | Core procurement logic leaking into discovery tooling | HIGH | Prohibit any BOM math or shortage calculation imports in `core/discovery/`. |
| **R04** | Incomplete evidence records for future vendors | MEDIUM | Automated validator enforces non-null screenshot/HAR or explicit textual observation. |

---

## 9. EXACT FILE IMPACT MATRIX (PHASE B PREVIEW)

The following files will be created/modified when Phase B is authorized:

### New Files to Create:
1. `core/discovery/__init__.py`
2. `core/discovery/models.py`
3. `core/discovery/validator.py`
4. `core/discovery/evidence.py`
5. `core/discovery/graph_builder.py`
6. `core/discovery/cli.py`
7. `tests/test_universal_discovery.py`
8. `docs/DISCOVERY/UNIVERSAL_DISCOVERY_REFACTOR_PLAN.md`

### Existing Files Modified:
- `core/__init__.py` (Export discovery package)

### Untouched Files (Strict Invariant):
- `main.py` (0 diff)
- `bom_auditor.py` (0 diff)
- `excel_loader.py` (0 diff)
- `Inventory.xlsx` (0 diff)
- `vendors/lion/*` (0 diff)
- `tests/test_lion_adapter.py` (0 diff)

---

## 10. CONCLUSION & HARD STOP

Phase A (Architectural Audit & Refactoring Plan) is complete.

**Next Action:** Await explicit user authorization for Phase B implementation.
