"""
Omnix Automated Test Suite — Section 3: Live Log & Event Reporting
Tests cover all 7 core acceptance criteria and 6 application domains:
1. Real-time event recording & ISO-8601 UTC timestamping
2. Standard severity levels (INFO, WARNING, ERROR)
3. Bounded in-memory retention and disk log rotation
4. Centralized sensitive-data redaction (passwords, tokens, API keys, URLs, exceptions)
5. Idempotent initialization without duplicate handlers
6. Accurate operation lifecycles with correlation IDs and single terminal outcomes
7. Cross-thread event delivery to Qt event bridge
8. Live instrumentation across all 6 domains: Inventory, BOM, Procurement, Plugins, BackupRestore, Export
9. LiveLogWidget rendering, real-time streaming, filtering, and bounded table display
"""

import os
import sys
import tempfile
import pytest
import datetime
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from core.logger import (
    EventRecord,
    EventBuffer,
    OperationTracker,
    log_event,
    track_operation,
    setup_logging,
    get_logger,
    get_event_buffer,
    get_event_bridge,
    add_event_subscriber,
    remove_event_subscriber,
    sanitize_text,
    sanitize_dict,
    reset_logging_for_testing,
    SecretRedactingFormatter,
)
from core.inventory.models import InventoryProduct
from core.inventory.database import DatabaseManager
from core.inventory.repository import SqliteInventoryRepository
from core.inventory.backup import DatabaseBackupService
from core.inventory.exporter import InventoryExcelExporter
from core.models import AdapterConfig
from core.procurement.registry import VendorRegistry
from core.procurement.models import ProcurementMode
from core.vendor_interface import IVendorAdapter
from bom_auditor import BOMAuditor
from ui.widgets.live_log_widget import LiveLogWidget


@pytest.fixture(autouse=True)
def clean_logging_state():
    """Ensure pristine logging and event buffer state before and after each test."""
    reset_logging_for_testing()
    yield
    reset_logging_for_testing()


@pytest.fixture
def temp_repo():
    """Provides an isolated in-memory SqliteInventoryRepository."""
    db_mgr = DatabaseManager(":memory:")
    repo = SqliteInventoryRepository(db_mgr)
    return repo


class DummyTestAdapter(IVendorAdapter):
    VENDOR_ID = "vendor_test_dummy"
    STOREFRONT_NAME = "Dummy Vendor"

    def __init__(self, config=None):
        self.config = config or AdapterConfig(vendor_id=self.VENDOR_ID, base_url="https://dummy.example.com")


# ===========================================================================
# 1. Core Event Record, Timestamping, and Severity Levels
# ===========================================================================

class TestEventRecordAndSeverity:
    """Verifies acceptance criteria 1 and 3: Real-time event recording, UTC ISO timestamps, and severities."""

    def test_event_record_utc_timestamp_and_fields(self):
        rec = log_event(
            domain="Inventory",
            event_type="START",
            message="Initial component inventory check",
            level="INFO",
            operation_id="op_test_001",
            details={"count": 42},
        )
        assert rec.domain == "Inventory"
        assert rec.event_type == "START"
        assert rec.level == "INFO"
        assert rec.message == "Initial component inventory check"
        assert rec.operation_id == "op_test_001"
        assert rec.details == {"count": 42}

        # Timestamp must be valid ISO-8601 UTC
        dt = datetime.datetime.fromisoformat(rec.timestamp)
        assert dt.tzinfo is not None

    def test_severity_levels_normalized(self):
        r_info = log_event("System", "LOG", "Info msg", level="info")
        r_warn = log_event("System", "LOG", "Warning msg", level="warning")
        r_err = log_event("System", "LOG", "Error msg", level="error")
        r_unknown = log_event("System", "LOG", "Fallback msg", level="custom_xyz")

        assert r_info.level == "INFO"
        assert r_warn.level == "WARNING"
        assert r_err.level == "ERROR"
        assert r_unknown.level == "INFO"  # Safe default fallback

    def test_event_record_serialization(self):
        rec = log_event("BOM", "COMPLETION", "Audit finished", level="INFO")
        d = rec.to_dict()
        assert d["domain"] == "BOM"
        assert d["event_type"] == "COMPLETION"
        assert d["level"] == "INFO"
        assert "timestamp" in d


# ===========================================================================
# 2. Bounded Retention & Log Rotation
# ===========================================================================

class TestBoundedRetentionAndDiskRotation:
    """Verifies acceptance criterion 5: Bounded memory buffer and disk log rotation."""

    def test_in_memory_event_buffer_bounded_retention(self):
        buf = EventBuffer(max_size=50)
        for i in range(120):
            buf.append(EventRecord(
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                level="INFO",
                domain="System",
                event_type="PROGRESS",
                message=f"Event number {i}",
            ))

        assert buf.count() == 50
        all_events = buf.get_all()
        assert len(all_events) == 50
        # Oldest events (0..69) should have been pruned; newest (70..119) preserved
        assert all_events[0].message == "Event number 70"
        assert all_events[-1].message == "Event number 119"

    def test_global_event_buffer_bounded_at_1000(self):
        buf = get_event_buffer()
        assert buf.max_size == 1000
        for i in range(1050):
            log_event("System", "PROGRESS", f"Bulk event {i}")
        assert buf.count() == 1000
        first = buf.get_all()[0]
        assert first.message == "Bulk event 50"

    def test_disk_log_rotation_bounded_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup logging with tiny max_bytes (1024 bytes) and 3 backups
            setup_logging(log_dir=tmpdir, max_bytes=1024, backup_count=3, console=False)
            logger = get_logger("TestRotation")

            # Write enough data to trigger multiple rotations
            payload = "X" * 300
            for i in range(40):
                logger.info(f"Line {i}: {payload}")

            files = os.listdir(tmpdir)
            # Must contain omnix.log and rotated files (e.g. omnix.log.1, omnix.log.2)
            assert "omnix.log" in files
            rotated_files = [f for f in files if f.startswith("omnix.log.")]
            assert len(rotated_files) > 0
            # Total log files must not exceed backup_count + 1 (i.e. <= 4)
            assert len(files) <= 4
            reset_logging_for_testing()


# ===========================================================================
# 3. Sensitive Data Redaction
# ===========================================================================

class TestSensitiveDataRedaction:
    """Verifies acceptance criterion 6: Redaction of credentials, tokens, passwords, and secrets."""

    def test_sanitize_plaintext_passwords_and_tokens(self):
        raw = "User authentication attempted with password='SuperSecret123!' and token: my_secret_token_abc"
        sanitized = sanitize_text(raw)
        assert "SuperSecret123!" not in sanitized
        assert "my_secret_token_abc" not in sanitized
        assert "***REDACTED***" in sanitized

    def test_sanitize_api_keys_and_cookies(self):
        raw = "Connecting to vendor with api-key=synth_api_key_sample_98765 and cookie: session_id_xyz987"
        sanitized = sanitize_text(raw)
        assert "synth_api_key_sample_98765" not in sanitized
        assert "session_id_xyz987" not in sanitized
        assert "api-key=***REDACTED***" in sanitized or "api-key=***REDACTED***" in sanitized.lower()

    def test_sanitize_bearer_tokens(self):
        raw = "HTTP Authorization: Bearer synthetic_test_bearer_token_12345_fixture"
        sanitized = sanitize_text(raw)
        assert "synthetic_test_bearer_token_12345_fixture" not in sanitized
        assert "Bearer ***REDACTED***" in sanitized

    def test_sanitize_basic_auth_url(self):
        raw = "Querying internal endpoint https://admin:secret_pass123@api.vendor.com/v1/search"
        sanitized = sanitize_text(raw)
        assert "secret_pass123" not in sanitized
        assert "https://admin:***REDACTED***@api.vendor.com/v1/search" in sanitized

    def test_sanitize_dict_keys(self):
        data = {
            "vendor_id": "vendor_lion",
            "username": "amin_user",
            "password": "CleartextPassword99",
            "api_key": "SecretKey123",
            "nested": {
                "auth_token": "TokenABC",
                "normal_val": 42,
            },
        }
        clean = sanitize_dict(data)
        assert clean["username"] == "amin_user"
        assert clean["password"] == "***REDACTED***"
        assert clean["api_key"] == "***REDACTED***"
        assert clean["nested"]["auth_token"] == "***REDACTED***"
        assert clean["nested"]["normal_val"] == 42

    def test_formatter_redacts_exception_strings(self):
        formatter = SecretRedactingFormatter("%(levelname)s: %(message)s")
        try:
            raise ValueError("Connection failed with password=LeakedPass!")
        except Exception as e:
            import logging
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg=f"Error occurred: {e}", args=(), exc_info=sys.exc_info(),
            )
            formatted = formatter.format(record)
            assert "LeakedPass!" not in formatted
            assert "***REDACTED***" in formatted

    def test_sanitize_session_id_variants(self):
        """Verifies session_id, session-id, sessionId redaction across text, URLs, and dicts."""
        t1 = "User login session_id: synth_sess_12345"
        t2 = "API request https://vendor.com/cart?session-id=synth_sess_67890&part=10k"
        t3 = "Cookie header: sessionId=synth_sess_abcde; path=/"
        assert "synth_sess_12345" not in sanitize_text(t1)
        assert "synth_sess_67890" not in sanitize_text(t2)
        assert "synth_sess_abcde" not in sanitize_text(t3)

        d = {
            "session_id": "secret_sess_val1",
            "session-id": "secret_sess_val2",
            "sessionId": "secret_sess_val3",
            "safe_session_count": 5,
        }
        clean_d = sanitize_dict(d)
        assert clean_d["session_id"] == "***REDACTED***"
        assert clean_d["session-id"] == "***REDACTED***"
        assert clean_d["sessionId"] == "***REDACTED***"
        assert clean_d["safe_session_count"] == 5

    def test_sanitize_private_key_variants(self):
        """Verifies private_key, private-key, privateKey, and PEM blocks are redacted."""
        t1 = "Loaded key private_key=pk_synth_secret_999"
        t2 = "Config: private-key: pk_synth_secret_888"
        t3 = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0synthkeymaterial\n-----END RSA PRIVATE KEY-----"
        assert "pk_synth_secret_999" not in sanitize_text(t1)
        assert "pk_synth_secret_888" not in sanitize_text(t2)
        assert "0synthkeymaterial" not in sanitize_text(t3)

        d = {
            "private_key": "pk_material_1",
            "private-key": "pk_material_2",
            "privateKey": "pk_material_3",
        }
        clean_d = sanitize_dict(d)
        assert clean_d["private_key"] == "***REDACTED***"
        assert clean_d["private-key"] == "***REDACTED***"
        assert clean_d["privateKey"] == "***REDACTED***"

    def test_sanitize_jwt_variants(self):
        """Verifies JWT tokens in headers, query strings, and standalone format are redacted."""
        raw_jwt = "eyJ0ZXN0Ijoic3ludGhldGljX2p3dF9maXh0dXJlXzAxIn0.eyJkYXRhIjoic3ludGhldGljX3Rlc3RfcGF5bG9hZF8wMiJ9.synthetic_signature_test_mock_03"
        t1 = f"jwt={raw_jwt}"
        t2 = f"Authorization: JWT {raw_jwt}"
        t3 = f"Token received: {raw_jwt}"
        assert raw_jwt not in sanitize_text(t1)
        assert raw_jwt not in sanitize_text(t2)
        assert raw_jwt not in sanitize_text(t3)

        d = {
            "jwt": raw_jwt,
            "jwt_token": raw_jwt,
            "jwtToken": raw_jwt,
        }
        clean_d = sanitize_dict(d)
        assert clean_d["jwt"] == "***REDACTED***"
        assert clean_d["jwt_token"] == "***REDACTED***"
        assert clean_d["jwtToken"] == "***REDACTED***"

    def test_preserve_ordinary_engineering_terms(self):
        """Ensures that normal engineering words are never falsely redacted."""
        phrases = [
            "Component passivation inspection passed",
            "Bypass capacitor 100nF added to rail",
            "Author of BOM document is Engineering",
            "Passed 50 out of 50 test cycles",
            "Authentication server status: healthy",
            "Tokenized search string generated 4 terms",
        ]
        for p in phrases:
            assert sanitize_text(p) == p

    def test_disk_log_redacts_sensitive_values(self):
        """Verifies that actual persisted disk log files contain redacted values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            l = setup_logging(log_dir=tmpdir, console=False)
            log_event(
                "System", "START",
                "Connecting with session_id=sess_disk_123 and private_key=pk_disk_456",
                details={"jwt": "jwt_disk_789", "session_id": "sess_in_details"},
            )
            # Flush handlers
            for h in l.handlers:
                h.flush()

            log_file = os.path.join(tmpdir, "omnix.log")
            assert os.path.exists(log_file)
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()

            assert "sess_disk_123" not in content
            assert "pk_disk_456" not in content
            assert "***REDACTED***" in content
            reset_logging_for_testing()


# ===========================================================================
# 4. Idempotent Initialization Without Duplicate Handlers
# ===========================================================================

class TestIdempotentInitialization:
    """Verifies that calling setup_logging multiple times does not duplicate handlers."""

    def test_setup_logging_idempotence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            l1 = setup_logging(log_dir=tmpdir, console=False)
            initial_handler_count = len(l1.handlers)
            assert initial_handler_count > 0

            # Second call must be a no-op and preserve same handler count
            l2 = setup_logging(log_dir=tmpdir, console=False)
            assert l1 is l2
            assert len(l2.handlers) == initial_handler_count
            reset_logging_for_testing()


# ===========================================================================
# 5. Operation Lifecycles, Correlation IDs, and No False Completions
# ===========================================================================

class TestOperationLifecycleTracking:
    """Verifies acceptance criteria 2 & 7: Accurate lifecycle sequence, single terminal status, correlation ID."""

    def test_successful_operation_emits_start_and_completion_with_same_op_id(self):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        with track_operation("Inventory", "Sync Components") as op:
            op.progress("Verifying records")
            # Operation finishes cleanly

        assert len(captured) == 3
        # 1. START
        assert captured[0].event_type == "START"
        assert captured[0].level == "INFO"
        # 2. PROGRESS
        assert captured[1].event_type == "PROGRESS"
        assert "Verifying records" in captured[1].message
        # 3. COMPLETION
        assert captured[2].event_type == "COMPLETION"
        assert captured[2].level == "INFO"

        # Correlation ID must match across all 3
        op_id = captured[0].operation_id
        assert op_id is not None
        assert captured[1].operation_id == op_id
        assert captured[2].operation_id == op_id

    def test_failed_operation_emits_start_and_failure_never_completion(self):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        with pytest.raises(RuntimeError):
            with track_operation("BOM", "Parse Excel Document") as op:
                op.progress("Reading workbook")
                raise RuntimeError("Invalid sheet format")

        assert len(captured) == 3
        assert captured[0].event_type == "START"
        assert captured[1].event_type == "PROGRESS"
        assert captured[2].event_type == "FAILURE"
        assert captured[2].level == "ERROR"
        assert "Invalid sheet format" in captured[2].message

        # Must NOT contain a false COMPLETION event
        types = [c.event_type for c in captured]
        assert "COMPLETION" not in types

        # Single terminal outcome guaranteed
        terminal_events = [c for c in captured if c.event_type in ("COMPLETION", "FAILURE")]
        assert len(terminal_events) == 1


# ===========================================================================
# 6. Real-Time Qt Signal Bridge
# ===========================================================================

class TestQtEventBridge:
    """Verifies real-time signal dispatch via Qt event bridge for thread-safe UI updates."""

    def test_qt_bridge_emits_event_record(self, qapp):
        bridge = get_event_bridge()
        emitted_events = []
        bridge.eventLogged.connect(lambda ev: emitted_events.append(ev))

        log_event("Procurement", "START", "Starting procurement run")
        qapp.processEvents()

        assert len(emitted_events) == 1
        assert emitted_events[0].domain == "Procurement"
        assert emitted_events[0].event_type == "START"
        assert emitted_events[0].message == "Starting procurement run"


# ===========================================================================
# 7. Domain Instrumentation Tests (All 6 Domains)
# ===========================================================================

class TestSixDomainInstrumentation:
    """Verifies acceptance criteria 2: Real lifecycle events across all 6 application domains."""

    def test_domain_1_inventory_create_update_delete(self, temp_repo):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        # 1. Create Component
        p = InventoryProduct(
            manufacturer="Texas Instruments",
            mpn="LM358DR",
            category="Amplifier",
            type_technology="Operational Amplifier",
            value="100kHz",
            package="SOIC-8",
            footprint="SOIC-8",
            quantity_in_stock=50,
        )
        created = temp_repo.create_component(p)
        assert created is not None

        # Must record Inventory START and COMPLETION
        inv_events = [c for c in captured if c.domain == "Inventory"]
        assert any(e.event_type == "START" and "LM358DR" in e.message for e in inv_events)
        assert any(e.event_type == "COMPLETION" and "Successfully created" in e.message for e in inv_events)

        # 2. Update Component
        captured.clear()
        temp_repo.update_component(created.id, quantity_in_stock=75)
        update_events = [c for c in captured if c.domain == "Inventory"]
        assert any(e.event_type == "COMPLETION" and "Successfully updated" in e.message for e in update_events)

        # 3. Delete Component
        captured.clear()
        temp_repo.delete_component(created.id)
        delete_events = [c for c in captured if c.domain == "Inventory"]
        assert any(e.event_type == "COMPLETION" and "Successfully deleted" in e.message for e in delete_events)

    def test_domain_1_inventory_creation_failure_logged(self, temp_repo):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        # Attempt to create component with negative stock (violates validation)
        p_invalid = InventoryProduct(
            manufacturer="STMicroelectronics",
            mpn="STM32F401RE",
            category="MCU",
            type_technology="32-bit",
            package="LQFP-64",
            footprint="LQFP-64",
            value="84MHz",
            quantity_in_stock=-10,
        )
        with pytest.raises(Exception):
            temp_repo.create_component(p_invalid)

        fail_events = [c for c in captured if c.domain == "Inventory" and c.event_type == "FAILURE"]
        assert len(fail_events) == 1
        assert fail_events[0].level == "ERROR"
        assert "must be non-negative" in fail_events[0].message

    def test_domain_2_bom_audit_lifecycle(self, tmp_path):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        # Missing BOM file triggers FAILURE
        ok, msg, res = BOMAuditor.audit_bom(str(tmp_path / "non_existent.xlsx"))
        assert ok is False
        bom_fails = [c for c in captured if c.domain == "BOM" and c.event_type == "FAILURE"]
        assert len(bom_fails) == 1
        assert bom_fails[0].level == "ERROR"

        # Valid BOM file triggers START and COMPLETION
        captured.clear()
        import openpyxl
        bom_file = tmp_path / "test_sample_bom.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Bill of Materials"
        ws.append(["Designator", "Quantity", "Comment", "MPN", "Manufacturer"])
        ws.append(["R1", "10", "10k 0805", "CR0805-FX-1002ELF", "Bourns"])
        wb.save(bom_file)
        wb.close()

        ok, msg, res = BOMAuditor.audit_bom(str(bom_file), mode=ProcurementMode.DATABASE_AWARE)
        assert ok is True
        bom_events = [c for c in captured if c.domain == "BOM"]
        assert any(e.event_type == "START" for e in bom_events)
        assert any(e.event_type == "COMPLETION" and "1 items evaluated" in e.message for e in bom_events)

    def test_domain_3_procurement_cart_worker(self, qapp):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        from ui.dialogs.order_preview_dialog import OrderWorkerThread

        # Test OrderWorkerThread direct items branch with mock bridge
        items = [{"name": "LM358DR", "qty": 10, "url": "https://example.com"}]
        worker = OrderWorkerThread(items=items)

        with patch("ui.dialogs.order_preview_dialog.ProcurementBridge.execute_staged_procurement_batch") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "successful_count": 1,
                "failed_count": 0,
                "results": [{"part": "LM358DR", "status": "SUCCESS", "qty": 10, "msg": "Staged"}],
            }
            worker._run_direct_items()

        proc_events = [c for c in captured if c.domain == "Procurement"]
        assert any(e.event_type == "START" for e in proc_events)
        assert any(e.event_type == "COMPLETION" for e in proc_events)

    def test_domain_4_plugins_lifecycle(self):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        reg = VendorRegistry()
        # 1. Register adapter
        reg.register_adapter(
            vendor_id="vendor_test_dummy",
            adapter_class=DummyTestAdapter,
            display_name="Test Dummy",
        )
        plugin_events = [c for c in captured if c.domain == "Plugins"]
        assert any(e.event_type == "COMPLETION" and "Registered vendor adapter" in e.message for e in plugin_events)

        # 2. Toggle vendor enable/disable
        captured.clear()
        reg.set_vendor_enabled("vendor_test_dummy", False)
        assert any(e.event_type == "COMPLETION" and "Disabled vendor plugin" in e.message for e in captured)

        captured.clear()
        reg.set_vendor_enabled("vendor_test_dummy", True)
        assert any(e.event_type == "COMPLETION" and "Enabled vendor plugin" in e.message for e in captured)

    def test_domain_5_backup_restore_lifecycle(self, tmp_path):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        db_file = str(tmp_path / "active_inventory.db")
        repo = SqliteInventoryRepository(db_file)
        backup_file = str(tmp_path / "test_inventory_backup.db")

        # 1. Export backup
        ok, msg, meta = DatabaseBackupService.export_backup(repo._db, backup_file)
        assert ok is True
        backup_events = [c for c in captured if c.domain == "BackupRestore"]
        assert any(e.event_type == "START" for e in backup_events)
        assert any(e.event_type == "COMPLETION" and "exported successfully" in e.message.lower() for e in backup_events)

        # 2. Restore backup
        captured.clear()
        ok_res, msg_res, _ = DatabaseBackupService.restore_backup(
            repo, backup_file, safety_dir=str(tmp_path / "safety")
        )
        assert ok_res is True

        restore_events = [c for c in captured if c.domain == "BackupRestore"]
        assert any(e.event_type == "START" for e in restore_events)
        assert any(e.event_type == "COMPLETION" and "restored successfully" in e.message.lower() for e in restore_events)

    def test_domain_6_export_excel_lifecycle(self, temp_repo, tmp_path):
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        out_file = str(tmp_path / "exported_inventory.xlsx")
        res_path = InventoryExcelExporter.export(temp_repo, out_file)
        assert os.path.exists(res_path)

        export_events = [c for c in captured if c.domain == "Export"]
        assert any(e.event_type == "START" for e in export_events)
        assert any(e.event_type == "COMPLETION" and "successfully exported" in e.message.lower() for e in export_events)

    def test_domain_3_multivendor_staging_partial_failure_terminal_outcome(self, qapp):
        """
        Verifies that partial failure in multi-vendor cart staging emits an explicit
        terminal FAILURE event (with WARNING level), not left as a PROGRESS event.
        """
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        from ui.dialogs.order_preview_dialog import OrderWorkerThread
        from unittest.mock import patch

        items = [
            {"name": "PART_OK", "qty": 5, "url": "https://example.com/ok"},
            {"name": "PART_FAIL", "qty": 10, "url": "https://example.com/fail"},
        ]
        worker = OrderWorkerThread(items=items)

        with patch("ui.dialogs.order_preview_dialog.ProcurementBridge.execute_staged_procurement_batch") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "successful_count": 1,
                "failed_count": 1,
                "message": "Partially failed: 1/2 items failed staging",
                "results": [
                    {"part": "PART_OK", "status": "SUCCESS", "qty": 5, "msg": "Staged"},
                    {"part": "PART_FAIL", "status": "FAILED", "qty": 10, "msg": "Out of stock"},
                ],
            }
            worker._run_direct_items()

        proc_events = [c for c in captured if c.domain == "Procurement"]
        assert len(proc_events) >= 2

        # Start event exists
        start_ev = next(e for e in proc_events if e.event_type == "START")
        op_id = start_ev.operation_id
        assert op_id is not None

        # Terminal event MUST be FAILURE with WARNING level (not left as PROGRESS, not COMPLETION)
        terminal_evs = [e for e in proc_events if e.event_type in ("COMPLETION", "FAILURE")]
        assert len(terminal_evs) == 1
        term = terminal_evs[0]
        assert term.event_type == "FAILURE"
        assert term.level == "WARNING"
        assert "partially failed" in term.message.lower()
        assert term.operation_id == op_id

    def test_all_six_domains_share_stable_correlation_ids(self, temp_repo, tmp_path):
        """
        Verifies that START and terminal events for operations across all 6 domains
        consistently share the exact same non-None operation_id.
        """
        captured = []
        add_event_subscriber(lambda r: captured.append(r))

        # 1. Inventory
        p = InventoryProduct(
            manufacturer="Texas Instruments",
            mpn="SN74HC00N",
            category="Logic",
            type_technology="NAND Gate",
            value="Quad 2-Input",
            package="DIP-14",
            footprint="DIP-14",
            quantity_in_stock=100,
        )
        created = temp_repo.create_component(p)
        inv_events = [c for c in captured if c.domain == "Inventory"]
        assert len(inv_events) >= 2
        inv_op_id = inv_events[0].operation_id
        assert inv_op_id is not None
        assert all(e.operation_id == inv_op_id for e in inv_events)

        # 2. BOM
        captured.clear()
        import openpyxl
        bom_file = tmp_path / "test_corr_bom.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "BOM"
        ws.append(["Designator", "Quantity", "Comment", "MPN", "Manufacturer"])
        ws.append(["U1", "1", "NAND", "SN74HC00N", "Texas Instruments"])
        wb.save(bom_file)
        wb.close()
        BOMAuditor.audit_bom(str(bom_file), mode=ProcurementMode.DATABASE_AWARE)
        bom_events = [c for c in captured if c.domain == "BOM"]
        assert len(bom_events) >= 2
        bom_op_id = bom_events[0].operation_id
        assert bom_op_id is not None
        assert all(e.operation_id == bom_op_id for e in bom_events)

        # 3. Procurement
        captured.clear()
        from ui.dialogs.order_preview_dialog import OrderWorkerThread
        items = [{"name": "SN74HC00N", "qty": 1, "url": "https://example.com"}]
        worker = OrderWorkerThread(items=items)
        with patch("ui.dialogs.order_preview_dialog.ProcurementBridge.execute_staged_procurement_batch") as mock_exec:
            mock_exec.return_value = {"success": True, "successful_count": 1, "failed_count": 0}
            worker._run_direct_items()
        proc_events = [c for c in captured if c.domain == "Procurement"]
        assert len(proc_events) >= 2
        proc_op_id = proc_events[0].operation_id
        assert proc_op_id is not None
        assert all(e.operation_id == proc_op_id for e in proc_events)

        # 4. Plugins
        captured.clear()
        reg = VendorRegistry()
        reg.register_adapter(vendor_id="vendor_corr_test", adapter_class=DummyTestAdapter)
        plugin_events = [c for c in captured if c.domain == "Plugins"]
        assert len(plugin_events) >= 2
        plug_op_id = plugin_events[0].operation_id
        assert plug_op_id is not None
        assert all(e.operation_id == plug_op_id for e in plugin_events)

        # 5. BackupRestore
        captured.clear()
        backup_file = str(tmp_path / "corr_backup.db")
        DatabaseBackupService.export_backup(temp_repo._db, backup_file)
        backup_events = [c for c in captured if c.domain == "BackupRestore"]
        assert len(backup_events) >= 2
        bk_op_id = backup_events[0].operation_id
        assert bk_op_id is not None
        assert all(e.operation_id == bk_op_id for e in backup_events)

        # 6. Export
        captured.clear()
        out_file = str(tmp_path / "corr_export.xlsx")
        InventoryExcelExporter.export(temp_repo, out_file)
        exp_events = [c for c in captured if c.domain == "Export"]
        assert len(exp_events) >= 2
        exp_op_id = exp_events[0].operation_id
        assert exp_op_id is not None
        assert all(e.operation_id == exp_op_id for e in exp_events)


# ===========================================================================
# 8. LiveLogWidget UI Streaming, Filtering, and Display Bounds
# ===========================================================================

class TestLiveLogWidgetUI:
    """Verifies Section 3 Live Log UI requirements."""

    def test_live_log_widget_loads_initial_events_and_appends_realtime(self, qapp):
        # 1. Pre-seed buffer with 2 events
        log_event("Inventory", "START", "Pre-seeded event 1")
        log_event("BOM", "COMPLETION", "Pre-seeded event 2")

        widget = LiveLogWidget()
        widget.show()
        qapp.processEvents()

        assert widget.table.rowCount() == 2
        assert "Pre-seeded event 1" in widget.table.item(0, 4).text()
        assert "Pre-seeded event 2" in widget.table.item(1, 4).text()

        # 2. Emit live event in real-time
        log_event("Export", "COMPLETION", "Real-time live export event")
        qapp.processEvents()

        assert widget.table.rowCount() == 3
        assert "Real-time live export event" in widget.table.item(2, 4).text()

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_live_log_widget_severity_and_domain_filtering(self, qapp):
        widget = LiveLogWidget()
        widget.show()
        qapp.processEvents()

        log_event("Inventory", "START", "Inv info", level="INFO")
        log_event("BOM", "FAILURE", "BOM error", level="ERROR")
        log_event("Procurement", "PROGRESS", "Proc warning", level="WARNING")
        qapp.processEvents()

        assert widget.table.rowCount() == 3

        # Filter by Severity: ERROR
        widget.severity_combo.setCurrentText("ERROR")
        qapp.processEvents()
        assert widget.table.rowCount() == 1
        assert "BOM error" in widget.table.item(0, 4).text()

        # Reset Severity, filter by Domain: Procurement
        widget.severity_combo.setCurrentText("All Severities")
        widget.domain_combo.setCurrentText("Procurement")
        qapp.processEvents()
        assert widget.table.rowCount() == 1
        assert "Proc warning" in widget.table.item(0, 4).text()

        # Text search filter
        widget.domain_combo.setCurrentText("All Domains")
        widget.search_input.setText("Inv info")
        qapp.processEvents()
        assert widget.table.rowCount() == 1
        assert "Inv info" in widget.table.item(0, 4).text()

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_live_log_widget_clear_view(self, qapp):
        widget = LiveLogWidget()
        widget.show()
        qapp.processEvents()

        log_event("System", "LOG", "Test event to clear")
        qapp.processEvents()
        assert widget.table.rowCount() == 1

        widget._on_clear_view()
        qapp.processEvents()
        assert widget.table.rowCount() == 0
        assert get_event_buffer().count() == 0

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_open_logs_folder_win32_success(self, qapp, monkeypatch):
        widget = LiveLogWidget()
        mock_startfile = MagicMock()
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(os, "startfile", mock_startfile, raising=False)

        widget._on_open_logs_folder()

        mock_startfile.assert_called_once()
        called_path = mock_startfile.call_args[0][0]
        assert os.path.isdir(called_path)

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_open_logs_folder_non_win32_success(self, qapp, monkeypatch):
        widget = LiveLogWidget()
        mock_popen = MagicMock()
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr("subprocess.Popen", mock_popen)

        widget._on_open_logs_folder()

        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "xdg-open"
        assert os.path.isdir(cmd[1])

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_open_logs_folder_handles_error_gracefully(self, qapp, monkeypatch):
        widget = LiveLogWidget()
        mock_startfile = MagicMock(side_effect=OSError("Access denied"))
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(os, "startfile", mock_startfile, raising=False)

        events_caught = []
        add_event_subscriber(events_caught.append)
        try:
            widget._on_open_logs_folder()
            qapp.processEvents()
        finally:
            remove_event_subscriber(events_caught.append)

        assert any("Could not open logs folder" in e.message and e.level == "WARNING" for e in events_caught)

        widget.close()
        widget.deleteLater()
        qapp.processEvents()

    def test_qfont_no_setpointsize_warning_on_widgets_and_dialogs(self, qapp):
        from PyQt6.QtCore import qInstallMessageHandler
        from PyQt6.QtWidgets import QComboBox
        from ui.dialogs.component_edit_dialog import ComponentEditDialog
        from ui.styles import DARK_STYLESHEET

        warnings = []
        def handler(mode, context, message):
            if "setPointSize" in message or "Point size" in message:
                warnings.append(message)

        qInstallMessageHandler(handler)
        try:
            qapp.setStyleSheet(DARK_STYLESHEET)

            # 1. ComboBox editable and non-editable
            cb = QComboBox()
            cb.setEditable(True)
            cb.show()
            qapp.processEvents()
            cb.close()

            # 2. LiveLogWidget
            ll = LiveLogWidget()
            ll.show()
            qapp.processEvents()
            ll.close()
            ll.deleteLater()

            # 3. ComponentEditDialog
            repo = SqliteInventoryRepository(":memory:")
            repo.load()
            dlg = ComponentEditDialog(repository=repo)
            dlg.show()
            qapp.processEvents()
            dlg.close()
            dlg.deleteLater()
            qapp.processEvents()
        finally:
            qInstallMessageHandler(None)

        assert len(warnings) == 0, f"Unexpected QFont warnings caught: {warnings}"
