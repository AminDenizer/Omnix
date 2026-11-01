import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QGraphicsDropShadowEffect, QFrame
)
from PyQt6.QtGui import QPixmap, QColor, QIcon
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from config import APP_NAME, APP_SUBTITLE, DEVELOPER_CREDIT_HTML, get_bundle_dir


class SplashScreen(QWidget):
    """
    Startup splash screen with glowing IC logo, developer credit,
    and smooth animated progress bar.
    """

    finished = pyqtSignal()

    def __init__(self, total_duration_ms: int = 1000):
        super().__init__()
        self.total_duration = total_duration_ms
        self.current_progress = 0
        self.tick_interval = 20  # 20ms update interval for 50fps smooth motion
        self.step_increment = 100.0 / (self.total_duration / self.tick_interval)

        self.setWindowFlags(
            Qt.WindowType.SplashScreen |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.resize(520, 340)
        self._init_ui()
        self._center_on_screen()

        # Set window icon
        icons_dir = os.path.join(get_bundle_dir(), "ui", "icons")
        ico_path = os.path.join(icons_dir, "app_logo.ico")
        png_path = os.path.join(icons_dir, "app_logo.png")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        elif os.path.exists(png_path):
            self.setWindowIcon(QIcon(png_path))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_progress)

    def _center_on_screen(self):
        screen = self.screen()
        if screen:
            screen_geo = screen.geometry()
            x = (screen_geo.width() - self.width()) // 2
            y = (screen_geo.height() - self.height()) // 2
            self.move(x, y)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)

        # Elevated card container with dark navy gradient
        self.card = QFrame()
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet("""
            QFrame#splashCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0f172a, stop:0.55 #080d18, stop:1 #03060d);
                border: 1.5px solid #1e3a5f;
                border-radius: 16px;
            }
        """)

        # Soft floating drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setColor(QColor(0, 0, 0, 210))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 22, 28, 22)
        card_layout.setSpacing(10)

        # 1. Header: Logo, Title and Subtitle
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.setSpacing(4)

        # Glowing IC Microchip Logo
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = os.path.join(get_bundle_dir(), "ui", "icons", "app_logo.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(68, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        header_layout.addWidget(logo_lbl)

        # App Brand Title
        title_lbl = QLabel(APP_NAME)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size: 24px; font-weight: 800; color: #38bdf8; letter-spacing: 0.8px;")
        header_layout.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel(APP_SUBTITLE)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 500;")
        header_layout.addWidget(sub_lbl)

        card_layout.addLayout(header_layout)
        card_layout.addSpacing(4)

        # 2. Developer Credit Box
        dev_badge = QFrame()
        dev_badge.setObjectName("devBadge")
        dev_badge.setStyleSheet("""
            QFrame#devBadge {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px 14px;
            }
        """)
        dev_layout = QVBoxLayout(dev_badge)
        dev_layout.setContentsMargins(10, 6, 10, 6)
        dev_layout.setSpacing(0)

        dev_title = QLabel(DEVELOPER_CREDIT_HTML)
        dev_title.setTextFormat(Qt.TextFormat.RichText)
        dev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_title.setStyleSheet("font-size: 12px; color: #f1f5f9; font-weight: 600;")
        dev_layout.addWidget(dev_title)

        card_layout.addWidget(dev_badge)
        card_layout.addStretch()

        # 3. Dynamic Status Label & Percentage (LTR layout)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(2, 0, 2, 0)
        status_row.setSpacing(8)

        self.status_lbl = QLabel("Initializing application...")
        self.status_lbl.setStyleSheet("font-size: 11.5px; color: #7dd3fc; font-weight: 500;")
        status_row.addWidget(self.status_lbl)

        status_row.addStretch()

        self.percent_lbl = QLabel("0%")
        self.percent_lbl.setStyleSheet("font-size: 11.5px; font-weight: 700; color: #34d399; font-family: Consolas, monospace;")
        status_row.addWidget(self.percent_lbl)

        card_layout.addLayout(status_row)

        # 4. Neon Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0b111e;
                border: 1px solid #1e293b;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284c7, stop:0.6 #38bdf8, stop:1 #34d399);
                border-radius: 2px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        root_layout.addWidget(self.card)

    def start(self):
        """Display the splash screen and start progress animation."""
        self.show()
        self.timer.start(self.tick_interval)

    def _update_progress(self):
        self.current_progress += self.step_increment
        int_val = min(100, int(self.current_progress))
        self.progress_bar.setValue(int_val)
        self.percent_lbl.setText(f"{int_val}%")

        if int_val < 30:
            self.status_lbl.setText("Detecting local Excel database...")
        elif int_val < 65:
            self.status_lbl.setText("Reading table schema & records...")
        elif int_val < 85:
            self.status_lbl.setText("Preparing high-speed search index...")
        else:
            self.status_lbl.setText("Ready.")

        if self.current_progress >= 100:
            self.timer.stop()
            self.close()
            self.finished.emit()
