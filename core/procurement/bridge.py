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
    def get_plugin_status(vendor_id: Optional[str], registry: Optional[VendorRegistry] = None) -> str:
        """
        Determines the explicit status of a vendor plugin:
        - READY FOR ORDER
        - PLUGIN DISABLED
        - PLUGIN NOT REGISTERED
        - PLUGIN NOT INSTALLED
        """
        if not vendor_id:
            return "PLUGIN NOT INSTALLED"

        clean_vid = str(vendor_id).strip()
        reg = registry if registry is not None else VendorRegistry.get_default_registry()

        # 1. Check runtime registry
        if reg is not None and hasattr(reg, "has_vendor") and reg.has_vendor(clean_vid):
            if hasattr(reg, "is_vendor_enabled") and reg.is_vendor_enabled(clean_vid):
                return "READY FOR ORDER"
            return "PLUGIN DISABLED"

        # 2. Check persistent store if available
        try:
            from core.plugins.plugin_lifecycle_manager import get_lifecycle_manager
            mgr = get_lifecycle_manager(registry=reg)
            p_rec = mgr.store.get_plugin(clean_vid)
            if p_rec is not None:
                # Installed in store, but not registered or active in registry
                return "PLUGIN NOT REGISTERED"
        except Exception:
            pass

        return "PLUGIN NOT INSTALLED"

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
        Determines whether an inventory shortage item dictionary contains an automated-orderable request.

        In Mode A (DATABASE_AWARE): Returns True if item has a valid registered vendor URL or multi-vendor links.

        Returns:
            (is_orderable, vendor_id)
        """

        # Check if item is marked as an unsupported or removed procurement mode
        raw_mode = item.get("mode")
        if raw_mode is not None:
            mode_str = raw_mode.value if isinstance(raw_mode, ProcurementMode) else str(raw_mode).strip().upper()
            if mode_str != ProcurementMode.DATABASE_AWARE.value:
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
        Converts an inventory shortage line item dictionary into a
        formal immutable ProcurementRequest under Mode A (Database-Aware Stock Reconciliation).

        Rules:
        - Strict MPN: Never fall back to Comment or Part Name!
        - Mode A: Reconciles against inventory link. Mode A is the sole supported procurement workflow.
        """
        # Determine effective mode (Mode A sole workflow)
        if mode is not None:
            eff_mode = mode if isinstance(mode, ProcurementMode) else None
            if eff_mode is None:
                try:
                    eff_mode = ProcurementMode(str(mode))
                except ValueError:
                    raise ValueError(
                        f"Unsupported procurement mode '{mode}'. "
                        "Mode A (DATABASE_AWARE) is the sole supported procurement workflow."
                    )
        else:
            item_mode = item.get("mode")
            if isinstance(item_mode, ProcurementMode):
                eff_mode = item_mode
            elif item_mode is not None:
                mode_str = str(item_mode).strip().upper()
                if mode_str == ProcurementMode.DATABASE_AWARE.value:
                    eff_mode = ProcurementMode.DATABASE_AWARE
                else:
                    raise ValueError(
                        f"Unsupported procurement mode '{item_mode}'. "
                        "Mode A (DATABASE_AWARE) is the sole supported procurement workflow."
                    )
            else:
                eff_mode = ProcurementMode.DATABASE_AWARE

        if eff_mode != ProcurementMode.DATABASE_AWARE:
            raise ValueError(
                f"Unsupported procurement mode '{eff_mode}'. "
                "Mode A (DATABASE_AWARE) is the sole supported procurement workflow."
            )

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

        # Mode A: Reconcile against inventory links
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
            target_vendor = item.get("vendor_id")
            if explicit_url and not target_vendor:
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
    def preflight_check(
        items: List[Dict[str, Any]],
        registry: Optional[VendorRegistry] = None
    ) -> Dict[str, Any]:
        """
        Executes a deterministic preflight check across candidate items prior to staging.

        Inspects every item and its supplier links independently to determine:
        - Total items examined
        - Items with eligible supplier links
        - Items without eligible supplier links
        - Breakdowns: invalid links, plugins not installed, plugins not registered, plugins disabled
        - Excluded items with specific failure reasons
        """
        reg = registry if registry is not None else VendorRegistry.get_default_registry()
        total_items = len(items)
        eligible_items = []
        excluded_items = []

        invalid_links_count = 0
        not_installed_count = 0
        not_registered_count = 0
        disabled_count = 0
        covered_by_stock_count = 0

        for item in items:
            p_name = item.get("part_name") or item.get("part_number") or item.get("designator") or "Item"
            raw_n = item.get("needed_qty")
            if raw_n is None:
                raw_n = item.get("shortage_qty")
            if raw_n is None:
                raw_n = item.get("total_needed_qty") or item.get("unit_qty") or 1
            try:
                needed_qty = int(raw_n)
            except (ValueError, TypeError):
                needed_qty = 1

            if any(item.get(k) is not None and int(item.get(k)) <= 0 for k in ("needed_qty", "shortage_qty")):
                covered_by_stock_count += 1
                excluded_items.append({
                    "item": item,
                    "part": p_name,
                    "reason": "FULLY_COVERED_BY_STOCK",
                    "message": "No procurement requirement: item is fully covered by stock (0 pcs needed)"
                })
                continue

            link = str(item.get("link", "")).strip()
            raw_link = str(item.get("raw_link") or link).strip()

            from core.procurement.vendor_links import parse_vendor_links
            parsed = parse_vendor_links(raw_link or link, registry=reg)

            if parsed.is_empty:
                invalid_links_count += 1
                excluded_items.append({
                    "item": item,
                    "part": p_name,
                    "reason": "BLANK_LINK",
                    "message": "Missing store link"
                })
                continue

            if not parsed.is_valid:
                invalid_links_count += 1
                excluded_items.append({
                    "item": item,
                    "part": p_name,
                    "reason": "INVALID_LINK",
                    "message": parsed.error_message or "Syntactically invalid store link"
                })
                continue

            # Check individual links for plugin readiness
            item_links = parsed.links
            link_evaluations = []
            for vid, entry in item_links.items():
                p_stat = ProcurementBridge.get_plugin_status(vid, reg)
                link_evaluations.append((vid, entry.url, p_stat))

            ready_links = [(v, u) for v, u, st in link_evaluations if st == "READY FOR ORDER"]

            if not ready_links:
                # Determine primary reason from evaluations
                primary_stat = link_evaluations[0][2] if link_evaluations else "PLUGIN NOT INSTALLED"
                if primary_stat == "PLUGIN NOT INSTALLED":
                    not_installed_count += 1
                elif primary_stat == "PLUGIN NOT REGISTERED":
                    not_registered_count += 1
                elif primary_stat == "PLUGIN DISABLED":
                    disabled_count += 1

                excluded_items.append({
                    "item": item,
                    "part": p_name,
                    "reason": primary_stat,
                    "message": f"Plugin unavailable for supplier link: {primary_stat}"
                })
            else:
                eligible_items.append(item)

        return {
            "total_items": total_items,
            "eligible_count": len(eligible_items),
            "excluded_count": len(excluded_items),
            "eligible_items": eligible_items,
            "excluded_items": excluded_items,
            "invalid_links_count": invalid_links_count,
            "not_installed_count": not_installed_count,
            "not_registered_count": not_registered_count,
            "disabled_count": disabled_count,
            "covered_by_stock_count": covered_by_stock_count,
            "is_all_eligible": len(eligible_items) == total_items and total_items > 0,
            "is_none_eligible": len(eligible_items) == 0,
        }

    @staticmethod
    def execute_staged_procurement_batch(
        items: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str, int, str], None]] = None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Executes cart staging across a batch of shortage items using the Universal
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
                "preflight": None,
                "results": [],
                "items": [],
            }

        # 1. Execute Staging Preflight Upfront
        preflight = ProcurementBridge.preflight_check(items, registry=reg)
        if preflight["is_none_eligible"]:
            # Zero items eligible: abort staging immediately without calling adapters or reporting false execution failures.
            # Count excluded items in failed_count to maintain contract consistency with batch failure reporting.
            reasons = [exc["message"] for exc in preflight["excluded_items"]]
            summary_reason = reasons[0] if reasons else "No vendor plugins available for selected items."
            return {
                "success": False,
                "message": f"Preflight check failed: {summary_reason}",
                "total_items": total,
                "eligible_items": 0,
                "excluded_items": len(preflight["excluded_items"]),
                "attempted_items": 0,
                "successful_count": 0,
                "failed_count": len(preflight["excluded_items"]),
                "actual_failed_count": 0,
                "preflight": preflight,
                "excluded_details": preflight["excluded_items"],
                "results": [
                    {
                        "part": exc["part"],
                        "status": "FAILED",
                        "status_code": (
                            SupplierOutcomeStatus.NO_OP_SATISFIED.value
                            if exc.get("reason") == "COVERED_BY_STOCK"
                            else SupplierOutcomeStatus.SKIPPED.value
                        ),
                        "qty": 0,
                        "msg": exc["message"],
                        "vendor_id": "",
                        "item": exc["item"],
                    }
                    for exc in preflight["excluded_items"]
                ],
                "supplier_results": [],
                "items": items,
            }

        # Mixed availability preflight filtering:
        # Separate eligible items from excluded items upfront.
        # Excluded items are recorded with their explicit preflight exclusion reasons,
        # and NEVER dispatched to adapters or counted as attempted/failed staging operations.
        eligible_items_list = preflight["eligible_items"]
        excluded_items_list = preflight["excluded_items"]

        for exc in excluded_items_list:
            exc_item = exc["item"]
            exc_item["order_success"] = False
            exc_item["actual_ordered_qty"] = 0
            exc_item["qty_ordered"] = 0
            exc_item["order_message"] = exc["message"]
            sc = (
                SupplierOutcomeStatus.NO_OP_SATISFIED
                if exc.get("reason") == "COVERED_BY_STOCK"
                else SupplierOutcomeStatus.SKIPPED
            )
            results_log.append({
                "part": exc["part"],
                "status": "EXCLUDED",
                "status_code": sc.value,
                "qty": 0,
                "msg": exc["message"],
                "vendor_id": "",
                "item": exc_item,
            })
            supplier_results.append(SupplierItemResult(
                run_id=run_id,
                item_id=str(exc_item.get("designator") or exc["part"]),
                mpn=str(exc_item.get("part_number") or exc["part"]),
                vendor_id="",
                requested_quantity=int(exc_item.get("needed_qty") or exc_item.get("shortage_qty") or 0),
                effective_quantity=0,
                staged_quantity=0,
                status=sc,
                message=exc["message"],
                pdp_url=str(exc_item.get("link", "")),
            ))

        items_to_stage = eligible_items_list
        attempted_count = len(items_to_stage)

        # -------------------------------------------------------------
        # Step 1.5: Upfront Pre-Authentication for Involved Vendors
        # Ensures sessions are authenticated and session cookies are loaded
        # before any candidate inspection or cart staging begins.
        # -------------------------------------------------------------
        vendors_to_preauth = set()
        for itm in items_to_stage:
            orderable, vid = ProcurementBridge.is_item_orderable(itm, reg)
            if orderable and vid:
                vendors_to_preauth.add(vid)

        for v_id in sorted(vendors_to_preauth):
            try:
                adapter = reg.get_adapter(v_id)
                v_disp = (
                    reg.get_vendor_name(v_id)
                    if hasattr(reg, "get_vendor_name")
                    else v_id.replace("vendor_", "").title()
                )
                session_stat = adapter.validate_session()
                if session_stat and not getattr(session_stat, "is_authenticated", False):
                    if progress_callback:
                        progress_callback(0, total, v_disp, 0, f"Logging in to {v_disp}...")
                    auth_res = adapter.authenticate()
                    if auth_res and not auth_res.success:
                        logger.warning(f"Upfront authentication for {v_id} failed: {auth_res.message}")
            except Exception as auth_err:
                logger.warning(f"Upfront pre-authentication error for {v_id}: {str(auth_err)}")

        for idx, item in enumerate(items_to_stage, start=1):
            if cancel_check and cancel_check():
                log_event("INFO", "Procurement staging batch cancelled by user request.")
                for rem_item in items_to_stage[idx - 1:]:
                    rem_name = rem_item.get("part_name") or rem_item.get("part_number") or rem_item.get("designator") or "Item"
                    rem_item["order_success"] = False
                    rem_item["actual_ordered_qty"] = 0
                    rem_item["qty_ordered"] = 0
                    rem_item["order_message"] = "Automation stopped by user"
                    results_log.append({
                        "part": rem_name,
                        "status": "STOPPED",
                        "status_code": SupplierOutcomeStatus.SKIPPED.value,
                        "qty": 0,
                        "msg": "Stopped by user",
                        "vendor_id": rem_item.get("vendor_id") or "",
                        "item": rem_item,
                    })
                break
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
            "total_items": total,
            "eligible_items": len(eligible_items_list),
            "excluded_items": len(excluded_items_list),
            "attempted_items": attempted_count,
            "successful_count": successful_count,
            "failed_count": failed_count + len(excluded_items_list),
            "actual_failed_count": failed_count,
            "preflight": preflight,
            "excluded_details": excluded_items_list,
            "results": results_log,
            "supplier_results": supplier_results,
            "items": items,
        }
