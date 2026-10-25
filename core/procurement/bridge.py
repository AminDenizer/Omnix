import datetime
"""
Universal Procurement Bridge Layer.

Serves as the architectural bridge connecting existing BOM parsing (BOMAuditor)
and inventory shortage tracking (ExcelDataLoader / OrderPreviewDialog) to the
underlying Universal Procurement Orchestrator and Vendor Registry.

Preserves complete backward compatibility for legacy callers while eliminating
vendor-specific coupling and hardcoded domain assumptions.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from core.models import CartMutationResult
from core.procurement.models import (
    SupplierOutcomeStatus,
    SupplierItemResult,
    BOMProcurementPlan,
    CandidateEvaluation,
    ProcurementMode,
    ProcurementRequest,
    RequestProcurementResult,
    VendorProcurementCandidate,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry

logger = logging.getLogger("OmnixProcurementBridge")


class ProcurementBridge:
    """
    Bridge utility providing deterministic translation, link classification,
    and batch execution between legacy item dictionaries and the universal
    procurement architecture.
    """

    @staticmethod
    def classify_link(
        link: str,
        registry: Optional[VendorRegistry] = None
    ) -> Tuple[str, str, Optional[str]]:
        """
        Classifies a given URL string against the Vendor Registry.

        Returns:
            Tuple of (link_type, link_domain, vendor_id):
            - link_type: 'LION', 'JAVAN', 'ROBOEQ', or uppercase vendor identifier;
                         'MULTI' if multiple valid vendor links are present;
                         'INVALID' if domain is unrecognized or link is malformed;
                         'NONE' if link is empty.
            - link_domain: Normalized domain string (e.g. 'lionelectronic.ir', 'multi-vendor').
            - vendor_id: Registered vendor identifier (e.g. 'vendor_lion'), or None.
        """
        if not link or not link.strip():
            return "NONE", "", None

        raw_link = link.strip()
        reg = registry if registry is not None else VendorRegistry.get_default_registry()

        try:
            from core.procurement.vendor_links import parse_vendor_links
            parsed = parse_vendor_links(raw_link, registry=reg)
            if not parsed.is_valid:
                return "INVALID", "", None
            if parsed.is_empty:
                return "NONE", "", None
            if parsed.count == 1:
                entry = parsed.get_single_entry()
                domain = ""
                try:
                    p = urlparse(entry.url)
                    domain = (p.netloc or entry.url).replace("www.", "").lower()
                    if ":" in domain:
                        domain = domain.split(":")[0]
                except Exception:
                    domain = entry.url.lower()
                return entry.vendor_label, domain, entry.vendor_id
            elif parsed.count > 1:
                return "MULTI", "multi-vendor", None
            else:
                # Valid legacy URL syntax, but unknown / unsupported vendor domain
                domain = ""
                try:
                    p = urlparse(raw_link)
                    domain = (p.netloc or raw_link).replace("www.", "").lower()
                    if ":" in domain:
                        domain = domain.split(":")[0]
                except Exception:
                    domain = raw_link.lower()
                return "INVALID", domain, None
        except Exception:
            pass

        # Fallback to existing logic if parse_vendor_links is unavailable
        domain = ""
        try:
            parsed = urlparse(raw_link)
            domain = (parsed.netloc or raw_link).replace("www.", "").lower()
            if ":" in domain:
                domain = domain.split(":")[0]
        except Exception:
            domain = raw_link.lower()

        vendor_id = reg.get_vendor_for_url(raw_link)

        if vendor_id:
            # Map canonical vendor IDs to standard link types
            if vendor_id == "vendor_lion":
                link_type = "LION"
            elif vendor_id == "vendor_javan":
                link_type = "JAVAN"
            elif vendor_id == "vendor_roboeq":
                link_type = "ROBOEQ"
            else:
                link_type = vendor_id.replace("vendor_", "").upper()
            return link_type, domain, vendor_id

        return "INVALID", domain, None

    @staticmethod
    def is_item_orderable(
        item: Dict[str, Any],
        registry: Optional[VendorRegistry] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Determines whether a shortage or direct BOM item dictionary contains an automated-orderable request.

        In Mode B (DIRECT_BOM): Returns True if item has valid non-empty MPN and is marked valid.
        In Mode A (DATABASE_AWARE): Returns True if item has a valid registered vendor URL or multi-vendor links.

        Returns:
            (is_orderable, vendor_id)
        """
        mode = item.get("mode")
        if mode == ProcurementMode.DIRECT_BOM or mode == "DIRECT_BOM":
            pn = item.get("part_number") or ""
            is_valid = item.get("is_valid", True)
            if is_valid and str(pn).strip():
                return True, None
            return False, None

        # Check for zero or negative shortage / needed quantity in Mode A
        for q_key in ("needed_qty", "shortage_qty"):
            if q_key in item and item[q_key] is not None:
                try:
                    if int(item[q_key]) <= 0:
                        return False, None
                except (ValueError, TypeError):
                    pass

        # Check if an explicit vendor has been selected for a multi-vendor item
        selected_vid = item.get("selected_vendor_id") or item.get("selected_vendor")
        vendor_links = item.get("vendor_links")

        if vendor_links:
            if selected_vid:
                if selected_vid in vendor_links:
                    return True, selected_vid
                return False, None
            elif len(vendor_links) == 1:
                vid = next(iter(vendor_links.keys()))
                return True, vid
            elif len(vendor_links) > 1:
                # Multi-vendor item: it is orderable in Mode A once a vendor is chosen
                return True, None

        link = str(item.get("link", "")).strip()
        link_type, _, vendor_id = ProcurementBridge.classify_link(link, registry)
        if link_type == "MULTI":
            return True, None
        return vendor_id is not None, vendor_id

    @staticmethod
    def item_to_request(
        item: Dict[str, Any],
        line_item_id: Optional[str] = None,
        registry: Optional[VendorRegistry] = None,
        mode: Optional[ProcurementMode] = None,
    ) -> ProcurementRequest:
        """
        Converts an inventory shortage or BOM line item dictionary into a
        formal immutable ProcurementRequest with strict MPN integrity and explicit mode branching.

        Rules:
        - Strict MPN: Never fall back to Comment or Part Name!
        - Mode B: Inventory links and DB stock are ignored; queries broadcast across all enabled vendors.
        - Mode A: Reconciles against inventory link.
        """
        # Determine effective mode
        if mode is not None:
            eff_mode = mode if isinstance(mode, ProcurementMode) else ProcurementMode(mode)
        else:
            item_mode = item.get("mode")
            if isinstance(item_mode, ProcurementMode):
                eff_mode = item_mode
            elif isinstance(item_mode, str) and item_mode in ProcurementMode.__members__:
                eff_mode = ProcurementMode(item_mode)
            elif item_mode == "DIRECT_BOM":
                eff_mode = ProcurementMode.DIRECT_BOM
            else:
                eff_mode = ProcurementMode.DATABASE_AWARE

        # Strict MPN validation: Missing MPN must NEVER fall back to Comment
        raw_pn = item.get("part_number") or item.get("part_name")
        if not raw_pn or not isinstance(raw_pn, str) or not raw_pn.strip():
            raise ValueError("part_number must be a non-empty string. Fallback to comment is prohibited.")
        part_number = raw_pn.strip()

        # Explicit check for known purchase requirement with strict zero preservation (Section 5 Fix C)
        raw_qty = None
        for key in ("needed_qty", "shortage_qty"):
            if key in item and item[key] is not None:
                try:
                    raw_qty = int(item[key])
                    break
                except (ValueError, TypeError):
                    pass

        if raw_qty is None:
            for key in ("total_needed_qty", "total_needed", "unit_qty"):
                if key in item and item[key] is not None:
                    try:
                        raw_qty = int(item[key])
                        break
                    except (ValueError, TypeError):
                        pass

        if raw_qty is None:
            raw_qty = 1

        if raw_qty <= 0:
            raise ValueError(
                f"Component '{part_number}' has zero or negative purchase requirement ({raw_qty} pcs). "
                "Fully stocked components cannot be dispatched for procurement."
            )

        req_qty = raw_qty

        if line_item_id:
            lid = line_item_id
        elif "row_idx" in item:
            lid = f"bom_row_{item['row_idx']}"
        elif "orig_row_idx" in item:
            lid = f"inv_row_{item['orig_row_idx']}"
        else:
            lid = str(item.get("designator") or part_number or "item")

        description = str(item.get("description") or item.get("comment") or "")

        # Explicit mode branching
        if eff_mode == ProcurementMode.DIRECT_BOM:
            explicit_url = None
            target_vendor = None
            exact_mpn = item.get("exact_mpn_required", True)
            package = str(item.get("package") or "").strip() or None
            footprint = str(item.get("footprint") or "").strip() or None
            raw_m = str(item.get("manufacturer") or item.get("brand") or "").strip()
            manufacturer = None if raw_m.upper() == "ANY" else (raw_m or None)
            allowed_mfg = item.get("allowed_manufacturers") or item.get("approved_manufacturers")
            is_mfg_any = bool(
                item.get("is_manufacturer_any", False)
                or raw_m.upper() == "ANY"
                or item.get("manufacturer_rule") == "ANY"
                or (not manufacturer and not allowed_mfg)
            )
            req_specs = item.get("required_specs") or {}
            req_dims = item.get("required_dimensions") or {}
        else:
            # Mode A: DATABASE_AWARE
            selected_vendor = item.get("selected_vendor_id") or item.get("selected_vendor")
            raw_link = str(item.get("link", "")).strip()
            vendor_links = item.get("vendor_links")

            if vendor_links is None and raw_link:
                try:
                    from core.procurement.vendor_links import parse_vendor_links
                    parsed = parse_vendor_links(raw_link, registry=registry)
                    if parsed.is_valid and parsed.count > 0:
                        vendor_links = {vid: e.url for vid, e in parsed.links.items()}
                except Exception:
                    vendor_links = None

            explicit_url = None
            target_vendor = None

            if vendor_links:
                if selected_vendor:
                    # Case D: Selected vendor has no link in component's mapping
                    if selected_vendor not in vendor_links:
                        raise ValueError(
                            f"Selected vendor '{selected_vendor}' has no valid URL for component '{part_number}'. "
                            f"Available vendors: {list(vendor_links.keys())}."
                        )
                    explicit_url = vendor_links[selected_vendor]
                    target_vendor = selected_vendor
                elif len(vendor_links) == 1:
                    # Case A: Exactly one valid URL
                    target_vendor, explicit_url = next(iter(vendor_links.items()))
                else:
                    # Case B: Multiple valid URLs, but no vendor selected
                    raise ValueError(
                        f"Component '{part_number}' has multiple vendor links {list(vendor_links.keys())}. "
                        "Vendor selection is required before procurement dispatch."
                    )
            else:
                explicit_url = raw_link if raw_link.startswith("http") else None
                if explicit_url:
                    _, _, target_vendor = ProcurementBridge.classify_link(explicit_url, registry)

            exact_mpn = item.get("exact_mpn_required", True)
            package = str(item.get("package") or "").strip() or None
            footprint = str(item.get("footprint") or "").strip() or None
            raw_m = str(item.get("manufacturer") or item.get("brand") or "").strip()
            manufacturer = None if raw_m.upper() == "ANY" else (raw_m or None)
            allowed_mfg = item.get("allowed_manufacturers") or item.get("approved_manufacturers")
            is_mfg_any = bool(
                item.get("is_manufacturer_any", False)
                or raw_m.upper() == "ANY"
                or item.get("manufacturer_rule") == "ANY"
                or (not manufacturer and not allowed_mfg)
            )
            req_specs = item.get("required_specs") or {}
            req_dims = item.get("required_dimensions") or {}

        metadata = {
            k: v
            for k, v in item.items()
            if k not in ("part_number", "needed_qty", "shortage_qty", "link")
        }

        return ProcurementRequest(
            part_number=part_number,
            required_quantity=req_qty,
            description=description,
            explicit_vendor_id=target_vendor,
            explicit_vendor_url=explicit_url,
            manufacturer=manufacturer,
            allowed_manufacturers=allowed_mfg,
            is_manufacturer_any=is_mfg_any,
            package=package,
            footprint=footprint,
            required_specs=req_specs,
            required_dimensions=req_dims,
            exact_mpn_required=exact_mpn,
            mode=eff_mode,
            source=str(lid),
            metadata=metadata,
        )

    @staticmethod
    def execute_staged_procurement_batch(
        items: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str, int, str], None]] = None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
    ) -> Dict[str, Any]:
        """
        Executes cart staging across a batch of shortage or direct BOM items using the Universal
        Procurement Orchestrator and registered vendor adapters.

        Args:
            items: List of shortage/BOM dictionaries (from BOMAuditor or ExcelDataLoader).
            progress_callback: Optional progress reporter (current, total, part_name, qty, msg).
            registry: Optional custom VendorRegistry instance.
            orchestrator: Optional custom UniversalProcurementOrchestrator instance.

        Returns:
            Dict summary:
            {
                "success": bool,
                "message": str,
                "successful_count": int,
                "failed_count": int,
                "results": List[Dict[str, Any]],
                "items": List[Dict[str, Any]]
            }
        """
        reg = registry if registry is not None else VendorRegistry.get_default_registry()
        orch = orchestrator or UniversalProcurementOrchestrator(registry=reg)

        total = len(items)
        successful_count = 0
        failed_count = 0
        results_log = []
        supplier_results: List[SupplierItemResult] = []
        run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if total == 0:
            return {
                "success": True,
                "message": "No items to stage.",
                "successful_count": 0,
                "failed_count": 0,
                "results": [],
                "items": [],
            }

        for idx, item in enumerate(items, start=1):
            p_name = (
                item.get("part_name")
                or item.get("part_number")
                or item.get("designator")
                or f"Item {idx}"
            )
            raw_n = item.get("needed_qty")
            if raw_n is None:
                raw_n = item.get("shortage_qty")
            if raw_n is None:
                raw_n = item.get("total_needed_qty") or item.get("unit_qty") or 1
            try:
                needed_qty = int(raw_n)
            except (ValueError, TypeError):
                needed_qty = 1
            link = str(item.get("link", "")).strip()

            is_orderable, vendor_id = ProcurementBridge.is_item_orderable(item, reg)

            if not is_orderable:
                failed_count += 1
                item["order_success"] = False
                item["actual_ordered_qty"] = 0
                item["qty_ordered"] = 0
                if any(item.get(k) is not None and int(item.get(k)) <= 0 for k in ("needed_qty", "shortage_qty")):
                    msg = "No procurement requirement: item is fully covered by stock (0 pcs needed)"
                elif link:
                    msg = f"No supported vendor adapter for link: {link}"
                else:
                    msg = "Missing or invalid part number / store link"
                item["order_message"] = msg
                is_stock_covered = any(item.get(k) is not None and int(item.get(k)) <= 0 for k in ("needed_qty", "shortage_qty"))
                sc = SupplierOutcomeStatus.NO_OP_SATISFIED if is_stock_covered else SupplierOutcomeStatus.SKIPPED
                results_log.append({
                    "part": p_name,
                    "status": "FAILED",
                    "status_code": sc.value,
                    "qty": 0,
                    "msg": msg,
                    "vendor_id": vendor_id or "",
                    "item": item,
                })
                supplier_results.append(SupplierItemResult(
                    run_id=run_id,
                    item_id=str(item.get("designator") or p_name),
                    mpn=str(item.get("part_number") or p_name),
                    vendor_id=vendor_id or "",
                    requested_quantity=needed_qty,
                    effective_quantity=needed_qty,
                    staged_quantity=0,
                    status=sc,
                    message=msg,
                    pdp_url=link,
                ))
                if progress_callback:
                    progress_callback(idx, total, p_name, 0, f"Skipped ({msg})")
                continue

            v_target_desc = vendor_id if vendor_id else "multi-vendor catalog"
            if progress_callback:
                progress_callback(
                    idx, total, p_name, needed_qty, f"Staging {needed_qty} pcs for {v_target_desc}..."
                )

            try:
                # Build procurement request
                req = ProcurementBridge.item_to_request(item, registry=reg)

                # Generate procurement plan
                plan: BOMProcurementPlan = orch.build_plan([req])
                res: Optional[RequestProcurementResult] = plan.results[0] if plan.results else None

                if res and res.status == "RESOLVED" and res.selected_evaluation:
                    candidate = res.selected_evaluation.candidate
                    stage_res: CartMutationResult = orch.stage_candidate(
                        candidate, res.selected_evaluation.effective_quantity
                    )

                    if stage_res.success:
                        successful_count += 1
                        item["order_success"] = True
                        item["actual_ordered_qty"] = stage_res.actual_quantity_staged
                        item["qty_ordered"] = stage_res.actual_quantity_staged
                        msg = stage_res.raw_vendor_message or ("Already satisfied in cart" if stage_res.is_noop else "Added to cart")
                        item["order_message"] = msg
                        sc = SupplierOutcomeStatus.NO_OP_SATISFIED if stage_res.is_noop else SupplierOutcomeStatus.ADDED_TO_CART
                        results_log.append({
                            "part": p_name,
                            "status": "SUCCESS",
                            "status_code": sc.value,
                            "qty": stage_res.actual_quantity_staged,
                            "msg": msg,
                            "vendor_id": candidate.vendor_id,
                            "item": item,
                        })
                        supplier_results.append(SupplierItemResult(
                            run_id=run_id,
                            item_id=str(item.get("designator") or p_name),
                            mpn=candidate.part_number,
                            vendor_id=candidate.vendor_id,
                            requested_quantity=needed_qty,
                            effective_quantity=res.selected_evaluation.effective_quantity,
                            staged_quantity=stage_res.actual_quantity_staged,
                            status=sc,
                            message=msg,
                            available_quantity=candidate.stock_quantity,
                            unit_price_irr=res.selected_evaluation.effective_unit_price_irr,
                            total_price_irr=res.selected_evaluation.effective_total_price_irr,
                            is_verified=True,
                            is_noop=stage_res.is_noop,
                            pdp_url=candidate.product_ref.pdp_url if candidate.product_ref else link,
                        ))
                        if progress_callback:
                            cb_msg = f"{msg}" if stage_res.is_noop else f"Added {stage_res.actual_quantity_staged} pcs ({msg})"
                            progress_callback(
                                idx,
                                total,
                                p_name,
                                stage_res.actual_quantity_staged,
                                cb_msg,
                            )

                    else:
                        failed_count += 1
                        item["order_success"] = False
                        item["actual_ordered_qty"] = stage_res.actual_quantity_staged
                        item["qty_ordered"] = stage_res.actual_quantity_staged
                        msg = stage_res.raw_vendor_message or "Staging failed"
                        item["order_message"] = msg
                        sc = SupplierOutcomeStatus.CHALLENGE_BLOCKED if stage_res.error_category == "CHALLENGE_BLOCKED" else SupplierOutcomeStatus.FAILED
                        results_log.append({
                            "part": p_name,
                            "status": "FAILED",
                            "status_code": sc.value,
                            "qty": stage_res.actual_quantity_staged,
                            "msg": msg,
                            "vendor_id": candidate.vendor_id,
                            "item": item,
                        })
                        supplier_results.append(SupplierItemResult(
                            run_id=run_id,
                            item_id=str(item.get("designator") or p_name),
                            mpn=candidate.part_number,
                            vendor_id=candidate.vendor_id,
                            requested_quantity=needed_qty,
                            effective_quantity=res.selected_evaluation.effective_quantity if res.selected_evaluation else needed_qty,
                            staged_quantity=0,
                            status=sc,
                            message=msg,
                            error_category=stage_res.error_category,
                            available_quantity=candidate.stock_quantity,
                            is_verified=False,
                            pdp_url=candidate.product_ref.pdp_url if candidate.product_ref else link,
                        ))
                        if progress_callback:
                            progress_callback(
                                idx,
                                total,
                                p_name,
                                stage_res.actual_quantity_staged,
                                f"Failed: {msg}",
                            )
                else:
                    failed_count += 1
                    item["order_success"] = False
                    item["actual_ordered_qty"] = 0
                    item["qty_ordered"] = 0
                    fail_msg = res.error_message if res else "Candidate resolution failed"
                    item["order_message"] = fail_msg
                    is_insufficient = bool(res and res.status == "INSUFFICIENT_STOCK")
                    is_oos = bool(res and res.status == "OUT_OF_STOCK")
                    if is_insufficient:
                        sc = SupplierOutcomeStatus.INSUFFICIENT_STOCK
                        row_status = "SKIPPED"
                    elif is_oos:
                        sc = SupplierOutcomeStatus.OUT_OF_STOCK
                        row_status = "FAILED"
                    else:
                        sc = SupplierOutcomeStatus.FAILED
                        row_status = "FAILED"
                    results_log.append({
                        "part": p_name,
                        "status": row_status,
                        "status_code": sc.value,
                        "qty": 0,
                        "msg": fail_msg,
                        "vendor_id": vendor_id or "multi_vendor",
                        "item": item,
                    })
                    eff_q = needed_qty
                    avail_q = None
                    pkg_step = 1
                    moq_val = 1
                    if res and res.evaluations:
                        ev0 = res.evaluations[0]
                        eff_q = ev0.effective_quantity or needed_qty
                        if ev0.candidate:
                            avail_q = ev0.candidate.stock_quantity
                            if ev0.candidate.order_constraints:
                                pkg_step = ev0.candidate.order_constraints.packaging_step_raw or 1
                                moq_val = ev0.candidate.order_constraints.moq_raw or 1

                    supplier_results.append(SupplierItemResult(
                        run_id=run_id,
                        item_id=str(item.get("designator") or p_name),
                        mpn=p_name,
                        vendor_id=vendor_id or "multi_vendor",
                        requested_quantity=needed_qty,
                        effective_quantity=eff_q,
                        staged_quantity=0,
                        status=sc,
                        message=fail_msg,
                        available_quantity=avail_q,
                        packaging_step=pkg_step,
                        moq=moq_val,
                        pdp_url=link,
                    ))
                    if progress_callback:
                        progress_callback(idx, total, p_name, 0, f"Error: {fail_msg}")

            except Exception as e:
                failed_count += 1
                err_msg = f"Unexpected staging error: {str(e)}"
                item["order_success"] = False
                item["actual_ordered_qty"] = 0
                item["qty_ordered"] = 0
                item["order_message"] = err_msg
                results_log.append({
                    "part": p_name,
                    "status": "FAILED",
                    "qty": 0,
                    "msg": err_msg,
                    "vendor_id": vendor_id or "multi_vendor",
                    "item": item,
                })
                if progress_callback:
                    progress_callback(idx, total, p_name, 0, f"Exception: {err_msg}")

        overall_success = successful_count > 0 or (total == 0)
        summary_msg = (
            f"Batch staging completed: {successful_count} succeeded, {failed_count} failed."
        )

        return {
            "success": overall_success,
            "message": summary_msg,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "results": results_log,
            "supplier_results": supplier_results,
            "items": items,
        }
