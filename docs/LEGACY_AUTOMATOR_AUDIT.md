# OMNIX Legacy Automator Audit: LionAutomator & JavanAutomator

## 1. Executive Summary & Architectural Scope

This audit traces and documents the legacy automator prototypes located at the project root:
- `lion_automator.py` (379 lines)
- `javan_automator.py` (368 lines)

These monolithic prototype classes represent early proof-of-concept scripts for browser-based automation on `lionelectronic.ir` and `javanelec.com`. They have been **architecturally superseded** by the production-grade, modular vendor plugin architecture located in:
- `vendors/lion/` (`LionVendorAdapter`, `LionSelectors`, `LionSessionManager`, `LionErrorTranslator`, `manifest.json`)
- `vendors/javan/` (`JavanVendorAdapter`, `JavanSelectors`, `JavanSessionManager`, `JavanErrorTranslator`, `manifest.json`)

Currently, neither `lion_automator.py` nor `javan_automator.py` is invoked by the application runtime (`ui/`, `core/inventory/`, `core/procurement/`, or `bom_auditor.py`). The only reference in the entire codebase is in `tests/test_lion_rules.py`, which imports `LionAutomator` solely to test a standalone quantity rounding function (`calculate_target_quantity`).

In compliance with the project's non-destructive preservation rules, these files remain in place but are formally classified as **Legacy Prototypes — Superseded by Modular Vendor Adapters**.

---

## 2. Historical Context & Evolution

### Early Phase: Monolithic Prototypes
In the initial development phases of OMNIX, `LionAutomator` and `JavanAutomator` served as rapid prototypes to demonstrate that Chrome WebDriver could authenticate, navigate storefronts, and manipulate shopping carts.

Key characteristics of this phase:
- Single-file monolithic classes combining browser initialization, DOM queries, authentication workflows, order calculations, and error handling.
- Synchronous and blocking operations.
- Direct global coupling to `settings_manager.settings`.
- Ad-hoc error reporting via tuples like `(bool, str)` or unstructured exceptions.

### Current Phase: Modular Vendor Plugin Architecture
To support multi-vendor procurement, Mode A deterministic link validation, hot plugin reload, and versioned coexistence, OMNIX introduced the vendor adapter standard (`IVendorAdapter`). The monolithic scripts were thoroughly refactored into domain-separated packages under `vendors/`:
- **Contract Fulfillment**: Strict compliance with `core/vendor_interface.py` (`IVendorAdapter`).
- **Separation of Concerns**: Separate modules for DOM queries (`selectors.py`), HTTP/browser sessions (`session.py`), error translation (`errors.py`), and plugin metadata (`manifest.json`).
- **Registry Integration**: Managed through `VendorRegistry` and `VersionedRegistry` with atomic URL routing.

---

## 3. Detailed Architectural Comparison

| Dimension | Legacy Prototypes (`lion_automator.py`, `javan_automator.py`) | Production Adapters (`vendors/lion/`, `vendors/javan/`) |
| :--- | :--- | :--- |
| **Interface Contract** | Ad-hoc class methods (`login_browser`, `order_products`, `get_cart_items`). No formal interface. | Formal implementation of `IVendorAdapter` protocol (`core.vendor_interface`). |
| **Architectural Role** | Standalone script running an unmanaged browser instance. | Modular plugin registered with `VendorRegistry` and orchestrated by `ProcurementOrchestrator`. |
| **Configuration** | Directly queries global mutable `settings_manager.settings`. | Configured via immutable, strongly typed `AdapterConfig` dataclass. |
| **DOM Selectors** | Hardcoded inline string literals across method bodies. Vulnerable to site updates. | Centralized selector registries (`LionSelectors`, `JavanSelectors`) with fallback chains and DOM drift detection (`DOMDriftError`). |
| **Session & Auth** | Inline Selenium `send_keys` and cookie inspection. | Dedicated `SessionManager` (`LionSessionManager`, `JavanSessionManager`) with cookie persistence, token extraction, and Challenge Handler integration. |
| **Error Handling** | Unstructured `(bool, "message")` tuples or raw Selenium exceptions. | Standardized `OmnixVendorError` hierarchy (`ProductNotFoundError`, `OutOfStockError`, `MOQViolationError`, `TransportNetworkError`, etc.). |
| **Lifecycle Hooks** | None. Browser driver instantiated and closed haphazardly. | Standardized lifecycle methods: `initialize()`, `shutdown()`, `health_check()`. |
| **Mode A Link Validation** | Unsupported. Cannot validate links without launching a browser. | Supported via lightweight URL parsing, vendor domain mapping, and headless validation. |
| **Packaging & Metadata** | Loose script files in project root without metadata. | Formal packages with declarative `manifest.json`, versioning, domain routes, and capability flags. |

---

## 4. Codebase Reference & Dependency Audit

A full scan of the active codebase was performed to trace all references to `lion_automator` and `javan_automator`:

### 1. Application Runtime (`core/`, `ui/`, `vendors/`)
- **Result**: **0 references**.
- Neither `MainWindow`, `BOMAuditor`, `ProcurementBridge`, nor any UI dialog imports or calls either legacy automator.

### 2. Test Suite (`tests/`)
- `tests/test_lion_rules.py`:
  - Contains: `from lion_automator import LionAutomator`
  - Usage: Tests `calculate_target_quantity(needed_qty, site_step)`.
  - Finding: The test does not actually instantiate `LionAutomator` or call any of its methods. It merely imports the file because the helper function was defined alongside the class.
- `tests/test_javan_adapter.py`:
  - Tests `JavanVendorAdapter` exclusively (34 passed tests).
- `tests/test_lion_adapter.py`:
  - Tests `LionVendorAdapter` exclusively (26 passed tests).
- `tests/test_roboeq_adapter.py`:
  - Tests `RoboEqVendorAdapter` exclusively (24 passed tests).

---

## 5. Decommissioning & Modernization Roadmap

To maintain clean code governance while respecting safety constraints:

1. **Preservation Gate**:
   - `lion_automator.py` and `javan_automator.py` remain preserved in the repository so that no existing files or Git history are disrupted.
2. **Recommended Action (Upon User Approval)**:
   - Move the 2 quantity calculation tests from `tests/test_lion_rules.py` into `tests/test_lion_adapter.py`.
   - Safely archive `lion_automator.py` and `javan_automator.py` into an `archive/` or `legacy/` directory, or remove them when officially retired from version control.
3. **Current Operating Standard**:
   - All current and future vendor automation, Mode A link verification, and Mode A order staging must exclusively target the modular adapters under `vendors/`.
