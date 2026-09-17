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
    BOMProcurementPlan,
    CandidateEvaluation,
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
                         'INVALID' if domain is unrecognized;
                         'NONE' if link is empty.
            - link_domain: Normalized domain string (e.g. 'lionelectronic.ir').
            - vendor_id: Registered vendor identifier (e.g. 'vendor_lion'), or None.
        """
        if not link or not link.strip():
            return "NONE", "", None

        raw_link = link.strip()
        domain = ""
        try:
            parsed = urlparse(raw_link)
            domain = (parsed.netloc or raw_link).replace("www.", "").lower()
            if ":" in domain:
                domain = domain.split(":")[0]
        except Exception:
            domain = raw_link.lower()

        reg = registry if registry is not None else VendorRegistry.get_default_registry()
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
        Determines whether a shortage item dictionary contains an automated-orderable link.

        Returns:
            (is_orderable, vendor_id)
        """
        link = str(item.get("link", "")).strip()
        _, _, vendor_id = ProcurementBridge.classify_link(link, registry)
        return vendor_id is not None, vendor_id

    @staticmethod
    def item_to_request(
        item: Dict[str, Any],
        line_item_id: Optional[str] = None,
        registry: Optional[VendorRegistry] = None
    ) -> ProcurementRequest:
        """
        Converts an inventory shortage or BOM shortage item dictionary into a
        formal immutable ProcurementRequest.
        """
        part_number = (
            item.get("part_number")
            or item.get("comment")
            or item.get("part_name")
            or ""
        )
        try:
            req_qty = int(
                item.get("needed_qty")
                or item.get("shortage_qty")
                or item.get("unit_qty")
                or 1
            )
        except (ValueError, TypeError):
            req_qty = 1
        req_qty = max(1, req_qty)

        raw_link = str(item.get("link", "")).strip()
        explicit_url = raw_link if raw_link.startswith("http") else None

        # Determine target vendor if link is registered
        target_vendor = None
        if explicit_url:
            _, _, target_vendor = ProcurementBridge.classify_link(explicit_url, registry)

        if line_item_id:
            lid = line_item_id
        elif "row_idx" in item:
            lid = f"bom_row_{item['row_idx']}"
        elif "orig_row_idx" in item:
            lid = f"inv_row_{item['orig_row_idx']}"
        else:
            lid = str(item.get("designator") or item.get("part_name") or "item")

        description = str(item.get("description") or item.get("comment") or "")
        exact_mpn = item.get("exact_mpn_required", False if explicit_url else True)

        if explicit_url:
            package = str(item.get("package") or "").strip() or None if item.get("package_required") else None
            footprint = str(item.get("footprint") or "").strip() or None if item.get("footprint_required") else None
            manufacturer = (
                str(item.get("manufacturer") or item.get("brand") or "").strip() or None
                if item.get("manufacturer_required")
                else None
            )
        else:
            package = str(item.get("package") or "").strip() or None
            footprint = str(item.get("footprint") or "").strip() or None
            manufacturer = str(item.get("manufacturer") or item.get("brand") or "").strip() or None

        allowed_mfg = item.get("allowed_manufacturers") or item.get("approved_manufacturers")
        is_mfg_any = bool(item.get("is_manufacturer_any", False))
        req_specs = item.get("required_specs") or {}
        req_dims = item.get("required_dimensions") or {}

        metadata = {
            k: v
            for k, v in item.items()
            if k not in ("part_number", "needed_qty", "shortage_qty", "link")
        }

        return ProcurementRequest(
            part_number=str(part_number).strip(),
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
        Executes cart staging across a batch of shortage items using the Universal
        Procurement Orchestrator and registered vendor adapters.

        Args:
            items: List of shortage dictionaries (from BOMAuditor or ExcelDataLoader).
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
            needed_qty = int(item.get("needed_qty") or item.get("shortage_qty") or 1)
            link = str(item.get("link", "")).strip()

            is_orderable, vendor_id = ProcurementBridge.is_item_orderable(item, reg)

            if not is_orderable:
                failed_count += 1
                item["order_success"] = False
                item["actual_ordered_qty"] = 0
                item["qty_ordered"] = 0
                msg = f"No supported vendor adapter for link: {link}" if link else "Missing store link"
                item["order_message"] = msg
                results_log.append({
                    "part": p_name,
                    "status": "FAILED",
                    "qty": 0,
                    "msg": msg,
                    "item": item,
                })
                if progress_callback:
                    progress_callback(idx, total, p_name, 0, f"Skipped ({msg})")
                continue

            if progress_callback:
                progress_callback(
                    idx, total, p_name, needed_qty, f"Staging {needed_qty} pcs for {vendor_id}..."
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
                        item["order_message"] = stage_res.raw_vendor_message or "Added to cart"
                        results_log.append({
                            "part": p_name,
                            "status": "SUCCESS",
                            "qty": stage_res.actual_quantity_staged,
                            "msg": item["order_message"],
                            "vendor_id": candidate.vendor_id,
                            "item": item,
                        })
                        if progress_callback:
                            progress_callback(
                                idx,
                                total,
                                p_name,
                                stage_res.actual_quantity_staged,
                                f"Added {stage_res.actual_quantity_staged} pcs ({item['order_message']})",
                            )
                    else:
                        failed_count += 1
                        item["order_success"] = False
                        item["actual_ordered_qty"] = stage_res.actual_quantity_staged
                        item["qty_ordered"] = stage_res.actual_quantity_staged
                        msg = stage_res.raw_vendor_message or "Staging failed"
                        item["order_message"] = msg
                        results_log.append({
                            "part": p_name,
                            "status": "FAILED",
                            "qty": stage_res.actual_quantity_staged,
                            "msg": msg,
                            "vendor_id": candidate.vendor_id,
                            "item": item,
                        })
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
                    results_log.append({
                        "part": p_name,
                        "status": "FAILED",
                        "qty": 0,
                        "msg": fail_msg,
                        "vendor_id": vendor_id,
                        "item": item,
                    })
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
                    "vendor_id": vendor_id,
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
            "items": items,
        }
