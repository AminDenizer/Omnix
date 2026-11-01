# UNIVERSAL VENDOR ONBOARDING PIPELINE — ARCHITECTURAL GAP ANALYSIS
## Omnix Multi-Vendor Procurement Platform — Onboarding Generality Review

**Document Reference:** `DOC-OMNIX-GAP-001`  
**Version:** `1.0.0`  
**Date:** 2026-09-16  
**Auditor:** Omnix Architecture & Discovery Gate  
**Target Codebase:** `core/discovery/`, `core/`, `vendors/`, `docs/DISCOVERY/`  
**Status:** **`GAP_ANALYSIS_COMPLETE`**  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/DISCOVERY/UNIVERSAL_DISCOVERY_PIPELINE.md` (DOC-OMNIX-PIPE-001)
- `docs/DISCOVERY/PHASE7_5_UNIVERSAL_PIPELINE_AUDIT.md` (DOC-OMNIX-AUDIT-HARDENING-001)

---

## 1. EXECUTIVE OBJECTIVE

The objective of this gap analysis is to answer the core architectural question:

> **"Can a completely unknown third vendor with an arbitrary web commerce architecture be onboarded without modifying `core/discovery/` or adding vendor-specific branches to generic code?"**

This document audits all components of the discovery, modeling, validation, specification, and adapter pipeline to classify every dimension as **`PASS`**, **`GAP`**, **`RISK`**, or **`OPEN QUESTION`**.

---

## 2. COMPREHENSIVE COMPONENT AUDIT MATRIX

| Pipeline Dimension | Tested Component / API | Finding Classification | Analysis & Architectural Verification |
|---|---|:---:|---|
| **1. Target Modeling** | `VendorTarget` in `core/discovery/models.py` | **`PASS`** | Pure dataclass accepting `vendor_id`, `vendor_name`, `base_url`, `description`, `category_targets`. Contains zero hardcoded vendor identifiers. |
| **2. Chrome Observation** | `DiscoverySession` in `core/discovery/session.py` | **`PASS`** | Universal Selenium WebDriver harness. Headless/windowed options, anti-detection flags, settle delay controls, DOM/screenshot/cookie query methods. Zero vendor-specific selectors or heuristics. |
| **3. Evidence Management** | `EvidenceRecorder` in `core/discovery/evidence.py` | **`PASS`** | Deterministic ID pattern `EV-{VENDOR}-{WORKFLOW}-{INDEX:03d}` dynamically formatted from `vendor_id`. Structured JSON serialization conforming to schema. |
| **4. Graph Modeling** | `SiteMapGraph` & `GraphBuilder` in `core/discovery/` | **`PASS`** | Programmatic builder enforcing referential integrity between nodes and edges, unique IDs, and selector validation. |
| **5. Graph Validation** | `SiteMapGraphValidator` in `core/discovery/validator.py` | **`PASS`** | 10-point automated structural, topological, orphan, selector, extraction, and Core-leakage audit. Completely vendor-agnostic. |
| **6. Discovery CLI** | `core/discovery/cli.py` | **`PASS`** | Command-line interface providing `validate`, `audit`, and `inspect-evidence` commands for any arbitrary graph path. |
| **7. Adapter Contract** | `IVendorAdapter` in `core/vendor_interface.py` | **`PASS`** | Abstract base class with 13 typed conceptual operations. Covers all e-commerce lifecycle events. |
| **8. Normalized Models** | `core/models.py` | **`PASS`** | Standard typed dataclasses (`SearchResultSet`, `SearchItem`, `ProductDetails`, `StockStatus`, `OrderConstraints`, `CartDetails`, `CartMutationResult`). |
| **9. Error Taxonomy** | `core/errors.py` | **`PASS`** | 13 normalized `OmnixVendorError` subclasses covering DOM validation, HTTP errors, WAF/Captcha challenges, transport timeouts, and session invalidation. |
| **10. Node / Edge Types** | `NodeType`, `RelationshipType` in `models.py` | **`PASS`** | Covers all fundamental web interaction types (`PAGE`, `INPUT`, `BUTTON`, `RESULT`, `MODAL`, `NAVIGATES_TO`, `SUBMITS_FORM`, `MUTATES_STATE`, `RENDERS_ELEMENT`, `TRIGGERS_MODAL`, `RESOLVES_TO`). |
| **11. Extraction Rules** | `ExtractionDefinition` in `models.py` | **`PASS`** | Declarative extraction supporting CSS selectors, DOM attributes, regex transforms, and canonical normalization rules. |
| **12. Multi-Vendor Isolation** | `vendors/` package structure | **`PASS`** | `vendors/lion/` and `vendors/javan/` are completely isolated with zero cross-vendor imports and zero dependencies on Core procurement math. |
| **13. SPA / Dynamic Web Apps** | AJAX / Client-side rendering | **`RISK`** | Single-Page Applications (React/Vue/Angular) requiring heavy client-side hydration may require larger settle windows (3.0s+) or explicit element wait predicates. Covered defensively by `wait_settle()` and `WebDriverWait`. |
| **14. WAF / Cloudflare Challenge** | Turnstile / Captcha blockers | **`RISK`** | Strict bot protection (Cloudflare Under Attack mode) requires human intervention. Handled cleanly by `SecurityChallengeError` and `WAFBlockError` translation. |
| **15. Faceted Multi-Page Pagination** | Deep catalog crawling | **`OPEN QUESTION`** | How vendors with infinite scrolling vs multi-page numbered pagination present search results beyond page 1. Can be captured via standard `EV-{VENDOR}-SRCH-PAG` evidence records. |

---

## 3. VENDOR-SPECIFIC LEAKAGE VERIFICATION

A comprehensive static analysis across `core/discovery/` and `core/` confirmed:
- `Query: lion` -> **0 matches**
- `Query: javan` -> **0 matches**
- `Query: vendor_lion` -> **0 matches**
- `Query: vendor_javan` -> **0 matches**
- `Query: LION` -> **0 matches**
- `Query: JAVAN` -> **0 matches**

**Result:** Zero vendor-specific behavioral logic or hardcoded assumptions exist in generic code.

---

## 4. GAP ANALYSIS CONCLUSION & PHASE 2 READINESS

The gap analysis demonstrates that:
1. The **Universal Discovery Engine** (`core/discovery/`) contains all required abstractions and tools to observe, record, model, validate, and specify any third-party e-commerce website.
2. No generic code refactoring or schema modification is required prior to initiating a third-vendor empirical discovery run.
3. The repository is certified ready to proceed to **Phase 2 — Third-Vendor Dry Run**.

```
========================================================================================
FINAL PHASE 1 GATE DECISION: GAP_ANALYSIS_APPROVED (NO BLOCKING GAPS IDENTIFIED)
========================================================================================
```
