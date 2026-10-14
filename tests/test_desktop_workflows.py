"""
Omnix Automated Test Suite — Desktop UI Workflows & Multi-Candidate Preview
Governing GAPs:
- GAP-07: Multi-Candidate Comparison & Alternative Selection (OrderPreviewDialog)
- GAP-02: Direct MPN Quick Order Workflow (QuickOrderDialog - Tab 1)
- GAP-03: Direct Product URL Quick Order Workflow (QuickOrderDialog - Tab 2)
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QRadioButton

from core.models import CartMutationResult, OrderConstraints, ProductReference
from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    ManufacturerRule,
    ProcurementMode,
    ProcurementRequest,
    RequestProcurementResult,
    VendorProcurementCandidate,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry
from ui.dialogs.order_preview_dialog import OrderPreviewDialog, OrderWorkerThread
from ui.dialogs.quick_order_dialog import (
    CartStageWorker,
    MPNSearchWorker,
    QuickOrderDialog,
    URLInspectWorker,
    validate_vendor_pdp_url,
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a singleton QApplication instance exists for GUI tests in offscreen mode."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app


@pytest.fixture
def mock_registry():
    """Create a mock vendor registry with Lion, Javan, and RoboEq."""
    reg = MagicMock(spec=VendorRegistry)
    reg.enabled_vendor_ids = ["vendor_lion", "vendor_javan", "vendor_roboeq"]
    reg.is_vendor_enabled.side_effect = lambda v: v in reg.enabled_vendor_ids

    def _get_vendor_for_url(url, enabled_only=True):
        u = (url or "").lower()
        if "lionelectronic.ir" in u:
            vid = "vendor_lion"
        elif "javanelec.com" in u:
            vid = "vendor_javan"
        elif "roboeq.ir" in u:
            vid = "vendor_roboeq"
        else:
            return None
        if enabled_only and vid not in reg.enabled_vendor_ids:
            return None
        return vid

    reg.get_vendor_for_url.side_effect = _get_vendor_for_url

    default_adapter_ret = reg.get_adapter.return_value

    def _get_adapter(vid, *args, **kwargs):
        if reg.get_adapter.return_value is not default_adapter_ret:
            return reg.get_adapter.return_value
        return VendorRegistry.get_default_registry().get_adapter(vid)

    reg.get_adapter.side_effect = _get_adapter
    return reg



@pytest.fixture
def sample_candidate_offers():
    """Create a set of realistic multi-vendor candidate offers for testing comparison."""
    # Candidate 1: Lion NE555 (Eligible, 5000 IRR, MOQ 5, Step 1)
    cand_lion = VendorProcurementCandidate(
        vendor_id="vendor_lion",
        part_number="NE555P",
        product_ref=ProductReference(vendor_id="vendor_lion", vendor_sku="LION-555", pdp_url="https://lionelectronic.ir/products/2070-ne555p"),
        description="Precision Timer DIP-8",
        in_stock=True,
        stock_quantity=100,
        can_order=True,
        base_unit_price_irr=5000,
        order_constraints=OrderConstraints(moq_raw=5, packaging_step_raw=1),
        manufacturer="Texas Instruments",
        package="DIP-8",
        footprint="DIP-8",
    )
    eval_lion = CandidateEvaluation(
        candidate=cand_lion,
        required_quantity=3,
        effective_quantity=5,
        effective_unit_price_irr=5000,
        effective_total_price_irr=25000,
        is_eligible=True,
        state=EvaluationState.ELIGIBLE,
        rejection_reasons=[],
    )

    # Candidate 2: Javan NE555 (Eligible, 4500 IRR, MOQ 10, Step 10) - Cheaper unit price but higher MOQ
    cand_javan = VendorProcurementCandidate(
        vendor_id="vendor_javan",
        part_number="NE555P",
        product_ref=ProductReference(vendor_id="vendor_javan", vendor_sku="JAV-555", pdp_url="https://javanelec.com/shop/product/12345/ti/ne555p"),
        description="Standard Timer DIP-8",
        in_stock=True,
        stock_quantity=50,
        can_order=True,
        base_unit_price_irr=4500,
        order_constraints=OrderConstraints(moq_raw=10, packaging_step_raw=10),
        manufacturer="Texas Instruments",
        package="DIP-8",
        footprint="DIP-8",
    )
    eval_javan = CandidateEvaluation(
        candidate=cand_javan,
        required_quantity=3,
        effective_quantity=10,
        effective_unit_price_irr=4500,
        effective_total_price_irr=45000,
        is_eligible=True,
        state=EvaluationState.ELIGIBLE,
        rejection_reasons=[],
    )

    # Candidate 3: RoboEq NE555 Incompatible Package (SOP-8 instead of DIP-8) - Disqualified
    cand_roboeq = VendorProcurementCandidate(
        vendor_id="vendor_roboeq",
        part_number="NE555D",
        product_ref=ProductReference(vendor_id="vendor_roboeq", vendor_sku="ROBO-555", pdp_url="https://roboeq.ir/products/detail/0101001/ne555p-timer/"),
        description="SMD Timer SOP-8",
        in_stock=True,
        stock_quantity=200,
        can_order=True,
        base_unit_price_irr=3000,
        order_constraints=OrderConstraints(moq_raw=1, packaging_step_raw=1),
        manufacturer="STMicroelectronics",
        package="SOP-8",
        footprint="SOP-8",
    )
    eval_roboeq = CandidateEvaluation(
        candidate=cand_roboeq,
        required_quantity=3,
        effective_quantity=0,
        effective_unit_price_irr=3000,
        effective_total_price_irr=0,
        is_eligible=False,
        state=EvaluationState.INCOMPATIBLE_PACKAGE,
        rejection_reasons=["Package mismatch: expected 'DIP-8', found 'SOP-8'"],
    )

    return [cand_lion, cand_javan, cand_roboeq], [eval_lion, eval_javan, eval_roboeq]


# ==============================================================================
# SECTION 1: GAP-07 — Multi-Candidate Comparison & Alternative Selection Tests
# ==============================================================================

class TestGAP07MultiCandidateComparison:
    """Test suite for GAP-07 in OrderPreviewDialog."""

    def test_master_detail_structure_and_population(self, qapp, sample_candidate_offers):
        """Verify Master Table displays line items and selecting a row displays Detail Table offers."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        plan = BOMProcurementPlan(results=[result])

        dlg = OrderPreviewDialog(plan=plan)
        assert dlg.master_table.rowCount() == 1
        assert dlg.master_table.columnCount() == 9

        # Master table row 0 check
        assert dlg.master_table.item(0, 0).text() == "✅ READY"
        assert dlg.master_table.item(0, 2).text() == "NE555P"
        assert dlg.master_table.item(0, 3).text() == "Lion"
        assert dlg.master_table.item(0, 4).text() == "LION-555"
        assert dlg.master_table.item(0, 5).text() == "5"

        # Detail table populated
        dlg.master_table.selectRow(0)
        assert dlg.detail_table.rowCount() == 3
        assert dlg.detail_table.columnCount() == 12

        # Verify candidate vendor names in detail table
        assert dlg.detail_table.item(0, 1).text() == "Lion"
        assert dlg.detail_table.item(1, 1).text() == "Javan"
        assert dlg.detail_table.item(2, 1).text() == "Roboeq"

    def test_factual_candidate_rendering_no_heuristic_ranking(self, qapp, sample_candidate_offers):
        """Verify all candidate offers are rendered with raw factual parameters without heuristic scores."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))
        dlg.master_table.selectRow(0)

        # Candidate 0: Lion
        assert dlg.detail_table.item(0, 2).text() == "LION-555"
        assert dlg.detail_table.item(0, 3).text() == "NE555P"
        assert dlg.detail_table.item(0, 4).text() == "Texas Instruments"
        assert "DIP-8" in dlg.detail_table.item(0, 5).text()
        assert dlg.detail_table.item(0, 6).text() == "100"  # stock
        assert dlg.detail_table.item(0, 7).text() == "5"    # MOQ
        assert dlg.detail_table.item(0, 8).text() == "1"    # Step
        assert "5,000 IRR" in dlg.detail_table.item(0, 9).text()
        assert "25,000 IRR" in dlg.detail_table.item(0, 10).text()
        assert "SELECTED TARGET" in dlg.detail_table.item(0, 11).text()

        # Candidate 1: Javan
        assert dlg.detail_table.item(1, 2).text() == "JAV-555"
        assert dlg.detail_table.item(1, 6).text() == "50"
        assert dlg.detail_table.item(1, 7).text() == "10"
        assert dlg.detail_table.item(1, 8).text() == "10"
        assert "4,500 IRR" in dlg.detail_table.item(1, 9).text()
        assert "45,000 IRR" in dlg.detail_table.item(1, 10).text()
        assert "ELIGIBLE (Alternative)" in dlg.detail_table.item(1, 11).text()

        # Candidate 2: RoboEq (Incompatible Package)
        assert "SOP-8" in dlg.detail_table.item(2, 5).text()
        assert "REJECTED (INCOMPATIBLE_PACKAGE)" in dlg.detail_table.item(2, 11).text()

    def test_candidate_selection_override_and_cost_recalculation(self, qapp, sample_candidate_offers):
        """Selecting an eligible alternative candidate updates selected_evaluation, master table, and total cost."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))
        dlg.master_table.selectRow(0)

        # Initial total cost: Lion (25,000 IRR)
        assert "25,000 IRR" in dlg.lbl_total_cost.text()
        assert dlg.results[0].selected_evaluation == evaluations[0]

        # Override candidate: Select candidate 1 (Javan)
        dlg._on_candidate_radio_toggled(1, True)

        # Verify selection updated
        assert dlg.results[0].selected_evaluation == evaluations[1]
        assert dlg.master_table.item(0, 3).text() == "Javan"
        assert dlg.master_table.item(0, 4).text() == "JAV-555"
        assert dlg.master_table.item(0, 5).text() == "10"
        assert "45,000 IRR" in dlg.lbl_total_cost.text()

    def test_ineligible_candidate_radio_disabled(self, qapp, sample_candidate_offers):
        """Ineligible candidate cell widget has disabled radio button."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))
        dlg.master_table.selectRow(0)

        # Check radio button for candidate 2 (RoboEq - Incompatible Package)
        widget_box = dlg.detail_table.cellWidget(2, 0)
        radio = widget_box.findChild(QRadioButton)
        assert radio is not None
        assert radio.isEnabled() is False

    def test_ineligible_candidate_rejection_tooltip(self, qapp, sample_candidate_offers):
        """Disqualified candidate shows explicit rejection reason in tooltip."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))
        dlg.master_table.selectRow(0)

        status_item = dlg.detail_table.item(2, 11)
        assert "Package mismatch" in status_item.toolTip()

    def test_cheaper_incompatible_candidate_never_selected(self, qapp, sample_candidate_offers):
        """A cheaper candidate with an incompatible package is never selected over a valid candidate."""
        candidates, evaluations = sample_candidate_offers
        # Candidate 2 (RoboEq) is 3000 IRR (cheaper than Lion 5000 IRR and Javan 4500 IRR), but has SOP-8 package
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],  # Lion selected
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))

        # Ensure RoboEq is not selected
        assert dlg.results[0].selected_evaluation.candidate.vendor_id != "vendor_roboeq"
        assert dlg.results[0].selected_evaluation.is_eligible is True

    def test_unresolved_line_items_skipped_in_staging(self, qapp, sample_candidate_offers):
        """Unresolved line items without an eligible candidate are omitted from automated staging."""
        candidates, evaluations = sample_candidate_offers
        req_resolved = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        res_resolved = RequestProcurementResult(
            request=req_resolved,
            status="RESOLVED",
            candidates=[candidates[0]],
            evaluations=[evaluations[0]],
            selected_evaluation=evaluations[0],
        )

        req_unresolved = ProcurementRequest(part_number="UNKNOWN_CHIP", required_quantity=10)
        res_unresolved = RequestProcurementResult(
            request=req_unresolved,
            status="UNRESOLVED",
            candidates=[],
            evaluations=[],
            selected_evaluation=None,
            error_message="No candidates discovered",
        )

        mock_orchestrator = MagicMock(spec=UniversalProcurementOrchestrator)
        mock_orchestrator.stage_candidate.return_value = CartMutationResult(
            vendor_id="vendor_lion",
            vendor_sku="LION-555",
            requested_quantity=5,
            actual_quantity_staged=5,
            success=True,
            is_noop=False,
        )

        worker = OrderWorkerThread(
            results=[res_resolved, res_unresolved],
            orchestrator=mock_orchestrator,
        )

        captured_finished = []
        worker.finished_signal.connect(lambda d: captured_finished.append(d))
        worker.run()

        # Only 1 call to stage_candidate (for NE555P), none for UNKNOWN_CHIP
        assert mock_orchestrator.stage_candidate.call_count == 1
        assert captured_finished[0]["successful_count"] == 1
        assert captured_finished[0]["failed_count"] == 0

    def test_order_worker_thread_uses_selected_candidate_with_sync_cart(self, qapp, sample_candidate_offers):
        """OrderWorkerThread strictly passes the selected candidate and sync_cart=True to stage_candidate."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3, package="DIP-8")
        # User manually selected candidate 1 (Javan)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[1],
        )

        mock_orchestrator = MagicMock(spec=UniversalProcurementOrchestrator)
        mock_orchestrator.stage_candidate.return_value = CartMutationResult(
            vendor_id="vendor_javan",
            vendor_sku="JAV-555",
            requested_quantity=10,
            actual_quantity_staged=10,
            success=True,
            is_noop=False,
        )

        worker = OrderWorkerThread(
            results=[result],
            orchestrator=mock_orchestrator,
        )
        worker.run()

        mock_orchestrator.stage_candidate.assert_called_once_with(
            candidates[1], 10, sync_cart=True
        )

    def test_order_worker_thread_direct_items_routes_via_procurement_bridge(self, qapp):
        """OrderWorkerThread direct shortage execution unifies under ProcurementBridge."""
        items = [
            {
                "orig_row_idx": 1,
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/products/ne555p",
            },
            {
                "orig_row_idx": 2,
                "part_name": "LM358",
                "part_number": "LM358",
                "needed_qty": 10,
                "link": "https://javanelec.com/product/lm358",
            },
        ]

        expected_bridge_res = {
            "success": True,
            "message": "Batch staging completed: 2 succeeded, 0 failed.",
            "successful_count": 2,
            "failed_count": 0,
            "results": [
                {"part": "NE555P", "status": "SUCCESS", "qty": 5, "msg": "Added 5 pcs", "vendor_id": "vendor_lion"},
                {"part": "LM358", "status": "SUCCESS", "qty": 10, "msg": "Added 10 pcs", "vendor_id": "vendor_javan"},
            ],
            "items": items,
        }

        with patch("ui.dialogs.order_preview_dialog.ProcurementBridge.execute_staged_procurement_batch") as mock_bridge:
            def fake_bridge(items, progress_callback=None, registry=None, orchestrator=None):
                if progress_callback:
                    progress_callback(1, 2, "NE555P", 5, "Added 5 pcs")
                    progress_callback(2, 2, "LM358", 10, "Added 10 pcs")
                return expected_bridge_res

            mock_bridge.side_effect = fake_bridge

            worker = OrderWorkerThread(items=items)

            captured_progress = []
            captured_finished = []
            worker.progress_signal.connect(lambda c, t, p, q, m: captured_progress.append((c, t, p, q, m)))
            worker.finished_signal.connect(lambda d: captured_finished.append(d))

            worker.run()

            mock_bridge.assert_called_once()
            call_kwargs = mock_bridge.call_args[1]
            assert call_kwargs["items"] == items
            assert call_kwargs["registry"] == worker.registry
            assert call_kwargs["orchestrator"] == worker.orchestrator

            assert len(captured_progress) == 2
            assert captured_progress[0] == (1, 2, "NE555P", 5, "Added 5 pcs")
            assert captured_progress[1] == (2, 2, "LM358", 10, "Added 10 pcs")

            assert len(captured_finished) == 1
            assert captured_finished[0]["success"] is True
            assert captured_finished[0]["successful_count"] == 2

    def test_order_worker_thread_no_legacy_automator_imports(self):
        """Ensure order_preview_dialog has zero runtime import dependencies on LionAutomator or JavanAutomator."""
        import ui.dialogs.order_preview_dialog as opd
        assert not hasattr(opd, "LionAutomator")
        assert not hasattr(opd, "JavanAutomator")

    def test_order_worker_thread_direct_items_end_to_end_with_registry(self, qapp):
        """Verify full direct items execution through UniversalProcurementOrchestrator and registry."""
        from tests.test_procurement_bridge import MockTestAdapter
        MockTestAdapter.staged_calls.clear()

        reg = VendorRegistry()
        reg.register_adapter(
            vendor_id="vendor_mock",
            adapter_class=MockTestAdapter,
            display_name="Mock Store",
            domains=["mockstore.com"],
        )
        orch = UniversalProcurementOrchestrator(registry=reg)

        items = [
            {
                "orig_row_idx": 1,
                "part_name": "Part A",
                "part_number": "PART-A",
                "needed_qty": 7,
                "link": "https://mockstore.com/item-a",
            }
        ]

        worker = OrderWorkerThread(items=items, registry=reg, orchestrator=orch)
        finished_results = []
        progress_events = []
        worker.progress_signal.connect(lambda c, t, p, q, m: progress_events.append((c, t, p, q, m)))
        worker.finished_signal.connect(lambda d: finished_results.append(d))

        worker.run()

        assert len(finished_results) == 1
        assert finished_results[0]["success"] is True
        assert finished_results[0]["successful_count"] == 1
        assert finished_results[0]["failed_count"] == 0
        assert items[0]["order_success"] is True
        assert items[0]["actual_ordered_qty"] == 7
        assert len(MockTestAdapter.staged_calls) == 1

    def test_mode_a_progress_noop_satisfied_presentation(self, qapp):
        """No-op satisfied results display neutral 'No new quantity added' without checkmark or green styling."""
        shortages = [
            {
                "orig_row_idx": 1,
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/products/ne555p",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages)

        # 1. No-Op satisfied progress: displays neutral text without success checkmark, quantity, or green color
        dlg._on_mode_a_order_progress(1, 1, "NE555P", 0, "Already satisfied in cart (5/5 pcs)")
        status_item = dlg.table.item(0, 5)
        assert status_item is not None
        assert status_item.text() == "No new quantity added"
        assert "In Cart" not in status_item.text()
        assert "0 pcs" not in status_item.text()
        assert "✅" not in status_item.text()
        assert status_item.foreground().color().name() == "#94a3b8"

        # 2. Unrelated error containing the word 'satisfied' is NOT classified as a no-op
        dlg._on_mode_a_order_progress(1, 1, "NE555P", 0, "Failed: Constraints not satisfied")
        assert status_item.text().startswith("❌")
        assert status_item.text() != "No new quantity added"
        assert status_item.foreground().color().name() == "#f87171"

        # 3. Genuinely staged quantity progress: displays success checkmark and green color
        dlg._on_mode_a_order_progress(1, 1, "NE555P", 5, "Added 5 pcs to cart")
        assert status_item.text() == "✅ Added 5 pcs"
        assert status_item.foreground().color().name() == "#34d399"

    def test_mode_a_order_finished_guards_staging_results_log(self, qapp):
        """Mode A completion handler treats empty/missing results as None while preserving non-empty results."""
        shortages = [
            {
                "orig_row_idx": 1,
                "part_name": "NE555P",
                "part_number": "NE555P",
                "needed_qty": 5,
                "link": "https://lionelectronic.ir/products/ne555p",
            }
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages)

        # Empty result list -> None
        with patch.object(QMessageBox, "information"), patch("webbrowser.open"):
            dlg._on_mode_a_order_finished({"success": True, "successful_count": 0, "results": []})
            assert dlg.staging_results_log is None

        # Missing results key -> None
        with patch.object(QMessageBox, "information"), patch("webbrowser.open"):
            dlg._on_mode_a_order_finished({"success": True, "successful_count": 0})
            assert dlg.staging_results_log is None

        # Non-empty failed results -> preserved
        failed_results = [{"part": "NE555P", "status": "FAILED", "qty": 0, "msg": "Out of stock"}]
        with patch.object(QMessageBox, "warning"):
            dlg._on_mode_a_order_finished({"success": False, "message": "Failed", "results": failed_results})
            assert dlg.staging_results_log == failed_results

        # Non-empty successful results -> preserved
        success_results = [{"part": "NE555P", "status": "SUCCESS", "qty": 5, "msg": "Added 5 pcs"}]
        with patch.object(QMessageBox, "information"), patch("webbrowser.open"):
            dlg._on_mode_a_order_finished({"success": True, "successful_count": 1, "results": success_results})
            assert dlg.staging_results_log == success_results

    def test_open_shopping_cart_urls(self, qapp, sample_candidate_offers):
        """_open_shopping_cart opens browser tabs for active vendors of selected candidates."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],  # Lion
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))

        with patch("webbrowser.open") as mock_open:
            dlg._open_shopping_cart()
            mock_open.assert_called_once_with("https://lionelectronic.ir/orders/cart")

    def test_open_shopping_cart_urls_javan_authoritative(self, qapp, sample_candidate_offers):
        """_open_shopping_cart opens authoritative Javan cart URL (https://www.javanelec.com/shoppingcarts)."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[1],  # Javan candidate
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))

        with patch("webbrowser.open") as mock_open:
            dlg._open_shopping_cart()
            mock_open.assert_called_once_with("https://www.javanelec.com/shoppingcarts")

    def test_open_shopping_cart_urls_roboeq(self, qapp, sample_candidate_offers):
        """_open_shopping_cart opens RoboEq cart URL via adapter."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[2],  # RoboEq candidate
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))

        with patch("webbrowser.open") as mock_open:
            dlg._open_shopping_cart()
            mock_open.assert_called_once_with("https://roboeq.ir/cart/")

    def test_open_shopping_cart_urls_multi_vendor(self, qapp, sample_candidate_offers):
        """_open_shopping_cart opens multiple unique vendor cart URLs without duplicates."""
        candidates, evaluations = sample_candidate_offers
        r1 = RequestProcurementResult(
            request=ProcurementRequest(part_number="NE555P", required_quantity=3),
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],  # Lion
        )
        r2 = RequestProcurementResult(
            request=ProcurementRequest(part_number="LM358", required_quantity=5),
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[1],  # Javan
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[r1, r2]))

        with patch("webbrowser.open") as mock_open:
            dlg._open_shopping_cart()
            assert mock_open.call_count == 2
            opened_urls = [call.args[0] for call in mock_open.call_args_list]
            assert "https://lionelectronic.ir/orders/cart" in opened_urls
            assert "https://www.javanelec.com/shoppingcarts" in opened_urls

    def test_open_shopping_cart_mode_a_delegates_to_adapters(self, qapp):
        """Mode A shortage ordering resolves cart URLs via registry adapters."""
        shortages = [
            {"orig_row_idx": 1, "part_name": "NE555", "needed_qty": 5, "link": "https://lionelectronic.ir/products/2070-ne555p", "vendor_id": "vendor_lion"},
            {"orig_row_idx": 2, "part_name": "LM358", "needed_qty": 10, "link": "https://www.javanelec.com/shop/product/123", "vendor_id": "vendor_javan"},
        ]
        dlg = OrderPreviewDialog(all_shortages=shortages)

        with patch("webbrowser.open") as mock_open:
            dlg._open_shopping_cart()
            assert mock_open.call_count == 2
            opened_urls = [call.args[0] for call in mock_open.call_args_list]
            assert "https://lionelectronic.ir/orders/cart" in opened_urls
            assert "https://www.javanelec.com/shoppingcarts" in opened_urls

    def test_open_shopping_cart_unresolved_vendor_does_not_open_browser(self, qapp):
        """When vendor cannot be resolved, shopping cart opening does NOT navigate browser or guess a vendor."""
        shortages = [{"orig_row_idx": 1, "part_name": "UNKNOWN", "needed_qty": 1, "link": "https://broken-store.com/item"}]
        dlg = OrderPreviewDialog(all_shortages=shortages)

        with patch("webbrowser.open") as mock_open, patch.object(QMessageBox, "warning") as mock_warn:
            dlg._open_shopping_cart()
            mock_open.assert_not_called()
            mock_warn.assert_called_once()
            assert "Cart Unavailable" in mock_warn.call_args[0][1]

    def test_open_shopping_cart_adapter_failure_does_not_open_browser(self, qapp):
        """When adapter raises exception or cart URL is unavailable, do NOT navigate browser or fall back to Lion."""
        shortages = [{"orig_row_idx": 1, "part_name": "TEST", "needed_qty": 1, "link": "https://lionelectronic.ir/products/2070-ne555p", "vendor_id": "vendor_broken"}]
        mock_reg = MagicMock()
        mock_reg.get_vendor_for_url.return_value = "vendor_broken"
        mock_reg.get_adapter.side_effect = RuntimeError("Simulated adapter failure")
        dlg = OrderPreviewDialog(all_shortages=shortages, registry=mock_reg)

        with patch("webbrowser.open") as mock_open, patch.object(QMessageBox, "warning") as mock_warn:
            dlg._open_shopping_cart()
            mock_open.assert_not_called()
            mock_warn.assert_called_once()
            assert "Cart Unavailable" in mock_warn.call_args[0][1]


    def test_confirm_payment_and_add_stock(self, qapp, sample_candidate_offers):
        """Confirm payment prompts user and updates inventory stock via inventory_loader."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        mock_loader = MagicMock()
        mock_loader.batch_increment_stock.return_value = (1, "Success")
        callback_mock = MagicMock()

        dlg = OrderPreviewDialog(
            plan=BOMProcurementPlan(results=[result]),
            inventory_loader=mock_loader,
            on_stock_updated=callback_mock,
        )

        dlg._has_updated_inventory = False

        def _mock_clicked(self_mb):
            for b in self_mb.buttons():
                if "Yes" in b.text():
                    return b
            return None

        with patch.object(QMessageBox, "exec"), \
             patch.object(QMessageBox, "clickedButton", _mock_clicked), \
             patch.object(QMessageBox, "information"):
            dlg._confirm_payment_and_add_stock()

        assert mock_loader.batch_increment_stock.called
        assert dlg._has_updated_inventory is True
        assert callback_mock.called

    def test_master_and_detail_double_click_opens_pdp_url(self, qapp, sample_candidate_offers):
        """Double clicking a master row or detail row opens the candidate's canonical PDP URL."""
        candidates, evaluations = sample_candidate_offers
        req = ProcurementRequest(part_number="NE555P", required_quantity=3)
        result = RequestProcurementResult(
            request=req,
            status="RESOLVED",
            candidates=candidates,
            evaluations=evaluations,
            selected_evaluation=evaluations[0],
        )
        dlg = OrderPreviewDialog(plan=BOMProcurementPlan(results=[result]))
        dlg.master_table.selectRow(0)

        with patch("webbrowser.open") as mock_open:
            item = dlg.master_table.item(0, 2)
            dlg._on_master_table_double_clicked(item)
            mock_open.assert_called_once_with("https://lionelectronic.ir/products/2070-ne555p")

        with patch("webbrowser.open") as mock_open:
            d_item = dlg.detail_table.item(1, 2)
            dlg._on_detail_table_double_clicked(d_item)
            mock_open.assert_called_once_with("https://javanelec.com/shop/product/12345/ti/ne555p")


# ==============================================================================
# SECTION 2: GAP-02 — Direct MPN Quick Order Workflow Tests
# ==============================================================================

class TestGAP02DirectMPNQuickOrder:
    """Test suite for Direct MPN Quick Order in QuickOrderDialog."""

    def test_direct_mpn_ui_inputs_and_defaults(self, qapp, mock_registry):
        """Verify Direct MPN tab has all required inputs with correct defaults."""
        dlg = QuickOrderDialog(registry=mock_registry)
        assert dlg.tabs.count() == 2
        assert dlg.tabs.tabText(0) == "🔍 Direct MPN Sourcing (GAP-02)"

        assert dlg.mpn_input.text() == ""
        assert dlg.mpn_qty_stepper.value() == 1
        assert dlg.mpn_brand_rule_combo.currentText() == "ANY (Generic Allowed)"
        assert dlg.mpn_vendor_combo.currentText() == "🌐 All Enabled Vendors"
        assert dlg.btn_mpn_stage.isEnabled() is False

    def test_direct_mpn_empty_input_validation(self, qapp, mock_registry):
        """Empty or blank MPN input triggers validation warning without starting worker."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.mpn_input.setText("   ")

        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg._on_mpn_search_clicked()
            assert mock_warn.called
            assert "Part Number Required" in mock_warn.call_args[0][1]
            assert dlg.mpn_worker is None

    def test_direct_mpn_never_falls_back_to_comment(self, qapp, mock_registry):
        """Direct MPN workflow strictly preserves MPN as required parameter without Comment fallback."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.mpn_input.setText("STM32F103C8T6")
        dlg.mpn_qty_stepper.setValue(10)

        with patch.object(MPNSearchWorker, "start"):
            dlg._on_mpn_search_clicked()
            assert dlg.mpn_worker is not None
            req = dlg.mpn_worker.request
            assert req.part_number == "STM32F103C8T6"
            assert req.required_quantity == 10
            assert req.mode == ProcurementMode.DIRECT_BOM

    def test_direct_mpn_brand_rule_exact(self, qapp, mock_registry):
        """Direct MPN sourcing with EXACT brand rule sets exact manufacturer."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.mpn_input.setText("NE555P")
        dlg.mpn_brand_rule_combo.setCurrentIndex(1)  # EXACT
        dlg.mpn_brand_input.setText("Texas Instruments")

        with patch.object(MPNSearchWorker, "start"):
            dlg._on_mpn_search_clicked()
            req = dlg.mpn_worker.request
            assert req.is_manufacturer_any is False
            assert req.manufacturer == "Texas Instruments"

    def test_direct_mpn_brand_rule_approved_list(self, qapp, mock_registry):
        """Direct MPN sourcing with APPROVED_LIST rule parses comma-separated allowed manufacturers."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.mpn_input.setText("LM358N")
        dlg.mpn_brand_rule_combo.setCurrentIndex(2)  # APPROVED_LIST
        dlg.mpn_brand_input.setText("TI, STMicroelectronics, ON Semi")

        with patch.object(MPNSearchWorker, "start"):
            dlg._on_mpn_search_clicked()
            req = dlg.mpn_worker.request
            assert req.is_manufacturer_any is False
            assert req.allowed_manufacturers == ["TI", "STMicroelectronics", "ON Semi"]

    def test_direct_mpn_vendor_filtering(self, qapp, mock_registry):
        """Direct MPN sourcing targeting a specific vendor passes vendor_ids filter."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.mpn_input.setText("NE555P")
        dlg.mpn_vendor_combo.setCurrentIndex(1)  # Lion

        with patch.object(MPNSearchWorker, "start"):
            dlg._on_mpn_search_clicked()
            assert dlg.mpn_worker.vendor_ids == ["vendor_lion"]

    def test_direct_mpn_candidate_table_rendering(self, qapp, mock_registry, sample_candidate_offers):
        """Discovered candidates are rendered in MPN candidate table with correct data and selection."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)

        dlg._on_mpn_search_results(candidates, evaluations)

        assert dlg.mpn_table.rowCount() == 3
        assert dlg.mpn_table.columnCount() == 12

        # Check Lion row
        assert dlg.mpn_table.item(0, 1).text() == "Lion"
        assert dlg.mpn_table.item(0, 2).text() == "LION-555"
        assert dlg.mpn_table.item(0, 6).text() == "100"
        assert "5,000 IRR" in dlg.mpn_table.item(0, 9).text()

        # Check RoboEq row (ineligible)
        assert "REJECTED (INCOMPATIBLE_PACKAGE)" in dlg.mpn_table.item(2, 11).text()

    def test_direct_mpn_candidate_selection_enables_stage_button(self, qapp, mock_registry, sample_candidate_offers):
        """Selecting an eligible candidate enables the Stage Cart button with candidate details."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg._on_mpn_search_results(candidates, evaluations)

        # Select candidate 0 (Lion)
        dlg._on_mpn_radio_toggled(0, True)

        assert dlg.selected_mpn_eval_idx == 0
        assert dlg.btn_mpn_stage.isEnabled() is True

    def test_direct_mpn_ineligible_candidate_disabled(self, qapp, mock_registry, sample_candidate_offers):
        """Ineligible candidate radio button is disabled in Direct MPN table."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg._on_mpn_search_results(candidates, evaluations)

        widget_box = dlg.mpn_table.cellWidget(2, 0)
        radio = widget_box.findChild(QRadioButton)
        assert radio.isEnabled() is False

    def test_direct_mpn_effective_quantity_moq_step_application(self, qapp, mock_registry, sample_candidate_offers):
        """Direct MPN candidate evaluation properly applies MOQ and packaging step rules."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg._on_mpn_search_results(candidates, evaluations)

        # Candidate 0 (Lion): MOQ 5, Step 1 -> Effective Qty = 5
        assert evaluations[0].effective_quantity == 5
        assert evaluations[0].effective_total_price_irr == 25000

        # Candidate 1 (Javan): MOQ 10, Step 10 -> Effective Qty = 10
        assert evaluations[1].effective_quantity == 10
        assert evaluations[1].effective_total_price_irr == 45000

    def test_direct_mpn_cart_staging_invokes_stage_candidate_with_sync_cart(self, qapp, mock_registry, sample_candidate_offers):
        """Staging selected MPN candidate invokes orchestrator.stage_candidate with sync_cart=True."""
        candidates, evaluations = sample_candidate_offers
        mock_orch = MagicMock(spec=UniversalProcurementOrchestrator)
        mock_orch.stage_candidate.return_value = CartMutationResult(
            vendor_id="vendor_lion",
            vendor_sku="LION-555",
            requested_quantity=5,
            actual_quantity_staged=5,
            success=True,
            is_noop=False,
            raw_vendor_message="Item successfully added to cart.",
        )

        dlg = QuickOrderDialog(registry=mock_registry, orchestrator=mock_orch)
        dlg._on_mpn_search_results(candidates, evaluations)
        dlg._on_mpn_radio_toggled(0, True)

        with patch.object(CartStageWorker, "start"):
            dlg._on_mpn_stage_clicked()
            assert dlg.stage_worker is not None
            assert dlg.stage_worker.candidate == candidates[0]
            assert dlg.stage_worker.quantity == 5

    def test_direct_mpn_zero_candidates_found(self, qapp, mock_registry):
        """When no candidates are found, candidate table is empty and stage button is disabled."""
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg._on_mpn_search_results([], [])
        assert dlg.mpn_table.rowCount() == 0
        assert dlg.btn_mpn_stage.isEnabled() is False
        assert "No products found" in dlg.status_msg_lbl.text()



# ==============================================================================
# SECTION 3: GAP-03 — Direct Product URL Quick Order Workflow Tests
# ==============================================================================

class TestGAP03DirectURLQuickOrder:
    """Test suite for Direct Product URL Quick Order in QuickOrderDialog."""

    def test_validate_vendor_pdp_url_valid_lion(self, mock_registry):
        """Valid Lion Electronic PDP URLs pass validation."""
        valid, vid, err = validate_vendor_pdp_url(
            "https://lionelectronic.ir/products/2070-ne555p", registry=mock_registry
        )
        assert valid is True
        assert vid == "vendor_lion"
        assert err is None

    def test_validate_vendor_pdp_url_valid_javan(self, mock_registry):
        """Valid Javan Electronic PDP URLs pass validation."""
        valid, vid, err = validate_vendor_pdp_url(
            "https://javanelec.com/shop/product/12345/ti/lm358", registry=mock_registry
        )
        assert valid is True
        assert vid == "vendor_javan"
        assert err is None

    def test_validate_vendor_pdp_url_valid_roboeq(self, mock_registry):
        """Valid RoboEq PDP URLs pass validation."""
        valid, vid, err = validate_vendor_pdp_url(
            "https://roboeq.ir/products/detail/0101001/ne555p-timer/", registry=mock_registry
        )
        assert valid is True
        assert vid == "vendor_roboeq"
        assert err is None

    def test_validate_vendor_pdp_url_non_pdp_urls_rejected(self, mock_registry):
        """Non-PDP URLs (home, cart, search, category) on vendor domains are rejected."""
        non_pdp_urls = [
            "https://lionelectronic.ir/",
            "https://lionelectronic.ir/orders/cart",
            "https://lionelectronic.ir/search?q=stm32",
            "https://javanelec.com/cart",
            "https://javanelec.com/category/semiconductors",
            "https://roboeq.ir/cart",
            "https://roboeq.ir/search/",
        ]
        for url in non_pdp_urls:
            valid, vid, err = validate_vendor_pdp_url(url, registry=mock_registry)
            assert valid is False
            assert "not a recognized Product Detail Page (PDP)" in err

    def test_validate_vendor_pdp_url_unsupported_domain_rejected(self, mock_registry):
        """Unrecognized domains are rejected."""
        valid, vid, err = validate_vendor_pdp_url(
            "https://www.digikey.com/product-detail/en/texas-instruments/NE555P/296-1411-5-ND",
            registry=mock_registry,
        )
        assert valid is False
        assert vid is None
        assert "not recognized as a registered vendor" in err

    def test_validate_vendor_pdp_url_empty_or_none(self, mock_registry):
        """Empty or blank URLs fail validation."""
        valid, vid, err = validate_vendor_pdp_url("", registry=mock_registry)
        assert valid is False
        assert "required and cannot be empty" in err

    def test_validate_vendor_pdp_url_disabled_vendor_rejected(self):
        """URLs for disabled vendors are rejected with a message to enable in Settings."""
        reg = MagicMock(spec=VendorRegistry)
        reg.enabled_vendor_ids = ["vendor_javan"]
        reg.is_vendor_enabled.side_effect = lambda v: v in reg.enabled_vendor_ids
        reg.get_vendor_for_url.side_effect = lambda u, enabled_only=True: "vendor_lion" if "lion" in u else None

        valid, vid, err = validate_vendor_pdp_url(
            "https://lionelectronic.ir/products/2070-ne555p", registry=reg
        )
        assert valid is False
        assert vid == "vendor_lion"
        assert "currently disabled in Settings" in err

    def test_validate_vendor_pdp_url_adapter_unavailable_fails_closed(self):
        """When vendor adapter is unavailable or registry raises, validation fails closed."""
        reg = MagicMock(spec=VendorRegistry)
        reg.is_vendor_enabled.return_value = True
        reg.get_vendor_for_url.return_value = "vendor_lion"
        reg.get_adapter.side_effect = RuntimeError("Adapter not installed")

        valid, vid, err = validate_vendor_pdp_url(
            "https://lionelectronic.ir/products/2070-ne555p", registry=reg
        )
        assert valid is False
        assert vid == "vendor_lion"
        assert "unavailable" in err.lower()

    def test_validate_vendor_pdp_url_missing_capability_fails_closed(self):
        """When vendor adapter lacks is_pdp_url method, validation fails closed."""
        reg = MagicMock(spec=VendorRegistry)
        reg.is_vendor_enabled.return_value = True
        reg.get_vendor_for_url.return_value = "vendor_lion"
        mock_adapter = object()  # No is_pdp_url attribute
        reg.get_adapter.return_value = mock_adapter

        valid, vid, err = validate_vendor_pdp_url(
            "https://lionelectronic.ir/products/2070-ne555p", registry=reg
        )
        assert valid is False
        assert vid == "vendor_lion"
        assert "does not support url validation" in err.lower()

    def test_validate_vendor_pdp_url_adapter_exception_fails_closed(self):
        """When adapter.is_pdp_url raises an exception, validation fails closed."""
        reg = MagicMock(spec=VendorRegistry)
        reg.is_vendor_enabled.return_value = True
        reg.get_vendor_for_url.return_value = "vendor_lion"
        mock_adapter = MagicMock()
        mock_adapter.is_pdp_url.side_effect = ValueError("Malformed regex")
        reg.get_adapter.return_value = mock_adapter

        valid, vid, err = validate_vendor_pdp_url(
            "https://lionelectronic.ir/products/2070-ne555p", registry=reg
        )
        assert valid is False
        assert vid == "vendor_lion"
        assert "error during url validation" in err.lower()

    def test_direct_url_inspect_worker_execution(self, qapp, mock_registry):
        """URLInspectWorker resolves product, stock, and constraints and constructs candidate."""
        mock_adapter = MagicMock()
        mock_pref = ProductReference(vendor_id="vendor_lion", vendor_sku="LION-555", pdp_url="https://lionelectronic.ir/products/2070-ne555p")
        mock_adapter.resolve_product.return_value = mock_pref

        mock_details = MagicMock()
        mock_details.mpn = "NE555P"
        mock_details.can_order = True
        mock_details.price_irr = 5000
        mock_details.package_raw = "DIP-8"
        mock_details.manufacturer = "Texas Instruments"
        mock_details.raw_status_text = "In Stock"
        mock_details.specs = {"package": "DIP-8"}
        mock_details.dimensions = {}
        mock_details.order_constraints = OrderConstraints(moq_raw=5, packaging_step_raw=1)
        mock_adapter.inspect_product.return_value = mock_details

        mock_stock = MagicMock()
        mock_stock.in_stock = True
        mock_stock.stock_quantity = 100
        mock_adapter.inspect_stock.return_value = mock_stock
        mock_adapter.determine_order_constraints.return_value = OrderConstraints(moq_raw=5, packaging_step_raw=1)

        mock_registry.get_adapter.return_value = mock_adapter

        worker = URLInspectWorker(
            url="https://lionelectronic.ir/products/2070-ne555p",
            quantity=3,
            vendor_id="vendor_lion",
            registry=mock_registry,
        )

        captured = []
        worker.result_signal.connect(lambda c, e: captured.append((c, e)))
        worker.run()

        assert len(captured) == 1
        cand, ev = captured[0]
        assert cand.vendor_id == "vendor_lion"
        assert cand.part_number == "NE555P"
        assert cand.in_stock is True
        assert cand.stock_quantity == 100
        assert ev.is_eligible is True
        assert ev.effective_quantity == 5  # MOQ 5 applied
        assert ev.effective_total_price_irr == 25000

    def test_direct_url_summary_card_rendering(self, qapp, mock_registry, sample_candidate_offers):
        """Direct URL tab renders inspected product summary table accurately."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.tabs.setCurrentIndex(1)

        dlg._on_url_inspect_result(candidates[0], evaluations[0])

        assert dlg.url_details_table.rowCount() == 11
        assert dlg.btn_url_stage.isEnabled() is True

        # Check rendered values
        found_attrs = {}
        for r in range(dlg.url_details_table.rowCount()):
            k = dlg.url_details_table.item(r, 0).text()
            v = dlg.url_details_table.item(r, 1).text()
            found_attrs[k] = v

        assert found_attrs["Vendor"] == "Lion"
        assert found_attrs["Vendor SKU"] == "LION-555"
        assert found_attrs["Part Number / MPN"] == "NE555P"
        assert found_attrs["Manufacturer / Brand"] == "Texas Instruments"
        assert "100 units in stock" in found_attrs["Stock Availability"]
        assert "5,000 IRR" in found_attrs["Unit Price"]
        assert "25,000 IRR" in found_attrs["Total Cost"]
        assert "✅ ELIGIBLE" in found_attrs["Status & Eligibility"]

    def test_direct_url_cart_staging_integration(self, qapp, mock_registry, sample_candidate_offers):
        """Staging direct URL product triggers CartStageWorker with candidate and effective quantity."""
        candidates, evaluations = sample_candidate_offers
        mock_orch = MagicMock(spec=UniversalProcurementOrchestrator)

        dlg = QuickOrderDialog(registry=mock_registry, orchestrator=mock_orch)
        dlg.tabs.setCurrentIndex(1)
        dlg._on_url_inspect_result(candidates[0], evaluations[0])

        with patch.object(CartStageWorker, "start"):
            dlg._on_url_stage_clicked()
            assert dlg.stage_worker is not None
            assert dlg.stage_worker.candidate == candidates[0]
            assert dlg.stage_worker.quantity == 5

    def test_direct_url_ineligible_product_stage_disabled(self, qapp, mock_registry, sample_candidate_offers):
        """When inspected URL product is ineligible, stage button is disabled and status shows rejection."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.tabs.setCurrentIndex(1)

        # Pass ineligible candidate 2 (RoboEq SOP-8)
        dlg._on_url_inspect_result(candidates[2], evaluations[2])

        assert dlg.btn_url_stage.isEnabled() is False
        assert "cannot be ordered" in dlg.status_msg_lbl.text()

    def test_quick_order_no_vendor_selectors_imported(self):
        """Verify QuickOrderDialog does not import or couple to vendor-specific Selectors."""
        import ui.dialogs.quick_order_dialog as qod
        assert not hasattr(qod, "LionSelectors"), "LionSelectors should not be imported in quick_order_dialog"
        assert not hasattr(qod, "JavanSelectors"), "JavanSelectors should not be imported in quick_order_dialog"
        assert not hasattr(qod, "RoboEqSelectors"), "RoboEqSelectors should not be imported in quick_order_dialog"

    def test_quick_order_open_cart_delegates_to_adapter_javan(self, qapp, mock_registry, sample_candidate_offers):
        """QuickOrderDialog._on_open_cart_clicked opens authoritative Javan cart URL via adapter."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.tabs.setCurrentIndex(0)
        dlg.mpn_candidates = candidates
        dlg.mpn_evaluations = evaluations
        dlg.selected_mpn_eval_idx = 1  # Javan candidate

        with patch("webbrowser.open") as mock_open:
            dlg._on_open_cart_clicked()
            mock_open.assert_called_once_with("https://www.javanelec.com/shoppingcarts")

    def test_quick_order_open_cart_delegates_to_adapter_url_tab(self, qapp, mock_registry, sample_candidate_offers):
        """QuickOrderDialog._on_open_cart_clicked in URL tab delegates to adapter."""
        candidates, evaluations = sample_candidate_offers
        dlg = QuickOrderDialog(registry=mock_registry)
        dlg.tabs.setCurrentIndex(1)
        dlg.url_candidate = candidates[2]  # RoboEq candidate

        with patch("webbrowser.open") as mock_open:
            dlg._on_open_cart_clicked()
            mock_open.assert_called_once_with("https://roboeq.ir/cart/")

    def test_quick_order_open_cart_unresolved_vendor_does_not_open_browser(self, qapp, mock_registry):
        """When vendor is None or unresolved, QuickOrderDialog does NOT open browser or fall back to Lion."""
        dlg = QuickOrderDialog(registry=mock_registry)

        with patch("webbrowser.open") as mock_open, patch.object(QMessageBox, "warning") as mock_warn:
            dlg._open_vendor_cart(None)
            mock_open.assert_not_called()
            mock_warn.assert_called_once()
            assert "Vendor Cart Unavailable" in mock_warn.call_args[0][1]

    def test_quick_order_open_cart_adapter_failure_does_not_open_browser(self, qapp):
        """When adapter retrieval or cart URL fails, QuickOrderDialog does NOT open browser or fall back."""
        mock_reg = MagicMock()
        mock_reg.get_adapter.side_effect = RuntimeError("Adapter crashed")
        dlg = QuickOrderDialog(registry=mock_reg)

        with patch("webbrowser.open") as mock_open, patch.object(QMessageBox, "warning") as mock_warn:
            dlg._open_vendor_cart("vendor_broken")
            mock_open.assert_not_called()
            mock_warn.assert_called_once()
            assert "Vendor Cart Unavailable" in mock_warn.call_args[0][1]

    def test_quick_order_open_cart_invalid_or_empty_url_does_not_open_browser(self, qapp):
        """When adapter returns None or non-URL, QuickOrderDialog does NOT open browser."""
        mock_adapter = MagicMock()
        mock_adapter.get_cart_url.return_value = ""  # empty URL
        mock_reg = MagicMock()
        mock_reg.get_adapter.return_value = mock_adapter
        mock_reg.get_vendor_name.return_value = "Test Vendor"
        dlg = QuickOrderDialog(registry=mock_reg)

        with patch("webbrowser.open") as mock_open, patch.object(QMessageBox, "warning") as mock_warn:
            dlg._open_vendor_cart("vendor_test")
            mock_open.assert_not_called()
            mock_warn.assert_called_once()
            assert "Vendor Cart Unavailable" in mock_warn.call_args[0][1]


