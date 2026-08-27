import sqlite3
import datetime
from typing import List, Optional, Dict, Any, Set
from models import Component
from config import (
    DEFAULT_CATEGORIES,
    DEFAULT_PACKAGES,
    DEFAULT_APP_SETTINGS,
    DEFAULT_DB_FILENAME,
    get_default_db_path
)

COMMON_PACKAGES = DEFAULT_PACKAGES


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path if db_path is not None else get_default_db_path()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Components table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    package TEXT,
                    category TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    min_alert INTEGER NOT NULL DEFAULT 10,
                    drawers TEXT NOT NULL DEFAULT '',
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Stock history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component_id INTEGER NOT NULL,
                    change_type TEXT NOT NULL DEFAULT 'ADD',
                    amount INTEGER NOT NULL DEFAULT 0,
                    previous_qty INTEGER NOT NULL DEFAULT 0,
                    new_qty INTEGER NOT NULL DEFAULT 0,
                    drawer_number INTEGER,
                    note TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
                )
            """)

            # Custom categories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Custom packages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Application settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Default category mode setting ('DEFAULT' | 'CUSTOM')
            cursor.execute("""
                INSERT OR IGNORE INTO app_settings (key, value)
                VALUES ('category_mode', 'DEFAULT')
            """)

            # Default package mode setting ('DEFAULT' | 'CUSTOM')
            cursor.execute("""
                INSERT OR IGNORE INTO app_settings (key, value)
                VALUES ('package_mode', 'DEFAULT')
            """)

            # ================= SCHEMA MIGRATION =================
            # Ensure stock_history has all columns
            cursor.execute("PRAGMA table_info(stock_history)")
            hist_cols = [r['name'] for r in cursor.fetchall()]
            if 'change_type' not in hist_cols and len(hist_cols) > 0:
                cursor.execute("ALTER TABLE stock_history ADD COLUMN change_type TEXT NOT NULL DEFAULT 'ADD'")
            if 'amount' not in hist_cols and len(hist_cols) > 0:
                cursor.execute("ALTER TABLE stock_history ADD COLUMN amount INTEGER NOT NULL DEFAULT 0")
            if 'previous_qty' not in hist_cols and len(hist_cols) > 0:
                cursor.execute("ALTER TABLE stock_history ADD COLUMN previous_qty INTEGER NOT NULL DEFAULT 0")
            if 'new_qty' not in hist_cols and len(hist_cols) > 0:
                cursor.execute("ALTER TABLE stock_history ADD COLUMN new_qty INTEGER NOT NULL DEFAULT 0")
            if 'drawer_number' not in hist_cols and len(hist_cols) > 0:
                cursor.execute("ALTER TABLE stock_history ADD COLUMN drawer_number INTEGER")

            # Ensure components has 'drawers' column
            cursor.execute("PRAGMA table_info(components)")
            comp_cols = [r['name'] for r in cursor.fetchall()]
            if 'drawers' not in comp_cols and len(comp_cols) > 0:
                cursor.execute("ALTER TABLE components ADD COLUMN drawers TEXT")
                print("[INFO] [DB] Migrated components table: added 'drawers' column")

            # Ensure all legacy categories are migrated to clean standard English
            category_mapping = {
                "مقاومت (Resistor)": "Resistor",
                "مقاومت": "Resistor",
                "خازن (Capacitor)": "Capacitor",
                "خازن": "Capacitor",
                "سلف و بوبین (Inductor)": "Inductor",
                "سلف": "Inductor",
                "دیود و ال‌ای‌دی (Diode/LED)": "Diode / LED",
                "دیود": "Diode / LED",
                "ترانزیستور و ماسفت (Transistor/MOSFET)": "Transistor / MOSFET",
                "ترانزیستور": "Transistor / MOSFET",
                "آی‌سی و رگولاتور (IC/Regulator)": "IC / Regulator",
                "آی‌سی": "IC / Regulator",
                "میکروکنترلر و پروسسور (MCU)": "Microcontroller (MCU)",
                "میکروکنترلر": "Microcontroller (MCU)",
                "کانکتور و ترمینال (Connector)": "Connector / Terminal",
                "کانکتور": "Connector / Terminal",
                "کلید و رله (Switch/Relay)": "Switch / Relay",
                "کلید": "Switch / Relay",
                "ماژول و سنسور (Module/Sensor)": "Sensor / Module",
                "سنسور": "Sensor / Module",
                "ماژول": "Sensor / Module",
                "کریستال و نوسان‌ساز (Crystal)": "Crystal / Oscillator",
                "کریستال": "Crystal / Oscillator",
                "فیوز و محافظتی (Protection)": "Protection / Fuse",
                "فیوز": "Protection / Fuse",
                "سایر قطعات (Other)": "Other",
                "سایر": "Other"
            }
            for old_cat, new_cat in category_mapping.items():
                cursor.execute("UPDATE components SET category = ? WHERE category = ?", (new_cat, old_cat))
                cursor.execute("UPDATE custom_categories SET name = ? WHERE name = ?", (new_cat, old_cat))

            # Normalize package and category empty values to '—'
            cursor.execute("UPDATE components SET package = '—' WHERE package IS NULL OR TRIM(package) = ''")
            cursor.execute("UPDATE components SET category = '—' WHERE category IS NULL OR TRIM(category) = ''")

            conn.commit()
            print(f"[INFO] [DB] SQLite database initialized at {self.db_path}")

    # ================= Category Management =================

    def get_category_mode(self) -> str:
        """Returns the active category mode: 'DEFAULT' or 'CUSTOM'"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = 'category_mode'")
            row = cursor.fetchone()
            return row['value'] if row else "DEFAULT"

    def set_category_mode(self, mode: str) -> bool:
        """Updates active category mode ('DEFAULT' or 'CUSTOM')"""
        clean_mode = "CUSTOM" if mode.upper() == "CUSTOM" else "DEFAULT"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_settings (key, value)
                VALUES ('category_mode', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (clean_mode,))
            conn.commit()
            print(f"[INFO] [DB] Category mode changed to: {clean_mode}")
            return True

    def get_categories(self) -> List[str]:
        """Returns the active list of categories depending on the current mode"""
        mode = self.get_category_mode()
        if mode == "CUSTOM":
            customs = self.get_custom_categories()
            if customs:
                return (["—"] if "—" not in customs else []) + customs
            return DEFAULT_CATEGORIES
        return DEFAULT_CATEGORIES

    def get_custom_categories(self) -> List[str]:
        """Returns all custom user-defined categories sorted alphabetically"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM custom_categories ORDER BY name ASC")
            rows = cursor.fetchall()
            return [r['name'] for r in rows]

    def add_custom_category(self, name: str) -> bool:
        """Adds a new custom category"""
        clean_name = name.strip()
        if not clean_name:
            return False
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO custom_categories (name, created_at)
                    VALUES (?, ?)
                """, (clean_name, now))
                conn.commit()
                print(f"[INFO] [DB] Added custom category: '{clean_name}'")
                return True
        except sqlite3.IntegrityError:
            return False

    def delete_custom_category(self, name: str) -> bool:
        """Deletes a custom category by name"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM custom_categories WHERE name = ?", (name,))
            conn.commit()
            print(f"[INFO] [DB] Deleted custom category: '{name}'")
            return True

    # ================= Package Management =================

    def get_package_mode(self) -> str:
        """Returns the active package mode: 'DEFAULT' or 'CUSTOM'"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = 'package_mode'")
            row = cursor.fetchone()
            return row['value'] if row else "DEFAULT"

    def set_package_mode(self, mode: str) -> bool:
        """Updates active package mode ('DEFAULT' or 'CUSTOM')"""
        clean_mode = "CUSTOM" if mode.upper() == "CUSTOM" else "DEFAULT"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_settings (key, value)
                VALUES ('package_mode', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (clean_mode,))
            conn.commit()
            print(f"[INFO] [DB] Package mode changed to: {clean_mode}")
            return True

    def get_packages(self) -> List[str]:
        """Returns the active list of packages depending on the current mode"""
        mode = self.get_package_mode()
        if mode == "CUSTOM":
            customs = self.get_custom_packages()
            if customs:
                return (["—"] if "—" not in customs else []) + customs
            return DEFAULT_PACKAGES
        return DEFAULT_PACKAGES

    def get_custom_packages(self) -> List[str]:
        """Returns all custom user-defined packages sorted alphabetically"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM custom_packages ORDER BY name ASC")
            rows = cursor.fetchall()
            return [r['name'] for r in rows]

    def add_custom_package(self, name: str) -> bool:
        """Adds a new custom package"""
        clean_name = name.strip()
        if not clean_name:
            return False
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO custom_packages (name, created_at)
                    VALUES (?, ?)
                """, (clean_name, now))
                conn.commit()
                print(f"[INFO] [DB] Added custom package: '{clean_name}'")
                return True
        except sqlite3.IntegrityError:
            return False

    def delete_custom_package(self, name: str) -> bool:
        """Deletes a custom package by name"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM custom_packages WHERE name = ?", (name,))
            conn.commit()
            print(f"[INFO] [DB] Deleted custom package: '{name}'")
            return True

    # ================= Component CRUD =================

    def add_component(self, comp: Component) -> int:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Format drawer stocks
            if comp.drawer_stocks:
                drawers_str = ", ".join([f"{d}:{q}" for d, q in sorted(comp.drawer_stocks.items())])
                total_qty = sum(comp.drawer_stocks.values())
            else:
                drawers_str = comp.drawers.strip()
                total_qty = max(0, int(comp.quantity))

            cursor.execute("""
                INSERT INTO components (name, value, package, category, quantity, min_alert, drawers, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comp.name.strip(),
                comp.value.strip(),
                comp.package.strip(),
                comp.category.strip() if comp.category else "Other",
                total_qty,
                max(0, int(comp.min_alert)),
                drawers_str,
                comp.description.strip(),
                now,
                now
            ))
            comp_id = cursor.lastrowid
            
            # Log initial creation in history
            cursor.execute("""
                INSERT INTO stock_history (component_id, change_type, amount, previous_qty, new_qty, note, timestamp)
                VALUES (?, 'ADD', ?, 0, ?, 'Initial registration', ?)
            """, (comp_id, total_qty, total_qty, now))
            
            conn.commit()
            print(f"[INFO] [DB] Component added: ID={comp_id}, Value='{comp.value}', TotalQty={total_qty}")
            return comp_id

    def update_component(self, comp: Component) -> bool:
        if comp.id is None:
            return False
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Retrieve previous quantity
            cursor.execute("SELECT quantity FROM components WHERE id = ?", (comp.id,))
            row = cursor.fetchone()
            old_qty = row['quantity'] if row else 0

            # Format drawer stocks
            if comp.drawer_stocks:
                drawers_str = ", ".join([f"{d}:{q}" for d, q in sorted(comp.drawer_stocks.items())])
                new_qty = sum(comp.drawer_stocks.values())
            else:
                drawers_str = comp.drawers.strip()
                new_qty = max(0, int(comp.quantity))

            if old_qty != new_qty:
                diff = new_qty - old_qty
                c_type = "ADD" if diff > 0 else "DEDUCT"
                cursor.execute("""
                    INSERT INTO stock_history (component_id, change_type, amount, previous_qty, new_qty, note, timestamp)
                    VALUES (?, ?, ?, ?, ?, 'Direct edit from form', ?)
                """, (comp.id, c_type, abs(diff), old_qty, new_qty, now))

            cursor.execute("""
                UPDATE components
                SET name = ?, value = ?, package = ?, category = ?, quantity = ?, min_alert = ?, drawers = ?, description = ?, updated_at = ?
                WHERE id = ?
            """, (
                comp.name.strip(),
                comp.value.strip(),
                comp.package.strip(),
                comp.category.strip() if comp.category else "Other",
                new_qty,
                max(0, int(comp.min_alert)),
                drawers_str,
                comp.description.strip(),
                now,
                comp.id
            ))
            conn.commit()
            print(f"[INFO] [DB] Component updated: ID={comp.id}, Value='{comp.value}', NewQty={new_qty}")
            return cursor.rowcount > 0

    def delete_component(self, comp_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM components WHERE id = ?", (comp_id,))
            cursor.execute("DELETE FROM stock_history WHERE component_id = ?", (comp_id,))
            conn.commit()
            print(f"[INFO] [DB] Component deleted: ID={comp_id}")
            return cursor.rowcount > 0

    def get_component(self, comp_id: int) -> Optional[Component]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM components WHERE id = ?", (comp_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_component(row)
            return None

    def get_all_components(self) -> List[Component]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM components ORDER BY id DESC")
            rows = cursor.fetchall()
            return [self._row_to_component(r) for r in rows]

    def search_components(self, query: str = "", category: str = "", stock_filter: str = "ALL") -> List[Component]:
        all_comps = self.get_all_components()
        results = []

        clean_q = query.strip().lower()
        is_num = clean_q.isdigit()
        search_drawer_num = int(clean_q) if is_num else None

        for comp in all_comps:
            # Category filter
            if category and category not in ("همه دسته‌ها", "All Categories") and comp.category != category:
                continue

            # Stock filter
            if stock_filter == "IN_STOCK" and comp.stock_status != "OK":
                continue
            elif stock_filter == "LOW_STOCK" and comp.stock_status != "LOW":
                continue
            elif stock_filter == "EMPTY" and comp.stock_status != "EMPTY":
                continue

            # Text / Drawer search filter
            if clean_q:
                match_text = (
                    clean_q in comp.name.lower() or
                    clean_q in comp.value.lower() or
                    clean_q in comp.package.lower() or
                    clean_q in comp.description.lower()
                )
                match_drawer = False
                if search_drawer_num is not None:
                    match_drawer = search_drawer_num in comp.drawer_list
                else:
                    match_drawer = clean_q in comp.drawers.lower()

                if not (match_text or match_drawer):
                    continue

            results.append(comp)

        return results

    def get_components_by_drawer(self, drawer_number: int) -> List[Component]:
        all_comps = self.get_all_components()
        return [c for c in all_comps if drawer_number in c.drawer_list]

    def get_all_used_drawers(self) -> List[int]:
        all_comps = self.get_all_components()
        drawer_set: Set[int] = set()
        for comp in all_comps:
            drawer_set.update(comp.drawer_list)
        return sorted(list(drawer_set))

    # ================= Multi-Drawer Stock Operations =================

    def adjust_single_drawer_stock(self, comp_id: int, drawer_num: int, delta: int, note: str = "") -> Optional[int]:
        """Adjusts stock for a single specified drawer on a component (+1 or -1)"""
        comp = self.get_component(comp_id)
        if not comp:
            return None

        current_stocks = comp.drawer_stocks
        if drawer_num not in current_stocks:
            current_stocks[drawer_num] = 0

        old_drawer_qty = current_stocks[drawer_num]
        new_drawer_qty = max(0, old_drawer_qty + delta)
        
        # If deducting more than available in this drawer
        if delta < 0 and old_drawer_qty <= 0:
            print(f"[WARN] [STOCK] Drawer {drawer_num} of Component ID={comp_id} is already empty (qty=0)")
            return None

        actual_delta = new_drawer_qty - old_drawer_qty
        current_stocks[drawer_num] = new_drawer_qty
        comp.drawer_stocks = current_stocks

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE components
                SET quantity = ?, drawers = ?, updated_at = ?
                WHERE id = ?
            """, (comp.quantity, comp.drawers, now, comp_id))

            c_type = "ADD" if delta > 0 else "DEDUCT"
            cursor.execute("""
                INSERT INTO stock_history (component_id, change_type, amount, previous_qty, new_qty, drawer_number, note, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (comp_id, c_type, abs(actual_delta), comp.quantity - actual_delta, comp.quantity, drawer_num, note or f"Quick change on Drawer {drawer_num}", now))

            conn.commit()
            print(f"[INFO] [STOCK] Component ID={comp_id} Drawer {drawer_num} adjusted by {delta:+d}. New Drawer Qty={new_drawer_qty}, Total={comp.quantity}")
            return comp.quantity

    def adjust_drawer_stocks(self, comp_id: int, breakdown: Dict[int, int], is_deduct: bool, note: str = "") -> Optional[int]:
        """Adjusts stock across multiple drawers according to breakdown dict: {drawer_num: amount}"""
        comp = self.get_component(comp_id)
        if not comp:
            return None

        current_stocks = comp.drawer_stocks
        old_total = comp.quantity

        for d_num, amount in breakdown.items():
            if amount <= 0:
                continue
            cur_qty = current_stocks.get(d_num, 0)
            if is_deduct:
                if amount > cur_qty:
                    print(f"[ERROR] [STOCK] Cannot deduct {amount} from Drawer {d_num} (current qty: {cur_qty})")
                    return None
                current_stocks[d_num] = cur_qty - amount
            else:
                current_stocks[d_num] = cur_qty + amount

        comp.drawer_stocks = current_stocks
        new_total = comp.quantity
        total_change = abs(new_total - old_total)

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE components
                SET quantity = ?, drawers = ?, updated_at = ?
                WHERE id = ?
            """, (new_total, comp.drawers, now, comp_id))

            c_type = "DEDUCT" if is_deduct else "ADD"
            cursor.execute("""
                INSERT INTO stock_history (component_id, change_type, amount, previous_qty, new_qty, note, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (comp_id, c_type, total_change, old_total, new_total, note or "Bulk stock adjustment", now))

            conn.commit()
            print(f"[INFO] [STOCK] Bulk adjustment for Component ID={comp_id}: {'-' if is_deduct else '+'}{total_change}. New Total={new_total}")
            return new_total

    def get_stock_history(self, component_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent stock transactions for a specific component or all components."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if component_id is not None:
                cursor.execute("""
                    SELECT * FROM stock_history
                    WHERE component_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (component_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM stock_history
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_statistics(self) -> Dict[str, Any]:
        """Calculates total inventory statistics"""
        comps = self.get_all_components()
        total_types = len(comps)
        total_items = sum(c.quantity for c in comps)
        low_stock_count = sum(1 for c in comps if c.stock_status == "LOW")
        empty_count = sum(1 for c in comps if c.stock_status == "EMPTY")
        in_stock_count = sum(1 for c in comps if c.stock_status == "OK")
        used_drawers = self.get_all_used_drawers()

        return {
            "total_types": total_types,
            "total_items": total_items,
            "in_stock_count": in_stock_count,
            "low_stock_count": low_stock_count,
            "empty_count": empty_count,
            "total_drawers": len(used_drawers),
            "used_drawers": used_drawers
        }

    def _row_to_component(self, row: sqlite3.Row) -> Component:
        return Component(
            id=row['id'],
            name=row['name'],
            value=row['value'],
            package=row['package'] or "",
            category=row['category'] or "Other",
            quantity=row['quantity'] or 0,
            min_alert=row['min_alert'] if row['min_alert'] is not None else 10,
            drawers=row['drawers'] or "",
            description=row['description'] or "",
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )


DatabaseManager = Database
