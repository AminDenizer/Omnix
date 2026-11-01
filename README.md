# Omnix — Electronic Inventory, Altium BOM Auditor & Multi-Vendor Procurement Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Selenium](https://img.shields.io/badge/Automation-Selenium-orange.svg)](https://www.selenium.dev/)
[![Tests](https://img.shields.io/badge/Tests-1284%20Passed-brightgreen.svg)](https://pytest.org/)
[![Release](https://img.shields.io/badge/Release-v1.0.0-blue.svg)](https://github.com/AminDenizer/Omnix/releases)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

**Omnix** is an enterprise-grade, high-performance desktop workstation engineered for electronic hardware design laboratories and assembly lines. It integrates:
1. **Canonical Mode A Inventory Engine**: High-speed SQLite database with multi-drawer bin tracking, stock policies, and encrypted backups.
2. **Altium Designer BOM Auditor**: Real-time shortage auditing, board multiplier scaling, and printable A4/A5 assembly worksheets.
3. **Matrix Label Printing Engine**: Component box/reel labeling with scissors cut guides and high-contrast B&W thermal/laser printing.
4. **Decoupled Multi-Vendor Procurement**: Extensible XPL plugin architecture supporting automated cart placement, PDP validation, and order reconciliation for Lion Electronic, Javan, and RoboEq.

---

## 📑 Table of Contents
- [✨ Key Features](#-key-features)
- [📦 System Architecture](#-system-architecture)
- [🖥️ Core Workflows](#️-core-workflows)
  - [1. Warehouse & Stock Management (Mode A)](#1-warehouse--stock-management-mode-a)
  - [2. Altium BOM Assembly & Shortage Audit](#2-altium-bom-assembly--shortage-audit)
  - [3. Matrix Component Label Printing](#3-matrix-component-label-printing)
  - [4. Multi-Vendor Procurement & Plugin Engine](#4-multi-vendor-procurement--plugin-engine)
- [⌨️ Keyboard Shortcuts](#️-keyboard-shortcuts)
- [🧪 Automated Test Suite (1,284 Tests)](#-automated-test-suite-1284-tests)
- [🛠️ Build Standalone Executable (Omnix.exe)](#️-build-standalone-executable-omnixexe)
- [👨‍💻 Author & Credits](#-author--credits)

---

## ✨ Key Features

- **Database-Aware Inventory (Mode A)**: Fast, ACID-compliant local database storing component attributes, drawer locations, thresholds, and multi-supplier links.
- **Altium BOM Multi-Board Scaler**: Calculates required quantities scaled by production board count ($TotalNeeded = QtyPerBoard \times Multiplier$).
- **Matrix Label Engine**:
  - Scissors cut guidelines (`✂ - - - -`) for fast manual cutting.
  - Clear, readable typography and visual borders with zero-highlight design for crisp black-and-white printing.
- **Multi-Vendor XPL Plugin Architecture**:
  - Modular, sandboxed vendor adapters (`.xpl`) verified with Ed25519 digital signatures.
  - Multi-candidate preview dialogs with automatic MOQ and packaging step arithmetic.
  - Cart synchronization, idempotency keys, and delta verification.
- **Backup, Restore & Merge Pipeline**:
  - Export and import encrypted, timestamped backups (`.obk`).
  - Merge secondary databases with interactive conflict resolution.
- **Engineered Matte Dark UI**: Sleek, high-contrast PyQt6 desktop interface with custom title bar, responsive keyboard navigation, and live logging.

---

## 📦 System Architecture

```
Omnix/
├── main.py                     # High-DPI application entry point & Qt runner
├── config.py                   # Centralized application constants & path resolvers
├── bom_auditor.py              # Altium BOM parser, multiplier engine & report generator
├── excel_loader.py             # Excel import/export synchronization engine
├── core/
│   ├── inventory/              # Database models, SQLite repository, backup & merge engine
│   ├── procurement/            # Universal procurement orchestrator, bridge & vendor registry
│   ├── plugins/                # Modular XPL plugin installer, trust store & verification engine
│   └── discovery/              # Vendor web discovery, evidence capturing & site mapping
├── ui/
│   ├── main_window.py          # Unified desktop workstation & layout orchestration
│   ├── native_window.py        # Windows frameless native window event handling
│   ├── styles.py               # Modern matte dark design system
│   ├── printing/               # Matrix label engine & A4/A5 assembly worksheet print engine
│   ├── widgets/                # Table views, sidebar, live log ribbon & audit panels
│   └── dialogs/                # Settings, order preview, component edit & merge modals
├── vendors/                    # Modular vendor packages (Lion, Javan, RoboEq)
└── tests/                      # Full test suite (78 files, 1,284 automated tests)
```

---

## 🖥️ Core Workflows

### 1. Warehouse & Stock Management (Mode A)
1. Launch **Omnix**. The local database is initialized automatically.
2. Use the live search bar (`/`) to filter components across Part Name, Part Number, Description, or Footprint.
3. Edit component drawer allocations, threshold levels, and supplier links in the component editor.
4. Back up or merge warehouse databases seamlessly via the **Backup & Restore** tab.

### 2. Altium BOM Assembly & Shortage Audit
1. Navigate to the **BOM Assembly Auditor** tab.
2. Drop an Altium BOM spreadsheet (`.xlsx` or `.xls`).
3. Set the **Board Multiplier** for your production run.
4. Omnix automatically cross-references your warehouse inventory and highlights shortages, available parts, and missing catalog items.
5. Export detailed A4/A5 Assembly Worksheets directly to PDF.

### 3. Matrix Component Label Printing
1. In the **Assembly Preparation** tab, select components or load from your BOM.
2. Click **Print Matrix Labels** to preview and export cut-ready component labels.
3. Designed specifically for standard office laser or thermal B&W printers with dotted cut lines.

### 4. Multi-Vendor Procurement & Plugin Engine
1. Review candidate shortages across supported suppliers (**Lion Electronic**, **Javan**, **RoboEq**).
2. Configure vendor credentials in **Account Settings** (stored securely on your local machine).
3. The automated procurement engine validates product availability, adjusts for packaging steps (MOQ), and places items safely into your vendor cart.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action | Description |
| :---: | :--- | :--- |
| **`/`** | Focus Search Bar | Jumps directly to multi-term component search |
| **`Esc`** | Smart Escape Navigation | Clears search input $\rightarrow$ Defocuses table $\rightarrow$ Prompts exit |
| **`F5`** | Refresh View | Reloads data from the local database |
| **`Ctrl + Q`** | Safe Exit | Safely closes the application |
| **`Double Click`** | Open Store / Details | Opens product URL or opens component detail dialog |

---

## 🧪 Automated Test Suite (1,284 Tests)

Omnix includes an extensive end-to-end test suite covering all business logic, database migrations, UI rendering, vendor adapters, and procurement workflows:

```bash
python -m pytest -v
```

```
===================== 1284 passed in 251.46s =====================
```

---

## 🛠️ Build Standalone Executable (Omnix.exe)

To compile the single-file portable Windows executable including all signed plugins, UI assets, and seed data:

```bash
pip install -r requirements.txt
python -m PyInstaller Omnix.spec
```

The resulting standalone executable is generated at `dist/Omnix.exe`.

---

## 👨‍💻 Author & Credits

- **Developer**: **Amin Denizer**
- **Email**: `a.m.denizer@gmail.com`
- **Organization**: **DOT**
- **Repository**: [https://github.com/AminDenizer/Omnix](https://github.com/AminDenizer/Omnix)
