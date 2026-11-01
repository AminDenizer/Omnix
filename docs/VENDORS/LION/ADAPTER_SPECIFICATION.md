# LION ELECTRONIC VENDOR ADAPTER FORMAL SPECIFICATION
## Omnix Multi-Vendor Procurement Platform — Vendor Adapter Contract

**Document Reference:** `DOC-OMNIX-SPEC-LION-001`  
**Version:** `1.0.0`  
**Status:** Approved Engineering Specification  
**Vendor Identifier:** `vendor_lion`  
**Vendor Name:** Lion Electronic (`https://lionelectronic.ir`)  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/VENDORS/LION/SITE_MAP_GRAPH.json` (Phase 5 Approved Graph)
- `docs/VENDORS/LION/PHASE5_AUDIT_REPORT.md` (DOC-OMNIX-AUDIT-LION-001)

---

## 1. PURPOSE AND ARCHITECTURAL BOUNDARY

This document defines the formal, binding technical specification for the **Lion Electronic Vendor Adapter** (`LionVendorAdapter`).

The Adapter serves as the isolated translation layer between the vendor-agnostic **Omnix Core** and the vendor-specific web commerce platform of **Lion Electronic** (`lionelectronic.ir`).

```
┌────────────────────────────────────────────────────────────────────────┐
│                              OMNIX CORE                                │
│  • BOM Interpretation & Normalization                                  │
│  • Inventory Matching & Shortage Calculation                           │
│  • Procurement Modes (Mode A: Inventory-Based)                         │
│  • Multi-Vendor Discovery & Sourcing Orchestration                     │
│  • Deterministic Purchase Allocation & Optimization                   │
│  • Central Normalized Error Handling & Reporting                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Normalized Procurement Intent
                                    │ (Canonical Parts & Target Quantities)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   LION VENDOR ADAPTER (`vendor_lion`)                   │
│  • Lion URL & Route Handling (`/products`, `/login`, `/orders/cart`)   │
│  • Lion DOM Selector Execution (`#quantity-cell`, `.stock-amount`)     │
│  • Technical Spec Extraction (`شماره فنی`, `پکیج`, `سازنده`)           │
│  • Internal Browser AJAX Settle Time & Event Dispatching               │
│  • Raw Packaging Step Extraction (`packaging_step_raw`)                │
│  • SweetAlert2 & Lion Error Modal Translation                          │
│  • Result Normalization to IVendorAdapter Output Contracts            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Browser Automation Actions
                                    │ & Session Context
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    LION ELECTRONIC PLATFORM (WEB)                      │
│                  `https://lionelectronic.ir`                           │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Strict Core / Adapter Separation Rules
1. **Core Owns Business Logic:** Procurement modes (Mode A), BOM parsing, stock allocation, and cross-vendor pricing comparisons are owned exclusively by Core. The Lion Adapter contains zero BOM math and zero multi-vendor ranking logic.
2. **Adapter Owns Vendor Mechanics:** The Lion Adapter encapsulates all Lion-specific HTML IDs, CSS classes, URL patterns, Persian text strings, SweetAlert popup signatures, and Yii2 session tokens.
3. **Vendor Isolation:** The Lion Adapter is 100% standalone. It has no dependencies on, or shared code with, any other vendor adapter.
4. **Evidence-Backed Requirements:** Every selector, URL, state transition, and error condition specified herein is traceable to verified Phase 5 evidence records (`EV-LION-*`).

---

## 2. ADAPTER INTERFACE CONTRACT (`IVendorAdapter`)

The `LionVendorAdapter` must implement the conceptual `IVendorAdapter` contract. All operations accept typed inputs and return normalized data contracts.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   LION ADAPTER CONCEPTUAL OPERATIONS                   │
├────────────────────────────────────────────────────────────────────────┤
│ initialize(config)                    -> AdapterStatus                 │
│ search_part(query)                    -> SearchResultSet               │
│ resolve_product(url_or_sku)           -> ProductReference              │
│ inspect_product(product_ref)          -> ProductDetails                │
│ extract_product_data(dom_context)     -> CanonicalComponentDraft       │
│ inspect_stock(product_ref)            -> StockStatus                   │
│ determine_order_constraints(prod_ref) -> OrderConstraints              │
│ add_to_cart(product_ref, quantity)    -> CartMutationResult            │
│ inspect_cart()                        -> CartDetails                   │
│ authenticate(credentials)             -> AuthResult                    │
│ validate_session()                    -> SessionStatus                 │
│ recover_from_error(error_context)     -> RecoveryResult                │
│ close()                               -> void                          │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Normalized Data Contracts

#### A. `SearchResultSet` Contract
```json
{
  "vendor_id": "vendor_lion",
  "query": "0805 10k",
  "total_matches": 40,
  "is_exact_match": false,
  "items": [
    {
      "vendor_sku": "1497-0805W8F9103T5E",
      "mpn_hint": "0805W8F9103T5E",
      "title": "مقاومت SMD 0805 10K 1%",
      "pdp_url": "https://lionelectronic.ir/products/1497-0805W8F9103T5E",
      "thumbnail_url": "https://lionelectronic.ir/uploads/..."
    }
  ]
}
```

#### B. `ProductDetails` Contract
```json
{
  "vendor_id": "vendor_lion",
  "vendor_sku": "2070-NE555P",
  "pdp_url": "https://lionelectronic.ir/products/2070-NE555P",
  "mpn": "NE555P",
  "manufacturer": "Texas Instruments",
  "package_raw": "DIP-8",
  "stock_quantity": 145,
  "can_order": true,
  "is_inquiry_only": false,
  "raw_status_text": "موجود",
  "price_irr": 85000,
  "order_constraints": {
    "packaging_step_raw": 1,
    "moq_raw": 1
  }
}
```

#### C. `CartMutationResult` Contract
```json
{
  "vendor_id": "vendor_lion",
  "vendor_sku": "1932-LM358N",
  "requested_quantity": 50,
  "actual_quantity_staged": 50,
  "success": true,
  "error_category": null,
  "raw_vendor_message": "Added 50 units (Pack of 50)",
  "cart_total_items": 1
}
```

---

## 3. SEARCH MECHANISM SPECIFICATION

### 3.1 HTTP Routing & Form Structure
* **Primary Search URL:** `GET https://lionelectronic.ir/products?search={query}`
* **Query Parameter:** `search` (Mandatory; case-insensitive).
* **Form Action:** `/products` (Method: `GET`).
* **Search Input Selector:**
  * Primary: `input#w0.header-search-input.form-control[name='search']` (`EV-LION-SRCH-001`)
  * Stable Fallback: `input[name='search']` (`EV-LION-SRCH-001`, Rank 4 Attribute Matcher)
* **Placeholder:** `"Part Number ..."`

### 3.2 Search Response Scenarios
1. **Exact MPN Search (`EV-LION-SRCH-002`):**
   * Target: Exact part number (e.g. `NE555P`).
   * Behavior: Lion does **not** auto-redirect to PDP; it renders a search results page containing candidate cards matching the exact token.
2. **Parametric / Keyword Search (`EV-LION-SRCH-003`):**
   * Target: Multi-token query (e.g. `0805 10k`).
   * Behavior: Renders 40 matching items per page in `.products-list, .product-grid`. Product links conform to regex `^/products/(\d+)-([a-zA-Z0-9_.-]+)$`.
3. **Zero-Results Empty State (`EV-LION-SRCH-004`):**
   * Target: Non-existent query (e.g. `XYZ999NONEXISTENT`).
   * Behavior: Returns HTTP 200 rendering `.empty-result, .no-products, .alert-info` with 0 candidate product links.
4. **Invalid Search Routes (`EV-LION-SRCH-005`):**
   * `GET https://lionelectronic.ir/search?q=...` $\to$ **HTTP 404 Not Found**.
   * `GET https://lionelectronic.ir/products?q=...` $\to$ Redirects to category root `/products/category`.
   * **Adapter Rule:** The adapter must strictly use `?search={query}`.

---

## 4. PRODUCT DETAIL PAGE (PDP) SPECIFICATION

### 4.1 URL Architecture
* **Canonical URL Regex:** `^https://lionelectronic\.ir/products/(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.-]+)$` (`EV-LION-PDP-001`)
* **Example:** `https://lionelectronic.ir/products/2070-NE555P` (`product_id = 2070`, `slug = NE555P`).

### 4.2 Raw Vendor Data vs. Normalized Omnix Field Mapping

| Raw Lion DOM / JS Element | Selector / Extraction Rule | Normalized Adapter Field | Type | Evidence ID |
|---|---|---|:---:|:---:|
| URL Slug Prefix | `a[href^='/products/']` $\to$ `r"/products/(\d+)-"` | `vendor_sku` | `str` | `EV-LION-PDP-001` |
| Table Row `'شماره فنی'` | `table tr:has(td:contains('شماره فنی')) td:nth-child(2)` | `mpn` | `str` | `EV-LION-PDP-005` |
| Table Row `'سازنده'` | `table tr:has(td:contains('سازنده')) td:nth-child(2)` | `manufacturer` | `str` | `EV-LION-PDP-005` |
| Table Row `'پکیج'` | `table tr:has(td:contains('پکیج')) td:nth-child(2)` | `package_raw` | `str` | `EV-LION-PDP-005` |
| `span.stock-amount` | `span.stock-amount` $\to$ `r"([\d,]+)"` | `stock_quantity` | `int` | `EV-LION-PDP-002` |
| `window.productCanOrder` | `JS: window.productCanOrder` | `can_order` | `bool` | `EV-LION-PDP-003` |
| Text: `"به زودی"` | `span.stock-amount, input.quantity-cell` | `is_restock_pipeline` | `bool` | `EV-LION-PDP-008` |
| Text: `"اتمام موجودی"` | `.stock-status, .product-stock` | `is_out_of_stock` | `bool` | `EV-LION-PDP-007` |
| `input#quantity-cell` | `input#quantity-cell[value]` | `packaging_step_raw` | `int` | `EV-LION-QTY-001` |
| `button.add-inquiry` | `button.add-inquiry, button.save-btn` | `is_inquiry_only` | `bool` | `EV-LION-PDP-006` |

### 4.3 Stock and Purchasability Decision Matrix

```
┌─────────────────────────┬────────────────────────┬──────────────────────────────────────────┐
│ `window.productCanOrder` │ Stock Element Text     │ Adapter Normalized Status                │
├─────────────────────────┼────────────────────────┼──────────────────────────────────────────┤
│ `true`                  │ Integer (e.g. `2,900`) │ `IN_STOCK` (Stock = 2900, Direct Buy)    │
│ `false`                 │ `"به زودی"`            │ `RESTOCK_PIPELINE` (Stock = 0, No Cart)  │
│ `false`                 │ `"اتمام موجودی"`       │ `OUT_OF_STOCK` (Stock = 0, No Cart)      │
│ `false`                 │ Inquiry Button Present │ `INQUIRY_ONLY` (Commercial Quote Only)   │
│ `null / undefined`      │ 0 or empty             │ `UNAVAILABLE`                            │
└─────────────────────────┴────────────────────────┴──────────────────────────────────────────┘
```

---

## 5. PACKAGING, MOQ & QUANTITY CONSTRAINT BOUNDARY

### 5.1 Raw Vendor Property vs. Procurement Mathematics

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURAL BOUNDARY                          │
├────────────────────────────────────────────────────────────────────────┤
│ LION ADAPTER RESPONSIBILITY:                                           │
│ 1. Extract raw integer `packaging_step_raw` from `#quantity-cell.value`│
│ 2. Set exact requested integer in `#quantity-cell`                     │
│ 3. Detect SweetAlert packaging step violation modals on failure        │
├────────────────────────────────────────────────────────────────────────┤
│ OMNIX CORE / PROCUREMENT RESPONSIBILITY (PHASE 6+):                    │
│ 1. Evaluate shortage quantity against BOM demand                       │
│ 2. Apply step rounding: target_qty = ceil(needed / step) * step        │
│ 3. Handle MOQ snap and price break optimization                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Discovered Packaging Behaviors (`EV-LION-QTY-001`, `002`, `003`)
* **Default Spinbox Value:** `#quantity-cell` initializes with the vendor's minimum packaging increment (e.g. `50` for 0603 SMD chip components, `10` for standard SMD reels, `1` for discrete DIP ICs).
* **Validation Enforcement:** Entering a quantity not conforming to the vendor packaging increment or exceeding available stock triggers a SweetAlert2 modal dialog (`.swal2-modal`).
* **Historical Heuristic Deprecation:** The previous automator's client-side rule `[2,5,10] -> 10` is **not** an empirical vendor publishing fact. The adapter must pass `packaging_step_raw` up to Core rather than hardcoding piecewise substitutions.

---

## 6. CART MUTATION & INTERNAL AJAX SPECIFICATION

### 6.1 Internal Browser AJAX Contract
* **Target Route:** `POST https://lionelectronic.ir/orders/cart/add` (`EV-LION-CART-002`)
* **Endpoint Classification:** `INTERNAL_BROWSER_AJAX`
* **Session Prerequisites:** Requires active browser cookies (`_identity`, `_csrf`, session token).
* **Headers:** `X-Requested-With: XMLHttpRequest`.

### 6.2 Browser Automation Execution Sequence
1. **Focus & Modify Quantity Input (`EV-LION-QTY-003`):**
   ```javascript
   var el = document.getElementById('quantity-cell') || document.querySelector('.quantity-cell');
   el.value = target_qty;
   el.setAttribute('value', target_qty);
   if (window.jQuery) {
     $('#quantity-cell, .quantity-cell').val(target_qty).trigger('input').trigger('change');
   }
   ```
2. **Trigger Purchase Action (`EV-LION-PDP-004`):**
   ```javascript
   var btn = document.querySelector('button.btn-buy, button.add-btn, .btn-buy');
   if (btn && !btn.classList.contains('disabled')) {
     btn.click();
   }
   ```
3. **Settle Window & Modal Inspection (`EV-LION-ERR-001`):**
   * Wait `2.0 - 2.5` seconds for asynchronous AJAX completion and cart badge animation.
   * Inspect DOM for `.swal2-container, .swal2-html-container, .alert-danger`.
4. **Staged Cart Inspection Route (`EV-LION-CART-001`):**
   * Navigating to `https://lionelectronic.ir/orders/cart` renders the complete summary of staged parts, unit prices, and quantities.

---

## 7. AUTHENTICATION & SESSION SPECIFICATION

### 7.1 Authentication Route & Form Anatomy
* **Login URL:** `https://lionelectronic.ir/login` (`EV-LION-AUTH-001`)
* **Username Field:** `input#loginform-username` (Rank 2 Semantic ID)
* **Password Field:** `input#loginform-password` (Rank 2 Semantic ID)
* **Submit Action:** `button[name='signup-button'], #login-form button[type='submit'], button.blue-btn`

### 7.2 Session State Verification (`EV-LION-AUTH-002`)
* **Success Signature:** URL navigates away from `/login` (to `/` or `/orders`); DOM contains anchor with text `"خروج"` (Logout) or `"حساب کاربری"` (Account).
* **Failure Signature:** URL remains at `/login`; DOM renders error messages in `.help-block-error, .alert-danger, .has-error`.
* **Guest-to-Authenticated Cart Persistence:** Items added during guest browsing remain intact in the shopping cart after successful authentication.

---

## 8. ERROR TRANSLATION CONTRACT (13 NORMALIZED CATEGORIES)

The `LionVendorAdapter` must translate vendor-specific DOM, HTTP, and transport signals into the 13 standard Omnix error categories:

| Omnix Error Category | Lion Observable Signature | Detection Mechanism | Evidence ID | Verification Level | Adapter Translation & Recovery Action |
|---|---|---|---|:---:|---|
| `NOT_FOUND` | HTTP 404 or text `"صفحه‌ای یافت نشد"` | HTTP status / PDP Title | `EV-LION-ERR-002` | **`VERIFIED`** | Mark part unfulfillable on Lion; abort PDP workflow. |
| `ZERO_RESULTS` | HTTP 200 with 0 cards in `.empty-result` | DOM Card Counter | `EV-LION-SRCH-004` | **`VERIFIED`** | Return empty result set; trigger Base MPN or fuzzy retry. |
| `OUT_OF_STOCK` | Stock = 0, `"اتمام موجودی"`, `"به زودی"` | DOM Text / Badge | `EV-LION-PDP-007`, `008` | **`VERIFIED`** | Report 0 available inventory; flag inquiry requirement. |
| `MOQ_VIOLATION` | SweetAlert containing `"حداقل"` | SweetAlert2 Modal | `EV-LION-ERR-004` | **`VERIFIED`** | Dismiss modal; clamp quantity to MOQ and retry. |
| `ORDER_MULTIPLE_VIOLATION`| SweetAlert containing `"ضریب"` / `"مضرب"` | SweetAlert2 Modal | `EV-LION-ERR-001` | **`VERIFIED`** | Dismiss modal; round quantity to step and retry. |
| `MAX_QUANTITY_EXCEEDED` | SweetAlert `"موجودی کافی نیست"` | SweetAlert2 Modal | `EV-LION-ERR-003` | **`VERIFIED`** | Dismiss modal; clamp quantity to live stock ceiling. |
| `NETWORK_ERROR` | Transport timeout / SSL handshake reset | Transport Exception | `EV-LION-ERR-006` | **`VERIFIED`** | Execute exponential backoff retry loop (Max 3 retries). |
| `AUTH_REQUIRED` | HTTP 302 redirect to `/login` | URL Route / HTTP 302 | `EV-LION-AUTH-001` | **`OBSERVED (DEFENSIVE)`** | Trigger `authenticate()` workflow using stored credentials. |
| `SESSION_EXPIRED` | HTTP 401 / Invalid CSRF / Auth redirect | HTTP / Cookie State | `EV-LION-AUTH-002` | **`OBSERVED (DEFENSIVE)`** | Clear stale cookies; re-authenticate and restore cart. |
| `CAPTCHA_TRIGGERED` | Turnstile / reCAPTCHA iframe rendered | Security Container | `EV-LION-ERR-006` | **`OBSERVED (DEFENSIVE)`** | Halt automated execution; notify operator for human gate. |
| `WAF_BLOCK` | HTTP 403 Forbidden / Cloudflare block page | HTTP 403 / HTML Title | `EV-LION-ERR-006` | **`OBSERVED (DEFENSIVE)`** | Halt execution; trigger rate-limit cooldown delay. |
| `DOM_DRIFT` | Missing `#quantity-cell` or `.stock-amount`| DOM Query Exception | `EV-LION-QTY-001` | **`OBSERVED (DEFENSIVE)`** | Log selector failure; fallback to secondary selectors. |
| `UNKNOWN_VENDOR_ERROR` | Unclassified `.swal2-container` popup | Generic Modal Query | `EV-LION-ERR-001` | **`OBSERVED (DEFENSIVE)`** | Extract modal text; return unclassified vendor fault. |

---

## 9. ADAPTER STATE MACHINE SPECIFICATION

```
┌────────────────────────────────────────────────────────────────────────┐
│                      LION ADAPTER STATE MACHINE                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ initialize(config)
                                    ▼
                          ┌──────────────────┐
                          │   STATE: READY   │
                          └─────────┬────────┘
                                    │ search_part(query)
                                    ▼
                       ┌─────────────────────────┐
                       │ STATE: EXECUTING_SEARCH │
                       └────────────┬────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  │ HTTP 200                          │ Zero Matches
                  ▼                                   ▼
      ┌────────────────────────┐          ┌───────────────────────┐
      │ STATE: CANDIDATES_GRID │          │ STATE: SEARCH_EMPTY   │
      └───────────┬────────────┘          └───────────────────────┘
                  │ resolve_product(url)
                  ▼
         ┌───────────────────┐
         │ STATE: PDP_LOADED │
         └────────┬──────────┘
                  │ inspect_product()
                  ▼
        ┌─────────────────────┐
        │ STATE: PDP_INSPECTED│ ◄─────────────────────────┐
        └─────────┬───────────┘                           │
                  │ add_to_cart(qty)                      │ Recovery
                  ▼                                       │ (Clamp / Round)
         ┌───────────────────┐     SweetAlert Error       │
         │ STATE: MUTATING_  ├────────────────────────────┘
         │        CART       │
         └────────┬──────────┘
                  │ Success (2.2s settle, no modal)
                  ▼
        ┌─────────────────────┐
        │ STATE: CART_STAGED  │
        └─────────┬───────────┘
                  │ inspect_cart()
                  ▼
       ┌───────────────────────┐
       │   STATE: CART_READY   │
       └───────────────────────┘
```

---

## 10. HISTORICAL AUTOMATOR COMPARATIVE AUDIT (`lion_automator.py`)

A formal comparative audit between this specification and the existing reference implementation (`autom/lion_automator.py`) was performed:

| Feature / Logic | In `lion_automator.py` | In Adapter Specification | Architectural Assessment |
|---|---|---|---|
| **Search Routing** | Direct PDP navigation only | `GET /products?search={q}` | **Enhanced:** Specification adds formal search & candidate discovery. |
| **Quantity Input** | `#quantity-cell` | `input#quantity-cell` | **Preserved:** Empirically verified static HTML ID (`EV-LION-QTY-001`). |
| **Step Heuristic** | `[2,5,10] -> 10` hardcoded | Exposes raw step to Core | **Corrected:** Removed client-side heuristic from vendor model. |
| **Buy Trigger** | `button.btn-buy` | `button.btn-buy, button.add-btn` | **Preserved:** Empirically verified primary selector (`EV-LION-PDP-004`). |
| **AJAX Settle Time** | `time.sleep(2.2)` | 2.0–2.5s asynchronous settle | **Preserved:** Necessary for DOM/cart animation completion (`EV-LION-CART-002`). |
| **SweetAlert Check** | Keyword regex in `.swal2` | 13-Category error translation | **Formalized:** Replaced ad-hoc regex with typed error taxonomy. |
| **Login Selectors** | `#loginform-username/password`| Same semantic IDs | **Preserved:** Empirically verified ActiveForm elements (`EV-LION-AUTH-001`). |
| **Mode A/B Logic** | Mixed shortage calculation | Zero Core logic | **Decoupled:** All procurement mode logic removed from adapter boundary. |

---

## 11. IMPLEMENTATION READINESS MATRIX

| Adapter Capability | Supporting Evidence | Required Mechanism | Implementation Readiness Status |
|---|---|---|:---:|
| **Catalog Search** | `EV-LION-SRCH-001..004` | `GET /products?search={q}` | `VERIFIED_READY` |
| **PDP Extraction** | `EV-LION-PDP-001..008` | DOM Specs Table & JS Flag | `VERIFIED_READY` |
| **Stock Inspection** | `EV-LION-PDP-002` | `span.stock-amount` integer parse | `VERIFIED_READY` |
| **Order Constraints** | `EV-LION-QTY-001..003` | `#quantity-cell` raw value | `VERIFIED_READY` |
| **Cart Staging** | `EV-LION-CART-001..003` | Browser DOM Click & Settle | `VERIFIED_READY` |
| **User Authentication** | `EV-LION-AUTH-001..002` | `/login` form automation | `VERIFIED_READY` |
| **Operational Errors** | `EV-LION-ERR-001..004` | SweetAlert2 modal translation | `VERIFIED_READY` |
| **Transport Retry** | `EV-LION-ERR-006` | Exponential backoff retry | `VERIFIED_READY` |
| **Session Invalidation**| `EV-LION-AUTH-002` | Re-auth trigger on 401/302 | `DEFENSIVE_ONLY` |
| **Security Challenge** | `EV-LION-ERR-006` | Operator pause on Turnstile/WAF | `DEFENSIVE_ONLY` |
| **DOM Drift Fallback** | `EV-LION-QTY-001` | Secondary selector cascades | `DEFENSIVE_ONLY` |
| **Step Rounding Math** | None (Core Rule) | `ceil(needed / step) * step` | `CORE_OWNED` |
| **Headless Public API** | None (Not present) | Standalone REST HTTP Client | `NOT_SUPPORTED` |

---

## 12. OPEN QUESTIONS & FUTURE VERIFICATION

The following technical edge-cases are preserved as open observation points for future empirical runtime testing:
1. **`OQ-LION-001` Multi-Hour Session Expiration:** Exact session cookie TTL and CSRF invalidation response on Lion under idle conditions exceeding 24 hours.
2. **`OQ-LION-002` Dynamic WAF Rate Limits:** Empirical threshold of requests-per-minute before ArvanCloud / Cloudflare triggers an HTTP 429 or 403 challenge.
3. **`OQ-LION-003` Multi-Tier Volume Discount Tables:** Complete DOM schema mapping for products exhibiting complex tiered pricing matrices (`table.price-tiers`).

---

## 13. STRICT NON-GOALS

The following operations are explicitly out of scope for the `LionVendorAdapter`:
- Autonomous financial transaction execution / payment gateway submission.
- Solving or bypassing interactive CAPTCHA / Cloudflare Turnstile challenges.
- Direct headless cart manipulation without browser session context.
- BOM interpretation, shortage calculation, or multi-vendor price comparison.
- Cross-vendor fallback or shared state management with other vendor adapters.
