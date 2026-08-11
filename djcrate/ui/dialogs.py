from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QDialogButtonBox, QTextEdit, QWidget, QFrame,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QCheckBox
)
from PyQt6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QColor
from djcrate.logger import logger

import os
class SmartCrateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Smart Crate")
        self.setFixedSize(350, 160)
        self.setStyleSheet("""
            QDialog { background-color: #1E1B1A; }
            QLineEdit, QComboBox { 
                background-color: #141212; 
                color: #E8E3DF; 
                border: 1px solid #2A2725; 
                border-radius: 4px; 
                padding: 4px;
            }
            QPushButton {
                background-color: #2A2725;
                color: #E8E3DF;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #3B3633; }
        """)
        
        layout = QVBoxLayout(self)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Smart Crate Name")
        layout.addWidget(self.name_input)
        
        rule_layout = QHBoxLayout()
        self.field_combo = QComboBox()
        self.field_combo.addItems(["Title", "Artist", "Genre", "BPM"])
        
        self.op_combo = QComboBox()
        self.op_combo.addItems(["contains", "=", ">=", "<="])
        
        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("Value")
        
        rule_layout.addWidget(self.field_combo)
        rule_layout.addWidget(self.op_combo)
        rule_layout.addWidget(self.val_input)
        
        layout.addLayout(rule_layout)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_data(self):
        return {
            'name': self.name_input.text().strip(),
            'field': self.field_combo.currentText(),
            'operator': self.op_combo.currentText(),
            'value': self.val_input.text().strip()
        }


class LogDialog(QDialog):
    def __init__(self, title, log_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Log: {title}")
        self.setMinimumSize(600, 400)
        self.setStyleSheet("""
            QDialog { background-color: #1E1B1A; color: #E8E3DF; }
            QTextEdit { background-color: #141212; color: #D8D3CF; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #3F3B3A; }
        """)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(log_content)
        layout.addWidget(self.text_edit)


class MetadataEditorDialog(QDialog):
    """Dialog to edit ID3/metadata tags of a track file."""
    def __init__(self, track_path: str, parent=None):
        super().__init__(parent)
        self.track_path = track_path
        self.setWindowTitle("Edit Track Metadata")
        self.setFixedSize(400, 260)
        self.setStyleSheet("""
            QDialog { background-color: #1E1B1A; color: #E8E3DF; }
            QLabel { font-weight: bold; color: #A39E9A; }
            QLineEdit { background-color: #141212; color: #E8E3DF; border: 1px solid #3F3B3A; border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #2F2B2A; color: #E8E3DF; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { background-color: #3F3B3A; }
        """)

        layout = QVBoxLayout(self)
        
        file_lbl = QLabel(f"File: {os.path.basename(track_path)}")
        file_lbl.setStyleSheet("color: #C47D63; font-size: 11px;")
        layout.addWidget(file_lbl)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Track Title")
        layout.addWidget(QLabel("Title:"))
        layout.addWidget(self.title_input)

        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist")
        layout.addWidget(QLabel("Artist:"))
        layout.addWidget(self.artist_input)

        self.album_input = QLineEdit()
        self.album_input.setPlaceholderText("Album")
        layout.addWidget(QLabel("Album:"))
        layout.addWidget(self.album_input)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_metadata)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.load_current_metadata()

    def load_current_metadata(self):
        """Pre-populate fields from embedded audio tags; fall back to filename parsing."""
        # Attempt to read existing embedded tags via mutagen
        try:
            import mutagen
            audio = mutagen.File(self.track_path)
            if audio and audio.tags:
                tags = audio.tags
                # Covers ID3 (MP3/WAV), Vorbis (FLAC/OGG), and MP4 comment frames
                def _first(tag_obj):
                    """Return the first string value from a tag frame or list."""
                    if tag_obj is None:
                        return ""
                    if hasattr(tag_obj, 'text'):
                        return str(tag_obj.text[0]).strip()
                    if isinstance(tag_obj, list):
                        return str(tag_obj[0]).strip()
                    return str(tag_obj).strip()

                title = (
                    _first(tags.get('TIT2')) or _first(tags.get('title')) or
                    _first(tags.get('\xa9nam'))  # MP4
                )
                artist = (
                    _first(tags.get('TPE1')) or _first(tags.get('artist')) or
                    _first(tags.get('\xa9ART'))  # MP4
                )
                album = (
                    _first(tags.get('TALB')) or _first(tags.get('album')) or
                    _first(tags.get('\xa9alb'))  # MP4
                )
                if title:
                    self.title_input.setText(title)
                if artist:
                    self.artist_input.setText(artist)
                if album:
                    self.album_input.setText(album)
                if title or artist:
                    return  # Tags found — no need for filename fallback
        except Exception:
            pass  # mutagen not available or corrupt file — fall through

        # Filename fallback: "Artist - Title" convention
        filename = os.path.basename(self.track_path).rsplit('.', 1)[0]
        if ' - ' in filename:
            art, tit = filename.split(' - ', 1)
            self.artist_input.setText(art.strip())
            self.title_input.setText(tit.strip())
        else:
            self.title_input.setText(filename)


    def save_metadata(self):
        try:
            import mutagen
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, ID3NoHeaderError
            ext = self.track_path.lower().split('.')[-1]
            if ext == 'mp3':
                try:
                    tags = ID3(self.track_path)
                except ID3NoHeaderError:
                    tags = ID3()
                if self.title_input.text(): tags.add(TIT2(encoding=3, text=self.title_input.text()))
                if self.artist_input.text(): tags.add(TPE1(encoding=3, text=self.artist_input.text()))
                if self.album_input.text(): tags.add(TALB(encoding=3, text=self.album_input.text()))
                tags.save(self.track_path)
        except Exception as e:
            logger.error(f"Error writing metadata tags: {e}")
        self.accept()


class BulkMetadataEditorDialog(QDialog):
    """Dialog to edit metadata for multiple selected tracks at once."""
    def __init__(self, track_paths: list, parent=None):
        super().__init__(parent)
        self.track_paths = track_paths
        self.setWindowTitle(f"Bulk Edit Metadata ({len(track_paths)} Tracks)")
        self.setFixedSize(420, 320)
        self.setStyleSheet("""
            QDialog { background-color: #1E1B1A; color: #E8E3DF; }
            QLabel { font-weight: bold; color: #A39E9A; }
            QLineEdit { background-color: #141212; color: #E8E3DF; border: 1px solid #3F3B3A; border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #2F2B2A; color: #E8E3DF; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { background-color: #3F3B3A; }
            QCheckBox { color: #E8E3DF; font-size: 11px; }
        """)

        layout = QVBoxLayout(self)

        hdr = QLabel(f"Modifying {len(track_paths)} selected tracks. Check fields to apply.")
        hdr.setStyleSheet("color: #FF5500; font-size: 11px;")
        layout.addWidget(hdr)

        # Artist
        self.artist_cb = QCheckBox("Apply Artist:")
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist Name")
        artist_box = QHBoxLayout()
        artist_box.addWidget(self.artist_cb)
        artist_box.addWidget(self.artist_input, 1)
        layout.addLayout(artist_box)

        # Album
        self.album_cb = QCheckBox("Apply Album:")
        self.album_input = QLineEdit()
        self.album_input.setPlaceholderText("Album Title")
        album_box = QHBoxLayout()
        album_box.addWidget(self.album_cb)
        album_box.addWidget(self.album_input, 1)
        layout.addLayout(album_box)

        # Genre
        self.genre_cb = QCheckBox("Apply Genre:")
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("Genre (e.g. Techno, House)")
        genre_box = QHBoxLayout()
        genre_box.addWidget(self.genre_cb)
        genre_box.addWidget(self.genre_input, 1)
        layout.addLayout(genre_box)

        # Year
        self.year_cb = QCheckBox("Apply Year:")
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("Release Year (e.g. 2026)")
        year_box = QHBoxLayout()
        year_box.addWidget(self.year_cb)
        year_box.addWidget(self.year_input, 1)
        layout.addLayout(year_box)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.save_bulk)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def save_bulk(self):
        artist = self.artist_input.text().strip() if self.artist_cb.isChecked() else None
        album = self.album_input.text().strip() if self.album_cb.isChecked() else None
        genre = self.genre_input.text().strip() if self.genre_cb.isChecked() else None
        year = self.year_input.text().strip() if self.year_cb.isChecked() else None

        if not any([artist, album, genre, year]):
            self.reject()
            return

        try:
            import mutagen
            from mutagen.id3 import ID3, TPE1, TALB, TCON, TDRC, ID3NoHeaderError
            from mutagen.flac import FLAC
            from mutagen.wave import WAVE
            from mutagen.mp4 import MP4

            for path in self.track_paths:
                if not os.path.exists(path):
                    continue
                ext = path.lower().rsplit('.', 1)[-1]
                if ext == 'mp3':
                    try:
                        audio = ID3(path)
                    except ID3NoHeaderError:
                        audio = ID3()
                    if artist is not None: audio.add(TPE1(encoding=3, text=artist))
                    if album is not None: audio.add(TALB(encoding=3, text=album))
                    if genre is not None: audio.add(TCON(encoding=3, text=genre))
                    if year is not None: audio.add(TDRC(encoding=3, text=year))
                    audio.save(path)
                elif ext == 'flac':
                    audio = FLAC(path)
                    if artist is not None: audio['artist'] = artist
                    if album is not None: audio['album'] = album
                    if genre is not None: audio['genre'] = genre
                    if year is not None: audio['date'] = year
                    audio.save()
                elif ext in ('m4a', 'mp4'):
                    audio = MP4(path)
                    if artist is not None: audio.tags['\xa9ART'] = [artist]
                    if album is not None: audio.tags['\xa9alb'] = [album]
                    if genre is not None: audio.tags['\xa9gen'] = [genre]
                    if year is not None: audio.tags['\xa9day'] = [year]
                    audio.save()
        except Exception as e:
            logger.error(f"Bulk metadata write error: {e}")

        self.accept()


class MixSplitterDialog(QDialog):
    """Dialog to parse tracklist timestamps and split long audio files."""
    def __init__(self, parent=None, default_file=""):
        super().__init__(parent)
        self.setWindowTitle("Mix Splitter (Timestamp Parser)")
        self.setMinimumSize(560, 440)
        self.setStyleSheet("""
            QDialog { background-color: #1E1B1A; color: #E8E3DF; }
            QLabel { font-weight: bold; color: #A39E9A; }
            QLineEdit, QTextEdit { background-color: #141212; color: #E8E3DF; border: 1px solid #3F3B3A; border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #2F2B2A; color: #E8E3DF; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { background-color: #3F3B3A; }
        """)

        layout = QVBoxLayout(self)

        # File Selection
        file_box = QHBoxLayout()
        self.file_input = QLineEdit(default_file)
        self.file_input.setPlaceholderText("Select master audio mix file (.mp3, .wav, .flac)...")
        browse_btn = QPushButton("Browse...")
        from PyQt6.QtWidgets import QFileDialog
        browse_btn.clicked.connect(self._browse_file)
        file_box.addWidget(self.file_input, 1)
        file_box.addWidget(browse_btn)
        layout.addWidget(QLabel("Master Audio File:"))
        layout.addLayout(file_box)

        # Timestamps Text Box
        layout.addWidget(QLabel("Paste Tracklist Timestamps (e.g. 00:00 Artist - Track Name):"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("00:00 Intro - DJ Crate Mix\n03:45 Carl Cox - Techno Jam\n08:12 Amelie Lens - Higher")
        layout.addWidget(self.text_edit, 1)

        # Action Buttons
        btn_box = QHBoxLayout()
        self.split_btn = QPushButton("Split Mix")
        import qtawesome as qta
        self.split_btn.setIcon(qta.icon("fa5s.cut", color="#FFFFFF"))
        self.split_btn.setStyleSheet("background-color: #FF5500; color: #FFFFFF; font-weight: bold; padding: 8px 16px;")
        self.split_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.split_btn)
        layout.addLayout(btn_box)

    def _browse_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select DJ Mix Audio File", "", "Audio Files (*.mp3 *.wav *.flac *.m4a)")
        if path:
            self.file_input.setText(path)

    def get_parsed_data(self):
        """
        Parses timestamps line by line. Returns tuple: (input_file, tracks_info_list)
        """
        import re
        input_file = self.file_input.text().strip()
        lines = self.text_edit.toPlainText().splitlines()
        parsed_tracks = []

        time_pattern = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)')

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            match = time_pattern.search(line_str)
            if not match:
                continue

            time_str = match.group(1)
            parts = time_str.split(':')
            if len(parts) == 2:
                sec = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                continue

            # Extract title / artist from line after timestamp
            clean_title = time_pattern.sub('', line_str).strip(" -–—:\t")
            if not clean_title:
                clean_title = f"Track at {time_str}"

            artist, title = "", clean_title
            if ' - ' in clean_title:
                artist, title = clean_title.split(' - ', 1)
            elif ' – ' in clean_title:
                artist, title = clean_title.split(' – ', 1)

            parsed_tracks.append({
                'start_sec': sec,
                'end_sec': None, # calculated below
                'title': title.strip(),
                'artist': artist.strip(),
                'time_str': time_str
            })

        # Calculate end_sec for each track
        parsed_tracks.sort(key=lambda t: t['start_sec'])
        for i in range(len(parsed_tracks) - 1):
            parsed_tracks[i]['end_sec'] = parsed_tracks[i + 1]['start_sec']

        return input_file, parsed_tracks

