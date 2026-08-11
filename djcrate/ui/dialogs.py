from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QDialogButtonBox, QTextEdit, QWidget, QFrame,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect
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
        filename = os.path.basename(self.track_path).rsplit('.', 1)[0]
        if ' - ' in filename:
            art, tit = filename.split(' - ', 1)
            self.artist_input.setText(art)
            self.title_input.setText(tit)
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
