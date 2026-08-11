"""
ClipboardGrabberWidget — Non-intrusive floating HUD for quick media downloads.

Monitors the system clipboard for YouTube, SoundCloud, or Bandcamp URLs.
When a recognised URL is copied, a small overlay widget slides in from the
bottom-right corner of the primary screen, offering one-click MP3 or WAV
download without interrupting the user's workflow.
"""

import os
import re
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QApplication, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QPoint
)
from PyQt6.QtGui import QColor
import qtawesome as qta

# Domains that trigger the quick-grab HUD
_SUPPORTED_DOMAINS = ('youtube.com', 'youtu.be', 'soundcloud.com', 'bandcamp.com')

# Regexes for extracting a human-readable slug from known URL shapes
_YT_ID_RE    = re.compile(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})')
_SC_SLUG_RE  = re.compile(r'soundcloud\.com/[^/]+/([^/?]+)')
_BC_SLUG_RE  = re.compile(r'bandcamp\.com/track/([^/?]+)')


def _derive_title_from_url(url: str) -> str:
    """
    Extract a minimal human-readable title from a media URL.

    Falls back to a generic "Quick Capture" string if the URL shape is
    unrecognised.  This avoids storing the literal string "Quick Capture Track"
    in download history for every clipboard capture.
    """
    m = _YT_ID_RE.search(url)
    if m:
        return f"YouTube/{m.group(1)}"
    m = _SC_SLUG_RE.search(url)
    if m:
        slug = m.group(1).replace('-', ' ').title()
        return f"SoundCloud – {slug}"
    m = _BC_SLUG_RE.search(url)
    if m:
        slug = m.group(1).replace('-', ' ').title()
        return f"Bandcamp – {slug}"
    return "Quick Capture"


class ClipboardGrabberWidget(QWidget):
    """
    Floating HUD widget that appears whenever a supported media URL is copied.

    The widget slides into view from below using a 300 ms ease-out animation,
    auto-dismisses after 7 seconds, and allows the user to trigger an MP3 or
    WAV download with a single click.

    Signals
    -------
    download_requested(url: str, fmt: str)
        Emitted when the user clicks a download button.
    """

    download_requested = pyqtSignal(str, str)  # (url, format)

    def __init__(self, accent_color: str = "#FF5500", parent=None):
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
        self.setFixedWidth(370)

        self.setup_ui()

        # Auto-dismiss timer — restarted each time the widget shows
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide_widget)

        # Slide-in animation (moves the widget upward into its final position)
        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(300)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── UI Construction ──────────────────────────────────────────────────────

    def setup_ui(self):
        """Build the HUD card layout inside a translucent container."""
        container = QWidget(self)
        container.setObjectName("hudContainer")
        container.setGeometry(0, 0, self.width(), self.height())
        container.setStyleSheet(f"""
            QWidget#hudContainer {{
                background-color: #181615;
                border: 1px solid #383432;
                border-left: 4px solid {self.accent_color};
                border-radius: 8px;
            }}
            QLabel {{ color: #E8E3DF; font-family: 'Inter', sans-serif; background: transparent; }}
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
                border-color: {self.accent_color};
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

        title_lbl = QLabel("Media Link Detected")
        title_lbl.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF;")
        self.url_lbl = QLabel("")
        self.url_lbl.setStyleSheet("font-size: 10px; color: #A39E9A;")
        self.url_lbl.setFixedHeight(14)

        info_layout.addWidget(title_lbl)
        info_layout.addWidget(self.url_lbl)
        layout.addLayout(info_layout, 1)

        self.btn_mp3 = QPushButton("MP3")
        self.btn_mp3.setToolTip("Quick download as MP3")
        self.btn_mp3.clicked.connect(lambda: self._on_download("mp3"))

        self.btn_wav = QPushButton("WAV")
        self.btn_wav.setToolTip("Quick download as WAV")
        self.btn_wav.clicked.connect(lambda: self._on_download("wav"))

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "background: transparent; border: none; color: #7A7470; font-size: 12px;"
        )
        close_btn.clicked.connect(self.hide_widget)

        layout.addWidget(self.btn_mp3)
        layout.addWidget(self.btn_wav)
        layout.addWidget(close_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

    # ── Public API ───────────────────────────────────────────────────────────

    def check_clipboard(self):
        """
        Poll the clipboard for new supported media URLs.

        Called by the main window's clipboard timer (every 1500 ms).
        Only triggers on URLs that differ from the last detected one.
        """
        text = QApplication.clipboard().text().strip()
        if text and text != self.last_copied:
            if any(domain in text.lower() for domain in _SUPPORTED_DOMAINS):
                self.last_copied = text
                self.show_for_url(text)

    def show_for_url(self, url: str):
        """
        Display the HUD for the given URL with a smooth slide-in animation.

        Parameters
        ----------
        url : str
            The detected media URL to show in the subtitle label.
        """
        self.current_url = url
        short_url = url[:45] + ("…" if len(url) > 45 else "")
        self.url_lbl.setText(short_url)

        # Calculate final resting position (bottom-right of primary screen)
        screen = QApplication.primaryScreen().availableGeometry()
        final_x = screen.width() - self.width() - 20
        final_y = screen.height() - self.height() - 40

        # Start 20 px below so the slide-up is visible
        start_y = final_y + 20

        self.move(final_x, start_y)
        self.show()
        self.raise_()

        # Animate upward to final position
        self._slide_anim.stop()
        self._slide_anim.setStartValue(QPoint(final_x, start_y))
        self._slide_anim.setEndValue(QPoint(final_x, final_y))
        self._slide_anim.start()

        self.dismiss_timer.start(7000)

    # ── Private Helpers ──────────────────────────────────────────────────────

    def _on_download(self, fmt: str):
        """Emit download signal and close the HUD."""
        if self.current_url:
            self.download_requested.emit(self.current_url, fmt)
        self.hide_widget()

    def hide_widget(self):
        """Stop the dismiss timer and hide the HUD."""
        self.dismiss_timer.stop()
        self.hide()
