"""
Omnix Core - Universal Procurement Orchestrator
Governing Document: docs/PROCUREMENT/PHASE9_CONTRACT_GAP_ANALYSIS.md Section 14
"""

import datetime
from typing import List, Optional, Dict, Any

from core.errors import OmnixVendorError, UnknownVendorError
from core.models import CartMutationResult, ProductReference, OrderConstraints
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
        target_vendors = self._resolve_target_vendors(request, vendor_ids)

        for vid in target_vendors:
            try:
                adapter = self.registry.get_adapter(vid)

                # Case A: Explicit product URL provided
                if request.explicit_vendor_url:
                    candidate = self._inspect_explicit_url(adapter, vid, request.explicit_vendor_url)
                    if candidate:
                        candidates.append(candidate)
                    continue

                # Case B: Catalog search by part number
                search_res = adapter.search_part(request.part_number)
                if not search_res or not search_res.items:
                    continue

                # Inspect matching search items
                for item in search_res.items:
                    try:
                        pref = adapter.resolve_product(item.pdp_url or item.vendor_sku)
                        details = adapter.inspect_product(pref)
                        stock = adapter.inspect_stock(pref)
                        constraints = adapter.determine_order_constraints(pref)

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

    def evaluate_candidate(
        self,
        candidate: VendorProcurementCandidate,
        required_quantity: int,
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
        # Resolve request parameters if request object passed
        if request is not None:
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

        reasons: List[str] = []
        unknown_params: List[str] = []
        primary_failures: List[EvaluationState] = []

        # -------------------------------------------------------------
        # 1. MPN matching
        # -------------------------------------------------------------
        is_exact = self._check_mpn_match(candidate.part_number, requested_part_number)
        if exact_mpn_required and requested_part_number and not is_exact:
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
        if not effective_any:
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
        if requested_package and requested_package.strip():
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
        if requested_footprint and requested_footprint.strip():
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
        if required_specs:
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
        if required_dimensions:
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
            reasons.append("Item is not orderable (inquiry-only, coming-soon, or sale closed).")
            primary_failures.append(EvaluationState.UNORDERABLE)
        if not candidate.in_stock:
            reasons.append("Item is out of stock.")
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
            primary_failures.append(EvaluationState.OUT_OF_STOCK)

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
    ) -> BOMProcurementPlan:
        """
        Build an aggregate procurement plan across multiple requests.
        """
        plan_id = f"PLAN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        created_at = datetime.datetime.now().isoformat()
        results: List[RequestProcurementResult] = []

        for req in requests:
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
                err_msg = f"No candidate products found for '{req.part_number}'."
            elif all(not c.in_stock or not c.can_order for c in cands):
                status = "OUT_OF_STOCK"
                err_msg = f"All {len(cands)} candidates for '{req.part_number}' are out of stock or inquiry-only."
            else:
                status = "UNRESOLVED"
                err_msg = f"Found {len(cands)} candidates but none met eligibility constraints."

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

    def stage_candidate(
        self,
        candidate: VendorProcurementCandidate,
        quantity: int,
    ) -> CartMutationResult:
        """
        Stage a candidate into the vendor's browser cart (strictly non-destructive).
        """
        adapter = self.registry.get_adapter(candidate.vendor_id)
        return adapter.add_to_cart(candidate.product_ref, quantity)

    def _resolve_target_vendors(
        self,
        request: ProcurementRequest,
        vendor_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Resolve list of target vendor IDs for a request."""
        # 1. Explicit vendor ID
        if request.explicit_vendor_id:
            if self.registry.has_vendor(request.explicit_vendor_id):
                return [request.explicit_vendor_id]
            raise UnknownVendorError(f"Requested vendor '{request.explicit_vendor_id}' is not registered.", vendor_id=request.explicit_vendor_id)

        # 2. Explicit vendor URL
        if request.explicit_vendor_url:
            resolved_vid = self.registry.get_vendor_for_url(request.explicit_vendor_url)
            if resolved_vid:
                return [resolved_vid]
            return []

        # 3. Caller-specified vendor IDs
        if vendor_ids:
            return [v for v in vendor_ids if self.registry.has_vendor(v)]

        # 4. Default: all registered vendors
        return self.registry.list_vendors()

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
            constraints = adapter.determine_order_constraints(pref)

            raw_specs = getattr(details, "specs", {}) or {}
            raw_dims = getattr(details, "dimensions", {}) or {}

            return VendorProcurementCandidate(
                vendor_id=vendor_id,
                part_number=details.mpn or pref.vendor_sku,
                product_ref=pref,
                description=details.mpn or "",
                in_stock=stock.in_stock,
                stock_quantity=stock.stock_quantity,
                can_order=details.can_order,
                base_unit_price_irr=details.price_irr,
                order_constraints=constraints or details.order_constraints or OrderConstraints(),
                manufacturer=details.manufacturer,
                package=details.package_raw,
                footprint=getattr(details, "footprint_raw", None) or getattr(details, "footprint", None) or raw_specs.get("footprint"),
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
