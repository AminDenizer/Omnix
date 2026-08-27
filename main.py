import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from PyQt6.QtGui import QFont, QIcon

# Add current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import APP_NAME
from database import Database
from models import Component
from ui.main_window import MainWindow
from ui.splash_screen import SplashScreen
from ui.styles import DARK_STYLESHEET
from ui.generate_icons import generate_arrows


def seed_sample_data(db: Database):
    """Seed initial sample components for testing if database is empty"""
    if len(db.get_all_components()) > 0:
        return

    sample_components = [
        Component(
            name="مقاومت SMD",
            value="10k 1%",
            package="SMD 0805",
            category="Resistor",
            quantity=250,
            min_alert=50,
            drawers="1:100, 2:100, 4:50",
            description="مقاومت پرکاربرد پول‌آپ در مدارات دیجیتال (کشوهای ۱، ۲ و ۴)"
        ),
        Component(
            name="خازن سرامیکی SMD",
            value="100nF (0.1uF) 50V",
            package="SMD 0805",
            category="Capacitor",
            quantity=180,
            min_alert=30,
            drawers="3:180",
            description="خازن دکوپلاژ تغذیه آی‌سی‌ها"
        ),
        Component(
            name="رگولاتور ولتاژ خطی",
            value="AMS1117-3.3",
            package="SOT-223",
            category="IC / Regulator",
            quantity=15,
            min_alert=20,
            drawers="5:15, 8:0",
            description="تبدیل ۵ ولت به ۳.۳ ولت با جریان ۱ آمپر (کشو ۸ ناموجود است)"
        ),
        Component(
            name="ترانزیستور NPN",
            value="BC547",
            package="TO-92",
            category="Transistor / MOSFET",
            quantity=0,
            min_alert=15,
            drawers="7:0",
            description="ترانزیستور سویچینگ و تقویت سیگنال (ناموجود)"
        ),
        Component(
            name="میکروکنترلر",
            value="STM32F103C8T6 (BluePill IC)",
            package="QFP / TQFP",
            category="Microcontroller (MCU)",
            quantity=40,
            min_alert=5,
            drawers="12:40",
            description="میکروکنترلر ۳۲ بیتی ARM Cortex-M3"
        ),
        Component(
            name="ال‌ای‌دی سبز",
            value="LED 3mm Green",
            package="Axial (Through-Hole)",
            category="Diode / LED",
            quantity=120,
            min_alert=20,
            drawers="1:120",
            description="نشانگر وضعیت تغذیه برد"
        )
    ]

    for comp in sample_components:
        db.add_component(comp)
    print(f"[INFO] [INIT] Seeded {len(sample_components)} sample components into database.")


def main():
    print(f"[INFO] Starting {APP_NAME}...")

    # Enable High-DPI scaling
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))

    # Generate vector icons and logos
    try:
        generate_arrows()
    except Exception as e:
        print(f"[WARN] Icon generator notice: {e}")

    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "icons", "app_logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # Apply matte dark stylesheet
    app.setStyleSheet(DARK_STYLESHEET)

    # Initialize Database
    db = Database()
    seed_sample_data(db)

    # Initialize Main Window (prepared in background)
    window = MainWindow(db=db)

    # Launch Startup Splash Screen with fast, smooth loading animation
    splash = SplashScreen(total_duration_ms=1800)
    splash.finished.connect(window.show)
    splash.start()

    print("[INFO] Application startup launched with splash screen.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
