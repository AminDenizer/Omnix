# PHASE 9 — STEP 8: UNIVERSAL PROCUREMENT INTEGRATION & GATE CERTIFICATION SCOPE AUDIT

**Document Identifier:** `PHASE9-STEP8-SCOPE-AUDIT`  
**Execution Gate:** `PHASE_9_STEP_8_SCOPE_AUDIT_COMPLETE`  
**Status:** PROPOSED & PENDING AUTHORIZATION  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md`
- `docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md`
- `docs/PROCUREMENT/PHASE9_STEP6_BRIDGE_AUDIT.md`
- `docs/PROCUREMENT/PHASE9_STEP6_BRIDGE_INTEGRATION_AUDIT.md`
- `docs/PROCUREMENT/PHASE9_STEP7_CONTRACT_AUDIT.md`

---

## 1. Objective

Step 8 serves as the final integration hardening, comprehensive end-to-end validation, and formal Phase 9 certification milestone.

The objective is to verify that the universal procurement pipeline operates end-to-end across both input modes:
- **Mode A (Inventory Shortages):** `Inventory.xlsx` $	o$ `ExcelDataLoader.get_shortage_items()` $	o$ `ProcurementBridge` $	o$ `UniversalProcurementOrchestrator` $	o$ Multi-Vendor Cart Staging $	o$ Payment Confirmation $	o$ `ExcelDataLoader.batch_increment_stock()`.
- **BOM Assembly Shortages:** `Sample_BOM.xlsx` $	o$ `BOMAuditor.audit_bom()` $	o$ `ProcurementBridge` $	o$ `UniversalProcurementOrchestrator` $	o$ Multi-Vendor Cart Staging $	o$ Payment Confirmation $	o$ `ExcelDataLoader.batch_increment_stock()`.

This validation proves that multi-vendor procurement operates deterministically across all three onboarded vendors (`vendor_lion`, `vendor_javan`, `vendor_roboeq`) with zero single-vendor monolithic coupling and strict mathematical and financial safety boundaries.

---

## 2. Current-State Evidence

1. **Git Repository Status:**
   - Active Branch: `Auto`
   - Head Commit: `c5def05 docs(procurement): add phase 9 step 7 contract audit`
   - Working Tree: Clean (0 uncommitted changes, 0 untracked files).
2. **Automated Test Suite:**
   - **177 / 177 PASSED** across all test modules (100% pass rate).
   - Includes unit tests for `models.py`, `registry.py`, `orchestrator.py`, `bridge.py`, `bom_auditor.py`, `excel_loader.py`, and all 3 vendor adapters.
3. **Site Map Graph Audits:**
   - Lion Electronic (`vendor_lion`): 10/10 PASS (0 errors, 0 warnings).
   - Javan Electronic (`vendor_javan`): 10/10 PASS (0 errors, 0 warnings).
   - RoboEq Electronic (`vendor_roboeq`): 10/10 PASS (0 errors, 0 warnings).
4. **Architectural Decoupling:**
   - `core/procurement/`: 0 forbidden terms (`selenium`, `webdriver`, `find_element`, `By.`, `xpath`, `css_selector`, `driver.`).
   - Legacy hardcoded `"lionelectronic.ir"` checks completely eliminated from core logic.

---

## 3. Exact Implementation Scope for Step 8

When authorized, Step 8 execution will perform:

1. **End-to-End Pipeline Integration Test Suite (`tests/test_phase9_e2e_procurement.py`):**
   - Test Mode A full lifecycle: Generate realistic inventory shortages across Lion, Javan, and RoboEq, execute batch staging, verify cart results, and assert exact stock increments in `Inventory.xlsx`.
   - Test BOM assembly full lifecycle: Load Altium BOM spreadsheet with multi-board multipliers, audit stock against inventory database, translate shortages to procurement requests, execute multi-vendor staging, and update stock.
   - Test edge cases:
     - All items in stock (0 shortages, order button disabled).
     - Mixed vendor items + unsupported external links + blank links.
     - Out of stock / inquiry-only items correctly handled and excluded from inventory incrementing.
     - Quantity stepping and MOQ constraints correctly applied in final staged quantities.
2. **Final Phase 9 Integration Audit Document (`docs/PROCUREMENT/PHASE9_INTEGRATION_AUDIT_REPORT.md`):**
   - Document complete architectural transition from monolithic script to universal multi-vendor procurement core.
   - Record test suite execution, coverage metrics, and Site Map audit compliance.
   - Issue Phase 9 Certification: `PHASE_9_COMPLETE`.

---

## 4. File Modification Governance Matrix

| File / Subsystem | Allowed Action | Governance Rule |
| :--- | :--- | :--- |
| `tests/test_phase9_e2e_procurement.py` | **NEW FILE** | Add deterministic end-to-end integration tests without live browser dependencies. |
| `docs/PROCUREMENT/PHASE9_STEP8_SCOPE_AUDIT.md` | **NEW FILE** | Pre-implementation scope audit document. |
| `docs/PROCUREMENT/PHASE9_INTEGRATION_AUDIT_REPORT.md` | **NEW FILE** | Final certification report. |
| `core/discovery/` | **STRICTLY FROZEN** | Zero edits permitted. |
| `vendors/lion/`, `vendors/javan/`, `vendors/roboeq/` | **STRICTLY FROZEN** | Zero edits permitted. |
| `core/procurement/models.py` | **FROZEN** | Contract frozen in Step 7. |
| `core/procurement/registry.py` | **FROZEN** | Contract frozen in Step 6. |
| `core/procurement/orchestrator.py` | **FROZEN** | Contract frozen in Step 4. |
| `core/procurement/bridge.py` | **FROZEN** | Contract frozen in Step 6. |
| `Inventory.xlsx` schema | **STRICTLY FROZEN** | Zero column/schema modifications. |

---

## 5. Non-Negotiable Invariants & Safety Boundaries

1. **Mathematical Invariant:**
   - BOM requirements: `total_needed_qty = unit_qty * board_multiplier`
   - Shortage calculation: `shortage_qty = max(0, total_needed_qty - db_stock_qty)`
   - Inventory shortage: `target = target_stock if target_stock > min_stock else min_stock`, `needed_qty = max(int(target - curr_stock), int(min_stock - curr_stock), 1)`
2. **Financial Safety Boundary:**
   - Non-destructive shopping cart staging ONLY.
   - Zero autonomous payment execution, credit card transactions, or final order submission.
3. **Determinism Boundary:**
   - Zero heuristic scoring, AI/LLM ranking, or probabilistic ordering logic.
4. **Architectural Neutrality Boundary:**
   - Zero vendor-specific branching, CSS selectors, or XPath expressions in `core/procurement/`.

---

## 6. Acceptance Criteria

Step 8 completion requires:
1. `tests/test_phase9_e2e_procurement.py` created and passing 100%.
2. Full test suite passing with 0 errors and 0 failures.
3. All 3 vendor Site Map graphs maintaining 10/10 PASS on CLI audit.
4. Static coupling check passing with 0 violations in `core/procurement/`.
5. Atomic git commits with conventional messages.
6. Final gate declared: `PHASE_9_COMPLETE`.

---

## 7. Gate Declaration

**Gate Status:** `PHASE_9_STEP_8_SCOPE_AUDIT_COMPLETE`  
**Ready For:** User authorization to execute Step 8.
