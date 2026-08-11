from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QIcon, QPixmap
import qtawesome as qta

class MiniPlayerWindow(QWidget):
    """
    Compact floating mini-player (340x90px) designed to stay on top
    while working inside DJ software (Mixxx, Serato, Rekordbox).
    """
    play_pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    expand_clicked = pyqtSignal()

    def __init__(self, main_window, accent_color="#C47D63"):
        super().__init__()
        self.main_window = main_window
        self.accent_color = accent_color
        self.is_moving = False
        self.drag_position = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(340, 90)

        self.setup_ui()

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color
        self.update_style()

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#miniContainer {{
                background-color: #161514;
                border: 2px solid {self.accent_color};
                border-radius: 12px;
            }}
            QLabel#miniTitle {{
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
            }}
            QLabel#miniArtist {{
                color: #A0A0A0;
                font-size: 10px;
            }}
            QPushButton.miniControlBtn {{
                background-color: #262423;
                border: 1px solid #363433;
                border-radius: 18px;
            }}
            QPushButton.miniControlBtn:hover {{
                background-color: {self.accent_color};
                border-color: {self.accent_color};
            }}
        """)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget()
        self.container.setObjectName("miniContainer")
        
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Track Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        self.title_lbl = QLabel("DJ Crate Mini Player")
        self.title_lbl.setObjectName("miniTitle")
        
        self.artist_lbl = QLabel("No track previewing")
        self.artist_lbl.setObjectName("miniArtist")

        info_layout.addWidget(self.title_lbl)
        info_layout.addWidget(self.artist_lbl)
        layout.addLayout(info_layout, 1)

        # Controls
        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setProperty("class", "miniControlBtn")
        self.play_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
        self.play_btn.clicked.connect(self.play_pause_clicked.emit)

        self.stop_btn = QPushButton()
        self.stop_btn.setFixedSize(32, 32)
        self.stop_btn.setProperty("class", "miniControlBtn")
        self.stop_btn.setIcon(qta.icon("fa5s.stop", color="#FFFFFF"))
        self.stop_btn.clicked.connect(self.stop_clicked.emit)

        self.expand_btn = QPushButton()
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setStyleSheet("background: transparent; border: none;")
        self.expand_btn.setIcon(qta.icon("fa5s.expand-alt", color="#A0A0A0"))
        self.expand_btn.setToolTip("Restore Full Window")
        self.expand_btn.clicked.connect(self.expand_clicked.emit)

        layout.addWidget(self.play_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.expand_btn)

        main_layout.addWidget(self.container)
        self.update_style()

    def update_track(self, title: str, artist: str, is_playing: bool):
        self.title_lbl.setText(title or "DJ Crate Mini Player")
        self.artist_lbl.setText(artist or "Preview Mode")
        icon_name = "fa5s.pause" if is_playing else "fa5s.play"
        self.play_btn.setIcon(qta.icon(icon_name, color="#FFFFFF"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_moving = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_moving and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        event.accept()
