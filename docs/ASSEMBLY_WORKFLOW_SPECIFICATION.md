# Omnix Altium BOM Assembly Preparation & A5 Landscape Print Specification

## 1. Overview & Purpose
The **Assembly & BOM Preparation** workflow (Tab 3 in the Omnix Desktop Application) provides a dedicated, read-only physical manufacturing preparation view for production engineers and technicians. It consumes normalized Altium BOM data directly from the active BOM audit state (`BOMAuditResult`) without secondary parsing or procurement engine overhead.

---

## 2. Authoritative Project Name Contract
1. **Resolution Rule**:
   $$\text{PROJECT\_NAME} = \text{stem of uploaded BOM filename}$$
   (e.g., `FC_IO_V1.3.xlsx` $\to$ `FC_IO_V1.3`).
2. **Placement**:
   - `PROJECT_NAME` appears **only** as the header of the first column (Column 0).
   - Data cells in Column 0 contain **only** `N1`, `N2`, `N3` ... `Nn`.
   - The project name is **never** repeated inside table rows and **never** prepended to N markers (e.g., `FC_IO_V1.3-N1` is strictly prohibited).

---

## 3. Automatic Row Markers (`N1`...`Nn`)
1. **Sequence**: 1-based sequential integers prefixed with `"N"` (`N1`, `N2`, ..., `Nn`).
2. **Order**: Follows canonical BOM row order.
3. **Domain Isolation**:
   - Purely presentation markers for physical worksheet reference and manual package labeling.
   - Strictly excluded from Core procurement matching, candidate selection, cart identity, and `Inventory.xlsx` logic.
4. **Project Reset**: Loading a new BOM resets numbering cleanly starting from `N1`.

---

## 4. 9-Column Assembly Table Contract

| Column # | Header Label | Source Field (`BOMItem`) | Alignment | Formatting / Notes |
|:---:|:---|:---|:---:|:---|
| **0** | `<PROJECT_NAME>` | Sequential Row Marker | Center | Bold Monospace Cyan (`N1`, `N2`...) |
| **1** | `Comment` | `item.comment` | Left | UTF-8 Text / Persian Support |
| **2** | `Description` | `item.description` | Left | Word-wrapped description |
| **3** | `Designator` | `item.designator` | Left | Monospace, preserves multi-designators (`C2,C23`) |
| **4** | `Footprint` | `item.footprint` | Center | Monospace footprint string |
| **5** | `LibRef` | `item.lib_ref` | Left | CAD schematic library reference |
| **6** | `Quantity` | `item.unit_qty` / total | Center | Bold integer quantity |
| **7** | `Part Number` | `item.part_number` | Left | Bold Monospace MPN |
| **8** | `Package` | `item.package or item.footprint` | Center | Physical package identification |

---

## 5. Unified A5 Landscape Print Engine (`AssemblyPrintEngine`)
- **Target**: A5 Landscape ($210 \times 148\text{ mm}$), $6\text{ mm}$ margins ($198 \times 136\text{ mm}$ printable area).
- **Single Canonical Renderer**: Drives Print Preview (`AssemblyPreviewDialog`), Physical Printing (`QPrintDialog`), and Vector PDF Export.
- **Header Block**: Title block with Project Name, Date/Time, Total Line Items, and Total Component Count.
- **Repeated Table Header**: `thead { display: table-header-group; }` ensures the 9-column header repeats at the top of every page.
- **Row Protection**: `tr { page-break-inside: avoid; }` prevents rows from splitting across page breaks.
- **Mixed-Language (Persian + English)**: High-quality bidirectional text support (`dir="auto"` for descriptions/comments, explicit `dir="ltr"` for MPNs, designators, footprints, and packages).
- **PDF Export Default Filename**: `<PROJECT_NAME>_Assembly_Worksheet_A5.pdf`.
