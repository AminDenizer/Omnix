# OMNIX Test Suite Audit

> **Mandatory Governance Gate**:
> In strict compliance with the architectural directives, **NO tests may be deleted without explicit user approval**.
> This audit provides a comprehensive classification of the 44 active test files and 859 individual test cases.

## Executive Summary

| Metric | Value |
| --- | --- |
| **Total Test Files** | 44 |
| **Total Test Cases** | 859 |
| **Passing Test Cases** | 859 (100%) |
| **Failed / Errored** | 0 (0%) |
| **Test Execution Duration** | ~115 seconds (full sequential suite) |
| **Workspace Path** | `D:\omnix\omnix` |

## Classification Taxonomy

- **KEEP (43 files)**: Critical regression guards covering SQLite storage, reference data, link validation, vendor adapters, BOM auditing, and UI workflows.
- **UPDATE (1 file)**: Test suites that test valid domain logic but should be aligned or consolidated (`test_lion_rules.py`).
- **MERGE (0 files pending approval)**: Potential merge candidates flagged for user review.
- **CANDIDATES FOR REMOVAL (0 files)**: None currently approved for removal. All tests are actively passing.

## Comprehensive File-by-File Audit

| # | Test File | Tests | Status | Classification | Domain Focus |
| - | --------- | ----- | ------ | -------------- | ------------ |
| 1 | `test_altium_contract_ingestion.py` | 4 | Passed | **KEEP** | Altium CSV/Excel BOM parsing contract and ingestion validation |
| 2 | `test_assembly_preparation.py` | 15 | Passed | **KEEP** | BOM assembly preparation, grouping, and line-item reconciliation |
| 3 | `test_bom_auditor.py` | 2 | Passed | **KEEP** | Core BOM auditor logic, stock reconciliation, and shortage detection |
| 4 | `test_bom_brand_selection.py` | 9 | Passed | **KEEP** | Brand preference selection and manufacturer filtering during BOM auditing |
| 5 | `test_cart_sync.py` | 24 | Passed | **KEEP** | Cart item synchronization and quantity validation across vendor sessions |
| 6 | `test_challenge_handler.py` | 11 | Passed | **KEEP** | Security challenges, CAPTCHA mitigation, and login retry loops |
| 7 | `test_component_management.py` | 39 | Passed | **KEEP** | Component Inventory CRUD, supplier links, and UI interactions |
| 8 | `test_database_inventory.py` | 35 | Passed | **KEEP** | Authoritative SQLite repository, DDL schemas, constraints, and transactions |
| 9 | `test_desktop_workflows.py` | 54 | Passed | **KEEP** | End-to-end desktop workflow and multi-window navigation flows |
| 10 | `test_dialog_and_edge_cases.py` | 3 | Passed | **KEEP** | Dialog modal edge cases, cancel behaviors, and input sanitation |
| 11 | `test_dual_path_mode_a.py` | 17 | Passed | **KEEP** | Mode A dual-path validation: SQLite store vs read-only Excel ingestion |
| 12 | `test_dual_procurement_modes.py` | 4 | Passed | **KEEP** | Architectural gating guaranteeing Mode A operations remain isolated from Mode B |
| 13 | `test_excel_loader.py` | 7 | Passed | **KEEP** | Read-only Excel workbook ingestion, column mapping, and schema extraction |
| 14 | `test_export_pipeline.py` | 15 | Passed | **KEEP** | Customer-facing 2-sheet Excel export pipeline with styles and formulas |
| 15 | `test_interactive_authentication.py` | 11 | Passed | **KEEP** | Interactive vendor credential prompt dialog and session handoff |
| 16 | `test_inventory_database_loader.py` | 10 | Passed | **KEEP** | Database path resolution priority and automatic schema bootstrap |
| 17 | `test_javan_adapter.py` | 34 | Passed | **KEEP** | Javan Electronic production adapter: search, details, cart, and error translation |
| 18 | `test_link_validator.py` | 7 | Passed | **KEEP** | Mode A deterministic supplier link validation service and status badges |
| 19 | `test_lion_adapter.py` | 26 | Passed | **KEEP** | Lion Electronic production adapter: search, details, cart, and error translation |
| 20 | `test_lion_rules.py` | 2 | Passed | **UPDATE** | Legacy smart quantity step rules; should be merged into test_lion_adapter.py |
| 21 | `test_multi_vendor_procurement.py` | 15 | Passed | **KEEP** | Multi-vendor procurement aggregation and multi-order staging |
| 22 | `test_multi_vendor_settings.py` | 11 | Passed | **KEEP** | Settings manager multi-vendor configuration, persistence, and defaults |
| 23 | `test_package_inspector.py` | 54 | Passed | **KEEP** | SMD package normalization, code mapping (e.g. 0603 -> 0603), and footprint rules |
| 24 | `test_phase10_task_a1_constraints.py` | 21 | Passed | **KEEP** | Phase 10 regression guards and constraint verification |
| 25 | `test_phase9_e2e_procurement.py` | 6 | Passed | **KEEP** | Phase 9 end-to-end simulated procurement pipeline |
| 26 | `test_plugin_contract.py` | 50 | Passed | **KEEP** | Strict verification of IVendorAdapter protocol implementation on all adapters |
| 27 | `test_plugin_lifecycle.py` | 14 | Passed | **KEEP** | Vendor plugin lifecycle: loading, initialization, health check, and teardown |
| 28 | `test_plugin_manifest_validator.py` | 79 | Passed | **KEEP** | Declarative plugin manifest.json schema validation and semantic checking |
| 29 | `test_procurement_bridge.py` | 10 | Passed | **KEEP** | Mode A bridge mapping BOM and shortage items into procurement staging |
| 30 | `test_procurement_models.py` | 19 | Passed | **KEEP** | Dataclasses and value objects for procurement, items, orders, and statuses |
| 31 | `test_procurement_orchestrator.py` | 8 | Passed | **KEEP** | Procurement orchestration across multiple vendor adapters |
| 32 | `test_provider_management.py` | 6 | Passed | **KEEP** | Vendor & Link Providers (ref_providers) CRUD, active toggles, and UI dialog |
| 33 | `test_reference_data_and_grouping.py` | 27 | Passed | **KEEP** | Reference data (ref_categories, ref_types, ref_manufacturers) and Group Key integrity |
| 34 | `test_roboeq_adapter.py` | 24 | Passed | **KEEP** | RoboEq production adapter: search, details, cart, and error translation |
| 35 | `test_settings_and_config.py` | 2 | Passed | **KEEP** | Application settings persistence, schema defaults, and config paths |
| 36 | `test_sqlite_ui_integration.py` | 9 | Passed | **KEEP** | Integration tests between SQLite repository and MainWindow UI views |
| 37 | `test_stock_policy_updater.py` | 15 | Passed | **KEEP** | Stock policy threshold editing, validation rules, and DB persistence |
| 38 | `test_supplier_availability_gate.py` | 37 | Passed | **KEEP** | Supplier availability verification and out-of-stock gating |
| 39 | `test_tab2_canonical_procurement.py` | 7 | Passed | **KEEP** | Tab 2 procurement view staging, selection, and dispatch |
| 40 | `test_ui_tab1_inventory_view.py` | 19 | Passed | **KEEP** | Tab 1 UI inventory tables, column distribution, search, and stock policy views |
| 41 | `test_universal_discovery.py` | 21 | Passed | **KEEP** | Universal site discovery, sitemap crawling, and product catalog indexing |
| 42 | `test_vendor_links.py` | 33 | Passed | **KEEP** | Vendor link syntax parsing (LION=...; JAVAN=...), tokenization, and fallback |
| 43 | `test_vendor_registry.py` | 17 | Passed | **KEEP** | Vendor registry discovery, registration, and URL-to-adapter resolution |
| 44 | `test_versioned_registry.py` | 26 | Passed | **KEEP** | Versioned vendor registry supporting concurrent plugin versions and hot switching |

## Detailed Test File Breakdown

### 1. `test_altium_contract_ingestion.py`
- **Classification**: `KEEP`
- **Domain**: Altium CSV/Excel BOM parsing contract and ingestion validation
- **Summary**: 4 passed in 1.31s
- **Module Docstring**: Comprehensive Unit Tests for GAP-16: Extended Altium Parameter Contract Ingestion Governing Document: DOC-OMNIX-ALTIUM-CONTRACT-001 (20-Parameter Canonical Contract)
- **Test Classes**:
  - `TestAltiumContractIngestion` (4 tests): Tests verifying 20-parameter ingestion, alias resolution, strict validation, and specs bundling.

### 2. `test_assembly_preparation.py`
- **Classification**: `KEEP`
- **Domain**: BOM assembly preparation, grouping, and line-item reconciliation
- **Summary**: 15 passed in 4.29s
- **Test Classes**:
  - `TestAssemblyProjectNameContract` (2 tests): Tests for Authoritative Project Name stem extraction.
  - `TestAssemblyNNumberingContract` (3 tests): Tests for N1...Nn row marker generation and isolation.
  - `TestAssemblyTableContract` (3 tests): Tests for exact 9-column assembly table structure and data preservation.
  - `TestAssemblyPrintEngine` (4 tests): Tests for A5 Landscape HTML generation, margins, and vector PDF export.
  - `TestAssemblyDialogsAndUX` (1 tests): Tests for AssemblyPreviewDialog and interactive actions.
  - `TestProcurementAndStateIsolation` (2 tests): Tests guaranteeing that Assembly workflow does not mutate BOM data or procurement state.

### 3. `test_bom_auditor.py`
- **Classification**: `KEEP`
- **Domain**: Core BOM auditor logic, stock reconciliation, and shortage detection
- **Summary**: 2 passed in 2.18s
- **Test Classes**:
  - `TestBOMAuditor` (2 tests): No class docstring

### 4. `test_bom_brand_selection.py`
- **Classification**: `KEEP`
- **Domain**: Brand preference selection and manufacturer filtering during BOM auditing
- **Summary**: 9 passed in 2.21s
- **Module Docstring**: Comprehensive Unit Tests for Manufacturer Rules and Brand Selection Engine Governing GAPs: GAP-06 (Manufacturer Constraint Engine) + GAP-16 (Altium Contract Ingestion)
- **Test Classes**:
  - `TestManufacturerRuleDataStateSeparation` (6 tests): Verifies strict separation between ManufacturerRule and ManufacturerDataState.
  - `TestCandidateEvaluationWithBrandRules` (3 tests): Tests evaluating vendor candidates against different brand rules.

### 5. `test_cart_sync.py`
- **Classification**: `KEEP`
- **Domain**: Cart item synchronization and quantity validation across vendor sessions
- **Summary**: 24 passed in 0.49s
- **Module Docstring**: Unit and Integration Tests for TASK-A4: Multi-Vendor Cart Idempotency & Delta Synchronization (GAP-13) Governing Document: docs/PRODUCT/MASTER_IMPLEMENTATION_ROADMAP.md (TASK-A4)
- **Test Classes**:
  - `MockCartVendorAdapter` (0 tests): Configurable mock adapter for cart idempotency testing.
  - `MockLionCartAdapter` (0 tests): No class docstring
  - `MockJavanCartAdapter` (0 tests): No class docstring
  - `MockRoboEqCartAdapter` (0 tests): No class docstring
  - `TestQuantityReconciliationA3` (8 tests): Verify exact compliance with canonical A3 MOQ and packaging-step rules.
  - `TestCartItemIdentityCascade` (7 tests): Verify strict 4-priority matching cascade and negative constraints.
  - `TestCartSynchronizationAndIdempotency` (5 tests): Verify deterministic delta staging, multi-line summation, and repeated execution convergence.
  - `TestMultiVendorIsolationAndErrorHandling` (3 tests): Verify vendor isolation, disabled vendor bypass, and max_orderable enforcement.
  - `TestBridgeBatchDeltaStaging` (1 tests): Verify ProcurementBridge batch execution with delta synchronization.
- **Standalone Test Functions** (1 tests)

### 6. `test_challenge_handler.py`
- **Classification**: `KEEP`
- **Domain**: Security challenges, CAPTCHA mitigation, and login retry loops
- **Summary**: 11 passed in 0.58s
- **Module Docstring**: Omnix Unit & Contract Tests for GAP-17: Universal Security Challenge / CAPTCHA Handler Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-17)
- **Test Classes**:
  - `TestChallengeModelEnumsAndContracts` (4 tests): Verifies all challenge types and state transitions (GAP-17).
  - `TestChallengeContextAndResult` (3 tests): Tests for ChallengeContext and ChallengeResult data structures.
  - `TestCallbackChallengeHandler` (4 tests): Tests for CallbackChallengeHandler resolution flows (GAP-17).

### 7. `test_component_management.py`
- **Classification**: `KEEP`
- **Domain**: Component Inventory CRUD, supplier links, and UI interactions
- **Summary**: 39 passed in 9.04s
- **Module Docstring**: Omnix Automated Tests for Phase 2.2: Component Management UI, CRUD & Supplier Links Governing Document: Phase 2.2 Specification  Verifies: 1. Component CRUD and SQLite persistence. 2. Duplicate normalized identity enforcement with Persian notice: «این قطعه از قبل ثبت شده است.» 3. Multi-vendor supplier link management and transactional integrity. 4. Stock grouping invariants (5-dimension key, leading zeros e.g. 0603/0805, aggregate recalculation). 5. Safe deletion preserving group policies and other components. 6. Reactive UI updates (tables, search filtering, stats ribbon, and selections).
- **Test Classes**:
  - `TestComponentCRUD` (5 tests): Verifies physical component creation, editing, deletion, and canceling.
  - `TestComponentIdentityAndDuplicates` (6 tests): Verifies duplicate detection, Persian notice, and identity collision protection.
  - `TestSupplierLinksManagement` (3 tests): Verifies adding, editing, removing, and transactional safety of supplier links.
  - `TestStockGroupingInvariantsAndUI` (7 tests): Verifies 5-field grouping key invariants and UI reactivity.
  - `TestEmptyGroupPolicyCleanupInvariant` (4 tests): Verifies that empty groups and their stock policies are cleaned up atomically upon last component deletion.
  - `TestThreeDistinctInventoryViews` (2 tests): Verifies the three distinct inventory views, placement of CRUD buttons, and synchronization.
  - `TestComponentInventoryViewAndColumns` (5 tests): Verifies Component Inventory column layout, order, empty state, and tab-switching persistence.
  - `TestComponentEditDialogLifecycleAndReferenceData` (7 tests): Verifies dialog reset, zero state leakage, category-dependent types, and explicit reference additions.

### 8. `test_database_inventory.py`
- **Classification**: `KEEP`
- **Domain**: Authoritative SQLite repository, DDL schemas, constraints, and transactions
- **Summary**: 35 passed in 2.36s
- **Module Docstring**: Unit & Integration Tests for Omnix SQLite Database Foundation & Inventory Repository Governing Document: Phase 1 Master Architecture Specification & Stage 1 Implementation
- **Test Classes**:
  - `TestDatabaseLifecycle` (7 tests): No class docstring
  - `TestComponentIdentity` (4 tests): No class docstring
  - `TestComponentCRUD` (5 tests): No class docstring
  - `TestSupplierLinks` (3 tests): No class docstring
  - `TestReferenceData` (10 tests): No class docstring
  - `TestStockAggregationAndPolicies` (6 tests): No class docstring

### 9. `test_desktop_workflows.py`
- **Classification**: `KEEP`
- **Domain**: End-to-end desktop workflow and multi-window navigation flows
- **Summary**: 54 passed in 3.43s
- **Module Docstring**: Omnix Automated Test Suite — Desktop UI Workflows & Multi-Candidate Preview Governing GAPs: - GAP-07: Multi-Candidate Comparison & Alternative Selection (OrderPreviewDialog) - GAP-02: Direct MPN Quick Order Workflow (QuickOrderDialog - Tab 1) - GAP-03: Direct Product URL Quick Order Workflow (QuickOrderDialog - Tab 2)
- **Test Classes**:
  - `TestGAP07MultiCandidateComparison` (22 tests): Test suite for GAP-07 in OrderPreviewDialog.
  - `TestGAP02DirectMPNQuickOrder` (12 tests): Test suite for Direct MPN Quick Order in QuickOrderDialog.
  - `TestGAP03DirectURLQuickOrder` (20 tests): Test suite for Direct Product URL Quick Order in QuickOrderDialog.

### 10. `test_dialog_and_edge_cases.py`
- **Classification**: `KEEP`
- **Domain**: Dialog modal edge cases, cancel behaviors, and input sanitation
- **Summary**: 3 passed in 3.08s
- **Test Classes**:
  - `TestDialogAndEdgeCases` (3 tests): No class docstring

### 11. `test_dual_path_mode_a.py`
- **Classification**: `KEEP`
- **Domain**: Mode A dual-path validation: SQLite store vs read-only Excel ingestion
- **Summary**: 17 passed in 2.64s
- **Module Docstring**: Tests for Dual-Path Mode A Validation: Stock Shortages + Altium BOM.  Governing Requirements: - Section 3: Path A — Stock Shortages Integration - Section 4: Path B — Altium BOM Procurement Integration (based on FC_IO_V_1_3(2) / FC_IO_V_1_2 structure) - Section 5: Preserved Multi-Vendor Contracts Across Both Paths - Section 6: Separately Identifiable Entry-Point Integration Tests
- **Test Classes**:
  - `MockLionAdapter` (0 tests): No class docstring
  - `MockJavanAdapter` (0 tests): No class docstring
  - `TestPathAStockShortagesIntegration` (6 tests): Validates Entry Point A: Stock Shortages / Replenishment. Verifies that shortage items loaded from Inventory.xlsx flow correctly through multi-vendor link resolution, OrderPreviewDialog, user selection, and atomic adapter dispatch.
  - `TestPathBBOMProcurementIntegration` (8 tests): Validates Entry Point B: Altium BOM Procurement. Mirrors FC_IO_V_1_3(2).xlsx / FC_IO_V_1_2.xlsx canonical parameters and verifies BOM import, reconciliation with Inventory datastore, multi-vendor link parsing, OrderPreviewDialog integration, user selection, and atomic adapter dispatch.
  - `TestSharedModeAContracts` (3 tests): Validates shared Mode A contracts and invariants across both entry points.

### 12. `test_dual_procurement_modes.py`
- **Classification**: `KEEP`
- **Domain**: Architectural gating guaranteeing Mode A operations remain isolated from Mode B
- **Summary**: 4 passed in 2.10s
- **Module Docstring**: Comprehensive Unit & Integration Tests for GAP-01: Dual Procurement Modes - Mode A: Database-Aware Stock Reconciliation (Inventory.xlsx dependent) - Mode B: Direct BOM Sourcing (100% Inventory-Independent turnkey procurement)
- **Test Classes**:
  - `TestDualProcurementModes` (4 tests): Tests evaluating Mode A and Mode B isolation, calculation, and bridge translation.

### 13. `test_excel_loader.py`
- **Classification**: `KEEP`
- **Domain**: Read-only Excel workbook ingestion, column mapping, and schema extraction
- **Summary**: 7 passed in 2.08s
- **Test Classes**:
  - `TestExcelDataLoader` (7 tests): No class docstring

### 14. `test_export_pipeline.py`
- **Classification**: `KEEP`
- **Domain**: Customer-facing 2-sheet Excel export pipeline with styles and formulas
- **Summary**: 15 passed in 2.94s
- **Module Docstring**: Omnix Automated Test Suite — Multi-Vendor Deterministic Export Pipeline (GAP-18) Exhaustive verification of CSV, XLSX, and PDF exports, deterministic ordering, data contracts, audit trails, and side-effect-free execution.
- **Test Classes**:
  - `TestProcurementReportBuilder` (7 tests): Test suite for ProcurementReportBuilder determinism, data contracts, and mapping.
  - `TestProcurementCSVExporter` (3 tests): Test suite for RFC 4180 CSV export determinism, UTF-8 BOM, and structure.
  - `TestProcurementXLSXExporter` (1 tests): Test suite for openpyxl Excel multi-sheet export, styling, and formulas.
  - `TestProcurementPDFExporter` (3 tests): Test suite for HTML generation and vector PDF export via QTextDocument.
  - `TestOrderPreviewDialogExportUI` (1 tests): Test suite verifying OrderPreviewDialog export actions and integration.

### 15. `test_interactive_authentication.py`
- **Classification**: `KEEP`
- **Domain**: Interactive vendor credential prompt dialog and session handoff
- **Summary**: 11 passed in 19.83s
- **Module Docstring**: Omnix Unit & Contract Tests for GAP-09: Interactive Authentication & Headful Fallback Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-09, GAP-17)
- **Test Classes**:
  - `TestSessionPromotionContracts` (3 tests): Tests session promotion between headless and headful modes (GAP-09).
  - `TestInteractiveAuthenticationFlow` (8 tests): Tests interactive authentication workflows across adapters (GAP-09, GAP-17).

### 16. `test_inventory_database_loader.py`
- **Classification**: `KEEP`
- **Domain**: Database path resolution priority and automatic schema bootstrap
- **Summary**: 10 passed, 1 warning in 1.27s
- **Module Docstring**: Unit & Contract Tests for Omnix Inventory Database Loader & Repository Governing Document: Phase 1 Master Architecture Specification
- **Test Classes**:
  - `TestPackageNormalizationAndKey` (3 tests): Test package normalization and canonical group key generation.
  - `TestInventoryDatabaseLoader` (5 tests): Test strictly read-only loading and verification of workbook data.
  - `TestExcelInventoryRepository` (1 tests): Test repository abstraction over Excel workbook.
  - `TestRealInventoryWorkbookIntegration` (1 tests): Integration test with the actual repository workbook autom/atom/Inventory.xlsm.

### 17. `test_javan_adapter.py`
- **Classification**: `KEEP`
- **Domain**: Javan Electronic production adapter: search, details, cart, and error translation
- **Summary**: 34 passed in 1.03s
- **Module Docstring**: Deterministic Unit Tests for Javan Electronic Vendor Adapter (JavanVendorAdapter) Tests all 13 IVendorAdapter contract operations, selector regexes, error translations, mock HTML extractions, and ordering validations without hitting live network.
- **Test Classes**:
  - `TestJavanAdapterContract` (5 tests): No class docstring
  - `TestJavanSelectorsAndPatterns` (3 tests): No class docstring
  - `TestJavanErrorTranslation` (11 tests): No class docstring
  - `TestJavanProductResolution` (5 tests): No class docstring
  - `TestJavanProductDataExtraction` (3 tests): No class docstring
  - `TestJavanCartAndOrderingValidations` (1 tests): No class docstring
  - `TestJavanLM358Extraction` (1 tests): No class docstring
  - `TestJavanSessionAndRecovery` (5 tests): No class docstring

### 18. `test_link_validator.py`
- **Classification**: `KEEP`
- **Domain**: Mode A deterministic supplier link validation service and status badges
- **Summary**: 7 passed in 1.39s
- **Module Docstring**: Omnix Automated Tests for Mode A Deterministic Link Validation Service Governing Document: Phase G & H Link Validation Specification
- **Test Classes**:
  - `DummyAdapter` (0 tests): No class docstring
  - `TestLinkValidatorDeterministicRules` (7 tests): Verifies deterministic matching and classification rules of LinkValidator.

### 19. `test_lion_adapter.py`
- **Classification**: `KEEP`
- **Domain**: Lion Electronic production adapter: search, details, cart, and error translation
- **Summary**: 26 passed in 1.46s
- **Module Docstring**: Deterministic Unit and Contract Tests for Lion Vendor Adapter Governing Documents: - docs/VENDORS/LION/ADAPTER_SPECIFICATION.md - docs/VENDORS/LION/PHASE6_5_IMPLEMENTATION_READINESS.md
- **Test Classes**:
  - `TestLionAdapterContract` (5 tests): Verify that LionVendorAdapter implements IVendorAdapter and exports expected attributes.
  - `TestLionSelectorsAndPatterns` (3 tests): Verify regex patterns and key selectors matching SITE_MAP_GRAPH.json.
  - `TestLionErrorTranslation` (11 tests): Verify translation of 13 normalized error categories.
  - `TestProductResolution` (4 tests): Verify resolution of URLs and SKUs to normalized ProductReference.
  - `TestProductDataExtraction` (2 tests): Verify technical table parsing and raw packaging step extraction.
  - `TestCartAndOrderingValidations` (1 tests): Verify validation boundaries in add_to_cart.

### 20. `test_lion_rules.py`
- **Classification**: `UPDATE`
- **Domain**: Legacy smart quantity step rules; should be merged into test_lion_adapter.py
- **Summary**: 2 passed in 0.70s
- **Test Classes**:
  - `TestLionAutomatorRules` (2 tests): No class docstring

### 21. `test_multi_vendor_procurement.py`
- **Classification**: `KEEP`
- **Domain**: Multi-vendor procurement aggregation and multi-order staging
- **Summary**: 15 passed in 0.49s
- **Module Docstring**: Deterministic Multi-Vendor Integration Test Suite for Omnix Procurement Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Strictly offline: Zero Selenium, Zero live websites, Zero network dependencies.
- **Test Classes**:
  - `BaseFakeVendorAdapter` (0 tests): Base fake adapter for deterministic integration tests with operation instrumentation.
  - `FakeLionAdapter` (0 tests): No class docstring
  - `FakeJavanAdapter` (0 tests): No class docstring
  - `FakeRoboEqAdapter` (0 tests): No class docstring
  - `FakeFailingAdapter` (0 tests): No class docstring
  - `TestMultiVendorIntegrationSuite` (15 tests): 15-Point Multi-Vendor Orchestration Integration Test Suite.

### 22. `test_multi_vendor_settings.py`
- **Classification**: `KEEP`
- **Domain**: Settings manager multi-vendor configuration, persistence, and defaults
- **Summary**: 11 passed in 0.49s
- **Module Docstring**: Omnix Unit & Contract Tests for GAP-11: Multi-Vendor Settings & Dynamic Enable/Disable Governing Document: docs/PRODUCT/CANONICAL_GAP_REGISTRY.md (GAP-11)
- **Test Classes**:
  - `DummyTestAdapter` (0 tests): No class docstring
  - `TestMultiVendorSettingsModel` (4 tests): Tests for VendorSettings model invariants and credential security (GAP-11).
  - `TestMultiVendorSettingsManager` (4 tests): Tests for SettingsManager multi-vendor persistence and isolation (GAP-11).
  - `TestVendorRegistryAndOrchestratorFiltering` (3 tests): Tests for dynamic vendor filtering in VendorRegistry and Orchestrator (GAP-11).

### 23. `test_package_inspector.py`
- **Classification**: `KEEP`
- **Domain**: SMD package normalization, code mapping (e.g. 0603 -> 0603), and footprint rules
- **Summary**: 54 passed, 1 warning in 1.13s
- **Module Docstring**: Omnix Vendor Plugin System — Comprehensive Phase 4 Package Inspection Tests Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md  Validates that PackageInspector: 1. Correctly verifies valid packages (single-vendor, multi-module, assets, declarative config). 2. Computes archive SHA-256, validates manifest schema and semantic rules. 3. Enforces strict archive safety limits (10 MiB zip, 50 MiB total, 20 MiB entry, 10:1 ratio, 500 entries, extension whitelist). 4. Detects zip-slip, traversal, case collisions, duplicate members, symlinks/devices. 5. Verifies META-INF/MANIFEST.MF digests, detects unlisted files, missing files, tampered contents, uncanonical ordering. 6. Verifies static entry-point presence without importing or executing. 7. Strictly guarantees zero execution, zero import, zero disk extraction, zero registry mutation.
- **Test Classes**:
  - `TestPackageInspectorValidPackages` (5 tests): Tests confirming that well-formed, compliant .xpl packages inspect successfully.
  - `TestPackageInspectorIdentityAndManifest` (12 tests): Tests verifying manifest integrity, presence, and single-vendor identity rules.
  - `TestPackageInspectorArchiveSafetyAndLimits` (16 tests): Tests verifying limits, corruption handling, traversal, collisions, and bombs.
  - `TestPackageInspectorManifestMFIntegrity` (7 tests): Tests verifying per-file digests and integrity manifest rules.
  - `TestPackageInspectorEntryPointVerification` (2 tests): Tests confirming static verification of entry-point presence without importing.
  - `TestPackageInspectorNonExecutionGuarantees` (4 tests): Critical security tests verifying that package inspection: 1. NEVER executes Python code from the archive. 2. NEVER imports any module into sys.modules. 3. NEVER extracts files to disk. 4. NEVER mutates VendorRegistry.
  - `TestPackageInspectorReconciliationBoundariesAndWhitelist` (8 tests): Focused reconciliation tests for Phase 4 archive limits, binary vs decimal units, strict boundary checks (immediately below, at, and above thresholds), authoritative MANIFEST.MF format verification, and strict extension whitelist.

### 24. `test_phase10_task_a1_constraints.py`
- **Classification**: `KEEP`
- **Domain**: Phase 10 regression guards and constraint verification
- **Summary**: 21 passed in 0.46s
- **Module Docstring**: Omnix Deterministic Unit & Contract Tests for TASK-A1: Core Technical Matching, Package/Footprint Constraints & Brand Rules Governing Document: docs/PRODUCT/MASTER_PRODUCT_COMPLETION_GAP_ANALYSIS.md (GAPs: GAP-04, GAP-05, GAP-06)
- **Test Classes**:
  - `TestTaskA1PackageConstraints` (5 tests): GAP-04: Package constraint verification with conservative normalization.
  - `TestTaskA1FootprintConstraints` (4 tests): GAP-04: Footprint constraint verification evaluated independently.
  - `TestTaskA1ManufacturerBrandConstraints` (6 tests): GAP-06: Brand / Manufacturer rules (ANY vs Explicit Approved Set).
  - `TestTaskA1TechnicalSpecsAndDimensions` (4 tests): GAP-05: Generic technical parameters and physical dimensions verification.
  - `TestTaskA1MultipleFailuresAndCriticalScenario` (2 tests): Preservation of multiple simultaneous failures and Section 14 regression scenario.

### 25. `test_phase9_e2e_procurement.py`
- **Classification**: `KEEP`
- **Domain**: Phase 9 end-to-end simulated procurement pipeline
- **Summary**: 6 passed in 1.40s
- **Module Docstring**: End-to-End Multi-Vendor Procurement Integration Test Suite Phase 9 — Step 8 Gate Certification Governing Documents: - docs/MASTER_PROJECT_SPECIFICATION.md - docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md - docs/PROCUREMENT/PHASE9_STEP8_SCOPE_AUDIT.md  Strictly offline: Zero Selenium, Zero live websites, Zero network dependencies. Validates Mode A (Inventory Shortages) and Mode B (Altium BOM Assembly) lifecycles, error handling, MOQ stepping, partial failure tolerance, and post-order inventory updates.
- **Test Classes**:
  - `BaseE2EFakeAdapter` (0 tests): Base fake adapter for E2E tests implementing all 13 contract methods.
  - `FakeLionE2EAdapter` (0 tests): No class docstring
  - `FakeJavanE2EAdapter` (0 tests): No class docstring
  - `FakeRoboEqE2EAdapter` (0 tests): No class docstring
  - `TestModeAInventoryShortagesEndToEnd` (1 tests): Validates Mode A: Inventory.xlsx -> Shortage Extraction -> Orchestrator -> Cart Staging -> Stock Update.
  - `TestModeBAltiumBOMAssemblyEndToEnd` (1 tests): Validates Mode B: Altium BOM -> Multiplier Calculation -> Audit -> Multi-Vendor Staging -> Stock Update.
  - `TestMultiVendorProcurementEdgeCases` (4 tests): Validates edge cases: 100% stock, OOS items, network failure resilience, direct URL routing.

### 26. `test_plugin_contract.py`
- **Classification**: `KEEP`
- **Domain**: Strict verification of IVendorAdapter protocol implementation on all adapters
- **Summary**: 50 passed in 1.19s
- **Module Docstring**: Unit & Contract Tests for Omnix Vendor Plugin Contract (Phase 2) Governing Document: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Sections 6 & 7  Validates: 1. Canonical models: PluginCapability (16 items), CapabilityStatus (5 items),    CapabilityBlockingReason (7 items), PluginProcurementMode (2 items). 2. CapabilityEvaluationRecord validation, timestamping, blocking consistency,    and secret leakage protection in diagnostic details. 3. IVendorAdapter base contracts: 13 abstract methods, fail-closed defaults,    empty default capabilities and modes, deterministic queries. 4. Centralized CAPABILITY_METHOD_MAP covering all 16 capabilities,    verifying real adapter methods and explicit empty Layer C live test boundaries. 5. Declared capability and procurement mode consistency validation. 6. Built-in production adapters (Lion, Javan, RoboEq) compliance and evidence-backed    declarations (Layer A/B only, zero Layer C).
- **Test Classes**:
  - `TestCanonicalEnums` (5 tests): Verify exact membership and string compatibility of all Phase 2 enums.
  - `TestCapabilityEvaluationRecord` (9 tests): Verify evaluation record validation, timestamping, and diagnostic sanitization.
  - `MinimalConcreteAdapter` (0 tests): Minimal subclass to test default base behaviors without mocking.
  - `TestIVendorAdapterContract` (9 tests): Verify base IVendorAdapter abstract specifications and fail-closed behaviors.
  - `TestCapabilityMethodMap` (4 tests): Verify the completeness and accuracy of the centralized capability-to-method map.
  - `TestProcurementModeCapabilityConsistency` (5 tests): Verify consistency rules between declared capabilities and supported procurement modes.
  - `TestBuiltInAdaptersCompliance` (5 tests): Verify Lion, Javan, and RoboEq declared capabilities and modes against codebase evidence.

### 27. `test_plugin_lifecycle.py`
- **Classification**: `KEEP`
- **Domain**: Vendor plugin lifecycle: loading, initialization, health check, and teardown
- **Summary**: 14 passed in 2.87s
- **Module Docstring**: Unit and integration tests for Omnix Phase 2.5: Empty-by-Default Plugin Lifecycle. Governing Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Governing Architectural Decision: OD-010 (Default-Empty Plugin Distribution & Dynamic Lifecycle)  Verifies: 1. An ordinary new registry is empty. 2. The default registry is empty on first access. 3. Repeated default-registry access does not register vendors. 4. Importing an adapter does not register it automatically as a side-effect. 5. Explicit valid registration via manifest works and populates routes. 6. Invalid manifest registration fails without partial mutation. 7. Duplicate registration and domain collisions are rejected atomically. 8. Unregistering a vendor purges its route mappings consistently. 9. Inventory loading handles known storefront URLs with an empty registry (fail-closed). 10. BOM auditing handles missing plugins without crashing. 11. Procurement with no enabled/registered vendors returns a clear, non-crashing result. 12. The Settings dialog works with zero registered vendors and renders clear empty state. 13. Dynamically registered vendors receive appropriate configuration tabs in Settings UI. 14. Full procurement, quantity calculation, and staging operate correctly when vendors are explicitly registered.
- **Test Classes**:
  - `DummyLifecycleAdapter` (0 tests): Minimal compliant vendor adapter for lifecycle unit testing.
  - `TestEmptyByDefaultInitialization` (4 tests): Verify registry starts empty and vendor adapter imports cause zero side-effects.
  - `TestExplicitManifestRegistrationLifecycle` (4 tests): Verify explicit manifest validation, atomic failure, and unregistration.
  - `TestFailClosedProcurementBehavior` (3 tests): Verify inventory, BOM, and procurement fail closed without crashing when zero plugins exist.
  - `TestSettingsUIDynamicLifecycle` (2 tests): Verify Settings dialog behaves gracefully with zero plugins and dynamically renders active ones.
  - `TestExplicitRegistrationProcurementEndToEnd` (1 tests): Verify complete procurement execution when a plugin is explicitly registered.

### 28. `test_plugin_manifest_validator.py`
- **Classification**: `KEEP`
- **Domain**: Declarative plugin manifest.json schema validation and semantic checking
- **Summary**: 79 passed in 0.68s
- **Module Docstring**: Comprehensive Test Suite for Omnix Plugin Manifest Validator & JSON Schema Governing Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 5  Tests: 1. Valid Manifests (Minimal, Full, Mode A-only, Mode B-only, All Capabilities) 2. Strict JSON Parsing (Duplicate keys, NaN, Infinity, Oversized, Malformed) 3. JSON Schema Validation (Draft 2020-12 compliance, Type checks, Extra properties) 4. Domain Semantic Rules (SemVer 2.0.0, Entry-point path safety, Identifier conventions) 5. Security Boundaries (Zero module imports, Zero code execution, Zero network egress)
- **Test Classes**:
  - `TestValidManifests` (9 tests): Verifies valid manifests across all permitted configurations.
  - `TestStrictJSONParsing` (11 tests): Verifies that parsing rejects malformed, duplicate-key, or non-standard JSON.
  - `TestSchemaValidation` (7 tests): Verifies that schema structural violations are caught deterministically.
  - `TestSemanticValidation` (8 tests): Verifies domain rules that extend beyond basic JSON schema typing.
  - `TestSecurityBoundaries` (5 tests): Verifies that the validator never imports, executes, connects, or extracts.
  - `TestSemanticVersionComparator` (4 tests): Verifies that our self-contained SemVer class adheres to SemVer 2.0.0 spec.

### 29. `test_procurement_bridge.py`
- **Classification**: `KEEP`
- **Domain**: Mode A bridge mapping BOM and shortage items into procurement staging
- **Summary**: 10 passed in 1.25s
- **Module Docstring**: Unit tests for Universal Procurement Bridge layer.  Verifies deterministic translation, URL classification, orderability detection, and staged batch execution across multiple vendors without live browser dependencies.
- **Test Classes**:
  - `MockTestAdapter` (0 tests): Mock adapter for deterministic bridge execution testing.
  - `TestProcurementBridgeClassification` (6 tests): Tests URL classification and vendor resolution via ProcurementBridge.
  - `TestProcurementBridgeRequestTranslation` (2 tests): Tests translation of legacy shortage dicts into immutable ProcurementRequests.
  - `TestProcurementBridgeBatchExecution` (2 tests): Tests batch execution logic with progress feedback and error containment.

### 30. `test_procurement_models.py`
- **Classification**: `KEEP`
- **Domain**: Dataclasses and value objects for procurement, items, orders, and statuses
- **Summary**: 19 passed in 0.48s
- **Module Docstring**: Deterministic Unit Tests for Procurement Models and Helper Functions Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
- **Test Classes**:
  - `TestPriceTierAndValidation` (3 tests): Verify PriceTier initialization, invariants, and validation.
  - `TestProcurementRequestValidation` (3 tests): Verify ProcurementRequest validation and defaulting.
  - `TestEffectiveQuantityCalculations` (6 tests): Verify deterministic quantity stepping, MOQ, and max limit enforcement.
  - `TestPriceTierEvaluation` (3 tests): Verify tier selection, boundary checking, and fallback pricing.
  - `TestTaskA1ModelExtensions` (4 tests): Verify Task A1 model fields, EvaluationState enum, and string normalization.

### 31. `test_procurement_orchestrator.py`
- **Classification**: `KEEP`
- **Domain**: Procurement orchestration across multiple vendor adapters
- **Summary**: 8 passed in 0.43s
- **Module Docstring**: Deterministic Unit Tests for UniversalProcurementOrchestrator Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
- **Test Classes**:
  - `MockLionAdapter` (0 tests): No class docstring
  - `MockJavanAdapter` (0 tests): No class docstring
  - `TestUniversalProcurementOrchestratorRouting` (4 tests): Verify deterministic vendor routing according to explicit IDs, URLs, or all vendors.
  - `TestUniversalProcurementOrchestratorEvaluationAndSelection` (3 tests): Verify deterministic candidate evaluation and price/MPN precedence.
  - `TestUniversalProcurementOrchestratorCartStaging` (1 tests): Verify non-destructive cart staging through adapter contract.

### 32. `test_provider_management.py`
- **Classification**: `KEEP`
- **Domain**: Vendor & Link Providers (ref_providers) CRUD, active toggles, and UI dialog
- **Summary**: 6 passed in 3.18s
- **Module Docstring**: Omnix Automated Tests for Vendor & Link Providers Reference Data Governing Document: Phase F Specification
- **Test Classes**:
  - `TestProviderReferenceDataCRUD` (6 tests): Verifies ref_providers table and repository CRUD.

### 33. `test_reference_data_and_grouping.py`
- **Classification**: `KEEP`
- **Domain**: Reference data (ref_categories, ref_types, ref_manufacturers) and Group Key integrity
- **Summary**: 27 passed in 8.00s
- **Module Docstring**: Unit & Integration Tests for: 1. Reference Data sheet importing from Excel into SQLite. 2. Thyristor and newly imported categories/types component registration. 3. Database-backed canonical classification & 5-dimension grouping key normalization. 4. Package leading zeroes preservation (0603, 0805). 5. Dedicated Reference Data management dialog and uncluttered registration form. 6. Three distinct inventory views preservation.
- **Test Classes**:
  - `TestReferenceDataImportAndBootstrap` (4 tests): Verifies that the Reference Data sheet is parsed and seeded into SQLite.
  - `TestCanonicalClassificationAndGrouping` (3 tests): Verifies that classification differences unify to canonical keys and preserve leading zeros.
  - `TestUIStreamliningAndReferenceDataDialog` (3 tests): Verifies that the registration form is uncluttered and the reference data manager dialog functions.
  - `TestTransistorRegistrationAndGrouping` (2 tests): Verifies that Transistor category and types are available and an actual transistor component workflow succeeds.
  - `TestReferenceDataCRUDAndIntegrity` (1 tests): Verifies that Reference Data CRUD operations enforce referential integrity and prevent data corruption.
  - `TestExcelExporterTwoSheetContract` (1 tests): Verifies customer-facing Excel export with exactly two worksheets: ['Inventory', 'Assembly View'].
  - `TestAssemblyViewUIImprovements` (2 tests): Verifies Incomplete control visibility and Quantity in Stock column layout.
  - `TestTitleBarKeyboardRoutingAndFormUX` (11 tests): Targeted verification for native title bar, keyboard routing, form UX, steppers, and Excel presentation.

### 34. `test_roboeq_adapter.py`
- **Classification**: `KEEP`
- **Domain**: RoboEq production adapter: search, details, cart, and error translation
- **Summary**: 24 passed in 1.27s
- **Module Docstring**: Deterministic Unit Tests for RoboEq Electronic Vendor Adapter (RoboEqVendorAdapter) Tests all 13 IVendorAdapter contract operations, selector regexes, error translations, mock HTML extractions, and ordering validations without hitting live network.
- **Test Classes**:
  - `TestRoboEqAdapterContract` (5 tests): No class docstring
  - `TestRoboEqSelectorsAndPatterns` (3 tests): No class docstring
  - `TestRoboEqErrorTranslation` (8 tests): No class docstring
  - `TestRoboEqProductResolution` (3 tests): No class docstring
  - `TestRoboEqDataExtraction` (2 tests): No class docstring
  - `TestRoboEqCartAndLifecycle` (3 tests): No class docstring

### 35. `test_settings_and_config.py`
- **Classification**: `KEEP`
- **Domain**: Application settings persistence, schema defaults, and config paths
- **Summary**: 2 passed in 0.27s
- **Test Classes**:
  - `TestSettingsAndConfig` (2 tests): No class docstring

### 36. `test_sqlite_ui_integration.py`
- **Classification**: `KEEP`
- **Domain**: Integration tests between SQLite repository and MainWindow UI views
- **Summary**: 9 passed in 3.66s
- **Module Docstring**: Omnix Automated Tests for Phase 2.1: SQLite Repository Integration & UI Preservation Governing Document: Phase 2.1 Implementation Specification  Tests: 1. MainWindow initializes with SqliteInventoryRepository as authoritative repository. 2. Tab 1 two-table layout, vertical splitter, search bar, and statistics ribbon function with SQLite. 3. Policy editing persists to SQLite and reactively updates group aggregates and products table. 4. Safe Excel bootstrap imports reference data, components, supplier links, and policies    without modifying the source workbook. 5. In-memory and temporary database isolation protects user data.
- **Test Classes**:
  - `TestPhase21SqliteUIIntegration` (5 tests): Tests for Phase 2.1: SQLite desktop integration and UI preservation.
  - `TestSafeBootstrapMigration` (4 tests): Tests verifying non-destructive Excel to SQLite migration invariants.

### 37. `test_stock_policy_updater.py`
- **Classification**: `KEEP`
- **Domain**: Stock policy threshold editing, validation rules, and DB persistence
- **Summary**: 15 passed, 2 warnings in 25.39s
- **Module Docstring**: Omnix Tests - Stock Policy Updater & Threshold Editing Dialog Governing Document: Phase 1 Refinement Specification  Verifies: - Editing and saving Min Stock and Target Stock to a temporary copy of Inventory.xlsm - Exact row identification by canonical Group Key - Formula preservation across all formula-generated columns - Validation rules (Target Stock >= Min Stock >= 0) - PolicyEditDialog interaction, inline validation, and cancel behavior - Error handling for locked/read-only files - Byte immutability of the real user's original workbook
- **Test Classes**:
  - `TestStockPolicyWriter` (8 tests): Test suite for StockPolicyWriter Excel COM persistence.
  - `TestPolicyEditDialog` (7 tests): Test suite for PolicyEditDialog UI.

### 38. `test_supplier_availability_gate.py`
- **Classification**: `KEEP`
- **Domain**: Supplier availability verification and out-of-stock gating
- **Summary**: 37 passed in 1.61s
- **Module Docstring**: Tests for Fail-Closed Supplier Availability Gates (Lion Electronic + Javan Electronic).  Validates: 1. Lion product-status gate:    - Explicitly available -> ALLOW    - به‌زودی (ZWNJ, spaced, compact) -> BLOCK    - اتمام موجودی -> BLOCK    - Status cannot be reliably identified -> BLOCK    - Inquiry-only / productCanOrder=false -> BLOCK 2. Javan product-status gate:    - Explicitly open/available (موجود در انبار) -> ALLOW    - تأمین -> BLOCK    - اتمام -> BLOCK    - ناموجود-سفارش دهید (even with lead time / delivery estimate) -> BLOCK    - Visible order button / lead time does not override prohibited status -> BLOCK    - Status cannot be reliably identified -> BLOCK 3. Dual-Path Integration:    - Path A (Stock Shortages) with eligible vs blocked links    - Path B (Altium BOM) with eligible vs blocked links    - Multi-vendor selection of blocked supplier fails closed without silent fallback    - Transport / network error fails closed before add_to_cart
- **Test Classes**:
  - `TestLionAvailabilityGate` (7 tests): Verifies fail-closed product-status rules for Lion Electronic.
  - `TestJavanAvailabilityGate` (8 tests): Verifies fail-closed product-status rules for Javan Electronic.
  - `TestDualPathSupplierAvailabilityGate` (7 tests): Verifies that blocked products never reach add_to_cart across Path A and Path B.

### 39. `test_tab2_canonical_procurement.py`
- **Classification**: `KEEP`
- **Domain**: Tab 2 procurement view staging, selection, and dispatch
- **Summary**: 7 passed in 1.26s
- **Module Docstring**: Tests for Tab 2 (Altium BOM Project Auditor) Canonical Procurement Semantics: - Mode A (Database-Aware / Inventory-Driven):   * Direct purchasing strictly targeting the Inventory.xlsx link.   * Validation of MPN, Package, Footprint, Specs, Dimensions.   * Brand double-check only if BOM specified an explicit brand; passes if ANY.   * Strict typed failures on mismatch (INCOMPATIBLE_MPN, INCOMPATIBLE_PACKAGE, etc.).   * No multi-vendor fallback or silent vendor substitution. - Mode B (BOM-Direct / Turnkey):   * Multi-vendor discovery across all enabled registered vendors.   * Brand Rule handling (ANY, single brand, approved list).   * Canonical quantity calculation (if req < moq: moq; else: ceil(req/step)*step).   * Deterministic price & quantity ranking. - 7 Historical Safeguards:   * Strict live site stock (NO-PARTIAL-STOCK).   * Out of stock & unorderable detection.
- **Test Classes**:
  - `MockLionTab2Adapter` (0 tests): No class docstring
  - `MockJavanTab2Adapter` (0 tests): No class docstring
  - `TestModeAValidationAndSafeguards` (4 tests): Mode A tests: Database-aware direct purchasing strictly using Inventory.xlsx LINK.
  - `TestModeBTurnkeySourcing` (2 tests): Mode B tests: Pure CAD BOM turnkey sourcing across all enabled vendors.
  - `TestCanonicalQuantityCalculation` (1 tests): Verifies Layer 5 Canonical Quantity Rule.

### 40. `test_ui_tab1_inventory_view.py`
- **Classification**: `KEEP`
- **Domain**: Tab 1 UI inventory tables, column distribution, search, and stock policy views
- **Summary**: 19 passed, 19 warnings in 9.01s
- **Test Classes**:
  - `TestTab1InventoryView` (19 tests): Test suite verifying Phase 1 Read-Only Inventory and Stock Policy view.

### 41. `test_universal_discovery.py`
- **Classification**: `KEEP`
- **Domain**: Universal site discovery, sitemap crawling, and product catalog indexing
- **Summary**: 21 passed in 6.05s
- **Module Docstring**: Deterministic Unit Tests for Omnix Universal Discovery Engine & Validator Governing Specifications: - docs/DISCOVERY/SITE_MAP_SCHEMA.md - docs/DISCOVERY/DISCOVERY_METHODOLOGY.md
- **Test Classes**:
  - `TestUniversalDiscoveryModels` (2 tests): Verify dataclass serialization, deserialization, and schema fidelity.
  - `TestEvidenceRecorder` (2 tests): Verify deterministic evidence recording and ID generation.
  - `TestSiteMapGraphBuilder` (3 tests): Verify programmatic graph construction and reference validation.
  - `TestSiteMapGraphValidator` (8 tests): Verify 10-point quality assurance validator.
  - `TestUniversalDiscoveryCLI` (6 tests): Verify CLI interface and exit codes.

### 42. `test_vendor_links.py`
- **Classification**: `KEEP`
- **Domain**: Vendor link syntax parsing (LION=...; JAVAN=...), tokenization, and fallback
- **Summary**: 33 passed in 1.92s
- **Module Docstring**: Tests for Multi-Vendor Purchase Link Integration for Mode A. Governing Requirements: - Section 9.1: Parser Tests (19 scenarios) - Section 9.2: Single-Link Behavior (bypasses dialog, direct dispatch) - Section 9.3: Multi-Link Selection (dialog prompt, meaningful display names, cancel safety, selection preservation) - Section 9.4: Adapter Dispatch & Regression (atomic resolution, combined string isolation, Case D enforcement)
- **Test Classes**:
  - `MockLionAdapter` (0 tests): No class docstring
  - `MockJavanAdapter` (0 tests): No class docstring
  - `TestVendorLinksParser` (19 tests): Covers all 19 required parsing scenarios from Section 9.1.
  - `TestSingleLinkBehavior` (3 tests): Verifies that items with exactly 1 valid URL bypass selection dialogs completely.
  - `TestMultiLinkSelection` (7 tests): Verifies vendor selection modal prompt, meaningful names, cancel safety, and Case D.
  - `TestAdapterDispatchAndRegression` (4 tests): Verifies atomic adapter resolution, combined string isolation, and Excel loading.

### 43. `test_vendor_registry.py`
- **Classification**: `KEEP`
- **Domain**: Vendor registry discovery, registration, and URL-to-adapter resolution
- **Summary**: 17 passed in 1.24s
- **Module Docstring**: Deterministic Unit Tests for VendorRegistry Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 15
- **Test Classes**:
  - `MockVendorAdapterA` (0 tests): No class docstring
  - `MockVendorAdapterB` (0 tests): No class docstring
  - `TestVendorRegistryRegistration` (4 tests): Verify adapter registration, duplicate rejection, and type safety.
  - `TestVendorRegistryLookupAndFactory` (4 tests): Verify deterministic instantiation, config propagation, and error handling.
  - `TestVendorRegistryURLRouting` (5 tests): Verify deterministic URL-based vendor identification and edge cases.
  - `TestVendorRegistryProductionAdapters` (3 tests): Verify registration and routing of the three production adapters: Lion, Javan, RoboEq.
  - `TestVendorRegistryThreadSafety` (1 tests): Verify concurrent registration and lookup safety.

### 44. `test_versioned_registry.py`
- **Classification**: `KEEP`
- **Domain**: Versioned vendor registry supporting concurrent plugin versions and hot switching
- **Summary**: 26 passed in 0.64s
- **Module Docstring**: Deterministic Unit and Concurrency Tests for Omnix Phase 3: Version-Aware Registry Metadata. Governing Architecture Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Phase 3.  Covers all 22 required Phase 3 verification scenarios:  1. Empty-by-default behavior is preserved for new and default registries.  2. Multiple versions of one vendor coexist.  3. First-version activation follows the documented default.  4. Additional versions remain inactive by default.  5. Registering after explicit deactivation does not reactivate the vendor.  6. Explicit activation switches the selected version.  7. Explicitly registering the first version with activate=False leaves the vendor inactive.  8. Duplicate version registration is rejected.  9. Invalid manifest registration leaves registry state unchanged. 10. Plugin identity conflicts are rejected atomically. 11. Only active-version domains appear in live route mappings. 12. Failed activation due to collision preserves the previous active version and routes. 13. Unregistering an inactive version leaves the active version undisturbed. 14. Unregistering the active version clears its pointer and routes without silent fallback. 15. Unregistering a complete vendor clears every associated version and route. 16. Version-specific metadata remains queryable for inactive versions. 17. get_enabled_vendors() excludes disabled and inactive vendors. 18. get_adapter(vendor_id) fails closed when no version is active. 19. URL-to-adapter resolution corresponds to the exact active version selected in its consistent registry snapshot. 20. Concurrent read/switch tests establish that readers cannot observe partially updated routing or pointer state. 21. Legacy registration defaults and manifest-backed registration remain distinguishable. 22. Existing adapter contract and capability validation remain intact.
- **Test Classes**:
  - `MockVersionAdapter` (0 tests): Compliant mock vendor adapter for versioned registry testing.
  - `MockVendorBAdapter` (0 tests): No class docstring
  - `MockVendorCAdapter` (0 tests): No class docstring
  - `TestPhase3VersionedRegistry` (22 tests): Complete, deterministic verification of Phase 3 Version-Aware Registry Metadata.
  - `TestPhase3AtomicProcurementDispatch` (4 tests): Regression tests verifying atomic procurement URL dispatch without TOCTOU.

## Mandatory Gate & Next Steps

1. **Zero Test Deletions**: Every test in the existing 859-test suite is retained in working order.
2. **Proposed Consolidation for User Review**:
   - `test_lion_rules.py` (2 tests) imports legacy `lion_automator` solely to test `calculate_target_quantity`. It is recommended to migrate these 2 calculation tests into `tests/test_lion_adapter.py` upon user authorization, allowing `lion_automator.py` to be completely unreferenced.
