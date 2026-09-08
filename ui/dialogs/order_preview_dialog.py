import webbrowser
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QProgressBar, QFrame,
    QMessageBox, QHeaderView, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from lion_automator import LionAutomator
from settings_manager import settings
from ui.dialogs.settings_dialog import SettingsDialog


class OrderWorkerThread(QThread):
    """Background worker thread to execute batch ordering on Lion Electronic."""

    progress_signal = pyqtSignal(int, int, str, int, str)  # current, total, part_name, qty, msg
    finished_signal = pyqtSignal(dict)

    def __init__(self, items: List[Dict[str, Any]]):
        super().__init__()
        self.items = items
        self.automator = LionAutomator()

    def run(self):
        def callback(current, total, part_name, qty, msg):
            self.progress_signal.emit(current, total, part_name, qty, msg)

        results = self.automator.order_items_batch(self.items, progress_callback=callback)
        self.finished_signal.emit(results)


class OrderPreviewDialog(QDialog):
    """
    Dialog for previewing, confirming, and executing batch purchases
    on Lion Electronic for inventory shortages and project BOM missing parts.
    Enforces strict Lion Electronic URL validation and allows immediate stock increment
    upon payment confirmation.
    """

    def __init__(
        self,
        all_shortages: Optional[List[Dict[str, Any]]] = None,
        orderable_items: Optional[List[Dict[str, Any]]] = None,
        missing_db_items: Optional[List[Dict[str, Any]]] = None,
        source_title: str = "Inventory Shortage Order",
        inventory_loader=None,
        on_stock_updated=None,
        parent=None
    ):
        super().__init__(parent)
        items_in = all_shortages if all_shortages is not None else (orderable_items or [])
        self.all_shortages = items_in
        self.missing_db_items = missing_db_items or []
        self.source_title = source_title
        self.inventory_loader = inventory_loader
        self.on_stock_updated = on_stock_updated
        self.worker: Optional[OrderWorkerThread] = None
        self._has_updated_inventory = False

        # Classify shortages
        self.lion_items: List[Dict[str, Any]] = []
        self.external_items: List[Dict[str, Any]] = []
        self.blank_link_items: List[Dict[str, Any]] = []

        for it in self.all_shortages:
            link = str(it.get("link", "")).strip()
            if link and "lionelectronic.ir" in link.lower():
                self.lion_items.append(it)
            elif link.startswith("http"):
                self.external_items.append(it)
            else:
                self.blank_link_items.append(it)

        self.invalid_items = self.external_items + self.blank_link_items

        self.setWindowTitle(f"Procurement & Order Confirmation — {source_title}")
        self.resize(980, 620)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Header Title
        title_lbl = QLabel(f"🛒 {self.source_title}")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        # Summary Subtitle
        summary_text = (
            f"<b>{len(self.lion_items)}</b> of <b>{len(self.all_shortages)}</b> shortage items have valid Lion Electronic links ready for automated purchasing."
        )
        if self.invalid_items:
            summary_text += f" &nbsp; (❌ <b>{len(self.external_items)}</b> external non-Lion links, ⚠️ <b>{len(self.blank_link_items)}</b> blank links)."
        
        desc_lbl = QLabel(summary_text)
        desc_lbl.setTextFormat(Qt.TextFormat.RichText)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Main Table of All Shortages
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Part / Designator", "Part Number / Description", "Current Stock", "Shortage Needed", "Store Link", "Validation & Status"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 240)
        self.table.setColumnWidth(5, 140)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._populate_table()
        layout.addWidget(self.table)

        # Compact Status Ribbon in footer
        status_ribbon = QFrame()
        status_ribbon.setObjectName("ribbonFrame")
        status_layout = QHBoxLayout(status_ribbon)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(10)

        # 1. Ready to Order Pill (Green)
        pill_ready = QLabel(f"✅ Ready to Order: {len(self.lion_items)}")
        pill_ready.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.12); "
            "border: 1px solid rgba(16, 185, 129, 0.35); "
            "color: #34d399; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
        )
        ready_names = [it.get("part_name") or it.get("part_number") or it.get("designator", "") for it in self.lion_items]
        pill_ready.setToolTip(f"Ready for Lion Electronic automated purchase ({len(self.lion_items)} items):\n" + "\n".join(f"• {n}" for n in ready_names[:25]))
        status_layout.addWidget(pill_ready)

        # 2. Invalid Link (Non-Lion) Pill (Red)
        if self.external_items:
            pill_ext = QLabel(f"❌ Invalid Link (Non-Lion): {len(self.external_items)}")
            pill_ext.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "border: 1px solid rgba(239, 68, 68, 0.35); "
                "color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            ext_names = [
                f"{it.get('part_name') or it.get('part_number') or it.get('designator', '')} ({it.get('link_domain', 'external')})"
                for it in self.external_items
            ]
            pill_ext.setToolTip(
                f"Non-Lion Store Links ({len(self.external_items)} items):\n"
                f"Action: Update store URLs to lionelectronic.ir in Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in ext_names[:25])
            )
            status_layout.addWidget(pill_ext)

        # 3. Blank Link Pill (Amber/Yellow)
        if self.blank_link_items:
            pill_blank = QLabel(f"⚠️ Blank Link: {len(self.blank_link_items)}")
            pill_blank.setStyleSheet(
                "background-color: rgba(245, 158, 11, 0.12); "
                "border: 1px solid rgba(245, 158, 11, 0.35); "
                "color: #fbbf24; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            blank_names = [it.get("part_name") or it.get("part_number") or it.get("designator", "") for it in self.blank_link_items]
            pill_blank.setToolTip(
                f"Blank Store Links in DB ({len(self.blank_link_items)} items):\n"
                f"Action: Add Lion Electronic product links in Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in blank_names[:25])
            )
            status_layout.addWidget(pill_blank)

        # 4. Missing DB Pill (Coral/Red)
        if self.missing_db_items:
            pill_missing = QLabel(f"🔴 Not in DB: {len(self.missing_db_items)}")
            pill_missing.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "border: 1px solid rgba(239, 68, 68, 0.35); "
                "color: #f87171; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 12px;"
            )
            missing_names = [
                it.get("part_number") or it.get("comment") or it.get("part_name", "")
                for it in self.missing_db_items
            ]
            pill_missing.setToolTip(
                f"Items Not Found in Inventory.xlsx ({len(self.missing_db_items)} items):\n"
                f"Action: Register these components into Inventory.xlsx\n\n"
                + "\n".join(f"• {n}" for n in missing_names[:25])
            )
            status_layout.addWidget(pill_missing)

        status_layout.addStretch()
        layout.addWidget(status_ribbon)

        # Progress Area
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(len(self.lion_items), 1))
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;")
        self.progress_lbl.hide()
        layout.addWidget(self.progress_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.settings_btn = QPushButton("⚙️ Account Settings")
        self.settings_btn.setObjectName("secondaryBtn")
        self.settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.settings_btn)

        btn_layout.addStretch()

        self.confirm_payment_btn = QPushButton("💰 Confirm Payment & Add Stock")
        self.confirm_payment_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover {
                background-color: #10b981;
            }
        """)
        self.confirm_payment_btn.hide()
        self.confirm_payment_btn.clicked.connect(self._confirm_payment_and_add_stock)
        btn_layout.addWidget(self.confirm_payment_btn)

        self.cancel_btn = QPushButton("Cancel / Dismiss")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.open_cart_btn = QPushButton("🛒 Open Shopping Cart in Browser")
        self.open_cart_btn.setObjectName("secondaryBtn")
        self.open_cart_btn.hide()
        self.open_cart_btn.clicked.connect(lambda: webbrowser.open("https://lionelectronic.ir/orders/cart"))
        btn_layout.addWidget(self.open_cart_btn)

        self.order_btn = QPushButton(f"🛒 Order {len(self.lion_items)} Items on Lion Electronic")
        self.order_btn.clicked.connect(self._start_order)
        if len(self.lion_items) == 0:
            self.order_btn.setText("🛒 No Valid Lion Items to Order")
            self.order_btn.setEnabled(False)
        btn_layout.addWidget(self.order_btn)

        layout.addLayout(btn_layout)

    def _populate_table(self):
        self.table.setRowCount(len(self.all_shortages))
        font_num = QFont("Consolas", 10)
        font_txt = QFont("Segoe UI", 10)

        for row_idx, it in enumerate(self.all_shortages):
            # 0. Part Name / Designator
            p_name = it.get("part_name") or it.get("designator", "")
            item0 = QTableWidgetItem(p_name)
            item0.setFont(font_txt)
            self.table.setItem(row_idx, 0, item0)

            # 1. Description / Part No
            p_desc = it.get("description") or it.get("part_number") or it.get("comment", "")
            item1 = QTableWidgetItem(p_desc)
            item1.setFont(font_txt)
            self.table.setItem(row_idx, 1, item1)

            # 2. Current Stock
            stock_val = str(it.get("current_stock", 0))
            item2 = QTableWidgetItem(stock_val)
            item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item2.setFont(font_num)
            self.table.setItem(row_idx, 2, item2)

            # 3. Shortage Needed
            needed_val = str(it.get("needed_qty", 1))
            item3 = QTableWidgetItem(needed_val)
            item3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item3.setFont(font_num)
            item3.setForeground(QColor("#fbbf24"))  # Amber
            self.table.setItem(row_idx, 3, item3)

            # 4. Link
            link_val = str(it.get("link", "")).strip()
            item4 = QTableWidgetItem(link_val)
            item4.setFont(font_txt)
            if link_val.startswith("http"):
                if "lionelectronic.ir" in link_val.lower():
                    item4.setForeground(QColor("#38bdf8"))  # Cyan Lion link
                    item4.setToolTip(f"Lion Electronic link: {link_val}")
                else:
                    item4.setText(f"❌ Non-Lion URL ({it.get('link_domain', '')})")
                    item4.setForeground(QColor("#f87171"))  # Red invalid
                    item4.setToolTip(f"Invalid store link ({link_val}). Please update to lionelectronic.ir in Inventory.xlsx.")
            else:
                item4.setText("— Blank Store Link —")
                item4.setForeground(QColor("#f87171"))
                item4.setToolTip("Missing/blank store link. Please add Lion Electronic URL in Inventory.xlsx.")
            self.table.setItem(row_idx, 4, item4)

            # 5. Status
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFont(font_txt)

            if link_val and "lionelectronic.ir" in link_val.lower():
                status_item.setText("✅ Lion Ready")
                status_item.setForeground(QColor("#34d399"))
                status_item.setToolTip("Lion Electronic store link verified. Ready for automated purchase.")
            elif link_val.startswith("http"):
                domain = it.get("link_domain") or "External"
                status_item.setText("❌ Invalid Link")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip(f"Invalid link ({domain}). Automated purchasing strictly requires lionelectronic.ir. Update in Inventory.xlsx.")
            else:
                status_item.setText("❌ Blank Link")
                status_item.setForeground(QColor("#f87171"))
                status_item.setToolTip("Blank store link. Component exists in inventory database but has no store URL.")

            self.table.setItem(row_idx, 5, status_item)

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        row = item.row()
        if 0 <= row < len(self.all_shortages):
            url = str(self.all_shortages[row].get("link", "")).strip()
            if url.startswith("http"):
                webbrowser.open(url)

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _start_order(self):
        if not self.lion_items:
            return

        user = settings.get("lion_username", "").strip()
        pwd = settings.get("lion_password", "").strip()

        if not user or not pwd:
            QMessageBox.warning(
                self,
                "Credentials Required",
                "Please configure your Lion Electronic username and password in Settings before ordering."
            )
            self._open_settings()
            return

        self.order_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.progress_lbl.show()
        show_browser = settings.get("show_browser", False)
        init_msg = "Launching Chrome and authenticating..." if show_browser else "Authenticating and ordering in background..."
        self.progress_lbl.setText(init_msg)

        self.worker = OrderWorkerThread(self.lion_items)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current: int, total: int, part_name: str, qty: int, msg: str):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(f"[{current}/{total}] {part_name}: {msg}")

        # Update matching table row status using exact item identity or part_name + link
        if 0 <= current - 1 < len(self.lion_items):
            target_item = self.lion_items[current - 1]
            t_name = (target_item.get("part_name") or target_item.get("part_number") or target_item.get("designator", "")).strip().lower()
            t_link = str(target_item.get("link", "")).strip().lower()

            for row in range(self.table.rowCount()):
                row_it = self.all_shortages[row] if row < len(self.all_shortages) else None
                matched = False
                if row_it is target_item:
                    matched = True
                elif row_it:
                    r_name = (row_it.get("part_name") or row_it.get("part_number") or row_it.get("designator", "")).strip().lower()
                    r_link = str(row_it.get("link", "")).strip().lower()
                    if r_name == t_name and r_link == t_link:
                        matched = True
                    elif r_name == t_name:
                        matched = True

                if matched:
                    status_item = self.table.item(row, 5)
                    if status_item:
                        if "Partial" in msg:
                            status_item.setText(f"⚠️ Partial ({qty} pcs)")
                            status_item.setForeground(QColor("#fbbf24"))  # Amber
                            status_item.setToolTip(f"Partial site stock added: {msg}")
                        elif "Added" in msg or "Queued" in msg:
                            status_item.setText(f"✅ Added {qty} pcs")
                            status_item.setForeground(QColor("#34d399"))  # Green
                            status_item.setToolTip(f"Successfully added to cart: {msg}")
                        elif "Insufficient" in msg:
                            status_item.setText("⚠️ Low Site Stock")
                            status_item.setForeground(QColor("#fbbf24"))  # Amber
                            status_item.setToolTip(f"Insufficient stock on store: {msg}")
                        elif "Inquiry" in msg or "Sale Closed" in msg:
                            status_item.setText("⚠️ Inquiry Only")
                            status_item.setForeground(QColor("#fbbf24"))  # Amber
                            status_item.setToolTip(f"Inquiry Only / Sale Closed on Lion: {msg}")
                        elif "Coming Soon" in msg:
                            status_item.setText("⏳ Coming Soon")
                            status_item.setForeground(QColor("#fbbf24"))  # Amber
                            status_item.setToolTip(f"Coming Soon: {msg}")
                        elif "Out of stock" in msg or "0 available" in msg:
                            status_item.setText("❌ Out of Stock")
                            status_item.setForeground(QColor("#f87171"))  # Red
                            status_item.setToolTip(f"Out of stock on store: {msg}")
                        else:
                            short_txt = msg[:18] if len(msg) > 18 else msg
                            status_item.setText(f"❌ {short_txt}")
                            status_item.setForeground(QColor("#f87171"))
                            status_item.setToolTip(msg)
                    break

    def _on_finished(self, results: Dict[str, Any]):
        self.order_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.open_cart_btn.show()
        self.confirm_payment_btn.show()
        self.confirm_payment_btn.setEnabled(True)

        show_browser = settings.get("show_browser", False)

        if results.get("success"):
            succ_count = results.get('successful_count', 0)
            self.progress_lbl.setText(f"✅ Order batch completed! ({succ_count} items in cart)")
            self.progress_lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold;")
            
            if show_browser:
                QMessageBox.information(
                    self,
                    "Order Processed",
                    f"Successfully added {succ_count} items into your Lion Electronic cart!\n\n"
                    f"The Chrome browser window has opened directly to your shopping cart. "
                    f"Please review your items and finalize your checkout in Chrome."
                )
            else:
                QMessageBox.information(
                    self,
                    "Order Processed",
                    f"Successfully added {succ_count} items into your Lion Electronic cart in the background!\n\n"
                    f"Click OK to open your shopping cart in your web browser."
                )
                webbrowser.open("https://lionelectronic.ir/orders/cart")
        else:
            self.progress_lbl.setText(f"❌ Order issue: {results.get('message', 'Unknown error')}")
            self.progress_lbl.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold;")
            QMessageBox.warning(
                self,
                "Order Incomplete",
                f"Automated ordering encountered an issue:\n{results.get('message')}"
            )

    def _confirm_payment_and_add_stock(self):
        if self._has_updated_inventory:
            QMessageBox.information(self, "Already Updated", "Inventory stock has already been updated for this batch.")
            return

        if not self.inventory_loader:
            QMessageBox.warning(self, "No Database", "Active inventory database reference is not available.")
            return

        # Strictly filter ONLY items that were successfully added to the cart
        success_items = []
        for it in self.lion_items:
            if it.get("order_success") is True and (it.get("actual_ordered_qty") or 0) > 0:
                success_items.append(it)
            elif it.get("order_success") is None:
                # If batch ordering was not yet run, check explicit positive ordered quantity
                qty = it.get("actual_ordered_qty") if it.get("actual_ordered_qty") is not None else it.get("qty_ordered")
                if qty is not None and qty > 0:
                    success_items.append(it)

        if not success_items:
            QMessageBox.information(
                self,
                "No Items Ordered",
                "No items were successfully purchased in this batch to add to inventory.\n"
                "(Items with insufficient stock, coming-soon status, or errors are strictly excluded)."
            )
            return

        # Prepare summary of quantities to add based on actual ordered amounts
        lines = []
        for it in success_items:
            name = it.get("part_name") or it.get("part_number") or it.get("designator", "")
            qty = it.get("actual_ordered_qty") if it.get("actual_ordered_qty") is not None else (it.get("qty_ordered") or 0)
            if qty > 0:
                lines.append(f"• <b>{name}</b>: +{qty} pcs")

        items_text = "<br>".join(lines[:15])
        if len(lines) > 15:
            items_text += f"<br><i>(+{len(lines)-15} more items)</i>"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Payment & Stock Update")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(
            f"<b>Did you complete and pay for this order on Lion Electronic?</b><br><br>"
            f"The following successfully purchased quantities (<b>{len(success_items)} item(s)</b>) will be added to <code>Quantity in Stock</code> in <code>Inventory.xlsx</code>:<br><br>"
            f"{items_text}<br><br>"
            f"Click <b>Yes</b> to add these quantities to your inventory now."
        )
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton("Yes, Add to Inventory", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("No / Cancel", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(yes_btn)
        msg_box.exec()

        if msg_box.clickedButton() != yes_btn:
            return

        count, msg = self.inventory_loader.batch_increment_stock(success_items)
        if count > 0:
            self._has_updated_inventory = True
            self.confirm_payment_btn.setText("✅ Stock Added to Inventory")
            self.confirm_payment_btn.setEnabled(False)
            self.confirm_payment_btn.setStyleSheet("background-color: #1e293b; color: #34d399; font-weight: bold;")

            QMessageBox.information(
                self,
                "Inventory Updated",
                f"✅ Success!\n\n{count} item(s) have been added to your current stock in Inventory.xlsx."
            )

            if self.on_stock_updated:
                self.on_stock_updated()
        else:
            QMessageBox.warning(
                self,
                "Update Failed",
                f"Could not update stock in Inventory.xlsx:\n{msg}"
            )

