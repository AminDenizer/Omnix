# OMNIX VENDOR SITE MAP GRAPH SCHEMA SPECIFICATION
## Formal Typed Directed Graph Specification for Vendor Discovery Artifacts

**Document Reference:** `DOC-OMNIX-SCHEMA-001`  
**Version:** `1.0.0`  
**Status:** Approved Engineering Specification  
**Governing Specification:** `docs/MASTER_PROJECT_SPECIFICATION.md`  
**Governing Methodology:** `docs/DISCOVERY/DISCOVERY_METHODOLOGY.md`  
**Target Target Artifact:** `docs/VENDORS/{VENDOR_ID}/SITE_MAP_GRAPH.json`

---

## 1. PURPOSE AND ARCHITECTURAL SCOPE

This specification defines the formal JSON schema for the **Site Map Graph** (`SITE_MAP_GRAPH.json`) generated for each electronic component distributor supported by **Omnix**.

The Site Map Graph models a vendor's online commerce platform as a **typed, directed state graph**. It captures the structural hierarchy of pages, DOM elements, API endpoints, interactive user actions, data extraction bindings, packaging constraints, and error state transitions.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          SITE MAP GRAPH ROLES                          │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Vendor Site Neutrality: Encapsulates vendor structure only.         │
│ 2. Evidence-Backed: Every node, edge, and selector binds to an Ev-ID.  │
│ 3. Core Independence: Contains ZERO Core or Mode A/B business rules.   │
│ 4. Decoupled Adapter Basis: Serves as the input to IVendorAdapter.    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. METADATA SCHEMA

The root of every `SITE_MAP_GRAPH.json` must contain a strictly typed `metadata` object:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "metadata": {
    "vendor_id": "vendor_lion",
    "vendor_name": "Lion Electronic",
    "base_url": "https://lionelectronic.ir",
    "schema_version": "1.0.0",
    "discovery_version": "1.0.0",
    "created_at": "2026-09-16T15:00:00Z",
    "updated_at": "2026-09-16T16:00:00Z",
    "last_verified": "2026-09-16T16:00:00Z",
    "verification_status": "VERIFIED"
  }
}
```

### Metadata Field Specifications:
* `vendor_id` (*string, required*): Immutable snake_case unique identifier (e.g. `vendor_lion`, `vendor_javan`). Must match the parent directory name `docs/VENDORS/{VENDOR}/`.
* `vendor_name` (*string, required*): Human-readable commercial entity name (e.g. `Lion Electronic`).
* `base_url` (*string, required, format: uri*): Canonical root URL (e.g. `https://lionelectronic.ir`).
* `schema_version` (*string, required*): Semantic version of this schema specification (`1.0.0`).
* `discovery_version` (*string, required*): Version of the vendor-specific discovery execution.
* `created_at` / `updated_at` / `last_verified` (*string, required, format: date-time*): ISO-8601 UTC timestamps.
* `verification_status` (*enum, required*): Overall graph status (`UNVERIFIED`, `OBSERVED`, `REPRODUCED`, `VERIFIED`).

---

## 3. NODE SCHEMA

Nodes represent distinct structural, behavioral, or semantic entities on the vendor's platform.

### 3.1 Supported Node Types

| Node Type | Purpose | Example |
|---|---|---|
| `PAGE` | Distinct URL route or major view state | `node_page_home`, `node_page_search_results` |
| `COMPONENT` | Structural DOM container element | `node_comp_header_search`, `node_comp_spec_table` |
| `FORM` | Interactive data submission container | `node_form_search`, `node_form_login` |
| `INPUT` | Text field, spinbox, or checkbox | `node_input_search_query`, `node_input_quantity` |
| `BUTTON` | Clickable interactive trigger | `node_btn_search_submit`, `node_btn_add_to_cart` |
| `LINK` | Navigational anchor element | `node_link_pdp_card`, `node_link_cart_drawer` |
| `RESULT` | Output collection of a query | `node_res_product_grid`, `node_res_empty_search` |
| `PRODUCT` | Discrete purchasable catalog item entity | `node_prod_item_card` |
| `CART` | Persistent shopping basket container | `node_cart_session_drawer`, `node_cart_page` |
| `MODAL` | Floating dialog, popup, or overlay | `node_modal_swal_error`, `node_modal_out_of_stock` |
| `ERROR` | Visual error message, badge, or toast | `node_err_invalid_step`, `node_err_login_failed` |
| `API_ENDPOINT` | Direct HTTP/XHR/REST network target | `node_api_cart_add`, `node_api_search_suggest` |
| `DATA_SOURCE` | Technical attribute location in DOM/JS | `node_data_stock_amount`, `node_data_package_spec` |
| `STATE` | Internal vendor session or product state | `node_state_logged_in`, `node_state_can_order_true` |

### 3.2 Node Object Specification
```json
{
  "id": "node_btn_add_to_cart",
  "type": "BUTTON",
  "label": "Add to Cart Button",
  "description": "Primary action button on PDP to inject selected quantity into shopping cart",
  "selectors": ["sel_btn_buy_primary", "sel_btn_buy_fallback"],
  "url_pattern": "^https://lionelectronic\\.ir/products/\\d+-[a-zA-Z0-9_-]+$",
  "properties": {
    "is_interactive": true,
    "debounce_ms": 250,
    "expected_tag": "button"
  },
  "evidence_ids": ["EV-LION-PDP-004"]
}
```

---

## 4. EDGE (RELATIONSHIP) SCHEMA

Edges represent directional transitions, structural ownership, data extractions, and error branches between nodes.

### 4.1 Supported Relationship Types

| Relationship | Semantics | Source $\to$ Target Example |
|---|---|---|
| `CONTAINS` | Structural parent-child hierarchy | `PAGE: Home` $\to$ `COMPONENT: Search Bar` |
| `TRIGGERS` | User or automation event triggering action | `BUTTON: Add to Cart` $\to$ `API_ENDPOINT: /cart/add` |
| `NAVIGATES_TO` | Page redirection or URL route transition | `LINK: Product Card` $\to$ `PAGE: Product Detail` |
| `RETURNS` | Operation resulting in an outcome node | `API_ENDPOINT: Search` $\to$ `RESULT: Product Grid` |
| `EXTRACTS` | Data binding from element into attribute | `DATA_SOURCE: Spec Table` $\to$ `PRODUCT.package` |
| `UPDATES` | Action causing internal state change | `BUTTON: Add to Cart` $\to$ `CART.item_count` |
| `FAILS_WITH` | Negative error branch transition | `BUTTON: Add to Cart` $\to$ `MODAL: Out of Stock Alert` |
| `RECOVERS_TO` | Error dismissal or recovery path | `MODAL: SweetAlert OK` $\to$ `PAGE: Product Detail` |
| `REQUIRES` | Pre-condition dependency | `BUTTON: Checkout` $\to$ `STATE: Logged In` |
| `DEPENDS_ON` | Temporal or data dependency | `INPUT: Quantity` $\to$ `DATA_SOURCE: Packaging Step` |

### 4.2 Edge Object Specification
```json
{
  "id": "edge_buy_triggers_cart_api",
  "source_node_id": "node_btn_add_to_cart",
  "target_node_id": "node_api_cart_add",
  "relationship_type": "TRIGGERS",
  "condition": "element.is_enabled() && !element.has_class('disabled')",
  "evidence_ids": ["EV-LION-CART-002"]
}
```

---

## 5. SELECTOR SCHEMA

Selectors are isolated into an independent dictionary to enable zero-code updates during vendor DOM redesigns.

### 5.1 Selector Types
* `css`: Standard CSS3/CSS4 selector.
* `xpath`: Explicit XPath 1.0/2.0 expression.
* `id`: Native HTML element ID (without leading `#`).
* `text`: Text-content match expression.
* `attribute`: HTML attribute exact or substring matcher (`[name='btn']`).
* `data_attribute`: Custom data attribute matcher (`[data-testid='buy']`).
* `url_pattern`: Regular expression matching browser address bar URL.
* `json_path`: JSONPath query for extracting fields from API responses.
* `js_expression`: JavaScript evaluation string (e.g. `window.productCanOrder`).

### 5.2 Selector Object Specification
```json
{
  "id": "sel_btn_buy_primary",
  "type": "css",
  "value": "button.btn-buy, button.add-btn",
  "priority": 1,
  "stability": "STABLE_CLASS",
  "evidence_ids": ["EV-LION-PDP-005"]
}
```

---

## 6. DATA EXTRACTION SCHEMA

Data extraction rules bind raw vendor DOM/API structures to typed **CanonicalComponent** fields:

```json
{
  "id": "extract_product_package",
  "field_name": "package",
  "source_node_id": "node_comp_spec_table",
  "source_type": "DOM_TEXT",
  "selector_id": "sel_spec_package_row",
  "attribute": null,
  "regex": "پکیج\\s*:\\s*([A-Za-z0-9_-]+)",
  "transform": "TRIM_UPPERCASE",
  "normalization_rule": "CANONICAL_PACKAGE_MAP",
  "required": true,
  "evidence_ids": ["EV-LION-PDP-008"]
}
```

### Supported Transformation Types:
* `TRIM_UPPERCASE`: Strips whitespace and standardizes casing.
* `EXTRACT_INTEGER`: Extracts first contiguous sequence of digits (`r'\d+'`).
* `EXTRACT_FLOAT`: Parses decimal numbers.
* `CLEAN_PERSIAN_DIGITS`: Replaces Persian/Arabic numerals (`۱۲۳`) with standard ASCII (`123`).
* `PARSE_PRICE_TOMANS`: Converts Tomans string to standard IRR integer.

---

## 7. STATE SCHEMA

The state dictionary enumerates discrete observable operational states of the vendor session:

```json
{
  "states": {
    "STATE_LOGGED_OUT": {
      "label": "Guest Session (Unauthenticated)",
      "indicator_selectors": ["sel_login_link", "sel_guest_cart_badge"],
      "evidence_ids": ["EV-LION-AUTH-001"]
    },
    "STATE_LOGGED_IN": {
      "label": "Authenticated User Session",
      "indicator_selectors": ["sel_user_profile_badge", "sel_logout_btn"],
      "evidence_ids": ["EV-LION-AUTH-002"]
    },
    "STATE_CAN_ORDER_TRUE": {
      "label": "Product Available for Direct Web Purchase",
      "indicator_selectors": ["sel_btn_buy_enabled"],
      "evidence_ids": ["EV-LION-PDP-006"]
    },
    "STATE_INQUIRY_ONLY": {
      "label": "Product Requires Commercial Inquiry (No Direct Cart)",
      "indicator_selectors": ["sel_btn_inquiry", "sel_badge_call_for_price"],
      "evidence_ids": ["EV-LION-PDP-007"]
    }
  }
}
```

---

## 8. ACTION SCHEMA

Actions formalize every step that an automation adapter can execute against a node:

```json
{
  "id": "action_add_quantity_to_cart",
  "label": "Enter Quantity and Click Buy",
  "action_type": "add_to_cart",
  "target_input_node_id": "node_input_quantity",
  "target_button_node_id": "node_btn_add_to_cart",
  "preconditions": [
    "STATE_CAN_ORDER_TRUE",
    "node_input_quantity.is_visible()",
    "quantity >= order_constraints.moq",
    "quantity % order_constraints.order_multiple == 0"
  ],
  "postconditions": [
    "CART.item_count > previous_count",
    "STATE_CART_UPDATE_SUCCESS"
  ],
  "timeout_ms": 10000,
  "evidence_ids": ["EV-LION-CART-003"]
}
```

---

## 9. ERROR SCHEMA

Error mappings bind vendor-specific failure indicators to normalized Omnix error categories. Observable signatures may originate from DOM modals, toast elements, HTTP response status codes, network payload bodies, or security challenge states:

```json
{
  "id": "err_swal_moq_multiple_mismatch",
  "error_type": "ORDER_MULTIPLE_VIOLATION",
  "trigger_node_id": "node_btn_add_to_cart",
  "signature_type": "DOM_MODAL",
  "observable_signature": {
    "modal_selector_id": "sel_swal_container",
    "text_keywords": ["ضریب", "مضرب", "بسته بندی", "حداقل"]
  },
  "recovery_action": "action_dismiss_swal_and_round_quantity",
  "terminal": false,
  "evidence_ids": ["EV-LION-ERR-001"]
}
```

For network or security challenge errors (e.g. `NETWORK_ERROR`, `WAF_BLOCK`, `NOT_FOUND`):
```json
{
  "id": "err_http_404_not_found",
  "error_type": "NOT_FOUND",
  "trigger_node_id": "node_page_pdp",
  "signature_type": "HTTP_STATUS",
  "observable_signature": {
    "http_status": 404,
    "url_redirect_pattern": "/404|/not-found"
  },
  "recovery_action": "action_flag_item_unfulfillable",
  "terminal": true,
  "evidence_ids": ["EV-LION-ERR-002"]
}
```


---

## 10. EVIDENCE REFERENCE & TRACEABILITY RULES

1. **Zero Unreferenced Elements:** Every node, edge, selector, data extraction rule, and error mapping **must** include at least one valid `evidence_ids` reference.
2. **Format Uniformity:** Evidence IDs must strictly follow the syntax `EV-{VENDOR}-{WORKFLOW}-{INDEX}`.
3. **Validation Enforcement:** Schema linters must reject any graph containing empty `evidence_ids` arrays on active production nodes.

---

## 11. GRAPH VALIDATION RULES

A `SITE_MAP_GRAPH.json` artifact is invalid if any of the following automated checks fail:

* **`VAL-001` Duplicate Node IDs:** All node IDs must be globally unique across the graph.
* **`VAL-002` Duplicate Edge IDs:** All edge IDs must be unique across the graph.
* **`VAL-003` Orphan Node Detection:** Every node (except root `PAGE: Home`) must have at least one incoming or outgoing edge.
* **`VAL-004` Dead-End Unreachable States:** Non-terminal nodes must have valid recovery or navigation transitions.
* **`VAL-005` Broken Selector References:** Any `selector_id` referenced in a node or extraction rule must exist in the `selectors` dictionary.
* **`VAL-006` Vendor Isolation Integrity:** Graph must contain zero mentions of procurement business logic, BOM math, or vendor ranking algorithms.

---

## 12. COMPLETE REFERENCE EXAMPLE (ILLUSTRATIVE TEMPLATE)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "metadata": {
    "vendor_id": "example_distributor",
    "vendor_name": "Example Electronic Components Ltd",
    "base_url": "https://example-distributor.test",
    "schema_version": "1.0.0",
    "discovery_version": "1.0.0",
    "created_at": "2026-09-16T15:00:00Z",
    "updated_at": "2026-09-16T16:00:00Z",
    "last_verified": "2026-09-16T16:00:00Z",
    "verification_status": "OBSERVED"
  },
  "nodes": [
    {
      "id": "node_page_home",
      "type": "PAGE",
      "label": "Store Frontpage",
      "url_pattern": "^https://example-distributor\\.test/?$",
      "selectors": ["sel_body_home"],
      "evidence_ids": ["EV-EX-HOME-001"]
    },
    {
      "id": "node_input_search",
      "type": "INPUT",
      "label": "Catalog Search Field",
      "selectors": ["sel_input_search"],
      "evidence_ids": ["EV-EX-SRCH-001"]
    },
    {
      "id": "node_btn_search_submit",
      "type": "BUTTON",
      "label": "Search Submit Button",
      "selectors": ["sel_btn_search_submit"],
      "evidence_ids": ["EV-EX-SRCH-002"]
    },
    {
      "id": "node_page_search_results",
      "type": "PAGE",
      "label": "Search Results View",
      "url_pattern": "^https://example-distributor\\.test/search\\?q=.*$",
      "selectors": ["sel_results_container"],
      "evidence_ids": ["EV-EX-SRCH-003"]
    },
    {
      "id": "node_page_pdp",
      "type": "PAGE",
      "label": "Product Detail Page",
      "url_pattern": "^https://example-distributor\\.test/products/\\d+$",
      "selectors": ["sel_pdp_container"],
      "evidence_ids": ["EV-EX-PDP-001"]
    },
    {
      "id": "node_input_qty",
      "type": "INPUT",
      "label": "Purchase Quantity Input",
      "selectors": ["sel_input_qty"],
      "evidence_ids": ["EV-EX-PDP-002"]
    },
    {
      "id": "node_btn_add_to_cart",
      "type": "BUTTON",
      "label": "Add to Cart Button",
      "selectors": ["sel_btn_buy"],
      "evidence_ids": ["EV-EX-PDP-003"]
    },
    {
      "id": "node_cart_page",
      "type": "CART",
      "label": "Shopping Cart Page",
      "url_pattern": "^https://example-distributor\\.test/cart$",
      "selectors": ["sel_cart_table"],
      "evidence_ids": ["EV-EX-CART-001"]
    }
  ],
  "edges": [
    {
      "id": "edge_home_contains_search_input",
      "source_node_id": "node_page_home",
      "target_node_id": "node_input_search",
      "relationship_type": "CONTAINS",
      "condition": null,
      "evidence_ids": ["EV-EX-HOME-002"]
    },
    {
      "id": "edge_search_triggers_results",
      "source_node_id": "node_btn_search_submit",
      "target_node_id": "node_page_search_results",
      "relationship_type": "NAVIGATES_TO",
      "condition": "input.value.length > 0",
      "evidence_ids": ["EV-EX-SRCH-004"]
    },
    {
      "id": "edge_buy_triggers_cart_update",
      "source_node_id": "node_btn_add_to_cart",
      "target_node_id": "node_cart_page",
      "relationship_type": "UPDATES",
      "condition": "quantity >= moq",
      "evidence_ids": ["EV-EX-CART-002"]
    }
  ],
  "selectors": {
    "sel_body_home": {
      "id": "sel_body_home",
      "type": "css",
      "value": "body.homepage",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-HOME-001"]
    },
    "sel_input_search": {
      "id": "sel_input_search",
      "type": "id",
      "value": "site-search-input",
      "priority": 1,
      "stability": "SEMANTIC_ID",
      "evidence_ids": ["EV-EX-SRCH-001"]
    },
    "sel_btn_search_submit": {
      "id": "sel_btn_search_submit",
      "type": "css",
      "value": "button.search-submit-btn",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-SRCH-002"]
    },
    "sel_results_container": {
      "id": "sel_results_container",
      "type": "css",
      "value": "div.search-results-grid",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-SRCH-003"]
    },
    "sel_pdp_container": {
      "id": "sel_pdp_container",
      "type": "css",
      "value": "div.product-detail-view",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-PDP-001"]
    },
    "sel_input_qty": {
      "id": "sel_input_qty",
      "type": "id",
      "value": "order-quantity-input",
      "priority": 1,
      "stability": "SEMANTIC_ID",
      "evidence_ids": ["EV-EX-PDP-002"]
    },
    "sel_btn_buy": {
      "id": "sel_btn_buy",
      "type": "css",
      "value": "button.btn-add-to-cart",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-PDP-003"]
    },
    "sel_cart_table": {
      "id": "sel_cart_table",
      "type": "css",
      "value": "table.cart-items-table",
      "priority": 1,
      "stability": "STABLE_CLASS",
      "evidence_ids": ["EV-EX-CART-001"]
    }
  },
  "extractions": [
    {
      "id": "ext_mpn",
      "field_name": "mpn",
      "source_node_id": "node_page_pdp",
      "source_type": "DOM_TEXT",
      "selector_id": "sel_pdp_container",
      "attribute": null,
      "regex": "Part Number:\\s*([A-Za-z0-9_-]+)",
      "transform": "TRIM_UPPERCASE",
      "normalization_rule": null,
      "required": true,
      "evidence_ids": ["EV-EX-PDP-004"]
    }
  ],
  "errors": [
    {
      "id": "err_out_of_stock",
      "error_type": "OUT_OF_STOCK",
      "trigger_node_id": "node_btn_add_to_cart",
      "observable_signature": {
        "text_keywords": ["Out of Stock", "موجودی کافی نیست"]
      },
      "recovery_action": "action_abort_item",
      "terminal": true,
      "evidence_ids": ["EV-EX-ERR-001"]
    }
  ]
}
```
