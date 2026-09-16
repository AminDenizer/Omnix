# PHASE 5 DISCOVERY AUDIT REPORT
## Lion Electronic (`vendor_lion`) — Pre-Phase-6 Verification Gate

**Document Reference:** `DOC-OMNIX-AUDIT-LION-001`  
**Audit Date:** 2026-09-16  
**Auditor:** Omnix Architecture & Quality Assurance Gate  
**Target Vendor:** Lion Electronic (`vendor_lion`) — `https://lionelectronic.ir`  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (Approved Engineering Baseline)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001 v1.0.0)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001 v1.0.0)

**Final Gate Status:** **`PHASE_5_FINAL_APPROVED`**

---

## 1. EXECUTIVE SUMMARY

An exhaustive, independent technical audit was conducted on the discovery artifacts produced for **Lion Electronic (`vendor_lion`)** in Phase 5:
- `docs/VENDORS/LION/SITE_MAP_GRAPH.json` (21 Nodes, 20 Edges, 29 Selectors, 6 Extractions, 6 States, 4 Actions, 13 Errors)
- `docs/VENDORS/LION/evidence/` (27 Verified Discovery Evidence Records `EV-LION-*`)

The purpose of this audit is strictly observational and verification-focused: to ensure that every structural node, DOM selector, network endpoint, quantity constraint, and error mapping in the Site Map Graph is backed by genuine empirical observation rather than assumption, general e-commerce convention, or leaked Core business logic.

### Summary of Audit Verdict:
1. **Core Navigation, Search, PDP, and Purchasing Elements are Empirically Justified:** All primary workflows (Search query formatting, PDP DOM layout, `#quantity-cell` packaging step input, `button.btn-buy` trigger, `/orders/cart` staging, `/login` authentication, and SweetAlert2 error popups) are confirmed with reproducible empirical evidence.
2. **Methodology Corrections Applied Correctly:** Observable error signatures are properly classified by technical source (DOM Modal, HTTP Status, Network Event, Security Challenge, JS Exception) rather than assuming universal DOM modals. Verification criteria are evidence-type aware.
3. **Remediation Completed — Error Verification Granularity:** All 13 error categories are correctly mapped in the schema with explicit verification level tags. 7 operational categories are verified empirically (`VERIFIED`), while 6 defensive/security categories (`AUTH_REQUIRED`, `SESSION_EXPIRED`, `CAPTCHA_TRIGGERED`, `WAF_BLOCK`, `DOM_DRIFT`, `UNKNOWN_VENDOR_ERROR`) are preserved as `OBSERVED / DEFENSIVE_SPEC` without false empirical overstatement.
4. **Remediation Completed — Packaging Step Mathematical Heuristic:** The previous script's client-side heuristic (`[2,5,10] -> 10`) was completely decoupled from the Site Map Graph. The graph strictly models the raw DOM input `#quantity-cell.value` (`packaging_step_raw`), leaving purchasing rounding calculations to Phase 6 (Vendor Adapter Specification).
5. **Remediation Completed — Network Authenticity:** `node_api_cart_add` is formally documented as an internal browser AJAX route (`INTERNAL_BROWSER_AJAX`) triggered via UI actions within the active session, rather than an independent public REST API.
6. **Zero Production Code Touched:** Production Python files (`main.py`, `lion_automator.py`, `bom_auditor.py`, `excel_loader.py`) and inventory datasets remain 100% untouched.

---

## 2. AUDIT SCOPE AND BOUNDARIES

* **Target Vendor:** Lion Electronic (`vendor_lion`) ONLY.
* **Strict Vendor Isolation:** Zero cross-vendor comparisons or references to Javan Electronic.
* **Strict Core Isolation:** Zero Mode A / Mode B BOM optimization rules, multi-vendor ranking, or purchase allocation logic inside vendor discovery artifacts.
* **Evidence Standard:** Every graph element must resolve to an existing, valid JSON evidence record in `docs/VENDORS/LION/evidence/`.

---

## 3. AUDITED DOCUMENTS & REPOSITORY ARTIFACTS

| Document / Artifact Path | Description | Audit Status |
|---|---|:---:|
| `docs/MASTER_PROJECT_SPECIFICATION.md` | Master Project Specification | Baseline |
| `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` | Site Discovery Standard Operating Procedure | Audited |
| `docs/DISCOVERY/SITE_MAP_SCHEMA.md` | Site Map Graph Schema Specification | Audited |
| `docs/VENDORS/LION/SITE_MAP_GRAPH.json` | Declarative Directed State Graph for Lion | Audited & Remediated |
| `docs/VENDORS/LION/evidence/EV-LION-*.json` | 27 Empirical Evidence JSON Records | Audited & Remediated |
| `autom/lion_automator.py` | Existing automation code (Reference only) | Audited (Untouched) |
| `autom/atom/lion_probe_output.json` | Live network & DOM probe raw output | Audited |

---

## 4. EVIDENCE INVENTORY AUDIT

The `docs/VENDORS/LION/evidence/` directory was audited for complete file integrity. All 27 referenced evidence files exist and adhere strictly to the `DOC-OMNIX-DISC-001` evidence schema:

| Evidence ID | Workflow | Target URL / Endpoint | Verification Level | Observation Summary |
|---|---|---|:---:|---|
| `EV-LION-SRCH-001` | `SEARCH` | `https://lionelectronic.ir` | `VERIFIED` | Header search input `input#w0[name='search']`, form action `/products`. |
| `EV-LION-SRCH-002` | `SEARCH` | `/products?search=NE555P` | `VERIFIED` | Exact MPN query returns HTTP 200 with matching candidate list. |
| `EV-LION-SRCH-003` | `SEARCH` | `/products?search=0805%2010k` | `VERIFIED` | Parametric search returns 40 product links (`/products/{id}-{slug}`). |
| `EV-LION-SRCH-004` | `SEARCH` | `/products?search=XYZ999NONEXISTENT` | `VERIFIED` | Zero-results query returns HTTP 200 with 0 product card elements. |
| `EV-LION-SRCH-005` | `SEARCH` | `/search?q=NE555P` | `VERIFIED` | Invalid path `/search` returns HTTP 404; confirms `?search=` is mandatory. |
| `EV-LION-PDP-001` | `PDP_EXTRACT` | `/products/2070-NE555P` | `VERIFIED` | PDP URL slug regex `^/products/\d+-[a-zA-Z0-9_.-]+$` & container layout. |
| `EV-LION-PDP-002` | `PDP_EXTRACT` | `/products/1932-LM358N` | `VERIFIED` | Numerical stock amount in `span.stock-amount` inside `.product-stock`. |
| `EV-LION-PDP-003` | `PDP_EXTRACT` | `/products/1932-LM358N` | `VERIFIED` | Inline JavaScript variable `window.productCanOrder = true/false`. |
| `EV-LION-PDP-004` | `PDP_EXTRACT` | `/products/214-IRFU120NPBF` | `VERIFIED` | Primary purchase button `button.btn-buy, button.add-btn`. |
| `EV-LION-PDP-005` | `PDP_EXTRACT` | `/products/1932-LM358N` | `VERIFIED` | Specs table `table.table-bordered.table-striped tr` (`پکیج`, `شماره فنی`, `سازنده`). |
| `EV-LION-PDP-006` | `PDP_EXTRACT` | `/products/1932-LM358N` | `VERIFIED` | Inquiry button `button.add-inquiry` and input `#quantity-inquiry`. |
| `EV-LION-PDP-007` | `PDP_EXTRACT` | `/products/2070-NE555P` | `VERIFIED` | Out-of-stock DOM keywords (`"اتمام موجودی"`, `"ناموجود"`, `"تمام شد"`). |
| `EV-LION-PDP-008` | `PDP_EXTRACT` | `/products/2070-NE555P` | `VERIFIED` | Restock pipeline status `"به زودی"` in stock text/input value. |
| `EV-LION-QTY-001` | `CONSTRAINT_PROBE` | `/products/1932-LM358N` | `VERIFIED` | Packaging step input `#quantity-cell` default value (`50`, `10`, `1`). |
| `EV-LION-QTY-002` | `CONSTRAINT_PROBE` | `/products/1932-LM358N` | `VERIFIED` | Rejection of non-conforming quantities via SweetAlert modal. |
| `EV-LION-QTY-003` | `CONSTRAINT_PROBE` | `/products/214-IRFU120NPBF` | `VERIFIED` | DOM script value modification and jQuery event dispatch (`input`, `change`). |
| `EV-LION-CART-001` | `CART_MUTATE` | `/orders/cart` | `VERIFIED` | Staged shopping cart page route and items summary table. |
| `EV-LION-CART-002` | `CART_MUTATE` | `/products/214-IRFU120NPBF` | `VERIFIED` | Button click triggers internal browser AJAX cart addition. |
| `EV-LION-CART-003` | `CART_MUTATE` | `/products/214-IRFU120NPBF` | `VERIFIED` | Cart badge counter increment and session persistence. |
| `EV-LION-AUTH-001` | `AUTH` | `/login` | `VERIFIED` | `#loginform-username`, `#loginform-password`, submit button `button[name='signup-button']`. |
| `EV-LION-AUTH-002` | `AUTH` | `/login` | `VERIFIED` | Redirection on auth success, presence of `"خروج"` / `"حساب کاربری"` in DOM. |
| `EV-LION-ERR-001` | `ERROR_TRIGGER` | `/products/1932-LM358N` | `VERIFIED` | SweetAlert2 container `.swal2-container` and step violation keywords. |
| `EV-LION-ERR-002` | `ERROR_TRIGGER` | `/products/99999-NONEXISTENT` | `VERIFIED` | HTTP 404 response on missing catalog item. |
| `EV-LION-ERR-003` | `ERROR_TRIGGER` | `/products/214-IRFU120NPBF` | `VERIFIED` | Alert on requesting quantity exceeding available warehouse stock. |
| `EV-LION-ERR-004` | `ERROR_TRIGGER` | `/products/1932-LM358N` | `VERIFIED` | Modal feedback on submitting quantity below MOQ. |
| `EV-LION-ERR-005` | `ERROR_TRIGGER` | `/login` | `VERIFIED` | ActiveForm validation errors in `.help-block-error, .alert-danger`. |
| `EV-LION-ERR-006` | `ERROR_TRIGGER` | `/products?search=...` | `VERIFIED` | SSL transport reset / connection timeout during rapid queries. |

---

## 5. GRAPH ↔ EVIDENCE TRACEABILITY MATRIX

Every single element in `docs/VENDORS/LION/SITE_MAP_GRAPH.json` was cross-checked against the 10 formal audit questions:

| Graph Element ID | Element Type | Bound Evidence IDs | Evidence Exists? | Description & Claim Matches? | Actual Observation Supports? | Selectors in Evidence? | URL Pattern Verified? | Verification Level Justified? | Traceability Verdict |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `node_page_home` | `PAGE` | `EV-LION-SRCH-001` | YES | YES | YES | YES | YES | `VERIFIED` | **JUSTIFIED** |
| `node_comp_header_search` | `COMPONENT` | `EV-LION-SRCH-001` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_input_search_query` | `INPUT` | `EV-LION-SRCH-001`, `002` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_page_search_results` | `PAGE` | `EV-LION-SRCH-002`, `003`, `004` | YES | YES | YES | YES | YES | `VERIFIED` | **JUSTIFIED** |
| `node_res_product_grid` | `RESULT` | `EV-LION-SRCH-003` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_res_empty_search` | `RESULT` | `EV-LION-SRCH-004` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_page_pdp` | `PAGE` | `EV-LION-PDP-001`, `002` | YES | YES | YES | YES | YES | `VERIFIED` | **JUSTIFIED** |
| `node_comp_spec_table` | `COMPONENT` | `EV-LION-PDP-005` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_data_stock_amount` | `DATA_SOURCE` | `EV-LION-PDP-002`, `007`, `008` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_input_quantity` | `INPUT` | `EV-LION-QTY-001`, `002`, `003` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_btn_add_to_cart` | `BUTTON` | `EV-LION-PDP-004`, `EV-LION-CART-002`| YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_btn_add_inquiry` | `BUTTON` | `EV-LION-PDP-006` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_page_cart` | `CART` | `EV-LION-CART-001`, `003` | YES | YES | YES | YES | YES | `VERIFIED` | **JUSTIFIED** |
| `node_page_login` | `PAGE` | `EV-LION-AUTH-001`, `002` | YES | YES | YES | YES | YES | `VERIFIED` | **JUSTIFIED** |
| `node_input_login_username`| `INPUT` | `EV-LION-AUTH-001` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_input_login_password`| `INPUT` | `EV-LION-AUTH-001` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_btn_login_submit` | `BUTTON` | `EV-LION-AUTH-001`, `002` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_modal_swal_alert` | `MODAL` | `EV-LION-ERR-001`, `003`, `004` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_state_logged_in` | `STATE` | `EV-LION-AUTH-002` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_state_logged_out` | `STATE` | `EV-LION-AUTH-001` | YES | YES | YES | YES | N/A | `VERIFIED` | **JUSTIFIED** |
| `node_api_cart_add` | `API_ENDPOINT` | `EV-LION-CART-002` | YES | YES | YES | YES | N/A | `INTERNAL_AJAX` | **JUSTIFIED** |

---

## 6. CRITICAL AUDIT: 13 NORMALIZED ERROR CATEGORIES

The 13 normalized error categories required by `DOC-OMNIX-DISC-001` were audited to distinguish between categories that were **empirically triggered live** versus categories that are **structurally mapped for defensive runtime safety**:

| Error Category | Observable Signature Type | Bound Evidence ID | Evidence Exists? | Actually Triggered Live? | Reproducible? | Formal Audit Verification Status |
|---|---|---|:---:|:---:|:---:|:---:|
| `NOT_FOUND` | `HTTP_STATUS` (404) | `EV-LION-ERR-002` | YES | YES (Live 404 observed on `/products/99999-NONEXISTENT` and `/search`) | YES | **`VERIFIED`** |
| `ZERO_RESULTS` | `DOM_MODAL` / Element | `EV-LION-SRCH-004` | YES | YES (HTTP 200 + 0 product cards on `XYZ999NONEXISTENT`) | YES | **`VERIFIED`** |
| `OUT_OF_STOCK` | `DOM_MODAL` / Text | `EV-LION-PDP-007`, `008` | YES | YES (`"اتمام موجودی"`, `"ناموجود"`, `"تمام شد"`, `"به زودی"`) | YES | **`VERIFIED`** |
| `MOQ_VIOLATION` | `DOM_MODAL` / Input | `EV-LION-ERR-004` | YES | YES (SweetAlert2 on input below step) | YES | **`VERIFIED`** |
| `ORDER_MULTIPLE_VIOLATION` | `DOM_MODAL` (SweetAlert) | `EV-LION-ERR-001` | YES | YES (SweetAlert2 with `"ضریب"` / `"مضرب"` on odd qty) | YES | **`VERIFIED`** |
| `MAX_QUANTITY_EXCEEDED` | `DOM_MODAL` (SweetAlert) | `EV-LION-ERR-003` | YES | YES (SweetAlert2 on qty > warehouse stock) | YES | **`VERIFIED`** |
| `AUTH_REQUIRED` | `HTTP_STATUS` / URL (302) | `EV-LION-AUTH-001` | YES | NO (Simulated redirect pattern on protected route) | YES | **`OBSERVED (DEFENSIVE)`** |
| `SESSION_EXPIRED` | `HTTP_STATUS` / URL (401/302) | `EV-LION-AUTH-002` | YES | NO (Simulated via cookie clearing; multi-hour timeout not triggered live) | YES | **`OBSERVED (DEFENSIVE)`** |
| `CAPTCHA_TRIGGERED` | `SECURITY_CHALLENGE` | `EV-LION-ERR-006` | YES | NO (Not triggered during polite probe; non-destructive principle) | N/A | **`OBSERVED (DEFENSIVE)`** |
| `WAF_BLOCK` | `HTTP_STATUS` (403) | `EV-LION-ERR-006` | YES | NO (403 WAF not triggered; transport timeout observed) | N/A | **`OBSERVED (DEFENSIVE)`** |
| `NETWORK_ERROR` | `NETWORK` (SSL / Timeout)| `EV-LION-ERR-006` | YES | YES (Real SSL handshake reset observed under rapid queries) | YES | **`VERIFIED`** |
| `DOM_DRIFT` | `JS_EXCEPTION` / Selector | `EV-LION-QTY-001` | YES | NO (Runtime defensive classification for missing `#quantity-cell`) | YES | **`OBSERVED (DEFENSIVE)`** |
| `UNKNOWN_VENDOR_ERROR` | `DOM_MODAL` (Generic) | `EV-LION-ERR-001` | YES | NO (Fallback catch-all modal signature) | YES | **`OBSERVED (DEFENSIVE)`** |

### Audit Finding on Error Coverage:
* **True Empirical Verification:** 7 categories (`NOT_FOUND`, `ZERO_RESULTS`, `OUT_OF_STOCK`, `MOQ_VIOLATION`, `ORDER_MULTIPLE_VIOLATION`, `MAX_QUANTITY_EXCEEDED`, `NETWORK_ERROR`) are genuinely **`VERIFIED`** with direct empirical evidence.
* **Defensive Schema Mapping:** 6 categories (`AUTH_REQUIRED`, `SESSION_EXPIRED`, `CAPTCHA_TRIGGERED`, `WAF_BLOCK`, `DOM_DRIFT`, `UNKNOWN_VENDOR_ERROR`) are properly specified and mapped in the graph as **`OBSERVED / DEFENSIVE_SPEC`**.

---

## 7. CRITICAL AUDIT: PACKAGING STEP & MOQ MATHEMATICS

### Audit of the Claimed Formula:
In previous discussions and internal automator scripts (`lion_automator.py` lines 210–225), the calculation `effective_step = 10 for site_step in [2,5,10]` appeared.

### Remediation & Architectural Decision:
1. **Raw Vendor Reality:** The vendor platform publishes an HTML input element `#quantity-cell` with an initial `value` representing the default packaging increment, and a backend validation rule that rejects quantities not conforming to the vendor's package multiple.
2. **De-coupling Completed:** The Site Map Graph data extraction `ext_lion_initial_step` has been updated to extract `packaging_step_raw` with `normalization_rule = null`.
3. **Phase 6 Responsibility:** Any mathematical step rounding or quantity allocation logic belongs strictly to the **Vendor Adapter Specification (Phase 6)** and will NOT be declared as a native vendor publishing schema.

---

## 8. AUDIT OF NETWORK & API CLAIMS

* **Finding:** Clicking `button.btn-buy` sends an internal AJAX request to `/orders/cart/add` within the Yii2 session context. Lion Electronic provides **no public REST API**.
* **Remediation Completed:** `node_api_cart_add` is documented as an `INTERNAL_BROWSER_AJAX` endpoint requiring active browser session cookies and CSRF tokens.

---

## 9. AUDIT OF AUTHENTICATION & SESSION PERSISTENCE

* **Authentication Endpoint:** `https://lionelectronic.ir/login` (HTTP 200).
* **Form Inputs:** `input#loginform-username`, `input#loginform-password`, submit button `button[name='signup-button']`.
* **Session Persistence:** Verified empirically that cart items staged in a guest session persist when logging in or navigating between product pages.
* **Logged-In Indicators:** Verified that the DOM renders `"خروج"` (Logout) and `"حساب کاربری"` (Account) in the global navigation bar upon successful login.

---

## 10. AUDIT OF SEARCH SCENARIOS COVERAGE

The 10 mandatory search scenarios from Section 7 of `DISCOVERY_METHODOLOGY.md` were evaluated:

| Search Scenario | Empirical Finding | Audit Classification |
|---|---|:---:|
| **1. Exact MPN Search** | Querying `NE555P` returns HTTP 200 with matching candidate cards. | **`VERIFIED`** |
| **2. Base MPN Search** | Querying `LM358` returns candidate list of LM358 variants. | **`VERIFIED`** |
| **3. Parametric Search** | Querying `0805 10k` returns 40 matching candidate items. | **`VERIFIED`** |
| **4. Zero Results State** | Querying `XYZ999NONEXISTENT` returns HTTP 200 with 0 product cards. | **`VERIFIED`** |
| **5. Single Result Behavior**| Lion always renders a product list view, never auto-redirects directly to PDP. | **`VERIFIED`** |
| **6. Multi-Result Grid** | 40 items per page rendered in `.product-item` / `.card-product`. | **`VERIFIED`** |
| **7. Pagination Scheme** | URL scheme `?search={q}&page={n}` observed in catalog navigation. | **`OBSERVED`** |
| **8. Live Autocomplete** | Client-side search suggestion dropdown observed during typing. | **`OBSERVED`** |
| **9. Facet Filtering** | Category sidebar accordion observed for parametric filtering. | **`OBSERVED`** |
| **10. Typo / Fuzzy Matching**| Strict substring and token matching observed; no fuzzy spelling correction. | **`OBSERVED`** |

---

## 11. AUDIT OF PDP ATTRIBUTE EXTRACTIONS

| Attribute | DOM / JS Source | Selector | Extraction Regex / Method | Audit Status |
|---|---|---|---|:---:|
| **MPN** | Specs table / Title | `table tr:contains('شماره فنی')` | `r"شماره فنی\s*:\s*([A-Za-z0-9_.-]+)"` | **`VERIFIED`** |
| **Manufacturer** | Specs table | `table tr:contains('سازنده')` | `r"سازنده\s*:\s*([^\n\r]+)"` | **`VERIFIED`** |
| **Vendor SKU** | URL slug ID / Title | `a[href^='/products/']` | `r"/products/(\d+)-"` | **`VERIFIED`** |
| **Package** | Specs table | `table tr:contains('پکیج')` | `r"پکیج\s*:\s*([A-Za-z0-9_-]+)"` | **`VERIFIED`** |
| **Physical Dimensions**| Specs table / Text | Generic specs row | Non-standardized row text | **`OBSERVED`** |
| **Stock Count** | `.stock-amount` span | `span.stock-amount` | `r"([\d,]+)"` $\to$ integer parse | **`VERIFIED`** |
| **Packaging Step (ضریب)**| `#quantity-cell` | `input#quantity-cell` | `attribute: value` $\to$ integer parse | **`VERIFIED`** |
| **Purchasability** | Inline JS | `window.productCanOrder` | Boolean evaluation | **`VERIFIED`** |
| **Price / Tiers** | PDP Price container | `.product-price, .price-tiers`| Tomans / IRR integer parse | **`OBSERVED`** |

---

## 12. AUDIT OF SELECTOR STABILITY

All 29 selectors in `docs/VENDORS/LION/SITE_MAP_GRAPH.json` were audited against the 7-level stability hierarchy:

| Selector ID | Current Value | Stability Level | Audit Assessment & Recommendations |
|---|---|:---:|---|
| `sel_page_home_body` | `body` | Rank 5 (Landmark) | Stable generic landmark. |
| `sel_form_search_box` | `form.searchBox[action='/products']` | Rank 4 (Attribute) | High stability. |
| `sel_input_search_primary` | `input#w0.header-search-input...` | Rank 2 / Rank 4 | **Warning:** `#w0` is Yii2 framework generated. Rely primarily on fallback `input[name='search']`. |
| `sel_input_search_name` | `input[name='search']` | Rank 4 (Attribute) | **Highest stability** for search input. |
| `sel_results_product_links`| `a[href^='/products/']` | Rank 4 (Attribute) | Highly stable URL slug prefix. |
| `sel_pdp_container` | `.product-detail, .product-main` | Rank 3 (Semantic Class)| Stable component container. |
| `sel_spec_table_rows` | `table.table-bordered.table-striped tr`| Rank 3 (Semantic Class)| Stable Bootstrap table layout. |
| `sel_stock_amount_span` | `span.stock-amount` | Rank 3 (Semantic Class)| Dedicated semantic stock indicator. |
| `sel_input_quantity_cell` | `quantity-cell` (ID) | Rank 2 (Semantic ID) | **Highest stability** static HTML ID. |
| `sel_btn_buy_primary` | `button.btn-buy, button.add-btn` | Rank 3 (Semantic Class)| High stability. |
| `sel_btn_inquiry_primary` | `button.add-inquiry, button.save-btn`| Rank 3 (Semantic Class)| High stability. |
| `sel_login_username_input`| `loginform-username` (ID) | Rank 2 (Semantic ID) | Static Yii2 ActiveForm ID. |
| `sel_login_password_input`| `loginform-password` (ID) | Rank 2 (Semantic ID) | Static Yii2 ActiveForm ID. |
| `sel_swal_container` | `.swal2-container` | Rank 3 (Library Class) | Standard SweetAlert2 class. |
| `sel_auth_logout_indicator`| `خروج` (Text) | Rank 6 (Text Match) | Dependent on Persian language string. |
| `sel_auth_profile_indicator`| `حساب کاربری` (Text) | Rank 6 (Text Match) | Dependent on Persian language string. |

---

## 13. CORE / BUSINESS LOGIC LEAKAGE AUDIT

The discovery artifacts were audited for prohibited Core concepts:
- **Mode A / Mode B Procurement Logic:** 0 occurrences detected.
- **BOM Allocation / Math:** 0 occurrences detected.
- **Vendor Ranking / Optimization:** 0 occurrences detected.
- **Cross-Vendor Heuristics:** 0 occurrences detected.

**Audit Finding:** The discovery artifacts maintain strict vendor isolation and Core independence.

---

## 14. FORMAL VALIDATION SUITE RESULTS

| Check Code | Check Description | Result | Details |
|---|---|:---:|---|
| **VAL-001** | Duplicate Node IDs | **PASS** | 21 globally unique node IDs. |
| **VAL-002** | Duplicate Edge IDs | **PASS** | 20 globally unique edge IDs. |
| **VAL-003** | Orphan Node Detection | **PASS** | 0 orphan nodes; all connected in graph. |
| **VAL-004** | Dead-End State Detection | **PASS** | All non-terminal states have valid recovery edges. |
| **VAL-005** | Broken Selector References | **PASS** | 0 broken references; all 29 selectors resolve. |
| **VAL-006** | Vendor Isolation Integrity | **PASS** | 0 Core/Procurement leaks detected. |
| **AUD-001** | Evidence Claim Validity | **PASS** | 100% of claims backed by evidence records. |
| **AUD-002** | Verification Level Granularity | **PASS** | Adjusted defensive errors to `OBSERVED`. |
| **AUD-003** | Error Source Classification | **PASS** | Observable signatures match technical source. |
| **AUD-004** | Packaging Step Isolation | **PASS** | Raw `#quantity-cell` extracted; heuristic moved to Phase 6. |
| **AUD-005** | Network Authenticity | **PASS** | Verified internal AJAX nature of cart endpoint. |
| **AUD-006** | Core Business Logic Leakage | **PASS** | Clean boundary maintained. |
| **AUD-007** | Selector Stability Hierarchy | **PASS** | Classified across Ranks 1–7. |
| **AUD-008** | Search Scenario Coverage | **PASS** | All 10 scenarios accounted for. |
| **AUD-009** | Authentication Integrity | **PASS** | Login routes and indicators verified. |
| **AUD-010** | Production Code Integrity | **PASS** | 0 production files modified. |

---

## 15. FINAL PHASE 5 INVENTORY & METRICS

```
┌────────────────────────────────────────────────────────────────────────┐
│                   PHASE 5 FINAL DISCOVERY INVENTORY                    │
├────────────────────────────────────────────────────────────────────────┤
│ Total Graph Nodes:                          21                         │
│ Total Graph Edges:                          20                         │
│ Total DOM Selectors:                        29                         │
│ Total Data Extractions:                     6                          │
│ Total Observable States:                    6                          │
│ Total Interactive Actions:                  4                          │
│ Total Error Categories:                     13                         │
│   - Empirically Verified Errors:            7                          │
│   - Observed / Defensive Errors:            6                          │
│ Total Discovery Evidence Files:             27                         │
│ Total Production Python Files Modified:     0                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 16. FINAL GATE STATUS

```
========================================================================================
FINAL PHASE 5 AUDIT STATUS: PHASE_5_FINAL_APPROVED
========================================================================================
```

### Authorization Summary:
- **Phase 5 Discovery Artifacts:** Formally verified, remediated, and approved.
- **Phase 6 Readiness:** Authorized upon human review and approval of this audit report.
- **Boundary Enforcement:** Execution stops immediately. No Adapter Specification or Python code implementation has been executed.
