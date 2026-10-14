"""
Omnix UI — Direct Quick Order Dialog (GAP-02 & GAP-03)
Provides standalone procurement workflows for Direct MPN Search and Direct Product URL Staging
without requiring an existing Excel BOM or Inventory datastore.
100% reuses UniversalProcurementOrchestrator and VendorRegistry with GAP-13 delta synchronization.
"""

import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import CartMutationResult, ProductReference
from core.procurement.models import (
    CandidateEvaluation,
    EvaluationState,
    ManufacturerRule,
    ProcurementMode,
    ProcurementRequest,
    VendorProcurementCandidate,
)
from core.procurement.orchestrator import UniversalProcurementOrchestrator
from core.procurement.registry import VendorRegistry, default_registry
from ui.widgets.number_stepper import NumberStepperWidget
def validate_vendor_pdp_url(
    url: str, registry: Optional[VendorRegistry] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that a URL is a recognized, enabled vendor AND matches a canonical product detail page (PDP).
    
    Returns:
        (is_valid, vendor_id, error_message)
    """
    clean_url = (url or "").strip()
    if not clean_url:
        return False, None, "Product URL is required and cannot be empty."

    reg = registry or VendorRegistry.get_default_registry()
    vendor_id = reg.get_vendor_for_url(clean_url, enabled_only=False)
    if not vendor_id:
        return False, None, "The provided URL domain is not recognized as a registered vendor (supported: Lion, Javan, RoboEq)."

    if not reg.is_vendor_enabled(vendor_id):
        v_title = vendor_id.replace("vendor_", "").title()
        return False, vendor_id, f"Vendor '{v_title}' is currently disabled in Settings. Please enable it to proceed."

    # Validate PDP path via vendor adapter - fail closed
    try:
        adapter = reg.get_adapter(vendor_id)
    except Exception as e:
        return False, vendor_id, f"Vendor adapter for '{vendor_id}' is unavailable: {e}"

    if not hasattr(adapter, "is_pdp_url") or not callable(adapter.is_pdp_url):
        return False, vendor_id, f"Vendor adapter for '{vendor_id}' does not support URL validation capability."

    try:
        if not adapter.is_pdp_url(clean_url):
            return False, vendor_id, "The provided URL is not a recognized Product Detail Page (PDP). Home, search, cart, and category links cannot be ordered."
    except Exception as e:
        return False, vendor_id, f"Vendor adapter error during URL validation: {e}"

    return True, vendor_id, None


class MPNSearchWorker(QThread):
    """Background thread to gather and evaluate candidates across enabled vendors for Direct MPN."""

    results_signal = pyqtSignal(list, list)  # (candidates, evaluations)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        request: ProcurementRequest,
        vendor_ids: Optional[List[str]] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
    ):
        super().__init__()
        self.request = request
        self.vendor_ids = vendor_ids
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator()

    def run(self):
        try:
            candidates = self.orchestrator.gather_candidates(
                self.request, vendor_ids=self.vendor_ids
            )
            evaluations = [
                self.orchestrator.evaluate_candidate(c, request=self.request)
                for c in candidates
            ]
            self.results_signal.emit(candidates, evaluations)
        except Exception as e:
            self.error_signal.emit(str(e))


class URLInspectWorker(QThread):
    """Background thread to inspect product, stock, and constraints for Direct URL."""

    result_signal = pyqtSignal(object, object)  # (candidate, evaluation)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        quantity: int,
        vendor_id: str,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
    ):
        super().__init__()
        self.url = url
        self.quantity = quantity
        self.vendor_id = vendor_id
        self.registry = registry or default_registry
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator(registry=self.registry)

    def run(self):
        try:
            adapter = self.registry.get_adapter(self.vendor_id)
            pref = adapter.resolve_product(self.url)
            details = adapter.inspect_product(pref)
            stock = adapter.inspect_stock(pref)
            constraints = adapter.determine_order_constraints(pref)

            raw_specs = getattr(details, "specs", {}) or {}
            raw_dims = getattr(details, "dimensions", {}) or {}

            candidate = VendorProcurementCandidate(
                vendor_id=self.vendor_id,
                part_number=details.mpn or pref.vendor_sku or "UNKNOWN",
                product_ref=pref,
                description=details.mpn or "",
                in_stock=stock.in_stock,
                stock_quantity=stock.stock_quantity,
                can_order=details.can_order,
                base_unit_price_irr=details.price_irr,
                order_constraints=constraints or details.order_constraints,
                manufacturer=details.manufacturer,
                package=details.package_raw,
                footprint=getattr(details, "footprint_raw", None) or raw_specs.get("footprint"),
                dimensions=raw_dims,
                raw_status_text=details.raw_status_text,
                specs=raw_specs,
            )

            req = ProcurementRequest(
                part_number=candidate.part_number,
                required_quantity=self.quantity,
                explicit_vendor_id=self.vendor_id,
                explicit_vendor_url=self.url,
                mode=ProcurementMode.DIRECT_BOM,
                exact_mpn_required=False,
            )
            evaluation = self.orchestrator.evaluate_candidate(candidate, request=req)
            self.result_signal.emit(candidate, evaluation)
        except Exception as e:
            self.error_signal.emit(str(e))


class CartStageWorker(QThread):
    """Background thread to execute idempotent cart staging with delta synchronization."""

    finished_signal = pyqtSignal(object)  # CartMutationResult
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        candidate: VendorProcurementCandidate,
        quantity: int,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
    ):
        super().__init__()
        self.candidate = candidate
        self.quantity = quantity
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator()

    def run(self):
        try:
            res = self.orchestrator.stage_candidate(
                self.candidate, self.quantity, sync_cart=True
            )
            self.finished_signal.emit(res)
        except Exception as e:
            self.error_signal.emit(str(e))


class QuickOrderDialog(QDialog):
    """
    Direct Quick Order dialog supporting standalone MPN discovery (GAP-02)
    and Direct URL inspection & cart staging (GAP-03).
    """

    def __init__(
        self,
        inventory_loader=None,
        on_stock_updated=None,
        registry: Optional[VendorRegistry] = None,
        orchestrator: Optional[UniversalProcurementOrchestrator] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.inventory_loader = inventory_loader
        self.on_stock_updated = on_stock_updated
        self.registry = registry or VendorRegistry.get_default_registry()
        self.orchestrator = orchestrator or UniversalProcurementOrchestrator(registry=self.registry)

        self.setWindowTitle("⚡ Quick Order — Standalone MPN & URL Procurement")
        self.resize(1020, 680)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.mpn_candidates: List[VendorProcurementCandidate] = []
        self.mpn_evaluations: List[CandidateEvaluation] = []
        self.selected_mpn_eval_idx: Optional[int] = None

        self.url_candidate: Optional[VendorProcurementCandidate] = None
        self.url_evaluation: Optional[CandidateEvaluation] = None

        self.mpn_worker: Optional[MPNSearchWorker] = None
        self.url_worker: Optional[URLInspectWorker] = None
        self.stage_worker: Optional[CartStageWorker] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Title
        title_lbl = QLabel("⚡ Quick Order Procurement")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Procure parts directly across registered vendors (Lion, Javan, RoboEq) by Part Number or Product URL."
        )
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(sub_lbl)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_mpn_tab(), "🔍 Direct MPN Sourcing (GAP-02)")
        self.tabs.addTab(self._create_url_tab(), "🌐 Direct Product URL (GAP-03)")
        layout.addWidget(self.tabs)

        # Global Bottom Action Bar
        bottom_bar = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        bottom_bar.addWidget(self.progress_bar)

        self.status_msg_lbl = QLabel("")
        self.status_msg_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #38bdf8;")
        bottom_bar.addWidget(self.status_msg_lbl)

        bottom_bar.addStretch()

        self.btn_dismiss = QPushButton("Close")
        self.btn_dismiss.setObjectName("secondaryBtn")
        self.btn_dismiss.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_dismiss)

        layout.addLayout(bottom_bar)

    def _create_mpn_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(10)

        # Form Controls Frame
        form_frame = QFrame()
        form_frame.setObjectName("ribbonFrame")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.setSpacing(8)

        # Row 1: MPN & Quantity
        row1 = QHBoxLayout()
        lbl_mpn = QLabel("Part Number / MPN:*")
        lbl_mpn.setStyleSheet("font-weight: bold; color: #f8fafc;")
        row1.addWidget(lbl_mpn)

        self.mpn_input = QLineEdit()
        self.mpn_input.setPlaceholderText("e.g. NE555P, STM32F103C8T6, 1N4148")
        self.mpn_input.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                font-family: Consolas, monospace;
                padding: 5px 8px;
            }
            QLineEdit:focus { border-color: #38bdf8; }
        """)
        row1.addWidget(self.mpn_input, 2)

        lbl_qty = QLabel("Quantity:*")
        lbl_qty.setStyleSheet("font-weight: bold; color: #f8fafc;")
        row1.addWidget(lbl_qty)

        self.mpn_qty_stepper = NumberStepperWidget(value=1, min_val=1, max_val=100000)
        row1.addWidget(self.mpn_qty_stepper)

        lbl_vendor = QLabel("Target Vendors:")
        lbl_vendor.setStyleSheet("font-weight: bold; color: #f8fafc;")
        row1.addWidget(lbl_vendor)

        self.mpn_vendor_combo = QComboBox()
        self.mpn_vendor_combo.addItem("🌐 All Enabled Vendors", None)
        self.mpn_vendor_combo.addItem("🦁 Lion Electronic", "vendor_lion")
        self.mpn_vendor_combo.addItem("⚡ Javan Payesh", "vendor_javan")
        self.mpn_vendor_combo.addItem("🤖 RoboEq", "vendor_roboeq")
        self.mpn_vendor_combo.setStyleSheet("""
            QComboBox {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #38bdf8;
                font-weight: bold;
                padding: 4px 8px;
                min-width: 170px;
            }
        """)
        row1.addWidget(self.mpn_vendor_combo)

        form_layout.addLayout(row1)

        # Row 2: Brand Rule & Package/Footprint constraints
        row2 = QHBoxLayout()
        lbl_brand_rule = QLabel("Brand Rule:")
        lbl_brand_rule.setStyleSheet("color: #94a3b8;")
        row2.addWidget(lbl_brand_rule)

        self.mpn_brand_rule_combo = QComboBox()
        self.mpn_brand_rule_combo.addItem("ANY (Generic Allowed)", ManufacturerRule.ANY)
        self.mpn_brand_rule_combo.addItem("EXACT (Specific Manufacturer)", ManufacturerRule.EXACT)
        self.mpn_brand_rule_combo.addItem("APPROVED_LIST (Approved List)", ManufacturerRule.APPROVED_LIST)
        self.mpn_brand_rule_combo.currentIndexChanged.connect(self._on_mpn_brand_rule_changed)
        row2.addWidget(self.mpn_brand_rule_combo)

        self.mpn_brand_input = QLineEdit()
        self.mpn_brand_input.setPlaceholderText("Manufacturer name (e.g. Texas Instruments)")
        self.mpn_brand_input.setEnabled(False)
        self.mpn_brand_input.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 12px;
                padding: 4px 6px;
            }
        """)
        row2.addWidget(self.mpn_brand_input, 2)

        lbl_pkg = QLabel("Package:")
        lbl_pkg.setStyleSheet("color: #94a3b8;")
        row2.addWidget(lbl_pkg)

        self.mpn_pkg_input = QLineEdit()
        self.mpn_pkg_input.setPlaceholderText("e.g. DIP-8, SOIC-8")
        self.mpn_pkg_input.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 12px;
                padding: 4px 6px;
                max-width: 120px;
            }
        """)
        row2.addWidget(self.mpn_pkg_input)

        form_layout.addLayout(row2)

        # Search Trigger Button
        self.btn_mpn_search = QPushButton("🔍 Search & Discover Candidates Across Vendors")
        self.btn_mpn_search.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #38bdf8; color: #0f172a; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self.btn_mpn_search.clicked.connect(self._on_mpn_search_clicked)
        form_layout.addWidget(self.btn_mpn_search)

        layout.addWidget(form_frame)

        # Candidates Table
        self.mpn_table = QTableWidget()
        self.mpn_table.setColumnCount(12)
        self.mpn_table.setHorizontalHeaderLabels([
            "Select", "Vendor", "SKU", "MPN", "Manufacturer", "Package",
            "Stock", "MOQ", "Step", "Unit Price (IRR)", "Total Cost (IRR)", "Status & Compatibility"
        ])
        header = self.mpn_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        self.mpn_table.verticalHeader().setVisible(False)
        self.mpn_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mpn_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mpn_table.itemDoubleClicked.connect(self._on_mpn_table_double_clicked)
        layout.addWidget(self.mpn_table)

        # MPN Bottom Actions
        actions_layout = QHBoxLayout()

        self.btn_mpn_open_cart = QPushButton("🛒 Open Vendor Cart")
        self.btn_mpn_open_cart.setObjectName("secondaryBtn")
        self.btn_mpn_open_cart.hide()
        self.btn_mpn_open_cart.clicked.connect(self._on_open_cart_clicked)
        actions_layout.addWidget(self.btn_mpn_open_cart)

        self.btn_mpn_confirm_stock = QPushButton("💰 Confirm Payment & Add Stock")
        self.btn_mpn_confirm_stock.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        self.btn_mpn_confirm_stock.hide()
        self.btn_mpn_confirm_stock.clicked.connect(self._on_confirm_stock_clicked)
        actions_layout.addWidget(self.btn_mpn_confirm_stock)

        actions_layout.addStretch()

        self.btn_mpn_stage = QPushButton("🛒 Add Selected Candidate to Cart")
        self.btn_mpn_stage.setEnabled(False)
        self.btn_mpn_stage.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self.btn_mpn_stage.clicked.connect(self._on_mpn_stage_clicked)
        actions_layout.addWidget(self.btn_mpn_stage)

        layout.addLayout(actions_layout)
        return widget

    def _create_url_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(12)

        # URL Input Frame
        frame = QFrame()
        frame.setObjectName("ribbonFrame")
        f_layout = QVBoxLayout(frame)
        f_layout.setContentsMargins(12, 12, 12, 12)
        f_layout.setSpacing(10)

        r1 = QHBoxLayout()
        lbl_url = QLabel("Product URL:*")
        lbl_url.setStyleSheet("font-weight: bold; color: #f8fafc;")
        r1.addWidget(lbl_url)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("e.g. https://lionelectronic.ir/products/2070-NE555P or https://roboeq.ir/products/detail/0101001/...")
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: #0b101b;
                border: 1.5px solid #22324e;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 12px;
                font-family: Consolas, monospace;
                padding: 6px 8px;
            }
            QLineEdit:focus { border-color: #38bdf8; }
        """)
        r1.addWidget(self.url_input, 3)

        lbl_qty = QLabel("Quantity:*")
        lbl_qty.setStyleSheet("font-weight: bold; color: #f8fafc;")
        r1.addWidget(lbl_qty)

        self.url_qty_stepper = NumberStepperWidget(value=1, min_val=1, max_val=100000)
        r1.addWidget(self.url_qty_stepper)
        f_layout.addLayout(r1)

        self.btn_url_inspect = QPushButton("🔍 Inspect Product & Check Price")
        self.btn_url_inspect.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #38bdf8; color: #0f172a; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self.btn_url_inspect.clicked.connect(self._on_url_inspect_clicked)
        f_layout.addWidget(self.btn_url_inspect)

        layout.addWidget(frame)

        # Inspection Details Frame / Table
        self.url_details_table = QTableWidget()
        self.url_details_table.setColumnCount(2)
        self.url_details_table.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.url_details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.url_details_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.url_details_table.verticalHeader().setVisible(False)
        self.url_details_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.url_details_table)

        # URL Bottom Actions
        actions_layout = QHBoxLayout()

        self.btn_url_open_cart = QPushButton("🛒 Open Vendor Cart")
        self.btn_url_open_cart.setObjectName("secondaryBtn")
        self.btn_url_open_cart.hide()
        self.btn_url_open_cart.clicked.connect(self._on_open_cart_clicked)
        actions_layout.addWidget(self.btn_url_open_cart)

        self.btn_url_confirm_stock = QPushButton("💰 Confirm Payment & Add Stock")
        self.btn_url_confirm_stock.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        self.btn_url_confirm_stock.hide()
        self.btn_url_confirm_stock.clicked.connect(self._on_confirm_stock_clicked)
        actions_layout.addWidget(self.btn_url_confirm_stock)

        actions_layout.addStretch()

        self.btn_url_stage = QPushButton("🛒 Add Product to Cart")
        self.btn_url_stage.setEnabled(False)
        self.btn_url_stage.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self.btn_url_stage.clicked.connect(self._on_url_stage_clicked)
        actions_layout.addWidget(self.btn_url_stage)

        layout.addLayout(actions_layout)
        return widget

    def _on_mpn_brand_rule_changed(self, index: int):
        rule = self.mpn_brand_rule_combo.currentData()
        if rule == ManufacturerRule.ANY:
            self.mpn_brand_input.setEnabled(False)
            self.mpn_brand_input.clear()
            self.mpn_brand_input.setPlaceholderText("Any manufacturer allowed (generic)")
        elif rule == ManufacturerRule.EXACT:
            self.mpn_brand_input.setEnabled(True)
            self.mpn_brand_input.setPlaceholderText("Exact manufacturer name (e.g. STMicroelectronics)")
        elif rule == ManufacturerRule.APPROVED_LIST:
            self.mpn_brand_input.setEnabled(True)
            self.mpn_brand_input.setPlaceholderText("Comma-separated approved brands (e.g. TI, ST, NXP)")

    def _on_mpn_search_clicked(self):
        raw_mpn = self.mpn_input.text().strip()
        if not raw_mpn:
            QMessageBox.warning(
                self,
                "Part Number Required",
                "Please enter a valid Part Number / MPN. Empty or missing MPN is strictly prohibited."
            )
            self.mpn_input.setFocus()
            return

        qty = self.mpn_qty_stepper.value()
        brand_rule = self.mpn_brand_rule_combo.currentData()
        brand_text = self.mpn_brand_input.text().strip()
        pkg = self.mpn_pkg_input.text().strip() or None

        is_any = (brand_rule == ManufacturerRule.ANY)
        exact_mfg = brand_text if brand_rule == ManufacturerRule.EXACT and brand_text else None
        allowed_mfgs = [b.strip() for b in brand_text.split(",") if b.strip()] if brand_rule == ManufacturerRule.APPROVED_LIST else None

        req = ProcurementRequest(
            part_number=raw_mpn,
            required_quantity=qty,
            mode=ProcurementMode.DIRECT_BOM,
            is_manufacturer_any=is_any,
            manufacturer=exact_mfg,
            allowed_manufacturers=allowed_mfgs,
            package=pkg,
        )

        selected_vendor_id = self.mpn_vendor_combo.currentData()
        vendor_ids = [selected_vendor_id] if selected_vendor_id else None

        self.btn_mpn_search.setEnabled(False)
        self.btn_mpn_stage.setEnabled(False)
        self.progress_bar.show()
        self.status_msg_lbl.setText(f"Searching enabled vendor catalogs for '{raw_mpn}'...")

        self.mpn_worker = MPNSearchWorker(
            request=req,
            vendor_ids=vendor_ids,
            orchestrator=self.orchestrator,
        )
        self.mpn_worker.results_signal.connect(self._on_mpn_search_results)
        self.mpn_worker.error_signal.connect(self._on_mpn_search_error)
        self.mpn_worker.start()

    def _on_mpn_search_results(self, candidates: list, evaluations: list):
        self.btn_mpn_search.setEnabled(True)
        self.progress_bar.hide()
        self.mpn_candidates = candidates
        self.mpn_evaluations = evaluations
        self.selected_mpn_eval_idx = None

        self._render_mpn_table()

        if not candidates:
            self.status_msg_lbl.setText(f"No products found for '{self.mpn_input.text().strip()}'.")
            self.btn_mpn_stage.setEnabled(False)
            return

        eligible_count = sum(1 for e in evaluations if e.is_eligible)
        self.status_msg_lbl.setText(
            f"Found {len(candidates)} candidate offers ({eligible_count} eligible, {len(candidates) - eligible_count} rejected)."
        )

        # Auto-select best eligible candidate as initial default
        best_eval = self.orchestrator.select_best_candidate(evaluations)
        if best_eval and best_eval in evaluations:
            self.selected_mpn_eval_idx = evaluations.index(best_eval)
            self._update_mpn_table_selection()
            self.btn_mpn_stage.setEnabled(True)
        else:
            self.btn_mpn_stage.setEnabled(False)

    def _on_mpn_search_error(self, err_msg: str):
        self.btn_mpn_search.setEnabled(True)
        self.progress_bar.hide()
        self.status_msg_lbl.setText(f"Search error: {err_msg}")
        QMessageBox.warning(self, "Search Error", f"Candidate search failed: {err_msg}")

    def _render_mpn_table(self):
        self.mpn_table.setRowCount(len(self.mpn_evaluations))
        font_txt = QFont("Segoe UI", 10)
        font_num = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        for row_idx, ev in enumerate(self.mpn_evaluations):
            cand = ev.candidate

            # 0. Selection Radio / Button
            radio = QRadioButton()
            radio.setEnabled(ev.is_eligible)
            radio.toggled.connect(lambda checked, r=row_idx: self._on_mpn_radio_toggled(r, checked))
            radio_container = QWidget()
            r_lay = QHBoxLayout(radio_container)
            r_lay.setContentsMargins(0, 0, 0, 0)
            r_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            r_lay.addWidget(radio)
            self.mpn_table.setCellWidget(row_idx, 0, radio_container)

            # 1. Vendor
            v_name = cand.vendor_id.replace("vendor_", "").title()
            item_v = QTableWidgetItem(v_name)
            item_v.setFont(font_txt)
            self.mpn_table.setItem(row_idx, 1, item_v)

            # 2. SKU
            item_sku = QTableWidgetItem(cand.product_ref.vendor_sku or "—")
            item_sku.setFont(font_txt)
            self.mpn_table.setItem(row_idx, 2, item_sku)

            # 3. MPN
            item_mpn = QTableWidgetItem(cand.part_number or "—")
            item_mpn.setFont(font_txt)
            self.mpn_table.setItem(row_idx, 3, item_mpn)

            # 4. Manufacturer
            item_mfg = QTableWidgetItem(cand.manufacturer or "—")
            item_mfg.setFont(font_txt)
            self.mpn_table.setItem(row_idx, 4, item_mfg)

            # 5. Package / Footprint
            pkg_str = f"{cand.package or ''} / {cand.footprint or ''}".strip(" /") or "—"
            item_pkg = QTableWidgetItem(pkg_str)
            item_pkg.setFont(font_txt)
            self.mpn_table.setItem(row_idx, 5, item_pkg)

            # 6. Stock
            stk_str = str(cand.stock_quantity) if cand.in_stock else "Out of Stock"
            item_stk = QTableWidgetItem(stk_str)
            item_stk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_stk.setFont(font_num)
            item_stk.setForeground(QColor("#34d399") if cand.in_stock else QColor("#f87171"))
            self.mpn_table.setItem(row_idx, 6, item_stk)

            # 7. MOQ & 8. Step
            moq_val = cand.order_constraints.moq_raw or 1
            step_val = cand.order_constraints.packaging_step_raw or 1
            item_moq = QTableWidgetItem(str(moq_val))
            item_moq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_moq.setFont(font_num)
            self.mpn_table.setItem(row_idx, 7, item_moq)

            item_step = QTableWidgetItem(str(step_val))
            item_step.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_step.setFont(font_num)
            self.mpn_table.setItem(row_idx, 8, item_step)

            # 9. Unit Price (IRR)
            u_price = f"{ev.effective_unit_price_irr:,} IRR" if ev.effective_unit_price_irr is not None else "—"
            item_up = QTableWidgetItem(u_price)
            item_up.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_up.setFont(font_num)
            self.mpn_table.setItem(row_idx, 9, item_up)

            # 10. Total Cost (IRR)
            t_cost = f"{ev.effective_total_price_irr:,} IRR" if ev.effective_total_price_irr is not None else "—"
            item_tc = QTableWidgetItem(t_cost)
            item_tc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_tc.setFont(font_num)
            item_tc.setForeground(QColor("#38bdf8") if ev.is_eligible else QColor("#94a3b8"))
            self.mpn_table.setItem(row_idx, 10, item_tc)

            # 11. Status / Compatibility
            item_status = QTableWidgetItem()
            item_status.setFont(font_txt)
            if ev.is_eligible:
                item_status.setText("✅ ELIGIBLE")
                item_status.setForeground(QColor("#34d399"))
                item_status.setToolTip("Satisfies all technical constraints, stock, and orderability rules.")
            else:
                reasons_str = "; ".join(ev.rejection_reasons) or ev.state.value
                item_status.setText(f"❌ REJECTED ({ev.state.value})")
                item_status.setForeground(QColor("#f87171"))
                item_status.setToolTip(f"Candidate disqualified: {reasons_str}")
            self.mpn_table.setItem(row_idx, 11, item_status)

        for c in range(11):
            self.mpn_table.resizeColumnToContents(c)

    def _on_mpn_radio_toggled(self, row_idx: int, checked: bool):
        if checked and 0 <= row_idx < len(self.mpn_evaluations):
            ev = self.mpn_evaluations[row_idx]
            if ev.is_eligible:
                self.selected_mpn_eval_idx = row_idx
                self.btn_mpn_stage.setEnabled(True)
                cand = ev.candidate
                v_name = cand.vendor_id.replace("vendor_", "").title()
                self.status_msg_lbl.setText(
                    f"Selected: {v_name} | {cand.part_number} ({ev.effective_quantity} pcs @ {ev.effective_total_price_irr:,} IRR)"
                )

    def _update_mpn_table_selection(self):
        for r in range(self.mpn_table.rowCount()):
            widget = self.mpn_table.cellWidget(r, 0)
            if widget:
                radio = widget.findChild(QRadioButton)
                if radio:
                    radio.setChecked(r == self.selected_mpn_eval_idx)

    def _on_mpn_table_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        if 0 <= row < len(self.mpn_evaluations):
            cand = self.mpn_evaluations[row].candidate
            if cand.product_ref and cand.product_ref.pdp_url:
                webbrowser.open(cand.product_ref.pdp_url)

    def _on_mpn_stage_clicked(self):
        if self.selected_mpn_eval_idx is None or self.selected_mpn_eval_idx >= len(self.mpn_evaluations):
            QMessageBox.warning(self, "No Candidate Selected", "Please select an eligible candidate to stage into cart.")
            return

        ev = self.mpn_evaluations[self.selected_mpn_eval_idx]
        if not ev.is_eligible:
            QMessageBox.warning(self, "Ineligible Candidate", "Ineligible candidates cannot be staged.")
            return

        cand = ev.candidate
        qty = ev.effective_quantity

        self.btn_mpn_stage.setEnabled(False)
        self.btn_mpn_search.setEnabled(False)
        self.progress_bar.show()
        self.status_msg_lbl.setText(f"Staging {qty} pcs of {cand.part_number} to {cand.vendor_id} cart...")

        self.stage_worker = CartStageWorker(
            candidate=cand,
            quantity=qty,
            orchestrator=self.orchestrator,
        )
        self.stage_worker.finished_signal.connect(self._on_mpn_stage_finished)
        self.stage_worker.error_signal.connect(self._on_mpn_stage_error)
        self.stage_worker.start()

    def _on_mpn_stage_finished(self, res: CartMutationResult):
        self.btn_mpn_stage.setEnabled(True)
        self.btn_mpn_search.setEnabled(True)
        self.progress_bar.hide()

        if res.success:
            if res.is_noop:
                msg = f"✅ Already satisfied in cart: {res.initial_cart_qty}/{res.target_qty} pcs. 0 units added."
            else:
                msg = f"✅ Staged {res.actual_quantity_staged} pcs to {res.vendor_id} cart! ({res.raw_vendor_message})"
            self.status_msg_lbl.setText(msg)
            self.btn_mpn_open_cart.show()
            self.btn_mpn_confirm_stock.show()

            QMessageBox.information(
                self,
                "Cart Staging Succeeded",
                f"{msg}\n\nClick 'Open Vendor Cart' to review and finalize payment in your browser.",
            )
        else:
            err_msg = res.raw_vendor_message or res.error_category or "Staging failed"
            self.status_msg_lbl.setText(f"❌ Staging error: {err_msg}")
            QMessageBox.warning(self, "Staging Failed", f"Could not stage item to cart: {err_msg}")

    def _on_mpn_stage_error(self, err_msg: str):
        self.btn_mpn_stage.setEnabled(True)
        self.btn_mpn_search.setEnabled(True)
        self.progress_bar.hide()
        self.status_msg_lbl.setText(f"❌ Staging exception: {err_msg}")
        QMessageBox.warning(self, "Staging Error", f"Unexpected staging failure: {err_msg}")

    def _on_url_inspect_clicked(self):
        url = self.url_input.text().strip()
        is_valid, vendor_id, err_reason = validate_vendor_pdp_url(url, self.registry)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Product URL", err_reason or "Invalid URL.")
            self.url_input.setFocus()
            return

        qty = self.url_qty_stepper.value()

        self.btn_url_inspect.setEnabled(False)
        self.btn_url_stage.setEnabled(False)
        self.progress_bar.show()
        self.status_msg_lbl.setText(f"Inspecting product page on {vendor_id}...")

        self.url_worker = URLInspectWorker(
            url=url,
            quantity=qty,
            vendor_id=vendor_id,
            registry=self.registry,
            orchestrator=self.orchestrator,
        )
        self.url_worker.result_signal.connect(self._on_url_inspect_result)
        self.url_worker.error_signal.connect(self._on_url_inspect_error)
        self.url_worker.start()

    def _on_url_inspect_result(self, candidate: VendorProcurementCandidate, evaluation: CandidateEvaluation):
        self.btn_url_inspect.setEnabled(True)
        self.progress_bar.hide()
        self.url_candidate = candidate
        self.url_evaluation = evaluation

        self._render_url_table(candidate, evaluation)

        if evaluation.is_eligible:
            self.btn_url_stage.setEnabled(True)
            self.status_msg_lbl.setText(
                f"Product verified: {candidate.part_number} | Effective Qty: {evaluation.effective_quantity} | Cost: {evaluation.effective_total_price_irr:,} IRR"
            )
        else:
            self.btn_url_stage.setEnabled(False)
            reasons = "; ".join(evaluation.rejection_reasons) or evaluation.state.value
            self.status_msg_lbl.setText(f"Product cannot be ordered: {reasons}")

    def _on_url_inspect_error(self, err_msg: str):
        self.btn_url_inspect.setEnabled(True)
        self.progress_bar.hide()
        self.status_msg_lbl.setText(f"URL inspection error: {err_msg}")
        QMessageBox.warning(self, "Inspection Error", f"Could not inspect product URL: {err_msg}")

    def _render_url_table(self, cand: VendorProcurementCandidate, ev: CandidateEvaluation):
        attrs = [
            ("Vendor", cand.vendor_id.replace("vendor_", "").title()),
            ("Vendor SKU", cand.product_ref.vendor_sku or "—"),
            ("Part Number / MPN", cand.part_number or "—"),
            ("Manufacturer / Brand", cand.manufacturer or "—"),
            ("Package / Footprint", f"{cand.package or ''} / {cand.footprint or ''}".strip(" /") or "—"),
            ("Stock Availability", f"{cand.stock_quantity} units in stock" if cand.in_stock else "Out of stock / Inquiry-only"),
            ("Order Constraints", f"MOQ: {cand.order_constraints.moq_raw or 1} | Step: {cand.order_constraints.packaging_step_raw or 1}"),
            ("Unit Price", f"{ev.effective_unit_price_irr:,} IRR" if ev.effective_unit_price_irr is not None else "Unlisted"),
            ("Effective Quantity", f"{ev.effective_quantity} pcs (Requested: {ev.required_quantity})"),
            ("Total Cost", f"{ev.effective_total_price_irr:,} IRR" if ev.effective_total_price_irr is not None else "Unlisted"),
            ("Status & Eligibility", "✅ ELIGIBLE" if ev.is_eligible else f"❌ REJECTED ({ev.state.value}: {'; '.join(ev.rejection_reasons)})"),
        ]

        self.url_details_table.setRowCount(len(attrs))
        font_b = QFont("Segoe UI", 10, QFont.Weight.Bold)
        font_v = QFont("Segoe UI", 10)

        for r, (k, v) in enumerate(attrs):
            it_k = QTableWidgetItem(k)
            it_k.setFont(font_b)
            self.url_details_table.setItem(r, 0, it_k)

            it_v = QTableWidgetItem(str(v))
            it_v.setFont(font_v)
            if k == "Status & Eligibility":
                it_v.setForeground(QColor("#34d399") if ev.is_eligible else QColor("#f87171"))
            elif k == "Total Cost":
                it_v.setForeground(QColor("#38bdf8"))
            self.url_details_table.setItem(r, 1, it_v)

    def _on_url_stage_clicked(self):
        if not self.url_candidate or not self.url_evaluation or not self.url_evaluation.is_eligible:
            QMessageBox.warning(self, "Cannot Stage", "Valid eligible product details must be inspected first.")
            return

        cand = self.url_candidate
        qty = self.url_evaluation.effective_quantity

        self.btn_url_stage.setEnabled(False)
        self.btn_url_inspect.setEnabled(False)
        self.progress_bar.show()
        self.status_msg_lbl.setText(f"Staging {qty} pcs to {cand.vendor_id} cart...")

        self.stage_worker = CartStageWorker(
            candidate=cand,
            quantity=qty,
            orchestrator=self.orchestrator,
        )
        self.stage_worker.finished_signal.connect(self._on_url_stage_finished)
        self.stage_worker.error_signal.connect(self._on_url_stage_error)
        self.stage_worker.start()

    def _on_url_stage_finished(self, res: CartMutationResult):
        self.btn_url_stage.setEnabled(True)
        self.btn_url_inspect.setEnabled(True)
        self.progress_bar.hide()

        if res.success:
            if res.is_noop:
                msg = f"✅ Already satisfied in cart: {res.initial_cart_qty}/{res.target_qty} pcs. 0 units added."
            else:
                msg = f"✅ Staged {res.actual_quantity_staged} pcs to {res.vendor_id} cart! ({res.raw_vendor_message})"
            self.status_msg_lbl.setText(msg)
            self.btn_url_open_cart.show()
            self.btn_url_confirm_stock.show()

            QMessageBox.information(
                self,
                "Cart Staging Succeeded",
                f"{msg}\n\nClick 'Open Vendor Cart' to review and finalize payment in your browser.",
            )
        else:
            err_msg = res.raw_vendor_message or res.error_category or "Staging failed"
            self.status_msg_lbl.setText(f"❌ Staging error: {err_msg}")
            QMessageBox.warning(self, "Staging Failed", f"Could not stage item to cart: {err_msg}")

    def _on_url_stage_error(self, err_msg: str):
        self.btn_url_stage.setEnabled(True)
        self.btn_url_inspect.setEnabled(True)
        self.progress_bar.hide()
        self.status_msg_lbl.setText(f"❌ Staging exception: {err_msg}")
        QMessageBox.warning(self, "Staging Error", f"Unexpected staging failure: {err_msg}")

    def _open_vendor_cart(self, vendor_id: Optional[str]):
        """Open the cart URL for a given vendor using its adapter."""
        if not vendor_id:
            QMessageBox.warning(
                self,
                "Vendor Cart Unavailable",
                "Cannot open shopping cart: vendor could not be resolved.",
            )
            return

        try:
            adapter = self.registry.get_adapter(vendor_id)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Vendor Cart Unavailable",
                f"Cannot open shopping cart: vendor adapter for '{vendor_id}' is unavailable ({e}).",
            )
            return

        name_val = self.registry.get_vendor_name(vendor_id) if hasattr(self.registry, "get_vendor_name") else vendor_id
        v_title = name_val if isinstance(name_val, str) else str(vendor_id).replace("vendor_", "").title()

        if not hasattr(adapter, "get_cart_url") or not callable(adapter.get_cart_url):
            QMessageBox.warning(
                self,
                "Vendor Cart Unavailable",
                f"Vendor adapter for '{v_title}' does not support cart URL retrieval.",
            )
            return

        try:
            url = adapter.get_cart_url()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Vendor Cart Unavailable",
                f"Error retrieving cart URL from vendor adapter: {e}",
            )
            return

        clean_url = str(url or "").strip()
        if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            QMessageBox.warning(
                self,
                "Vendor Cart Unavailable",
                f"No valid storefront shopping cart URL is available for '{v_title}'.",
            )
            return

        webbrowser.open(clean_url)

    def _on_open_cart_clicked(self):
        vendor_id = None
        if self.tabs.currentIndex() == 0 and self.selected_mpn_eval_idx is not None:
            cand = self.mpn_evaluations[self.selected_mpn_eval_idx].candidate
            vendor_id = cand.vendor_id
        elif self.tabs.currentIndex() == 1 and self.url_candidate:
            vendor_id = self.url_candidate.vendor_id

        self._open_vendor_cart(vendor_id)

    def _on_confirm_stock_clicked(self):
        if not self.inventory_loader:
            QMessageBox.information(
                self,
                "No Inventory Database",
                "Direct Quick Order was executed standalone. No active Inventory.xlsx database loaded."
            )
            return

        cand = None
        qty = 0
        if self.tabs.currentIndex() == 0 and self.selected_mpn_eval_idx is not None:
            cand = self.mpn_evaluations[self.selected_mpn_eval_idx].candidate
            qty = self.mpn_evaluations[self.selected_mpn_eval_idx].effective_quantity
        elif self.tabs.currentIndex() == 1 and self.url_candidate and self.url_evaluation:
            cand = self.url_candidate
            qty = self.url_evaluation.effective_quantity

        if not cand or qty <= 0:
            return

        item_dict = {
            "part_number": cand.part_number,
            "part_name": cand.part_number,
            "actual_ordered_qty": qty,
            "order_success": True,
        }

        count, msg = self.inventory_loader.batch_increment_stock([item_dict])
        if count > 0:
            QMessageBox.information(
                self,
                "Inventory Updated",
                f"✅ Success!\n\nAdded {qty} units of '{cand.part_number}' to Inventory.xlsx.",
            )
            if self.on_stock_updated:
                self.on_stock_updated()
        else:
            QMessageBox.warning(
                self,
                "Inventory Update Failed",
                f"Could not update stock in Inventory.xlsx: {msg}"
            )

