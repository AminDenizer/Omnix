# JAVAN ELECTRONIC VENDOR ADAPTER FORMAL SPECIFICATION
## Omnix Multi-Vendor Procurement Platform — Vendor Adapter Contract

**Document Reference:** `DOC-OMNIX-SPEC-JAVAN-001`  
**Version:** `1.0.0`  
**Status:** Approved Engineering Specification  
**Vendor Identifier:** `vendor_javan`  
**Vendor Name:** Javan Electronic (`https://www.javanelec.com`)  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/DISCOVERY/UNIVERSAL_DISCOVERY_PIPELINE.md` (DOC-OMNIX-PIPE-001)
- `docs/VENDORS/JAVAN/SITE_MAP_GRAPH.json` (Phase C Discovered & Validated Graph)
- `docs/VENDORS/JAVAN/DISCOVERY_AUDIT.md` (DOC-OMNIX-AUDIT-JAVAN-001)

---

## 1. PURPOSE AND ARCHITECTURAL BOUNDARY

This document defines the formal, binding technical specification for the **Javan Electronic Vendor Adapter** (`JavanVendorAdapter`).

The Adapter serves as the isolated translation layer between the vendor-agnostic **Omnix Core** and the vendor-specific web commerce platform of **Javan Electronic** (`javanelec.com`).

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
│                   JAVAN VENDOR ADAPTER (`vendor_javan`)                │
│  • Javan URL & Route Handling (`/shop?searchfilter=`, `/shoppingcarts`)│
│  • Javan DOM Selector Execution (`#searchAll`, `H1.font-weight-bold`) │
│  • Technical Spec Table Extraction (`Brand`, `Package`, `Mounting`)    │
│  • Volume Tier Pricing Table Parsing (`50 عدد`, `200 عدد`, etc.)      │
│  • Internal Browser AJAX Settle Time & Event Dispatching               │
│  • Form POST Staging (`/shoppingcarts/createindex`)                    │
│  • Result Normalization to IVendorAdapter Output Contracts            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Browser Automation Actions
                                    │ & Session Context
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    JAVAN ELECTRONIC PLATFORM (WEB)                     │
│                   `https://www.javanelec.com`                          │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Strict Core / Adapter Separation Rules
1. **Core Owns Business Logic:** Procurement modes (Mode A), BOM parsing, stock allocation, and cross-vendor pricing comparisons are owned exclusively by Core. The Javan Adapter contains zero BOM math and zero multi-vendor ranking logic.
2. **Adapter Owns Vendor Mechanics:** The Javan Adapter encapsulates all Javan-specific HTML IDs, CSS classes, URL patterns, Persian text strings, tiered pricing tables, and ASP.NET MVC form tokens.
3. **Vendor Isolation:** The Javan Adapter is 100% standalone. It has no dependencies on, or shared code with, any other vendor adapter (e.g. `vendor_lion`).
4. **Evidence-Backed Requirements:** Every selector, URL, state transition, and error condition specified herein is traceable to verified Phase C evidence records (`EV-JAVAN-*`).

---

## 2. ADAPTER INTERFACE CONTRACT (`IVendorAdapter`)

The `JavanVendorAdapter` must implement the conceptual `IVendorAdapter` contract. All operations accept typed inputs and return normalized data contracts.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   JAVAN ADAPTER CONCEPTUAL OPERATIONS                  │
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
  "vendor_id": "vendor_javan",
  "query": "NE555",
  "total_matches": 6,
  "is_exact_match": false,
  "items": [
    {
      "vendor_sku": "17930",
      "mpn_hint": "NE555P",
      "title": "NE555P | Texas Instruments",
      "pdp_url": "https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p",
      "thumbnail_url": "https://www.javanelec.com/stfiles/getappdocument/2/false/365c897d-70a4-4956-a5ef-9d0466dedd0b.jpg",
      "is_original": true
    }
  ]
}
```

#### B. `ProductDetails` Contract
```json
{
  "vendor_id": "vendor_javan",
  "vendor_sku": "17930",
  "pdp_url": "https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p",
  "mpn": "NE555P",
  "manufacturer": "Texas Instruments",
  "package_raw": "DIP-8",
  "stock_quantity": null,
  "can_order": true,
  "is_inquiry_only": false,
  "price_irr": 78100,
  "price_tiers": [
    {"min_quantity": 50, "unit_price_irr": 78100},
    {"min_quantity": 200, "unit_price_irr": 77300},
    {"min_quantity": 500, "unit_price_irr": 76500},
    {"min_quantity": 1000, "unit_price_irr": 74900}
  ],
  "specifications": {
    "Number of Timers/Counters": "1 Pcs",
    "Type": "Standard",
    "Mounting Style": "Through Hole",
    "Supply Voltage (Min)": "4.5 V",
    "Supply Voltage (Max)": "16 V",
    "Minimum Operating Temperature": "0 °C",
    "Maximum Operating Temperature": "+70 °C",
    "Brand": "Texas Instruments",
    "Package": "DIP-8"
  },
  "order_constraints": {
    "packaging_step_raw": 50,
    "moq_raw": 50
  }
}
```

#### C. `CartMutationResult` Contract
```json
{
  "vendor_id": "vendor_javan",
  "vendor_sku": "17930",
  "requested_quantity": 50,
  "actual_quantity_staged": 50,
  "success": true,
  "error_category": null,
  "raw_vendor_message": "Item added to cart",
  "cart_total_items": 1
}
```

---

## 3. SEARCH MECHANISM SPECIFICATION

### 3.1 HTTP Routing & Form Structure
* **Primary Search URL:** `GET https://www.javanelec.com/shop?searchfilter={query}`
* **Query Parameter:** `searchfilter` (Mandatory; case-insensitive).
* **Fragment Identifier:** `#filter_items_-1` (Client-side anchor for item list).
* **Search Input Selector:**
  * Primary: `input#searchAll` (`EV-JAVAN-SRCH-001`, Stable ID)
  * Fallback: `input[name='searchAll']` (`EV-JAVAN-SRCH-001`, Attribute Matcher)
* **Placeholder:** `"محصول، برند یا دسته‌بندی مورد نظرتان را جستجو کنید"`

### 3.2 Search Response Scenarios
1. **Standard Component Search (`EV-JAVAN-SRCH-001`):**
   * Target: Common component (e.g. `NE555`).
   * Behavior: Renders product search result grid at `/shop?searchfilter=NE555`. Product links conform to pattern `/shop/product/{id}/{brand}/{part}`.
2. **Specific Manufacturer Part Number (`EV-JAVAN-SRCH-002`):**
   * Target: Exact MPN (e.g. `STM32F103C8T6`).
   * Behavior: Renders matching microcontroller product cards.
3. **Zero-Results Empty State (`EV-JAVAN-SRCH-003`):**
   * Target: Nonexistent part (e.g. `XYZNONEXISTENT9999`).
   * Behavior: HTTP 200 with `0 محصول` marker in filter summary; zero product cards rendered.
4. **Product Card Structure & Originality Badges (`EV-JAVAN-SRCH-004`):**
   * Link selector: `a[href*='/shop/product/']`
   * Originality badge: `span[data-prdtype='Original']` (`اوریجینال`) vs `span[data-prdtype='Copy']` (`کپی`).
5. **Category Navigation (`EV-JAVAN-SRCH-005`):**
   * URL: `GET /shop/category/{cat_id}/{cat_slug}`
   * Faceted filter sidebar: `[class*='filter'], .side-filter` with faceted brand and package filters.

---

## 4. PRODUCT DETAIL PAGE (PDP) SPECIFICATION

### 4.1 URL Architecture
* **Canonical URL Regex:** `^https://www\.javanelec\.com/shop/product/(?P<product_id>\d+)/(?P<manufacturer_slug>[a-zA-Z0-9_.-]+)/(?P<part_number_slug>[a-zA-Z0-9_.-]+)(?:/.*)?$` (`EV-JAVAN-PDP-001`, `EV-JAVAN-PDP-002`)
* **Example:** `https://www.javanelec.com/shop/product/17930/texas-instruments/ne555p` (`product_id = 17930`, `manufacturer = texas-instruments`, `part = ne555p`).

### 4.2 Raw Vendor Data vs. Normalized Omnix Field Mapping

| Raw Javan DOM / HTTP Element | Selector / Extraction Rule | Normalized Adapter Field | Type | Evidence ID |
|---|---|---|:---:|:---:|
| URL Path Regex | `r"/shop/product/(\d+)/"` | `vendor_sku` | `str` | `EV-JAVAN-PDP-001` |
| `H1.font-weight-bold` | `h1.font-weight-bold, h1` | `mpn` / `product_title` | `str` | `EV-JAVAN-PDP-002` |
| Specs Table Row `'Brand'` | `table tr:has(td:contains('Brand')) td:nth-child(2)` | `manufacturer` | `str` | `EV-JAVAN-PDP-002` |
| Specs Table Row `'Package'` | `table tr:has(td:contains('Package')) td:nth-child(2)` | `package_raw` | `str` | `EV-JAVAN-PDP-002` |
| Specs Table Rows | `table tr td` (All rows) | `specifications` | `dict` | `EV-JAVAN-PDP-002` |
| Volume Pricing Table | `table tr td` (Tier rows) | `price_tiers` | `list` | `EV-JAVAN-QTY-001` |
| Tier 1 Unit Price | First row in price table $	o$ `r"([\d,]+)"` | `price_irr` | `int` | `EV-JAVAN-QTY-001` |
| Tier 1 Quantity Break | First row in price table $	o$ `r"([\d,]+)\s*عدد"` | `packaging_step_raw` | `int` | `EV-JAVAN-QTY-001` |
| Add to Cart Button | `button.btn-success-outline[type='submit']` | `can_order` | `bool` | `EV-JAVAN-PDP-002`, `003` |

---

## 5. TIERED PRICING, MOQ & PACKAGING STEP SPECIFICATION

### 5.1 Raw Vendor Property vs. Procurement Mathematics

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURAL BOUNDARY                          │
├────────────────────────────────────────────────────────────────────────┤
│ JAVAN ADAPTER RESPONSIBILITY:                                          │
│ 1. Extract raw price tier list from PDP pricing table                  │
│ 2. Extract Tier 1 minimum quantity as `moq_raw` / `packaging_step_raw`│
│ 3. Expose complete `price_tiers` structure to Omnix Core               │
├────────────────────────────────────────────────────────────────────────┤
│ OMNIX CORE / PROCUREMENT RESPONSIBILITY:                               │
│ 1. Evaluate shortage quantity against BOM demand                       │
│ 2. Match requested quantity against tier break brackets                │
│ 3. Apply appropriate volume discount unit price in procurement matrix  │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Discovered Pricing Tier Behaviors (`EV-JAVAN-QTY-001`, `EV-JAVAN-PDP-004`)
* **Explicit Tier Tables:** Javan displays volume discounts directly in a tabular layout:
  * Example NE555P (`EV-JAVAN-QTY-001`):
    * `50 عدد` $	o$ `78,100 ریال` (Base unit price)
    * `200 عدد` $	o$ `77,300 ریال`
    * `500 عدد` $	o$ `76,500 ریال`
    * `1,000 عدد` $	o$ `74,900 ریال`
  * Example LM358D (`EV-JAVAN-PDP-004`):
    * `100 عدد` $	o$ `136,000 ریال`
    * `200 عدد` $	o$ `135,000 ریال`
    * `500 عدد` $	o$ `133,000 ریال`
    * `1,000 عدد` $	o$ `131,000 ریال`
    * `2,500 عدد` $	o$ `128,000 ریال`
* **Adapter Exposure:** The adapter exposes the lowest tier (`50` or `100`) as `packaging_step_raw` and passes the full list of `price_tiers` to Core.

---

## 6. CART MUTATION & STAGING SPECIFICATION

### 6.1 Order Form & Endpoint Contract
* **Target Route:** `POST https://www.javanelec.com/shoppingcarts/createindex` (`EV-JAVAN-PDP-003`, `EV-JAVAN-CART-003`)
* **Endpoint Classification:** `INTERNAL_BROWSER_AJAX / FORM_POST`
* **Session Prerequisites:** Requires active browser cookies (`ASP.NET_SessionId`, verification tokens).
* **Form Action:** `form[action*='shoppingcarts'], form.form-horizontal`
* **Hidden Parameters:** `Cart`, `ViewBasketType`.
* **Submit Action:** Click `button.btn-success-outline[type='submit']` with text `"اضافه به سبد خرید"`.

### 6.2 Browser Automation Execution Sequence
1. **Focus & Submit Add to Cart Button (`EV-JAVAN-PDP-003`):**
   ```javascript
   var btn = document.querySelector('button.btn-success-outline[type="submit"], button[type="submit"]');
   if (btn) {
     btn.click();
   }
   ```
2. **Settle Window (`EV-JAVAN-CART-003`):**
   * Wait `2.0 - 2.5` seconds for asynchronous POST completion and cart badge animation.
3. **Cart Overview Route (`EV-JAVAN-CART-002`):**
   * Navigating to `https://www.javanelec.com/shoppingcarts` renders active cart overview and order tabs (`سبد خرید`, `سبد سفارش`).
   * Empty cart marker: `سبد خرید شما خالی است`.

---

## 7. AUTHENTICATION & SESSION SPECIFICATION

### 7.1 Authentication Route & Form Anatomy
* **Login URL:** `https://www.javanelec.com/account/login` (`EV-JAVAN-AUTH-002`)
* **Username Field:** `input#UserName` (`input[name='UserName']`) (Stable ID)
* **Password Field:** `input#Password` (`input[name='Password']`) (Stable ID)
* **Remember Me Field:** `input#RememberMe` (`input[name='RememberMe']`)
* **Submit Button:** `input[type='submit'][value='ورود']` (`input.btn-info-outline`)

### 7.2 Session State Verification (`EV-JAVAN-AUTH-001`, `002`)
* **Success Signature:** URL navigates away from `/account/login`; header displays user greeting (`کاربر گرامی خوش آمدید`) or Logout link.
* **Failure Signature:** URL remains at `/account/login` or renders validation summary alerts.
* **Guest Cart Persistence:** Cart state created during guest session is linked to user account upon subsequent login.

---

## 8. ERROR TRANSLATION CONTRACT (13 NORMALIZED CATEGORIES)

The `JavanVendorAdapter` must translate vendor-specific DOM, HTTP, and transport signals into the 13 standard Omnix error categories:

| Omnix Error Category | Javan Observable Signature | Detection Mechanism | Evidence ID | Verification Level | Adapter Translation & Recovery Action |
|---|---|---|---|:---:|---|
| `NOT_FOUND` | URL `/home/notfound`, title `"Not Found"`, text `"صفحه مورد نظر شما یافت نشد"` | URL / Heading | `EV-JAVAN-ERR-001` | **`VERIFIED`** | Mark part unfulfillable on Javan; abort PDP workflow. |
| `ZERO_RESULTS` | Text `"0 محصول"` in filter summary | DOM Text Marker | `EV-JAVAN-SRCH-003` | **`VERIFIED`** | Return empty `SearchResultSet(total_matches=0)`. |
| `OUT_OF_STOCK` | Missing Add to Cart button / price table | DOM Button Check | `EV-JAVAN-SRCH-003`, `EV-JAVAN-PDP-002` | **`VERIFIED`** | Report 0 available inventory; set `can_order=False`. |
| `MOQ_VIOLATION` | Quantity submitted below Tier 1 minimum | Validation Alert | `EV-JAVAN-QTY-001` | **`VERIFIED`** | Clamp quantity to Tier 1 MOQ and retry. |
| `ORDER_MULTIPLE_VIOLATION`| Quantity not conforming to packaging step | Validation Alert | `EV-JAVAN-QTY-001` | **`VERIFIED`** | Round quantity to step and retry. |
| `MAX_QUANTITY_EXCEEDED` | Quantity exceeding distributor stock | Validation Alert | `EV-JAVAN-PDP-003` | **`VERIFIED`** | Clamp quantity to available ceiling. |
| `NETWORK_ERROR` | Transport timeout / SSL handshake reset | Transport Exception | `EV-JAVAN-AUTH-001` | **`VERIFIED`** | Execute exponential backoff retry (Max 3 attempts). |
| `AUTH_REQUIRED` | HTTP 302 redirect to `/account/login` | URL Route / HTTP 302 | `EV-JAVAN-AUTH-002` | **`OBSERVED (DEFENSIVE)`** | Trigger adapter `authenticate()` flow. |
| `SESSION_EXPIRED` | HTTP 401 / session timeout redirect | HTTP / Cookie State | `EV-JAVAN-AUTH-002` | **`OBSERVED (DEFENSIVE)`** | Clear session cookies; re-authenticate. |
| `CAPTCHA_TRIGGERED` | Captcha challenge container rendered | Security Container | `EV-JAVAN-ERR-001` | **`OBSERVED (DEFENSIVE)`** | Halt execution; trigger operator human intervention. |
| `WAF_BLOCK` | HTTP 403 Forbidden / firewall block | HTTP Status | `EV-JAVAN-ERR-001` | **`OBSERVED (DEFENSIVE)`** | Halt execution; trigger cooldown delay. |
| `DOM_DRIFT` | Missing expected static selector `#searchAll` | DOM Query Exception | `EV-JAVAN-SRCH-001` | **`OBSERVED (DEFENSIVE)`** | Fallback to secondary selectors; log DOM drift alert. |
| `UNKNOWN_VENDOR_ERROR` | Unclassified server error or popup | Generic Query | `EV-JAVAN-ERR-001` | **`OBSERVED (DEFENSIVE)`** | Extract error message; return unclassified error. |

---

## 9. ADAPTER STATE MACHINE SPECIFICATION

```
┌────────────────────────────────────────────────────────────────────────┐
│                      JAVAN ADAPTER STATE MACHINE                       │
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
         ┌───────────────────┐     Validation Alert       │
         │ STATE: MUTATING_  ├────────────────────────────┘
         │        CART       │
         └────────┬──────────┘
                  │ Success (2.2s settle, no alert)
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

## 10. IMPLEMENTATION READINESS MATRIX

| Adapter Capability | Supporting Evidence | Required Mechanism | Implementation Readiness Status |
|---|---|---|:---:|
| **Catalog Search** | `EV-JAVAN-SRCH-001..004` | `GET /shop?searchfilter={q}` | `VERIFIED_READY` |
| **PDP Extraction** | `EV-JAVAN-PDP-001..004` | DOM Specs Table & H1 Title | `VERIFIED_READY` |
| **Tiered Price Extraction** | `EV-JAVAN-QTY-001`, `EV-JAVAN-PDP-004` | Pricing table parse | `VERIFIED_READY` |
| **Order Constraints** | `EV-JAVAN-QTY-001` | Tier 1 min quantity | `VERIFIED_READY` |
| **Cart Staging** | `EV-JAVAN-CART-001..003`, `EV-JAVAN-PDP-003` | Browser Form POST & Settle | `VERIFIED_READY` |
| **User Authentication** | `EV-JAVAN-AUTH-001..002` | `/account/login` form automation | `VERIFIED_READY` |
| **Operational Errors** | `EV-JAVAN-ERR-001`, `EV-JAVAN-SRCH-003` | DOM alert & URL redirection | `VERIFIED_READY` |
| **Transport Retry** | `EV-JAVAN-AUTH-001` | Exponential backoff retry | `VERIFIED_READY` |
| **Session Invalidation**| `EV-JAVAN-AUTH-002` | Re-auth trigger on 401/302 | `DEFENSIVE_ONLY` |
| **Security Challenge** | `EV-JAVAN-ERR-001` | Operator pause on Captcha/WAF | `DEFENSIVE_ONLY` |
| **DOM Drift Fallback** | `EV-JAVAN-SRCH-001` | Secondary selector cascades | `DEFENSIVE_ONLY` |
| **Tier Discount Math** | None (Core Rule) | Bracket matching formula | `CORE_OWNED` |
| **Headless Public API** | None (Not present) | Standalone REST HTTP Client | `NOT_SUPPORTED` |

---

## 11. OPEN QUESTIONS & FUTURE VERIFICATION

The following technical edge-cases are preserved as open observation points:
1. **`OQ-JAVAN-001` Authentication Modal vs Standalone Redirect:** Whether Javan renders an AJAX modal during checkout or strictly redirects to `/account/login`.
2. **`OQ-JAVAN-002` Multiple-Order Pricing Enforcement:** Whether ordering non-tier exact quantities (e.g. 75 pcs) is clamped to 50 or priced at the 50-tier unit rate.
3. **`OQ-JAVAN-003` Live AJAX Cart Settle Timing:** Minimum settle window needed for asynchronous cart badge animations on slower connections.

---

## 12. STRICT NON-GOALS

The following operations are explicitly out of scope for the `JavanVendorAdapter`:
- Autonomous financial transaction execution / payment gateway checkout.
- Solving or bypassing interactive CAPTCHA challenges.
- Direct headless cart manipulation without browser session context.
- BOM interpretation, shortage calculation, or multi-vendor price comparison.
- Cross-vendor fallback or shared state management with other vendor adapters.
