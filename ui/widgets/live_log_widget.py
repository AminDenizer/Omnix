"""
Omnix UI — Live Log & Event Reporting View
Governing Requirement: Section 3 — Live Log & Event Reporting

Provides:
- Real-time diagnostic event stream with thread-safe UI updates
- Formatted timestamps, color-coded severity badges (INFO, WARNING, ERROR), domains, and lifecycle phases
- Quick filtering by Severity and Domain, plus real-time text search
- Bounded row retention matching the in-memory circular buffer (max 1000 events)
- Export to text/CSV and buffer clear capability
- Native Omnix matte dark design system styling
"""

import os
import sys
import subprocess
from typing import Optional, List
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QAbstractItemView,
)

from core.logger import (
    EventRecord,
    get_event_buffer,
    get_event_bridge,
    get_log_dir,
    log_event,
)


class LiveLogWidget(QWidget):
    """
    Real-time Live Log & Event Reporting widget.
    Subscribes to Qt event bridge for thread-safe event streaming.
    """

    MAX_DISPLAY_ROWS = 1000

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("liveLogWidget")
        self._all_records: List[EventRecord] = []
        self._auto_scroll = True
        self._init_ui()
        self._connect_signals()
        self._load_initial_events()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------------
        # Header Card
        # -------------------------------------------------------------------
        header_card = QFrame()
        header_card.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px 16px;
            }
        """)
        hdr_layout = QHBoxLayout(header_card)
        hdr_layout.setContentsMargins(0, 0, 0, 0)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(4)
        title_lbl = QLabel("Live Log & Event Reporting")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #f8fafc;")
        sub_lbl = QLabel("Real-time diagnostic event stream, operation lifecycles, and audit history.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        hdr_layout.addLayout(title_vbox, 1)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.open_log_folder_btn = QPushButton("Open Logs Folder")
        self.open_log_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.open_log_folder_btn.clicked.connect(self._on_open_logs_folder)
        btn_box.addWidget(self.open_log_folder_btn)

        self.export_btn = QPushButton("Export Log...")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0369a1;
                color: #ffffff;
            }
        """)
        self.export_btn.clicked.connect(self._on_export_log)
        btn_box.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear View")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f87171;
                border: 1px solid #7f1d1d;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #991b1b;
                color: #ffffff;
            }
        """)
        self.clear_btn.clicked.connect(self._on_clear_view)
        btn_box.addWidget(self.clear_btn)

        hdr_layout.addLayout(btn_box)
        main_layout.addWidget(header_card)

        # -------------------------------------------------------------------
        # Filter & Search Toolbar
        # -------------------------------------------------------------------
        filter_bar = QFrame()
        filter_bar.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px 12px;
            }
        """)
        fb_layout = QHBoxLayout(filter_bar)
        fb_layout.setContentsMargins(0, 0, 0, 0)
        fb_layout.setSpacing(12)

        # Severity Filter
        fb_layout.addWidget(QLabel("Severity:"))
        self.severity_combo = QComboBox()
        self.severity_combo.addItems(["All Severities", "INFO", "WARNING", "ERROR"])
        self.severity_combo.setStyleSheet(self._combo_style())
        self.severity_combo.currentIndexChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.severity_combo)

        # Domain Filter
        fb_layout.addWidget(QLabel("Domain:"))
        self.domain_combo = QComboBox()
        self.domain_combo.addItems([
            "All Domains",
            "Inventory",
            "BOM",
            "Procurement",
            "Plugins",
            "BackupRestore",
            "Export",
            "System",
        ])
        self.domain_combo.setStyleSheet(self._combo_style())
        self.domain_combo.currentIndexChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.domain_combo)

        # Search Query
        fb_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter messages or correlation IDs...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                padding: 5px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.search_input.textChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.search_input, 1)

        # Auto-scroll checkbox
        self.autoscroll_chk = QCheckBox("Auto-scroll")
        self.autoscroll_chk.setChecked(True)
        self.autoscroll_chk.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.autoscroll_chk.toggled.connect(self._on_autoscroll_toggled)
        fb_layout.addWidget(self.autoscroll_chk)

        main_layout.addWidget(filter_bar)

        # -------------------------------------------------------------------
        # Event Table
        # -------------------------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Timestamp (UTC)",
            "Severity",
            "Domain",
            "Phase",
            "Message",
        ])
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0b101b;
                alternate-background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #f8fafc;
                gridline-color: #1e293b;
                font-size: 12px;
                selection-background-color: #1e293b;
                selection-color: #38bdf8;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #1e293b;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                padding: 8px 10px;
                border: none;
                border-right: 1px solid #334155;
                font-weight: 700;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QHeaderView::section:last {
                border-right: none;
            }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(0, 160)  # Timestamp
        self.table.setColumnWidth(1, 90)   # Severity
        self.table.setColumnWidth(2, 110)  # Domain
        self.table.setColumnWidth(3, 100)  # Phase

        main_layout.addWidget(self.table, 1)

        # Status / Counter Label
        self.count_lbl = QLabel("0 events recorded")
        self.count_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        main_layout.addWidget(self.count_lbl)

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                padding: 4px 8px;
                font-size: 9pt;
                min-width: 110px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                border: 1px solid #334155;
                selection-background-color: #1e293b;
                color: #f8fafc;
            }
        """

    def _connect_signals(self):
        bridge = get_event_bridge()
        if hasattr(bridge, "eventLogged"):
            bridge.eventLogged.connect(self._on_event_received)

    def _load_initial_events(self):
        records = get_event_buffer().get_all()
        for r in records:
            self._append_record_internal(r)
        self._update_counter()

    def _on_event_received(self, record: EventRecord):
        """Slot invoked via Qt signal bridge on main GUI thread."""
        self._append_record_internal(record)
        self._update_counter()

    def _append_record_internal(self, record: EventRecord):
        self._all_records.append(record)
        if len(self._all_records) > self.MAX_DISPLAY_ROWS:
            self._all_records = self._all_records[-self.MAX_DISPLAY_ROWS:]

        if not self._record_matches_filters(record):
            return

        row = self.table.rowCount()
        self.table.insertRow(row)

        # 0. Timestamp
        t_str = record.timestamp.replace("T", " ")[:19]
        it_ts = QTableWidgetItem(t_str)
        it_ts.setForeground(QColor("#94a3b8"))
        it_ts.setToolTip(record.timestamp)
        self.table.setItem(row, 0, it_ts)

        # 1. Severity Badge
        it_sev = QTableWidgetItem(record.level)
        if record.level == "ERROR":
            it_sev.setForeground(QColor("#f87171"))  # Red
        elif record.level == "WARNING":
            it_sev.setForeground(QColor("#fbbf24"))  # Amber
        else:
            it_sev.setForeground(QColor("#38bdf8"))  # Cyan
        font_b = it_sev.font()
        font_b.setBold(True)
        it_sev.setFont(font_b)
        self.table.setItem(row, 1, it_sev)

        # 2. Domain
        it_dom = QTableWidgetItem(record.domain)
        it_dom.setForeground(QColor("#e2e8f0"))
        self.table.setItem(row, 2, it_dom)

        # 3. Phase / Event Type
        it_phase = QTableWidgetItem(record.event_type)
        it_phase.setForeground(QColor("#cbd5e1"))
        self.table.setItem(row, 3, it_phase)

        # 4. Message
        msg_display = record.message
        if record.operation_id:
            msg_display = f"[{record.operation_id}] {msg_display}"
        it_msg = QTableWidgetItem(msg_display)
        it_msg.setForeground(QColor("#f8fafc"))
        it_msg.setToolTip(record.message)
        self.table.setItem(row, 4, it_msg)

        # Prune excess rows in table if exceeded
        if self.table.rowCount() > self.MAX_DISPLAY_ROWS:
            self.table.removeRow(0)

        if self._auto_scroll:
            self.table.scrollToBottom()

    def _record_matches_filters(self, record: EventRecord) -> bool:
        # Severity
        sev_filter = self.severity_combo.currentText()
        if sev_filter != "All Severities" and record.level != sev_filter:
            return False

        # Domain
        dom_filter = self.domain_combo.currentText()
        if dom_filter != "All Domains" and record.domain.lower() != dom_filter.lower():
            return False

        # Search Query
        query = self.search_input.text().strip().lower()
        if query:
            haystack = f"{record.message} {record.domain} {record.event_type} {record.operation_id or ''} {record.timestamp}".lower()
            if query not in haystack:
                return False

        return True

    def _apply_filters(self):
        """Re-populates table with currently filtered records."""
        self.table.setRowCount(0)
        matching = [r for r in self._all_records if self._record_matches_filters(r)]
        for r in matching:
            row = self.table.rowCount()
            self.table.insertRow(row)

            t_str = r.timestamp.replace("T", " ")[:19]
            it_ts = QTableWidgetItem(t_str)
            it_ts.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 0, it_ts)

            it_sev = QTableWidgetItem(r.level)
            if r.level == "ERROR":
                it_sev.setForeground(QColor("#f87171"))
            elif r.level == "WARNING":
                it_sev.setForeground(QColor("#fbbf24"))
            else:
                it_sev.setForeground(QColor("#38bdf8"))
            font_b = it_sev.font()
            font_b.setBold(True)
            it_sev.setFont(font_b)
            self.table.setItem(row, 1, it_sev)

            it_dom = QTableWidgetItem(r.domain)
            it_dom.setForeground(QColor("#e2e8f0"))
            self.table.setItem(row, 2, it_dom)

            it_phase = QTableWidgetItem(r.event_type)
            it_phase.setForeground(QColor("#cbd5e1"))
            self.table.setItem(row, 3, it_phase)

            msg_display = r.message
            if r.operation_id:
                msg_display = f"[{r.operation_id}] {msg_display}"
            it_msg = QTableWidgetItem(msg_display)
            it_msg.setForeground(QColor("#f8fafc"))
            self.table.setItem(row, 4, it_msg)

        if self._auto_scroll:
            self.table.scrollToBottom()
        self._update_counter()

    def _on_autoscroll_toggled(self, checked: bool):
        self._auto_scroll = checked
        if checked:
            self.table.scrollToBottom()

    def _on_clear_view(self):
        self.table.setRowCount(0)
        self._all_records.clear()
        get_event_buffer().clear()
        self._update_counter()

    def _on_export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostic Events",
            os.path.join(get_log_dir(), "events_export.txt"),
            "Text Log (*.txt);;CSV (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                if path.endswith(".csv"):
                    f.write("Timestamp,Severity,Domain,Phase,OperationID,Message\n")
                    for r in self._all_records:
                        op = r.operation_id or ""
                        msg = r.message.replace('"', '""')
                        f.write(f'"{r.timestamp}","{r.level}","{r.domain}","{r.event_type}","{op}","{msg}"\n')
                else:
                    for r in self._all_records:
                        op = f" [{r.operation_id}]" if r.operation_id else ""
                        f.write(f"{r.timestamp} [{r.level}] [{r.domain}:{r.event_type}]{op} {r.message}\n")
            log_event("Export", "COMPLETION", f"Exported diagnostic log view to {os.path.basename(path)}")
        except Exception as e:
            log_event("Export", "FAILURE", f"Failed to export diagnostic log view: {e}", level="ERROR")

    def _on_open_logs_folder(self):
        folder = get_log_dir()
        try:
            os.makedirs(folder, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except (OSError, subprocess.SubprocessError) as e:
            log_event("LiveLog", "FAILURE", f"Could not open logs folder '{folder}': {e}", level="WARNING")

    def _update_counter(self):
        total = len(self._all_records)
        shown = self.table.rowCount()
        if shown == total:
            self.count_lbl.setText(f"{total} events recorded")
        else:
            self.count_lbl.setText(f"Showing {shown} of {total} events recorded")
