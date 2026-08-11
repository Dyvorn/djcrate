import os
import re
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QApplication, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor
import qtawesome as qta

class ClipboardGrabberWidget(QWidget):
    """
    Non-intrusive floating HUD widget that appears in screen corner
    whenever a YouTube / SoundCloud / Bandcamp URL is copied to the clipboard.
    """
    download_requested = pyqtSignal(str, str) # url, format

    def __init__(self, accent_color="#FF5500", parent=None):
        super().__init__(parent)
        self.accent_color = accent_color
        self.current_url = ""
        self.last_copied = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(64)
        self.setFixedWidth(360)

        self.setup_ui()

        # Dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide_widget)

    def setup_ui(self):
        container = QWidget(self)
        container.setObjectName("hudContainer")
        container.setStyleSheet(f"""
            QWidget#hudContainer {{
                background-color: #181615;
                border: 1px solid #383432;
                border-left: 4px solid {self.accent_color};
                border-radius: 8px;
            }}
            QLabel {{ color: #E8E3DF; font-family: 'Inter', sans-serif; }}
            QPushButton {{
                background-color: #2F2B2A;
                color: #E8E3DF;
                border: 1px solid #3F3B3A;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.accent_color};
                color: #FFFFFF;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.link", color=self.accent_color).pixmap(18, 18))
        layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title = QLabel("Media Link Detected")
        title.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF;")
        self.url_lbl = QLabel("Copy URL detected")
        self.url_lbl.setStyleSheet("font-size: 10px; color: #A39E9A;")
        self.url_lbl.setFixedHeight(14)

        info_layout.addWidget(title)
        info_layout.addWidget(self.url_lbl)
        layout.addLayout(info_layout, 1)

        # Action Buttons
        self.btn_mp3 = QPushButton("MP3")
        self.btn_mp3.setToolTip("Quick download as MP3")
        self.btn_mp3.clicked.connect(lambda: self._on_download("mp3"))

        self.btn_wav = QPushButton("WAV")
        self.btn_wav.setToolTip("Quick download as WAV")
        self.btn_wav.clicked.connect(lambda: self._on_download("wav"))

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("background: transparent; border: none; color: #7A7470; font-size: 12px;")
        close_btn.clicked.connect(self.hide_widget)

        layout.addWidget(self.btn_mp3)
        layout.addWidget(self.btn_wav)
        layout.addWidget(close_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

    def check_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if text and text != self.last_copied:
            if any(domain in text.lower() for domain in ['youtube.com', 'youtu.be', 'soundcloud.com', 'bandcamp.com']):
                self.last_copied = text
                self.show_for_url(text)

    def show_for_url(self, url: str):
        self.current_url = url
        short_url = url[:40] + ("..." if len(url) > 40 else "")
        self.url_lbl.setText(short_url)

        # Position near bottom-right corner of primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width() - 20
        y = screen.height() - self.height() - 40
        self.move(x, y)

        self.show()
        self.raise_()
        self.dismiss_timer.start(7000)

    def _on_download(self, fmt: str):
        if self.current_url:
            self.download_requested.emit(self.current_url, fmt)
        self.hide_widget()

    def hide_widget(self):
        self.dismiss_timer.stop()
        self.hide()
