"""
Omnix Core - Inventory Database Connection & Lifecycle Manager
Governing Document: Phase 1 Master Architecture Specification
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

from config import get_app_dir
from core.inventory.models import InventoryDatabaseError, normalize_identity_part

CURRENT_SCHEMA_VERSION = 2

V1_SCHEMA_DDL = """
-- Schema migration metadata
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL
);

-- Canonical Reference Data: Manufacturers / Brands
CREATE TABLE IF NOT EXISTS ref_manufacturers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ref_mfr_norm ON ref_manufacturers (norm_name);

-- Canonical Reference Data: Categories
CREATE TABLE IF NOT EXISTS ref_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ref_cat_norm ON ref_categories (norm_name);

-- Canonical Reference Data: Types / Technologies (associated with Category)
CREATE TABLE IF NOT EXISTS ref_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES ref_categories(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category_id, norm_name)
);
CREATE INDEX IF NOT EXISTS idx_ref_types_cat_norm ON ref_types (category_id, norm_name);

-- Canonical Reference Data: Link and Vendor Providers
CREATE TABLE IF NOT EXISTS ref_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    base_url TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ref_providers_id ON ref_providers (provider_id);

-- Physical Components
CREATE TABLE IF NOT EXISTS components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manufacturer TEXT NOT NULL,
    mpn TEXT NOT NULL,
    norm_manufacturer TEXT NOT NULL,
    norm_mpn TEXT NOT NULL,
    category TEXT NOT NULL,
    type_technology TEXT NOT NULL,
    package TEXT NOT NULL,
    raw_package TEXT DEFAULT '',
    footprint TEXT NOT NULL,
    value TEXT NOT NULL,
    description TEXT DEFAULT '',
    quantity_in_stock INTEGER NOT NULL DEFAULT 0 CHECK (quantity_in_stock >= 0),
    group_key TEXT NOT NULL,
    min_stock INTEGER NOT NULL DEFAULT 0 CHECK (min_stock >= 0),
    target_stock INTEGER NOT NULL DEFAULT 0 CHECK (target_stock >= min_stock),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_component_identity UNIQUE (norm_manufacturer, norm_mpn)
);
CREATE INDEX IF NOT EXISTS idx_components_identity ON components (norm_manufacturer, norm_mpn);
CREATE INDEX IF NOT EXISTS idx_components_group_key ON components (group_key);
CREATE INDEX IF NOT EXISTS idx_components_category ON components (category);

-- Supplier Purchase Links (Normalized One-to-Many)
CREATE TABLE IF NOT EXISTS supplier_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    vendor_id TEXT NOT NULL,
    vendor_label TEXT NOT NULL,
    url TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (component_id, vendor_id, url)
);
CREATE INDEX IF NOT EXISTS idx_supplier_links_comp ON supplier_links (component_id);

-- Stock Policies (Per 5-dimension group key)
CREATE TABLE IF NOT EXISTS stock_policies (
    group_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    type_technology TEXT NOT NULL,
    value TEXT NOT NULL,
    package TEXT NOT NULL,
    footprint TEXT NOT NULL,
    min_stock INTEGER DEFAULT NULL CHECK (min_stock IS NULL OR min_stock >= 0),
    target_stock INTEGER DEFAULT NULL CHECK (target_stock IS NULL OR (min_stock IS NULL AND target_stock >= 0) OR target_stock >= min_stock),
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_policies_group ON stock_policies (group_key);
"""


def resolve_database_path(configured_path: Optional[str] = None) -> str:
    """
    Deterministically resolves the SQLite database path.

    Resolution Priority:
    1. Explicit `configured_path` parameter (e.g. ':memory:' or specific test file).
    2. Environment variable `OMNIX_DATABASE_PATH`.
    3. Production default: '<app_dir>/data/omnix_inventory.db'.

    When returning a file path on disk, automatically ensures the parent directory exists.
    """
    if configured_path is not None and str(configured_path).strip():
        p_str = str(configured_path).strip()
        if p_str == ":memory:":
            return ":memory:"
        abs_p = os.path.abspath(p_str)
        os.makedirs(os.path.dirname(abs_p), exist_ok=True)
        return abs_p

    env_p = os.environ.get("OMNIX_DATABASE_PATH")
    if env_p and str(env_p).strip():
        p_str = str(env_p).strip()
        if p_str == ":memory:":
            return ":memory:"
        abs_p = os.path.abspath(p_str)
        os.makedirs(os.path.dirname(abs_p), exist_ok=True)
        return abs_p

    default_path = os.path.join(get_app_dir(), "data", "omnix_inventory.db")
    abs_default = os.path.abspath(default_path)
    os.makedirs(os.path.dirname(abs_default), exist_ok=True)
    return abs_default


class DatabaseManager:
    """
    Manages SQLite database connection lifecycle, WAL configuration,
    foreign key enforcement, and schema versioning.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = resolve_database_path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    @property
    def db_path(self) -> str:
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """
        Returns an open SQLite connection configured with Row factory,
        foreign keys enabled, and WAL journal mode (for file-based databases).
        """
        if self._connection is None:
            conn = sqlite3.connect(
                self._db_path,
                timeout=10.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enforce foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")

            # Configure WAL mode for concurrent file reads
            if self._db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")

            self._connection = conn

        return self._connection

    @contextmanager
    def transaction(self):
        """
        Context manager executing a block within a database transaction.
        Automatically commits on successful block exit, or rolls back on exception.
        """
        conn = self.get_connection()
        if conn.in_transaction:
            yield conn
        else:
            with conn:
                yield conn

    def get_schema_version(self) -> int:
        """Returns the current schema version from PRAGMA user_version."""
        conn = self.get_connection()
        cursor = conn.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        return row[0] if row else 0

    def initialize_schema(self) -> int:
        """
        Initializes or migrates the database schema up to CURRENT_SCHEMA_VERSION.
        Safe against repeated calls on existing databases.
        """
        current_version = self.get_schema_version()
        if current_version > CURRENT_SCHEMA_VERSION:
            raise InventoryDatabaseError(
                f"Database schema version ({current_version}) is newer than "
                f"supported by this application ({CURRENT_SCHEMA_VERSION})."
            )

        conn = self.get_connection()
        with self.transaction():
            if current_version == 0:
                conn.executescript(V1_SCHEMA_DDL)
                conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?);",
                    (CURRENT_SCHEMA_VERSION, "Initial schema with components (including min/target thresholds), supplier links, stock policies, and reference data"),
                )
                current_version = CURRENT_SCHEMA_VERSION

            elif current_version == 1:
                # Version 1 -> Version 2: Migrate min_stock and target_stock thresholds to components table
                conn.execute("ALTER TABLE components ADD COLUMN min_stock INTEGER NOT NULL DEFAULT 0 CHECK (min_stock >= 0);")
                conn.execute("ALTER TABLE components ADD COLUMN target_stock INTEGER NOT NULL DEFAULT 0 CHECK (target_stock >= min_stock);")

                conn.execute("""
                    UPDATE components SET
                        min_stock = COALESCE((
                            SELECT CASE WHEN sp.min_stock IS NOT NULL AND sp.min_stock >= 0 THEN sp.min_stock ELSE 0 END
                            FROM stock_policies sp WHERE sp.group_key = components.group_key
                        ), 0),
                        target_stock = COALESCE((
                            SELECT CASE
                                WHEN sp.target_stock IS NOT NULL AND sp.target_stock >= COALESCE(sp.min_stock, 0) THEN sp.target_stock
                                WHEN sp.min_stock IS NOT NULL AND sp.min_stock >= 0 THEN sp.min_stock
                                ELSE 0
                            END
                            FROM stock_policies sp WHERE sp.group_key = components.group_key
                        ), 0);
                """)
                conn.execute("PRAGMA user_version = 2;")
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?);",
                    (2, "Migrate min_stock and target_stock thresholds to individual components"),
                )
                current_version = 2

            # Ensure ref_providers table and indexes exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ref_providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    norm_name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    base_url TEXT DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_providers_id ON ref_providers (provider_id);")

            # Seed default providers if table is empty
            count = conn.execute("SELECT COUNT(*) FROM ref_providers;").fetchone()[0]
            if count == 0:
                raw_providers = [
                    ("vendor_lion", "Lion Electronic (LION)", "LION", "https://lionelectronic.ir", 1),
                    ("vendor_javan", "Javan Electronic (JAVAN)", "JAVAN", "https://javanelec.com", 1),
                    ("generic", "Other / Generic", "OTHER", "", 1),
                ]
                default_providers = [
                    (pid, name, normalize_identity_part(name), label, url, active)
                    for pid, name, label, url, active in raw_providers
                ]
                conn.executemany(
                    "INSERT OR IGNORE INTO ref_providers (provider_id, name, norm_name, label, base_url, is_active) VALUES (?, ?, ?, ?, ?, ?);",
                    default_providers,
                )

        return current_version

    def backup(self, target_path: str) -> bool:
        """
        Performs an atomic hot backup of the SQLite database to target_path.
        """
        abs_target = os.path.abspath(target_path)
        os.makedirs(os.path.dirname(abs_target), exist_ok=True)
        source_conn = self.get_connection()
        target_conn = sqlite3.connect(abs_target)
        try:
            with target_conn:
                source_conn.backup(target_conn)
            return True
        finally:
            target_conn.close()

    def close(self):
        """Closes the active database connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            finally:
                self._connection = None
