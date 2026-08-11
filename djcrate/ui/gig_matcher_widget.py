"""
GigMatcherWidget — Ultra-compact live gig companion overlay for Serato / Rekordbox.

Input the currently-playing track's Key and BPM to instantly surface the best
harmonically compatible tracks from your downloaded library, ranked by match score.
Sits always-on-top, frameless, and draggable so it can be pinned over your DJ software.
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QFont
import qtawesome as qta
from djcrate.utils import CamelotMatcher


class GigMatcherWidget(QWidget):
    """
    Ultra-compact live gig companion widget docked over Serato / Rekordbox.

    Input the live-playing track's Camelot Key & BPM to instantly view compatible
    tracks from the library, ranked by harmonic + tempo match score.

    Signals
    -------
    track_preview_requested(dict)
        Emitted when the user double-clicks a result row; passes the track dict.
    """

    track_preview_requested = pyqtSignal(dict)

    CAMELOT_KEYS = [
        "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
        "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
        "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
    ]

    # Score thresholds for colour bands
    _EXCELLENT = 85
    _GOOD = 60

    # Colour palette per band
    _COLOURS = {
        'excellent': ('#00E676', 'rgba(0, 230, 118, 0.12)'),
        'good':      ('#FFD600', 'rgba(255, 214, 0, 0.10)'),
        'weak':      ('#FF5252', 'rgba(255, 82, 82, 0.08)'),
    }

    def __init__(self, library_tracks=None, accent_color="#FF5500", parent=None):
        super().__init__(parent)
        self.library_tracks = library_tracks or []
        self.accent_color = accent_color
        self.drag_position = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(300, 440)
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
            QListWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid #1E1B1A;
            }}
            QListWidget::item:selected {{
                background-color: #2C2A29;
            }}
        """)

        self.setObjectName("gigMatcher")
        self.setup_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def setup_ui(self):
        """Build the static widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # Draggable header
        hdr = QHBoxLayout()
        hdr_icon = QLabel()
        hdr_icon.setPixmap(qta.icon("fa5s.bolt", color="#00E676").pixmap(16, 16))

        hdr_title = QLabel("LIVE GIG MATCH ASSISTANT")
        hdr_title.setStyleSheet(
            "font-size: 11px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;"
        )

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("background: transparent; border: none; color: #7A7470;")
        close_btn.clicked.connect(self.hide)

        hdr.addWidget(hdr_icon)
        hdr.addWidget(hdr_title, 1)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Key + BPM inputs
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

        # Match results list
        self.match_list = QListWidget()
        self.match_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.match_list, 1)

        self.status_lbl = QLabel("Double-click track to preview & copy path")
        self.status_lbl.setStyleSheet("color: #7A7470; font-size: 10px; font-weight: 600;")
        layout.addWidget(self.status_lbl)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_library_tracks(self, tracks: list):
        """Refresh the track list and immediately re-run the current match query."""
        self.library_tracks = tracks
        self.update_matches()

    def update_matches(self):
        """
        Re-score the entire library against the current Key & BPM inputs and
        repopulate the list with colour-coded result rows (top 30 results).
        """
        self.match_list.clear()
        playing_key = self.key_combo.currentText()
        playing_bpm = str(self.bpm_spin.value())

        matches = []
        for t in self.library_tracks:
            t_key = t.get('key', '')
            t_bpm = t.get('bpm', '')
            if not t_key:
                continue

            score, key_qual, bpm_qual = CamelotMatcher.calculate_match_score(
                playing_key, playing_bpm, t_key, str(t_bpm)
            )
            if score > 50:
                matches.append((score, t, key_qual, bpm_qual))

        matches.sort(key=lambda x: x[0], reverse=True)

        for score, track, key_qual, bpm_qual in matches[:30]:
            item = self._build_list_item(score, track, key_qual, bpm_qual)
            self.match_list.addItem(item)

    # ── Private Helpers ──────────────────────────────────────────────────────

    def _band_for_score(self, score: int) -> str:
        """Return the colour-band key ('excellent', 'good', 'weak') for a score."""
        if score >= self._EXCELLENT:
            return 'excellent'
        elif score >= self._GOOD:
            return 'good'
        return 'weak'

    def _build_list_item(self, score: int, track: dict, key_qual: str, bpm_qual: str) -> QListWidgetItem:
        """
        Construct a colour-coded ``QListWidgetItem`` for one match result.

        Each item stores the full track dict in ``UserRole`` for double-click retrieval.
        """
        band = self._band_for_score(score)
        fg_color, bg_color = self._COLOURS[band]

        title = track.get('title', 'Unknown')
        artist = track.get('artist', 'Unknown')
        key_str = track.get('key', '—')
        bpm_str = track.get('bpm', '—')

        # Two-line format: score badge + artist/title, then key/bpm metadata
        line1 = f"  {score}%  {artist} – {title}"
        line2 = f"     Key: {key_str} ({key_qual})  ·  BPM: {bpm_str}"

        item = QListWidgetItem(f"{line1}\n{line2}")
        item.setData(Qt.ItemDataRole.UserRole, track)
        item.setForeground(QColor(fg_color))
        item.setBackground(QColor(bg_color))

        font = QFont("Inter", 10)
        item.setFont(font)

        return item

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Copy the track file path to clipboard and emit preview signal."""
        track = item.data(Qt.ItemDataRole.UserRole)
        if track and track.get('path'):
            QApplication.clipboard().setText(track['path'])
            self.status_lbl.setText(f"Copied: {os.path.basename(track['path'])}")
            self.track_preview_requested.emit(track)

    # ── Drag Support ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
