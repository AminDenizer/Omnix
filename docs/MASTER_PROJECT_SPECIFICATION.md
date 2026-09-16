# MASTER PROJECT SPECIFICATION (MPS)
## Omnix: Deterministic Multi-Vendor Electronics Procurement Platform

**Document Reference:** `DOC-OMNIX-MPS-001`  
**Version:** `1.0.0-DRAFT`  
**Status:** Approved Specification Baseline  
**Target System:** Omnix Enterprise Core & Multi-Vendor Ecosystem  
**Author:** DOT Engineering / Architecture Taskforce  
**Baseline Reference:** Technical Audit v1.0.0 (`atom/Auto` branch)

---

## 1. PRODUCT DEFINITION

### 1.1 Core Mission
**Omnix** is a deterministic, multi-vendor electronic component procurement automation platform. Its primary objective is to transform raw engineering design outputs—specifically Altium Designer Bills of Materials (BOMs)—into verified, cost-optimized, and constraint-compliant purchasing orders across multiple independent electronic component distributors.

```
+─────────────────+      +─────────────────────+      +──────────────────────+      +───────────────────────+
|   Altium BOM    | ───► | Component Identity  | ───► | Dynamic Multi-Vendor | ───► |  Constraint-Compliant |
| Import & Parse  |      |   & Normalization   |      |  Discovery & Match   |      | Cart & Order Creation |
+─────────────────+      +─────────────────────+      +──────────────────────+      +───────────────────────+
```

### 1.2 Long-Term System Capabilities
1. **Multi-Source BOM Ingestion:** Ingest and parse engineering BOMs (Altium Designer `.xlsx`/`.csv` exports) with heterogeneous column taxonomies.
2. **Deterministic Component Normalization:** Dissect raw engineering strings into structured technical parameters (Manufacturer Part Number [MPN], Manufacturer, Footprint/Package, Physical Case Size, Electrical Ratings, Tolerance, Suffixes).
3. **Dual-Mode Procurement Intent:** Support both **Inventory-Based** procurement (purchasing net shortages against internal stock) and **BOM-Direct** procurement (purchasing full batch build requirements regardless of on-hand inventory).
4. **Dynamic Catalog Discovery:** Autonomously search, query, and identify target components on live vendor platforms without relying on pre-existing, hard-coded URLs.
5. **Multi-Attribute Product Matching:** Formally verify candidate vendor products against engineering requirements, distinguishing exact matches from incompatible variants (e.g., rejecting an 0603 passive when an 0805 footprint is required).
6. **Constraint-Aware Quantity Computation:** Mathematically resolve vendor Minimum Order Quantities (MOQs), packaging order multiples (ضریب سفارش / بسته بندی), and available vendor stock levels.
7. **Multi-Vendor Split Allocation:** Distribute a single BOM procurement requirement across multiple coexisting vendors based on availability, lead time, and cost constraints.
8. **Automated Cart Staging:** Execute deterministic, headless/visible browser sessions to authenticate, validate site stock, and populate vendor shopping carts.
9. **Full Auditability & Reporting:** Generate structured purchase breakdown reports, historical decision logs, and verified stock increment manifests.

### 1.3 Target vs. Current Paradigm

| Dimension | Current State (Audit Baseline) | Target State (MPS) |
|---|---|---|
| **Vendor Scope** | Monolithic single-vendor script tied exclusively to `lionelectronic.ir`. | Vendor-agnostic Core hosting multiple concurrently active `IVendorAdapter` instances. |
| **Product Discovery** | 100% dependent on static URLs hard-coded in an Excel column. | Dynamic search querying vendor catalogs by MPN, attributes, and package. |
| **Procurement Mode** | Single heuristic shortage check against `Inventory.xlsx`. | Explicit selection between **Mode A (Inventory-Based)** and **Mode B (BOM-Direct)**. |
| **Component Identity** | Loose substring matching on raw `Part Name` / `Part Number`. | Multi-attribute domain model (MPN, Manufacturer, Package, Size, Tolerance, Suffix). |
| **Quantity Logic** | Hard-coded Lion step rules embedded inside Selenium automation code. | Formal mathematical constraint engine executing in Core prior to vendor automation. |
| **Persistence** | Direct cell-level reading/writing to `Inventory.xlsx` on local disk via `openpyxl`. | Abstract Repository Layer separating persistent application state from export formats. |
| **Execution Safety** | Fragile DOM scraping with hard-coded Persian error string checks. | Structured discovery-mapped selectors, contract-tested adapters, and state machines. |

---

## 2. MULTI-VENDOR COEXISTENCE PRINCIPLE

### 2.1 Coexistence Invariant
Multiple vendors **must coexist simultaneously** within the platform runtime. Vendor adapters are modular plugins; **Vendor B does not replace Vendor A**.

```
                           ┌─────────────────────────────────────────┐
                           │               OMNIX CORE                │
                           │  (BOM Engine, Matching, Order Decision) │
                           └────────────────────┬────────────────────┘
                                                │
                                    IVendorAdapter Interface
                                                │
                   ┌────────────────────────────┼────────────────────────────┐
                   ▼                            ▼                            ▼
         ┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
         │   Lion Adapter    │        │   Javan Adapter   │        │   Paya Adapter    │
         │ (lionelectronic.ir)│        │  (javanelec.com)  │        │ (payaelectronics) │
         └───────────────────┘        └───────────────────┘        └───────────────────┘
```

### 2.2 Core Independence Rule
1. **Zero Vendor Logic in Core:** The Core engine must never contain vendor-specific domain names, URL structures, HTML/CSS selectors, API headers, or packaging heuristics.
2. **Uniform Adapter Contracts:** All vendor-specific communication occurs exclusively through the `IVendorAdapter` contract.
3. **Simultaneous Multi-Vendor Sourcing:** A single BOM consisting of 50 line items can be fulfilled simultaneously by 3 distinct vendors:
   - Items 1–20: Routed to **Lion Electronic** (Adapter `vendor_lion`)
   - Items 21–35: Routed to **Javan Electronic** (Adapter `vendor_javan`)
   - Items 36–50: Routed to **Future Distributor X** (Adapter `vendor_x`)

---

## 3. BOM & PROCUREMENT MODES

The BOM is the primary origin of procurement intent. Procurement modes belong strictly to the **BOM/Procurement-Intent Layer** and are completely independent of vendor adapter implementations.

```
                                  [ Altium BOM ]
                                         │
                                         ▼
                     Select Procurement Mode (BOM-Level Intent)
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
     [ Mode A: Inventory-Based ]                     [ Mode B: BOM-Direct ]
                 │                                               │
     Read On-Hand Stock from DB                      Ignore On-Hand Stock from DB
                 │                                               │
     Calculate Shortage:                             Procurement Requirement =
     Needed = max(0, BOM_Req - Stock)                BOM_Req (Full Batch Quantity)
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                        [ Core Procurement Engine ]
                       Apply Vendor MOQ & Multiples
```

### 3.1 Mode A: Inventory-Based Procurement
* **Conceptual Definition:** Procurement is calculated to satisfy the net deficit between production requirements and available warehouse stock.
* **Governing Parameters:**
  - $Q_{\text{BOM}}$: Gross quantity required by the BOM for a single board.
  - $M_{\text{Board}}$: Total number of boards to assemble in the current production run.
  - $Q_{\text{Gross}} = Q_{\text{BOM}} \times M_{\text{Board}}$: Total gross component demand.
  - $S_{\text{Current}}$: Total physical stock recorded in internal inventory.
  - $S_{\text{Min}}$: Configured safety/reorder threshold in internal inventory.
  - $S_{\text{Target}}$: Configured target replenishment stock level.
* **Shortage Formulation:**
  - **Standard Shortage:**
    $$\Delta_{\text{Shortage}} = \max\left(0, Q_{\text{Gross}} - S_{\text{Current}}\right)$$
  - **Restock-Aware Shortage (when $S_{\text{Current}} - Q_{\text{Gross}} < S_{\text{Min}}$):**
    $$\Delta_{\text{Procure}} = \max\left(\Delta_{\text{Shortage}}, (S_{\text{Target}} - (S_{\text{Current}} - Q_{\text{Gross}}))\right)$$
  *(Note: Exact safety stock replenishment policies are documented in Section 23 as Open Decisions).*

### 3.2 Mode B: BOM-Direct Procurement
* **Conceptual Definition:** Procurement is executed strictly for the project batch requirements, completely bypassing and ignoring internal warehouse stock levels.
* **Governing Formulation:**
  $$Q_{\text{Procure}} = Q_{\text{Gross}} = Q_{\text{BOM}} \times M_{\text{Board}}$$
* **Operational Intent:** Used for dedicated client turnkey projects, high-volume production batches where inventory must not be depleted, or organizations operating without internal warehouse stocking.

---

## 4. ORDER CONSTRAINTS & QUANTITY RESOLUTION

Vendors impose commercial and packaging constraints that dictate how raw component requirements must be converted into valid purchase orders.

### 4.1 Constraint Definitions

| Constraint Term | Symbol | Persian Term | Definition |
|---|---|---|---|
| **Required Quantity** | $Q_{\text{Req}}$ | تعداد مورد نیاز | The net required quantity calculated by the BOM Procurement Layer (Mode A or Mode B). |
| **Minimum Order Quantity (MOQ)** | $Q_{\text{MOQ}}$ | حداقل تعداد سفارش | The absolute minimum number of units a vendor will sell for a given line item. |
| **Order Multiple / Quantity Multiple** | $M_{\text{Order}}$ | ضریب سفارش / مضرب بسته‌بندی | The increment step size enforced by vendor packaging (e.g. reels of 100, strips of 10, tubes of 50). **This is a packaging quantity constraint, NOT a price discount.** |
| **Available Vendor Stock** | $S_{\text{Vendor}}$ | موجودی فروشنده | The live quantity of physical stock available for immediate purchase on the vendor's catalog. |
| **Maximum Order Quantity** | $Q_{\text{Max}}$ | حداکثر تعداد مجاز | The maximum ceiling of units a vendor permits per single order or customer session. |

### 4.2 Deterministic Quantity Resolution Algorithm
For any component requiring quantity $Q_{\text{Req}} > 0$ matched to a vendor with constraints $(Q_{\text{MOQ}}, M_{\text{Order}}, S_{\text{Vendor}})$:

$$\text{Step 1: Apply Order Multiple Ceiling}$$
$$Q_{\text{Multiple}} = \left\lceil \frac{Q_{\text{Req}}}{M_{\text{Order}}} \right\rceil \times M_{\text{Order}}$$

$$\text{Step 2: Enforce Minimum Order Quantity}$$
$$Q_{\text{Target}} = \max\left(Q_{\text{Multiple}}, Q_{\text{MOQ}}\right)$$

$$\text{Step 3: Validate Against Vendor Stock}$$
$$\text{Status} = \begin{cases} 
\text{VALID} & \text{if } Q_{\text{Target}} \le S_{\text{Vendor}} \\
\text{INSUFFICIENT\_STOCK} & \text{if } S_{\text{Vendor}} < Q_{\text{Target}} \text{ and } S_{\text{Vendor}} \ge Q_{\text{MOQ}} \\
\text{UNFULFILLABLE} & \text{if } S_{\text{Vendor}} < Q_{\text{MOQ}}
\end{cases}$$

### 4.3 Practical Electronics Constraint Examples

* **Example 1 (Chip Resistors in Tape/Reel):**
  - BOM Requirement: $Q_{\text{Req}} = 45$ pcs
  - Vendor Constraints: $\text{MOQ} = 10$, $\text{Order Multiple} = 10$
  - Calculation: $\lceil 45 / 10 \rceil \times 10 = 50 \ge 10 \implies \mathbf{Q_{\text{Final}} = 50\text{ pcs}}$.
* **Example 2 (Microcontroller in Tube):**
  - BOM Requirement: $Q_{\text{Req}} = 12$ pcs
  - Vendor Constraints: $\text{MOQ} = 25$ (1 Tube), $\text{Order Multiple} = 25$
  - Calculation: $\max(\lceil 12 / 25 \rceil \times 25, 25) \implies \mathbf{Q_{\text{Final}} = 25\text{ pcs}}$.
* **Example 3 (High-Value Sensor with Odd Requirement):**
  - BOM Requirement: $Q_{\text{Req}} = 11$ pcs
  - Vendor Constraints: $\text{MOQ} = 1$, $\text{Order Multiple} = 2$
  - Calculation: $\lceil 11 / 2 \rceil \times 2 = 12 \ge 1 \implies \mathbf{Q_{\text{Final}} = 12\text{ pcs}}$.

---

## 5. COMPONENT IDENTITY & DOMAIN DATA MODEL

Component identity in electronics engineering cannot be established by a single Part Number string. Physical packaging, voltage ratings, temperature grades, and manufacturer suffixes represent distinct, non-interchangeable physical items.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             COMPONENT DOMAIN                             │
├────────────────────────────┬─────────────────────────────────────────────┤
│ 1. Primary Identifiers     │ MPN, Manufacturer/Brand, Internal SKU/ECODE │
├────────────────────────────┼─────────────────────────────────────────────┤
│ 2. Physical Attributes     │ Package/Case (0805, SOIC-8), Footprint, Size│
├────────────────────────────┼─────────────────────────────────────────────┤
│ 3. Electrical Attributes   │ Value (10k, 100nF), Voltage (50V), Tol (1%) │
├────────────────────────────┼─────────────────────────────────────────────┤
│ 4. Commercial Attributes   │ Packaging Suffix (-TR, -ND, /REEL), RoHS    │
└────────────────────────────┴─────────────────────────────────────────────┘
```

### 5.1 Conceptual Data Tiers

1. **Raw BOM Record (`RawBOMRecord`):** Unsanitized text lines directly extracted from CAD exports (e.g. `Comment="100nF 50V 0805"`, `Designator="C1, C2"`, `Footprint="CAPC2012X110N"`).
2. **Normalized Engineering Component (`CanonicalComponent`):** Deterministically parsed domain entity where electrical values, physical package codes, tolerances, and MPNs are split into typed properties.
3. **Live Vendor Product (`LiveVendorProduct`):** Product data returned by a vendor search or detail page (vendor SKU, vendor title, raw vendor package string, live price tiers, live stock, MOQ, order multiple).
4. **Matching Assessment (`MatchDecision`):** The deterministic output evaluating candidate compatibility (Exact Match, Suffix Variant, Package Conflict, Rejected).

### 5.2 Physical Dimension Invariant
* Components with identical electrical values but differing physical case sizes (e.g., `0402`, `0603`, `0805`, `1206`, `1210`) are **strictly non-interchangeable** on printed circuit board assemblies.
* The system must **never guess or auto-substitute** physical footprint sizes without explicit rule configuration.

---

## 6. DYNAMIC VENDOR PRODUCT DISCOVERY

### 6.1 Discovery Pipeline
The system must transition from static link dependency to dynamic catalog exploration:

```
[ CanonicalComponent ]
         │
         ▼
[ Vendor Adapter ] ──► Formulate Search Query (1. Exact MPN ──► 2. Base Part Number ──► 3. Value + Package)
         │
         ▼
[ Vendor Web / API ] ──► Execute Search Request (HTTP REST or Browser DOM Search)
         │
         ▼
[ Search Results ] ──► Extract Candidate Product Cards (URLs, Titles, Prices, Stock)
         │
         ▼
[ Product Matcher ] ──► Deterministic Verification against CanonicalComponent
         │
         ▼
[ Selected Product ] ──► Fetch Live Order Constraints & Populate Cart
```

### 6.2 Discovery Hierarchy
1. **Tier 1 (Exact MPN Query):** Query vendor catalog using the exact alphanumeric Manufacturer Part Number (e.g., `STM32F103C8T6`, `LM358N`).
2. **Tier 2 (Base MPN Fallback):** Strip commercial packaging suffixes (`-REEL`, `TR`, `PBF`, `#PBF`) and search base silicon designation.
3. **Tier 3 (Parametric Keyword Query):** For passives and standard discrete parts lacking explicit MPNs, query by standardized composite terms (e.g., `Resistor 10k 0805 1%`, `Capacitor 100uF 25V SMD 6.3`).

---

## 7. SITE DISCOVERY & SITE MAPPING (PHASE ROLE)

Site Discovery is a dedicated engineering methodology for dissecting vendor websites prior to implementing their adapters.

### 7.1 Discovery Relationship Graph
A vendor website is formalized as an interactive directed state graph:

$$\text{Page} \xrightarrow{\text{Element}} \text{Action} \xrightarrow{} \text{Result} \xrightarrow{} \text{Data / State} \xrightarrow{\text{Trigger}} \text{Error / Modal}$$

```
[ Vendor Home / Catalog ]
         │
         ├─── Action: Submit Query into #search-input
         │          │
         │          ▼
         └───► [ Search Results View ]
                    │
                    ├─── State A: Single exact redirect ──► [ Product Detail Page ]
                    │                                             │
                    ├─── State B: Multiple results list           │
                    │         │                                   │
                    │         └── Action: Click Product Link ─────┘
                    │
                    └─── State C: 0 Results ──► [ Empty Search State ]
                                                      │
                    ┌─────────────────────────────────┘
                    ▼
         [ Product Detail Page ]
         ├── Extract: Stock Quantity (.stock-amount)
         ├── Extract: Packaging Step (#quantity-cell)
         ├── Extract: Price Breaks (.price-tier-table)
         └── Action: Set Quantity & Click button.btn-buy
                    │
                    ├── State 1: AJAX Success ──► Item in Cart (.cart-count + 1)
                    └── State 2: SweetAlert / Error Modal (.swal2-modal)
                                  ├── MOQ Violation Alert
                                  └── Out of Stock Alert
```

### 7.2 Graph Artifact Representation
Future Site Maps will be stored as structured declarative JSON/YAML graph specifications that document every URL pattern, DOM selector, API endpoint, network payload, and error state machine for each vendor.

---

## 8. CORE ARCHITECTURE & SUBSYSTEM BOUNDARIES

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                       OMNIX CORE                                       │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ Subsystem                │ Owns / Responsibilities  │ Boundary & Output                │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 1. BOM Engine            │ Ingestion, Multiplier,   │ Produces CanonicalBOM and        │
│                          │ Mode Selection (A/B)     │ ProcurementRequirements          │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 2. Component Model       │ Canonical attributes,    │ CanonicalComponent entities      │
│                          │ Normalization rules      │                                  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 3. Matching Engine       │ Verification, Footprint  │ MatchDecision & Confidence Score │
│                          │ compatibility checking   │                                  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 4. Inventory Repository  │ Read/Write on-hand stock,│ Decoupled storage interface      │
│                          │ Reserve quantities       │                                  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 5. Procurement Engine    │ Constraint calculation,  │ Validated ProcurementPlan        │
│                          │ Vendor distribution      │                                  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 6. Vendor Registry       │ Plugin discovery,        │ Instantiated IVendorAdapter      │
│                          │ Lifecycle management     │ instances                        │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 7. Audit & Reporting     │ Event logging, Decision  │ Structured ProcurementReport &   │
│                          │ trail, Execution metrics │ AuditTrail manifests             │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

---

## 9. VENDOR ADAPTER ARCHITECTURE

### 9.1 Adapter Responsibility Contract
Every vendor adapter must inherit from `IVendorAdapter` and encapsulate:
1. **Authentication & Session:** Managing logins, cookies, headers, and token refresh.
2. **Catalog Discovery & Search:** Querying vendor search endpoints and parsing result cards.
3. **Product Detail Extraction:** Extracting live stock, price tiers, package strings, and step constraints.
4. **Quantity Constraint Mapping:** Translating vendor site rules into normalized `OrderConstraints`.
5. **Cart Operations:** Programmatically injecting products into shopping carts.
6. **Error Normalization:** Mapping vendor-specific DOM alerts (e.g. SweetAlert2 modals, Persian warning spans) into standard typed exceptions (`OutOfStockError`, `MOQViolationError`, `SessionExpiredError`).

---

## 10. PROCUREMENT ENGINE WORKFLOW

```
  1. Ingest BOM & Board Multiplier
                 │
  2. Select Mode (A: Inventory-Based | B: BOM-Direct)
                 │
  3. Formulate Net Procurement Requirements (Q_Req)
                 │
  4. Query Vendor Registry for Active Adapters
                 │
  5. Search Candidate Products Across Vendors
                 │
  6. Filter Incompatible Packages/Variants via Matching Engine
                 │
  7. Fetch Live Stock & Constraints (MOQ, Order Multiple)
                 │
  8. Execute Quantity Optimization Algorithm (Section 4.2)
                 │
  9. Generate Multi-Vendor Sourcing Allocation
                 │
 10. Present Procurement Plan for Human Confirmation
                 │
 11. Dispatch Staged Cart Execution to Vendor Adapters
```

---

## 11. MULTI-VENDOR ALLOCATION & DISTRIBUTION

When a component is available across multiple vendors, or when no single vendor has sufficient stock to fulfill the total requirement, the Procurement Engine must support multi-vendor order distribution.

### 11.1 Sourcing Scenarios
* **Scenario A (Single Best Vendor):** Vendor 1 has full stock and lower price $\implies$ 100% allocated to Vendor 1.
* **Scenario B (Split Inventory Sourcing):** Requirement = 500 pcs.
  - Vendor A Stock = 200 pcs (Allocated: 200 pcs)
  - Vendor B Stock = 400 pcs (Allocated: 300 pcs)
  - Total Purchased = 500 pcs across 2 vendors.
* **Scenario C (MOQ-Constrained Sourcing):** Requirement = 80 pcs. Vendor A MOQ = 100 pcs, Vendor B MOQ = 25 pcs (Multiple 25 $\implies$ 100 pcs). Decision engine compares total financial outlay.

*(Note: Specific vendor ranking and optimization algorithms are documented in Section 23 as Open Decisions).*

---

## 12. PURCHASE RESULT DATA MODEL

The output of a procurement run is a structured `ProcurementReport` containing line-item detail:

```json
{
  "procurement_id": "ORD-20260916-001",
  "timestamp": "2026-09-16T15:30:00Z",
  "bom_name": "FC_IO_V_1_2.xlsx",
  "board_multiplier": 10,
  "procurement_mode": "INVENTORY_BASED",
  "summary": {
    "total_bom_items": 45,
    "in_stock_items": 30,
    "procured_items": 15,
    "total_vendor_orders": 2
  },
  "allocations": [
    {
      "vendor_id": "vendor_lion",
      "vendor_name": "Lion Electronic",
      "items": [
        {
          "designator": "U1, U2",
          "mpn": "NE555P",
          "matched_sku": "2070-NE555P",
          "package": "DIP-8",
          "needed_qty": 20,
          "vendor_moq": 10,
          "vendor_multiple": 10,
          "final_purchase_qty": 20,
          "unit_price": 12000,
          "total_price": 240000,
          "status": "ADDED_TO_CART"
        }
      ]
    },
    {
      "vendor_id": "vendor_javan",
      "vendor_name": "Javan Electronic",
      "items": [
        {
          "designator": "R1-R10",
          "mpn": "RC0805FR-0710KL",
          "matched_sku": "RES-0805-10K",
          "package": "0805",
          "needed_qty": 100,
          "vendor_moq": 50,
          "vendor_multiple": 50,
          "final_purchase_qty": 100,
          "unit_price": 450,
          "total_price": 45000,
          "status": "ADDED_TO_CART"
        }
      ]
    }
  ]
}
```

---

## 13. AUDIT TRAIL & TRACEABILITY

Every state change, data transformation, and procurement action must be recorded in an append-only audit trail:

1. **BOM Ingestion Event:** Hash of imported file, total parsed rows, detected CAD format.
2. **Matching Decision Event:** Candidate search queries, raw vendor candidates returned, scoring breakdown, match rationale.
3. **Constraint Resolution Event:** Initial shortage quantity, applied MOQ, applied order multiple, final quantity adjustment.
4. **Vendor Session Event:** Timestamp of login, session IP, cart payload submission, vendor response status.
5. **Inventory Sync Event:** Pre-order stock level, post-payment increment amount, updated timestamp.

---

## 14. DETERMINISTIC AUTOMATION PRINCIPLE

Omnix operates under a strict **Zero-Black-Box Determinism** guarantee:

1. **No Runtime AI Decision-Making:** Production procurement decisions (which MPN to purchase, which vendor to select, what quantity to order) must **never** depend on non-deterministic generative models or unpredictable AI agent loops.
2. **Deterministic Rules & Constraints:** All quantity calculations, package checks, and multi-vendor allocations are governed by strict mathematical equations, deterministic parsers, and explicit user-configured business rules.
3. **Role of AI:** AI is utilized strictly during offline development phases (codebase audits, technical specifications, exploratory site structure analysis, and test generation).

---

## 15. CONCEPTUAL DATA DOMAINS

```
┌──────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│     BOM DOMAIN   │       │   COMPONENT DOMAIN   │       │    VENDOR DOMAIN     │
├──────────────────┤       ├──────────────────────┤       ├──────────────────────┤
│ • BOMHeader      │ ────► │ • CanonicalComponent │ ◄───► │ • VendorProfile      │
│ • BOMLineItem    │       │ • PhysicalPackage    │       │ • LiveVendorProduct  │
│ • AssemblyConfig │       │ • ElectricalRating   │       │ • PriceTierBreak     │
└──────────────────┘       └──────────────────────┘       │ • OrderConstraints   │
                                                          └──────────────────────┘
                                     │                               │
                                     ▼                               ▼
                           ┌──────────────────────────────────────────────┐
                           │              PROCUREMENT DOMAIN              │
                           ├──────────────────────────────────────────────┤
                           │ • ProcurementRequirement                     │
                           │ • MatchCandidate                             │
                           │ • PurchaseAllocation                         │
                           │ • StagedCartManifest                         │
                           │ • AuditTrailEvent                            │
                           └──────────────────────────────────────────────┘
```

---

## 16. EXCEL PERSISTENCE & DATABASE EVOLUTION

### 16.1 Current vs. Target Persistence Model

```
CURRENT STATE (Anti-Pattern):
[ UI Table ] ◄── direct cell bind ──► [ ExcelDataLoader ] ◄── disk I/O ──► [ Inventory.xlsx ]
                                                                                  ▲
[ Scraper / Auditor ] ──────────────────── direct cell lookup ───────────────────┘

TARGET STATE (Clean Separation):
[ UI Presentation ] ──────► [ Procurement / Inventory Application Service ]
                                                 │
                                                 ▼
                                     [ IInventoryRepository ]
                                                 │
                                ┌────────────────┴────────────────┐
                                ▼                                 ▼
                    [ SQLite / Embedded DB ]             [ Excel File Adapter ]
                    (Primary ACID Storage)               (Import / Export / Reports)
```

### 16.2 Excel Migration Strategy
* **Preserve User Workflow:** Excel remains fully supported as a human-friendly format for importing BOMs, downloading purchase reports, and exporting inventory snapshots.
* **Decouple Core Runtime:** Runtime data queries (search, stock updates, matching) execute against an in-memory/embedded ACID repository to prevent Windows file locking issues (`PermissionError: [Errno 13]`) and eliminate data corruption.

---

## 17. ERROR TAXONOMY & FAULT TOLERANCE

| Error Category | Specific Error Types | Handling & Recovery Strategy |
|---|---|---|
| **1. Ingestion Errors** | `InvalidBOMFormat`, `MissingDesignators`, `CorruptSpreadsheet` | Reject import with exact cell coordinate error message; request user re-export. |
| **2. Identity Errors** | `AmbiguousFootprint`, `ConflictingSpecs`, `UnrecognizedMPN` | Flag component as `REQUIRES_HUMAN_RESOLUTION`; pause ordering for that specific item. |
| **3. Search Errors** | `VendorCatalogUnavailable`, `ZeroSearchResults`, `NetworkTimeout` | Log search failure, attempt Tier 2/3 fallback queries; fallback to alternative active vendors. |
| **4. Constraint Errors**| `InsufficientVendorStock`, `MOQExceedsBudget`, `DiscontinuedPart` | Trigger multi-vendor split allocation or flag for manual procurement approval. |
| **5. Session Errors** | `AuthenticationFailed`, `CaptchaTriggered`, `SessionExpired` | Pause automation worker; notify user via GUI modal to solve challenge or update credentials. |
| **6. Site Drift Errors** | `DOMSelectorNotFound`, `UnexpectedModal`, `CartPayloadRejected` | Abort specific vendor worker cleanly; preserve error screenshot/DOM dump in audit logs. |

---

## 18. SECURITY ARCHITECTURE

1. **Credential Protection:** Vendor login credentials must never be stored in plaintext JSON. Target storage must utilize OS-native encrypted keyrings (Windows DPAPI via `keyring` library).
2. **Session Isolation:** Browser automation sessions must execute in isolated temporary profiles, preventing cross-vendor cookie leaks.
3. **No Financial Automation:** Payment gateway completion (Shetab OTP / CVV2) is strictly retained as a human manual step. The system automates up to the verified shopping cart stage only.

---

## 19. DOCUMENTATION HIERARCHY

The engineering documentation suite is organized systematically:

```
docs/
├── MASTER_PROJECT_SPECIFICATION.md   # System-wide Master Specification (This Document)
├── PRD.md                            # Product Requirements Document (User Flows & Personas)
├── SRS.md                            # Software Requirements Specification (Functional/Non-Functional)
├── TDD.md                            # Technical Design Document (Class Schemas & Sequence Diagrams)
├── ADR/                              # Architecture Decision Records
│   ├── ADR-001-vendor-adapters.md
│   ├── ADR-002-deterministic-engine.md
│   └── ADR-003-persistence-evolution.md
├── DISCOVERY/                        # Discovery Methodology & Specifications
│   ├── DISCOVERY_METHODOLOGY.md
│   └── SITE_MAP_SCHEMA.md
└── VENDORS/                          # Vendor-Specific Specifications & Site Maps
    ├── LION/
    │   ├── VENDOR_SPEC.md
    │   └── SITE_MAP_GRAPH.json
    └── JAVAN/
        ├── VENDOR_SPEC.md
        └── SITE_MAP_GRAPH.json
```

---

## 20. DEVELOPMENT ROADMAP

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Technical Audit (COMPLETED)                                           │
│ └── Baseline current state, document technical debt and coupling.              │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2: Master Project Specification (CURRENT)                                │
│ └── Establish target system boundaries, procurement modes, and data models.    │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3: Formal Engineering Specifications (PRD, SRS, TDD, ADRs)               │
│ └── Detail precise algorithms, interface schemas, and state machines.          │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 4: Discovery Framework Specification                                     │
│ └── Define site mapping schemas, graph models, and DOM extraction contracts.   │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 5: Vendor Site Discovery & Site Mapping Execution                        │
│ └── Perform deep exploration of target vendor platforms (Lion, Javan, etc.).   │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 6: Vendor Adapter Specifications                                         │
│ └── Produce formal adapter specs based on verified discovery graphs.           │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 7: Core Domain & Procurement Engine Implementation                       │
│ └── Build normalized component model, Mode A/B engine, and repository layer.   │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 8: Multi-Vendor Adapter Implementation                                   │
│ └── Implement isolated Lion and Javan adapters implementing IVendorAdapter.    │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 9: Multi-Vendor UI & Allocation Integration                              │
│ └── Deliver multi-vendor procurement dashboard and order confirmation dialogs. │
├────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 10: End-to-End Hardening, Verification & CI/CD Pipeline                  │
│ └── Automated integration tests, Nuitka binary compilation, release packaging. │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 21. NON-GOALS FOR THIS PHASE

To ensure strict engineering governance, the following activities are explicitly out of scope for Phase 2:
* **NO Production Code Changes:** No modifications, refactoring, or deletion of existing Python scripts.
* **NO Site Mapping Execution:** No live crawling, network probing, or DOM inspection of vendor websites.
* **NO Adapter Implementation:** No creation of new adapter classes or modification of `lion_automator.py`.
* **NO Database Migration:** No alteration of `Inventory.xlsx` or database schemas.
* **NO Autonomous AI Runtime:** No integration of LLM/AI runtime decision loops into application logic.

---

## 22. CURRENT → TARGET → GAP TRACEABILITY MATRIX

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TRACEABILITY MATRIX                                                                             │
├────────────────────────┬─────────────────────────┬─────────────────────────┬────────────────────┤
│ Subsystem              │ Current State (Audit)   │ Target State (MPS)      │ Gap / Refactoring  │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ BOM Processing         │ Hard-coded Altium       │ Universal BOM Engine    │ Extract parser,    │
│                        │ column names in UI      │ with column mapping     │ add Mode A/B logic │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ Component Identity     │ Raw string comparison   │ Multi-attribute domain  │ Create Canonical-  │
│                        │ on Part Name/Number     │ model (MPN, Package)    │ Component model    │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ Vendor Integration     │ Monolithic scraper      │ Pluggable adapters      │ Implement IVendor- │
│                        │ tied to Lion Electronic │ via IVendorAdapter      │ Adapter interface  │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ Product Discovery      │ 100% static URLs        │ Dynamic 3-tier catalog  │ Implement vendor   │
│                        │ in Excel sheet          │ search and matching     │ search routines    │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ Quantity Constraints   │ Embedded in Selenium    │ Core mathematical       │ Move calculations  │
│                        │ script with sleeps      │ constraint engine       │ to Core engine     │
├────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────┤
│ Persistence / Data     │ Direct openpyxl file    │ Repository pattern      │ Implement storage  │
│                        │ read/write on disk      │ with SQLite backend     │ abstraction layer  │
└────────────────────────┴─────────────────────────┴─────────────────────────┴────────────────────┘
```

---

## 23. OPEN ARCHITECTURAL DECISIONS

The following architectural decisions are deliberately preserved as **Open Decisions** for Phase 3 (PRD/SRS/TDD/ADR) and cannot be unilaterally assumed:

1. **`OD-001` — Package / Footprint Standardization Taxonomy:**
   - *Options:* IPC-7351B standard naming vs. Altium generic library footprints vs. Manufacturer-specific case codes.
2. **`OD-002` — Multi-Vendor Sourcing Optimization Metric:**
   - *Options:* Pure lowest purchase cost vs. Minimum total vendor shipments vs. Shortest aggregate lead time vs. Strict user preference list.
3. **`OD-003` — Safety Stock Replenishment Formula in Mode A:**
   - *Options:* Fixed minimum delta vs. Target stock top-up vs. Dynamic historical run-rate buffer.
4. **`OD-004` — Ambiguous Match Resolution Policy:**
   - *Options:* Strict fail-stop requiring human UI confirmation vs. Highest-scoring variant auto-selection with visual review.
5. **`OD-005` — Primary Automation Engine Standard:**
   - *Options:* Retain Selenium WebDriver with enhanced anti-detection hooks vs. Migrate to Playwright async framework.
6. **`OD-006` — Credential Storage Encryption Standard:**
   - *Options:* OS-native keyring (Windows DPAPI) vs. Master-password encrypted SQLite database.

---

## 24. ARCHITECTURAL RISKS & MITIGATION

1. **Anti-Bot Countermeasures (WAF / Cloudflare / ArvanCloud):**
   - *Risk:* Vendor websites deploy bot-detection on search or cart endpoints.
   - *Mitigation:* Decouple discovery from execution, support human-assisted session initialization, recycle browser profile sessions.
2. **Vendor DOM / CSS Instability:**
   - *Risk:* Vendor website UI updates break CSS selectors.
   - *Mitigation:* Declarative Site Map graphs allowing rapid selector updates without altering core application code.
3. **Excel File Concurrency Conflicts:**
   - *Risk:* User keeping `Inventory.xlsx` open in Microsoft Excel locks the file against background application writes.
   - *Mitigation:* Isolate runtime state inside embedded SQLite repository; treat Excel purely as asynchronous import/export.

---

## 25. ACCEPTANCE CRITERIA VERIFICATION

- [x] Current and Target states are clearly demarcated.
- [x] Omnix is formally defined as a multi-vendor platform.
- [x] Multi-vendor simultaneous coexistence is guaranteed.
- [x] Core is 100% vendor-independent.
- [x] BOM/procurement layer owns procurement intent.
- [x] Mode A (Inventory-Based) and Mode B (BOM-Direct) are formally formulated.
- [x] MOQ is strictly distinguished from Order Multiples.
- [x] Component identity is multi-attribute (MPN, Footprint, Package, Specs).
- [x] Package size (e.g. 0603 vs 0805) is treated as a hard invariant.
- [x] Dynamic vendor discovery is specified over static URLs.
- [x] Site Discovery is decoupled into a dedicated future phase.
- [x] Vendor Adapters are isolated behind `IVendorAdapter`.
- [x] Multi-vendor distribution output data model is defined.
- [x] Audit trail and decision tracking are specified.
- [x] Deterministic automation rule is established (Zero runtime AI agents).
- [x] Excel is separated conceptually from persistent application state.
- [x] Error taxonomy and security boundaries are defined.
- [x] Dependency-aware roadmap is established.
- [x] Open decisions are explicitly recorded.
- [x] **Zero production code was modified.**

---

## 26. SPECIFICATION SUMMARY & NEXT PHASE

### Summary of Accomplishment
The Master Project Specification (MPS) establishes the complete conceptual and architectural foundation for transforming Omnix from a single-vendor script into a modular, multi-vendor electronics procurement platform.

### Identified Next Step
**Recommended Next Phase:** **Phase 3 — Formal Engineering Specifications (PRD, SRS, TDD & Architecture Decision Records [ADRs])** followed by **Phase 4 & 5 — Vendor Site Discovery & Site Mapping**.
