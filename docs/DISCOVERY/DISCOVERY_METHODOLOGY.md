# OMNIX VENDOR SITE DISCOVERY METHODOLOGY
## Standard Operating Procedure for Empirical Vendor Web & API Discovery

**Document Reference:** `DOC-OMNIX-DISC-001`  
**Version:** `1.0.0`  
**Status:** Approved Engineering Standard  
**Governing Specification:** `docs/MASTER_PROJECT_SPECIFICATION.md`  
**Target Output:** `docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json`

---

## 1. PURPOSE AND SCOPE

This document defines the official engineering methodology for discovering, analyzing, and documenting third-party electronic component distributor websites and APIs for the **Omnix** platform.

The objective of site discovery is to produce an empirical, evidence-backed, vendor-neutral **Site Map Graph** (`SITE_MAP_GRAPH.json`) for each vendor. This graph captures the exact navigable states, DOM elements, API endpoints, quantity constraints, and error behaviors of the vendor platform. 

This methodology guarantees that subsequent **Vendor Adapter Specifications** and implementations are built on verified technical evidence rather than assumptions, guesswork, or fragile reverse engineering.

---

## 2. DISCOVERY PRINCIPLES

All site discovery activities within Omnix must strictly adhere to the following seven core principles:

1. **Evidence-First:** No URL pattern, DOM selector, API route, packaging multiple, or error signature may be included in a vendor specification without a corresponding, verifiable Discovery Evidence Record.
2. **Zero-Assumption:** Never assume a vendor platform behaves like standard e-commerce software (e.g., WooCommerce, Shopify, Magento, or custom frameworks). Every behavior (search pagination, step rounding, cart mutation) must be observed and verified.
3. **Non-Destructive Discovery:** Discovery activities must never execute unauthorized financial transactions, trigger high-rate automated denial-of-service traffic, or degrade vendor infrastructure. Automated order placement stops strictly at the staged shopping cart inspection level.
4. **Repeatability:** Every discovered state transition, selector query, and network response must be reliably reproducible across independent clean sessions.
5. **Deterministic Documentation:** Observations must be recorded as typed, structured schemas (JSON/YAML) and formal state graphs, never as informal prose or unverified code snippets.
6. **Vendor Isolation:** Discovery of Vendor A (e.g., Lion Electronic) must remain strictly isolated from Vendor B (e.g., Javan Electronic). Cross-vendor heuristics are forbidden.
7. **No Production Code Modification During Discovery:** Discovery is an observational analysis phase. Production Python codebase files, database structures, and runtime configuration must not be modified during discovery.

---

## 3. DISCOVERY LIFECYCLE

The site discovery process executes across twelve sequential, dependency-aware phases:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               DISCOVERY LIFECYCLE PHASES                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase A: Domain / SSL / Platform Architecture Identification                           │
│ Phase B: Catalog Taxonomy & Search Mechanism Mapping                                   │
│ Phase C: Search Result Listing & Pagination Decomposition                              │
│ Phase D: Product Detail Page (PDP) Architecture Mapping                                │
│ Phase E: Product Identity, Package & Technical Attribute Extraction                    │
│ Phase F: Stock Availability, MOQ & Order Multiple Probing                              │
│ Phase G: Pricing Tier & Multi-Break Structure Extraction                               │
│ Phase H: Cart Mutation, Session State & Network Interception                           │
│ Phase I: Authentication, Session Lifespan & Cookie Persistence                         │
│ Phase J: Error Modals, Toast Alerts & Edge-State Mapping                               │
│ Phase K: Evidence Validation & Verification Level Sign-off                             │
│ Phase L: Declarative Site Map Graph Generation (`SITE_MAP_GRAPH.json`)                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Phase A: Domain / SSL / Platform Identification
* Identify the primary domain, subdomains, SSL/TLS configuration, CDN/WAF providers (e.g., Cloudflare, ArvanCloud), and underlying web stack (server-rendered MVC, SPA, jQuery, React, Vue).
* Record base URLs for catalog, search, authentication, and checkout routes.

### Phase B: Catalog and Search Architecture
* Inspect how search queries are accepted: URL query parameters (e.g., `GET /products?search=NE555P`), POST forms, or background AJAX/GraphQL endpoints.
* Identify search input DOM elements, debounce intervals, auto-suggest popups, and category dropdown filters.

### Phase C: Search Result Mapping
* Observe behavior across distinct search outcomes:
  1. Exact unique match redirecting directly to a Product Detail Page (PDP).
  2. Multi-item matching returning a paginated product grid or table.
  3. Zero-results empty state.
* Document candidate product card selectors (title link, thumbnail, vendor SKU snippet, price snippet, stock indicator).

### Phase D: Product Detail Page Mapping
* Map the structural anatomy of the PDP: breadcrumbs, product title, main imagery, technical specification table, datasheet anchors, stock badge container, quantity input form, and purchase button.

### Phase E: Product Identity / Package / Technical Attribute Discovery
* Identify where the following attributes reside across the DOM, embedded JSON (e.g., Schema.org / JSON-LD), global JavaScript objects (e.g., `window.productData`), and specification tables:
  - Manufacturer Part Number (MPN)
  - Manufacturer / Brand name
  - Vendor SKU / Catalog Number
  - Package / Footprint (e.g., DIP-8, SOIC-8, SMD 0805, TO-220)
  - Physical Case Dimensions (e.g., Metric 2012 vs Imperial 0805)
  - Electrical Specs (Resistance, Capacitance, Voltage rating, Tolerance, Power rating)

### Phase F: Stock / MOQ / Order Multiple Discovery
* Empirically determine how the vendor enforces purchasing quantities:
  - Numerical stock count vs. qualitative availability badge ("In Stock", "Out of Stock", "Call/Inquiry", "Coming Soon").
  - Minimum Order Quantity (MOQ).
  - Order Multiple / Packaging Step (ضریب سفارش / مضرب بسته‌بندی): Determine if the site enforces packaging increments (e.g., reels of 100, strips of 10, cut tape of 5, tubes of 25).
  - Probe input validation: Observe client-side JavaScript input constraints versus server-side response on invalid quantities.

### Phase G: Pricing and Price-Tier Discovery
* Locate unit prices, currency denomination (IRR / Tomans / USD), tax inclusion status, and volume price-break tables (e.g., 1–9 pcs, 10–49 pcs, 50–99 pcs, 100+ pcs).

### Phase H: Cart Mutation and Network Discovery
* Intercept the exact network request triggered by clicking "Add to Cart":
  - HTTP Method (POST / PUT / XHR).
  - Request URL, headers, cookies, CSRF tokens, and payload structure (JSON vs `application/x-www-form-urlencoded`).
  - Response format (JSON status, HTML fragment, redirect).
  - UI state mutations (cart badge count increment, sliding drawer open, toast popup).

### Phase I: Authentication and Session Lifecycle
* Trace the login workflow (`/login`): username/mobile/email inputs, password fields, remember-me options, OTP triggers, and session cookies.
* Measure session lifespan and verify whether cart items persist across guest-to-authenticated transitions.

### Phase J: Error / Modal / Edge-State Discovery
* Intentionally trigger negative edge cases to capture DOM signatures:
  - Submitting quantity below MOQ.
  - Submitting quantity violating Order Multiple (e.g., entering 7 when multiple is 5).
  - Submitting quantity exceeding available vendor stock.
  - Adding a discontinued or inquiry-only item.
  - Session timeout / expired CSRF token.
  - WAF / Captcha challenge triggers.

### Phase K: Evidence Validation
* Cross-reference all observed behaviors against the Evidence Collection Standard. Ensure all critical selectors and transitions achieve `VERIFIED` status.

### Phase L: Site Map Graph Generation
* Compile the verified discovery data into the standard `docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json` format adhering strictly to `SITE_MAP_SCHEMA.md`.

---

## 4. EVIDENCE COLLECTION STANDARD

Every discovered behavior, selector, and endpoint must be recorded as an individual Discovery Evidence Record.

```json
{
  "evidence_id": "EV-LION-PDP-001",
  "vendor_id": "vendor_lion",
  "workflow": "PRODUCT_DETAIL_EXTRACTION",
  "timestamp": "2026-09-16T15:45:00Z",
  "entry_state": "PAGE_LOADED",
  "url": "https://lionelectronic.ir/products/2070-NE555P",
  "action": "Inspect technical specification table and stock container",
  "expected_observation": "Locate package type DIP-8 and available stock count",
  "actual_observation": "Package is displayed in table row with header 'پکیج'; stock is in span.stock-amount with integer text '145'",
  "selector": "table.technical-specs tr:has(td:contains('پکیج')) td:nth-child(2), span.stock-amount",
  "network_request": null,
  "network_response": null,
  "screenshot_reference": "evidence/screenshots/EV-LION-PDP-001.png",
  "har_reference": "evidence/har/EV-LION-PDP-001.har",
  "verification_status": "VERIFIED",
  "verifier": "DevTools Inspector & DOM Validation Suite",
  "notes": "Stock amount text requires regex strip of non-digit characters."
}
```

### Required Fields for Evidence Records:
* `evidence_id`: Unique identifier formatted as `EV-{VENDOR}-{WORKFLOW}-{INDEX}` (e.g., `EV-JAVAN-SRCH-001`).
* `vendor_id`: Canonical vendor ID string (e.g., `vendor_lion`, `vendor_javan`).
* `workflow`: Functional area (`SEARCH`, `PDP_EXTRACT`, `CONSTRAINT_PROBE`, `CART_MUTATE`, `AUTH`, `ERROR_TRIGGER`).
* `timestamp`: ISO-8601 UTC timestamp of observation.
* `entry_state`: Pre-condition state before action execution.
* `url`: Exact URL where the observation occurred.
* `action`: Specific human or automation action executed.
* `expected_observation`: Engineering hypothesis.
* `actual_observation`: Empirical result observed.
* `selector`: CSS selector, XPath, or DOM query identified.
* `network_request`: Method, URL, headers, and payload if network traffic was involved.
* `network_response`: HTTP status code and response payload.
* `screenshot_reference`: Path to visual evidence capture.
* `har_reference`: Path to HTTP Archive (.har) capture.
* `verification_status`: Status enum (`UNVERIFIED`, `OBSERVED`, `REPRODUCED`, `VERIFIED`).
* `verifier`: Identity of engineer or automated discovery suite.
* `notes`: Technical constraints, regex patterns, or edge-case notes.

---

## 5. SELECTOR DISCOVERY & STABILITY RULES

When capturing DOM selectors, candidate queries must be classified by structural stability.

### 5.1 Selector Stability Hierarchy (Ranked by Preference)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Rank 1: Dedicated Semantic Test/Data Attributes (Highest Stability)    │
│         [data-testid="add-to-cart"], [data-sku="2070-NE555P"]          │
├────────────────────────────────────────────────────────────────────────┤
│ Rank 2: Unique, Static Semantic HTML IDs                               │
│         #quantity-cell, #loginform-username, #search-input             │
├────────────────────────────────────────────────────────────────────────┤
│ Rank 3: Semantic, Stable BEM/Component CSS Classes                     │
│         button.btn-buy, span.stock-amount, table.product-specifications│
├────────────────────────────────────────────────────────────────────────┤
│ Rank 4: Attribute Selectors with Partial/Prefix Matches                │
│         input[name='signup-button'], a[href*='/products/']             │
├────────────────────────────────────────────────────────────────────────┤
│ Rank 5: Structural XPath with Semantic Landmarks                       │
│         //table[@class='specs']//tr[td[contains(text(),'Package')]]/td │
├────────────────────────────────────────────────────────────────────────┤
│ Rank 6: Text-Based Matchers (Subject to Translation/Spelling Changes)  │
│         button:contains("افزودن به سبد خرید")                          │
├────────────────────────────────────────────────────────────────────────┤
│ Rank 7: Auto-Generated / Dynamic / Obfuscated Class Names (FORBIDDEN)  │
│         div.css-1r8k3p9, button.jss142 (Do NOT use in Site Maps)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. NETWORK DISCOVERY PROTOCOL

When vendor platforms utilize client-side API requests for searching, loading product variants, or adding items to carts, discovery must intercept and document the raw HTTP exchange:

1. **Endpoint Identity:** HTTP Method (`GET`, `POST`, `PUT`, `DELETE`), Path, and URL Query Parameters.
2. **Authentication & Authorization Headers:** `Cookie`, `Authorization: Bearer <token>`, `X-CSRF-Token`, custom vendor headers (`X-Requested-With: XMLHttpRequest`).
3. **Payload Structure:** MIME Type (`application/json`, `multipart/form-data`, `application/x-www-form-urlencoded`) and JSON schema definition.
4. **Response Contract:** HTTP Status Codes (200 OK, 400 Bad Request, 401 Unauthorized, 422 Unprocessable Entity, 429 Rate Limited), Content-Type, and full response JSON schema.
5. **Session Mutation:** `Set-Cookie` directives and session token renewal mechanisms.

---

## 7. SEARCH DISCOVERY PROTOCOL

The search discovery workflow must empirically verify the following ten scenarios for each vendor:

1. **Exact MPN Search:** Querying an unambiguous, exact manufacturer part number (e.g. `NE555P`, `LM358N`, `STM32F103C8T6`).
2. **Base MPN Search:** Querying base silicon numbers stripped of packaging suffixes (e.g. searching `LM358` instead of `LM358N`).
3. **Parametric / Keyword Search:** Querying generic components (e.g. `Resistor 10k 0805 1%`, `Capacitor 100uF 25V SMD`).
4. **Zero Results State:** Querying non-existent strings (e.g. `XYZ999NONEXISTENT`) to identify the empty-state container and message selectors.
5. **Single Result Redirect:** Detecting whether a unique exact search result redirects directly to the PDP or renders a 1-item search grid.
6. **Multi-Result Grid:** Inspecting result card loops, grid layouts, and product count headers.
7. **Pagination Controls:** Discovering pagination URL schemes (`?page=2`, `?p=2`), "Load More" buttons, or infinite scroll mechanisms.
8. **Live Autocomplete / Dropdown:** Discovering instant search preview dropdowns triggered during input typing.
9. **Category & Facet Filtering:** Mapping filter checkboxes (In Stock Only, SMD, DIP, Manufacturer filters).
10. **Typo / Fuzzy Matching:** Observing whether the search engine performs fuzzy correction or strict alphanumeric substring matching.

---

## 8. PRODUCT DISCOVERY & ATTRIBUTE MAPPING

Every candidate component discovered must be mapped against the typed **CanonicalComponent** schema:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Canonical Field          │ Vendor Discovery Investigation Point                        │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Manufacturer Part Number │ PDP Header, Technical Specs table ('شماره فنی' / 'MPN'),    │
│                          │ Breadcrumb, Schema.org `mpn` JSON metadata.                 │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Manufacturer / Brand     │ Specs table ('سازنده' / 'Brand'), Product sub-header,       │
│                          │ Filter facets, Manufacturer logo image alt tag.             │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Vendor SKU / ECODE       │ Product title prefix, URL slug ID, SKU element text.        │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Package / Case Code      │ Specs table ('پکیج' / 'فوت پرینت'), Title suffix (DIP-8,    │
│                          │ SOIC-8, SMD-0805, TO-220, SOT-23).                          │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Physical Dimensions      │ Specs table ('ابعاد' / 'Size'), Metric (2012) vs Imperial   │
│                          │ (0805), Pitch spacing (2.54mm, 1.27mm, 0.5mm).              │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Electrical Ratings       │ Specs table ('ولتاژ', 'جریان', 'مقاومت', 'ظرفیت', 'توان',    │
│                          │ 'تلرانس', 'دمای کاری').                                     │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Live Stock Count         │ `.stock-amount`, `.product-stock`, `window.productStock`.   │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ MOQ & Order Multiple     │ Input `#quantity-cell` default value, input step attribute, │
│                          │ Warning badges ('حداقل سفارش: X عدد', 'ضریب بسته: Y عدد').  │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Volume Pricing Tiers     │ Price tier table (`table.price-tiers`), Volume discount     │
│                          │ badge containers.                                           │
└──────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 9. CART MUTATION & STATE MACHINE DISCOVERY

The cart discovery workflow must formally document the complete interaction cycle:

```
┌──────────────┐       ┌────────────────┐       ┌─────────────────┐       ┌────────────────┐
│ 1. PDP State │ ───►  │ 2. Set Qty     │ ───►  │ 3. Click Buy    │ ───►  │ 4. Intercept   │
│ In Stock     │       │ Respecting Step│       │ Action (Button) │       │ AJAX / Request │
└──────────────┘       └────────────────┘       └─────────────────┘       └───────┬────────┘
                                                                                  │
                       ┌──────────────────────────────────────────────────────────┘
                       ▼
             ┌───────────────────┐
             │ 5. Evaluate State │
             └─────────┬─────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ State A: Success             │ │ State B: Failure Modal       │
│ • Cart badge increments (+1) │ │ • SweetAlert2 modal (.swal2) │
│ • Toast / Drawer displays    │ │ • Error text parsed          │
│ • Cookie updated             │ │ • Recovery action identified │
└──────────────────────────────┘ └──────────────────────────────┘
```

---

## 10. ERROR TAXONOMY & OBSERVABLE SIGNATURES

When vendor platforms fail to fulfill an action or present an exceptional condition, the discovery engineer must map the observable signature into one of thirteen standard Omnix error categories.

Evidence sources must match the actual error mechanism (DOM modal, toast notification, HTTP response status, browser state, network event, URL transition, or security challenge). Not every error category requires a DOM selector or modal.

### 10.1 Normalized Error Categories and Evidence Sources

| Error Category | Primary Evidence Source | Description & Typical Signature |
|---|---|---|
| `NOT_FOUND` | HTTP Status / URL / DOM | HTTP 404 response, redirection to a 'not found' route, or missing product container. |
| `ZERO_RESULTS` | DOM Text / Component | Empty-search container, 0-match counter, or 'no products found' message. |
| `OUT_OF_STOCK` | DOM Text / Badge / State | 0-stock count, 'out of stock' badge, or disabled purchase button. |
| `MOQ_VIOLATION` | DOM Modal / Toast / Validation | Alert or modal indicating quantity entered is below the minimum order threshold. |
| `ORDER_MULTIPLE_VIOLATION` | DOM Modal / Toast / Validation | Alert or modal indicating quantity is not a valid multiple of the packaging step. |
| `MAX_QUANTITY_EXCEEDED` | DOM Modal / Toast / Validation | Alert indicating entered quantity exceeds vendor warehouse stock or purchase cap. |
| `AUTH_REQUIRED` | URL / DOM / HTTP 401 | Redirection to `/login`, modal prompt, or HTTP 401 response on protected actions. |
| `SESSION_EXPIRED` | HTTP 401/403 / URL / Cookie | Expiration of session cookies/tokens, CSRF token mismatch, or redirect to login. |
| `CAPTCHA_TRIGGERED` | Security State / DOM / Frame | Presentation of Cloudflare Turnstile, reCAPTCHA iframe, or challenge screen. |
| `WAF_BLOCK` | HTTP 403/503 / Network / State | Cloudflare / ArvanCloud 403 Forbidden screen, IP rate-limit page, or dropped connection. |
| `NETWORK_ERROR` | Network / Transport Event | Connection timeout, DNS resolution failure, network drop, or HTTP 5xx server error. |
| `DOM_DRIFT` | DOM Selector Inspection | Expected selector missing or structural HTML changes following vendor frontend updates. |
| `UNKNOWN_VENDOR_ERROR` | DOM / Network / Unhandled | Unclassified modal, popup, or unexpected API payload requiring manual triage. |

---

## 11. ANTI-BOT & SECURITY DISCOVERY RULES

During site discovery, security and bot-mitigation mechanisms must be **observed and documented only**:

* **Observational Profiling:** Document the presence of Cloudflare Turnstile, reCAPTCHA v2/v3, ArvanCloud security screens, and request rate-limiting thresholds.
* **No Bypass Tooling:** Do not deploy automated cracking tools, captcha bypass solvers, or credential stuffing during discovery.
* **Session Lifecycle:** Document how long an authenticated session remains valid when executing routine browser actions.

---

## 12. EVIDENCE VERIFICATION LEVELS

Every node, selector, network endpoint, and state transition in a Site Map must declare a formal Verification Level:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Level 1: UNVERIFIED                                                                    │
│ └── Node/selector/behavior is hypothesized based on general e-commerce patterns but    │
│     has not yet been empirically observed or tested on the live vendor website.        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Level 2: OBSERVED                                                                      │
│ └── Node/selector/behavior was observed once during a manual DevTools inspection,      │
│     network trace, or live crawl.                                                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Level 3: REPRODUCED                                                                    │
│ └── Node/selector/behavior was successfully tested and reproduced across multiple      │
│     clean browser sessions or independent test queries.                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Level 4: VERIFIED (Mandatory for Production Adapter Specifications)                    │
│ └── Formally verified: Empirical Observation + Reproducibility + Applicable Evidence  │
│     Artifacts + Contract Validation (where technically applicable).                    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 12.1 Evidence-Type Aware Verification Requirements
To prevent rigid, unachievable requirements, evidence artifacts must correspond directly to the technical nature of the graph element:

* **DOM Node / Selector:** Requires DOM inspection evidence and reproducibility across sessions. Visual screenshot is applicable where layout validation is relevant. (HAR trace is not mandatory for static DOM elements).
* **API Endpoint:** Requires HTTP network request/response evidence, status code, payload schema, and reproducibility. HAR capture is expected. (Visual screenshot is optional unless UI mutation is being validated).
* **HTTP / Network Error:** Requires HTTP response status, error body/headers, and network event logs. (DOM screenshot is irrelevant unless a visual error page was rendered).
* **Browser Security State (WAF/CAPTCHA):** Requires browser/network challenge evidence, HTTP response status (e.g. 403/503), and screenshot of challenge screen where applicable.
* **Page Node:** Requires URL pattern matching, HTTP 200 response, and reproducible navigation state.
* **Data Source:** Requires source-specific extraction verification (DOM text regex for spec tables; JSONPath for API responses; JS property for runtime variables).

*Rule: Every production-relevant graph element must have sufficient applicable evidence for its type and observed behavior.*

---

## 13. DISCOVERY COMPLETION & EXIT CRITERIA

A vendor platform is formally approved for **Phase 6: Vendor Adapter Specification** only when the following criteria are 100% satisfied:

- [ ] All 12 Discovery Lifecycle phases have been executed.
- [ ] 100% of required production graph elements achieve `VERIFIED` verification status with applicable evidence.
- [ ] Exact MPN, Base MPN, and Parametric search behaviors are documented with empirical evidence.
- [ ] Location of MPN, Manufacturer, Package, Size, and Specs are verified across PDP layouts.
- [ ] Packaging step (ضریب سفارش) and MOQ rounding rules are mathematically verified with test inputs.
- [ ] Add-to-Cart mutation payload and cart state transitions are captured with network/DOM evidence.
- [ ] All 13 normalized error categories must have verified observable signatures, where the signature may originate from DOM, browser state, HTTP/network response, or security challenge state as applicable.
- [ ] A validated, linted `SITE_MAP_GRAPH.json` file adhering to `SITE_MAP_SCHEMA.md` is compiled.
- [ ] **Zero production code was modified during discovery.**

