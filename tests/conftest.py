import os
import sys
import tempfile
import pytest
from PyQt6.QtWidgets import QApplication

# Ensure root directory is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import Database
from models import Component


@pytest.fixture(scope="session")
def qapp():
    """Session-level QApplication instance for UI tests."""
    app = QApplication.instance()
    if app is None:
        # Offscreen platform for headless and automated execution
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    """Creates an isolated temporary SQLite database for a single test."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_inventory.db")
    db = Database(db_path)
    yield db
    # Cleanup database file after test
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.fixture
def sample_component():
    """Returns a realistic sample Component model instance."""
    return Component(
        name="مقاومت SMD",
        value="10k 1%",
        package="SMD 0805",
        category="Resistor",
        quantity=50,
        min_alert=10,
        drawers="1:25, 4:25",
        description="مقاومت اس ام دی دقیق"
    )


@pytest.fixture
def sample_db_with_data(temp_db, sample_component):
    """Returns a temporary database pre-populated with standard testing data."""
    temp_db.add_component(sample_component)
    
    comp2 = Component(
        name="میکروکنترلر",
        value="STM32F103C8T6",
        package="QFP / TQFP",
        category="Microcontroller (MCU)",
        quantity=40,
        min_alert=5,
        drawers="12:40",
        description="برد بلوپیل"
    )
    temp_db.add_component(comp2)

    comp3 = Component(
        name="خازن سرامیکی",
        value="100nF",
        package="SMD 0805",
        category="Capacitor",
        quantity=0,
        min_alert=20,
        drawers="7:0",
        description="خازن دکوپلاژ"
    )
    temp_db.add_component(comp3)

    return temp_db
