import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

# Add current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import APP_NAME, get_bundle_dir
from ui.main_window import MainWindow
from ui.splash_screen import SplashScreen
from ui.styles import DARK_STYLESHEET


def main():
    # Set Windows Process App User Model ID
    if sys.platform == "win32":
        try:
            import ctypes
            myappid = "dot.omnix.excel.viewer.v1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            pass

    # Enable High-DPI scaling
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} View")
    app.setFont(QFont("Segoe UI", 10))
    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    # Set application icon with multiple resolutions
    app_icon = QIcon()
    icons_dir = os.path.join(get_bundle_dir(), "ui", "icons")
    ico_path = os.path.join(icons_dir, "app_logo.ico")
    if os.path.exists(ico_path):
        app_icon.addFile(ico_path)
    for size_name in ["app_logo.png", "app_logo_256.png", "app_logo_64.png", "app_logo_32.png"]:
        p = os.path.join(icons_dir, size_name)
        if os.path.exists(p):
            app_icon.addFile(p)
    app.setWindowIcon(app_icon)

    # Apply matte dark stylesheet
    app.setStyleSheet(DARK_STYLESHEET)

    # Check CLI arguments for an excel file
    target_excel = None
    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if os.path.exists(candidate) and candidate.lower().endswith(('.xlsx', '.xlsm', '.xltx')):
            target_excel = candidate

    # Initialize Main Window
    window = MainWindow(default_file=target_excel)

    # Startup Splash Screen
    splash = SplashScreen(total_duration_ms=1000)
    splash.finished.connect(window.show)
    splash.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
