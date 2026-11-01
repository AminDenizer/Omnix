# PHASE 9 — UNIVERSAL PROCUREMENT CONTRACT GAP ANALYSIS
## Omnix Multi-Vendor Procurement Platform — Architectural Contract Audit

**Document Reference:** `DOC-OMNIX-GAP-PHASE9-001`  
**Audit Date:** 2026-09-16  
**Auditor:** Omnix Architecture & Core Procurement Governance Gate  
**Target Subsystems:** `core/vendor_interface.py`, `core/models.py`, `core/errors.py`, `core/procurement/`, `vendors/`, `bom_auditor.py`, `excel_loader.py`  
**Status:** **`PHASE_9_STEP_2_COMPLETE`**  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/DISCOVERY/UNIVERSAL_DISCOVERY_PIPELINE.md` (DOC-OMNIX-PIPE-001)
- `docs/DISCOVERY/PHASE_8_THIRD_VENDOR_UNIVERSALITY_AUDIT.md` (DOC-OMNIX-AUDIT-PHASE8-UNIVERSALITY-001)
- `docs/VENDORS/LION/ADAPTER_SPECIFICATION.md`
- `docs/VENDORS/JAVAN/ADAPTER_SPECIFICATION.md`
- `docs/VENDORS/ROBOEQ/ADAPTER_SPECIFICATION.md`

---

## 1. EXECUTIVE SUMMARY

With the successful completion and verification of the Universal Discovery and Adapter implementations across three diverse electronic component distributors (**Lion Electronic**, **Javan Electronic**, and **RoboEq Electronic**), Omnix enters **Phase 9: Universal Procurement Orchestration Integration**.

The objective of Phase 9 is to integrate these verified vendor adapters into the existing procurement workflow (Mode A: Inventory Shortages) **without coupling procurement logic to any specific vendor** and **without modifying core inventory math or BOM formulas**.

### Key Findings of this Gap Analysis:
1. **`IVendorAdapter` is 100% Structurally Sound**: All 13 canonical operations defined in `core/vendor_interface.py` provide full coverage for vendor interaction (catalog search, product resolution, inspection, stock checking, constraint evaluation, cart mutation, authentication, and error recovery). No breaking changes to `IVendorAdapter` are required.
2. **Missing Canonical Procurement Data Layer**: While low-level vendor models exist in `core/models.py`, the architecture currently lacks higher-level, vendor-neutral procurement abstractions:
   - `VendorProcurementCandidate`: Multi-attribute vendor offer representation.
   - `PriceTier`: Rich representation of volume discount brackets (essential for Javan and RoboEq).
   - `BOMProcurementPlan`: Aggregated multi-vendor procurement plan for a BOM or inventory shortage set.
3. **Missing Dynamic Vendor Registry**: Vendor adapter instantiation is currently ad-hoc. A central, vendor-neutral `VendorRegistry` is required in `core/procurement/registry.py` to manage discovery, registration, and factory creation of `IVendorAdapter` instances.
4. **Isolated Legacy Lion Couplings Identified**: Hardcoded references to Lion Electronic exist in `bom_auditor.py` (URL checking), `excel_loader.py` (link domain parsing), and `order_preview_dialog.py` (direct `LionAutomator` instantiation). These must be routed through the universal orchestrator without disturbing existing UI capabilities.
5. **Zero Blockers**: There are **0 blocking architectural defects**. The contract gaps are additive and can be cleanly fulfilled under `core/procurement/`.

---

## 2. SCOPE AND NON-GOALS

### In-Scope
- Formal evaluation of `IVendorAdapter` against end-to-end procurement workflows.
- Gap identification across data models, pricing representations, stock constraints, and session lifecycles.
- Identification of legacy Lion-specific assumptions in procurement code.
- Definition of `VendorRegistry` prerequisites and `UniversalProcurementOrchestrator` boundaries.
- Definition of non-destructive order staging boundaries.

### Non-Goals
- Modifying `core/discovery/` (already 100% validated and frozen).
- Rewriting existing vendor adapters (`vendors/lion/`, `vendors/javan/`, `vendors/roboeq/`).
- Changing BOM multiplication math (`unit_qty * board_multiplier`) or inventory shortage logic (`curr_stock <= min_stock`).
- Modifying `Inventory.xlsx` disk schema.
- Implementing automatic payment, credit card submission, or final irreversible financial checkout.
- Introducing probabilistic or LLM-based autonomous decisions in procurement core.

---

## 3. EVIDENCE & FILES AUDITED

| Subsystem / Layer | File Path | Lines of Code | Primary Responsibility | Audit Status |
|---|---|:---:|---|:---:|
| **Adapter Interface** | `core/vendor_interface.py` | 135 | `IVendorAdapter` 13-method abstract contract | Audited (Sufficient) |
| **Data Models** | `core/models.py` | 164 | Dataclass definitions for search, product, cart, session | Audited (Needs Tier Model) |
| **Error Taxonomy** | `core/errors.py` | 114 | 13 normalized vendor exception classes | Audited (Sufficient) |
| **Lion Adapter** | `vendors/lion/adapter.py` | 658 | Reference implementation for Yii2 store | Audited (Compliant) |
| **Javan Adapter** | `vendors/javan/adapter.py` | 688 | Reference implementation for ASP.NET store | Audited (Compliant) |
| **RoboEq Adapter** | `vendors/roboeq/adapter.py` | 465 | Reference implementation for Marketplace store | Audited (Compliant) |
| **BOM Auditor** | `bom_auditor.py` | 300 | Altium BOM Excel parsing and stock cross-referencing | Audited (Legacy coupling) |
| **Excel Loader** | `excel_loader.py` | 485 | `Inventory.xlsx` persistence, indexing, shortage math | Audited (Legacy coupling) |
| **Legacy Automator** | `lion_automator.py` | 379 | Monolithic Selenium automation for Lion | Audited (To be superseded) |
| **Order Preview UI** | `ui/dialogs/order_preview_dialog.py` | 556 | Shortage preview dialog and order execution thread | Audited (To be abstracted) |
| **BOM Widget** | `ui/widgets/bom_audit_widget.py` | 862 | Dual-table Altium BOM audit UI | Audited (To be abstracted) |

---

## 4. CURRENT `IVendorAdapter` CONTRACT EVALUATION

The `IVendorAdapter` base class defines 13 canonical operations:

```python
class IVendorAdapter(ABC):
    @property
    def vendor_id(self) -> str: ...
    @property
    def base_url(self) -> str: ...
    def initialize(self, config: Optional[AdapterConfig] = None) -> AdapterStatus: ...
    def search_part(self, query: str) -> SearchResultSet: ...
    def resolve_product(self, url_or_sku: str) -> ProductReference: ...
    def inspect_product(self, product_ref: ProductReference) -> ProductDetails: ...
    def extract_product_data(self, dom_context: Any) -> CanonicalComponentDraft: ...
    def inspect_stock(self, product_ref: ProductReference) -> StockStatus: ...
    def determine_order_constraints(self, product_ref: ProductReference) -> OrderConstraints: ...
    def add_to_cart(self, product_ref: ProductReference, quantity: int) -> CartMutationResult: ...
    def inspect_cart(self) -> CartDetails: ...
    def authenticate(self, credentials: Optional[AuthCredentials] = None) -> AuthResult: ...
    def validate_session(self) -> SessionStatus: ...
    def recover_from_error(self, error_context: Dict[str, Any]) -> RecoveryResult: ...
    def close(self) -> None: ...
```

### Assessment:
- **Coverage:** Complete for all per-vendor capabilities.
- **Independence:** Adapters operate purely as deterministic data and browser automation providers without knowing anything about project BOMs or `Inventory.xlsx`.
- **Sufficiency:** **100% SUFFICIENT AS-IS.** No changes to `IVendorAdapter` are required.

---

## 5. CURRENT CANONICAL DATA MODELS AUDIT

### Existing Models in `core/models.py`:
1. `AdapterConfig`: Configuration parameters (timeouts, headless, user-agent).
2. `AdapterStatus`: Adapter readiness and auth status.
3. `SearchItem` & `SearchResultSet`: Normalized catalog search items.
4. `ProductReference`: Uniform vendor SKU, URL, and identifier reference.
5. `ProductDetails`: Technical specifications, MPN, manufacturer, single unit price (`price_irr`), stock quantity, and order constraints.
6. `CanonicalComponentDraft`: Structured key-value technical parameters.
7. `StockStatus`: Stock quantity, availability flags (`in_stock`, `can_order`, `is_inquiry_only`).
8. `OrderConstraints`: Raw packaging step, MOQ, max orderable quantity.
9. `CartItem`, `CartDetails`, `CartMutationResult`: Cart staging structures.
10. `AuthCredentials`, `AuthResult`, `SessionStatus`, `RecoveryResult`: Session lifecycle models.

### Identified Gap (G-MODEL-001 — REQUIRED):
- `ProductDetails.price_irr` is a single integer representing base unit price.
- In distributors with volume pricing (e.g. Javan: 1-49 @ 85,000 IRR, 50-99 @ 78,100 IRR; RoboEq: multi-tier quantity columns), volume pricing cannot be represented by a single integer without losing bracket data.
- **Resolution:** Introduce `PriceTier` (`min_quantity: int`, `unit_price_irr: int`, `label: str`) in `core/procurement/models.py`.

---

## 6. CANONICAL PROCUREMENT FLOW AUDIT (17-STAGE TRACE)

The complete end-to-end procurement lifecycle was traced across all 17 conceptual stages:

| Stage # | Stage Name | Existing Contract / Model | Existing Implementation | Missing Contract / Gap | Leakage Risk | Severity | Responsible Files |
|:---:|---|---|---|---|:---:|:---:|---|
| **1** | **BOM / Shortage Detection** | `BOMItem`, `ExcelDataLoader` | `bom_auditor.py`, `excel_loader.py` | None (Formulas intact) | Low | NONE | `bom_auditor.py`, `excel_loader.py` |
| **2** | **Procurement Request** | Dict structures in UI | Ad-hoc dicts in `bom_audit_widget.py` | `ProcurementRequest` model | Med | **REQUIRED** | `core/procurement/models.py` |
| **3** | **Vendor Target Routing** | String link matching | Hardcoded `lionelectronic.ir` in `bom_auditor` | `VendorRegistry.resolve_vendor_for_item()` | High | **REQUIRED** | `core/procurement/registry.py` |
| **4** | **Adapter Lifecycle Init** | `AdapterConfig`, `initialize()` | Implemented in all 3 adapters | Lifecycle pool management | Low | **REQUIRED** | `core/procurement/orchestrator.py` |
| **5** | **Catalog Search** | `search_part() -> SearchResultSet` | Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **6** | **Candidate Normalization** | `SearchItem` | Implemented in all 3 adapters | `VendorProcurementCandidate` | Med | **REQUIRED** | `core/procurement/models.py` |
| **7** | **Product Resolution** | `resolve_product() -> ProductRef` | Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **8** | **Product Inspection** | `inspect_product() -> ProductDetails`| Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **9** | **Stock Verification** | `StockStatus` | Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **10** | **Constraint Evaluation** | `OrderConstraints` | Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **11** | **Price & Tier Evaluation**| `ProductDetails.price_irr` | Single price in details | `PriceTier` evaluation logic | Med | **REQUIRED** | `core/procurement/models.py` |
| **12** | **Effective Qty Calc** | Ad-hoc in `lion_automator.py` | Stepper math in `lion_automator.py` | Deterministic `calculate_effective_quantity()` | High | **REQUIRED** | `core/procurement/orchestrator.py` |
| **13** | **Candidate Selection** | Hardcoded Lion | Single-vendor Lion | Deterministic Multi-Vendor Policy | High | **REQUIRED** | `core/procurement/orchestrator.py` |
| **14** | **Cart Staging** | `add_to_cart() -> CartMutation` | Implemented in all 3 adapters | None (Safe non-destructive) | Low | NONE | `core/vendor_interface.py` |
| **15** | **Cart Inspection** | `inspect_cart() -> CartDetails` | Implemented in all 3 adapters | None | Low | NONE | `core/vendor_interface.py` |
| **16** | **User Review & Confirm** | `OrderPreviewDialog` | PyQt6 dialog with Lion hardcoding | Multi-vendor preview UI | High | **REQUIRED** | `ui/dialogs/order_preview_dialog.py` |
| **17** | **Inventory Stock Increment**| `batch_increment_stock()` | `excel_loader.py` | None (Disk persistence intact) | Low | NONE | `excel_loader.py` |

---

## 7. VENDOR CAPABILITY COMPARISON

| Feature / Capability | Vendor 1: Lion Electronic (`vendor_lion`) | Vendor 2: Javan Electronic (`vendor_javan`) | Vendor 3: RoboEq Electronic (`vendor_roboeq`) | Canonical Procurement Abstraction |
|---|---|---|---|---|
| **Pricing Structure** | Single unit price × stepper multiplier | Multi-tier volume discount table | Marketplace multi-seller tier columns | `PriceTier` & `effective_unit_price` |
| **Packaging Step** | Piecewise stepper (`site_step` 1, 10, 25, 50, 100) | Quantity bracket minimums (`50 عدد`) | Increment button step (`.inc-qty`) | `OrderConstraints.packaging_step_raw` |
| **Minimum Order Qty (MOQ)**| Equals initial input value | Equals lowest tier minimum | Equals seller minimum | `OrderConstraints.moq_raw` |
| **Stock Indicator** | Text label (`موجود` / `ناموجود`) | Origin badge (`موجود در انبار جوان`) | Integer stock or status badge (`موجود`) | `StockStatus.in_stock` & `can_order` |
| **Inquiry-Only Detection** | `window.productCanOrder == false` | Absence of add-to-cart button | Inquiry button or 0 sellers | `StockStatus.is_inquiry_only` |
| **Cart Staging Flow** | AJAX POST with SweetAlert2 modal check | Form POST with alert check | Quantity button increment & submit | `IVendorAdapter.add_to_cart()` |
| **Authentication Flow** | Form POST at `/login` | Form POST at `/login` | Central CAS SSO redirect at `auth.roboeq.ir` | `IVendorAdapter.authenticate()` |
| **Error Handling** | SweetAlert2 DOM inspection | HTTP redirect & flash alert inspection | Inline error notice inspection | `core.errors.OmnixVendorError` hierarchy |

---

## 8. PRICING CONTRACT GAP ANALYSIS

### Analysis of Distortion Risks:
- If pricing is flattened to a single `unit_price`, procurement calculations will miscalculate costs for high-volume purchases from tiered vendors like Javan.
- Example: Purchasing 200 units of LM358 on Javan costs 65,000 IRR/unit (Tier 3), whereas single-unit price is 95,000 IRR (Tier 1). Flattening to Tier 1 would overestimate cost by 31.5%.
- **Canonical Model Requirement:**
```python
@dataclass
class PriceTier:
    min_quantity: int
    unit_price_irr: int
    raw_label: str = ""

@dataclass
class VendorProcurementCandidate:
    vendor_id: str
    part_number: str
    product_ref: ProductReference
    description: str
    in_stock: bool
    stock_quantity: int
    base_unit_price_irr: Optional[int]
    price_tiers: List[PriceTier] = field(default_factory=list)
    order_constraints: OrderConstraints = field(default_factory=OrderConstraints)
```

---

## 9. STOCK / CONSTRAINT CONTRACT GAP ANALYSIS

### Deterministic Effective Quantity Formula:
To ensure 100% deterministic purchasing that respects all vendor packaging constraints without human intervention:

$$\text{effective\_qty} = \max\left(\left\lceil \frac{\text{needed\_qty}}{\text{packaging\_step}} \right\rceil \times \text{packaging\_step},\, \text{MOQ}\right)$$

If $\text{max\_orderable}$ is specified and $\text{effective\_qty} > \text{max\_orderable}$, the orchestrator flags a constraint violation error (`MaxQuantityExceededError`).

---

## 10. SESSION / AUTHENTICATION / RECOVERY GAP ANALYSIS

### Session Lifecycle Contract:
```
[Uninitialized]
       ↓ (initialize)
   [Ready / Guest Session]
       ↓ (authenticate)
   [Authenticated Session]
       ↓ (transient error / dialog)
   [Error State] ──(recover_from_error)──> [Recovered]
       ↓ (close)
   [Closed / Disposed]
```
- **Fidelity:** All 3 adapters cleanly implement this lifecycle.
- **Orchestrator Role:** The orchestrator manages adapter instances via `VendorRegistry` and handles session reuse without redundant Chrome spawning.

---

## 11. ERROR CONTRACT GAP ANALYSIS

The 13 error classes in `core/errors.py` cover all operational failure modes:
1. `ProductNotFoundError`
2. `ZeroSearchResultsError`
3. `OutOfStockError`
4. `MOQViolationError`
5. `OrderMultipleViolationError`
6. `MaxQuantityExceededError`
7. `TransportNetworkError`
8. `AuthenticationRequiredError`
9. `SessionExpiredError`
10. `SecurityChallengeError`
11. `WAFBlockError`
12. `DOMDriftError`
13. `UnknownVendorError`

### Assessment:
**100% SUFFICIENT.** The orchestrator will catch `OmnixVendorError` subclasses and translate them into candidate status messages for the UI.

---

## 12. DETERMINISTIC VENDOR SELECTION GAP ANALYSIS

### Architectural Principle:
- **Zero AI / Agent Heuristics:** Vendor selection must follow strict, transparent, deterministic rules.
- **Selection Modes:**
  1. **Direct Link Routing (Explicit):** If an item has an explicit vendor URL in `Inventory.xlsx` (e.g. `lionelectronic.ir`, `javanelec.com`, `roboeq.ir`), the orchestrator routes directly to that vendor's adapter.
  2. **Multi-Vendor Candidate Gathering (Search):** When querying by part number across vendors, the orchestrator returns all valid candidates to the UI for user visibility and confirmation.
  3. **Deterministic Selection Precedence:**
     - Primary: In-stock status (`in_stock == True` and `can_order == True`).
     - Secondary: Exact MPN match.
     - Tertiary: Lowest effective total price for the required quantity.

---

## 13. CART / ORDER DESTRUCTIVE ACTION BOUNDARY

```
┌────────────────────────────────────────────────────────────────────────┐
│                   OPERATIONAL SAFETY BOUNDARIES                        │
│                                                                        │
│   READ OPERATIONS (Completely Safe / Non-Destructive):                 │
│   • search_part()                                                      │
│   • resolve_product()                                                  │
│   • inspect_product()                                                  │
│   • inspect_stock()                                                    │
│   • determine_order_constraints()                                      │
│   • inspect_cart()                                                     │
│                                                                        │
│   STAGING OPERATIONS (Safe / In-Browser Cart Population):              │
│   • add_to_cart()                                                      │
│                                                                        │
│   DESTRUCTIVE / COMMIT OPERATIONS (Human-Only / External):             │
│   • Final checkout, address selection, payment submission              │
│   • STRICT INVARIANT: Omnix NEVER executes irreversible payment.       │
│   • Omnix leaves the browser open at the cart page for user review.    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 14. PROCUREMENT DATA MODEL CLASSIFICATION

| Model / Concept | Classification | Reason & Code Reference |
|---|:---:|---|
| `IVendorAdapter` | **A. Existing & Sufficient** | `core/vendor_interface.py` defines all 13 required operations. |
| `SearchResultSet` | **A. Existing & Sufficient** | `core/models.py:40` captures search results cleanly. |
| `ProductDetails` | **B. Existing but Insufficient** | `core/models.py:65` lacks volume pricing tier list. |
| `PriceTier` | **C. Missing & Required** | Needed to represent volume discounts in `core/procurement/models.py`. |
| `VendorProcurementCandidate`| **C. Missing & Required** | Needed as normalized candidate model in `core/procurement/models.py`. |
| `ProcurementRequest` | **C. Missing & Required** | Needed to encapsulate BOM/Shortage item query parameters. |
| `BOMProcurementPlan` | **C. Missing & Required** | Needed to represent aggregated multi-vendor procurement outcomes. |
| `VendorCapability` | **D. Missing but Not Yet Required** | Static capability descriptors can be inferred directly from adapters. |

---

## 15. VENDOR REGISTRY PREREQUISITES

The `VendorRegistry` in `core/procurement/registry.py` must satisfy:
1. **Dynamic Registration:** `VendorRegistry.register_adapter(vendor_id, adapter_class, config)`.
2. **Deterministic Lookup:** `VendorRegistry.get_adapter(vendor_id) -> IVendorAdapter`.
3. **Storefront URL Routing:** `VendorRegistry.get_vendor_for_url(url) -> Optional[str]`.
4. **Duplicate Protection:** Raises `ValueError` on conflicting registration attempts.
5. **Unknown Vendor Handling:** Raises `UnknownVendorError` for unregistered IDs.
6. **Thread Safety & Lifecycle Isolation:** Safe singleton or scoped factory.

---

## 16. LEGACY LION COUPLING INVENTORY

| File | Line(s) | Coupled Symbol / Expression | Nature of Coupling | Refactoring Strategy |
|---|:---:|---|---|---|
| `bom_auditor.py` | 47–49 | `"lionelectronic.ir" in self.link.lower()` | URL hardcoding to determine `link_type == "LION"` | Delegate to `VendorRegistry.get_vendor_for_url(link)` |
| `bom_auditor.py` | 117, 123 | `is_lion_orderable`, `get_orderable_shortages()` | Method name hardcoded to Lion | Generalize to `is_orderable`, `get_orderable_shortages()` |
| `excel_loader.py` | 401–402 | `"lionelectronic.ir" in link.lower()` | Shortage classification checks Lion only | Delegate to `VendorRegistry.get_vendor_for_url(link)` |
| `order_preview_dialog.py` | 10, 24 | `from lion_automator import LionAutomator` | Direct instantiation of legacy automation | Replace with `UniversalProcurementOrchestrator` |
| `order_preview_dialog.py` | 63, 70 | `self.lion_items` | UI list named specifically for Lion | Rename/generalize to `self.orderable_items` |
| `bom_audit_widget.py` | 510, 539 | `it.link_type == "LION"`, `Lion Items` | UI badge text hardcoded to Lion | Dynamic vendor name badge from `VendorRegistry` |

---

## 17. REQUIRED VS OPTIONAL CHANGES

### Required (Phase 9 Implementation)
1. `core/procurement/models.py`: Implement `PriceTier`, `VendorProcurementCandidate`, `ProcurementRequest`, `BOMProcurementPlan`.
2. `core/procurement/registry.py`: Implement `VendorRegistry` with URL resolver and factory.
3. `core/procurement/orchestrator.py`: Implement `UniversalProcurementOrchestrator`.
4. `tests/test_procurement_orchestrator.py`: Deterministic test suite with mocked adapters.
5. UI Bridge Refactoring: Update `OrderPreviewDialog` and `BOMAuditor` to use `VendorRegistry` and `UniversalProcurementOrchestrator`.

### Optional / Future (Phase 10+)
1. Multi-currency real-time conversion (USD/EUR to IRR).
2. Advanced distributor lead-time / shipping estimation.
3. Automated scheduled periodic inventory reorder scans.

---

## 18. EXPLICIT NON-REQUIREMENTS

- No modifications to `core/discovery/`.
- No modification of `Inventory.xlsx` file structure.
- No modifications to existing `tests/test_lion_adapter.py`, `tests/test_javan_adapter.py`, `tests/test_roboeq_adapter.py`.
- No direct database SQL connections to external vendor servers.

---

## 19. PROPOSED PHASE 9 IMPLEMENTATION SEQUENCE

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 9 IMPLEMENTATION SEQUENCE                                 │
│                                                                                        │
│   Step 1: Pre-Flight & Architecture Inspection (COMPLETED & VERIFIED)                  │
│          ↓                                                                             │
│   Step 2: Contract Gap Analysis Document (COMPLETED & VERIFIED)                        │
│          ↓                                                                             │
│   Step 3: Vendor Registry (`core/procurement/registry.py` + tests)                    │
│          ↓                                                                             │
│   Step 4: Procurement Orchestrator (`core/procurement/orchestrator.py` + models)       │
│          ↓                                                                             │
│   Step 5: Multi-Vendor Integration Tests (`tests/test_procurement_orchestrator.py`)    │
│          ↓                                                                             │
│   Step 6: Existing Procurement Core Bridge & Decoupling                                │
│          ↓                                                                             │
│   Step 7: Live Non-Destructive Storefront Verification                                 │
│          ↓                                                                             │
│   Step 8: Final Phase 9 Integration Audit & Gate Certification                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 20. RISKS AND ARCHITECTURAL INVARIANTS

1. **Deterministic Rule:** Core procurement must never make heuristic or AI-driven purchasing decisions.
2. **Vendor Isolation Rule:** Core procurement must never contain vendor selectors, DOM inspection, or vendor URLs.
3. **Calculation Invariant:** BOM multiplication and inventory threshold formulas must remain 100% mathematically identical.
4. **Safety Invariant:** All browser automation is non-destructive staging only.

---

## 21. FINAL GAP SEVERITY SUMMARY & GATE DECISION

```
========================================================================================
                              GAP ANALYSIS SUMMARY
========================================================================================
BLOCKER GAPS:              0  (Zero architectural blockers detected)
REQUIRED GAPS:             4  (Models, Registry, Orchestrator, UI Decoupling)
NON-BLOCKING GAPS:         3  (Currency conversion, Lead times, Cron triggers)

IVENDORADAPTER STATUS:     100% SUFFICIENT AS-IS
CANONICAL MODELS STATUS:   NEEDS ADDITIVE PROCUREMENT MODELS UNDER core/procurement/
VENDOR REGISTRY STATUS:    READY FOR IMPLEMENTATION UNDER core/procurement/registry.py

DECISION GATE:             PHASE_9_STEP_2_COMPLETE
STATUS:                    READY_FOR_STEP_3_VENDOR_REGISTRY
========================================================================================
```
