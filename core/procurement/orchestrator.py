"""
Omnix Core - Universal Procurement Orchestrator
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
"""

import datetime
import urllib.parse
from typing import List, Optional, Dict, Any, Tuple

from core.errors import OmnixVendorError, UnknownVendorError
from core.models import (
    CartMutationResult,
    CartItem,
    CartDetails,
    IdentityMatchTier,
    ProductReference,
    OrderConstraints,
)
from core.procurement.models import (
    EvaluationState,
    normalize_constraint_string,
    PriceTier,
    ProcurementRequest,
    VendorProcurementCandidate,
    CandidateEvaluation,
    RequestProcurementResult,
    BOMProcurementPlan,
    calculate_effective_quantity,
    effective_unit_price,
    effective_total_price,
)
from core.procurement.registry import VendorRegistry, default_registry



class UniversalProcurementOrchestrator:
    """
    Vendor-neutral procurement orchestrator sitting above IVendorAdapter and VendorRegistry.
    
    Responsibilities:
    1. Directs procurement requests to explicit or multi-vendor targets.
    2. Gathers and normalizes vendor candidates through IVendorAdapter operations.
    3. Evaluates candidates using deterministic step, MOQ, and volume tier price formulas.
    4. Deterministically selects the optimal eligible candidate without heuristic or AI ranking.
    5. Builds multi-item BOM/shortage procurement plans with full transparency.
    6. Stages items in vendor shopping carts (strictly non-destructive).
    """

    def __init__(self, registry: Optional[VendorRegistry] = None):
        self.registry = registry or default_registry

    def gather_candidates(
        self,
        request: ProcurementRequest,
        vendor_ids: Optional[List[str]] = None,
    ) -> List[VendorProcurementCandidate]:
        """
        Query vendor adapters to gather normalized product candidates for a ProcurementRequest.
        """
        candidates: List[VendorProcurementCandidate] = []

        # Case A: Explicit product URL provided — Atomic Version-Aware Resolution
        if request.explicit_vendor_url:
            clean_url = str(request.explicit_vendor_url).strip()
            if not clean_url:
                return []

            adapter = None
            reg_meta = None
            resolved_vid = None

            if hasattr(self.registry, "resolve_adapter_for_url"):
                try:
                    resolved = self.registry.resolve_adapter_for_url(clean_url, enabled_only=True)
                    if isinstance(resolved, tuple) and len(resolved) == 2:
                        adapter, reg_meta = resolved
                        if reg_meta is not None:
                            resolved_vid = getattr(reg_meta, "vendor_id", None)
                except Exception:
                    adapter = None
                    reg_meta = None
                    resolved_vid = None
            elif hasattr(self.registry, "get_vendor_for_url"):
                # Fallback for fake/mock registries lacking resolve_adapter_for_url
                resolved_vid = self.registry.get_vendor_for_url(clean_url, enabled_only=True)
                if resolved_vid and hasattr(self.registry, "get_adapter"):
                    try:
                        adapter = self.registry.get_adapter(resolved_vid)
                    except Exception:
                        adapter = None
                        resolved_vid = None

            if not adapter or not resolved_vid:
                return []

            if vendor_ids and resolved_vid not in vendor_ids:
                return []

            if request.explicit_vendor_id:
                clean_exp_vid = str(request.explicit_vendor_id).strip()
                if clean_exp_vid != resolved_vid:
                    return []

            candidate = self._inspect_explicit_url(adapter, resolved_vid, clean_url)
            if candidate:
                candidates.append(candidate)
            return candidates

        # Case B: Catalog search by part number across target vendors
        target_vendors = self._resolve_target_vendors(request, vendor_ids)

        for vid in target_vendors:
            try:
                adapter = self.registry.get_adapter(vid)
                search_res = adapter.search_part(request.part_number)
                if not search_res or not search_res.items:
                    continue

                # Inspect matching search items
                for item in search_res.items:
                    try:
                        pref = adapter.resolve_product(item.pdp_url or item.vendor_sku)
                        details = adapter.inspect_product(pref)
                        stock = adapter.inspect_stock(pref)
                        constraints = None
                        if hasattr(adapter, "determine_order_constraints"):
                            try:
                                constraints = adapter.determine_order_constraints(pref)
                            except Exception:
                                constraints = None

                        # Extract price tiers if provided in raw details
                        price_tiers: List[PriceTier] = []
                        raw_tiers = getattr(details, "raw_data", {}).get("price_tiers", [])
                        for t in raw_tiers:
                            if isinstance(t, dict) and "min_quantity" in t and "unit_price_irr" in t:
                                price_tiers.append(PriceTier(min_quantity=t["min_quantity"], unit_price_irr=t["unit_price_irr"], raw_label=t.get("raw_label", "")))

                        cand = VendorProcurementCandidate(
                            vendor_id=vid,
                            part_number=details.mpn or item.mpn_hint or item.vendor_sku,
                            product_ref=pref,
                            description=item.title or "",
                            in_stock=stock.in_stock,
                            stock_quantity=stock.stock_quantity,
                            can_order=details.can_order,
                            base_unit_price_irr=details.price_irr,
                            price_tiers=price_tiers,
                            order_constraints=constraints or details.order_constraints or OrderConstraints(),
                            manufacturer=details.manufacturer,
                            package=details.package_raw,
                            raw_status_text=details.raw_status_text,
                        )
                        candidates.append(cand)
                    except Exception:
                        continue

            except OmnixVendorError:
                continue
            except Exception:
                continue

        return candidates

    @classmethod
    def evaluate_candidate(
        cls,
        candidate: VendorProcurementCandidate,
        required_quantity: Optional[int] = None,
        exact_mpn_required: bool = True,
        requested_part_number: str = "",
        requested_package: Optional[str] = None,
        requested_footprint: Optional[str] = None,
        requested_manufacturer: Optional[str] = None,
        allowed_manufacturers: Optional[List[str]] = None,
        is_manufacturer_any: bool = False,
        required_specs: Optional[Dict[str, str]] = None,
        required_dimensions: Optional[Dict[str, str]] = None,
        request: Optional[ProcurementRequest] = None,
    ) -> CandidateEvaluation:
        """
        Evaluate candidate eligibility, effective quantity, hard technical constraints, and total cost.
        Governing GAPs: GAP-04, GAP-05, GAP-06.
        """
        # Handle case where request is passed as second positional argument
        if isinstance(required_quantity, ProcurementRequest):
            request = required_quantity
            required_quantity = None

        # Resolve request parameters if request object passed
        if request is not None:
            if required_quantity is None:
                required_quantity = request.required_quantity
            exact_mpn_required = request.exact_mpn_required
            requested_part_number = request.part_number
            if requested_package is None:
                requested_package = request.package
            if requested_footprint is None:
                requested_footprint = request.footprint
            if requested_manufacturer is None:
                requested_manufacturer = request.manufacturer
            if allowed_manufacturers is None:
                allowed_manufacturers = request.allowed_manufacturers
            if not is_manufacturer_any:
                is_manufacturer_any = request.is_manufacturer_any
            if required_specs is None:
                required_specs = request.required_specs
            if required_dimensions is None:
                required_dimensions = request.required_dimensions

        if required_quantity is None:
            required_quantity = 1

        reasons: List[str] = []
        unknown_params: List[str] = []
        primary_failures: List[EvaluationState] = []

        # -------------------------------------------------------------
        # 1. MPN matching
        # -------------------------------------------------------------
        # Option A: Direct Link Staging Without Content Matching (DOC-OMNIX-PLAN-FINAL-003)
        is_explicit_direct = bool(request and request.explicit_vendor_url)
        is_exact = cls._check_mpn_match(candidate.part_number, requested_part_number)
        if exact_mpn_required and requested_part_number and not is_exact and not is_explicit_direct:
            reasons.append(f"MPN mismatch: '{candidate.part_number}' != '{requested_part_number}'")
            primary_failures.append(EvaluationState.INCOMPATIBLE_MPN)

        # -------------------------------------------------------------
        # 2. Manufacturer / Brand Constraint (GAP-06)
        # -------------------------------------------------------------
        effective_any = is_manufacturer_any or (
            requested_manufacturer is not None and requested_manufacturer.strip().upper() == "ANY"
        ) or (
            allowed_manufacturers is not None and any(m.strip().upper() == "ANY" for m in allowed_manufacturers if m)
        )
        if not effective_any and not is_explicit_direct:
            if allowed_manufacturers:
                if not candidate.manufacturer or not candidate.manufacturer.strip():
                    unknown_params.append("manufacturer")
                    reasons.append("Candidate manufacturer is unlisted/unknown on vendor store.")
                    primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
                else:
                    cand_m_norm = normalize_constraint_string(candidate.manufacturer)
                    allowed_m_norms = [normalize_constraint_string(m) for m in allowed_manufacturers if m]
                    if cand_m_norm not in allowed_m_norms:
                        reasons.append(
                            f"Manufacturer mismatch: '{candidate.manufacturer}' not in approved list ({allowed_manufacturers})"
                        )
                        primary_failures.append(EvaluationState.INCOMPATIBLE_MANUFACTURER)
            elif requested_manufacturer and requested_manufacturer.strip():
                if not candidate.manufacturer or not candidate.manufacturer.strip():
                    unknown_params.append("manufacturer")
                    reasons.append(f"Required manufacturer '{requested_manufacturer}' is unlisted/unknown on candidate.")
                    primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
                else:
                    cand_m_norm = normalize_constraint_string(candidate.manufacturer)
                    req_m_norm = normalize_constraint_string(requested_manufacturer)
                    if cand_m_norm != req_m_norm:
                        reasons.append(
                            f"Manufacturer mismatch: '{candidate.manufacturer}' != '{requested_manufacturer}'"
                        )
                        primary_failures.append(EvaluationState.INCOMPATIBLE_MANUFACTURER)

        # -------------------------------------------------------------
        # 3. Package Constraint (GAP-04)
        # -------------------------------------------------------------
        if requested_package and requested_package.strip() and not is_explicit_direct:
            if not candidate.package or not candidate.package.strip():
                unknown_params.append("package")
                reasons.append(f"Required package '{requested_package}' is unlisted/unknown on vendor candidate.")
                primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
            else:
                cand_pkg_norm = normalize_constraint_string(candidate.package)
                req_pkg_norm = normalize_constraint_string(requested_package)
                if cand_pkg_norm != req_pkg_norm:
                    reasons.append(f"Package mismatch: '{candidate.package}' != '{requested_package}'")
                    primary_failures.append(EvaluationState.INCOMPATIBLE_PACKAGE)

        # -------------------------------------------------------------
        # 4. Footprint Constraint (GAP-04) - Evaluated Independently
        # -------------------------------------------------------------
        if requested_footprint and requested_footprint.strip() and not is_explicit_direct:
            cand_fp = candidate.footprint or candidate.specs.get("footprint")
            if not cand_fp or not str(cand_fp).strip():
                unknown_params.append("footprint")
                reasons.append(f"Required footprint '{requested_footprint}' is unlisted/unknown on vendor candidate.")
                primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
            else:
                cand_fp_norm = normalize_constraint_string(str(cand_fp))
                req_fp_norm = normalize_constraint_string(requested_footprint)
                if cand_fp_norm != req_fp_norm:
                    reasons.append(f"Footprint mismatch: '{cand_fp}' != '{requested_footprint}'")
                    primary_failures.append(EvaluationState.INCOMPATIBLE_FOOTPRINT)

        # -------------------------------------------------------------
        # 5. Generic Technical Specifications (GAP-05)
        # -------------------------------------------------------------
        if required_specs and not is_explicit_direct:
            for spec_key, req_val in required_specs.items():
                if not req_val or not str(req_val).strip():
                    continue
                cand_spec_val = candidate.specs.get(spec_key) or candidate.specs.get(spec_key.lower())
                if not cand_spec_val or not str(cand_spec_val).strip():
                    unknown_params.append(spec_key)
                    reasons.append(f"Required parameter '{spec_key}' ({req_val}) is unlisted/unknown on candidate.")
                    primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
                else:
                    if normalize_constraint_string(str(cand_spec_val)) != normalize_constraint_string(str(req_val)):
                        reasons.append(
                            f"Parameter mismatch for '{spec_key}': '{cand_spec_val}' != '{req_val}'"
                        )
                        primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)

        # -------------------------------------------------------------
        # 6. Physical Dimensions (GAP-05)
        # -------------------------------------------------------------
        if required_dimensions and not is_explicit_direct:
            for dim_key, req_val in required_dimensions.items():
                if not req_val or not str(req_val).strip():
                    continue
                cand_dim_val = (
                    candidate.dimensions.get(dim_key)
                    or candidate.specs.get(dim_key)
                    or candidate.specs.get(f"dim_{dim_key}")
                )
                if not cand_dim_val or not str(cand_dim_val).strip():
                    unknown_params.append(f"dimension:{dim_key}")
                    reasons.append(f"Required physical dimension '{dim_key}' ({req_val}) is unlisted/unknown on candidate.")
                    primary_failures.append(EvaluationState.UNKNOWN_REQUIRED_PARAMETER)
                else:
                    if normalize_constraint_string(str(cand_dim_val)) != normalize_constraint_string(str(req_val)):
                        reasons.append(
                            f"Physical dimension mismatch for '{dim_key}': '{cand_dim_val}' != '{req_val}'"
                        )
                        primary_failures.append(EvaluationState.INCOMPATIBLE_DIMENSIONS)

        # -------------------------------------------------------------
        # 7. Stock and Orderability
        # -------------------------------------------------------------
        if not candidate.can_order:
            status_desc = f" (Status: {candidate.raw_status_text})" if candidate.raw_status_text else ""
            reasons.append(f"Item is not orderable{status_desc} (inquiry-only, coming-soon, or sale closed).")
            primary_failures.append(EvaluationState.UNORDERABLE)
        if not candidate.in_stock:
            status_desc = f" (Status: {candidate.raw_status_text})" if candidate.raw_status_text else ""
            reasons.append(f"Item is out of stock{status_desc}.")
            primary_failures.append(EvaluationState.OUT_OF_STOCK)

        # -------------------------------------------------------------
        # 8. Effective Quantity Calculation
        # -------------------------------------------------------------
        effective_qty = required_quantity
        try:
            effective_qty = calculate_effective_quantity(
                needed_qty=required_quantity,
                packaging_step=candidate.order_constraints.packaging_step_raw,
                moq=candidate.order_constraints.moq_raw,
                max_orderable=candidate.order_constraints.max_orderable_raw,
            )
        except Exception as e:
            reasons.append(str(e))
            primary_failures.append(EvaluationState.UNORDERABLE)

        # Check stock quantity sufficiency if site reported positive integer stock
        if candidate.stock_quantity > 0 and candidate.stock_quantity < effective_qty:
            reasons.append(
                f"Insufficient stock on store ({candidate.stock_quantity} available < {effective_qty} needed)."
            )
            primary_failures.append(EvaluationState.INSUFFICIENT_STOCK)

        # -------------------------------------------------------------
        # 9. Pricing
        # -------------------------------------------------------------
        unit_p = effective_unit_price(candidate, effective_qty)
        total_p = effective_total_price(candidate, effective_qty)

        if unit_p is None:
            reasons.append("Price is unavailable or unlisted on vendor store.")
            primary_failures.append(EvaluationState.PRICE_UNAVAILABLE)

        # -------------------------------------------------------------
        # Final State Determination
        # -------------------------------------------------------------
        if not primary_failures and not reasons and not unknown_params:
            final_state = EvaluationState.ELIGIBLE
            is_eligible = True
        else:
            is_eligible = False
            state_priority = [
                EvaluationState.INCOMPATIBLE_MPN,
                EvaluationState.INCOMPATIBLE_MANUFACTURER,
                EvaluationState.INCOMPATIBLE_PACKAGE,
                EvaluationState.INCOMPATIBLE_FOOTPRINT,
                EvaluationState.INCOMPATIBLE_DIMENSIONS,
                EvaluationState.UNKNOWN_REQUIRED_PARAMETER,
                EvaluationState.UNORDERABLE,
                EvaluationState.INSUFFICIENT_STOCK,
                EvaluationState.OUT_OF_STOCK,
                EvaluationState.PRICE_UNAVAILABLE,
            ]
            final_state = EvaluationState.UNORDERABLE
            for st in state_priority:
                if st in primary_failures:
                    final_state = st
                    break

        return CandidateEvaluation(
            candidate=candidate,
            required_quantity=required_quantity,
            effective_quantity=effective_qty,
            effective_unit_price_irr=unit_p,
            effective_total_price_irr=total_p,
            is_eligible=is_eligible,
            is_exact_mpn=is_exact,
            state=final_state,
            rejection_reasons=reasons,
            unknown_parameters=unknown_params,
        )

    def select_best_candidate(
        self,
        evaluations: List[CandidateEvaluation],
    ) -> Optional[CandidateEvaluation]:
        """
        Deterministically select the best candidate according to explicit precedence:
        1. Eligible candidates only (is_eligible == True).
        2. Exact MPN match (is_exact_mpn == True).
        3. Lowest effective total price (effective_total_price_irr ascending).
        4. Lowest effective quantity (effective_quantity ascending).
        5. Deterministic tie-breaker: vendor_id lexical order, vendor_sku lexical order.
        """
        eligible = [e for e in evaluations if e.is_eligible and e.effective_total_price_irr is not None]
        if not eligible:
            return None

        def sort_key(e: CandidateEvaluation):
            return (
                0 if e.is_exact_mpn else 1,
                e.effective_total_price_irr or float('inf'),
                e.effective_quantity,
                e.candidate.vendor_id,
                e.candidate.product_ref.vendor_sku,
            )

        eligible.sort(key=sort_key)
        return eligible[0]

    def build_plan(
        self,
        requests: List[ProcurementRequest],
        vendor_ids: Optional[List[str]] = None,
        progress_callback: Optional[Any] = None,
    ) -> BOMProcurementPlan:
        """
        Build an aggregate procurement plan across multiple requests.
        """
        plan_id = f"PLAN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        created_at = datetime.datetime.now().isoformat()
        results: List[RequestProcurementResult] = []
        total_reqs = len(requests)

        for idx, req in enumerate(requests, start=1):
            if progress_callback:
                try:
                    progress_callback(idx, total_reqs, req.part_number, f"Inspecting candidates for '{req.part_number}' ({idx}/{total_reqs})...")
                except Exception:
                    pass

            cands = self.gather_candidates(req, vendor_ids=vendor_ids)
            evals = [
                self.evaluate_candidate(
                    c,
                    required_quantity=req.required_quantity,
                    exact_mpn_required=req.exact_mpn_required,
                    requested_part_number=req.part_number,
                    request=req,
                )
                for c in cands
            ]

            selected = self.select_best_candidate(evals)

            if selected:
                status = "RESOLVED"
                err_msg = ""
            elif not cands:
                status = "UNRESOLVED"
                if req.explicit_vendor_url:
                    err_msg = f"Failed to resolve or inspect vendor product at URL: {req.explicit_vendor_url}"
                else:
                    err_msg = f"No candidate products found for '{req.part_number}'."
            elif all(not c.in_stock or not c.can_order for c in cands):
                status = "OUT_OF_STOCK"
                err_msg = f"All {len(cands)} candidates for '{req.part_number}' are out of stock or inquiry-only."
            elif any(e.state == EvaluationState.INSUFFICIENT_STOCK for e in evals):
                status = "INSUFFICIENT_STOCK"
                ins_eval = next(e for e in evals if e.state == EvaluationState.INSUFFICIENT_STOCK)
                err_msg = f"Insufficient stock: {ins_eval.effective_quantity} units required by supplier package rules, but only {ins_eval.candidate.stock_quantity} are available. No quantity was added."
            else:
                status = "UNRESOLVED"
                reasons = [r for e in evals for r in e.rejection_reasons if r]
                if reasons:
                    err_msg = f"Found {len(cands)} candidate(s) but none met constraints: {reasons[0]}"
                else:
                    err_msg = f"Found {len(cands)} candidate(s) but none met eligibility constraints."

            results.append(
                RequestProcurementResult(
                    request=req,
                    candidates=cands,
                    evaluations=evals,
                    selected_evaluation=selected,
                    status=status,
                    error_message=err_msg,
                )
            )

        return BOMProcurementPlan(
            plan_id=plan_id,
            created_at=created_at,
            results=results,
        )

    @staticmethod
    def _normalize_url(url: Optional[str]) -> str:
        """Normalize URL for identity comparison (protocol case, trailing slash, www)."""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            path = parsed.path.rstrip("/").lower()
            return f"{netloc}{path}"
        except Exception:
            return (url or "").strip().rstrip("/").lower()

    @staticmethod
    def match_cart_item(
        candidate: VendorProcurementCandidate,
        cart_item: CartItem,
    ) -> Tuple[bool, IdentityMatchTier]:
        """
        Match candidate to a cart line using strict 4-priority cascade (GAP-13).

        Priority 1: Normalized Vendor SKU (only when both sides have valid non-empty SKU)
        Priority 2: Canonical PDP URL (exact normalized match when SKU is unavailable)
        Priority 3: MPN + Manufacturer (deterministic comparison when both are available; differing mfg -> NO_MATCH)
        Priority 4: MPN alone (controlled fallback ONLY when manufacturer genuinely absent on both sides)

        Negative Rules:
        - Product Name is NEVER used as a definitive identity key.
        - Differing valid manufacturers NEVER match even if MPN is identical.
        """
        cand_sku = (candidate.product_ref.vendor_sku or "").strip()
        cart_sku = (cart_item.vendor_sku or "").strip()

        cand_url = UniversalProcurementOrchestrator._normalize_url(candidate.product_ref.pdp_url)
        cart_url = UniversalProcurementOrchestrator._normalize_url(cart_item.pdp_url)

        cand_mpn = normalize_constraint_string(candidate.part_number)
        cart_mpn = normalize_constraint_string(cart_item.mpn or cart_item.vendor_sku)

        cand_mfg = normalize_constraint_string(candidate.manufacturer) if candidate.manufacturer else None
        cart_mfg = normalize_constraint_string(cart_item.manufacturer) if cart_item.manufacturer else None

        # Priority 1: Normalized Vendor SKU
        if cand_sku and cart_sku:
            if normalize_constraint_string(cand_sku) == normalize_constraint_string(cart_sku):
                return True, IdentityMatchTier.EXACT_VENDOR_SKU
            return False, IdentityMatchTier.NO_MATCH

        # Priority 2: Canonical PDP URL
        if cand_url and cart_url:
            if cand_url == cart_url:
                return True, IdentityMatchTier.CANONICAL_PDP_URL

        # Priority 3 & 4: MPN / Manufacturer matching
        if cand_mpn and cart_mpn and cand_mpn == cart_mpn:
            # If both sides specify manufacturer:
            if cand_mfg is not None and cart_mfg is not None:
                if cand_mfg == cart_mfg:
                    return True, IdentityMatchTier.MPN_AND_MANUFACTURER
                else:
                    # Differing manufacturers -> strictly NO_MATCH
                    return False, IdentityMatchTier.NO_MATCH

            # Priority 4: Controlled fallback only when manufacturer is genuinely absent on both sides
            if cand_mfg is None and cart_mfg is None:
                return True, IdentityMatchTier.MPN_ONLY_FALLBACK

            # If one side has mfg and other does not, treat as controlled fallback
            return True, IdentityMatchTier.MPN_ONLY_FALLBACK

        return False, IdentityMatchTier.NO_MATCH

    @staticmethod
    def get_existing_cart_quantity(
        candidate: VendorProcurementCandidate,
        cart: Optional[CartDetails],
    ) -> Tuple[int, List[Tuple[CartItem, IdentityMatchTier]]]:
        """
        Sum the quantities of all cart lines that match the SAME candidate identity (GAP-13).
        Returns (total_existing_quantity, matching_items_with_tiers).
        """
        if not cart or not cart.items:
            return 0, []

        matched: List[Tuple[CartItem, IdentityMatchTier]] = []
        total_qty = 0

        for item in cart.items:
            is_match, tier = UniversalProcurementOrchestrator.match_cart_item(candidate, item)
            if is_match:
                matched.append((item, tier))
                total_qty += item.quantity

        return total_qty, matched

    @staticmethod
    def calculate_cart_delta(
        candidate: VendorProcurementCandidate,
        target_orderable_qty: int,
        cart: Optional[CartDetails] = None,
    ) -> Tuple[int, int, bool, Optional[IdentityMatchTier]]:
        """
        Calculate cart delta quantity deterministically (GAP-13).

        Q_existing = SUM(quantities of all cart lines matching candidate)
        Delta_Q = max(0, target_orderable_qty - Q_existing)

        Returns:
            (existing_qty, delta_qty, is_noop, primary_match_tier)
        """
        if not cart or not cart.items:
            return 0, target_orderable_qty, False, None

        existing_qty, matched = UniversalProcurementOrchestrator.get_existing_cart_quantity(candidate, cart)
        primary_tier = matched[0][1] if matched else None

        if existing_qty >= target_orderable_qty:
            return existing_qty, 0, True, primary_tier

        delta_qty = target_orderable_qty - existing_qty
        return existing_qty, delta_qty, False, primary_tier

    def stage_candidate(
        self,
        candidate: VendorProcurementCandidate,
        quantity: int,
        sync_cart: bool = True,
        cached_cart: Optional[CartDetails] = None,
    ) -> CartMutationResult:
        """
        Stage a candidate into the vendor's browser cart (strictly non-destructive, GAP-13).
        
        If sync_cart=True:
        1. Check vendor enabled state upfront (bypasses disabled vendors with 0 network calls).
        2. Inspect cart (or use cached_cart).
        3. Reconcile quantity: Delta_Q = max(0, quantity - Q_existing).
        4. Enforce max_orderable limit if applicable.
        5. If Delta_Q == 0 -> Return deterministic No-Op success.
        6. If Delta_Q > 0 -> Call adapter.add_to_cart(candidate.product_ref, Delta_Q).
        """
        # 1. Vendor Enabled Check (GAP-11)
        if not self.registry.is_vendor_enabled(candidate.vendor_id):
            return CartMutationResult(
                vendor_id=candidate.vendor_id,
                vendor_sku=candidate.product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=0,
                success=False,
                error_category="VENDOR_DISABLED",
                raw_vendor_message=f"Vendor '{candidate.vendor_id}' is disabled in settings.",
                initial_cart_qty=0,
                target_qty=quantity,
                delta_qty=0,
                is_noop=False,
            )

        adapter = self.registry.get_adapter(candidate.vendor_id)

        if not sync_cart:
            res = adapter.add_to_cart(candidate.product_ref, quantity)
            res.target_qty = quantity
            res.delta_qty = quantity
            return res

        # 2. Cart Inspection & Delta Synchronization (GAP-13)
        try:
            cart = cached_cart if cached_cart is not None else adapter.inspect_cart()
        except Exception as e:
            err_msg = str(e)
            return CartMutationResult(
                vendor_id=candidate.vendor_id,
                vendor_sku=candidate.product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=0,
                success=False,
                error_category="CART_INSPECTION_FAILED",
                raw_vendor_message=f"Cart inspection failed: {err_msg}",
                initial_cart_qty=0,
                target_qty=quantity,
                delta_qty=0,
                is_noop=False,
            )

        existing_qty, delta_qty, is_noop, match_tier = self.calculate_cart_delta(
            candidate=candidate,
            target_orderable_qty=quantity,
            cart=cart,
        )

        confidence = "NONE"
        if match_tier in (IdentityMatchTier.EXACT_VENDOR_SKU, IdentityMatchTier.CANONICAL_PDP_URL, IdentityMatchTier.MPN_AND_MANUFACTURER):
            confidence = "HIGH"
        elif match_tier == IdentityMatchTier.MPN_ONLY_FALLBACK:
            confidence = "CONTROLLED_FALLBACK"

        # 3. Check max_orderable limit
        max_limit = candidate.order_constraints.max_orderable_raw
        if max_limit is not None and max_limit >= 1:
            if (existing_qty + delta_qty) > max_limit:
                return CartMutationResult(
                    vendor_id=candidate.vendor_id,
                    vendor_sku=candidate.product_ref.vendor_sku,
                    requested_quantity=quantity,
                    actual_quantity_staged=0,
                    success=False,
                    error_category="MAX_QUANTITY_EXCEEDED",
                    raw_vendor_message=f"Total cart quantity ({existing_qty + delta_qty}) exceeds max orderable limit ({max_limit}).",
                    initial_cart_qty=existing_qty,
                    target_qty=quantity,
                    delta_qty=delta_qty,
                    is_noop=False,
                    match_tier=match_tier,
                    match_confidence=confidence,
                )

        # 4. Idempotent No-Op Check
        if is_noop or delta_qty == 0:
            return CartMutationResult(
                vendor_id=candidate.vendor_id,
                vendor_sku=candidate.product_ref.vendor_sku,
                requested_quantity=quantity,
                actual_quantity_staged=0,
                success=True,
                raw_vendor_message=f"Already satisfied in cart ({existing_qty}/{quantity} pcs)",
                cart_total_items=cart.total_items if cart else 0,
                initial_cart_qty=existing_qty,
                target_qty=quantity,
                delta_qty=0,
                is_noop=True,
                match_tier=match_tier,
                match_confidence=confidence,
            )

        # 5. Execute Staging for Shortage Delta
        mutation = adapter.add_to_cart(candidate.product_ref, delta_qty)
        mutation.initial_cart_qty = existing_qty
        mutation.target_qty = quantity
        mutation.delta_qty = delta_qty
        mutation.is_noop = False
        mutation.match_tier = match_tier
        mutation.match_confidence = confidence

        return mutation

    def stage_procurement_plan(
        self,
        plan: BOMProcurementPlan,
        sync_cart: bool = True,
    ) -> Dict[str, Any]:
        """
        Stage all resolved candidates in a procurement plan with vendor isolation (GAP-13).
        """
        results: List[Dict[str, Any]] = []
        total_items = len(plan.results)
        successful_count = 0
        noop_count = 0
        staged_count = 0
        failed_count = 0

        vendor_items: Dict[str, List[Tuple[RequestProcurementResult, VendorProcurementCandidate, int]]] = {}
        for r in plan.results:
            if r.status == "RESOLVED" and r.selected_evaluation:
                cand = r.selected_evaluation.candidate
                eff_qty = r.selected_evaluation.effective_quantity
                vendor_items.setdefault(cand.vendor_id, []).append((r, cand, eff_qty))
            else:
                failed_count += 1
                results.append({
                    "part": r.request.part_number,
                    "status": "UNRESOLVED",
                    "vendor_id": None,
                    "qty": 0,
                    "msg": r.error_message or "Candidate resolution failed",
                })

        for vendor_id, items in vendor_items.items():
            if not self.registry.is_vendor_enabled(vendor_id):
                for r, cand, eff_qty in items:
                    failed_count += 1
                    results.append({
                        "part": r.request.part_number,
                        "status": "FAILED",
                        "vendor_id": vendor_id,
                        "qty": 0,
                        "msg": f"Vendor '{vendor_id}' is disabled in settings",
                    })
                continue

            adapter = self.registry.get_adapter(vendor_id)
            cached_cart = None
            if sync_cart:
                try:
                    cached_cart = adapter.inspect_cart()
                except Exception as e:
                    for r, cand, eff_qty in items:
                        failed_count += 1
                        results.append({
                            "part": r.request.part_number,
                            "status": "FAILED",
                            "vendor_id": vendor_id,
                            "qty": 0,
                            "msg": f"Cart inspection failed for {vendor_id}: {str(e)}",
                        })
                    continue

            for r, cand, eff_qty in items:
                mut = self.stage_candidate(cand, eff_qty, sync_cart=sync_cart, cached_cart=cached_cart)
                if mut.success:
                    successful_count += 1
                    if mut.is_noop:
                        noop_count += 1
                    else:
                        staged_count += 1
                    results.append({
                        "part": r.request.part_number,
                        "status": "SUCCESS",
                        "vendor_id": vendor_id,
                        "qty": mut.actual_quantity_staged,
                        "initial_qty": mut.initial_cart_qty,
                        "target_qty": mut.target_qty,
                        "delta_qty": mut.delta_qty,
                        "is_noop": mut.is_noop,
                        "msg": mut.raw_vendor_message or ("No-op" if mut.is_noop else "Added to cart"),
                    })
                else:
                    failed_count += 1
                    results.append({
                        "part": r.request.part_number,
                        "status": "FAILED",
                        "vendor_id": vendor_id,
                        "qty": 0,
                        "msg": mut.raw_vendor_message or mut.error_category or "Staging failed",
                    })

        return {
            "success": failed_count == 0,
            "total_items": total_items,
            "successful_count": successful_count,
            "noop_count": noop_count,
            "staged_count": staged_count,
            "failed_count": failed_count,
            "results": results,
        }


    def _resolve_target_vendors(
        self,
        request: ProcurementRequest,
        vendor_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Resolve list of target vendor IDs for a request, respecting vendor enabled state (GAP-11)."""
        # 1. Explicit vendor URL
        if request.explicit_vendor_url:
            clean_url = str(request.explicit_vendor_url).strip()
            if not clean_url:
                return []
            resolved_vid = None
            if hasattr(self.registry, "resolve_adapter_for_url"):
                try:
                    _, reg_meta = self.registry.resolve_adapter_for_url(clean_url, enabled_only=True)
                    if reg_meta is not None:
                        resolved_vid = getattr(reg_meta, "vendor_id", None)
                except Exception:
                    resolved_vid = None
            elif hasattr(self.registry, "get_vendor_for_url"):
                resolved_vid = self.registry.get_vendor_for_url(clean_url, enabled_only=True)

            if not resolved_vid:
                return []

            if request.explicit_vendor_id:
                if str(request.explicit_vendor_id).strip() != resolved_vid:
                    return []

            if vendor_ids and resolved_vid not in vendor_ids:
                return []

            return [resolved_vid]

        # 2. Explicit vendor ID (when no explicit URL)
        if request.explicit_vendor_id:
            if self.registry.has_vendor(request.explicit_vendor_id):
                if self.registry.is_vendor_enabled(request.explicit_vendor_id):
                    return [request.explicit_vendor_id]
                return []  # Explicit vendor is disabled
            raise UnknownVendorError(f"Requested vendor '{request.explicit_vendor_id}' is not registered.", vendor_id=request.explicit_vendor_id)

        # 3. Caller-specified vendor IDs (filtered by enabled state)
        if vendor_ids:
            return [v for v in vendor_ids if self.registry.has_vendor(v) and self.registry.is_vendor_enabled(v)]

        # 4. Default: all enabled registered vendors
        return self.registry.get_enabled_vendors()

    def _inspect_explicit_url(
        self,
        adapter: Any,
        vendor_id: str,
        url: str,
    ) -> Optional[VendorProcurementCandidate]:
        """Resolve and inspect a candidate from an explicit product URL."""
        try:
            pref = adapter.resolve_product(url)
            details = adapter.inspect_product(pref)
            stock = adapter.inspect_stock(pref)
            constraints = None
            if hasattr(adapter, "determine_order_constraints"):
                try:
                    constraints = adapter.determine_order_constraints(pref)
                except Exception:
                    constraints = None

            raw_specs = getattr(details, "specs", {}) or {}
            raw_dims = getattr(details, "dimensions", {}) or {}

            price_tiers: List[PriceTier] = []
            raw_tiers = getattr(details, "raw_data", {}).get("price_tiers", []) or getattr(details, "price_tiers", [])
            for t in raw_tiers:
                if isinstance(t, dict) and "min_quantity" in t and "unit_price_irr" in t:
                    price_tiers.append(PriceTier(min_quantity=t["min_quantity"], unit_price_irr=t["unit_price_irr"], raw_label=t.get("raw_label", "")))
                elif isinstance(t, PriceTier):
                    price_tiers.append(t)

            return VendorProcurementCandidate(
                vendor_id=vendor_id,
                part_number=details.mpn or pref.vendor_sku,
                product_ref=pref,
                description=details.mpn or "",
                in_stock=stock.in_stock,
                stock_quantity=stock.stock_quantity,
                can_order=details.can_order,
                base_unit_price_irr=details.price_irr,
                price_tiers=price_tiers,
                order_constraints=constraints or details.order_constraints or OrderConstraints(),
                manufacturer=details.manufacturer,
                package=details.package_raw,
                footprint=getattr(details, "footprint_raw", None) or getattr(details, "footprint", None) or raw_specs.get("footprint") or details.package_raw,
                dimensions=raw_dims,
                raw_status_text=details.raw_status_text,
                specs=raw_specs,
            )
        except Exception:
            return None

    @staticmethod
    def _check_mpn_match(candidate_mpn: str, requested_mpn: str) -> bool:
        """Normalize and compare MPNs."""
        if not candidate_mpn or not requested_mpn:
            return False
        c_norm = normalize_constraint_string(candidate_mpn)
        r_norm = normalize_constraint_string(requested_mpn)
        return c_norm == r_norm or r_norm in c_norm or c_norm in r_norm
