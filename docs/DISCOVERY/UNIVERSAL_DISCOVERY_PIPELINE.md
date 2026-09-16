# OMNIX UNIVERSAL VENDOR ONBOARDING PIPELINE
## Formal Engineering Standard: Discovery → Evidence → Site Map → Adapter Pipeline

**Document Reference:** `DOC-OMNIX-PROC-001`  
**Version:** `1.0.0`  
**Status:** Approved Architectural Standard  
**Governing Specification:** `docs/MASTER_PROJECT_SPECIFICATION.md`  
**Schema Standard:** `docs/DISCOVERY/SITE_MAP_SCHEMA.md`  
**Discovery Standard:** `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md`  

---

## 1. EXECUTIVE SUMMARY & ARCHITECTURAL INVARIANT

This standard establishes the mandatory, vendor-neutral engineering lifecycle for onboarding **ANY** e-commerce or electronic component vendor platform into **Omnix**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   MANDATORY ONBOARDING INVARIANT                       │
├────────────────────────────────────────────────────────────────────────┤
│ NO vendor adapter implementation may begin before:                    │
│   1. Empirical Chrome Observation from Zero Prior Knowledge            │
│   2. Structured Evidence Collection (`EV-{VENDOR}-*.json`)             │
│   3. Declarative Site Map Graph Construction (`SITE_MAP_GRAPH.json`)   │
│   4. Automated Schema & Topology Validation (Zero Errors)              │
│   5. Formal Adapter Contract Derivation (`ADAPTER_SPECIFICATION.md`)   │
│   6. Implementation Readiness Review Approval (Gate 6.5)               │
└────────────────────────────────────────────────────────────────────────┘
```

**Role Distribution:**
* **Lion Electronic (`vendor_lion`):** The first validated reference implementation and pipeline benchmark.
* **Javan Electronic (`vendor_javan`):** The upcoming second vendor to validate cross-vendor universality.
* **Future Vendors (`vendor_*`):** Executed through this exact same ten-phase pipeline without modifying Core discovery tooling.

---

## 2. THE 10-PHASE VENDOR ONBOARDING LIFECYCLE

```
┌───────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│PHASE 1│ ──> │PHASE 2       │ ──> │PHASE 3       │ ──> │PHASE 4         │
│ TARGET│     │ CHROME OBS   │     │ EVIDENCE     │     │ SITE MAP GRAPH │
└───────┘     └──────────────┘     └──────────────┘     └───────┬────────┘
                                                                │
                                                                ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│PHASE 8+  │ <── │PHASE 7.5     │ <── │PHASE 7       │ <── │PHASE 5/6/6.5│
│ PROD INT │     │ INTEGRATION  │     │ ADAPTER IMPL │     │ AUDIT & SPEC│
└──────────┘     └──────────────┘     └──────────────┘     └─────────────┘
```

### Phase 1: Vendor Target Registration
* Declare the vendor identity using `VendorTarget` in Python / JSON.
* Create the vendor repository root: `docs/VENDORS/{VENDOR_ID}/` with `evidence/`, `evidence/screenshots/`, and `evidence/har/`.

### Phase 2: Zero-Knowledge Chrome Observation
* Open an isolated Chrome observation session using `DiscoverySession` from `core.discovery.session`.
* Empirically traverse:
  1. Storefront homepage and global header search forms.
  2. Part Number search queries (exact tokens, multi-token parametric strings, non-existent strings).
  3. Search results pagination and candidate card DOM hierarchy.
  4. Product Detail Page (PDP) specifications table (`شماره فنی`, `سازنده`, `پکیج`).
  5. Live stock availability indicators and qualitative badges (`موجود`, `اتمام موجودی`, `به زودی`).
  6. Packaging step spinbox (`#quantity-cell.value`), MOQ, and order increments.
  7. Internal browser cart mutation (`button.btn-buy`, AJAX triggers, settle time).
  8. Staged cart inspection (`/orders/cart`).
  9. Authentication form anatomy (`/login`) and session cookies.
  10. Negative edge-case triggering (MOQ violations, multiple step violations, stock ceiling exceedances).

### Phase 3: Typed Evidence Collection
* For every observed selector, route, modal, or constraint, record a structured `EvidenceRecord` using `EvidenceRecorder`:
  - Deterministic ID: `EV-{VENDOR}-{WORKFLOW}-{INDEX:03d}` (e.g. `EV-JAVAN-SRCH-001`).
  - Saved to `docs/VENDORS/{VENDOR_ID}/evidence/EV-*.json`.
  - Tagged with verification status (`VERIFIED` vs `DEFENSIVE`).

### Phase 4: Site Map Graph Construction
* Assemble `docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json` using `SiteMapGraphBuilder`:
  - 14 supported Node Types (`PAGE`, `COMPONENT`, `FORM`, `INPUT`, `BUTTON`, `LINK`, `RESULT`, `PRODUCT`, `CART`, `MODAL`, `ERROR`, `API_ENDPOINT`, `DATA_SOURCE`, `STATE`).
  - 10 supported Relationship Types (`CONTAINS`, `TRIGGERS`, `NAVIGATES_TO`, `RETURNS`, `EXTRACTS`, `UPDATES`, `FAILS_WITH`, `RECOVERS_TO`, `REQUIRES`, `DEPENDS_ON`).
  - Unified priority selectors and raw extraction bindings.

### Phase 5: Automated Site Map Validation & Discovery Audit Gate
* Execute programmatic audit using the CLI:
  ```bash
  python -m core.discovery.cli audit docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json
  ```
* Verifies:
  1. Schema conformance & metadata completeness.
  2. Zero duplicate node or edge IDs.
  3. Edge topology integrity (source and target nodes exist).
  4. Zero orphan nodes.
  5. Selector-to-evidence reference resolution.
  6. Extraction-to-selector binding resolution.
  7. Evidence disk presence check.
  8. Mandatory workflow node types present.
  9. Zero Core procurement leakage in graph properties.
* Output: `docs/VENDORS/{VENDOR_ID}/PHASE5_AUDIT_REPORT.md`.

### Phase 6 & 6.5: Adapter Formal Specification & Implementation Readiness
* Derive `docs/VENDORS/{VENDOR_ID}/ADAPTER_SPECIFICATION.md`:
  - Map graph nodes to 13 conceptual operations of `IVendorAdapter`.
  - Define 3 normalized output contracts (`SearchResultSet`, `ProductDetails`, `CartMutationResult`).
  - Map observable signals to the 13 normalized error categories.
* Perform Phase 6.5 Implementation Readiness Review (`PHASE6_5_IMPLEMENTATION_READINESS.md`):
  - Hard sign-off that raw packaging steps are returned as-is (no piecewise client rounding).
  - Hard sign-off that AJAX cart mutations respect browser session context and settle timing.

### Phase 7: Deterministic Adapter Implementation
* Implement the vendor adapter package under `vendors/{vendor_id}/`:
  - `__init__.py`: Exports `{Vendor}VendorAdapter`, `{Vendor}Selectors`, `{Vendor}ErrorTranslator`.
  - `selectors.py`: Houses all selectors from `SITE_MAP_GRAPH.json`.
  - `errors.py`: 3-tier error classification engine.
  - `session.py`: Browser session lifecycle and settle window management.
  - `adapter.py`: Implements `IVendorAdapter` (all 13 methods).
* Output: `docs/VENDORS/{VENDOR_ID}/PHASE7_IMPLEMENTATION_REPORT.md`.

### Phase 7.5: Integration & Regression Audit
* Build deterministic unit and contract tests in `tests/test_{vendor_id}_adapter.py`.
* Execute non-destructive live storefront smoke test (read-only search and PDP resolution).
* Run full repository test suite (`python -m pytest tests -v`).
* Output: `docs/VENDORS/{VENDOR_ID}/PHASE7_5_INTEGRATION_AUDIT.md`.

### Phase 8+: Core Integration & Production Onboarding
* Register vendor adapter into Core Multi-Vendor Procurement Orchestrator.

---

## 3. COMMAND LINE INTERFACE (CLI) REFERENCE

The universal discovery engine provides a command-line interface for audit and inspection:

### 1. Validate / Audit a Site Map Graph
```bash
python -m core.discovery.cli audit docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json
```

### 2. Inspect Discovery Evidence Directory
```bash
python -m core.discovery.cli inspect-evidence docs/VENDORS/{VENDOR_ID}/evidence/
```

### 3. Machine-Readable JSON Output
```bash
python -m core.discovery.cli audit docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json --json-output
```

---

## 4. STRICT ARCHITECTURAL BOUNDARIES

```
┌────────────────────────────────────────────────────────────────────────┐
│                        RESPONSIBILITY BOUNDARY                         │
├─────────────────────────────────────────┬──────────────┬───────────────┤
│ Capability / Function                   │ Owned by Core│ Owned by Adapt│
├─────────────────────────────────────────┼──────────────┼───────────────┤
│ Altium BOM Parsing & Column Matching    │     YES      │      NO       │
│ Inventory Sizing & Shortage Math        │     YES      │      NO       │
│ Mode A (Inventory-Based Procurement)    │     YES      │      NO       │
│ Mode B (BOM-Direct Procurement)         │     YES      │      NO       │
│ Multi-Vendor Ranking & Allocation       │     YES      │      NO       │
│ Purchase Step Rounding Formulas         │     YES      │      NO       │
│ Vendor Discovery Tooling & Validator    │     YES      │      NO       │
│ Vendor Storefront URLs & Selectors      │      NO      │     YES       │
│ Raw Packaging Step Extraction           │      NO      │     YES       │
│ Vendor Error Modal Translation          │      NO      │     YES       │
│ Internal Browser AJAX Cart Staging      │      NO      │     YES       │
│ Active Session & Cookie Management      │      NO      │     YES       │
└─────────────────────────────────────────┴──────────────┴───────────────┘
```

---

## 5. GIT ATOMIC COMMIT DISCIPLINE

Every vendor onboarding milestone must adhere to conventional atomic Git commits:

1. `feat(discovery): introduce universal discovery models & schema`
2. `feat(discovery): add automated graph validator, evidence recorder & CLI`
3. `test(discovery): add unit tests for discovery engine & validator`
4. `docs(discovery): add universal discovery pipeline guide`
5. `refactor(lion): validate lion reference artifacts against generic engine`
6. `feat({vendor}): add {vendor} empirical discovery evidence & site map graph`
7. `feat({vendor}): define {vendor} formal adapter specification`
8. `feat({vendor}): implement {vendor} adapter conforming to IVendorAdapter`
9. `test({vendor}): add deterministic unit and regression coverage for {vendor}`
