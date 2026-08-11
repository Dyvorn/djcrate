import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor
import qtawesome as qta
from djcrate.utils import CamelotMatcher

class GigMatcherWidget(QWidget):
    """
    Ultra-compact live gig companion widget docked over Serato / Rekordbox.
    Input live playing track's Key & BPM to instantly view compatible tracks.
    """
    track_preview_requested = pyqtSignal(dict)

    CAMELOT_KEYS = [
        "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
        "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
        "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
    ]

    def __init__(self, library_tracks=None, accent_color="#FF5500", parent=None):
        super().__init__(parent)
        self.library_tracks = library_tracks or []
        self.accent_color = accent_color
        self.drag_position = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(290, 420)
        self.setStyleSheet(f"""
            QWidget#gigMatcher {{
                background-color: #141212;
                border: 1px solid #2C2827;
                border-top: 3px solid {self.accent_color};
                border-radius: 8px;
            }}
            QLabel {{ color: #E8E3DF; font-family: 'Inter', sans-serif; }}
            QComboBox, QSpinBox {{
                background-color: #1E1B1A;
                color: #FFFFFF;
                border: 1px solid #383432;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }}
            QListWidget {{
                background-color: #1A1817;
                border: 1px solid #282423;
                border-radius: 6px;
                color: #E8E3DF;
            }}
        """)

        self.setObjectName("gigMatcher")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # Header Title bar (draggable)
        hdr = QHBoxLayout()
        hdr_icon = QLabel()
        hdr_icon.setPixmap(qta.icon("fa5s.bolt", color="#00E676").pixmap(16, 16))
        
        hdr_title = QLabel("LIVE GIG MATCH ASSISTANT")
        hdr_title.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("background: transparent; border: none; color: #7A7470;")
        close_btn.clicked.connect(self.hide)

        hdr.addWidget(hdr_icon)
        hdr.addWidget(hdr_title, 1)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Inputs: Playing Key & BPM
        inputs_box = QHBoxLayout()
        inputs_box.setSpacing(8)

        inputs_box.addWidget(QLabel("Key:"))
        self.key_combo = QComboBox()
        self.key_combo.addItems(self.CAMELOT_KEYS)
        self.key_combo.setCurrentText("8A")
        self.key_combo.currentTextChanged.connect(self.update_matches)
        inputs_box.addWidget(self.key_combo)

        inputs_box.addWidget(QLabel("BPM:"))
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(40, 220)
        self.bpm_spin.setValue(128)
        self.bpm_spin.valueChanged.connect(self.update_matches)
        inputs_box.addWidget(self.bpm_spin)

        layout.addLayout(inputs_box)

        # Match List
        self.match_list = QListWidget()
        self.match_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.match_list, 1)

        self.status_lbl = QLabel("Double-click track to copy file path")
        self.status_lbl.setStyleSheet("color: #7A7470; font-size: 10px; font-weight: 600;")
        layout.addWidget(self.status_lbl)

    def set_library_tracks(self, tracks: list):
        self.library_tracks = tracks
        self.update_matches()

    def update_matches(self):
        self.match_list.clear()
        playing_key = self.key_combo.currentText()
        playing_bpm = self.bpm_spin.value()

        matches = []
        for t in self.library_tracks:
            t_key = t.get('key', '')
            t_bpm = t.get('bpm', '')
            if not t_key:
                continue

            score, key_qual, bpm_qual = CamelotMatcher.calculate_match_score(
                playing_key, str(playing_bpm), t_key, str(t_bpm)
            )
            if score > 50:
                matches.append((score, t, key_qual, bpm_qual))

        matches.sort(key=lambda x: x[0], reverse=True)

        for score, t, key_qual, bpm_qual in matches[:30]:
            item = QListWidgetItem()
            title = t.get('title', 'Unknown')
            artist = t.get('artist', 'Unknown')
            bpm_str = t.get('bpm', '')
            key_str = t.get('key', '')

            item_text = f"Match: {score}%  ·  {artist} - {title}\n    Key: {key_str} ({key_qual})  ·  BPM: {bpm_str}"
            item.setText(item_text)
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.match_list.addItem(item)

    def _on_item_double_clicked(self, item):
        track = item.data(Qt.ItemDataRole.UserRole)
        if track and track.get('path'):
            QApplication.clipboard().setText(track['path'])
            self.status_lbl.setText(f"Copied: {os.path.basename(track['path'])}")
            self.track_preview_requested.emit(track)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
