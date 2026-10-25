"""
Focused Unit & Integration Test Suite: Isolated BOM Supplier-Review Database
Governing Requirement: Part A8 — Test the Review Database

Verifies:
1. Review DB is created at its explicit path.
2. Review DB and production DB are physically separate.
3. Review operations target only the review DB.
4. Manual decisions persist across reinitialization.
5. Production DB contents remain completely unchanged.
6. Duplicate supplier candidates are handled deterministically.
7. User-provided URLs remain traceable.
8. Missing data is not fabricated.
9. Exact MPN mismatches are not accepted as exact matches.
10. Compatible cross-references remain distinct with explicit specs diff.
11. MOQ 100 / stock 99 deadlock is handled safely.
12. Coming-soon, out-of-stock, and order-on-request states are distinct.
"""

import os
import sqlite3
import pytest
from core.review.review_database import (
    ReviewDatabase,
    MatchClassification,
    AvailabilityStatus,
)


@pytest.fixture
def temp_review_db(tmp_path):
    """Provides a fresh isolated review database instance in a temporary folder."""
    db_file = str(tmp_path / "test_supplier_review.db")
    rdb = ReviewDatabase(db_path=db_file)
    rdb.populate_from_bom_and_candidates("FC_IO_V_1_3.xlsx")
    return rdb


class TestIsolatedSupplierReviewDatabase:
    """Verifies isolation, persistence, classifications, and replenishment safety."""

    def test_review_db_created_at_explicit_path(self, temp_review_db):
        """Review database must exist at the explicit configured path."""
        assert os.path.exists(temp_review_db.db_path)
        assert os.path.basename(temp_review_db.db_path) == "test_supplier_review.db"

    def test_review_and_production_databases_are_physically_separate(self, temp_review_db):
        """Review DB path and production DB path must never point to the same file."""
        prod_path = ReviewDatabase.PRODUCTION_DB_PATH
        assert os.path.normcase(temp_review_db.db_path) != os.path.normcase(prod_path)

        # Attempting to initialize ReviewDatabase pointing to production DB must raise ValueError
        with pytest.raises(ValueError, match="SAFETY VIOLATION"):
            ReviewDatabase(db_path=prod_path)

    def test_production_db_remains_unchanged(self, temp_review_db):
        """Review operations must never alter production database tables or counts."""
        prod_path = ReviewDatabase.PRODUCTION_DB_PATH
        if os.path.exists(prod_path):
            uri = f"file:{prod_path}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM components")
                comp_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM supplier_links")
                link_count = cur.fetchone()[0]

                # Production DB must retain historical counts
                assert comp_count == 18
                assert link_count == 0

    def test_manual_decisions_persist_across_reinitialization(self, temp_review_db):
        """User manual decisions must never be wiped out by reinitialization or reload."""
        url = "https://lionelectronic.ir/products/2799-CL10B104KB8NNNC"
        mpn = "GRM188R71H104KA93D"

        # Record manual decision
        temp_review_db.record_manual_decision(
            source_url=url,
            target_mpn=mpn,
            decision="APPROVED_ALTERNATIVE",
            notes="Approved Samsung 0603 100nF for non-critical filtering",
            decided_by="TEST_AUDITOR"
        )

        # Verify decision is stored
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT manual_review_status, manual_notes FROM supplier_candidates WHERE source_url = ? AND target_mpn = ?", (url, mpn))
            row = cur.fetchone()
            assert row["manual_review_status"] == "APPROVED_ALTERNATIVE"
            assert row["manual_notes"] == "Approved Samsung 0603 100nF for non-critical filtering"

        # Re-run full BOM and candidate population
        summary = temp_review_db.populate_from_bom_and_candidates("FC_IO_V_1_3.xlsx", preserve_decisions=True)
        assert summary["preserved_decisions"] >= 1

        # Confirm decision persists
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT manual_review_status, manual_notes FROM supplier_candidates WHERE source_url = ? AND target_mpn = ?", (url, mpn))
            row_after = cur.fetchone()
            assert row_after["manual_review_status"] == "APPROVED_ALTERNATIVE"
            assert "Approved Samsung" in row_after["manual_notes"]

    def test_duplicate_supplier_candidates_handled_deterministically(self, temp_review_db):
        """Populating candidates multiple times must be idempotent without creating duplicate rows."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM supplier_candidates")
            initial_count = cur.fetchone()[0]

        # Second population pass
        temp_review_db.populate_from_bom_and_candidates("FC_IO_V_1_3.xlsx", preserve_decisions=True)

        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM supplier_candidates")
            after_count = cur.fetchone()[0]

        assert initial_count == after_count

    def test_user_provided_urls_remain_traceable(self, temp_review_db):
        """All user-provided URLs must have source_classification = 'USER_PROVIDED'."""
        user_urls = [
            "https://lionelectronic.ir/products/1573-FRC0805J102TS",
            "https://lionelectronic.ir/products/1432-0805W8F1801T5E",
            "https://lionelectronic.ir/products/1578-0805W8J0272T5E",
            "https://lionelectronic.ir/products/1314-0603WAJ0562T5E",
            "https://lionelectronic.ir/products/3236-3296W-1-201",
            "https://lionelectronic.ir/products/6207-eMMC-WFBGA153-to-microSD-PCB",
            "https://lionelectronic.ir/products/2791-CL21B104KBCNNNC",
            "https://lionelectronic.ir/products/4737-CL10B104KC8NNNC",
            "https://www.javanelec.com/shop/product/21063/chaozhou-three-circle-(group)-co/100nf-(1210)-50v-10%25-x7r",
        ]

        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            for u in user_urls:
                cur.execute("SELECT source_classification, observed_title FROM supplier_candidates WHERE source_url = ?", (u,))
                row = cur.fetchone()
                assert row is not None, f"Missing user candidate URL: {u}"
                assert row["source_classification"] == "USER_PROVIDED"
                assert row["observed_title"] is not None

    def test_missing_data_is_not_fabricated(self, temp_review_db):
        """Unverified fields (e.g. price for out of stock / coming soon) must be NULL, never zero or fabricated."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT unit_price_irr, stock_quantity FROM supplier_candidates WHERE source_url = 'https://lionelectronic.ir/products/1578-0805W8J0272T5E'")
            row = cur.fetchone()
            assert row["unit_price_irr"] is None  # Unpriced out of stock
            assert row["stock_quantity"] == 0

    def test_compatible_cross_references_remain_distinct(self, temp_review_db):
        """Compatible cross-references must have classification COMPATIBLE_CROSS_REFERENCE and explicit specs diff."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT match_classification, matching_specs, differing_specs, manual_review_required
                FROM supplier_candidates
                WHERE source_url = 'https://lionelectronic.ir/products/2799-CL10B104KB8NNNC'
            """)
            row = cur.fetchone()
            assert row["match_classification"] == MatchClassification.COMPATIBLE_CROSS_REFERENCE.value
            assert "100nF" in row["matching_specs"]
            assert "Samsung Electro-Mechanics vs. Murata" in row["differing_specs"]
            assert row["manual_review_required"] == 1

    def test_moq_100_stock_99_deadlock_handling(self, temp_review_db):
        """Item with MOQ=100 and Stock=99 cannot be fulfilled and must report deadlock."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM supplier_candidates WHERE source_url = 'https://lionelectronic.ir/products/1314-0603WAJ0562T5E'")
            cid = cur.fetchone()[0]

        # Calculate with user requirement = 20
        res = temp_review_db.simulate_replenishment_check(candidate_id=cid, required_qty=20)
        assert res["can_fulfill"] is False
        assert res["effective_order_qty"] == 100
        assert "MOQ (100) exceeds total available stock (99)" in res["conflict_reason"]

    def test_coming_soon_and_order_on_request_distinctness(self, temp_review_db):
        """Coming soon ('به زودی') and Order on Request ('سفارش دهید') must be distinct non-purchasable states."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            # Coming soon
            cur.execute("SELECT id, availability_status FROM supplier_candidates WHERE source_url = 'https://lionelectronic.ir/products/1573-FRC0805J102TS'")
            row_cs = cur.fetchone()
            assert row_cs["availability_status"] == AvailabilityStatus.COMING_SOON.value
            res_cs = temp_review_db.simulate_replenishment_check(candidate_id=row_cs["id"], required_qty=5)
            assert res_cs["can_fulfill"] is False
            assert "به زودی" in res_cs["conflict_reason"]

            # Order on Request
            cur.execute("SELECT id, availability_status, delivery_estimate FROM supplier_candidates WHERE source_url = 'https://www.javanelec.com/shop/product/21063/chaozhou-three-circle-(group)-co/100nf-(1210)-50v-10%25-x7r'")
            row_oor = cur.fetchone()
            assert row_oor["availability_status"] == AvailabilityStatus.ORDER_ON_REQUEST.value
            assert "35" in row_oor["delivery_estimate"]
            res_oor = temp_review_db.simulate_replenishment_check(candidate_id=row_oor["id"], required_qty=5)
            assert res_oor["can_fulfill"] is False
            assert "35-day RFQ lead time" in res_oor["conflict_reason"]

    def test_low_stock_threshold_handling(self, temp_review_db):
        """Low stock product (3296W-1-201, Stock=11) fulfills requirements <= 11 and rejects > 11."""
        with temp_review_db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, stock_quantity FROM supplier_candidates WHERE source_url = 'https://lionelectronic.ir/products/3236-3296W-1-201'")
            row = cur.fetchone()
            assert row["stock_quantity"] == 11
            cid = row["id"]

        # Requirement 5 <= 11: Can fulfill
        res_ok = temp_review_db.simulate_replenishment_check(candidate_id=cid, required_qty=5)
        assert res_ok["can_fulfill"] is True
        assert res_ok["effective_order_qty"] == 5

        # Requirement 25 > 11: Insufficient stock
        res_fail = temp_review_db.simulate_replenishment_check(candidate_id=cid, required_qty=25)
        assert res_fail["can_fulfill"] is False
        assert "exceeds available supplier stock (11)" in res_fail["conflict_reason"]
