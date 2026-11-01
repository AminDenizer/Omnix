# Omnix — Electronic Inventory, Altium BOM Auditor & Procurement Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Selenium](https://img.shields.io/badge/Automation-Selenium-orange.svg)](https://www.selenium.dev/)
[![Tests](https://img.shields.io/badge/Tests-PyTest%2013%2F13%20Passed-brightgreen.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

**Omnix** is a high-performance, matte dark desktop application engineered for electronic hardware design and assembly workflows. It combines:
1. **Dynamic Warehouse Inventory Management** (`Inventory.xlsx`) with two-way spreadsheet synchronization.
2. **Altium Designer BOM Assembly Auditor** with multi-board scaling multipliers and PDF shortage reporting.
3. **Automated Lion Electronic Procurement Engine** with 7-layer validation, smart packaging step rounding, and zero-risk stock updates.

---

## 📑 Table of Contents
- [✨ Key Features](#-key-features)
- [📦 System Architecture & Core Logics](#-system-architecture--core-logics)
- [🖥️ User Manual & Workflow Guide](#️-user-manual--workflow-guide)
  - [1. Warehouse Inventory Management](#1-warehouse-inventory-management)
  - [2. Altium BOM Assembly Shortage Audit](#2-altium-bom-assembly-shortage-audit)
  - [3. Automated Purchasing on Lion Electronic](#3-automated-purchasing-on-lion-electronic)
- [⌨️ Keyboard Shortcuts](#️-keyboard-shortcuts)
- [📊 Database & BOM Schema Specifications](#-database--bom-schema-specifications)
- [🧪 Automated Test Suite](#-automated-test-suite)
- [🛠️ Build Standalone Executable (Omnix.exe)](#️-build-standalone-executable-omnixexe)
- [👨‍💻 Author & Credits](#-author--credits)

---

## ✨ Key Features

- **Strict Single-Source Database Loading**: Automatically and exclusively detects `Inventory.xlsx` located alongside the executable. If missing, prompts with instructions and hotkey `[F5]` reload.
- **Altium BOM Multi-Board Scaler**: Calculates exact required component quantities scaled by production board count ($TotalNeeded = QtyPerBoard \times Multiplier$).
- **Intelligent Inventory Matching**: Robust multi-field matching engine supporting exact Part Number, normalized text, Comment, Footprint, and Description.
- **7-Layer Automated Procurement Safeguards**:
  - **Layer 1**: 404 & Dead link prevention.
  - **Layer 2**: Inquiry-only and closed-sale detection.
  - **Layer 3**: Out-of-stock and coming-soon text analysis.
  - **Layer 4**: Buy button state and inquiry modal detection.
  - **Layer 5**: Smart packaging step / pack multiple calculation.
  - **Layer 6**: Strict store stock availability check (aborts on insufficient stock).
  - **Layer 7**: SweetAlert / store error toast capture.
- **Smart Packaging Multiple Rounding**:
  - Small multiples ($2, 5, 10$): Rounds up to the next multiple of $10$ (e.g. $45 \rightarrow 50$) to satisfy store batch rules and eliminate checkout errors.
  - Large package steps ($25, 50, 100$): Rounds up to the exact packaging step ($23 \rightarrow 25, 85 \rightarrow 100$).
  - Single-piece parts ($1$): Retains exact count ($11 \rightarrow 11$).
- **Strict No-Partial-Stock Policy**: If the store has fewer units than required ($11 < 20$), purchase is halted and flagged as `⚠️ Low Site Stock` without adding incomplete items to the cart.
- **Two-Way Database Stock Updates**: Post-purchase confirmation strictly updates only successfully ordered items in `Inventory.xlsx`.
- **Engineered Matte Dark UI**: High-contrast, left-to-right (LTR) layout with glowing microchip splash screen and multi-resolution Windows icons.

---

## 📦 System Architecture & Core Logics

```
Omnix/
├── main.py                     # Application entry point & High-DPI Qt runtime
├── config.py                   # App metadata, bundle directory, and path resolvers
├── excel_loader.py             # Inventory.xlsx loader, normalizer, and 2-way sync
├── bom_auditor.py              # Altium BOM parser, multiplier engine, and PDF generator
├── lion_automator.py           # Selenium automation engine with 7-layer validation
├── settings_manager.py         # Credentials manager (settings.json)
├── ui/
│   ├── main_window.py          # Dual-tab main window container & hotkeys
│   ├── splash_screen.py        # Glowing IC startup animation
│   ├── styles.py               # Slate/matte dark stylesheet
│   ├── widgets/
│   │   ├── inventory_table.py  # Interactive spreadsheet table & cell editor
│   │   ├── stats_ribbon.py     # Live KPIs & shortage counters
│   │   └── bom_audit_widget.py # Altium BOM drop zone & audit results
│   ├── dialogs/
│   │   ├── order_preview_dialog.py # Procurement modal & live progress tracker
│   │   └── settings_dialog.py      # Account settings & credentials modal
│   └── icons/                  # Multi-resolution ICO (16-256px) and UI assets
└── tests/                      # Comprehensive 13-test PyTest test suite
```

---

## 🖥️ User Manual & Workflow Guide

### 1. Warehouse Inventory Management
1. Place your inventory file named **`Inventory.xlsx`** in the same folder as `Omnix.exe`.
2. Launch `Omnix.exe`. The inventory is loaded automatically.
3. Use the search bar (`/`) for multi-term instant filtering (e.g., typing `Timer DIP-8` finds `NE555P`).
4. Double-click on any cell in **Min Stock** or **Target Stock** to edit thresholds directly. Changes are automatically saved back to `Inventory.xlsx`.
5. Press `[F5]` at any time to reload data from disk.

### 2. Altium BOM Assembly Shortage Audit
1. Switch to the **BOM Assembly Auditor** tab (Tab 2).
2. Drag and drop your Altium BOM export (`.xlsx` or `.xls`) or click to browse.
3. Set the **Boards Multiplier** (e.g., $10$ boards for a production run of 10 boards).
4. Review the breakdown:
   - ✅ **Fully Available**: Total needed $\le$ warehouse stock.
   - ⚠️ **Shortages**: Total needed $>$ warehouse stock.
   - 🔴 **Not in Database**: Unregistered components.
5. Click **📄 Export Missing & Shortages Report** to generate a clean PDF report.

### 3. Automated Purchasing on Lion Electronic
1. Click **⚙️ Account Settings** to configure your `lionelectronic.ir` username and password.
2. Click **🛒 Order Shortages on Lion Electronic**.
3. Review the items in the **Procurement & Order Confirmation** dialog.
4. Click **🛒 Order Items on Lion Electronic**.
5. The automation opens Chrome, logs in, checks store stock, applies packaging steps, and adds valid items to your cart.
6. Once the batch finishes, finalize payment in Chrome.
7. Return to Omnix and click **💰 Confirm Payment & Add Stock**. Only successfully purchased items are incremented in `Inventory.xlsx`.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action | Description |
| :---: | :--- | :--- |
| **`/`** | Focus Search Bar | Jumps to live multi-term search input |
| **`Esc`** | Smart Escape Navigation | Defocuses search $\rightarrow$ Clears query $\rightarrow$ Prompts exit confirmation |
| **`F5`** | Reload Database | Reloads `Inventory.xlsx` directly from disk |
| **`Ctrl + Q`** | Exit Application | Safely closes the application |
| **`Double Click`** | Open Store / Datasheet Link | Opens product URL in default browser |

---

## 📊 Database & BOM Schema Specifications

### Standard `Inventory.xlsx` Headers

| Column Header | Type | Description |
| :--- | :---: | :--- |
| `PART NAME` | String | Primary component name or designator identifier |
| `DISCRIPTION` | String | Technical specifications, package type, rating |
| `Quantity in Stock` | Integer | Current available stock quantity in warehouse |
| `FOOTPRINT` | String | PCB footprint (e.g., `DIP-8`, `SOIC-8`, `TO-220`) |
| `PART NUMBER` | String | Manufacturer part number (e.g., `NE555P`, `LM358N`) |
| `LINK` | URL | Direct store URL (e.g., `https://lionelectronic.ir/products/...`) |
| `Min Stock` | Integer | Minimum threshold (triggers shortage when $Current \le Min$) |
| `Target Stock` | Integer | Restock target quantity ($Needed = Target - Current$) |

---

## 🧪 Automated Test Suite

Run the full automated test suite using `pytest`:

```bash
python -m pytest -v
```

### Coverage (13 Tests):
- `test_excel_loader.py`: Strict file matching, Persian/Arabic string normalization, fuzzy column mapping, shortage calculations, live filtering, and atomic stock increment.
- `test_lion_rules.py`: Smart packaging step arithmetic, MOQ enforcement, and site stock threshold validation.
- `test_bom_auditor.py`: Multi-board quantity multiplication, database matching, and shortage list generation.
- `test_dialog_and_edge_cases.py`: Mixed successful and failed order processing and stock increment safety.
- `test_settings_and_config.py`: Settings persistence and path resolution.

---

## 🛠️ Build Standalone Executable (Omnix.exe)

To compile the single-file portable Windows executable with embedded multi-layer icons:

```bash
pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name "Omnix" --icon "ui/icons/app_logo.ico" --add-data "ui;ui" main.py
```

The output standalone file is generated at `dist/Omnix.exe`.

---

## 👨‍💻 Author & Credits

- **Developer**: **Amin Denizer**
- **Email**: `a.m.denizer@gmail.com`
- **Organization**: **DOT**
- **Repository**: [https://github.com/AminDenizer/Omnix](https://github.com/AminDenizer/Omnix)