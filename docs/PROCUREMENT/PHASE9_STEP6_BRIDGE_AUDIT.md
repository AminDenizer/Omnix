# PHASE 9 — STEP 6: EXISTING PROCUREMENT CORE BRIDGE & DECOUPLING AUDIT

**Document Identifier:** `PHASE9-STEP6-BRIDGE-AUDIT`  
**Status:** APPROVED FOR EXECUTION  
**Scope:** Architecture Bridge & Decoupling between Legacy Procurement and Universal Orchestration  
**Governing Documents:**
- `docs/MASTER_PROJECT_SPECIFICATION.md`
- `docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md`

---

## 1. Executive Summary & Objective

In Phases 1 through 8, the Universal Vendor Discovery pipeline established deterministic discovery, formal specifications, and isolated adapters for three independent electronic component distributors:
1. **Lion Electronic** (`vendor_lion` — `lionelectronic.ir`)
2. **Javan Electronic** (`vendor_javan` — `javanelec.com`)
3. **RoboEq** (`vendor_roboeq` — `roboeq.ir`)

In Phase 9 Steps 1 through 5, a vendor-neutral procurement core was created:
- `core/procurement/models.py` (Immutable procurement data transfer objects)
- `core/procurement/registry.py` (Dynamic vendor registry & adapter factory)
- `core/procurement/orchestrator.py` (Universal multi-vendor procurement orchestrator)
- Full integration test coverage (165 passing tests)

**Step 6 Objective:**  
Construct the bridge (`core/procurement/bridge.py`) that connects the existing procurement workflows (Mode A: Inventory Shortages, Mode B: Altium BOM Assembly) to the universal procurement core **without modifying**:
- Mathematical formulas for BOM requirements (`total_needed_qty = unit_qty * board_multiplier`)
- Mathematical formulas for inventory shortages (`needed_qty = max(target - curr, min - curr, 1)`)
- `Inventory.xlsx` schema and column structure
- Any vendor adapter implementation (`vendors/lion/`, `vendors/javan/`, `vendors/roboeq/`)
- Discovery engine (`core/discovery/`)

---

## 2. Legacy Coupling Audit Matrix

A comprehensive static audit identified the following legacy coupling points across the repository:

| File | Lines | Legacy Hardcoded Pattern | Problem Description | Target Decoupled Design |
| :--- | :--- | :--- | :--- | :--- |
| `bom_auditor.py` | 47–49 | `"lionelectronic.ir" in self.link.lower()` | Hardcodes link classification strictly to Lion Electronic (`link_type = "LION"`). | Delegate to `VendorRegistry.get_vendor_for_url(link)` to recognize all registered vendors (`vendor_lion`, `vendor_javan`, `vendor_roboeq`). |
| `bom_auditor.py` | 117, 123 | `is_lion_orderable`, `get_orderable_shortages()` | Hardcodes filtering to Lion orderability. | Provide `is_orderable` and `vendor_id`, while maintaining `is_lion_orderable` as backward-compatible alias. |
| `excel_loader.py` | 401–402 | `"lionelectronic.ir" in link.lower()` | Shortage classification checks only Lion domain. | Delegate to `VendorRegistry.get_vendor_for_url(link)` to classify orderability across any registered storefront. |
| `excel_loader.py` | 424 | `"is_lion_orderable": link_type == "LION"` | Emits single-vendor flag in dictionary. | Emits `"is_orderable"`, `"vendor_id"`, and `"is_lion_orderable"` for compatibility. |
| `ui/dialogs/order_preview_dialog.py` | 10, 24 | `from lion_automator import LionAutomator` | Directly instantiates monolithic Lion script. | Route via `ProcurementBridge` / `UniversalProcurementOrchestrator` using `VendorRegistry`. |
| `ui/dialogs/order_preview_dialog.py` | 63, 69–70 | `self.lion_items`, `if "lionelectronic.ir" in link` | UI tracks only Lion items. | Track `self.orderable_items` grouped or tagged by vendor, keeping `self.lion_items` alias. |
| `ui/dialogs/order_preview_dialog.py` | 95, 254 | Hardcoded Lion labels and strings | UI copy assumes Lion is the sole provider. | Dynamic copy displaying registered vendor names and multi-vendor counts. |
| `ui/widgets/bom_audit_widget.py` | 438–449 | Tooltips referencing Lion only | UI tooltips prompt user strictly for Lion links. | Dynamic vendor-neutral tooltips reflecting the specific vendor or generic store link. |

---

## 3. Target Bridge Architecture (`core/procurement/bridge.py`)

The bridge layer sits between legacy spreadsheet parsing/UI threads and the universal procurement orchestrator:

```
┌─────────────────────────────────────────────────────────┐
│              Mode A: Inventory.xlsx                      │
│             Mode B: Altium BOM Import                   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│               core/procurement/bridge.py                │
│ ┌─────────────────────────────────────────────────────┐ │
│ │                  ProcurementBridge                  │ │
│ │ • item_to_request(item) -> ProcurementRequest       │ │
│ │ • is_item_orderable(item) -> (bool, vendor_id)      │ │
│ │ • classify_link(link) -> (link_type, domain, vendor)│ │
│ │ • execute_staged_procurement_batch(items, callback) │ │
│ └─────────────────────────────────────────────────────┘ │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│           core/procurement/orchestrator.py              │
│       UniversalProcurementOrchestrator                  │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│             core/procurement/registry.py                │
│       VendorRegistry -> IVendorAdapter Instances        │
│       (vendor_lion, vendor_javan, vendor_roboeq)        │
└─────────────────────────────────────────────────────────┘
```

### 3.1 Bridge Method Contracts

```python
class ProcurementBridge:
    @staticmethod
    def item_to_request(item: Dict[str, Any], registry: Optional[VendorRegistry] = None) -> ProcurementRequest:
        """Converts an inventory/BOM shortage dictionary into an immutable ProcurementRequest."""
        ...

    @staticmethod
    def is_item_orderable(item: Dict[str, Any], registry: Optional[VendorRegistry] = None) -> Tuple[bool, Optional[str]]:
        """Determines if an item has a URL matching any registered vendor."""
        ...

    @staticmethod
    def classify_link(link: str, registry: Optional[VendorRegistry] = None) -> Tuple[str, str, Optional[str]]:
        """Returns (link_type, link_domain, vendor_id)."""
        ...

    @staticmethod
    def execute_staged_procurement_batch(
        items: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str, int, str], None]] = None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None
    ) -> Dict[str, Any]:
        """Executes cart staging across all orderable items grouped by vendor."""
        ...
```

---

## 4. Preservation & Backward Compatibility Guarantees

1. **BOM Formula Invariance:**
   - `total_needed_qty = unit_qty * board_multiplier`
   - `shortage_qty = max(0, total_needed_qty - db_stock_qty)`
   *Untouched and verified.*

2. **Inventory Shortage Formula Invariance:**
   - `target = target_stock if target_stock > min_stock else min_stock`
   - `needed_qty = max(int(target - curr_stock), int(min_stock - curr_stock), 1)`
   *Untouched and verified.*

3. **Dictionary Keys Compatibility:**
   All shortage dictionaries emitted by `excel_loader.py` and `bom_auditor.py` will continue to contain:
   - `is_lion_orderable` (boolean)
   - `link_type` (`"LION"`, `"JAVAN"`, `"ROBOEQ"`, `"VENDOR"`, `"INVALID"`, `"NONE"`)
   - `link_domain` (string)
   - *Plus new fields:* `is_orderable` (boolean), `vendor_id` (`Optional[str]`).

4. **Inventory Stock Incrementing:**
   `ExcelDataLoader.batch_increment_stock()` remains 100% untouched.

---

## 5. Non-Goals & Boundaries

- Zero modifications to `core/discovery/`.
- Zero modifications to vendor adapters (`vendors/lion/`, `vendors/javan/`, `vendors/roboeq/`).
- Zero AI/LLM or heuristic ordering decisions.
- Zero autonomous checkout or payment processing.
- No live browser automation dependencies during automated unit tests.
