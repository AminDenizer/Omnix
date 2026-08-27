# Omnix — Electronic Components Database Viewer

A high-performance, lightweight, matte dark database viewer for electronic components, built with Python and PyQt6. It automatically detects and reads local Excel spreadsheets (`.xlsx`) as the active database source with instant multi-column search and dynamic schema loading.

## ✨ Features
- **Dynamic Excel Schema**: Automatically extracts columns and records from the first sheet of any Excel spreadsheet.
- **Zero-Configuration Auto-Detection**: Automatically detects and loads any Excel database file (`SA.xlsx`, etc.) placed in the project folder.
- **Instant Multi-Term Live Search**: High-speed filtering across all columns, parameters, and part numbers in real-time.
- **Engineered Matte Dark UI**: Sleek high-contrast dark theme with Left-to-Right (LTR) engineering layout.
- **Multi-Stage Escape Navigation**: Smart `Esc` key handling (defocus/clear search -> deselect records -> prompt exit confirmation).
- **Interactive Data Table**: Click headers to sort, auto-fitted columns, copy cell/row context menu, and direct web link launching for datasheets/store URLs.

## 🚀 Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Launch Application
```bash
python main.py
```

---
Developed by **AminDenizer** from **DOT**
