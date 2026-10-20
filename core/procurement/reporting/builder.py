"""
Omnix Core — Deterministic Procurement Report Builder (GAP-18)
Pure functional builder that transforms a BOMProcurementPlan and optional staging actuals
into a normalized ProcurementReportData instance. Zero state mutation.
"""

import datetime
from typing import Any, Dict, List, Optional

from core.procurement.models import (
    BOMProcurementPlan,
    CandidateEvaluation,
    EvaluationState,
    ProcurementMode,
    RequestProcurementResult,
    VendorProcurementCandidate,
)
from core.procurement.reporting.models import (
    CandidateLifecycleState,
    ProcurementReportData,
    ReportCandidateRecord,
    ReportLineItem,
    ReportType,
    VendorSummary,
)


def _format_vendor_name(vendor_id: str) -> str:
    """Format canonical vendor ID into display name."""
    if not vendor_id:
        return "—"
    v_clean = vendor_id.replace("vendor_", "").title()
    if v_clean == "Lion":
        return "Lion Electronic"
    if v_clean == "Javan":
        return "Javan Electronic"
    if v_clean == "Roboeq":
        return "RoboEq"
    return v_clean


class ProcurementReportBuilder:
    """
    Constructs a ProcurementReportData snapshot with strictly deterministic ordering
    and factual qualification states.
    """

    @staticmethod
    def build(
        plan: BOMProcurementPlan,
        staging_results: Optional[List[Dict[str, Any]]] = None,
        source_title: str = "Procurement Order Report",
        source_file: str = "",
        procurement_mode: Optional[ProcurementMode] = None,
        board_multiplier: int = 1,
        enabled_vendors: Optional[List[str]] = None,
        report_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ProcurementReportData:
        """
        Pure function converting BOMProcurementPlan into ProcurementReportData.
        
        Guarantees:
        1. Line items are ordered deterministically by 1-based index (1..N).
        2. Discovered candidates per line item are ordered deterministically:
           - Selected candidate first
           - Other eligible candidates (alphabetical by vendor_id, SKU, MPN)
           - Ineligible candidates (alphabetical by vendor_id, SKU, MPN)
        3. Vendor summaries are ordered alphabetically by vendor_id.
        4. No state mutation on the input plan.
        """
        is_post_staging = bool(staging_results is not None)
        rep_type = ReportType.POST_STAGING_FINAL if is_post_staging else ReportType.PRE_ORDER_CONFIRMATION
        now_iso = created_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        r_id = report_id or f"REP-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Determine effective mode
        if procurement_mode is not None:
            eff_mode = procurement_mode if isinstance(procurement_mode, ProcurementMode) else ProcurementMode(procurement_mode)
        else:
            # Infer from first request or default to DATABASE_AWARE
            first_req_mode = plan.results[0].request.mode if plan.results else ProcurementMode.DATABASE_AWARE
            eff_mode = first_req_mode if isinstance(first_req_mode, ProcurementMode) else ProcurementMode(first_req_mode)

        # Index staging results if provided (key by part_number or index)
        staging_map: Dict[str, Dict[str, Any]] = {}
        if staging_results:
            for item in staging_results:
                p_key = (item.get("part") or item.get("part_number") or "").strip().upper()
                if p_key:
                    staging_map[p_key] = item

        line_items: List[ReportLineItem] = []
        vendor_accum: Dict[str, Dict[str, Any]] = {}
        total_estimated_cost = 0
        total_actual_staged_cost = 0
        total_warnings = 0
        resolved_count = 0
        unresolved_count = 0

        # Deterministic line item iteration (order in plan.results)
        for idx, res in enumerate(plan.results, start=1):
            req = res.request
            sel = res.selected_evaluation
            meta = req.metadata or {}

            # Raw quantities
            bom_raw_demand = meta.get("bom_raw_demand")
            if bom_raw_demand is None:
                bom_raw_demand = req.required_quantity
            db_stock = meta.get("db_stock_qty") or 0 if eff_mode == ProcurementMode.DATABASE_AWARE else 0
            shortage_qty = meta.get("shortage_qty") or req.required_quantity

            # Target orderable quantity (with A3 MOQ/step quantizations)
            target_order_qty = sel.effective_quantity if sel else req.required_quantity

            # Collect line-item warnings
            item_warnings: List[str] = []
            if req.required_specs:
                for k, v in req.required_specs.items():
                    item_warnings.append(f"Required spec constraint: {k}={v}")
            if req.required_dimensions:
                for k, v in req.required_dimensions.items():
                    item_warnings.append(f"Required dimension constraint: {k}={v}")

            # Collect and sort candidate audit records deterministically
            candidate_records: List[ReportCandidateRecord] = []
            for ev in res.evaluations:
                cand = ev.candidate
                is_this_selected = (sel is not None and sel == ev)
                cand_v_id = cand.vendor_id or "unknown"
                cand_v_name = _format_vendor_name(cand_v_id)
                cand_sku = cand.product_ref.vendor_sku if cand.product_ref else ""
                cand_url = cand.product_ref.pdp_url if cand.product_ref else ""

                # Tier pricing summary
                tier_summary = ""
                if cand.price_tiers:
                    tier_parts = [f"≥{t.min_quantity}: {t.unit_price_irr:,} IRR" for t in cand.price_tiers]
                    tier_summary = " | ".join(tier_parts)

                # Qualification state
                if is_this_selected:
                    q_state = CandidateLifecycleState.SELECTED_BY_USER.value
                elif ev.is_eligible:
                    q_state = CandidateLifecycleState.ELIGIBLE.value
                else:
                    q_state = ev.state.value if isinstance(ev.state, EvaluationState) else str(ev.state)

                if ev.unknown_parameters:
                    for unk in ev.unknown_parameters:
                        item_warnings.append(f"Candidate {cand_sku or cand.part_number}: Unverified parameter '{unk}'")

                c_rec = ReportCandidateRecord(
                    vendor_id=cand_v_id,
                    vendor_name=cand_v_name,
                    vendor_sku=cand_sku,
                    pdp_url=cand_url,
                    mpn=cand.part_number,
                    manufacturer=cand.manufacturer or "",
                    package=cand.package or "",
                    footprint=cand.footprint or "",
                    in_stock=cand.in_stock,
                    stock_quantity=cand.stock_quantity,
                    moq=cand.order_constraints.moq_raw or 1,
                    packaging_step=cand.order_constraints.packaging_step_raw or 1,
                    unit_price_irr=ev.effective_unit_price_irr,
                    total_price_irr=ev.effective_total_price_irr,
                    price_tiers_summary=tier_summary,
                    is_eligible=ev.is_eligible,
                    is_selected=is_this_selected,
                    is_actually_staged=False,
                    qualification_state=q_state,
                    rejection_reasons=list(ev.rejection_reasons),
                    unknown_parameters=list(ev.unknown_parameters),
                )
                candidate_records.append(c_rec)

            # Deterministic sorting of candidate audit records
            def _cand_sort_key(c: ReportCandidateRecord):
                # Priority 1: Selected (0 for selected, 1 for unselected)
                p1 = 0 if c.is_selected else 1
                # Priority 2: Eligible (0 for eligible, 1 for ineligible)
                p2 = 0 if c.is_eligible else 1
                return (p1, p2, c.vendor_id.lower(), c.vendor_sku.lower(), c.mpn.lower())

            candidate_records.sort(key=_cand_sort_key)

            # Line Item Status & Staging Info
            p_key = req.part_number.strip().upper()
            stage_info = staging_map.get(p_key)

            staged_qty: Optional[int] = None
            existing_cart_qty: Optional[int] = None
            delta_qty: Optional[int] = None
            final_cart_qty: Optional[int] = None
            is_noop = False
            vendor_msg = ""
            staging_status = "PENDING_CONFIRMATION"

            if sel and sel.is_eligible:
                resolved_count += 1
                status_str = "READY"
                v_id = sel.candidate.vendor_id
                v_name = _format_vendor_name(v_id)
                sku_str = sel.candidate.product_ref.vendor_sku if sel.candidate.product_ref else ""
                url_str = sel.candidate.product_ref.pdp_url if sel.candidate.product_ref else ""
                u_price = sel.effective_unit_price_irr
                t_price = sel.effective_total_price_irr
                moq_val = sel.candidate.order_constraints.moq_raw or 1
                step_val = sel.candidate.order_constraints.packaging_step_raw or 1

                if t_price:
                    total_estimated_cost += t_price

                # Post-staging actuals
                if stage_info:
                    st_status = stage_info.get("status", "")
                    staged_qty = stage_info.get("qty", 0)
                    is_noop = bool(stage_info.get("is_noop", False))
                    vendor_msg = stage_info.get("msg", "")

                    if st_status == "SUCCESS":
                        if is_noop:
                            staging_status = "NO_OP_SATISFIED"
                            status_str = "NO_OP_SATISFIED"
                        else:
                            staging_status = "STAGED"
                            status_str = "STAGED"
                        if t_price:
                            total_actual_staged_cost += t_price
                    else:
                        staging_status = "FAILED"
                        status_str = "FAILED"
                        item_warnings.append(f"Staging failed: {vendor_msg}")

                    # Mark candidate actually staged
                    for c in candidate_records:
                        if c.is_selected and staging_status in ("STAGED", "NO_OP_SATISFIED"):
                            c.is_actually_staged = True

                # Aggregate Vendor Summary
                if v_id not in vendor_accum:
                    vendor_accum[v_id] = {
                        "vendor_name": v_name,
                        "item_count": 0,
                        "total_pieces": 0,
                        "subtotal_cost_irr": 0,
                        "actual_staged_pieces": 0,
                        "success_count": 0,
                        "fail_count": 0,
                        "error_message": "",
                    }
                vendor_accum[v_id]["item_count"] += 1
                vendor_accum[v_id]["total_pieces"] += target_order_qty
                if t_price:
                    vendor_accum[v_id]["subtotal_cost_irr"] += t_price
                if staged_qty is not None:
                    vendor_accum[v_id]["actual_staged_pieces"] += staged_qty
                    if staging_status in ("STAGED", "NO_OP_SATISFIED"):
                        vendor_accum[v_id]["success_count"] += 1
                    else:
                        vendor_accum[v_id]["fail_count"] += 1
                        vendor_accum[v_id]["error_message"] = vendor_msg

            else:
                unresolved_count += 1
                status_str = "UNRESOLVED"
                v_id = None
                v_name = "—"
                sku_str = "—"
                url_str = ""
                u_price = None
                t_price = None
                moq_val = 1
                step_val = 1
                staging_status = "UNRESOLVED"
                if res.error_message:
                    item_warnings.append(res.error_message)

            total_warnings += len(item_warnings)

            line_item = ReportLineItem(
                line_number=idx,
                designator=str(meta.get("designator") or req.source or "—"),
                part_number=req.part_number,
                description=str(req.description or meta.get("comment") or ""),
                package=str(req.package or meta.get("package") or ""),
                footprint=str(req.footprint or meta.get("footprint") or ""),
                manufacturer=str(req.manufacturer or meta.get("manufacturer") or meta.get("brand") or ""),
                bom_demand_qty=bom_raw_demand,
                db_stock_qty=db_stock,
                shortage_qty=shortage_qty,
                target_order_qty=target_order_qty,
                existing_cart_qty=existing_cart_qty,
                delta_qty=delta_qty,
                actual_quantity_staged=staged_qty,
                final_cart_qty=final_cart_qty,
                is_noop=is_noop,
                status=status_str,
                selected_vendor_id=v_id,
                selected_vendor_name=v_name,
                selected_sku=sku_str,
                pdp_url=url_str,
                unit_price_irr=u_price,
                total_price_irr=t_price,
                moq=moq_val,
                packaging_step=step_val,
                candidate_count=len(res.candidates),
                candidates=candidate_records,
                warnings=item_warnings,
                staging_status=staging_status,
                vendor_response_message=vendor_msg,
            )
            line_items.append(line_item)

        # Build deterministically sorted Vendor Summaries (by vendor_id)
        vendor_summaries: List[VendorSummary] = []
        for v_id in sorted(vendor_accum.keys()):
            v_data = vendor_accum[v_id]
            s_count = v_data["success_count"]
            f_count = v_data["fail_count"]
            tot_i = v_data["item_count"]

            if not is_post_staging:
                v_st_status = "PENDING"
            elif f_count == 0 and s_count > 0:
                v_st_status = "SUCCESS"
            elif f_count > 0 and s_count > 0:
                v_st_status = "PARTIAL"
            elif f_count > 0:
                v_st_status = "FAILED"
            else:
                v_st_status = "SUCCESS"

            v_summary = VendorSummary(
                vendor_id=v_id,
                vendor_name=v_data["vendor_name"],
                item_count=v_data["item_count"],
                total_pieces=v_data["total_pieces"],
                subtotal_cost_irr=v_data["subtotal_cost_irr"],
                actual_staged_pieces=v_data["actual_staged_pieces"],
                staging_status=v_st_status,
                error_message=v_data["error_message"],
            )
            vendor_summaries.append(v_summary)

        return ProcurementReportData(
            report_id=r_id,
            report_title=source_title,
            report_type=rep_type,
            created_at=now_iso,
            procurement_mode=eff_mode,
            source_file=source_file or (source_title.replace("Procurement Order Preview — ", "")),
            board_multiplier=board_multiplier,
            currency="IRR",
            enabled_vendors=enabled_vendors or sorted(vendor_accum.keys()),
            line_items=line_items,
            vendor_summaries=vendor_summaries,
            total_line_items=len(line_items),
            resolved_line_items=resolved_count,
            unresolved_line_items=unresolved_count,
            total_estimated_cost_irr=total_estimated_cost,
            total_actual_staged_cost_irr=total_actual_staged_cost,
            total_warnings_count=total_warnings,
        )

    @staticmethod
    def build_from_shortages(
        shortages: List[Dict[str, Any]],
        staging_results: Optional[List[Dict[str, Any]]] = None,
        source_title: str = "Procurement Order Report",
        source_file: str = "",
        procurement_mode: Optional[ProcurementMode] = ProcurementMode.DATABASE_AWARE,
        board_multiplier: int = 1,
        enabled_vendors: Optional[List[str]] = None,
        report_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ProcurementReportData:
        """
        Pure function converting Mode A shortages / confirmation items into a deterministic ProcurementReportData.
        """
        is_post_staging = bool(staging_results is not None)
        rep_type = ReportType.POST_STAGING_FINAL if is_post_staging else ReportType.PRE_ORDER_CONFIRMATION
        now_iso = created_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        r_id = report_id or f"REP-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        eff_mode = procurement_mode if isinstance(procurement_mode, ProcurementMode) else ProcurementMode.DATABASE_AWARE

        # Index staging results if provided (key by part_number, designator, part_name)
        staging_map: Dict[str, Dict[str, Any]] = {}
        if staging_results:
            for item in staging_results:
                for k in ("part", "part_number", "part_name", "designator"):
                    val = str(item.get(k) or "").strip().upper()
                    if val and val not in staging_map:
                        staging_map[val] = item

        line_items: List[ReportLineItem] = []
        vendor_accum: Dict[str, Dict[str, Any]] = {}
        total_estimated_cost = 0
        total_actual_staged_cost = 0
        total_warnings = 0
        resolved_count = 0
        unresolved_count = 0

        for idx, it in enumerate(shortages, start=1):
            des = str(it.get("designator") or f"Item {idx}")
            pn = str(it.get("part_number") or it.get("part_name") or it.get("comment") or it.get("description") or f"Part_{idx}")
            desc = str(it.get("description") or it.get("comment") or "")
            pkg = str(it.get("package") or it.get("footprint") or "")
            footprint = str(it.get("footprint") or "")
            mfr = str(it.get("manufacturer") or it.get("brand") or "")
            bom_demand = int(it.get("total_needed") or it.get("total_needed_qty") or it.get("unit_qty") or 1)
            
            raw_stock = it.get("in_stock")
            if raw_stock is None:
                raw_stock = it.get("current_stock")
            if raw_stock is None:
                raw_stock = it.get("db_stock_qty")
            if raw_stock is None:
                raw_stock = it.get("stock_qty")
            if raw_stock is None:
                raw_stock = it.get("stock")
            db_stock = int(raw_stock) if (raw_stock is not None and str(raw_stock).isdigit()) else 0

            raw_shortage = it.get("shortage")
            if raw_shortage is None:
                raw_shortage = it.get("shortage_qty")
            if raw_shortage is None:
                raw_shortage = it.get("needed_qty")
            shortage_qty = int(raw_shortage) if (raw_shortage is not None and str(raw_shortage).isdigit()) else 1

            raw_target = it.get("needed_qty")
            if raw_target is None:
                raw_target = shortage_qty
            target_order_qty = int(raw_target) if (raw_target is not None and str(raw_target).isdigit()) else shortage_qty

            link = str(it.get("link", "")).strip()
            vid = it.get("vendor_id")
            if not vid and link:
                try:
                    from core.procurement.registry import VendorRegistry
                    vid = VendorRegistry.get_default_registry().get_vendor_for_url(link)
                except Exception:
                    vid = None

            if vid:
                v_name = _format_vendor_name(vid)
            else:
                v_name = "—"

            is_valid_link = bool(link and link.startswith("http"))
            is_registered_vendor = bool(vid)

            item_warnings: List[str] = []
            if not link:
                item_warnings.append("Store link is missing in database (Inventory.xlsx)")
            elif not is_registered_vendor:
                item_warnings.append(f"Store link domain is not a registered vendor: {link}")

            # Match staging result
            stage_info = (
                staging_map.get(pn.strip().upper())
                or staging_map.get(des.strip().upper())
                or staging_map.get(str(it.get("part_name", "")).strip().upper())
            )

            staged_qty: Optional[int] = None
            is_noop = False
            vendor_msg = ""
            staging_status = "PENDING_CONFIRMATION"

            if is_valid_link and (is_registered_vendor or is_lion):
                resolved_count += 1
                status_str = "READY"
            else:
                unresolved_count += 1
                status_str = "UNRESOLVED"
                staging_status = "UNRESOLVED"

            if stage_info:
                st_status = stage_info.get("status", "")
                staged_qty = stage_info.get("qty", 0)
                is_noop = bool(stage_info.get("is_noop", False))
                vendor_msg = stage_info.get("msg", "")

                if st_status == "SUCCESS":
                    if is_noop:
                        staging_status = "NO_OP_SATISFIED"
                        status_str = "NO_OP_SATISFIED"
                    else:
                        staging_status = "STAGED"
                        status_str = "STAGED"
                else:
                    staging_status = "FAILED"
                    status_str = "FAILED"
                    item_warnings.append(f"Staging failed: {vendor_msg}")

            # Vendor aggregation
            if vid:
                if vid not in vendor_accum:
                    vendor_accum[vid] = {
                        "vendor_name": v_name,
                        "item_count": 0,
                        "total_pieces": 0,
                        "subtotal_cost_irr": 0,
                        "actual_staged_pieces": 0,
                        "success_count": 0,
                        "fail_count": 0,
                        "error_message": "",
                    }
                vendor_accum[vid]["item_count"] += 1
                vendor_accum[vid]["total_pieces"] += target_order_qty
                if staged_qty is not None:
                    vendor_accum[vid]["actual_staged_pieces"] += staged_qty
                    if staging_status in ("STAGED", "NO_OP_SATISFIED"):
                        vendor_accum[vid]["success_count"] += 1
                    else:
                        vendor_accum[vid]["fail_count"] += 1
                        vendor_accum[vid]["error_message"] = vendor_msg

            total_warnings += len(item_warnings)

            cand_record = ReportCandidateRecord(
                vendor_id=vid or "unknown",
                vendor_name=v_name,
                vendor_sku=pn,
                pdp_url=link,
                mpn=pn,
                manufacturer=mfr,
                package=pkg,
                footprint=footprint,
                in_stock=True,
                stock_quantity=1000,
                moq=1,
                packaging_step=1,
                is_eligible=bool(is_registered_vendor and is_valid_link),
                is_selected=True,
                is_actually_staged=(staging_status in ("STAGED", "NO_OP_SATISFIED")),
                qualification_state=CandidateLifecycleState.SELECTED_BY_USER.value if (is_registered_vendor and is_valid_link) else CandidateLifecycleState.REJECTED.value,
                rejection_reasons=item_warnings if not (is_registered_vendor and is_valid_link) else [],
            )

            line_item = ReportLineItem(
                line_number=idx,
                designator=des,
                part_number=pn,
                description=desc,
                package=pkg,
                footprint=footprint,
                manufacturer=mfr,
                bom_demand_qty=bom_demand,
                db_stock_qty=db_stock,
                shortage_qty=shortage_qty,
                target_order_qty=target_order_qty,
                actual_quantity_staged=staged_qty,
                is_noop=is_noop,
                status=status_str,
                selected_vendor_id=vid,
                selected_vendor_name=v_name,
                selected_sku=pn,
                pdp_url=link,
                moq=1,
                packaging_step=1,
                candidate_count=1 if link else 0,
                candidates=[cand_record] if link else [],
                warnings=item_warnings,
                staging_status=staging_status,
                vendor_response_message=vendor_msg,
            )
            line_items.append(line_item)

        # Build deterministically sorted Vendor Summaries (by vendor_id)
        vendor_summaries: List[VendorSummary] = []
        for v_id in sorted(vendor_accum.keys()):
            v_data = vendor_accum[v_id]
            s_count = v_data["success_count"]
            f_count = v_data["fail_count"]

            if not is_post_staging:
                v_st_status = "PENDING"
            elif f_count == 0 and s_count > 0:
                v_st_status = "SUCCESS"
            elif f_count > 0 and s_count > 0:
                v_st_status = "PARTIAL"
            elif f_count > 0:
                v_st_status = "FAILED"
            else:
                v_st_status = "SUCCESS"

            v_summary = VendorSummary(
                vendor_id=v_id,
                vendor_name=v_data["vendor_name"],
                item_count=v_data["item_count"],
                total_pieces=v_data["total_pieces"],
                subtotal_cost_irr=v_data["subtotal_cost_irr"],
                actual_staged_pieces=v_data["actual_staged_pieces"],
                staging_status=v_st_status,
                error_message=v_data["error_message"],
            )
            vendor_summaries.append(v_summary)

        return ProcurementReportData(
            report_id=r_id,
            report_title=source_title,
            report_type=rep_type,
            created_at=now_iso,
            procurement_mode=eff_mode,
            source_file=source_file or (source_title.replace("Procurement Order Confirmation — ", "").replace("Procurement Order Preview — ", "")),
            board_multiplier=board_multiplier,
            currency="IRR",
            enabled_vendors=enabled_vendors or sorted(vendor_accum.keys()),
            line_items=line_items,
            vendor_summaries=vendor_summaries,
            total_line_items=len(line_items),
            resolved_line_items=resolved_count,
            unresolved_line_items=unresolved_count,
            total_estimated_cost_irr=total_estimated_cost,
            total_actual_staged_cost_irr=total_actual_staged_cost,
            total_warnings_count=total_warnings,
        )
