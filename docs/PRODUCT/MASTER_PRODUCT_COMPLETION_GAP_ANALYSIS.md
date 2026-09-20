# MASTER PRODUCT COMPLETION GAP AUDIT & FORENSIC EXPANSION
## Omnix — Deterministic Multi-Vendor Electronics Procurement Platform

**Document Reference:** `DOC-OMNIX-GAP-001`  
**Version:** `3.0.0-FINAL-FORENSIC-EXPANSION`  
**Status:** Authoritative Master Product Gap Analysis & Implementation Backlog  
**Repository:** `D:\management-elec\autom\atom`  
**Branch:** `Auto`  
**Automated Tests:** 331 / 331 PASSED  
**Discovery Graph Audits:** Lion (`10/10`), Javan (`10/10`), RoboEq (`10/10`) — ALL 30/30 PASS  
**Phase 9 Baseline:** `PHASE_9_FINAL_REVIEW_PASS`  
**Audit Date:** September 20, 2026  

---

## 1. EXECUTIVE SUMMARY & FORENSIC POSTURE ASSESSMENT

This document represents the **Final Forensic Product-Level Gap Expansion** for the Omnix platform.

### 1.1 Objective of the Forensic Expansion
Following the formal certification of Phase 9 (`PHASE_9_FINAL_REVIEW_PASS`), this audit expands and freezes every functional, architectural, authentication, UI, and CAD contract requirement identified across all architectural sessions. It reconciles the complete set of 20 product requirements (Requirements A through U) into a mathematically closed, dependency-ordered implementation backlog.

### 1.2 Core Architectural Invariant: Baseline Certified != Product Complete
- **Phase 9 Baseline (`PHASE_9_FINAL_REVIEW_PASS`):** Formally certified that the Universal Procurement Core (`core/procurement/`), dynamic Vendor Registry (`registry.py`), and decoupled adapter interface (`IVendorAdapter`) operate with 100% mathematical integrity across 183 unit/contract/integration tests.
- **Product Completion Status:** **TASKS A1 THROUGH A6 COMPLETED AND VERIFIED.** Multi-vendor desktop workflows, dual procurement modes, brand selection rules, package/footprint hard matching, interactive security challenge recovery, multi-vendor settings, idempotent cart staging, and multi-vendor deterministic export reporting are fully implemented and verified.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PRODUCT STATE CLASSIFICATION                                   │
├───────────────────────────────┬─────────────────────────────────┬────────────────────────────────┤
│ Subsystem / Layer             │ Automated / Contract State      │ Production Product State       │
├───────────────────────────────┼─────────────────────────────────┼────────────────────────────────┤
│ Datastore & Inventory Access  │ ExcelDataLoader (Inventory.xlsx)│ Production Excel Datastore (OK)│
│ Core Procurement Models       │ 100% Verified (Unit Tests)      │ Typed EvaluationState Verified │
│ Technical Matching Engine     │ MPN String Match Verified       │ Package/Footprint/Brand VERIF. │
│ Vendor Registry & Routing     │ 100% Verified (Regex Routing)   │ Enable/Disable Toggles VERIF.  │
│ Discovery Site Maps           │ 30 / 30 Checks PASSED (10/10)   │ Codified in Graph Selectors    │
│ Vendor Automation Adapters    │ Mock Staging Verified (183)     │ Interactive Challenge VERIFIED │
│ Desktop UI Workflows          │ Mode A & Mode B Working         │ Quick Order & Preview VERIFIED │
│ Cart Staging Runtime          │ Batch Staging Working           │ Idempotent Deduplication VERIF.│
│ Reporting & Audit             │ Deterministic Export Pipeline   │ Multi-Vendor PDF/CSV/XLSX VERIF│
│ Persistence & Relational DB   │ Openpyxl Direct File Access     │ Future SQLite Roadmap (GAP-14) │
└───────────────────────────────┴─────────────────────────────────┴────────────────────────────────┘
```

---

## 2. SOURCE-OF-TRUTH HIERARCHY & IMMUTABLE INVARIANTS

All gap determinations and architectural specifications in this document are strictly governed by the following hierarchy:

1. **Current Codebase Implementation:** (`core/`, `vendors/`, `ui/`, `bom_auditor.py`, `excel_loader.py`, `settings_manager.py`).
2. **Current Automated Test Suite:** (`tests/` — 183 passing tests).
3. **Master Project Specification:** (`docs/MASTER_PROJECT_SPECIFICATION.md` `DOC-OMNIX-MPS-001`).
4. **Master Implementation Roadmap:** (`docs/PRODUCT/MASTER_IMPLEMENTATION_ROADMAP.md`).
5. **Phase Certifications & Commit Log:** (Phases 1 through 9 on branch `Auto`).
6. **Explicit Open Decisions:** (`OD-001`, `OD-002`, `OD-003`).

### 2.1 Immutable Architecture Invariants:
1. **Excel Production Datastore:** `Inventory.xlsx` is the active, verified production datastore. `ExcelDataLoader` and `BOMAuditor` are the active data access layer.
2. **Zero Database Migration in Current Phase:** No SQLite migration or schema rewrite is permitted during the active completion tasks. `GAP-14` is preserved as a future evolutionary milestone.
3. **Altium Library Boundary:** External Altium component library construction (symbols, footprints, component DB) is **OUT OF SCOPE**. However, the **Altium Component Parameter Contract (`DOC-OMNIX-ALTIUM-CONTRACT-001`) is IN SCOPE** for Omnix ingestion.
4. **Strict Determinism:** 100% deterministic rule-based evaluation. Zero fuzzy heuristics or unverified assumptions.
5. **Zero Autonomous AI/LLM Purchasing Agents:** No LLM runtime decision loops for procurement or purchasing.
6. **Human-in-the-Loop Final Checkout:** Omnix automates up to the verified vendor shopping cart stage only. Final financial checkout and payment execution are strictly human-controlled.
7. **Vendor Isolation & Dynamic Configuration:** Each vendor adapter is fully decoupled and individually configurable (enabled/disabled, credentials, timeouts).
8. **Conservative Constraint Evaluation:** `OD-001` remains strictly **OPEN**. Package and Footprint are evaluated as two separate, independent constraints using exact normalized equality without assuming broad package family equivalences (e.g., DIP-8 != SOP-8; DIP-8 != PDIP-8).

---

## 3. MASTER GAP REGISTRY (FORENSICALLY VERIFIED)

The following master table details all **18 identified product gaps** across the Omnix platform. Each gap is grounded in repository evidence, classified by implementation layer, and evaluated for release-blocking status.

| ID | Domain | Requirement Title | Current Implementation State | Repository Evidence | Status | Primary Layer | Impact Classification | Dependencies | Blocking? |
|---|---|---|---|---|:---:|:---:|---|---|:---:|
| **`GAP-01`** | UI / Workflow | Dual Procurement Modes (Mode A vs Mode B) | Mode A (database-aware) and Mode B (turnkey direct BOM) fully implemented and UI switchable | [`bom_auditor.py:10`](file:///d:/management-elec/autom/atom/bom_auditor.py#L10) | `VERIFIED` | `UI / WORKFLOW` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_USER_WORKFLOW` | `GAP-04`, `GAP-06` | **YES** |
| **`GAP-02`** | UI / Workflow | Direct MPN Procurement Entry Form | Standalone QuickOrderDialog tab implemented with brand rules, stepper, vendor filtering, candidate table, and cart delta staging | [`ui/dialogs/quick_order_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/quick_order_dialog.py) | `VERIFIED` | `UI` | `BLOCKS_USER_WORKFLOW` | `GAP-04`, `GAP-07` | No |
| **`GAP-03`** | UI / Workflow | Direct URL Procurement Entry Form | Standalone QuickOrderDialog tab implemented with strict PDP regex validation, live inspection, constraint extraction, and cart delta staging | [`ui/dialogs/quick_order_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/quick_order_dialog.py) | `VERIFIED` | `UI` | `BLOCKS_USER_WORKFLOW` | `GAP-13` | No |
| **`GAP-04`** | Matching | Package & Footprint Hard Constraints | Exact normalized string equality in candidate evaluation with conservative normalization | [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py) | `VERIFIED` | `CORE_ENGINE` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_DATA_CORRECTNESS` | None (Internal Contract) | **YES** |
| **`GAP-05`** | Matching | `UNKNOWN_REQUIRED_PARAMETER` & Spec Engine | Typed `EvaluationState` enum, 4-state spec engine, and dimension validator implemented | [`core/procurement/models.py`](file:///d:/management-elec/autom/atom/core/procurement/models.py) | `VERIFIED` | `CORE_ENGINE` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_DATA_CORRECTNESS` | None | **YES** |
| **`GAP-06`** | Matching | Manufacturer / Brand Constraint Engine | `ANY` vs explicit approved manufacturer list filtering implemented in Core | [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py) | `VERIFIED` | `CORE_ENGINE` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_DATA_CORRECTNESS` | `GAP-05` | **YES** |
| **`GAP-07`** | UI / Preview | Multi-Candidate Alternative Selection UI | Master-Detail OrderPreviewDialog implemented with factual candidate comparison, radio candidate override, dynamic total recalculation, and staging | [`ui/dialogs/order_preview_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/order_preview_dialog.py) | `VERIFIED` | `UI` | `BLOCKS_USER_WORKFLOW`, `BLOCKS_MULTI_CANDIDATE` | `GAP-04`, `GAP-05` | No |
| **`GAP-08`** | Sourcing | Split-Vendor Line Item Sourcing | Entire line item allocated to single vendor | [`core/procurement/orchestrator.py:196`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py#L196) | `MISSING` | `CORE_ENGINE` | `NON_BLOCKING_PRODUCT_GAP`, `OPEN_SPECIFICATION_DEPENDENCY` | `OD-002` | No |
| **`GAP-09`** | Authentication | Interactive Challenge & Headful Fallback | Headless-to-headful session promotion with qualified cookie transfer across all vendors | [`vendors/lion/session.py`](file:///d:/management-elec/autom/atom/vendors/lion/session.py) | `VERIFIED` | `AUTHENTICATION` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_PRODUCTION_RUNTIME` | `GAP-11`, `GAP-17` | **YES** |
| **`GAP-10`** | Security | Encrypted Keyring Credential Storage | Plaintext JSON in `settings.json` | [`settings_manager.py:20`](file:///d:/management-elec/autom/atom/settings_manager.py#L20) | `PARTIALLY_IMPLEMENTED` | `SECURITY` | `NON_BLOCKING_PRODUCT_GAP` | None | No |
| **`GAP-11`** | Vendor Mgmt | Multi-Vendor Settings & Enable/Disable | 4-tab SettingsDialog with independent enable toggles, credentials, and dynamic registry filtering | [`ui/dialogs/settings_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/settings_dialog.py) | `VERIFIED` | `UI / SETTINGS` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_MULTI_VENDOR` | None | **YES** |
| **`GAP-12`** | Runtime | Finite State Machine Job Lifecycle | Coarse string statuses (`"RESOLVED"`, etc.) | [`core/procurement/models.py:88`](file:///d:/management-elec/autom/atom/core/procurement/models.py#L88) | `MISSING` | `RUNTIME` | `NON_BLOCKING_PRODUCT_GAP` | None | No |
| **`GAP-13`** | Runtime | Multi-Vendor Cart Idempotency & Delta Sync | Full cart inspection, 4-tier identity cascade, delta staging, and idempotent no-op returns implemented | [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py) | `VERIFIED` | `RUNTIME` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_PRODUCTION_RUNTIME` | None | **YES** |
| **`GAP-14`** | Persistence | SQLite ACID Repository Migration | Direct `openpyxl` file access with file locking risk | [`excel_loader.py:213`](file:///d:/management-elec/autom/atom/excel_loader.py#L213) | `DOCUMENTED_ONLY` | `PERSISTENCE` | `NON_BLOCKING_PRODUCT_GAP`, `OPEN_SPECIFICATION_DEPENDENCY` | `OD-003` | No |
| **`GAP-15`** | Audit | Append-Only Persistent Event Log | Basic Python console logging only | [`core/procurement/bridge.py:27`](file:///d:/management-elec/autom/atom/core/procurement/bridge.py#L27) | `MISSING` | `AUDIT` | `NON_BLOCKING_PRODUCT_GAP` | `GAP-14` | No |
| **`GAP-16`** | Altium Contract| Extended Parameter Ingestion Parser | Full 20-parameter contract parser, strict MPN validation, and technical spec extraction implemented | [`bom_auditor.py:10`](file:///d:/management-elec/autom/atom/bom_auditor.py#L10) | `VERIFIED` | `CAD_INTEGRATION` | `NON_BLOCKING_PRODUCT_GAP`, `BLOCKS_DATA_CORRECTNESS` | None (Contract Defined) | No |
| **`GAP-17`** | Security | Universal Challenge / CAPTCHA Handler | Unified `IChallengeHandler` subsystem with 8 challenge types, callback & Qt dialogs | [`core/procurement/challenge_handler.py`](file:///d:/management-elec/autom/atom/core/procurement/challenge_handler.py) | `VERIFIED` | `SECURITY / AUTH` | `BLOCKS_PRODUCT_COMPLETION`, `BLOCKS_PRODUCTION_RUNTIME` | None | **YES** |
| **`GAP-18`** | Reporting | Multi-Vendor Deterministic Export Pipeline | Pure functional multi-vendor PDF, CSV (RFC 4180/utf-8-sig), and XLSX (multi-sheet/openpyxl) deterministic export pipeline with candidate audit trails and Persian/RTL support | [`core/procurement/reporting/`](file:///d:/management-elec/autom/atom/core/procurement/reporting/) | `VERIFIED` | `REPORTING` | `NON_BLOCKING_PRODUCT_GAP` | `GAP-01`, `GAP-07` | No |

---

## 4. GAP STATUS & IMPACT BREAKDOWN

### 4.1 Status Summary
- **`VERIFIED`:** **12 GAPs** (`GAP-01`, `GAP-02`, `GAP-03`, `GAP-04`, `GAP-05`, `GAP-06`, `GAP-07`, `GAP-09`, `GAP-11`, `GAP-13`, `GAP-16`, `GAP-17`)
- **`PARTIALLY_IMPLEMENTED`:** **2 GAPs** (`GAP-10`, `GAP-18`)
- **`MISSING`:** **3 GAPs** (`GAP-08`, `GAP-12`, `GAP-15`)
- **`DOCUMENTED_ONLY`:** **1 GAP** (`GAP-14`)
- **Total Registered GAPs:** **18 GAPs**


### 4.2 Release-Blocking vs Non-Blocking GAPs
Forensic verification confirms that **EXACTLY 8 GAPS** are strictly classified as **`BLOCKS_PRODUCT_COMPLETION`** (ALL 8 ARE NOW VERIFIED):
1. **`GAP-01` (Dual Procurement Operating Modes):** Users must be able to select between Mode A (Database-Aware) and Mode B (Direct BOM Sourcing) without database presence blocking procurement. *(VERIFIED in Task A3)*
2. **`GAP-04` (Package & Footprint Independent Hard Constraints):** Prevents purchasing physically incompatible SMD/through-hole components (e.g. DIP vs SOP). *(VERIFIED in Task A1)*
3. **`GAP-05` (`UNKNOWN_REQUIRED_PARAMETER` & Spec Engine):** Prevents auto-accepting or auto-rejecting products with unlisted technical specifications or unconfirmed dimensions. *(VERIFIED in Task A1)*
4. **`GAP-06` (Manufacturer / Brand Constraint Engine):** Enforces user brand rules (`ANY` vs explicit approved brand set) so cheaper unapproved brands are not selected over approved ones. *(VERIFIED in Task A1)*
5. **`GAP-09` (Interactive Authentication & Headful Browser Fallback):** Enables human login and manual challenge solving when live anti-bot/CAPTCHA is encountered on Iranian storefronts. *(VERIFIED in Task A2)*
6. **`GAP-11` (Multi-Vendor Settings & Enable/Disable Subsystem):** Enables users to independently configure, enable/disable, and provide credentials for Lion, Javan, and RoboEq. *(VERIFIED in Task A2)*
7. **`GAP-13` (Multi-Vendor Cart Idempotency & Delta Synchronization):** Prevents duplicate item accumulation in vendor carts when users re-run procurement staging. *(VERIFIED in Task A4)*
8. **`GAP-17` (Universal Security Challenge & CAPTCHA Handler Subsystem):** Standardizes challenge interception (Cloudflare, reCAPTCHA, ArvanCloud, OTP) with human assistance. *(VERIFIED in Task A2)*

---

## 5. FORENSIC AUDIT OF THE 20 PRODUCT REQUIREMENTS (REQUIREMENTS A THROUGH U)

### Requirement A: Two Explicit Procurement Modes
- **Mode A (Database-Aware Procurement):**
  - Reconciles BOM components against `Inventory.xlsx`.
  - Computes net shortages: $Q_{\text{procure}} = \max(0, Q_{\text{BOM}} + Q_{\text{safety}} - Q_{\text{stock}})$.
  - Uses existing inventory database links and shortage logic.
- **Mode B (Direct BOM Procurement):**
  - Ingests BOM directly without requiring part numbers to exist in `Inventory.xlsx`.
  - Sets $Q_{\text{procure}} = Q_{\text{BOM}}$ directly.
  - Queries all enabled vendor catalogs to discover candidate components.
  - Database presence is **NOT a prerequisite** for ordering through Mode B.
- **Gap Status:** `GAP-01` (`PARTIALLY_IMPLEMENTED`). The bridge supports arbitrary items, but `BOMAuditor` and `BOMAuditWidget` are hardcoded to Mode A inventory matching.

### Requirement B & C: BOM-First Component Requirement Configuration & Brand Rules
- **Brand Selection UX:**
  - For each BOM component, the UI provides a brand selection field.
  - User can select `ANY` (mutually exclusive with specific brands).
  - Or select one or multiple specific brands (e.g., `STMicroelectronics`, `Texas Instruments`), which auto-deselects `ANY`.
- **Deterministic Sourcing Engine Constraint:**
  - If `ANY` is selected: Candidates from any manufacturer are eligible.
  - If an explicit brand set is selected: Candidates from unlisted manufacturers are marked `INCOMPATIBLE_MANUFACTURER` and disqualified, regardless of how cheap they are.
  - Sourcing logic will never choose a cheaper unapproved brand over an approved brand.
- **Gap Status:** `GAP-06` (`MISSING`).

### Requirement D & H: Multi-Candidate Sourcing & Decision Hierarchy
- **1-to-N Candidate Offer Topology:** A single BOM requirement produces $N$ candidate offers across multiple vendors and manufacturers.
- **Deterministic Decision Hierarchy (Hard Constraints over Price):**
  $$\text{Exact / Normalized MPN Match} \longrightarrow \text{Manufacturer / Brand Compliance} \longrightarrow \text{Package Identity} \longrightarrow \text{Footprint Identity} \longrightarrow \text{Technical Specs / Dimensions Completeness} \longrightarrow \text{Stock & Orderability} \longrightarrow \text{Volume Tiered Price / Cost Optimization}$$
- **Invariant:** Price is evaluated **ONLY** among candidates that have satisfied all preceding hard compatibility constraints. A cheaper candidate with a package mismatch or unknown required dimension is disqualified.
- **Gap Status:** `GAP-04` + `GAP-05` + `GAP-06` (`MISSING`).

### Requirement E & F: Technical Parameter Completeness & Physical Dimensions
- **Generic 4-State Evaluation Model:**
  1. `MATCH`: Parameter confirmed compatible with requirement.
  2. `MISMATCH`: Parameter confirmed incompatible (disqualifies candidate).
  3. `UNKNOWN_REQUIRED_PARAMETER`: Required parameter is unlisted or missing on vendor PDP. Candidate is flagged for human review and cannot be automatically ordered without user confirmation.
  4. `NOT_REQUIRED`: Parameter not specified in requirement.
- **Dimensional Compatibility:** Physical dimensions (length, width, height, lead pitch) are treated as independent hard constraints. Compatibility is never silently inferred.
- **Gap Status:** `GAP-05` (`MISSING`).

### Requirement G: Package and Footprint Independence (`OD-001` OPEN)
- **Invariant:** Package and Footprint are independent fields.
- **Taxonomy Rule:** No assumed package equivalences (e.g., DIP-8 != PDIP-8; SOIC-8 != SOP-8). `OD-001` remains strictly **OPEN**.
- **Normalization Rule:** Conservative normalization only: case folding, whitespace trimming, stripping `-` and `_`.
- **Gap Status:** `GAP-04` (`MISSING`).

### Requirement I & O: Vendor Management & Dynamic Enable/Disable
- **Dynamic Vendor Control:**
  - Settings UI allows enabling/disabling individual vendors (Lion, Javan, RoboEq).
  - Core orchestrator filters out disabled vendors: they are not queried, evaluated, or staged.
  - Adding future vendors requires zero changes to core procurement logic.
- **Gap Status:** `GAP-11` (`PARTIALLY_IMPLEMENTED`).

### Requirement J, K, L, M: Authentication, Challenge Framework & Headless Fallback
- **Unified Security Challenge Architecture (`GAP-17`):**
  - Common `ChallengeHandler` interface supporting: CAPTCHA, image CAPTCHA, text CAPTCHA, reCAPTCHA, hCaptcha, Turnstile, OTP, custom vendor challenge.
- **Headless to Headful Fallback Protocol (`GAP-09`):**
  - Normal execution runs headless.
  - If a security challenge or login requirement is detected, the adapter transitions to visible browser mode or presents the in-app challenge image dialog.
  - Exposes explicit lifecycle states: `WAITING_FOR_USER_AUTHENTICATION`, `WAITING_FOR_USER_CHALLENGE`, `AUTHENTICATION_FAILED`, `CHALLENGE_FAILED`, `AUTHENTICATED`, `READY_TO_RESUME`.
  - User completes the challenge $\to$ clicks Confirm $\to$ automation resumes with active session.
- **Gap Status:** `GAP-09` (`MISSING`) and `GAP-17` (`MISSING`).

### Requirement N: Direct Vendor / Direct MPN / Direct URL Workflows
- **Standalone Procurement:** Quick Order dialog allows entering an MPN or pasting a vendor product URL directly with a target quantity, bypassing `Inventory.xlsx` and BOM parsing entirely.
- **Gap Status:** `GAP-02` + `GAP-03` (`PARTIALLY_IMPLEMENTED`).

### Requirement P: Order Preview / Human Approval
- **Comprehensive Review Table (`GAP-07`):**
  - Displays: Requested Component, Selected MPN, Brand, Package, Footprint, Specs, Target Vendor, Vendor SKU, Unit Price, Effective Qty, MOQ, Step, Total Cost, Selection Rationale, Rejected Alternatives, Warnings.
  - User can expand alternatives and switch candidates with a single click before staging.
- **Gap Status:** `GAP-07` (`PARTIALLY_IMPLEMENTED`).

### Requirement Q: Exportable Procurement Reports
- **Multi-Vendor Deterministic Export Pipeline (`GAP-18`):**
  - Generates comprehensive PDF, CSV, and Excel procurement summary reports.
  - Documents exact parts, vendors, pricing, constraints, and audit trail for manual verification.
- **Gap Status:** `GAP-18` (`PARTIALLY_IMPLEMENTED`).

### Requirement R: Multi-Vendor Cart Idempotency ($\Delta Q$)
- **Cart Delta Synchronization Engine (`GAP-13`):**
  $$\Delta Q = \max\left(0, Q_{\text{target}} - Q_{\text{existing}}\right)$$
  - Query vendor cart $\to$ calculate $\Delta Q$ $\to$ stage only $\Delta Q$. If $\Delta Q == 0$, log as `CART_ALREADY_SATISFIED` with zero redundant additions.
- **Gap Status:** `GAP-13` (`MISSING`).

### Requirement S: Vendor Search Result Normalization
- **Candidate Contract:** `VendorProcurementCandidate` preserves original vendor values, PDP URLs, SKUs, and raw text while normalizing structured attributes without data fabrication.
- **Gap Status:** Verified in Phase 9 baseline (`core/procurement/models.py`).

### Requirement T: Altium Library Parameter Contract
- **Contract Schema (`DOC-OMNIX-ALTIUM-CONTRACT-001`):** Defines standard CAD columns (`Comment`, `Designator`, `Footprint`, `MPN`, `Manufacturer`, `Package`, `Tolerance`, `Voltage_Rating`, `Manufacturer_Rule`, `Approved_Manufacturers`).
- **Separation of Concerns:** Omnix implements the ingestion parser; external CAD library construction is **OUT OF SCOPE**.
- **Gap Status:** `GAP-16` (`PARTIALLY_IMPLEMENTED`).

### Requirement U: Excel Datastore Baseline
- **Datastore Baseline:** `Inventory.xlsx` is the active production datastore. No database migration during current completion tasks. Missing conceptual attributes are documented for future schema evolutions.
- **Gap Status:** Invariant preserved.

---

## 6. SUBSYSTEM BOUNDARY DECOMPOSITION

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               SUBSYSTEM BOUNDARY ARCHITECTURE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 [ 1. CORE MATCHING & CONSTRAINTS ]
 ├── GAP-04: Package & Footprint Independent Hard Constraints (OD-001 OPEN)
 ├── GAP-05: UNKNOWN_REQUIRED_PARAMETER State Enum & Generic Spec Validation Engine
 └── GAP-06: Manufacturer / Brand Constraint Engine (ANY vs Explicit Set)

 [ 2. SETTINGS, AUTHENTICATION & SECURITY CHALLENGES ]
 ├── GAP-11: Multi-Vendor Settings Dialog & Dynamic Enable/Disable Toggles
 ├── GAP-09: Interactive Authentication & Headful Browser Fallback State Machine
 ├── GAP-17: Universal Security Challenge & CAPTCHA Handler Subsystem
 └── GAP-10: Encrypted Keyring Credential Storage (Future / Post-Release)

 [ 3. PROCUREMENT MODES & CAD INGESTION ]
 ├── GAP-01: Dual Procurement Operating Modes (Mode A Database-Aware vs Mode B Direct BOM)
 └── GAP-16: Extended Altium Parameter Ingestion Parser (DOC-OMNIX-ALTIUM-CONTRACT-001)

 [ 4. RUNTIME EXECUTION & CART IDEMPOTENCY ]
 ├── GAP-13: Multi-Vendor Cart Idempotency & Delta Staging (ΔQ Synchronization)
 └── GAP-12: Finite State Machine Job Lifecycle (Future / Post-Release)

 [ 5. DESKTOP UI & STANDALONE WORKFLOWS ]
 ├── GAP-07: Multi-Candidate Alternative Comparison & Selection UI in OrderPreviewDialog
 ├── GAP-02: Direct MPN Quick Order Entry Dialog
 └── GAP-03: Direct URL Quick Order Entry Dialog

 [ 6. DETERMINISTIC REPORTING & AUDIT ]
 ├── GAP-18: Multi-Vendor Deterministic Export Pipeline (PDF / CSV / Excel)
 └── GAP-15: Append-Only Persistent Event Log (Future / Post-Release)

 [ 7. POST-RELEASE EVOLUTION & PERSISTENCE ]
 ├── GAP-08: Split-Vendor Line Item Sourcing (Gated on OD-002)
 └── GAP-14: Embedded ACID Relational Persistence (SQLite Migration — Gated on OD-003)
```

---

## 7. TOPOLOGICAL DEPENDENCY DAG

```
 [ LAYER 0: ENUMS & CONTRACT DEFINITIONS ]
 ├── GAP-05: UNKNOWN_REQUIRED_PARAMETER Enum & EvaluationState
 └── GAP-16: Altium Component Parameter Contract Schema
       │
       ▼
 [ LAYER 1: CORE MATCHING & CONSTRAINTS ENGINE ]
 ├── GAP-04: Package & Footprint Independent Constraint Check (OD-001 OPEN)
 └── GAP-06: Manufacturer / Brand Constraint Engine (ANY vs Explicit Set)
       │
       ▼
 [ LAYER 2: SETTINGS, AUTHENTICATION & CHALLENGE RECOVERY ] (Can proceed in parallel with Layer 1)
 ├── GAP-11: Multi-Vendor Settings Dialog & Dynamic Enable/Disable Subsystem
 ├── GAP-17: Universal Security Challenge & CAPTCHA Handler Subsystem
 └── GAP-09: Interactive Authentication & Headful Browser Fallback State Machine
       │
       ▼
 [ LAYER 3: WORKFLOW MODES & CAD INGESTION ]
 ├── GAP-01: Dual Procurement Modes (Mode A Database-Aware vs Mode B Direct BOM)
 └── GAP-16: Extended Altium Parameter Ingestion Parser
       │
       ▼
 [ LAYER 4: CART RUNTIME IDEMPOTENCY ]
 └── GAP-13: Multi-Vendor Cart Idempotency & Delta Staging (ΔQ Synchronization)
       │
       ▼
 [ LAYER 5: DESKTOP UI WORKFLOWS & PRESENTATION ]
 ├── GAP-07: Multi-Candidate Comparison & Alternative Selection in OrderPreviewDialog
 ├── GAP-02: Direct MPN Quick Order Dialog
 └── GAP-03: Direct URL Quick Order Dialog
       │
       ▼
 [ LAYER 6: DETERMINISTIC REPORTING & AUDIT ]
 └── GAP-18: Multi-Vendor Deterministic Export Pipeline (PDF / CSV / Excel)
       │
       ▼
 [ LAYER 7: RELEASE HARDENING & PACKAGING (PHASE 10) ]
 └── End-to-End Live Multi-Vendor Desktop Validation & Nuitka Binary Compilation
```

---

## 8. CRITICAL PRODUCT VERIFICATION SCENARIOS

| Scenario ID | Test Scenario | Expected Product Behavior | Current Code Behavior | Deficiency / Gap |
|---|---|---|---|---|
| **SCN-A** | **Multi-Brand Same MPN** (ST vs TI vs Unbranded) | Preserve all candidates, evaluate package, enforce brand rules (`ANY` vs approved set), let user choose | Picks cheapest unbranded without checking package or brand | `GAP-04`, `GAP-06`, `GAP-07` |
| **SCN-B** | **Required Parameter Unknown** on Vendor PDP | Flag as `UNKNOWN_REQUIRED_PARAMETER`, alert user in UI, block auto-ordering | Silently treats missing parameter as valid | `GAP-05` |
| **SCN-C** | **Human Login & Challenge Recovery** (CAPTCHA/OTP) | Switch to headful browser or show image dialog, prompt user, verify session, resume | Headless fails immediately with `AuthResult(False)` | `GAP-09`, `GAP-17` |
| **SCN-D** | **Disabled Vendor Sourcing** | Disabled vendor is excluded from catalog queries, candidate evaluation, and cart staging | All registered vendors are queried unconditionally | `GAP-11` |
| **SCN-E** | **Mode B Direct BOM Procurement** | Upload BOM, procure directly from vendors without requiring components in `Inventory.xlsx` | Forces lookup in `Inventory.xlsx`; marks non-DB items unorderable | `GAP-01` |
| **SCN-F** | **Direct MPN Quick Order** | Enter MPN and quantity in GUI, discover candidates across enabled vendors, preview, stage | Core supports search; no GUI dialog exists to input MPN | `GAP-02` |
| **SCN-G** | **Direct URL Quick Order** | Paste vendor product URL and quantity, inspect PDP, evaluate constraints, stage | Core resolves URL; no GUI dialog exists to paste URL | `GAP-03` |
| **SCN-H** | **Duplicate Staging Execution** (Accidental re-run) | Inspect cart, calculate $\Delta Q = \max(0, Q_{\text{target}} - Q_{\text{existing}})$, stage only $\Delta Q$ | Adds full quantity again, doubling cart items | `GAP-13` |
| **SCN-I** | **Export Procurement Report** | Export complete multi-vendor order summary to PDF, CSV, and Excel | Only exports Lion-specific shortage table | `GAP-18` |
| **SCN-J** | **Package Mismatch Rejection** (DIP-8 vs SOP-8) | Reject candidate as `INCOMPATIBLE_PACKAGE` even if price is substantially cheaper | Selects cheapest candidate ignoring package | `GAP-04` |
| **SCN-K** | **Physical Dimensions Mismatch** | Reject candidate as `INCOMPATIBLE_DIMENSIONS` or flag as `UNKNOWN_REQUIRED_PARAMETER` | Ignores dimensions entirely | `GAP-05` |

---

## 9. RECOMMENDED IMPLEMENTATION TASK SEQUENCE

```mermaid
flowchart TD
    A1["TASK-A1: Core Matching, Package/Footprint Constraints & Brand Rules (GAP-04, GAP-05, GAP-06)"] --> A2["TASK-A2: Multi-Vendor Settings & Universal Security Challenge Handler (GAP-11, GAP-17, GAP-09)"]
    A2 --> A3["TASK-A3: Dual Procurement Modes & Altium Parameter Ingestion (GAP-01, GAP-16)"]
    A3 --> A4["TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization (GAP-13)"]
    A4 --> A5["TASK-A5: Desktop UI Workflows & Multi-Candidate Preview (GAP-07, GAP-02, GAP-03)"]
    A5 --> A6["TASK-A6: Multi-Vendor Deterministic Export Pipeline (GAP-18)"]
    A6 --> A7["TASK-A7: Phase 10 Release Packaging, Windows Hardening & Nuitka Compilation"]
```

### TASK-A1: Core Technical Matching, Package/Footprint Constraints & Brand Rules
- **Target GAPs:** `GAP-04`, `GAP-05`, `GAP-06`
- **Scope:**
  1. Add `EvaluationState` enum (`ELIGIBLE`, `INCOMPATIBLE_MPN`, `INCOMPATIBLE_PACKAGE`, `INCOMPATIBLE_FOOTPRINT`, `INCOMPATIBLE_MANUFACTURER`, `INCOMPATIBLE_DIMENSIONS`, `UNKNOWN_REQUIRED_PARAMETER`, `UNORDERABLE`) to `core/procurement/models.py`.
  2. Implement independent package and footprint verification in `UniversalProcurementOrchestrator` using conservative normalized string matching (`OD-001` OPEN).
  3. Implement brand constraint validator (`ANY` vs explicit allowed brand set).
  4. Implement `UNKNOWN_REQUIRED_PARAMETER` flagging for unlisted specs and dimensions.
- **Datastore:** Operates entirely within the existing Excel datastore baseline.
- **Dependencies:** None (Pure domain & core matching logic).

### TASK-A2: Multi-Vendor Settings, Universal Challenge Handler & Interactive Authentication
- **Target GAPs:** `GAP-11`, `GAP-17`, `GAP-09`
- **Scope:**
  1. Expand `SettingsDialog` and `SettingsManager` to support tabbed/grouped configuration for Lion, Javan, and RoboEq (credentials, enable/disable toggles, timeouts).
  2. Create `core/procurement/challenge_handler.py` (`ChallengeHandler` abstraction supporting CAPTCHA, image CAPTCHA, Turnstile, OTP).
  3. Implement interactive headful browser fallback and user confirmation modal in adapters and UI.
- **Dependencies:** None.

### TASK-A3: Dual Procurement Modes & Altium Parameter Ingestion
- **Target GAPs:** `GAP-01`, `GAP-16`
- **Scope:**
  1. Add explicit Procurement Mode selector (Mode A: Database-Aware vs Mode B: Direct BOM Sourcing) to `BOMAuditWidget`.
  2. Implement Mode B sourcing workflow querying all enabled vendors directly from BOM.
  3. Extend `BOMAuditor` to ingest extended Altium Parameter Contract columns (`DOC-OMNIX-ALTIUM-CONTRACT-001`).
- **Dependencies:** `TASK-A1`.

### TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization
- **Target GAPs:** `GAP-13`
- **Scope:**
  1. Implement cart delta checking ($\Delta Q = \max(0, Q_{\text{target}} - Q_{\text{existing}})$) across all vendor adapters.
  2. Prevent duplicate item accumulation upon re-running batch procurement staging.
- **Dependencies:** `TASK-A2`.

### TASK-A5: Desktop UI Workflows & Multi-Candidate Preview
- **Target GAPs:** `GAP-07`, `GAP-02`, `GAP-03`
- **Scope:**
  1. Expand `OrderPreviewDialog` to display multi-candidate alternative offers, selection rationales, and candidate switching.
  2. Create `QuickOrderDialog` for standalone Direct MPN and Direct URL procurement.
- **Dependencies:** `TASK-A1`, `TASK-A3`.

### TASK-A6: Multi-Vendor Deterministic Export Pipeline
- **Target GAPs:** `GAP-18`
- **Status:** `COMPLETED_AND_VERIFIED` (331 tests passing total, +15 new tests).
- **Scope Accomplished:** Side-effect-free, deterministic export pipeline in PDF, CSV, and XLSX formats; complete candidate decision audit trails (`DISCOVERED`, `ELIGIBLE`, `REJECTED`, `SELECTED_BY_USER`, `ACTUALLY_STAGED`); Pre-Order vs Post-Staging separation; Persian/RTL text direction handling; pure UI export integration.
- **Dependencies:** `TASK-A3`, `TASK-A5`.

### TASK-A7: Phase 10 Release Packaging & Nuitka Hardening
- **Target Scope:** End-to-end live multi-vendor testing on Windows host and production Nuitka binary compilation.
- **Dependencies:** `TASK-A1` through `TASK-A6`.

---

## 10. EXACT FIRST IMPLEMENTATION TASK

```
================================================================================
EXACT FIRST IMPLEMENTATION TASK:
TASK-A1: Core Technical Matching, Package/Footprint Constraints & Brand Rules
         (Target GAPs: GAP-04, GAP-05, GAP-06)
================================================================================
```

### Technical Justification:
1. **Zero External Dependencies:** Depends solely on internal core models (`core/procurement/models.py` and `core/procurement/orchestrator.py`).
2. **Foundational Hardware Safety:** Eliminates the critical risk of purchasing physically incompatible SMD/through-hole parts (e.g. DIP vs SOP) or unapproved substitute brands.
3. **100% Mathematically Specified:** String normalizations, independent package/footprint checks, `ANY` vs explicit brand sets, and `UNKNOWN_REQUIRED_PARAMETER` semantics are fully defined without open ambiguities.
4. **Preserves Production Datastore:** Operates entirely within `Inventory.xlsx` and `ExcelDataLoader` with zero database migrations.

---

## 11. FINAL PRODUCT REQUIREMENT FORENSIC AUDIT SUMMARY

```
================================================================================
FINAL PRODUCT REQUIREMENT FORENSIC AUDIT SANITY CHECK
================================================================================
Repository:              D:\management-elec\autom\atom
Branch:                  Auto
Working Tree:            Clean
Automated Tests:         331 / 331 PASSED
Site Map Validation:     Lion (10/10), Javan (10/10), RoboEq (10/10) — ALL PASS (30/30)
Total GAPs in Registry:  18 GAPs (GAP-01 through GAP-18)
Release-Blocking GAPs:   8 GAPs (GAP-01, GAP-04, GAP-05, GAP-06, GAP-09, GAP-11, GAP-13, GAP-17 — ALL 8 VERIFIED)
Verified GAPs:           13 GAPs (GAP-01, GAP-02, GAP-03, GAP-04, GAP-05, GAP-06, GAP-07, GAP-09, GAP-11, GAP-13, GAP-16, GAP-17, GAP-18)
Active Next Task:        TASK-A7 (Phase 10 Release Packaging & Nuitka Hardening)
Open Decisions:          3 (OD-001: Package Taxonomy, OD-002: Sourcing Metric, OD-003: Safety Stock)
Out-of-Scope Items:      3 (OOS-001: Altium Library, OOS-002: Auto-Payment, OOS-003: Runtime AI/LLM)
Updated Document:        docs/PRODUCT/MASTER_PRODUCT_COMPLETION_GAP_ANALYSIS.md
================================================================================
```
