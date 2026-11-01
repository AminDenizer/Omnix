# Javan Electronic (`vendor_javan`) — Empirical Discovery Audit Report

**Audit Status:** `PHASE_C_DISCOVERY_APPROVED`  
**Target Vendor:** Javan Electronic (`vendor_javan`)  
**Base URL:** `https://www.javanelec.com`  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md` (DOC-OMNIX-SPEC-001)
- `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md` (DOC-OMNIX-DISC-001)
- `docs/DISCOVERY/SITE_MAP_SCHEMA.md` (DOC-OMNIX-SCHEMA-001)
- `docs/DISCOVERY/UNIVERSAL_DISCOVERY_PIPELINE.md` (DOC-OMNIX-PIPE-001)

---

## 1. Discovery Environment & Target Registration

- **Vendor ID:** `vendor_javan`
- **Vendor Name:** Javan Electronic
- **Base URL:** `https://www.javanelec.com` (Verified via DNS and HTTP/2 handshake)
- **Storefront Type:** Iranian Electronics Component Distributor & E-Commerce Platform
- **Execution Platform:** Windows 11 / Python 3.13.5
- **Discovery Engine:** Omnix Universal Discovery Harness (`core.discovery.session.DiscoverySession`)
- **Browser Automation:** Headless Chrome WebDriver (1920x1080 viewport, anti-bot bypass, polite rate-limiting)

---

## 2. Discovery Methodology & Verification Statuses

Empirical observation was conducted across 6 core e-commerce workflows without relying on pre-existing adapter code, assumptions, or Lion-specific heuristics.

Findings are strictly classified into:
- **`[VERIFIED]`**: Empirically observed and proven with captured DOM, network, and screenshot evidence.
- **`[OBSERVED]`**: Empirically observed structure or layout during session interaction.
- **`[DEFENSIVE / UNKNOWN]`**: Potential error state or boundary condition that was not triggered destructively.
- **`[OPEN QUESTION]`**: Implementation detail requiring runtime handling or business policy confirmation.

---

## 3. Workflows Observed & Empirical Evidence Inventory

| Evidence ID | Workflow | Action / Target | Observed Behavior | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| `EV-JAVAN-AUTH-001` | `AUTHENTICATION` | Landing Page Navigation (`/`) | HTTP 200, Title: `فروشگاه اینترنتی جوان الکترونیک`, Header navigation, `#searchAll` input, Cart badge. | `[VERIFIED]` |
| `EV-JAVAN-AUTH-002` | `AUTHENTICATION` | Login Form Navigation (`/account/login`) | POST form to `/shoppingcarts/createindex` with `#UserName`, `#Password`, `#RememberMe`, Submit `input[value="ورود"]`. | `[VERIFIED]` |
| `EV-JAVAN-SRCH-001` | `SEARCH` | Keyword Search `NE555` | Query routed to `/shop?searchfilter=NE555#filter_items_-1`. Returns product cards grid. | `[VERIFIED]` |
| `EV-JAVAN-SRCH-002` | `SEARCH` | MPN Search `STM32F103C8T6` | Specific MPN search returns matching ARM microcontrollers. | `[VERIFIED]` |
| `EV-JAVAN-SRCH-003` | `SEARCH` | Nonexistent Query `XYZNONEXISTENT9999` | Empty search state: `0 محصول` marker, filter summary, zero product cards. | `[VERIFIED]` |
| `EV-JAVAN-SRCH-004` | `SEARCH` | Search Result DOM Anchor Analysis | Product links follow pattern `/shop/product/{id}/{brand}/{part}`. Originality badges (`Original` / `Copy`) present. | `[VERIFIED]` |
| `EV-JAVAN-SRCH-005` | `SEARCH` | Category Hierarchy Navigation | Categorized product catalog with faceted filter sidebar (Brand, Package, Voltage). | `[VERIFIED]` |
| `EV-JAVAN-PDP-001` | `PDP` | Initial PDP Layout Inspection | Page loads with product title heading and main container. | `[VERIFIED]` |
| `EV-JAVAN-PDP-002` | `PDP` | Deep PDP DOM Inspection (`NE555P`) | Title: `H1.font-weight-bold` (`NE555P`), specifications table (Brand: `Texas Instruments`, Package: `DIP-8`, Temp, Voltage), price table. | `[VERIFIED]` |
| `EV-JAVAN-PDP-003` | `PDP` | Order Form & Submission Controls | Form submitting to `/shoppingcarts/createindex` (method POST) with button `اضافه به سبد خرید`. | `[VERIFIED]` |
| `EV-JAVAN-PDP-004` | `PDP` | Secondary PDP Inspection (`LM358D`) | Title: `LM358D` (STMicroelectronics, SO-8). Consistent tiered pricing and specs structure across manufacturers. | `[VERIFIED]` |
| `EV-JAVAN-QTY-001` | `PDP` | Volume Tiered Pricing Table | 4-tier price table extracted: `50 عدد: 78,100 IRR`, `200 عدد: 77,300 IRR`, `500 عدد: 76,500 IRR`, `1000 عدد: 74,900 IRR`. | `[VERIFIED]` |
| `EV-JAVAN-CART-001` | `CART` | Category to Cart Navigation | Navigation from product categories to active cart overview. | `[VERIFIED]` |
| `EV-JAVAN-CART-002` | `CART` | Cart Index Endpoint (`/shoppingcarts`) | Title: `جوان الکترونیک - سبد خرید/سفارش`. Empty state: `سبد خرید شما خالی است`. Cart & Order tabs displayed. | `[VERIFIED]` |
| `EV-JAVAN-CART-003` | `CART` | Cart Staging POST Target | Form POST endpoint `/shoppingcarts/createindex` accepting hidden cart state parameters. | `[VERIFIED]` |
| `EV-JAVAN-ERR-001` | `ERROR_HANDLING` | HTTP 404 Route Verification | Invalid URL redirects to `/home/notfound`, Title: `جوان الکترونیک - Not Found`, Heading: `صفحه مورد نظر شما یافت نشد`. | `[VERIFIED]` |

---

## 4. Site Map Graph Statistics & Topology

- **File Path:** [`docs/VENDORS/JAVAN/SITE_MAP_GRAPH.json`](file:///d:/management-elec/autom/atom/docs/VENDORS/JAVAN/SITE_MAP_GRAPH.json)
- **Total Nodes:** 21
  - `PAGE`: 6 (`javan_page_landing`, `javan_page_search_results`, `javan_page_category`, `javan_page_pdp`, `javan_page_cart`, `javan_page_login`, `javan_page_error_404`)
  - `INPUT`: 3 (`javan_input_search`, `javan_input_username`, `javan_input_password`)
  - `RESULT`: 1 (`javan_result_product_card`)
  - `BUTTON`: 2 (`javan_btn_add_to_cart`, `javan_btn_login_submit`)
  - `COMPONENT`: 2 (`javan_comp_pdp_specs`, `javan_comp_pdp_pricing`)
  - `FORM`: 2 (`javan_form_add_to_cart`, `javan_form_login`)
  - `STATE`: 3 (`javan_state_empty_search`, `javan_state_empty_cart`, `javan_state_error_404`)
  - `API_ENDPOINT`: 1 (`javan_api_cart_create`)
- **Total Edges:** 21
  - `CONTAINS`: 13
  - `TRIGGERS`: 2
  - `NAVIGATES_TO`: 3
  - `FAILS_WITH`: 2
  - `UPDATES`: 1
- **Total Selectors:** 19 (all CSS/ID with verified evidence trace)
- **Total Extractions:** 5 (Product title, MPN, Specifications table, Tiered price list, Empty cart text)

---

## 5. Automated Validation & Quality Assurance Checks

Executed: `python -m core.discovery.cli audit docs/VENDORS/JAVAN/SITE_MAP_GRAPH.json`

```
=== SITE MAP GRAPH VALIDATION REPORT: vendor_javan ===
Status: PASSED (Errors: 0, Warnings: 0, Total Checks: 10)
----------------------------------------------------------
[PASS] CHK-SCHEMA-001: Metadata Completeness - Metadata complete
[PASS] CHK-UNIQUE-001: Node ID Uniqueness - All 21 node IDs are unique
[PASS] CHK-UNIQUE-002: Edge ID Uniqueness - All 21 edge IDs are unique
[PASS] CHK-TOPOLOGY-001: Edge Topology Validity - All edge endpoints resolve to existing nodes
[PASS] CHK-ORPHAN-001: Orphan Node Detection - Zero orphan nodes detected
[PASS] CHK-SELECTOR-001: Selector Reference Integrity - All 19 selectors resolved cleanly
[PASS] CHK-EXTRACTION-001: Extraction Integrity - All 5 extractions bind to valid nodes
[PASS] CHK-EVIDENCE-001: Evidence Traceability - All 16 referenced evidence IDs exist on disk
[PASS] CHK-WORKFLOW-001: Workflow Completeness - All mandatory workflow node types present
[PASS] CHK-LEAKAGE-001: Core Leakage Guard - Zero Core procurement leakage detected in graph properties
```

---

## 6. Multi-Vendor Neutrality & Universality Verification

- **Codebase Grep Check:** Searched `core/discovery/` for vendor-specific identifiers (`lion`, `javan`, `LionSelectors`, `lionelectronic`, `javanelec`).
- **Result:** **ZERO** vendor-specific behavioral assumptions exist in `core/discovery/`.
- **Universality Verification Test:** `TestSiteMapGraphValidator.test_multi_vendor_discovery_neutrality` successfully validated both `vendor_lion` (Reference) and `vendor_javan` (New Target) through the same generic engine.
- **Pytest Suite:** `53 / 53 PASSED` (100%).

---

## 7. Unknowns & Open Questions for Adapter Specification Phase

1. **`[OPEN QUESTION]` Authentication Modal vs Standalone Page:**
   - Does Javan render an AJAX popup modal for login during cart checkout, or does it redirect to `/account/login`?
2. **`[OPEN QUESTION]` Order Multiple Enforcement:**
   - On the PDP, pricing is tiered (e.g. 50, 200, 500 pcs). If an order of 75 pcs is placed, does Javan accept 75 at the 50-tier unit price, or does it enforce multiples of 50?
3. **`[OPEN QUESTION]` Live AJAX Cart Synchronization:**
   - When submitting via `#more_result` or Add to Cart button, does Javan require a dedicated AJAX settle window (e.g. ~2.0s) similar to standard ASP.NET / jQuery storefronts?

---

## 8. Hard Architectural Boundary & No-Implementation Declaration

> [!IMPORTANT]
> **NO VENDOR ADAPTER IMPLEMENTATION WAS PERFORMED DURING PHASE C.**
> - `vendors/javan/adapter.py` was **NOT** created.
> - `vendors/javan/selectors.py` was **NOT** created.
> - `vendors/javan/errors.py` was **NOT** created.
> - `vendors/javan/session.py` was **NOT** created.
> - No production Python code in `main.py`, `bom_auditor.py`, `excel_loader.py`, or `Inventory.xlsx` was modified.
> - Phase C strictly terminates at Site Map Validation and Discovery Audit.

---

## 9. Final Gate Decision

**`FINAL PHASE C DECISION: PHASE_C_DISCOVERY_APPROVED`**
