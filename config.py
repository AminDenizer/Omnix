"""
Omnix Configuration & Application Constants
"""

import sys
import os

# Application Branding & Metadata
APP_NAME = "Omnix"
APP_SUBTITLE = "Electronic Components Database"
APP_VERSION = "1.0.0"
DEVELOPER_NAME = "AminDenizer"
DEVELOPER_ORG = "DOT"
DEVELOPER_CREDIT_HTML = "Developed by <font color='#38bdf8'><b>AminDenizer</b></font> from <font color='#34d399'><b>DOT</b></font>"

# Path Helpers
def get_app_dir() -> str:
    """Return root directory where the application binary (.exe) or main script resides."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir() -> str:
    """Return directory where internal resources are unpacked."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', get_app_dir())
    return os.path.dirname(os.path.abspath(__file__))
