# CANONICAL GAP REGISTRY & VERIFICATION MATRIX
## Omnix — Deterministic Multi-Vendor Electronics Procurement Platform

**Document Reference:** `DOC-OMNIX-REGISTRY-001`  
**Version:** `1.0.0-CANONICAL`  
**Status:** Authoritative Single Source of Truth for Project GAPs  
**Repository:** `D:\management-elec\autom\atom`  
**Branch:** `Auto`  
**Automated Tests:** 241 / 241 PASSED  
**Discovery Graph Audits:** Lion (`10/10`), Javan (`10/10`), RoboEq (`10/10`) — ALL 30/30 PASS  
**Phase 9 Certification Baseline:** `PHASE_9_FINAL_REVIEW_PASS`  
**Task A1 Status:** `COMPLETED_AND_VERIFIED`  
**Task A2 Status:** `COMPLETED_AND_VERIFIED`  
**Audit Date:** September 17, 2026  

---

## 1. EXECUTIVE SUMMARY & GOVERNING PRINCIPLES

This document establishes the **single, definitive Canonical GAP Registry** for the Omnix project. It replaces all prior ad-hoc or drifting numbering schemes and establishes an authoritative, forensically verified baseline across documentation, source code, and automated tests.

### 1.1 Controlled Status Vocabulary
Every requirement and gap in Omnix is classified under one of the following strict lifecycle states:

| Status | Definition |
|---|---|
| **`VERIFIED`** | Code is implemented, tested with unit/contract tests, and validated in test suite. |
| **`IMPLEMENTED`** | Code is fully written and integrated, awaiting full formal certification. |
| **`PARTIAL`** | Subsystem is partially implemented (e.g. Core logic present, UI missing; or Mode A working, Mode B unwritten). |
| **`MISSING`** | Subsystem or feature is completely unwritten in the current codebase. |
| **`DEFERRED`** | Architectural evolution item explicitly deferred to post-release milestones (e.g., gated on Open Decisions). |
| **`OUT_OF_SCOPE`** | Feature or capability explicitly excluded from Omnix boundaries. |

### 1.2 Core Architectural Invariants (Unchanged)
1. **Production Datastore Baseline:** `Inventory.xlsx` is the active, verified production component and inventory datastore. Direct file access is managed via `ExcelDataLoader` and `BOMAuditor`.
2. **Zero Near-Term Database Migration:** `GAP-14` (SQLite ACID repository migration) is explicitly deferred to post-release evolution. No SQLite code or schema migrations are allowed during Tasks A1 through A7.
3. **Open Decision `OD-001` Preserved:** Package taxonomy remains **OPEN**. Conservative string normalization only (case-folding, whitespace, stripping `-` and `_`). Zero assumed broad package family equivalences (e.g., `DIP-8` != `PDIP-8`; `SOIC-8` != `SOP-8`).
4. **Strict Determinism:** 100% deterministic rule-based evaluation. Zero fuzzy guessing, zero LLM/AI runtime decision loops (`OOS-003`).
5. **Human-in-the-Loop Checkout:** Procurement automates up to the verified vendor cart staging. Final financial payment is strictly human-executed (`OOS-002`).

---

## 2. CANONICAL MASTER GAP REGISTRY (18 GAPs)

The table below catalogs the complete set of **exactly 18 canonical GAPs** governing Omnix completion:

| ID | Title | Domain / Layer | Current Code State | Blocking? | Task Target | Dependencies | Status |
|---|---|---|---|:---:|:---:|---|:---:|
| **`GAP-01`** | Dual Procurement Modes (Mode A vs Mode B) | `UI / WORKFLOW` | Inventory subtraction hardcoded in `bom_auditor.py`; Mode B direct catalog BOM search missing. | **YES** | `TASK-A3` | `GAP-04`, `GAP-06` | `PARTIAL` |
| **`GAP-02`** | Direct MPN Procurement Quick Order Dialog | `UI` | Search supported in Core; no standalone desktop GUI dialog. | No | `TASK-A5` | `GAP-04`, `GAP-07` | `PARTIAL` |
| **`GAP-03`** | Direct URL Procurement Quick Order Dialog | `UI` | URL routing supported in Core; no standalone desktop GUI dialog. | No | `TASK-A5` | `GAP-13` | `PARTIAL` |
| **`GAP-04`** | Package & Footprint Hard Constraints (`OD-001` OPEN) | `CORE_ENGINE` | Fully implemented in Core models and orchestrator with conservative normalization. | **YES** | `TASK-A1` | None | `VERIFIED` |
| **`GAP-05`** | `UNKNOWN_REQUIRED_PARAMETER` & Spec Engine | `CORE_ENGINE` | Typed `EvaluationState` enum, 4-state spec engine, and dimension validator implemented. | **YES** | `TASK-A1` | None | `VERIFIED` |
| **`GAP-06`** | Manufacturer / Brand Constraint Engine | `CORE_ENGINE` | `ANY` vs explicit approved manufacturer list filtering implemented in Core. | **YES** | `TASK-A1` | `GAP-05` | `VERIFIED` |
| **`GAP-07`** | Multi-Candidate Alternative Selection UI | `UI` | Core evaluates candidate list; `OrderPreviewDialog` renders flat list without candidate override. | No | `TASK-A5` | `GAP-04`, `GAP-05`, `GAP-06` | `PARTIAL` |
| **`GAP-08`** | Split-Vendor Line Item Sourcing Allocation | `CORE_ENGINE` | Line items allocated to single vendor; split sourcing across multiple vendors deferred. | No | Post-Release | `OD-002` | `DEFERRED` |
| **`GAP-09`** | Interactive Authentication & Headful Fallback | `AUTHENTICATION` | Session promotion with explicit cookie transfer qualification and adapter challenge escalation implemented. | **YES** | `TASK-A2` | `GAP-11`, `GAP-17` | `VERIFIED` |
| **`GAP-10`** | Encrypted Keyring Credential Storage | `SECURITY` | Plaintext JSON in `settings.json`; OS keyring encryption deferred. | No | Post-Release | None | `DEFERRED` |
| **`GAP-11`** | Multi-Vendor Settings & Dynamic Enable/Disable | `UI / SETTINGS` | Multi-vendor settings, isolated schema, dynamic registry filtering, and 4-tab UI dialog implemented. | **YES** | `TASK-A2` | None | `VERIFIED` |
| **`GAP-12`** | Finite State Machine Job Lifecycle Engine | `RUNTIME` | Coarse string statuses (`"RESOLVED"`); explicit lifecycle FSM deferred. | No | Post-Release | None | `DEFERRED` |
| **`GAP-13`** | Multi-Vendor Cart Idempotency & Delta Sync | `RUNTIME` | Unconditional cart addition; pre-inspection and delta staging missing. | **YES** | `TASK-A4` | None | `MISSING` |
| **`GAP-14`** | Embedded ACID Relational Persistence (SQLite) | `PERSISTENCE` | `Inventory.xlsx` production datastore active; SQLite migration deferred. | No | Post-Release | `OD-003` | `DEFERRED` |
| **`GAP-15`** | Append-Only Persistent Audit Trail Event Log | `AUDIT` | Ephemeral stdout logging; append-only event store deferred. | No | Post-Release | `GAP-14` | `DEFERRED` |
| **`GAP-16`** | Extended Altium Parameter Ingestion Parser | `CAD_INTEGRATION` | Ingests 7 standard BOM columns; extended 20-parameter contract ingestion missing. | No | `TASK-A3` | None | `PARTIAL` |
| **`GAP-17`** | Universal Security Challenge / CAPTCHA Handler | `SECURITY / AUTH` | Unified `IChallengeHandler` subsystem with 8 challenge types, callback handler, and Qt dialog implemented. | **YES** | `TASK-A2` | None | `VERIFIED` |
| **`GAP-18`** | Multi-Vendor Deterministic Export Pipeline | `REPORTING` | Basic Lion shortage export; multi-vendor PDF/CSV/XLSX export pipeline missing. | No | `TASK-A6` | `GAP-01`, `GAP-07` | `PARTIAL` |

---

## 3. RELEASE-BLOCKING GAP CLASSIFICATION

Forensic verification confirms that **EXACTLY 8 GAPS** are strictly classified as **Release-Blocking (`BLOCKS_PRODUCT_COMPLETION`)**:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   8 RELEASE-BLOCKING GAPS                                        │
├──────────┬─────────────────────────────────────────────┬──────────────┬──────────────────────────┤
│ GAP ID   │ Title                                       │ Target Task  │ Current Status           │
├──────────┼─────────────────────────────────────────────┼──────────────┼──────────────────────────┤
│ GAP-01   │ Dual Procurement Modes (Mode A vs Mode B)   │ TASK-A3      │ PARTIAL                  │
│ GAP-04   │ Package & Footprint Hard Constraints        │ TASK-A1      │ VERIFIED (Core Verified) │
│ GAP-05   │ UNKNOWN_REQUIRED_PARAMETER & Spec Engine    │ TASK-A1      │ VERIFIED (Core Verified) │
│ GAP-06   │ Manufacturer / Brand Constraint Engine      │ TASK-A1      │ VERIFIED (Core Verified) │
│ GAP-09   │ Interactive Auth & Headful Fallback         │ TASK-A2      │ VERIFIED (Auth Verified) │
│ GAP-11   │ Multi-Vendor Settings & Enable/Disable      │ TASK-A2      │ VERIFIED (Settings Ver.) │
│ GAP-13   │ Multi-Vendor Cart Idempotency & Delta Sync  │ TASK-A4      │ MISSING                  │
│ GAP-17   │ Universal Security Challenge Handler        │ TASK-A2      │ VERIFIED (Handler Ver.)  │
└──────────┴─────────────────────────────────────────────┴──────────────┴──────────────────────────┘
```

---

## 4. TASK-A1 & TASK-A2 IMPLEMENTATION & VERIFICATION EVIDENCE

### 4.1 Task A1 Verification Evidence (GAP-04, GAP-05, GAP-06)
- **`GAP-04`**: `normalize_constraint_string()`, independent package/footprint matching ([`core/procurement/models.py`](file:///d:/management-elec/autom/atom/core/procurement/models.py), [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py)).
- **`GAP-05`**: `EvaluationState` enum, 4-state spec engine, dimension validator, `UNKNOWN_REQUIRED_PARAMETER` exclusion ([`core/procurement/models.py`](file:///d:/management-elec/autom/atom/core/procurement/models.py), [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py)).
- **`GAP-06`**: `ANY` vs approved manufacturer set filtering ([`core/procurement/models.py`](file:///d:/management-elec/autom/atom/core/procurement/models.py), [`core/procurement/orchestrator.py`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py)).

### 4.2 Task A2 Verification Evidence (GAP-11, GAP-17, GAP-09)
| GAP ID | Implemented Features | Source Code Location | Forensic Verification |
|---|---|---|---|
| **`GAP-11`** | • `VendorSettings` dataclass with masked `__repr__`<br>• `SettingsManager` multi-vendor storage & legacy synchronization<br>• `VendorRegistry` dynamic filtering (`is_vendor_enabled`)<br>• `UniversalProcurementOrchestrator` bypassed disabled vendors<br>• `SettingsDialog` 4-tab UI with enable toggles & credentials | [`core/models.py:27-58`](file:///d:/management-elec/autom/atom/core/models.py#L27-L58)<br>[`settings_manager.py:30-140`](file:///d:/management-elec/autom/atom/settings_manager.py#L30-L140)<br>[`core/procurement/registry.py:80-120`](file:///d:/management-elec/autom/atom/core/procurement/registry.py#L80-L120)<br>[`core/procurement/orchestrator.py:90-110`](file:///d:/management-elec/autom/atom/core/procurement/orchestrator.py#L90-L110)<br>[`ui/dialogs/settings_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/settings_dialog.py) | Passed 11 dedicated multi-vendor settings tests in [`tests/test_multi_vendor_settings.py`](file:///d:/management-elec/autom/atom/tests/test_multi_vendor_settings.py). |
| **`GAP-17`** | • `ChallengeType` enum (8 types: Turnstile, reCAPTCHA, hCaptcha, Image CAPTCHA, OTP, SMS, Password, Custom)<br>• `ChallengeState` enum (Solved, Cancelled, TimedOut, Unsupported, Failed)<br>• `ChallengeContext` & `ChallengeResult` dataclasses<br>• `IChallengeHandler` interface & `CallbackChallengeHandler`<br>• `UniversalChallengeDialog` & `QtChallengeHandler` | [`core/procurement/challenge_handler.py`](file:///d:/management-elec/autom/atom/core/procurement/challenge_handler.py)<br>[`ui/dialogs/challenge_dialog.py`](file:///d:/management-elec/autom/atom/ui/dialogs/challenge_dialog.py) | Passed 12 dedicated challenge handler tests in [`tests/test_challenge_handler.py`](file:///d:/management-elec/autom/atom/tests/test_challenge_handler.py). |
| **`GAP-09`** | • Headless-to-headful promotion (`promote_to_headful`)<br>• Qualified session continuity (`SessionContinuityMode`)<br>• Cookie capture, headless teardown, headful recreation, cookie re-application<br>• `IVendorAdapter.authenticate(credentials, challenge_handler)` integration across Lion, Javan, and RoboEq | [`vendors/lion/session.py:100-145`](file:///d:/management-elec/autom/atom/vendors/lion/session.py#L100-L145)<br>[`vendors/javan/session.py:100-145`](file:///d:/management-elec/autom/atom/vendors/javan/session.py#L100-L145)<br>[`vendors/roboeq/session.py:100-145`](file:///d:/management-elec/autom/atom/vendors/roboeq/session.py#L100-L145)<br>[`vendors/lion/adapter.py:540-630`](file:///d:/management-elec/autom/atom/vendors/lion/adapter.py#L540-L630)<br>[`vendors/javan/adapter.py:570-710`](file:///d:/management-elec/autom/atom/vendors/javan/adapter.py#L570-L710)<br>[`vendors/roboeq/adapter.py:440-520`](file:///d:/management-elec/autom/atom/vendors/roboeq/adapter.py#L440-L520) | Passed 10 dedicated interactive auth and session promotion tests in [`tests/test_interactive_authentication.py`](file:///d:/management-elec/autom/atom/tests/test_interactive_authentication.py). |

---

## 5. RECONCILED IMPLEMENTATION ROADMAP (TASKS A1 THROUGH A7)

```mermaid
flowchart TD
    A1["TASK-A1 [VERIFIED]: Core Technical Matching, Package/Footprint & Brand Rules (GAP-04, GAP-05, GAP-06)"]
    A2["TASK-A2 [VERIFIED]: Multi-Vendor Settings, Universal Challenge Handler & Interactive Auth (GAP-11, GAP-17, GAP-09)"]
    A3["TASK-A3 [NEXT]: Dual Procurement Modes & Altium Parameter Ingestion (GAP-01, GAP-16)"]
    A4["TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization (GAP-13)"]
    A5["TASK-A5: Desktop UI Workflows & Multi-Candidate Preview (GAP-07, GAP-02, GAP-03)"]
    A6["TASK-A6: Multi-Vendor Deterministic Export Pipeline (GAP-18)"]
    A7["TASK-A7: Phase 10 Release Packaging, Windows Hardening & Nuitka Compilation"]

    A1 --> A2
    A2 --> A3
    A3 --> A4
    A4 --> A5
    A5 --> A6
    A6 --> A7
```

### Task Definitions & Target Scopes:

#### TASK-A1: Core Technical Matching, Package/Footprint Constraints & Brand Rules
- **Target GAPs:** `GAP-04`, `GAP-05`, `GAP-06`
- **Status:** `COMPLETED_AND_VERIFIED` (208 tests passing baseline).

#### TASK-A2: Multi-Vendor Settings, Universal Challenge Handler & Interactive Auth
- **Target GAPs:** `GAP-11`, `GAP-17`, `GAP-09`
- **Status:** `COMPLETED_AND_VERIFIED` (241 tests passing total, +33 new tests).
- **Scope Accomplished:** Multi-vendor isolated settings schema, dynamic vendor enable/disable in `VendorRegistry` & `UniversalProcurementOrchestrator`, `IChallengeHandler` subsystem with 8 challenge types and UI dialog, session promotion (`SessionContinuityMode`) with cookie transfer, and adapter challenge escalation for Lion, Javan, and RoboEq.

#### TASK-A3: Dual Procurement Modes & Altium Parameter Ingestion
- **Target GAPs:** `GAP-01`, `GAP-16`
- **Scope:**
  1. Add Mode A (Database-Aware) vs Mode B (Direct BOM Sourcing) toggle to `BOMAuditWidget`.
  2. Implement Mode B sourcing workflow querying all enabled vendors directly from BOM.
  3. Extend `BOMAuditor` to ingest extended Altium Parameter Contract columns (`DOC-OMNIX-ALTIUM-CONTRACT-001`).

#### TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization
- **Target GAPs:** `GAP-13`
- **Scope:**
  1. Cart pre-inspection via `inspect_cart()` across all vendor adapters.
  2. Calculate missing delta: $\Delta Q = \max(0, Q_{\text{target}} - Q_{\text{staged}})$.
  3. Stage only $\Delta Q$ units (0 units added if already satisfied).

#### TASK-A5: Desktop UI Workflows & Multi-Candidate Preview
- **Target GAPs:** `GAP-07`, `GAP-02`, `GAP-03`
- **Scope:**
  1. Expand `OrderPreviewDialog` to display multi-candidate alternative offers, selection rationales, and candidate switching.
  2. Create `QuickOrderDialog` for standalone Direct MPN and Direct URL procurement.

#### TASK-A6: Multi-Vendor Deterministic Export Pipeline
- **Target GAPs:** `GAP-18`
- **Scope:**
  1. Implement multi-vendor procurement report generation in PDF, CSV, and Excel formats.
  2. Include complete decision audit trail, pricing breakdown, and unverified parameter warnings.

#### TASK-A7: Phase 10 Release Packaging & Nuitka Hardening
- **Target Scope:** End-to-end live multi-vendor validation on Windows host, application-level packaging, and production Nuitka binary compilation.

---

## 6. OPEN ARCHITECTURAL DECISIONS & OUT-OF-SCOPE BOUNDARIES

### 6.1 Open Architectural Decisions
- **`OD-001` (Package Taxonomy Standardization):** Standardizing package strings (`SOIC-8` vs `SOP-8`) vs IPC-7351B standards. Preserved **OPEN**. Conservative string normalization only.
- **`OD-002` (Multi-Vendor Split-Sourcing Allocation Metric):** Optimization function for dividing line items across vendors (cost vs shipments vs delivery). Preserved **OPEN**; `GAP-08` deferred.
- **`OD-003` (Safety Stock & Datastore Migration Strategy):** Formulas for safety stock in Mode A and SQLite migration architecture. Preserved **OPEN**; `GAP-14` deferred.

### 6.2 Out-of-Scope Boundaries
- **`OOS-001` (External Altium CAD Library DB Creation):** External Altium library construction (symbols, footprints, 3D models) is **OUT OF SCOPE**. Ingestion of the parameter contract (`GAP-16`) is **IN SCOPE**.
- **`OOS-002` (Automated Payment & Final Financial Checkout):** Payment gateway completion (CVV2, OTP, Shetab) is strictly retained as a human manual step.
- **`OOS-003` (Autonomous AI/LLM Purchasing Agents):** Non-deterministic generative loops are prohibited in production runtime. Omnix is 100% deterministic rule-based.

---

## 7. CANONICAL AUDIT SUMMARY

```
================================================================================
CANONICAL GAP REGISTRY AUDIT SUMMARY
================================================================================
Document Reference:      DOC-OMNIX-REGISTRY-001
Version:                 1.0.0-CANONICAL
Repository:              D:\management-elec\autom\atom
Branch:                  Auto
Automated Test Suite:    208 / 208 PASSED (7.40s)
Site Map Graph Audits:   Lion (10/10), Javan (10/10), RoboEq (10/10) — 30/30 PASS
Total Registered GAPs:   18 GAPs (GAP-01 through GAP-18)
Release-Blocking GAPs:   8 GAPs (GAP-01, GAP-04, GAP-05, GAP-06, GAP-09, GAP-11, GAP-13, GAP-17)
Verified GAPs in Core:   3 GAPs (GAP-04, GAP-05, GAP-06 — Completed in Task A1)
Next Task for Execution: TASK-A2 (GAP-11, GAP-17, GAP-09)
Datastore Baseline:      Inventory.xlsx (Production Datastore Preserved)
SQLite Status:           DEFERRED (GAP-14 gated on OD-003)
================================================================================
```
