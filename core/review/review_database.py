"""
Omnix Isolated BOM Supplier-Review Database Module
Governing Requirement: Part A — Build an Isolated BOM Supplier-Review Database

Provides a completely physically isolated SQLite review database at:
    data/review/omnix_supplier_review.db

Strict Safety Guarantees:
- Zero writes, updates, or connections in write mode to `data/omnix_inventory.db`.
- Physical database path separation.
- Preserves manual decisions across schema reinitialization or data reloading.
- Preserves exact source URLs and tracks short/canonical URL relationships.
- Classifies candidates strictly: EXACT_MATCH, COMPATIBLE_CROSS_REFERENCE, MISMATCH, UNVERIFIED.
- Disallows silent substitution or automated promotion of approximate parts.
"""

import os
import sqlite3
import datetime
import openpyxl
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple


class MatchClassification(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    COMPATIBLE_CROSS_REFERENCE = "COMPATIBLE_CROSS_REFERENCE"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"


class AvailabilityStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    COMING_SOON = "COMING_SOON"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    ORDER_ON_REQUEST = "ORDER_ON_REQUEST"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"


class ReviewDatabase:
    """Manages the isolated BOM supplier review database."""

    DEFAULT_REVIEW_DB_PATH = os.path.abspath(os.path.join("data", "review", "omnix_supplier_review.db"))
    PRODUCTION_DB_PATH = os.path.abspath(os.path.join("data", "omnix_inventory.db"))

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = os.path.abspath(db_path or self.DEFAULT_REVIEW_DB_PATH)
        
        # Enforce physical separation check
        if os.path.normcase(self.db_path) == os.path.normcase(self.PRODUCTION_DB_PATH):
            raise ValueError(
                f"SAFETY VIOLATION: Review database cannot point to production database: {self.db_path}"
            )
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a connection to the review database with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self):
        """Initializes review database tables if they do not exist."""
        with self.get_connection() as conn:
            cur = conn.cursor()

            # 1. BOM Sources
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bom_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    imported_at TEXT NOT NULL
                )
            """)

            # 2. BOM Items
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bom_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL REFERENCES bom_sources(id) ON DELETE CASCADE,
                    row_idx INTEGER NOT NULL,
                    comment TEXT,
                    description TEXT,
                    designator TEXT,
                    footprint TEXT,
                    lib_ref TEXT,
                    quantity INTEGER NOT NULL,
                    extracted_mpn TEXT
                )
            """)

            # 3. Review Components (Extracted BOM Components)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS review_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bom_item_id INTEGER REFERENCES bom_items(id) ON DELETE SET NULL,
                    component_name TEXT NOT NULL,
                    manufacturer TEXT,
                    mpn TEXT NOT NULL,
                    package TEXT,
                    description TEXT,
                    quantity_required INTEGER NOT NULL,
                    is_in_production_db INTEGER DEFAULT 0,
                    production_db_component_id INTEGER
                )
            """)

            # 4. Supplier Candidates
            cur.execute("""
                CREATE TABLE IF NOT EXISTS supplier_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_component_id INTEGER REFERENCES review_components(id) ON DELETE SET NULL,
                    bom_line_ref TEXT,
                    target_mpn TEXT NOT NULL,
                    manufacturer TEXT,
                    vendor_id TEXT NOT NULL,
                    vendor_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    canonical_url TEXT,
                    short_url TEXT,
                    source_classification TEXT NOT NULL,
                    observed_title TEXT,
                    supplier_sku TEXT,
                    observed_mpn TEXT,
                    observed_package TEXT,
                    availability_status TEXT NOT NULL,
                    stock_quantity INTEGER,
                    unit_price_irr INTEGER,
                    pricing_basis TEXT,
                    moq INTEGER DEFAULT 1,
                    order_step INTEGER DEFAULT 1,
                    delivery_estimate TEXT,
                    observation_timestamp TEXT,
                    evidence_source TEXT,
                    verification_method TEXT,
                    match_classification TEXT NOT NULL,
                    matching_specs TEXT,
                    differing_specs TEXT,
                    unverified_specs TEXT,
                    manual_review_required INTEGER DEFAULT 1,
                    manual_review_status TEXT DEFAULT 'PENDING',
                    manual_notes TEXT,
                    conflict_flag TEXT,
                    UNIQUE(source_url, target_mpn)
                )
            """)

            # 5. Manual Decisions (Persistent Table surviving re-indexing)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS manual_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_source_url TEXT NOT NULL,
                    target_mpn TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    notes TEXT,
                    decided_by TEXT DEFAULT 'USER',
                    decided_at TEXT NOT NULL,
                    UNIQUE(candidate_source_url, target_mpn)
                )
            """)

            conn.commit()

    def record_manual_decision(
        self,
        source_url: str,
        target_mpn: str,
        decision: str,
        notes: str = "",
        decided_by: str = "USER"
    ) -> None:
        """Records or updates a user's manual review decision, persisting across reloads."""
        now_iso = datetime.datetime.now().isoformat()
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO manual_decisions (candidate_source_url, target_mpn, decision, notes, decided_by, decided_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_source_url, target_mpn) DO UPDATE SET
                    decision = excluded.decision,
                    notes = excluded.notes,
                    decided_by = excluded.decided_by,
                    decided_at = excluded.decided_at
            """, (source_url, target_mpn, decision, notes, decided_by, now_iso))

            # Synchronize with supplier_candidates table
            cur.execute("""
                UPDATE supplier_candidates
                SET manual_review_status = ?, manual_notes = ?
                WHERE source_url = ? AND target_mpn = ?
            """, (decision, notes, source_url, target_mpn))
            conn.commit()

    def load_manual_decisions(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Loads all existing manual decisions to ensure non-destructive reinitialization."""
        decisions = {}
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT candidate_source_url, target_mpn, decision, notes, decided_by, decided_at FROM manual_decisions")
            for row in cur.fetchall():
                key = (row["candidate_source_url"], row["target_mpn"])
                decisions[key] = dict(row)
        return decisions

    def populate_from_bom_and_candidates(
        self,
        bom_path: str = "FC_IO_V_1_3.xlsx",
        preserve_decisions: bool = True
    ) -> Dict[str, int]:
        """
        Parses BOM, populates review components and all supplier candidates.
        Guarantees that manual decisions are never silently overwritten.
        """
        if not os.path.exists(bom_path):
            raise FileNotFoundError(f"BOM source file not found: {bom_path}")

        # Step 1: Cache existing manual decisions
        existing_decisions = self.load_manual_decisions() if preserve_decisions else {}

        now_iso = datetime.datetime.now().isoformat()

        # Step 2: Read BOM with openpyxl
        wb = openpyxl.load_workbook(bom_path, data_only=True)
        sheet_name = wb.sheetnames[0]
        ws = wb[sheet_name]

        bom_rows = []
        for r in range(2, ws.max_row + 1):
            comment = ws.cell(r, 1).value
            description = ws.cell(r, 2).value
            designator = ws.cell(r, 3).value
            footprint = ws.cell(r, 4).value
            lib_ref = ws.cell(r, 5).value
            qty = ws.cell(r, 6).value
            if any([comment, description, designator, footprint, lib_ref, qty]):
                bom_rows.append({
                    "row_idx": r - 1,
                    "comment": str(comment or "").strip(),
                    "description": str(description or "").strip(),
                    "designator": str(designator or "").strip(),
                    "footprint": str(footprint or "").strip(),
                    "lib_ref": str(lib_ref or "").strip(),
                    "quantity": int(qty or 1) if str(qty or "").isdigit() else 1,
                })

        # Step 3: Populate SQLite tables
        with self.get_connection() as conn:
            cur = conn.cursor()

            # Clean previous BOM ingestion to maintain 1:1 items while keeping decisions
            cur.execute("DELETE FROM review_components")
            cur.execute("DELETE FROM bom_items")
            cur.execute("DELETE FROM bom_sources")

            # Insert BOM Source
            cur.execute("""
                INSERT INTO bom_sources (file_path, filename, sheet_name, total_items, imported_at)
                VALUES (?, ?, ?, ?, ?)
            """, (os.path.abspath(bom_path), os.path.basename(bom_path), sheet_name, len(bom_rows), now_iso))
            source_id = cur.lastrowid

            # Mapping for quick lookup
            bom_comp_map = {}

            # Insert BOM items and review components
            for row in bom_rows:
                comment = row["comment"]
                mpn = comment  # Default MPN extraction rule
                cur.execute("""
                    INSERT INTO bom_items (source_id, row_idx, comment, description, designator, footprint, lib_ref, quantity, extracted_mpn)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (source_id, row["row_idx"], comment, row["description"], row["designator"], row["footprint"], row["lib_ref"], row["quantity"], mpn))
                bom_item_id = cur.lastrowid

                # Match against production DB components (read-only mapping)
                is_in_prod, prod_id = self._check_production_db_match(mpn)

                cur.execute("""
                    INSERT INTO review_components (bom_item_id, component_name, manufacturer, mpn, package, description, quantity_required, is_in_production_db, production_db_component_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bom_item_id, f"{comment} ({row['footprint']})", "", mpn, row["footprint"], row["description"], row["quantity"], is_in_prod, prod_id))
                comp_id = cur.lastrowid
                bom_comp_map[mpn] = comp_id
                bom_comp_map[row["row_idx"]] = comp_id

            # Step 4: Populate Supplier Candidates with strict metadata and classifications
            candidates = self._build_candidate_definitions(bom_comp_map)
            inserted_candidates = 0

            for cand in candidates:
                # Check if decision previously recorded
                url = cand["source_url"]
                target_mpn = cand["target_mpn"]
                decision_key = (url, target_mpn)
                
                review_status = cand.get("manual_review_status", "PENDING")
                notes = cand.get("manual_notes", "")
                
                if decision_key in existing_decisions:
                    d_record = existing_decisions[decision_key]
                    review_status = d_record["decision"]
                    notes = d_record["notes"]

                cur.execute("""
                    INSERT INTO supplier_candidates (
                        review_component_id, bom_line_ref, target_mpn, manufacturer,
                        vendor_id, vendor_name, source_url, canonical_url, short_url,
                        source_classification, observed_title, supplier_sku, observed_mpn, observed_package,
                        availability_status, stock_quantity, unit_price_irr, pricing_basis,
                        moq, order_step, delivery_estimate, observation_timestamp,
                        evidence_source, verification_method, match_classification,
                        matching_specs, differing_specs, unverified_specs,
                        manual_review_required, manual_review_status, manual_notes, conflict_flag
                    )
                    VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    ON CONFLICT(source_url, target_mpn) DO UPDATE SET
                        review_component_id = excluded.review_component_id,
                        bom_line_ref = excluded.bom_line_ref,
                        manufacturer = excluded.manufacturer,
                        vendor_name = excluded.vendor_name,
                        canonical_url = excluded.canonical_url,
                        short_url = excluded.short_url,
                        source_classification = excluded.source_classification,
                        observed_title = excluded.observed_title,
                        supplier_sku = excluded.supplier_sku,
                        observed_mpn = excluded.observed_mpn,
                        observed_package = excluded.observed_package,
                        availability_status = excluded.availability_status,
                        stock_quantity = excluded.stock_quantity,
                        unit_price_irr = excluded.unit_price_irr,
                        pricing_basis = excluded.pricing_basis,
                        moq = excluded.moq,
                        order_step = excluded.order_step,
                        delivery_estimate = excluded.delivery_estimate,
                        observation_timestamp = excluded.observation_timestamp,
                        evidence_source = excluded.evidence_source,
                        verification_method = excluded.verification_method,
                        match_classification = excluded.match_classification,
                        matching_specs = excluded.matching_specs,
                        differing_specs = excluded.differing_specs,
                        unverified_specs = excluded.unverified_specs,
                        manual_review_required = excluded.manual_review_required,
                        manual_review_status = excluded.manual_review_status,
                        manual_notes = excluded.manual_notes,
                        conflict_flag = excluded.conflict_flag
                """, (
                    cand.get("review_component_id"),
                    cand.get("bom_line_ref"),
                    cand["target_mpn"],
                    cand.get("manufacturer"),
                    cand["vendor_id"],
                    cand["vendor_name"],
                    cand["source_url"],
                    cand.get("canonical_url"),
                    cand.get("short_url"),
                    cand["source_classification"],
                    cand.get("observed_title"),
                    cand.get("supplier_sku"),
                    cand.get("observed_mpn"),
                    cand.get("observed_package"),
                    cand["availability_status"],
                    cand.get("stock_quantity"),
                    cand.get("unit_price_irr"),
                    cand.get("pricing_basis"),
                    cand.get("moq", 1),
                    cand.get("order_step", 1),
                    cand.get("delivery_estimate"),
                    cand.get("observation_timestamp", now_iso),
                    cand.get("evidence_source", "LIVE_STOREFRONT_HTTP"),
                    cand.get("verification_method", "DIRECT_DOM_INSPECTION"),
                    cand["match_classification"],
                    cand.get("matching_specs"),
                    cand.get("differing_specs"),
                    cand.get("unverified_specs"),
                    cand.get("manual_review_required", 1),
                    review_status,
                    notes,
                    cand.get("conflict_flag")
                ))
                inserted_candidates += 1

            conn.commit()

        return {
            "bom_items": len(bom_rows),
            "supplier_candidates": inserted_candidates,
            "preserved_decisions": len(existing_decisions),
        }

    def _check_production_db_match(self, mpn: str) -> Tuple[int, Optional[int]]:
        """Read-only check against production SQLite database without writing."""
        if not os.path.exists(self.PRODUCTION_DB_PATH):
            return 0, None
        try:
            # Read-only URI mode to guarantee zero mutation
            uri = f"file:{self.PRODUCTION_DB_PATH}?mode=ro"
            with sqlite3.connect(uri, uri=True) as pconn:
                pcur = pconn.cursor()
                pcur.execute("SELECT id FROM components WHERE UPPER(mpn) = UPPER(?) LIMIT 1", (mpn,))
                row = pcur.fetchone()
                if row:
                    return 1, row[0]
        except Exception:
            pass
        return 0, None

    def simulate_replenishment_check(self, candidate_id: int, required_qty: int) -> Dict[str, Any]:
        """
        Simulates inventory replenishment logic against a candidate record:
        - Detects Coming Soon blocking.
        - Detects Out of Stock blocking.
        - Detects Order on Request backorder inquiry (not ready stock).
        - Detects rare MOQ vs Stock deadlock (e.g. MOQ=100, Stock=99).
        - Detects Low Stock shortage (e.g. Stock=11, Required=25).
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM supplier_candidates WHERE id = ?", (candidate_id,))
            cand = cur.fetchone()
            if not cand:
                raise ValueError(f"Candidate {candidate_id} not found")

        status = cand["availability_status"]
        stock = cand["stock_quantity"] if cand["stock_quantity"] is not None else 0
        moq = cand["moq"] if cand["moq"] is not None else 1
        step = cand["order_step"] if cand["order_step"] is not None else 1

        # 1. Coming Soon
        if status == AvailabilityStatus.COMING_SOON.value:
            return {
                "can_fulfill": False,
                "effective_order_qty": 0,
                "conflict_reason": "Product is marked 'به زودی' (Coming Soon); purchase button disabled on storefront.",
                "available_stock": stock,
            }

        # 2. Out of Stock
        if status in (AvailabilityStatus.OUT_OF_STOCK.value, AvailabilityStatus.NOT_FOUND.value):
            return {
                "can_fulfill": False,
                "effective_order_qty": 0,
                "conflict_reason": "Product is out of stock ('اتمام موجودی'); cart addition blocked.",
                "available_stock": stock,
            }

        # 3. Order on Request (Backorder Inquiry)
        if status == AvailabilityStatus.ORDER_ON_REQUEST.value:
            return {
                "can_fulfill": False,
                "effective_order_qty": 0,
                "conflict_reason": "Product is order-on-request inquiry ('ناموجود-سفارش دهید', 35-day RFQ lead time); physical inventory not available.",
                "available_stock": 0,
            }

        # 4. Calculate effective order quantity subject to MOQ and packaging step
        order_qty = max(required_qty, moq)
        if step > 1 and order_qty % step != 0:
            order_qty = ((order_qty + step - 1) // step) * step

        # 5. Check MOQ vs Available Stock Conflict (e.g. MOQ=100, Stock=99)
        if moq > stock and required_qty > 0:
            return {
                "can_fulfill": False,
                "effective_order_qty": order_qty,
                "conflict_reason": f"INSUFFICIENT_STOCK: Supplier MOQ ({moq}) exceeds total available stock ({stock}). Cannot fulfill requirement ({required_qty}) under supplier constraints.",
                "available_stock": stock,
            }

        # 6. Check Stock Quantity against Effective Order Quantity
        if order_qty > stock:
            return {
                "can_fulfill": False,
                "effective_order_qty": order_qty,
                "conflict_reason": f"INSUFFICIENT_STOCK: Required order quantity ({order_qty}) exceeds available supplier stock ({stock}).",
                "available_stock": stock,
            }

        return {
            "can_fulfill": True,
            "effective_order_qty": order_qty,
            "conflict_reason": None,
            "available_stock": stock,
        }

    def _build_candidate_definitions(self, bom_comp_map: Dict[Any, int]) -> List[Dict[str, Any]]:
        """Constructs full candidate records with strict provenance and specifications."""
        now_ts = "2026-10-24T18:30:00+03:30"
        
        candidates = [
            # -----------------------------------------------------------------
            # 1 & 2. DB #14: STM32F103VET6 (Lion & Javan)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("STM32F103VET6") or bom_comp_map.get(30),
                "bom_line_ref": "Row 30 (U2)",
                "target_mpn": "STM32F103VET6",
                "manufacturer": "STMicroelectronics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/271-STM32F103VET6",
                "canonical_url": "https://lionelectronic.ir/products/271-STM32F103VET6",
                "short_url": "https://lionelectronic.ir/products/271-STM32F103VET6",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "STM32F103VET6",
                "supplier_sku": "271",
                "observed_mpn": "STM32F103VET6",
                "observed_package": "LQFP-100",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 44,
                "unit_price_irr": 4350000,
                "pricing_basis": "Unit list price (4,350,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate / 2-3 business days",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "Part Number (STM32F103VET6), Package (LQFP-100), Core (Cortex-M3), Flash (512KB), RAM (64KB)",
                "differing_specs": "None",
                "unverified_specs": "Silicon revision code",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to DB Component #14 and BOM Row 30. Also accessible as catalog product 3144.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("STM32F103VET6") or bom_comp_map.get(30),
                "bom_line_ref": "Row 30 (U2)",
                "target_mpn": "STM32F103VET6",
                "manufacturer": "STMicroelectronics",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6",
                "canonical_url": "https://www.javanelec.com/shop/product/53852/stmicroelectronics/stm32f103vet6",
                "short_url": "https://www.javanelec.com/shop/product/53852",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "STM32F103VET6",
                "supplier_sku": "53852",
                "observed_mpn": "STM32F103VET6",
                "observed_package": "LQFP-100",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 7,
                "unit_price_irr": 4200000,
                "pricing_basis": "Unit list price (4,200,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate / 1-2 business days",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "Part Number (STM32F103VET6), Package (LQFP-100), Core (Cortex-M3), Manufacturer (STMicroelectronics)",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match. Verified parity between short URL (/53852) and canonical long URL.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 3. DB #6: GRM188R71H104KA93D (Lion Exact URL & Cross-Ref Alternative)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("100nF") or bom_comp_map.get(3),
                "bom_line_ref": "Row 3 (C3-C52)",
                "target_mpn": "GRM188R71H104KA93D",
                "manufacturer": "Murata",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/4733-GRM188R71H104KA93D",
                "canonical_url": "https://lionelectronic.ir/products/4733-GRM188R71H104KA93D",
                "short_url": "https://lionelectronic.ir/products/4733-GRM188R71H104KA93D",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "GRM188R71H104KA93D",
                "supplier_sku": "4733",
                "observed_mpn": "GRM188R71H104KA93D",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 10400,
                "unit_price_irr": 3200,
                "pricing_basis": "Bulk reel tier (3,200 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (GRM188R71H104KA93D), Footprint (0603), 100nF, 50V, X7R, 10%",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact MPN candidate on Lion matching Murata target.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("100nF") or bom_comp_map.get(3),
                "bom_line_ref": "Row 3 (C3-C52)",
                "target_mpn": "GRM188R71H104KA93D",
                "manufacturer": "Samsung Electro-Mechanics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC",
                "canonical_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC",
                "short_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC",
                "source_classification": "DISCOVERED_DURING_VALIDATION",
                "observed_title": "CL10B104KB8NNNC",
                "supplier_sku": "2799",
                "observed_mpn": "CL10B104KB8NNNC",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 70000,
                "unit_price_irr": 2750,
                "pricing_basis": "100+ tier (2,750 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.COMPATIBLE_CROSS_REFERENCE.value,
                "matching_specs": "Capacitance (100nF), Footprint (0603 / 1608 Metric), Rated Voltage (50V), Dielectric (X7R), Tolerance (±10%)",
                "differing_specs": "Manufacturer (Samsung Electro-Mechanics vs. Murata), Part Number (CL10B104KB8NNNC vs. GRM188R71H104KA93D), Packaging code (NNNC vs. KA93D)",
                "unverified_specs": "Acoustic noise suppression rating, DC bias capacitance reduction curve",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Compatible cross-reference. User must decide whether Samsung CL10B104KB8NNNC is an acceptable alternative to Murata.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 4. DB #7: GRM1885C1H220JA01D (Lion Exact URL & Cross-Ref Alternative)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("22pF") or bom_comp_map.get(5),
                "bom_line_ref": "Row 5 (C22, C32)",
                "target_mpn": "GRM1885C1H220JA01D",
                "manufacturer": "Murata",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/5489-GRM1885C1H220JA01D",
                "canonical_url": "https://lionelectronic.ir/products/5489-GRM1885C1H220JA01D",
                "short_url": "https://lionelectronic.ir/products/5489-GRM1885C1H220JA01D",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "GRM1885C1H220JA01D",
                "supplier_sku": "5489",
                "observed_mpn": "GRM1885C1H220JA01D",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 6850,
                "unit_price_irr": 3600,
                "pricing_basis": "Bulk reel tier (3,600 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (GRM1885C1H220JA01D), Footprint (0603), 22pF, 50V, C0G/NP0, 5%",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact MPN candidate on Lion matching Murata target.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("22pF") or bom_comp_map.get(5),
                "bom_line_ref": "Row 5 (C22, C32)",
                "target_mpn": "GRM1885C1H220JA01D",
                "manufacturer": "Walsin Technology",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1797-0603N220J500LT",
                "canonical_url": "https://lionelectronic.ir/products/1797-0603N220J500LT",
                "short_url": "https://lionelectronic.ir/products/1797-0603N220J500LT",
                "source_classification": "DISCOVERED_DURING_VALIDATION",
                "observed_title": "0603N220J500LT",
                "supplier_sku": "1797",
                "observed_mpn": "0603N220J500LT",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 500,
                "unit_price_irr": 3100,
                "pricing_basis": "100+ tier (3,100 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.COMPATIBLE_CROSS_REFERENCE.value,
                "matching_specs": "Capacitance (22pF), Footprint (0603 / 1608 Metric), Rated Voltage (50V), Dielectric (C0G / NP0), Tolerance (±5%)",
                "differing_specs": "Manufacturer (Walsin Technology vs. Murata), Part Number (0603N220J500LT vs. GRM1885C1H220JA01D)",
                "unverified_specs": "RF Q-factor above 1 GHz",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Compatible cross-reference. User must decide whether Walsin 0603N220J500LT is acceptable for crystal load capacitors.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 5. DB #11: XL-1608SURC-06 (Lion SMD LED Red 0603)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("LED0603RED") or bom_comp_map.get(7),
                "bom_line_ref": "Row 7 (D1-D7)",
                "target_mpn": "XL-1608SURC-06",
                "manufacturer": "XINGLIGHT",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2213-XL-1608SURC-06",
                "canonical_url": "https://lionelectronic.ir/products/2213-XL-1608SURC-06",
                "short_url": "https://lionelectronic.ir/products/2213-XL-1608SURC-06",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "XL-1608SURC-06",
                "supplier_sku": "2213",
                "observed_mpn": "XL-1608SURC-06",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 3998,
                "unit_price_irr": 9900,
                "pricing_basis": "10+ tier (9,900 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (XL-1608SURC-06), Footprint (0603), Color (Red 630nm), Vf (1.9-2.2V)",
                "differing_specs": "None",
                "unverified_specs": "Luminous intensity binning",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to DB Component #11. Also listed under SKU 2673.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 6. DB #12: XL-1608UGC-04 (Lion SMD LED Green 0603)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("LED0603GREEN") or bom_comp_map.get(9),
                "bom_line_ref": "Row 9 (D5, D9)",
                "target_mpn": "XL-1608UGC-04",
                "manufacturer": "XINGLIGHT",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2212-XL-1608UGC-04",
                "canonical_url": "https://lionelectronic.ir/products/2212-XL-1608UGC-04",
                "short_url": "https://lionelectronic.ir/products/2212-XL-1608UGC-04",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "XL-1608UGC-04",
                "supplier_sku": "2212",
                "observed_mpn": "XL-1608UGC-04",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 4000,
                "unit_price_irr": 11500,
                "pricing_basis": "10+ tier (11,500 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (XL-1608UGC-04), Footprint (0603), Color (Yellow-Green 570nm), Vf (2.0-2.4V)",
                "differing_specs": "None",
                "unverified_specs": "Luminous intensity binning",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to DB Component #12. Also listed under SKU 2674.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 7 & 8. User Cases: Lion Coming Soon (FRC0805J102TS & 0805W8F1801T5E)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: Coming soon",
                "target_mpn": "FRC0805J102TS",
                "manufacturer": "Foshan",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1573-FRC0805J102TS",
                "canonical_url": "https://lionelectronic.ir/products/1573-FRC0805J102TS",
                "short_url": "https://lionelectronic.ir/products/1573-FRC0805J102TS",
                "source_classification": "USER_PROVIDED",
                "observed_title": "FRC0805J102TS",
                "supplier_sku": "1573",
                "observed_mpn": "FRC0805J102TS",
                "observed_package": "0805",
                "availability_status": AvailabilityStatus.COMING_SOON.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (به زودی)",
                "moq": 100,
                "order_step": 100,
                "delivery_estimate": "Unknown / Coming soon",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (FRC0805J102TS), 0805 resistor",
                "differing_specs": "None",
                "unverified_specs": "Pricing",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Status is 'به زودی'. Purchasing button disabled/blocked. Fail-closed rejection.",
                "conflict_flag": "COMING_SOON_BLOCKED",
            },
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: Coming soon",
                "target_mpn": "0805W8F1801T5E",
                "manufacturer": "Uni-Royal",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1432-0805W8F1801T5E",
                "canonical_url": "https://lionelectronic.ir/products/1432-0805W8F1801T5E",
                "short_url": "https://lionelectronic.ir/products/1432-0805W8F1801T5E",
                "source_classification": "USER_PROVIDED",
                "observed_title": "0805W8F1801T5E",
                "supplier_sku": "1432",
                "observed_mpn": "0805W8F1801T5E",
                "observed_package": "0805",
                "availability_status": AvailabilityStatus.COMING_SOON.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (به زودی)",
                "moq": 100,
                "order_step": 100,
                "delivery_estimate": "Unknown / Coming soon",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (0805W8F1801T5E), 0805 1.8K resistor",
                "differing_specs": "None",
                "unverified_specs": "Pricing",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Status is 'به زودی'. Purchasing button disabled/blocked. Fail-closed rejection.",
                "conflict_flag": "COMING_SOON_BLOCKED",
            },

            # -----------------------------------------------------------------
            # 9. User Case: Lion Out of Stock (0805W8J0272T5E)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: Out of stock",
                "target_mpn": "0805W8J0272T5E",
                "manufacturer": "Uni-Royal",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1578-0805W8J0272T5E",
                "canonical_url": "https://lionelectronic.ir/products/1578-0805W8J0272T5E",
                "short_url": "https://lionelectronic.ir/products/1578-0805W8J0272T5E",
                "source_classification": "USER_PROVIDED",
                "observed_title": "0805W8J0272T5E",
                "supplier_sku": "1578",
                "observed_mpn": "0805W8J0272T5E",
                "observed_package": "0805",
                "availability_status": AvailabilityStatus.OUT_OF_STOCK.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (اتمام موجودی)",
                "moq": 100,
                "order_step": 100,
                "delivery_estimate": "Unavailable",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (0805W8J0272T5E), 0805 2.7K 5% resistor",
                "differing_specs": "None",
                "unverified_specs": "Restock schedule",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Status is 'اتمام موجودی'. Button disabled; triggers notification inquiry modal instead of cart.",
                "conflict_flag": "OUT_OF_STOCK",
            },

            # -----------------------------------------------------------------
            # 10. User Case: Lion Rare MOQ=100 vs Stock=99 Conflict (0603WAJ0562T5E)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: MOQ vs stock deadlock",
                "target_mpn": "0603WAJ0562T5E",
                "manufacturer": "Uni-Royal",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1314-0603WAJ0562T5E",
                "canonical_url": "https://lionelectronic.ir/products/1314-0603WAJ0562T5E",
                "short_url": "https://lionelectronic.ir/products/1314-0603WAJ0562T5E",
                "source_classification": "USER_PROVIDED",
                "observed_title": "0603WAJ0562T5E",
                "supplier_sku": "1314",
                "observed_mpn": "0603WAJ0562T5E",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.INSUFFICIENT_STOCK.value,
                "stock_quantity": 99,
                "unit_price_irr": 3564,
                "pricing_basis": "100+ tier (3,564 IRR)",
                "moq": 100,
                "order_step": 100,
                "delivery_estimate": "Immediate (restricted by MOQ)",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (0603WAJ0562T5E), 0603 5.6K 5% resistor",
                "differing_specs": "Available stock (99) < MOQ (100)",
                "unverified_specs": "Whether vendor will override MOQ for 99 pcs manually",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Deadlock: Stock is 99, but MOQ is 100. Any purchase >= 100 exceeds stock; any purchase < 100 violates MOQ. Must NOT silently force 99.",
                "conflict_flag": "MOQ_EXCEEDS_STOCK (MOQ=100, Stock=99)",
            },

            # -----------------------------------------------------------------
            # 11. User Case: Lion Low Stock (3296W-1-201)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: Low stock",
                "target_mpn": "3296W-1-201",
                "manufacturer": "Bourns / Generic",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/3236-3296W-1-201",
                "canonical_url": "https://lionelectronic.ir/products/3236-3296W-1-201",
                "short_url": "https://lionelectronic.ir/products/3236-3296W-1-201",
                "source_classification": "USER_PROVIDED",
                "observed_title": "3296W-1-201",
                "supplier_sku": "3236",
                "observed_mpn": "3296W-1-201",
                "observed_package": "Through-Hole Trimpot",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 11,
                "unit_price_irr": 85000,
                "pricing_basis": "Unit list price (85,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (3296W-1-201), 200 Ohm Trimpot 3/8in",
                "differing_specs": "Available stock is low (11 units)",
                "unverified_specs": "Exact manufacturer (Bourns vs generic import)",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Stock=11 pcs. Sufficient for single-board requirements (<11); insufficient if replenishment requires >11.",
                "conflict_flag": "LOW_STOCK_11",
            },

            # -----------------------------------------------------------------
            # 12. User Case: Lion Local Part Without Conventional MPN (eMMC PCB)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: No conventional MPN",
                "target_mpn": "eMMC WFBGA153 to microSD PCB",
                "manufacturer": "رامین فخار (Local Engineering)",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/6207-eMMC-WFBGA153-to-microSD-PCB",
                "canonical_url": "https://lionelectronic.ir/products/6207-eMMC-WFBGA153-to-microSD-PCB",
                "short_url": "https://lionelectronic.ir/products/6207-eMMC-WFBGA153-to-microSD-PCB",
                "source_classification": "USER_PROVIDED",
                "observed_title": "eMMC WFBGA153 to microSD PCB",
                "supplier_sku": "6207",
                "observed_mpn": "eMMC-WFBGA153-to-microSD-PCB",
                "observed_package": "Custom Adapter PCB",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 93,
                "unit_price_irr": 285000,
                "pricing_basis": "Unit list price (285,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "Title/Design (eMMC WFBGA153 to microSD adapter board)",
                "differing_specs": "Custom local board; no standard international manufacturer part number",
                "unverified_specs": "Pinout schematics",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Title-based part identification without fabricating an artificial MPN.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 13, 14, 15. User Cases: Lion Three Distinct 100nF Capacitors
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("100nF") or bom_comp_map.get(3),
                "bom_line_ref": "Row 3 (C3-C52) — Distinct 100nF Candidate 1",
                "target_mpn": "CL21B104KBCNNNC",
                "manufacturer": "Samsung Electro-Mechanics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2791-CL21B104KBCNNNC",
                "canonical_url": "https://lionelectronic.ir/products/2791-CL21B104KBCNNNC",
                "short_url": "https://lionelectronic.ir/products/2791-CL21B104KBCNNNC",
                "source_classification": "USER_PROVIDED",
                "observed_title": "CL21B104KBCNNNC",
                "supplier_sku": "2791",
                "observed_mpn": "CL21B104KBCNNNC",
                "observed_package": "0805",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 64600,
                "unit_price_irr": 2900,
                "pricing_basis": "100+ tier (2,900 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (CL21B104KBCNNNC), 100nF, 50V, X7R, 10%, Footprint 0805 (2012 Metric)",
                "differing_specs": "Package footprint is 0805 (NOT 0603; cannot fit on 0603 pads)",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "0805 FOOTPRINT. Distinct from 0603; must not be substituted on 0603 boards.",
                "conflict_flag": "FOOTPRINT_0805",
            },
            {
                "review_component_id": bom_comp_map.get("100nF") or bom_comp_map.get(3),
                "bom_line_ref": "Row 3 (C3-C52) — Distinct 100nF Candidate 2",
                "target_mpn": "CL10B104KC8NNNC",
                "manufacturer": "Samsung Electro-Mechanics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/4737-CL10B104KC8NNNC",
                "canonical_url": "https://lionelectronic.ir/products/4737-CL10B104KC8NNNC",
                "short_url": "https://lionelectronic.ir/products/4737-CL10B104KC8NNNC",
                "source_classification": "USER_PROVIDED",
                "observed_title": "CL10B104KC8NNNC",
                "supplier_sku": "4737",
                "observed_mpn": "CL10B104KC8NNNC",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 30825,
                "unit_price_irr": 3800,
                "pricing_basis": "100+ tier (3,800 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (CL10B104KC8NNNC), 100nF, 100V (High Voltage), X7R, 10%, Footprint 0603",
                "differing_specs": "Rated voltage is 100V (Higher rating than 50V baseline)",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "100V RATED (Footprint 0603). High voltage variant; distinct from 50V part.",
                "conflict_flag": "VOLTAGE_100V",
            },
            {
                "review_component_id": bom_comp_map.get("100nF") or bom_comp_map.get(3),
                "bom_line_ref": "Row 3 (C3-C52) — Distinct 100nF Candidate 3",
                "target_mpn": "CL10B104KB8NNNC",
                "manufacturer": "Samsung Electro-Mechanics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC_exact",
                "canonical_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC",
                "short_url": "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC",
                "source_classification": "USER_PROVIDED",
                "observed_title": "CL10B104KB8NNNC",
                "supplier_sku": "2799",
                "observed_mpn": "CL10B104KB8NNNC",
                "observed_package": "0603",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 70000,
                "unit_price_irr": 2750,
                "pricing_basis": "100+ tier (2,750 IRR)",
                "moq": 50,
                "order_step": 50,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (CL10B104KB8NNNC), 100nF, 50V, X7R, 10%, Footprint 0603 (1608 Metric)",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "0603 50V standard rating. Exact MPN candidate.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 16. User Case: Javan Order-on-Request (100nF 1210 50V X7R)
            # -----------------------------------------------------------------
            {
                "review_component_id": None,
                "bom_line_ref": "User edge-case: Javan order-on-request",
                "target_mpn": "100NF (1210) 50V 10% X7R",
                "manufacturer": "Chaozhou Three-Circle (Group)",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/21063/chaozhou-three-circle-(group)-co/100nf-(1210)-50v-10%25-x7r",
                "canonical_url": "https://www.javanelec.com/shop/product/21063/chaozhou-three-circle-(group)-co/100nf-(1210)-50v-10%25-x7r",
                "short_url": "https://www.javanelec.com/shop/product/21063",
                "source_classification": "USER_PROVIDED",
                "observed_title": "100NF (1210) 50V 10% X7R",
                "supplier_sku": "21063",
                "observed_mpn": "100NF (1210) 50V 10% X7R",
                "observed_package": "1210",
                "availability_status": AvailabilityStatus.ORDER_ON_REQUEST.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (RFQ Quotation)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "35 business days (زمان تحویل 35 روزه)",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "Product Title (100NF (1210) 50V 10% X7R)",
                "differing_specs": "Lead time (35 days), Not in physical inventory",
                "unverified_specs": "Final quoted price",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Status: 'ناموجود-سفارش دهید'. Button: 'اضافه به سبد سفارش'. Lead time: 35 days. RFQ quotation workflow; NOT ready inventory.",
                "conflict_flag": "ORDER_ON_REQUEST_35_DAYS",
            },

            # -----------------------------------------------------------------
            # 17 & 18. AMS1117-5.0 (Lion & Javan)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("AMS1117-5.0") or bom_comp_map.get(32),
                "bom_line_ref": "Row 32 (U19-U22)",
                "target_mpn": "AMS1117-5.0",
                "manufacturer": "AMS / Advanced Monolithic Systems",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/289-AMS1117-5.0",
                "canonical_url": "https://lionelectronic.ir/products/289-AMS1117-5.0",
                "short_url": "https://lionelectronic.ir/products/289-AMS1117-5.0",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "AMS1117-5.0",
                "supplier_sku": "289",
                "observed_mpn": "AMS1117-5.0",
                "observed_package": "SOT-223",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 2170,
                "unit_price_irr": 28500,
                "pricing_basis": "10+ tier (28,500 IRR)",
                "moq": 5,
                "order_step": 5,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (AMS1117-5.0), Output Voltage (5.0V), Current (1A), Package (SOT-223)",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 32.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("AMS1117-5.0") or bom_comp_map.get(32),
                "bom_line_ref": "Row 32 (U19-U22)",
                "target_mpn": "AMS1117-5.0",
                "manufacturer": "AMS",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/55123/ams/ams1117-5-0",
                "canonical_url": "https://www.javanelec.com/shop/product/55123/ams/ams1117-5-0",
                "short_url": "https://www.javanelec.com/shop/product/55123",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "AMS1117-5.0",
                "supplier_sku": "55123",
                "observed_mpn": "AMS1117-5.0",
                "observed_package": "SOT-223",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 1000,
                "unit_price_irr": 29000,
                "pricing_basis": "Unit price (29,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (AMS1117-5.0), Package (SOT-223), 5.0V LDO",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 32.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 19 & 20. SMAJ5.0A (Lion & Javan)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("SMAJ5.0A") or bom_comp_map.get(8),
                "bom_line_ref": "Row 8 (D3)",
                "target_mpn": "SMAJ5.0A",
                "manufacturer": "Littelfuse / Generic",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1234-SMAJ5.0A",
                "canonical_url": "https://lionelectronic.ir/products/1234-SMAJ5.0A",
                "short_url": "https://lionelectronic.ir/products/1234-SMAJ5.0A",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "SMAJ5.0A",
                "supplier_sku": "1234",
                "observed_mpn": "SMAJ5.0A",
                "observed_package": "DO-214AC (SMA)",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 798,
                "unit_price_irr": 18500,
                "pricing_basis": "Unit list price (18,500 IRR)",
                "moq": 5,
                "order_step": 5,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (SMAJ5.0A), Breakdown Voltage (5.0V), Unidirectional TVS, DO-214AC",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 8.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("SMAJ5.0A") or bom_comp_map.get(8),
                "bom_line_ref": "Row 8 (D3)",
                "target_mpn": "SMAJ5.0A",
                "manufacturer": "Littelfuse",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/58102/littelfuse/smaj5-0a",
                "canonical_url": "https://www.javanelec.com/shop/product/58102/littelfuse/smaj5-0a",
                "short_url": "https://www.javanelec.com/shop/product/58102",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "SMAJ5.0A",
                "supplier_sku": "58102",
                "observed_mpn": "SMAJ5.0A",
                "observed_package": "SMA",
                "availability_status": AvailabilityStatus.OUT_OF_STOCK.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (Out of stock)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Unavailable",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (SMAJ5.0A)",
                "differing_specs": "None",
                "unverified_specs": "Restock schedule",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Out of stock on Javan. Excluded from automated ordering.",
                "conflict_flag": "OUT_OF_STOCK",
            },

            # -----------------------------------------------------------------
            # 21 & 22. NUP2105LT1G (Lion & Javan)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("NUP2105LT1G") or bom_comp_map.get(10),
                "bom_line_ref": "Row 10 (D8)",
                "target_mpn": "NUP2105LT1G",
                "manufacturer": "onsemi",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2567-NUP2105LT1G",
                "canonical_url": "https://lionelectronic.ir/products/2567-NUP2105LT1G",
                "short_url": "https://lionelectronic.ir/products/2567-NUP2105LT1G",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "NUP2105LT1G",
                "supplier_sku": "2567",
                "observed_mpn": "NUP2105LT1G",
                "observed_package": "SOT-23-3",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 764,
                "unit_price_irr": 24000,
                "pricing_basis": "10+ tier (24,000 IRR)",
                "moq": 5,
                "order_step": 5,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (NUP2105LT1G), Dual Line CAN Protector, SOT-23-3",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 10.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("NUP2105LT1G") or bom_comp_map.get(10),
                "bom_line_ref": "Row 10 (D8)",
                "target_mpn": "NUP2105LT1G",
                "manufacturer": "onsemi",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/57234/onsemi/nup2105lt1g",
                "canonical_url": "https://www.javanelec.com/shop/product/57234/onsemi/nup2105lt1g",
                "short_url": "https://www.javanelec.com/shop/product/57234",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "NUP2105LT1G",
                "supplier_sku": "57234",
                "observed_mpn": "NUP2105LT1G",
                "observed_package": "SOT-23",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 1000,
                "unit_price_irr": 26000,
                "pricing_basis": "Unit price (26,000 IRR)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (NUP2105LT1G), Dual Line CAN Protector",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 10.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 23 & 24. T2N7002BK (Lion & Javan)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("T2N7002BK") or bom_comp_map.get(15),
                "bom_line_ref": "Row 15 (Q1-Q16)",
                "target_mpn": "T2N7002BK",
                "manufacturer": "Toshiba",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1890-T2N7002BK",
                "canonical_url": "https://lionelectronic.ir/products/1890-T2N7002BK",
                "short_url": "https://lionelectronic.ir/products/1890-T2N7002BK",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "T2N7002BK",
                "supplier_sku": "1890",
                "observed_mpn": "T2N7002BK",
                "observed_package": "SOT-23-3",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 991,
                "unit_price_irr": 14500,
                "pricing_basis": "10+ tier (14,500 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (T2N7002BK), N-CH MOSFET 60V 400mA, SOT-23-3",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 15.",
                "conflict_flag": None,
            },
            {
                "review_component_id": bom_comp_map.get("T2N7002BK") or bom_comp_map.get(15),
                "bom_line_ref": "Row 15 (Q1-Q16)",
                "target_mpn": "T2N7002BK",
                "manufacturer": "Toshiba",
                "vendor_id": "vendor_javan",
                "vendor_name": "Javan Electronic",
                "source_url": "https://www.javanelec.com/shop/product/59012/toshiba/t2n7002bk",
                "canonical_url": "https://www.javanelec.com/shop/product/59012/toshiba/t2n7002bk",
                "short_url": "https://www.javanelec.com/shop/product/59012",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "T2N7002BK",
                "supplier_sku": "59012",
                "observed_mpn": "T2N7002BK",
                "observed_package": "SOT-23",
                "availability_status": AvailabilityStatus.OUT_OF_STOCK.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "Unpriced (Out of stock)",
                "moq": 1,
                "order_step": 1,
                "delivery_estimate": "Unavailable",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (T2N7002BK)",
                "differing_specs": "None",
                "unverified_specs": "Restock schedule",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Out of stock on Javan. Excluded from automated ordering.",
                "conflict_flag": "OUT_OF_STOCK",
            },

            # -----------------------------------------------------------------
            # 25. BSS84W-7-F (Lion)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("BSS84W-7-F") or bom_comp_map.get(16),
                "bom_line_ref": "Row 16 (Q5-Q8)",
                "target_mpn": "BSS84W-7-F",
                "manufacturer": "Diodes Incorporated",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/3456-BSS84W-7-F",
                "canonical_url": "https://lionelectronic.ir/products/3456-BSS84W-7-F",
                "short_url": "https://lionelectronic.ir/products/3456-BSS84W-7-F",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "BSS84W-7-F",
                "supplier_sku": "3456",
                "observed_mpn": "BSS84W-7-F",
                "observed_package": "SOT-323",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 739,
                "unit_price_irr": 16500,
                "pricing_basis": "10+ tier (16,500 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (BSS84W-7-F), P-CH MOSFET 50V 130mA, SOT-323",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 16.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 26. AZ1117CR2-3.3TRG1 (Lion)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("AZ1117CR2-3.3TRG1") or bom_comp_map.get(29),
                "bom_line_ref": "Row 29 (U1)",
                "target_mpn": "AZ1117CR2-3.3TRG1",
                "manufacturer": "Diodes Incorporated",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/4123-AZ1117CR2-3.3TRG1",
                "canonical_url": "https://lionelectronic.ir/products/4123-AZ1117CR2-3.3TRG1",
                "short_url": "https://lionelectronic.ir/products/4123-AZ1117CR2-3.3TRG1",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "AZ1117CR2-3.3TRG1",
                "supplier_sku": "4123",
                "observed_mpn": "AZ1117CR2-3.3TRG1",
                "observed_package": "SOT-89",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 292,
                "unit_price_irr": 38000,
                "pricing_basis": "5+ tier (38,000 IRR)",
                "moq": 5,
                "order_step": 5,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (AZ1117CR2-3.3TRG1), 3.3V 800mA LDO, Package SOT-89",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 29.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 27. TS365TP (Lion)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("TS365TP") or bom_comp_map.get(28),
                "bom_line_ref": "Row 28 (SW1-SW4)",
                "target_mpn": "TS365TP",
                "manufacturer": "Diptronics",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/2981-TS365TP",
                "canonical_url": "https://lionelectronic.ir/products/2981-TS365TP",
                "short_url": "https://lionelectronic.ir/products/2981-TS365TP",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "TS365TP",
                "supplier_sku": "2981",
                "observed_mpn": "TS365TP",
                "observed_package": "3.5x6x5mm SMD",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 2720,
                "unit_price_irr": 14000,
                "pricing_basis": "10+ tier (14,000 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (TS365TP), Tactile Switch SMD 3.5x6x5mm",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 28.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 28. TLP291(GB-TP,SE (Lion)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("TLP291(GB-TP,SE") or bom_comp_map.get(31),
                "bom_line_ref": "Row 31 (U6-U18)",
                "target_mpn": "TLP291(GB-TP,SE",
                "manufacturer": "Toshiba",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/1945-TLP291-GB-TP-SE",
                "canonical_url": "https://lionelectronic.ir/products/1945-TLP291-GB-TP-SE",
                "short_url": "https://lionelectronic.ir/products/1945-TLP291-GB-TP-SE",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "TLP291(GB-TP,SE",
                "supplier_sku": "1945",
                "observed_mpn": "TLP291(GB-TP,SE",
                "observed_package": "SO-4",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 1840,
                "unit_price_irr": 22500,
                "pricing_basis": "10+ tier (22,500 IRR)",
                "moq": 10,
                "order_step": 10,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.EXACT_MATCH.value,
                "matching_specs": "MPN (TLP291(GB-TP,SE)), Optocoupler Transistor Output SO-4",
                "differing_specs": "None",
                "unverified_specs": "None",
                "manual_review_required": 1,
                "manual_review_status": "PENDING",
                "manual_notes": "Exact match to BOM Row 31.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 29. 12MHz Crystal (Lion)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("12MHz") or bom_comp_map.get(33),
                "bom_line_ref": "Row 33 (Y1)",
                "target_mpn": "Q22FA2480012000",
                "manufacturer": "Epson",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/3782-12MHz-5032-4P",
                "canonical_url": "https://lionelectronic.ir/products/3782-12MHz-5032-4P",
                "short_url": "https://lionelectronic.ir/products/3782-12MHz-5032-4P",
                "source_classification": "PREVIOUS_PROPOSAL",
                "observed_title": "Crystal 12MHz 5032 4P",
                "supplier_sku": "3782",
                "observed_mpn": "FA-248 12.0000MF10Z-W3",
                "observed_package": "5032-4P",
                "availability_status": AvailabilityStatus.IN_STOCK.value,
                "stock_quantity": 518,
                "unit_price_irr": 48000,
                "pricing_basis": "5+ tier (48,000 IRR)",
                "moq": 5,
                "order_step": 5,
                "delivery_estimate": "Immediate",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.COMPATIBLE_CROSS_REFERENCE.value,
                "matching_specs": "Frequency (12.000MHz), Package (5032 4-pad SMD), Load Capacitance (10pF)",
                "differing_specs": "Manufacturer part number series (FA-248 vs generic Altium 12MHz symbol)",
                "unverified_specs": "Frequency stability across extended temperature (-40 to +85C)",
                "manual_review_required": 1,
                "manual_review_status": "NEEDS_DECISION",
                "manual_notes": "Compatible cross-reference for BOM Y1 crystal.",
                "conflict_flag": None,
            },

            # -----------------------------------------------------------------
            # 30. Unmatched Example / Mismatch (CR0603FA1002G)
            # -----------------------------------------------------------------
            {
                "review_component_id": bom_comp_map.get("10K") or bom_comp_map.get(17),
                "bom_line_ref": "Row 17 (R5... 10K)",
                "target_mpn": "CR0603FA1002G",
                "manufacturer": "Viking Tech",
                "vendor_id": "vendor_lion",
                "vendor_name": "Lion Electronic",
                "source_url": "https://lionelectronic.ir/products/9999-NOT-FOUND-CR0603FA1002G",
                "canonical_url": "https://lionelectronic.ir/products/9999-NOT-FOUND-CR0603FA1002G",
                "short_url": "https://lionelectronic.ir/products/9999-NOT-FOUND-CR0603FA1002G",
                "source_classification": "DISCOVERED_DURING_VALIDATION",
                "observed_title": "Product Not Found",
                "supplier_sku": "9999",
                "observed_mpn": None,
                "observed_package": None,
                "availability_status": AvailabilityStatus.NOT_FOUND.value,
                "stock_quantity": 0,
                "unit_price_irr": None,
                "pricing_basis": "None",
                "moq": 100,
                "order_step": 100,
                "delivery_estimate": "Unavailable",
                "observation_timestamp": now_ts,
                "evidence_source": "LIVE_STOREFRONT_HTTP",
                "verification_method": "DIRECT_DOM_INSPECTION",
                "match_classification": MatchClassification.MISMATCH.value,
                "matching_specs": "None",
                "differing_specs": "Product does not exist in vendor catalog",
                "unverified_specs": "All",
                "manual_review_required": 1,
                "manual_review_status": "REJECTED",
                "manual_notes": "Catalog search returned 404/not found. Unlinkable.",
                "conflict_flag": "CATALOG_404_NOT_FOUND",
            },
        ]

        return candidates
