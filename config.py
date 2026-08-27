"""
Omnix Configuration & Application Constants
Centralized configuration parameters, default taxonomies, metadata, and security constants.
"""

import sys
import os

# Application Branding & Metadata
APP_NAME = "Omnix"
APP_SUBTITLE = "مدیریت قطعات الکترونیک"
APP_VERSION = "1.0.0"
DEVELOPER_NAME = "AminDenizer"
DEVELOPER_ORG = "DOT"
DEVELOPER_CREDIT_HTML = "Developed by <font color='#38bdf8'><b>AminDenizer</b></font> from <font color='#34d399'><b>DOT</b></font>"

# Path Helpers for Portable Executable (.exe) & Source Execution
def get_app_dir() -> str:
    """Return root directory where the application binary (.exe) or main script resides."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir() -> str:
    """Return directory where internal resources are unpacked (PyInstaller _MEIPASS or source)."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', get_app_dir())
    return os.path.dirname(os.path.abspath(__file__))

# Database Configuration
DEFAULT_DB_FILENAME = "inventory.db"

def get_default_db_path() -> str:
    """Return absolute path to inventory.db located next to the executable."""
    return os.path.join(get_app_dir(), DEFAULT_DB_FILENAME)

# Default Component Categories
DEFAULT_CATEGORIES = [
    "—",
    "Resistor",
    "Capacitor",
    "Inductor",
    "Diode / LED",
    "Transistor / MOSFET",
    "IC / Regulator",
    "Microcontroller (MCU)",
    "Connector / Terminal",
    "Switch / Relay",
    "Sensor / Module",
    "Crystal / Oscillator",
    "Protection / Fuse",
    "Other"
]

# Default Component Packages / Footprints
DEFAULT_PACKAGES = [
    "—",
    "SMD 0402",
    "SMD 0603",
    "SMD 0805",
    "SMD 1206",
    "DIP-8",
    "DIP-14",
    "DIP-16",
    "DIP-28",
    "DIP-40",
    "SOIC-8",
    "SOIC-16",
    "SOT-23",
    "SOT-223",
    "TO-92",
    "TO-220",
    "QFP / TQFP",
    "QFN",
    "Radial (Electrolytic)",
    "Axial (Through-Hole)",
    "Other"
]

# Default Application Settings Key-Value Pairs
DEFAULT_APP_SETTINGS = {
    "category_mode": "DEFAULT",
    "package_mode": "DEFAULT",
    "app_theme": "DARK_MATTE",
    "low_stock_default_threshold": "10",
    "auto_backup_enabled": "0"
}

# Backup & Cryptographic Signing Constants
BACKUP_MAGIC_HEADER = "OMNIX_SECURE_BACKUP"
LEGACY_MAGIC_HEADER = "ELECSTORE_SECURE_BACKUP"
BACKUP_VERSION = "1.0"
BACKUP_SECRET_SALT = "OMNIX_SECURE_HMAC_SALT_2026_@AGY_BASE_EDITION"
LEGACY_BACKUP_SECRET_SALT = "ELECSTORE_SECURE_HMAC_SALT_2026_@AGY_BASE_EDITION"
