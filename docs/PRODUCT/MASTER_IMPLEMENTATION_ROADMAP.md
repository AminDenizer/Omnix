# MASTER ARCHITECTURE GAP AUDIT & IMPLEMENTATION ROADMAP
## Omnix — Deterministic Multi-Vendor Electronics Procurement Platform

**Document Reference:** `DOC-OMNIX-ROADMAP-001`  
**Version:** `2.0.0-RECONCILED`  
**Status:** Approved Master Architecture Gap Audit & Authoritative Implementation Roadmap  
**Repository:** `D:\management-elec\autom\atom`  
**Branch:** `Auto`  
**Automated Tests:** 331 / 331 PASSED  
**Discovery Graph Audits:** Lion (`10/10`), Javan (`10/10`), RoboEq (`10/10`) — ALL 30/30 PASS  
**Phase 9 Baseline:** `PHASE_9_FINAL_REVIEW_PASS`  
**Canonical Registry Reference:** `docs/PRODUCT/CANONICAL_GAP_REGISTRY.md` (`DOC-OMNIX-REGISTRY-001`)  
**Task A1 Status:** `COMPLETED_AND_VERIFIED`  
**Task A2 Status:** `COMPLETED_AND_VERIFIED`  
**Task A3 Status:** `COMPLETED_AND_VERIFIED`  
**Task A4 Status:** `COMPLETED_AND_VERIFIED`  
**Task A5 Status:** `COMPLETED_AND_VERIFIED`  
**Task A6 Status:** `COMPLETED_AND_VERIFIED`  
**Audit Date:** September 20, 2026  

---

## 1. EXECUTIVE SUMMARY & POSTURE

This document establishes the authoritative **Master Implementation Roadmap** for transforming Omnix into a production-grade, deterministic multi-vendor electronics procurement platform.

### 1.1 Canonical Alignment
All GAP definitions, numbering schemes, classifications, and task allocations in this roadmap are strictly governed by and reconciled with [`docs/PRODUCT/CANONICAL_GAP_REGISTRY.md`](file:///d:/management-elec/autom/atom/docs/PRODUCT/CANONICAL_GAP_REGISTRY.md) and [`docs/PRODUCT/MASTER_PRODUCT_COMPLETION_GAP_ANALYSIS.md`](file:///d:/management-elec/autom/atom/docs/PRODUCT/MASTER_PRODUCT_COMPLETION_GAP_ANALYSIS.md) (v3.0.0-FINAL-FORENSIC-EXPANSION).

### 1.2 Authoritative Architectural Facts
1. **Production Datastore Baseline:** `Inventory.xlsx` is the active, authoritative component and inventory datastore on disk. `ExcelDataLoader` and `BOMAuditor` are the active data access layer.
2. **Current Sourcing Data Pipeline:**
   $$\text{Inventory.xlsx} \longrightarrow \text{ExcelDataLoader / BOMAuditor} \longrightarrow \text{ProcurementBridge} \longrightarrow \text{ProcurementRequest} \longrightarrow \text{UniversalProcurementOrchestrator} \longrightarrow \text{Vendor Adapters} \longrightarrow \text{Storefront Shopping Cart}$$
3. **Zero Database Migration Invariant:** `GAP-14` (SQLite ACID Repository Layer) is an open architectural evolution path and is **DEFERRED** to post-release milestones. The current Excel-based data pipeline is preserved without modification or disruption.
4. **Tasks A1 through A6 Completed and Verified:** `GAP-04`, `GAP-05`, `GAP-06` (Task A1), `GAP-11`, `GAP-17`, `GAP-09` (Task A2), `GAP-01`, `GAP-16` (Task A3), `GAP-13` (Task A4), `GAP-07`, `GAP-02`, `GAP-03` (Task A5), and `GAP-18` (Task A6) are fully implemented and verified with 331 passing automated tests.

---

## 2. CANONICAL GAP REGISTRY SUMMARY

All 18 product and architectural GAPs are summarized below with their canonical IDs and blocking classifications:

| ID | Domain | Requirement Title | Current Implementation State | Blocking? | Target Task | Status |
|---|---|---|---|:---:|:---:|:---:|
| **`GAP-01`** | UI / Workflow | Sole Canonical Procurement Architecture (Mode A) | Mode A (database-aware shortage calculation and reconciliation) fully verified as the sole operational procurement architecture. | **YES** | `TASK-A3` | `VERIFIED` |
| **`GAP-02`** | UI / Workflow | Direct MPN Procurement Quick Order Dialog | Standalone QuickOrderDialog tab implemented with brand rules, stepper, vendor filtering, candidate table, and cart delta staging. | No | `TASK-A5` | `VERIFIED` |
| **`GAP-03`** | UI / Workflow | Direct URL Procurement Quick Order Dialog | Standalone QuickOrderDialog tab implemented with strict PDP regex validation, live inspection, constraint extraction, and cart delta staging. | No | `TASK-A5` | `VERIFIED` |
| **`GAP-04`** | Matching | Package & Footprint Hard Constraints (`OD-001` OPEN) | Fully implemented in Core models and orchestrator with conservative normalization. | **YES** | `TASK-A1` | `VERIFIED` |
| **`GAP-05`** | Matching | `UNKNOWN_REQUIRED_PARAMETER` & Spec Engine | Typed `EvaluationState` enum, 4-state spec engine, and dimension validator implemented. | **YES** | `TASK-A1` | `VERIFIED` |
| **`GAP-06`** | Matching | Manufacturer / Brand Constraint Engine | `ANY` vs explicit approved manufacturer list filtering implemented in Core. | **YES** | `TASK-A1` | `VERIFIED` |
| **`GAP-07`** | UI / Preview | Multi-Candidate Alternative Selection UI | Master-Detail OrderPreviewDialog implemented with factual candidate comparison, radio candidate override, dynamic total recalculation, and staging. | No | `TASK-A5` | `VERIFIED` |
| **`GAP-08`** | Sourcing | Split-Vendor Line Item Sourcing Allocation | Line items allocated to single vendor; split sourcing across multiple vendors deferred. | No | Post-Release | `DEFERRED` |
| **`GAP-09`** | Authentication | Interactive Authentication & Headful Fallback | Session promotion (`SessionContinuityMode`) and adapter challenge escalation implemented. | **YES** | `TASK-A2` | `VERIFIED` |
| **`GAP-10`** | Security | Encrypted Keyring Credential Storage | Plaintext JSON in `settings.json`; OS keyring encryption deferred. | No | Post-Release | `DEFERRED` |
| **`GAP-11`** | Vendor Mgmt | Multi-Vendor Settings & Dynamic Enable/Disable | Multi-vendor settings schema, dynamic registry filtering, and 4-tab UI dialog implemented. | **YES** | `TASK-A2` | `VERIFIED` |
| **`GAP-12`** | Runtime | Finite State Machine Job Lifecycle Engine | Coarse string statuses (`"RESOLVED"`); explicit lifecycle FSM deferred. | No | Post-Release | `DEFERRED` |
| **`GAP-13`** | Runtime | Multi-Vendor Cart Idempotency & Delta Sync | Strict 4-tier cart identity cascade, A3 quantity reconciliation, delta staging, and idempotent no-ops verified. | **YES** | `TASK-A4` | `VERIFIED` |
| **`GAP-14`** | Persistence | Embedded ACID Relational Persistence (SQLite) | `Inventory.xlsx` production datastore active; SQLite migration deferred. | No | Post-Release | `DEFERRED` |
| **`GAP-15`** | Audit | Append-Only Persistent Audit Trail Event Log | Ephemeral stdout logging; append-only event store deferred. | No | Post-Release | `DEFERRED` |
| **`GAP-16`** | Altium Contract| Extended Parameter Ingestion Parser | Full 20-parameter canonical contract ingestion, strict MPN validation, and technical spec extraction implemented. | No | `TASK-A3` | `VERIFIED` |
| **`GAP-17`** | Security | Universal Challenge / CAPTCHA Handler Subsystem | Unified `IChallengeHandler` subsystem with 8 challenge types, callback & Qt dialogs. | **YES** | `TASK-A2` | `VERIFIED` |
| **`GAP-18`** | Reporting | Multi-Vendor Deterministic Export Pipeline | Pure functional multi-vendor PDF, CSV (RFC 4180/utf-8-sig), and XLSX (multi-sheet/openpyxl) deterministic export pipeline with candidate audit trails and Persian/RTL support. | No | `TASK-A6` | `VERIFIED` |

---

## 3. RELEASE-BLOCKING GAPS

The following **EXACTLY 8 GAPS** are strictly release-blocking (ALL 8 ARE NOW VERIFIED):
1. **`GAP-01` (Canonical Procurement Architecture):** Enforces Mode A (Database-Aware) as the sole operational procurement workflow. *(VERIFIED via Task A3)*
2. **`GAP-04` (Package & Footprint Hard Constraints):** Prevents purchasing physically incompatible SMD/through-hole parts. *(VERIFIED in Core via Task A1)*
3. **`GAP-05` (`UNKNOWN_REQUIRED_PARAMETER` & Spec Engine):** Flags unlisted/unknown specs to prevent unsafe auto-ordering. *(VERIFIED in Core via Task A1)*
4. **`GAP-06` (Manufacturer / Brand Constraint Engine):** Enforces brand rules (`ANY` vs approved list) over lower pricing. *(VERIFIED in Core via Task A1)*
5. **`GAP-09` (Interactive Authentication & Headful Fallback):** Enables human challenge resolution on Iranian storefronts. *(VERIFIED via Task A2)*
6. **`GAP-11` (Multi-Vendor Settings & Enable/Disable Subsystem):** Enables dynamic activation and credentials for Lion, Javan, and RoboEq. *(VERIFIED via Task A2)*
7. **`GAP-13` (Multi-Vendor Cart Idempotency & Delta Synchronization):** Prevents duplicate item accumulation in vendor carts. *(VERIFIED via Task A4)*
8. **`GAP-17` (Universal Security Challenge Handler Subsystem):** Modular handling of CAPTCHA, Turnstile, and OTP challenges. *(VERIFIED via Task A2)*

---

## 4. CANONICAL PROCUREMENT ARCHITECTURE (GAP-01)

`
                                  [ Altium BOM Upload ]
                                            │
                                            ▼
                               [ Mode A: Database-Aware ]
                                            │
                               Read Inventory.xlsx on disk
                                            │
                               Match BOM against Database Stock
                                            │
                               Calculate Net Shortages:
                               Needed = max(0, Q_BOM * M - Stock)
                                            │
                               Link Source: Database Link Column
                                            │
                                            ▼
                              [ ProcurementRequest Model ]
                                            │
                                            ▼
                           [ UniversalProcurementOrchestrator ]
`

---

## 5. BOM BRAND CONSTRAINT ARCHITECTURE (`GAP-06`)

### 5.1 Semantics (Verified in Task A1 Core)
1. **Rule: `is_manufacturer_any == True` or `ANY`:**
   - No brand or manufacturer constraint is enforced.
   - Any candidate satisfying MPN, Package, and Footprint is eligible.
   - Mutually exclusive with explicit brand selections.
2. **Rule: Explicit Approved Brand Set (`allowed_manufacturers = [...]`):**
   - User specifies one or more approved brands (e.g. `["Texas Instruments", "STMicroelectronics"]`).
   - Sourcing engine evaluates: $cand.manufacturer \in allowed\_manufacturers$.
   - Unapproved brands or candidates with unknown manufacturers evaluate as `EvaluationState.INCOMPATIBLE_MANUFACTURER`.

### 5.2 Data Pipeline Flow
$$\text{BOM Table Brand Combobox (Task A3/A5)} \longrightarrow \text{ProcurementRequest.allowed_manufacturers} \longrightarrow \text{orchestrator.evaluate_candidate()}$$

---

## 6. VENDOR RUNTIME & SETTINGS ARCHITECTURE (`GAP-11`)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    VENDOR RUNTIME ARCHITECTURE                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 [ SettingsManager (`settings.json` / Keyring) ]
        │
        ├── vendor_lion:   { enabled: true,  username: "...", password: "..." }
        ├── vendor_javan:  { enabled: true,  username: "...", password: "..." }
        └── vendor_roboeq: { enabled: false, username: "...", password: "..." }
        │
        ▼
 [ VendorRegistry (`core/procurement/registry.py`) ]
        │
        ├── get_enabled_vendors() ──► ["vendor_lion", "vendor_javan"]
        ├── get_adapter(vendor_id) ──► Instantiates IVendorAdapter with credentials
        └── get_vendor_for_url(url) ──► Resolves domain (returns None if vendor disabled)
```

---

## 7. AUTHENTICATION & SESSION RESUMPTION ARCHITECTURE (`GAP-09`)

```
  1. Adapter starts Headless Browser Session
                    │
  2. Attempt automated form submission (`authenticate()`)
                    │
  3. Validate Session State (`validate_session()`)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   [ SUCCESS ]           [ CHALLENGE DETECTED ] (WAF / CAPTCHA / OTP)
         │                     │
   Proceed to Cart       4. Switch Browser to Visible / Headful Mode
         │                     │
         │               5. Emit `interactive_login_required` Signal to GUI
         │                     │
         │               6. Display Modal in Omnix GUI:
         │                  "Please complete login in the opened browser window"
         │                     │
         │               7. User completes challenge and clicks "I Have Logged In"
         │                     │
         │               8. Adapter verifies cookies (`validate_session() == True`)
         │                     │
         │               9. Hide/Minimize visible browser window
         │                     │
         └───────────────► 10. Resume exact staged procurement job
```

---

## 8. UNIVERSAL CHALLENGE HANDLER ARCHITECTURE (`GAP-17`)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 UNIVERSAL CHALLENGE HANDLER SUBSYSTEM                            │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│ Component                      │ Role & Responsibilities        │ Concrete Subtypes              │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│ `IChallengeHandler`            │ Core interface invoked by      │ `InteractiveWindowHandler`,    │
│                                │ vendor adapters upon challenge │ `InAppImageChallengeHandler`   │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│ `ChallengeType` Enum           │ Formal classification of       │ `IMAGE_CAPTCHA`, `TEXT_CAPTCHA`│
│                                │ detected security hurdle       │ `CLOUDFLARE_TURNSTILE`, `HCAP` │
│                                │                                │ `SMS_OTP`, `VENDOR_CUSTOM`     │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│ `ChallengeContext`             │ Context payload passed to GUI  │ Target URL, vendor ID, image   │
│                                │ for human solving              │ base64, session cookies        │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

## 9. DECISION HIERARCHY & CONSTRAINTS PRECEDENCE

`UniversalProcurementOrchestrator` enforces deterministic candidate qualification before price ranking:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    DETERMINISTIC EVALUATION PIPELINE                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       [ Vendor Candidate Offer ]
                                   │
                                   ▼
                1. MPN Match (Exact / Normalized) ──► Fail? ──► INCOMPATIBLE_MPN
                                   │ (Pass)
                                   ▼
                2. Brand / Manufacturer Match    ──► Fail? ──► INCOMPATIBLE_MANUFACTURER
                                   │ (Pass)
                                   ▼
                3. Package Compatibility (OD-001)──► Fail? ──► INCOMPATIBLE_PACKAGE
                                   │ (Pass)
                                   ▼
                4. Footprint Compatibility       ──► Fail? ──► INCOMPATIBLE_FOOTPRINT
                                   │ (Pass)
                                   ▼
                5. Technical Specs & Dimensions  ──► Fail/Missing? ──► UNKNOWN_REQUIRED_PARAMETER
                                   │ (Pass)
                                   ▼
                6. Stock & Orderability Check    ──► Fail? ──► OUT_OF_STOCK / UNORDERABLE
                                   │ (Pass)
                                   ▼
                7. Effective Quantity (MOQ/Step)
                                   │
                                   ▼
                8. Tiered Unit & Total Price Calculation
                                   │
                                   ▼
                       [ ELIGIBLE Candidate Pool ]
                                   │
                                   ▼
                  Deterministic Sorter (Price Ascending)
                                   │
                                   ▼
                       [ Optimal Candidate Selected ]
```

---

## 10. ALTIUM / BOM PARAMETER CONTRACT (`GAP-16`)

### 10.1 Scope Boundary
- **External Altium Component Library Database:** **OUT OF CURRENT SCOPE (`OOS-001`).**
- **Omnix Component Parameter Contract:** **IN SCOPE (`DOC-OMNIX-ALTIUM-CONTRACT-001`).**

### 10.2 Parameter Contract Specification
```
Canonical_Component_ID    [Mandatory]  Unique CAD library identifier
Description               [Mandatory]  Technical description
Manufacturer              [Mandatory]  Primary manufacturer name
MPN                       [Mandatory]  Manufacturer Part Number
Approved_Manufacturers    [Optional]   Comma-separated approved second sources
Manufacturer_Rule         [Mandatory]  Enum: EXACT, APPROVED_LIST, ANY
Package                   [Mandatory]  Physical case code (e.g. 0805, DIP-8, SOIC-8)
Package_Family            [Mandatory]  Enum: SMD, THROUGH_HOLE, BGA, CONNECTOR
Footprint_ID              [Mandatory]  Altium PCB footprint reference
Pin_Count                 [Mandatory]  Physical pin/pad count
Value                     [Parametric] Resistance, Capacitance, Inductance
Tolerance                 [Parametric] Tolerance rating (e.g. 1%, 5%)
Voltage_Rating            [Parametric] Maximum voltage rating (e.g. 50V)
Current_Rating            [Parametric] Maximum current rating (e.g. 2A)
Power_Rating              [Parametric] Power dissipation (e.g. 0.25W)
Lifecycle_Status          [Mandatory]  Enum: ACTIVE, NRND, EOL, OBSOLETE
Library_Version           [Mandatory]  Semantic version of library asset
```

---

## 11. CART STAGING IDEMPOTENCY ARCHITECTURE (`GAP-13`)

1. **Pre-Staging Inspection:** Adapter invokes `inspect_cart()` on the active vendor session.
2. **Delta Calculation:**
   $$\text{staged\_qty} = \sum_{\text{item} \in \text{cart}} \text{item.quantity} \quad (\text{where item.sku} == \text{target.sku})$$
   $$\Delta Q = \max(0, Q_{\text{target}} - \text{staged\_qty})$$
3. **Execution Decision:**
   - If $\Delta Q == 0$: Skip mutation; return `CartMutationResult(success=True, actual_quantity_staged=0, raw_vendor_message="Already staged")`.
   - If $\Delta Q > 0$: Add only $\Delta Q$ units to the cart.

---

## 12. OPEN ARCHITECTURAL DECISIONS (PRESERVED)

The following decisions remain **OPEN** and are strictly preserved:
- **`OD-001` (Package Standardization Taxonomy):** Standardizing vendor package strings (`SOIC-8` vs `SOP-8`) vs IPC-7351B standards. (Task A1 verified with conservative string normalization only).
- **`OD-002` (Multi-Vendor Sourcing Metric):** Lowest aggregate purchase cost vs minimum number of vendor shipments vs delivery speed. (`GAP-08` deferred).
- **`OD-003` (Safety Stock Formula & Persistence Evolution):** Fixed minimum threshold delta vs target replenishment buffer; SQLite ACID persistence migration (`GAP-14` deferred).

---

## 13. OUT OF CURRENT SCOPE

1. **External Altium Component Library Implementation (`OOS-001`):** Database creation, schematic symbol drawing, and 3D step model generation.
2. **Automated Payment & Checkout (`OOS-002`):** Payment gateway completion (CVV2, OTP, Shetab) is strictly retained as a human manual step.
3. **Autonomous AI/LLM Purchasing Agents (`OOS-003`):** Non-deterministic generative loops are prohibited in production runtime.

---

## 14. TOPOLOGICAL DEPENDENCY GRAPH

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 TOPOLOGICAL IMPLEMENTATION DAG                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 [ LAYER 0: CONTRACTS & ENUMS ]
 ├── GAP-05: UNKNOWN_REQUIRED_PARAMETER EvaluationState Enum (VERIFIED)
 └── GAP-16: Altium Component Parameter Contract Schema
       │
       ▼
 [ LAYER 1: TECHNICAL MATCHING & CONSTRAINTS ENGINE ]
 ├── GAP-04: Package & Footprint Constraint Checking (VERIFIED)
 └── GAP-06: Brand Constraint Rules in Core (VERIFIED)
       │
       ▼
 [ LAYER 2: SETTINGS, AUTHENTICATION & CHALLENGE RECOVERY ] (TASK-A2)
 ├── GAP-11: Multi-Vendor Settings Dialog & Dynamic Enable/Disable
 ├── GAP-17: Universal Security Challenge & CAPTCHA Handler Subsystem
 └── GAP-09: Interactive Authentication & Headful Browser Fallback
       │
       ▼
 [ LAYER 3: WORKFLOW MODES & CAD INGESTION ] (TASK-A3)
 ├── GAP-01: Canonical Procurement Architecture (Mode A)
 └── GAP-16: Extended Altium Parameter Ingestion Parser
       │
       ▼
 [ LAYER 4: CART RUNTIME IDEMPOTENCY ] (TASK-A4)
 └── GAP-13: Multi-Vendor Cart Idempotency & Delta Staging (ΔQ Synchronization)
       │
       ▼
 [ LAYER 5: DESKTOP UI WORKFLOWS & PRESENTATION ] (TASK-A5)
 ├── GAP-07: Multi-Candidate Comparison & Selection in OrderPreviewDialog
 ├── GAP-02: Direct MPN Quick Order Dialog
 └── GAP-03: Direct URL Quick Order Dialog
       │
       ▼
 [ LAYER 6: DETERMINISTIC REPORTING & AUDIT ] (TASK-A6)
 └── GAP-18: Multi-Vendor Deterministic Export Pipeline (PDF / CSV / Excel)
       │
       ▼
 [ LAYER 7: RELEASE HARDENING & PACKAGING ] (TASK-A7 / PHASE 10)
 └── End-to-End Live Multi-Vendor Desktop Validation & Nuitka Binary Compilation
```

---

## 15. ORDERED IMPLEMENTATION SEQUENCE (TASKS A1 THROUGH A7)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  ORDERED IMPLEMENTATION TASKS                                    │
├───────────┬───────────────────────────────────┬───────────────────────────────┬──────────────────┤
│ Task ID   │ Title                             │ Target GAPs                   │ Status           │
├───────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────┤
│ TASK-A1   │ Core Technical Matching & Brands  │ GAP-04, GAP-05, GAP-06        │ VERIFIED         │
│ TASK-A2   │ Multi-Vendor Settings & Challenge │ GAP-11, GAP-17, GAP-09        │ VERIFIED         │
│ TASK-A3   │ Dual Modes & Altium Ingestion     │ GAP-01, GAP-16                │ VERIFIED         │
│ TASK-A4   │ Multi-Vendor Cart Idempotency     │ GAP-13                        │ VERIFIED         │
│ TASK-A5   │ Desktop UI & Multi-Candidate      │ GAP-07, GAP-02, GAP-03        │ VERIFIED         │
│ TASK-A6   │ Deterministic Export Pipeline     │ GAP-18                        │ VERIFIED         │
│ TASK-A7   │ Phase 10 Release & Nuitka Binary  │ End-to-End Validation         │ NEXT_IN_SEQUENCE │
└───────────┴───────────────────────────────────┴───────────────────────────────┴──────────────────┘
```

### Detailed Task Specifications:

#### TASK-A1: Core Technical Matching, Package/Footprint Constraints & Brand Rules
- **Target GAPs:** `GAP-04`, `GAP-05`, `GAP-06`.
- **Status:** `COMPLETED_AND_VERIFIED` (208 unit/contract tests passing baseline).
- **Deliverables:** `EvaluationState` enum, `normalize_constraint_string()`, independent package/footprint validation, brand rule engine (`ANY` vs approved list), and hard-constraint precedence over price in candidate selection.

#### TASK-A2: Multi-Vendor Settings, Universal Security Challenge Handler & Interactive Auth
- **Target GAPs:** `GAP-11`, `GAP-17`, `GAP-09`.
- **Status:** `COMPLETED_AND_VERIFIED` (241 unit/contract tests passing total).
- **Deliverables:**
  1. `SettingsDialog` and `SettingsManager` multi-vendor tabs for Lion, Javan, and RoboEq with isolated credentials, enable/disable toggles, and timeout configuration.
  2. Dynamic vendor filtering in `VendorRegistry` (disabled vendors bypassed) and orchestrator integration.
  3. `core/procurement/challenge_handler.py` (`IChallengeHandler`, `ChallengeType`, `ChallengeState`, `ChallengeContext`, `ChallengeResult`, `CallbackChallengeHandler`).
  4. `ui/dialogs/challenge_dialog.py` (`UniversalChallengeDialog`, `QtChallengeHandler`).
  5. Qualified headless-to-headful session promotion (`SessionContinuityMode`) across all vendor session managers with cookie transfer.
  6. Universal challenge escalation and authentication flow across Lion, Javan, and RoboEq adapters.

#### TASK-A3: Dual Procurement Modes & Altium Parameter Ingestion
- **Target GAPs:** `GAP-01`, `GAP-16`.
- **Status:** `COMPLETED_AND_VERIFIED` (258 unit/contract tests passing total, +17 new tests).
- **Scope Accomplished:** Mode A (database-aware stock reconciliation), 20-parameter Altium contract parser, strict MPN validation, strict quantity validation, and `ManufacturerRule` vs `ManufacturerDataState` separation.
- **Affected Files:** `ui/widgets/bom_audit_widget.py`, `bom_auditor.py`, `core/procurement/bridge.py`, `core/procurement/models.py`.

#### TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization
- **Target GAPs:** `GAP-13`.
- **Status:** `COMPLETED_AND_VERIFIED` (282 unit/contract tests passing total, +24 new tests).
- **Scope Accomplished:** 4-tier cart identity cascade, A3 quantity reconciliation without secondary step rounding, multi-line cart aggregation, delta staging ($\Delta Q = \max(0, Q_{\text{target\_orderable}} - Q_{\text{existing}})$), idempotent no-ops, multi-vendor isolation, disabled vendor bypass, and RoboEq DOM cart extraction.
- **Affected Files:** `core/models.py`, `core/procurement/models.py`, `core/procurement/orchestrator.py`, `core/procurement/bridge.py`, `vendors/roboeq/adapter.py`, `tests/test_cart_sync.py`.

#### TASK-A5: Desktop UI Workflows & Multi-Candidate Preview
- **Target GAPs:** `GAP-07`, `GAP-02`, `GAP-03`.
- **Status:** `COMPLETED_AND_VERIFIED` (316 unit/contract tests passing total, +34 new tests).
- **Scope Accomplished:** Master-Detail `OrderPreviewDialog` with multi-candidate offers, factual parameter comparison, radio candidate override, dynamic total recalculation, and `QuickOrderDialog` with standalone Direct MPN (GAP-02) and Direct URL (GAP-03) sourcing workflows.
- **Affected Files:** `ui/dialogs/order_preview_dialog.py`, `ui/dialogs/quick_order_dialog.py` (NEW), `ui/main_window.py`, `tests/test_desktop_workflows.py` (NEW).

#### TASK-A6: Multi-Vendor Deterministic Export Pipeline
- **Target GAPs:** `GAP-18`.
- **Status:** `COMPLETED_AND_VERIFIED` (331 unit/contract tests passing total, +15 new tests).
- **Scope Accomplished:** Pure functional multi-vendor PDF, CSV (RFC 4180/utf-8-sig), and XLSX (multi-sheet/openpyxl) deterministic export pipeline with candidate audit trails (`DISCOVERED`, `ELIGIBLE`, `REJECTED`, `SELECTED_BY_USER`, `ACTUALLY_STAGED`), Pre-Order vs Post-Staging separation, Persian/RTL text direction handling, and side-effect-free UI export integration.
- **Affected Files:** `core/procurement/reporting/` (`__init__.py`, `models.py`, `builder.py`, `csv_exporter.py`, `xlsx_exporter.py`, `pdf_exporter.py`), `ui/dialogs/order_preview_dialog.py`, `tests/test_export_pipeline.py`.

#### TASK-A7: Phase 10 Release Packaging & Nuitka Hardening
- **Target Scope:** End-to-end live multi-vendor validation on Windows host, application-level packaging, and production Nuitka binary compilation.
- **Prerequisites:** Tasks A1 through A6 completed.

---

## 16. MASTER ROADMAP AUDIT SUMMARY

```
================================================================================
MASTER IMPLEMENTATION ROADMAP RECONCILIATION SUMMARY
================================================================================
Document Reference:      DOC-OMNIX-ROADMAP-001
Version:                 2.0.0-RECONCILED
Governing Registry:      docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (DOC-OMNIX-REGISTRY-001)
Repository:              D:\management-elec\autom\atom
Branch:                  Auto
Automated Tests:         331 / 331 PASSED
Site Map Graph Audits:   Lion (10/10), Javan (10/10), RoboEq (10/10) — 30/30 PASS
Canonical GAPs Count:    18 GAPs (GAP-01 through GAP-18)
Release-Blocking GAPs:   8 GAPs (GAP-01, GAP-04, GAP-05, GAP-06, GAP-09, GAP-11, GAP-13, GAP-17 — ALL 8 VERIFIED)
Verified GAPs:           13 GAPs (GAP-01, GAP-02, GAP-03, GAP-04, GAP-05, GAP-06, GAP-07, GAP-09, GAP-11, GAP-13, GAP-16, GAP-17, GAP-18)
Active Next Task:        TASK-A7 (Phase 10 Release Packaging & Nuitka Hardening)
Task Sequence:           TASK-A1 -> TASK-A2 -> TASK-A3 -> TASK-A4 -> TASK-A5 -> TASK-A6 -> TASK-A7
Current Datastore:       Inventory.xlsx (Production Datastore Preserved)
SQLite Status:           DEFERRED (GAP-14 gated on OD-003)
================================================================================
```
