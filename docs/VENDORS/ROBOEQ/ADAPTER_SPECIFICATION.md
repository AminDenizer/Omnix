# ROBOEQ ELECTRONIC VENDOR ADAPTER FORMAL SPECIFICATION
## Omnix Multi-Vendor Procurement Platform — Vendor Adapter Contract

**Document Reference:** `DOC-OMNIX-SPEC-ROBOEQ-001`  
**Version:** `1.0.0`  
**Status:** Approved Engineering Specification  
**Vendor Identifier:** `vendor_roboeq`  
**Vendor Name:** RoboEq Electronic (`https://roboeq.ir`)  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-MPS-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/DISCOVERY/UNIVERSAL_DISCOVERY_PIPELINE.md` (DOC-OMNIX-PIPE-001)
- `docs/VENDORS/ROBOEQ/SITE_MAP_GRAPH.json` (Phase 4 Discovered & Validated Graph)

---

## 1. PURPOSE AND ARCHITECTURAL BOUNDARY

This document defines the formal, binding technical specification for the **RoboEq Electronic Vendor Adapter** (`RoboEqVendorAdapter`).

The Adapter serves as the isolated translation layer between the vendor-agnostic **Omnix Core** and the multi-seller marketplace commerce platform of **RoboEq Electronic** (`roboeq.ir`).

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
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   ROBOEQ VENDOR ADAPTER (`vendor_roboeq`)              │
│  • RoboEq URL & Route Handling (`/search/?q=`, `/products/detail/`)   │
│  • RoboEq DOM Selector Execution (`.req-field`, `a[href*='detail']`)  │
│  • Technical Specs Extraction (`وزن`, `پکیج`, `دیتاشیت`)              │
│  • Multi-Seller Tier Pricing Extraction (`۱+عدد`, `۵۰+عدد`, etc.)     │
│  • Quantity Increment Steppers (`.inc-qty`, `.dec-qty`)               │
│  • Result Normalization to IVendorAdapter Output Contracts            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Browser Automation Actions
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   ROBOEQ ELECTRONIC PLATFORM (WEB)                     │
│                        `https://roboeq.ir`                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. ADAPTER INTERFACE CONTRACT (`IVendorAdapter`)

The `RoboEqVendorAdapter` must implement the conceptual `IVendorAdapter` contract. All 13 operations accept typed inputs and return normalized data contracts:

1. `initialize(config)` -> `AdapterStatus`
2. `search_part(query)` -> `SearchResultSet`
3. `resolve_product(url_or_sku)` -> `ProductReference`
4. `inspect_product(product_ref)` -> `ProductDetails`
5. `extract_product_data(dom_context)` -> `CanonicalComponentDraft`
6. `inspect_stock(product_ref)` -> `StockStatus`
7. `determine_order_constraints(prod_ref)` -> `OrderConstraints`
8. `add_to_cart(product_ref, quantity)` -> `CartMutationResult`
9. `inspect_cart()` -> `CartDetails`
10. `authenticate(credentials)` -> `AuthResult`
11. `validate_session()` -> `SessionStatus`
12. `recover_from_error(error_context)` -> `RecoveryResult`
13. `close()` -> `void`

---

## 3. SEARCH MECHANISM & ROUTING

- **Search URL:** `GET https://roboeq.ir/search/?q={query}` (`EV-ROBOEQ-SRCH-002`)
- **Search Input Selector:** `input.req-field, input[placeholder*='نام محصول'], input[placeholder*='جستجو']` (`EV-ROBOEQ-SRCH-001`)
- **Product Card Links:** `a[href*='/products/detail/']` (`EV-ROBOEQ-SRCH-002`, `004`)
- **Zero Results Marker:** `بدون نتیجه` in DOM text (`EV-ROBOEQ-SRCH-003`)

---

## 4. PRODUCT DETAIL PAGE (PDP)

- **Canonical URL Regex:** `r"^https?://(?:www\.)?roboeq\.ir/products/detail/(?P<product_id>\d+)/(?P<slug>[^/]+)/?\$"` (`EV-ROBOEQ-PDP-001`)
- **Product Title:** `h1, .product-title` (`EV-ROBOEQ-PDP-002`)
- **Multi-Seller Volume Pricing Table:** `table` with columns `۱+عدد`, `۵۰+عدد`, `۱۰۰+عدد`, `۳۰۰+عدد`, `۵۰۰+عدد` (`EV-ROBOEQ-PDP-003`)
- **Technical Specs Table:** `table tr` with `عنوان` / `مقدار` (`EV-ROBOEQ-PDP-004`)
- **Add to Cart Action:** Click `button:contains('افزودن به سبد'), button.waves-effect` (`EV-ROBOEQ-PDP-005`)
- **Quantity Controls:** `button.inc-qty`, `button.dec-qty` (`EV-ROBOEQ-QTY-001`)

---

## 5. AUTHENTICATION & ERROR TRANSLATION

- **Login Route:** `https://auth.roboeq.ir/cas/login?service=https%3A%2F%2Froboeq.ir%2Flogin%2F` (`EV-ROBOEQ-AUTH-001`)
- **Error 404 Route:** `https://roboeq.ir/error/404/?referer=...` (`EV-ROBOEQ-ERR-001`)
- **Error Translation:** 3-tier translation mapping Persian validation messages, page states (404, WAF, Captcha), and Selenium transport exceptions to the 13 canonical `OmnixVendorError` categories.
