"""
SetBuilderWidget — Interactive Harmonic Setlist Builder & Transition Planner for DJ Crate.

Provides:
- Real-time visual Energy Flow & BPM curve graph (SetlistEnergyGraph)
- Ordered track sequence with harmonic transition connector cards
- Exact pitch delta calculations and semitone shifts
- Auto-Harmonize nearest-neighbor Camelot ordering
- Live Next-Track Harmonic Suggester drawer
- Multi-format Setlist Exporters (Serato .crate, Rekordbox M3U8, CSV, Text Timestamps, HTML Cheat Sheet)
"""

import os
import math
from typing import List, Dict, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QScrollArea, QFrame, QLineEdit, QMenu, QMessageBox, QFileDialog,
    QInputDialog, QSizePolicy, QApplication, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QFont, QPainterPath,
    QCursor
)
import qtawesome as qta

from djcrate.utils import (
    CamelotMatcher, export_setlist_to_m3u8, export_setlist_to_csv,
    export_setlist_to_tracklist_text, export_setlist_to_cheat_sheet_html
)
from djcrate.serato import SeratoCrateWriter
from djcrate.logger import logger


class SetlistEnergyGraph(QWidget):
    """
    Interactive vector painter widget displaying the set's Energy Flow Trajectory,
    BPM curve, Camelot key nodes, and transition links.
    """
    node_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.flow_data: Dict[str, Any] = {}
        self.tracks: List[Dict[str, Any]] = []
        self.selected_index: int = 0
        self.hover_index: int = -1
        self.node_rects: List[QRectF] = []
        
        self.setFixedHeight(120)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_data(self, flow_data: dict, tracks: list, selected_index: int = 0):
        self.flow_data = flow_data or {}
        self.tracks = tracks or []
        self.selected_index = selected_index
        self.update()

    def set_selected_index(self, index: int):
        self.selected_index = index
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        old_hover = self.hover_index
        self.hover_index = -1

        for i, rect in enumerate(self.node_rects):
            if rect.adjusted(-6, -6, 6, 6).contains(pos):
                self.hover_index = i
                break

        if self.hover_index != old_hover:
            self.update()
            if 0 <= self.hover_index < len(self.tracks):
                t = self.tracks[self.hover_index]
                title = t.get('title', 'Unknown Title')
                artist = t.get('artist', 'Unknown Artist')
                key = t.get('key', '—')
                bpm = t.get('bpm', '—')
                start_time = self.flow_data.get('formatted_start_times', [])
                time_str = start_time[self.hover_index] if self.hover_index < len(start_time) else "00:00"
                
                tip = f"#{self.hover_index+1} · {artist} - {title}\nTime: {time_str} · Key: {key} · BPM: {bpm}"
                if self.hover_index < len(self.flow_data.get('transitions', [])):
                    tr = self.flow_data['transitions'][self.hover_index]
                    tip += f"\n↳ Next Transition: {tr['key_label']} ({tr['deck_a_pitch_pct']:+.1f}% pitch)"
                QToolTip.showText(self.mapToGlobal(event.pos()), tip, self)

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_index = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            for i, rect in enumerate(self.node_rects):
                if rect.adjusted(-8, -8, 8, 8).contains(pos):
                    self.selected_index = i
                    self.node_clicked.emit(i)
                    self.update()
                    break
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Obsidian Charcoal container background
        bg_rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor("#131318"))
        painter.setPen(QPen(QColor("#242430"), 1))
        painter.drawRoundedRect(bg_rect, 6, 6)

        if not self.tracks:
            painter.setPen(QColor("#6A6A78"))
            font = painter.font()
            font.setPixelSize(12)
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, "Add tracks to visualize set harmonic energy trajectory & BPM flow")
            painter.end()
            return

        curve_points = self.flow_data.get('energy_curve', [])
        transitions = self.flow_data.get('transitions', [])
        n_tracks = len(self.tracks)

        # Padding
        pad_left = 40
        pad_right = 40
        pad_top = 22
        pad_bottom = 26
        plot_w = max(10, w - pad_left - pad_right)
        plot_h = max(10, h - pad_top - pad_bottom)

        # Grid lines & energy level labels
        painter.setPen(QPen(QColor("#1D1D26"), 1, Qt.PenStyle.DashLine))
        for level, lbl in [(0.2, "LOW"), (0.5, "MID"), (0.8, "PEAK")]:
            y_grid = int(pad_top + plot_h * (1.0 - level))
            painter.drawLine(pad_left, y_grid, pad_left + plot_w, y_grid)
            font = painter.font()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#454555"))
            painter.drawText(6, y_grid + 4, lbl)
            painter.setPen(QPen(QColor("#1D1D26"), 1, Qt.PenStyle.DashLine))

        # Calculate node coordinates (x, y)
        self.node_rects = []
        coords = []

        for i in range(n_tracks):
            if n_tracks == 1:
                cx = pad_left + plot_w / 2
            else:
                cx = pad_left + (i / (n_tracks - 1)) * plot_w

            # Energy normalized to 0.0 - 1.0 (from 1.0 - 10.0 scale)
            e_val = curve_points[i]['energy'] if i < len(curve_points) else 5.0
            norm_e = max(0.05, min(0.95, (e_val - 1.0) / 9.0))
            cy = pad_top + plot_h * (1.0 - norm_e)

            coords.append((cx, cy))
            self.node_rects.append(QRectF(cx - 10, cy - 10, 20, 20))

        # Render filled energy gradient area under curve
        if len(coords) >= 2:
            path = QPainterPath()
            path.moveTo(coords[0][0], pad_top + plot_h)
            path.lineTo(coords[0][0], coords[0][1])

            for i in range(len(coords) - 1):
                p0 = coords[i]
                p1 = coords[i + 1]
                mid_x = (p0[0] + p1[0]) / 2.0
                path.cubicTo(mid_x, p0[1], mid_x, p1[1], p1[0], p1[1])

            path.lineTo(coords[-1][0], pad_top + plot_h)
            path.closeSubpath()

            grad = QLinearGradient(0, pad_top, 0, pad_top + plot_h)
            grad.setColorAt(0.0, QColor(0, 230, 118, 55))
            grad.setColorAt(0.6, QColor(0, 229, 255, 25))
            grad.setColorAt(1.0, QColor(0, 229, 255, 0))

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

            # Render transition connector segments between nodes
            for i in range(len(coords) - 1):
                p0 = coords[i]
                p1 = coords[i + 1]
                tr = transitions[i] if i < len(transitions) else None
                
                is_clash = tr.get('is_clash', False) if tr else False
                line_color = QColor("#FF4D4D") if is_clash else QColor("#00E676" if (tr and tr.get('overall_score', 0) >= 80) else "#FFD600")
                
                pen = QPen(line_color, 2 if not is_clash else 2.5)
                if is_clash:
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)

                mid_x = (p0[0] + p1[0]) / 2.0
                seg_path = QPainterPath()
                seg_path.moveTo(p0[0], p0[1])
                seg_path.cubicTo(mid_x, p0[1], mid_x, p1[1], p1[0], p1[1])
                painter.drawPath(seg_path)

                # If key clash, draw warning indicator on midpoint
                if is_clash:
                    mid_y = (p0[1] + p1[1]) / 2.0
                    painter.setBrush(QColor("#FF4D4D"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QPoint(int(mid_x), int(mid_y)), 4, 4)

        # Render Nodes (Camelot Color-coded circles with track numbers)
        for i, (cx, cy) in enumerate(coords):
            t = self.tracks[i]
            key = t.get('key', '')
            key_color = QColor(CamelotMatcher.get_camelot_color(key))
            is_selected = (i == self.selected_index)
            is_hovered = (i == self.hover_index)

            node_radius = 9 if not (is_selected or is_hovered) else 12

            # Selection Glow
            if is_selected:
                painter.setBrush(QColor(key_color.red(), key_color.green(), key_color.blue(), 60))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(int(cx), int(cy)), node_radius + 6, node_radius + 6)

            # Node Body
            painter.setBrush(key_color)
            painter.setPen(QPen(QColor("#FFFFFF" if is_selected else "#0E0E12"), 2))
            painter.drawEllipse(QPoint(int(cx), int(cy)), node_radius, node_radius)

            # Track number or key text
            font = painter.font()
            font.setPixelSize(9 if is_selected else 8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#000000" if key_color.lightness() > 140 else "#FFFFFF"))
            num_str = f"{i+1}"
            painter.drawText(QRectF(cx - 10, cy - 8, 20, 16), Qt.AlignmentFlag.AlignCenter, num_str)

            # Camelot Key label below node
            key_str = key if key else f"T{i+1}"
            painter.setPen(QColor(key_color))
            painter.drawText(QRectF(cx - 20, pad_top + plot_h + 4, 40, 14), Qt.AlignmentFlag.AlignCenter, key_str)

        painter.end()


class TransitionConnectorCard(QWidget):
    """
    Visual transition connector strip between two consecutive tracks in the setlist.
    Displays harmonic match ratio, pitch delta fader adjustment, and recommended mix strategy.
    """
    def __init__(self, transition_data: dict, parent=None):
        super().__init__(parent)
        self.data = transition_data
        self.setFixedHeight(40)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 2, 24, 2)
        layout.setSpacing(10)

        # Connector Line Icon
        arrow_lbl = QLabel()
        arrow_lbl.setPixmap(qta.icon("fa5s.long-arrow-alt-down", color="#5A5A6E").pixmap(14, 14))
        layout.addWidget(arrow_lbl)

        # Harmonic Key Badge
        key_lbl = self.data.get('key_label', 'Unknown')
        is_clash = self.data.get('is_clash', False)
        badge_color = self.data.get('badge_color', '#00E676')

        harm_badge = QLabel(f" {key_lbl} ")
        harm_badge.setFixedHeight(22)
        bg_rgba = "rgba(255, 77, 77, 0.15)" if is_clash else "rgba(0, 230, 118, 0.12)" if badge_color == "#00E676" else "rgba(255, 214, 0, 0.12)"
        harm_badge.setStyleSheet(f"""
            QLabel {{
                color: {badge_color};
                background-color: {bg_rgba};
                border: 1px solid {badge_color};
                border-radius: 4px;
                font-size: 10px;
                font-weight: 800;
                padding: 1px 6px;
            }}
        """)
        layout.addWidget(harm_badge)

        # Pitch Adjustment Badge
        bpm1 = self.data.get('bpm1', 0.0)
        bpm2 = self.data.get('bpm2', 0.0)
        pitch_pct = self.data.get('deck_a_pitch_pct', 0.0)
        
        if bpm1 > 0 and bpm2 > 0:
            sign = "+" if pitch_pct > 0 else ""
            pitch_str = f"Pitch Deck A: {sign}{pitch_pct:.1f}% ({round(bpm1)} → {round(bpm2)} BPM)"
            pitch_badge = QLabel(pitch_str)
            pitch_badge.setFixedHeight(22)
            pitch_badge.setStyleSheet("""
                QLabel {
                    color: #00E5FF;
                    background-color: rgba(0, 229, 255, 0.08);
                    border: 1px solid rgba(0, 229, 255, 0.25);
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 1px 6px;
                }
            """)
            layout.addWidget(pitch_badge)

        # Transition Mix Strategy Tag
        technique = self.data.get('technique', '')
        if technique:
            tech_lbl = QLabel(f"Strategy: {technique}")
            tech_lbl.setStyleSheet("color: #9C9CAE; font-size: 11px; font-style: italic;")
            layout.addWidget(tech_lbl)

        layout.addStretch()


class SetlistTrackRow(QWidget):
    """
    A single track item in the ordered setlist with position, Camelot key, BPM,
    time elapsed, move Up/Down buttons, play audition button, and note editor.
    """
    play_requested = pyqtSignal(dict)
    move_up_requested = pyqtSignal(int)
    move_down_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)
    note_edit_requested = pyqtSignal(int)

    def __init__(self, position: int, track: dict, start_time_str: str = "00:00",
                 is_first: bool = False, is_last: bool = False, parent=None):
        super().__init__(parent)
        self.position = position
        self.track = track
        self.start_time_str = start_time_str
        self.is_first = is_first
        self.is_last = is_last
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(48)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            SetlistTrackRow {
                background-color: #17171F;
                border: 1px solid #232330;
                border-radius: 6px;
            }
            SetlistTrackRow:hover {
                background-color: #1D1D28;
                border-color: #353545;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        # 1. Position Number & Drag Handle
        pos_lbl = QLabel(f"#{self.position + 1:02d}")
        pos_lbl.setFixedWidth(28)
        pos_lbl.setStyleSheet("color: #6C6C80; font-size: 11px; font-weight: 800;")
        layout.addWidget(pos_lbl)

        # 2. Cumulative Start Time
        time_lbl = QLabel(self.start_time_str)
        time_lbl.setFixedWidth(44)
        time_lbl.setStyleSheet("color: #00E5FF; font-size: 11px; font-family: monospace; font-weight: 700;")
        layout.addWidget(time_lbl)

        # 3. Play / Audition Button
        btn_play = QPushButton()
        btn_play.setIcon(qta.icon("fa5s.play", color="#E8E3DF"))
        btn_play.setFixedSize(28, 28)
        btn_play.setStyleSheet("QPushButton { background: #22222E; border: 1px solid #303040; border-radius: 4px; } QPushButton:hover { background: #2F2F40; }")
        btn_play.setToolTip("Audition / Play Track")
        btn_play.clicked.connect(lambda: self.play_requested.emit(self.track))
        layout.addWidget(btn_play)

        # 4. Title & Artist
        title = self.track.get('title', 'Unknown Title')
        artist = self.track.get('artist', 'Unknown Artist')
        
        info_box = QVBoxLayout()
        info_box.setContentsMargins(0, 2, 0, 2)
        info_box.setSpacing(1)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 700;")
        artist_lbl = QLabel(artist)
        artist_lbl.setStyleSheet("color: #8C8C9E; font-size: 11px;")

        info_box.addWidget(title_lbl)
        info_box.addWidget(artist_lbl)
        layout.addLayout(info_box, 1)

        # 5. Camelot Key Pill
        key = self.track.get('key', '')
        if key:
            key_color = CamelotMatcher.get_camelot_color(key)
            key_lbl = QLabel(f" {key} ")
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_lbl.setFixedWidth(44)
            key_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {key_color};
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1px solid {key_color};
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 800;
                    padding: 2px;
                }}
            """)
            layout.addWidget(key_lbl)

        # 6. BPM Badge
        bpm = self.track.get('bpm', '')
        if bpm:
            bpm_lbl = QLabel(f"{bpm} BPM")
            bpm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bpm_lbl.setFixedWidth(64)
            bpm_lbl.setStyleSheet("""
                QLabel {
                    color: #FF9100;
                    background-color: rgba(255, 145, 0, 0.08);
                    border: 1px solid rgba(255, 145, 0, 0.25);
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px;
                }
            """)
            layout.addWidget(bpm_lbl)

        # 7. Duration
        dur = int(self.track.get('duration', 0) or 0)
        dur_str = f"{dur // 60}:{dur % 60:02d}"
        dur_lbl = QLabel(dur_str)
        dur_lbl.setFixedWidth(38)
        dur_lbl.setStyleSheet("color: #7A7A8E; font-size: 11px;")
        layout.addWidget(dur_lbl)

        # 8. Notes Tooltip / Indicator
        item_notes = self.track.get('item_notes', '') or self.track.get('notes', '')
        btn_notes = QPushButton()
        btn_notes.setIcon(qta.icon("fa5s.sticky-note", color="#FFD600" if item_notes else "#6C6C80"))
        btn_notes.setFixedSize(26, 26)
        btn_notes.setStyleSheet("background: transparent; border: none;")
        btn_notes.setToolTip(f"Transition Notes: {item_notes}" if item_notes else "Add Transition / Cue Notes")
        btn_notes.clicked.connect(lambda: self.note_edit_requested.emit(self.position))
        layout.addWidget(btn_notes)

        # 9. Up / Down Move buttons
        btn_up = QPushButton()
        btn_up.setIcon(qta.icon("fa5s.chevron-up", color="#A0A0B0"))
        btn_up.setFixedSize(24, 24)
        btn_up.setEnabled(not self.is_first)
        btn_up.setStyleSheet("QPushButton { background: #22222E; border: none; border-radius: 3px; } QPushButton:hover { background: #2E2E3E; }")
        btn_up.clicked.connect(lambda: self.move_up_requested.emit(self.position))
        layout.addWidget(btn_up)

        btn_down = QPushButton()
        btn_down.setIcon(qta.icon("fa5s.chevron-down", color="#A0A0B0"))
        btn_down.setFixedSize(24, 24)
        btn_down.setEnabled(not self.is_last)
        btn_down.setStyleSheet("QPushButton { background: #22222E; border: none; border-radius: 3px; } QPushButton:hover { background: #2E2E3E; }")
        btn_down.clicked.connect(lambda: self.move_down_requested.emit(self.position))
        layout.addWidget(btn_down)

        # 10. Remove Button
        btn_del = QPushButton()
        btn_del.setIcon(qta.icon("fa5s.times", color="#FF5252"))
        btn_del.setFixedSize(24, 24)
        btn_del.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: rgba(255, 82, 82, 0.2); border-radius: 3px; }")
        btn_del.setToolTip("Remove from Setlist")
        btn_del.clicked.connect(lambda: self.remove_requested.emit(self.position))
        layout.addWidget(btn_del)


class NextTrackSuggester(QWidget):
    """
    Intelligent Harmonic Next-Track Suggester drawer.
    Surfaces the most harmonically and tempo-compatible tracks from the library
    for mixing immediately after the selected track.
    """
    insert_track_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library_tracks: List[dict] = []
        self.current_track: Optional[dict] = None
        self.setFixedWidth(290)
        self.setup_ui()

    def setup_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            NextTrackSuggester {
                background-color: #14141B;
                border-left: 1px solid #242432;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.magic", color="#00E676").pixmap(14, 14))
        title_lbl = QLabel("HARMONIC NEXT TRACKS")
        title_lbl.setStyleSheet("color: #00E676; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        hdr.addWidget(icon_lbl)
        hdr.addWidget(title_lbl, 1)
        layout.addLayout(hdr)

        self.anchor_lbl = QLabel("Select a track in setlist to find harmonic matches")
        self.anchor_lbl.setStyleSheet("color: #8A8A9E; font-size: 11px;")
        self.anchor_lbl.setWordWrap(True)
        layout.addWidget(self.anchor_lbl)

        # Scrollable list of suggestions
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.content_w = QWidget()
        self.content_layout = QVBoxLayout(self.content_w)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_layout.addStretch()

        self.scroll.setWidget(self.content_w)
        layout.addWidget(self.scroll, 1)

    def set_library_tracks(self, tracks: list):
        self.library_tracks = tracks or []
        if self.current_track:
            self.refresh_suggestions(self.current_track)

    def refresh_suggestions(self, track: dict):
        self.current_track = track
        # Clear layout
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not track:
            self.anchor_lbl.setText("Select a track in setlist to find harmonic matches")
            return

        t_title = track.get('title', 'Unknown')
        t_key = track.get('key', '—')
        t_bpm = track.get('bpm', '—')
        self.anchor_lbl.setText(f"Matching from: <b>{t_title}</b> ({t_key} · {t_bpm} BPM)")

        # Rank all library tracks
        ranked = []
        for cand in self.library_tracks:
            if cand.get('path') == track.get('file_path') or cand.get('path') == track.get('path'):
                continue
            cand_dict = {
                'title': cand.get('title', ''),
                'artist': cand.get('artist', ''),
                'key': cand.get('key', ''),
                'bpm': cand.get('bpm', ''),
                'rating': cand.get('rating', 0),
                'file_path': cand.get('path', ''),
                'duration': cand.get('duration', 0)
            }
            analysis = CamelotMatcher.calculate_transition_analysis(track, cand_dict)
            if not analysis['is_clash'] and analysis['overall_score'] >= 55:
                ranked.append((analysis['overall_score'], analysis, cand_dict))

        # Sort highest score first
        ranked.sort(key=lambda x: x[0], reverse=True)

        if not ranked:
            no_match = QLabel("No harmonic matches found in downloaded library.")
            no_match.setStyleSheet("color: #6C6C80; font-size: 11px; font-style: italic;")
            self.content_layout.insertWidget(0, no_match)
            return

        # Render top 8 suggestions
        for score, analysis, cand in ranked[:8]:
            card = QWidget()
            card.setStyleSheet("""
                QWidget {
                    background-color: #1A1A24;
                    border: 1px solid #282838;
                    border-radius: 6px;
                }
                QWidget:hover {
                    border-color: #00E676;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(8, 8, 8, 8)
            c_layout.setSpacing(4)

            top = QHBoxLayout()
            c_title = QLabel(cand.get('title', 'Unknown Title'))
            c_title.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: 700;")
            
            score_lbl = QLabel(f"{score}% Match")
            score_lbl.setStyleSheet("color: #00E676; font-size: 10px; font-weight: 800;")
            top.addWidget(c_title, 1)
            top.addWidget(score_lbl)
            c_layout.addLayout(top)

            meta = QHBoxLayout()
            c_artist = QLabel(cand.get('artist', 'Unknown'))
            c_artist.setStyleSheet("color: #8C8C9E; font-size: 10px;")
            meta.addWidget(c_artist, 1)

            key = cand.get('key', '')
            if key:
                k_col = CamelotMatcher.get_camelot_color(key)
                k_lbl = QLabel(key)
                k_lbl.setStyleSheet(f"color: {k_col}; font-weight: 800; font-size: 10px;")
                meta.addWidget(k_lbl)

            bpm = cand.get('bpm', '')
            if bpm:
                b_lbl = QLabel(f"{bpm} BPM")
                b_lbl.setStyleSheet("color: #FF9100; font-size: 10px; font-weight: 700;")
                meta.addWidget(b_lbl)

            c_layout.addLayout(meta)

            # Details
            pitch_str = f"{analysis['deck_a_pitch_pct']:+.1f}% pitch" if analysis['bpm1'] > 0 and analysis['bpm2'] > 0 else ""
            desc_lbl = QLabel(f"{analysis['key_label']} · {pitch_str}")
            desc_lbl.setStyleSheet("color: #00E5FF; font-size: 10px;")
            c_layout.addWidget(desc_lbl)

            # Insert Button
            btn_add = QPushButton(" + Insert into Set")
            btn_add.setFixedHeight(24)
            btn_add.setStyleSheet("""
                QPushButton {
                    background-color: #242436;
                    color: #E8E3DF;
                    border: 1px solid #36364D;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #00E676;
                    color: #0E0E12;
                    border-color: #00E676;
                }
            """)
            btn_add.clicked.connect(lambda _, c=cand: self.insert_track_requested.emit(c))
            c_layout.addWidget(btn_add)

            self.content_layout.insertWidget(self.content_layout.count() - 1, card)


class SetBuilderPage(QWidget):
    """
    Main Set Builder & Transition Planner workstation page.
    """
    track_preview_requested = pyqtSignal(dict)
    toast_requested = pyqtSignal(str, str)

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.active_setlist_id: Optional[int] = None
        self.setlists: List[dict] = []
        self.current_setlist_data: Optional[dict] = None
        self.library_tracks: List[dict] = []
        self.setup_ui()
        self.load_setlists()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Left Column: Header, Energy Graph, Track List
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # 1. Top Control Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        lbl_set = QLabel("Setlist:")
        lbl_set.setStyleSheet("color: #E8E3DF; font-size: 12px; font-weight: 700;")
        top_bar.addWidget(lbl_set)

        self.setlist_combo = QComboBox()
        self.setlist_combo.setFixedHeight(32)
        self.setlist_combo.setMinimumWidth(200)
        self.setlist_combo.currentIndexChanged.connect(self._on_setlist_combo_changed)
        top_bar.addWidget(self.setlist_combo)

        btn_new = QPushButton(" New Set")
        btn_new.setIcon(qta.icon("fa5s.plus", color="#00E676"))
        btn_new.setFixedHeight(32)
        btn_new.clicked.connect(self.create_new_setlist)
        top_bar.addWidget(btn_new)

        btn_dup = QPushButton(" Duplicate")
        btn_dup.setIcon(qta.icon("fa5s.copy", color="#A39E9A"))
        btn_dup.setFixedHeight(32)
        btn_dup.clicked.connect(self.duplicate_current_setlist)
        top_bar.addWidget(btn_dup)

        btn_rename = QPushButton(" Rename")
        btn_rename.setIcon(qta.icon("fa5s.edit", color="#A39E9A"))
        btn_rename.setFixedHeight(32)
        btn_rename.clicked.connect(self.rename_current_setlist)
        top_bar.addWidget(btn_rename)

        btn_del = QPushButton(" Delete")
        btn_del.setIcon(qta.icon("fa5s.trash", color="#FF5252"))
        btn_del.setFixedHeight(32)
        btn_del.clicked.connect(self.delete_current_setlist)
        top_bar.addWidget(btn_del)

        top_bar.addStretch()

        btn_auto_harm = QPushButton(" Auto-Harmonize")
        btn_auto_harm.setIcon(qta.icon("fa5s.magic", color="#00E5FF"))
        btn_auto_harm.setFixedHeight(32)
        btn_auto_harm.setToolTip("Automatically arrange tracks into the smoothest harmonic Camelot order")
        btn_auto_harm.clicked.connect(self.auto_harmonize_set)
        top_bar.addWidget(btn_auto_harm)

        btn_export = QPushButton(" Export Set ▾")
        btn_export.setIcon(qta.icon("fa5s.file-export", color="#FF9100"))
        btn_export.setFixedHeight(32)
        btn_export.clicked.connect(self.show_export_menu)
        top_bar.addWidget(btn_export)

        left_col.addLayout(top_bar)

        # 2. Stats Bar
        self.stats_bar = QWidget()
        self.stats_bar.setFixedHeight(34)
        self.stats_bar.setStyleSheet("""
            QWidget {
                background-color: #16161E;
                border: 1px solid #232330;
                border-radius: 6px;
            }
        """)
        sb_layout = QHBoxLayout(self.stats_bar)
        sb_layout.setContentsMargins(12, 4, 12, 4)
        sb_layout.setSpacing(16)

        self.lbl_stat_duration = QLabel("⏱️ Total Duration: 00:00")
        self.lbl_stat_duration.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 700;")
        self.lbl_stat_tracks = QLabel("🎵 0 Tracks")
        self.lbl_stat_tracks.setStyleSheet("color: #E8E3DF; font-size: 11px; font-weight: 700;")
        self.lbl_stat_bpm = QLabel("⚡ Avg BPM: 0")
        self.lbl_stat_bpm.setStyleSheet("color: #FF9100; font-size: 11px; font-weight: 700;")
        self.lbl_stat_health = QLabel("✨ 100% Harmonic Flow")
        self.lbl_stat_health.setStyleSheet("color: #00E676; font-size: 11px; font-weight: 800;")
        self.lbl_stat_clashes = QLabel("⚠️ 0 Clashes")
        self.lbl_stat_clashes.setStyleSheet("color: #8C8C9E; font-size: 11px; font-weight: 700;")

        sb_layout.addWidget(self.lbl_stat_duration)
        sb_layout.addWidget(self.lbl_stat_tracks)
        sb_layout.addWidget(self.lbl_stat_bpm)
        sb_layout.addWidget(self.lbl_stat_health)
        sb_layout.addWidget(self.lbl_stat_clashes)
        sb_layout.addStretch()

        left_col.addWidget(self.stats_bar)

        # 3. Interactive Energy Flow Graph
        self.energy_graph = SetlistEnergyGraph(self)
        self.energy_graph.node_clicked.connect(self._on_graph_node_clicked)
        left_col.addWidget(self.energy_graph)

        # 4. Scrollable Ordered Setlist Track Container
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setStyleSheet("background: transparent; border: none;")
        self.list_content = QWidget()
        self.list_layout = QVBoxLayout(self.list_content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        self.list_scroll.setWidget(self.list_content)
        left_col.addWidget(self.list_scroll, 1)

        main_layout.addLayout(left_col, 1)

        # Right Column: Suggester Panel
        self.suggester = NextTrackSuggester(self)
        self.suggester.insert_track_requested.connect(self.insert_suggested_track)
        main_layout.addWidget(self.suggester)

    def set_library_tracks(self, tracks: list):
        self.library_tracks = tracks or []
        self.suggester.set_library_tracks(self.library_tracks)

    def load_setlists(self):
        self.setlists = self.settings_manager.get_setlists()
        self.setlist_combo.blockSignals(True)
        self.setlist_combo.clear()

        if not self.setlists:
            # Create a default setlist if none exists
            new_id = self.settings_manager.create_setlist("Peak Time Set (Default)")
            self.setlists = self.settings_manager.get_setlists()

        for s in self.setlists:
            self.setlist_combo.addItem(f"{s['name']} ({s.get('track_count', 0)} tracks)", s['id'])

        self.setlist_combo.blockSignals(False)

        if self.setlists:
            self.active_setlist_id = self.setlists[0]['id']
            self.refresh_active_setlist()

    def _on_setlist_combo_changed(self, idx):
        if idx >= 0:
            set_id = self.setlist_combo.itemData(idx)
            if set_id:
                self.active_setlist_id = set_id
                self.refresh_active_setlist()

    def refresh_active_setlist(self):
        if not self.active_setlist_id:
            return

        self.current_setlist_data = self.settings_manager.get_setlist(self.active_setlist_id)
        if not self.current_setlist_data:
            return

        items = self.current_setlist_data.get('items', [])
        flow = CamelotMatcher.calculate_setlist_flow(items)

        # Update stats
        self.lbl_stat_duration.setText(f"⏱️ Total Duration: {flow['total_duration_str']}")
        self.lbl_stat_tracks.setText(f"🎵 {flow['track_count']} Tracks")
        self.lbl_stat_bpm.setText(f"⚡ Avg BPM: {flow['avg_bpm']}")
        self.lbl_stat_health.setText(f"✨ {flow['harmonic_flow_score']}% Harmonic Flow")
        
        clashes = flow['clash_count']
        self.lbl_stat_clashes.setText(f"⚠️ {clashes} Clashes" if clashes > 0 else "✅ 0 Clashes")
        self.lbl_stat_clashes.setStyleSheet(f"color: {'#FF4D4D' if clashes > 0 else '#00E676'}; font-size: 11px; font-weight: 700;")

        # Update Energy Graph
        self.energy_graph.set_data(flow, items)

        # Re-render list
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            empty_lbl = QLabel("This setlist is currently empty.\nAdd tracks from your Library (right-click → 'Add to Setlist') or use the Suggester!")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #6C6C80; font-size: 13px; padding: 40px;")
            self.list_layout.insertWidget(0, empty_lbl)
            self.suggester.refresh_suggestions(None)
            return

        for i, track in enumerate(items):
            start_time = flow['formatted_start_times'][i] if i < len(flow['formatted_start_times']) else "00:00"
            row = SetlistTrackRow(
                position=i,
                track=track,
                start_time_str=start_time,
                is_first=(i == 0),
                is_last=(i == len(items) - 1),
                parent=self
            )
            row.play_requested.connect(self.track_preview_requested.emit)
            row.move_up_requested.connect(self.move_track_up)
            row.move_down_requested.connect(self.move_track_down)
            row.remove_requested.connect(self.remove_track)
            row.note_edit_requested.connect(self.edit_track_note)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

            # Insert transition connector between consecutive rows
            if i < len(flow['transitions']):
                tr_card = TransitionConnectorCard(flow['transitions'][i], parent=self)
                self.list_layout.insertWidget(self.list_layout.count() - 1, tr_card)

        # Update suggester with first track or selected track
        if items:
            self.suggester.refresh_suggestions(items[min(self.energy_graph.selected_index, len(items)-1)])

    def _on_graph_node_clicked(self, index: int):
        if self.current_setlist_data and self.current_setlist_data.get('items'):
            items = self.current_setlist_data['items']
            if 0 <= index < len(items):
                self.suggester.refresh_suggestions(items[index])

    def create_new_setlist(self):
        name, ok = QInputDialog.getText(self, "Create New Setlist", "Enter setlist name:")
        if ok and name.strip():
            new_id = self.settings_manager.create_setlist(name.strip())
            self.load_setlists()
            self.active_setlist_id = new_id
            self.refresh_active_setlist()
            self.toast_requested.emit(f"Created setlist: {name.strip()}", "success")

    def duplicate_current_setlist(self):
        if not self.active_setlist_id:
            return
        curr_name = self.current_setlist_data.get('name', 'Set') if self.current_setlist_data else 'Set'
        new_name, ok = QInputDialog.getText(self, "Duplicate Setlist", "New setlist name:", text=f"{curr_name} (Copy)")
        if ok and new_name.strip():
            new_id = self.settings_manager.duplicate_setlist(self.active_setlist_id, new_name.strip())
            self.load_setlists()
            self.active_setlist_id = new_id
            self.refresh_active_setlist()
            self.toast_requested.emit(f"Duplicated setlist as '{new_name.strip()}'", "success")

    def rename_current_setlist(self):
        if not self.active_setlist_id:
            return
        curr_name = self.current_setlist_data.get('name', '') if self.current_setlist_data else ''
        new_name, ok = QInputDialog.getText(self, "Rename Setlist", "Enter new name:", text=curr_name)
        if ok and new_name.strip():
            self.settings_manager.update_setlist(self.active_setlist_id, name=new_name.strip())
            self.load_setlists()
            self.refresh_active_setlist()
            self.toast_requested.emit(f"Renamed setlist to '{new_name.strip()}'", "success")

    def delete_current_setlist(self):
        if not self.active_setlist_id:
            return
        reply = QMessageBox.question(
            self, "Delete Setlist",
            f"Are you sure you want to delete the setlist '{self.current_setlist_data.get('name', '')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings_manager.delete_setlist(self.active_setlist_id)
            self.active_setlist_id = None
            self.load_setlists()
            self.toast_requested.emit("Setlist deleted", "info")

    def add_tracks_to_setlist(self, file_paths: list):
        if not self.active_setlist_id:
            if not self.setlists:
                self.active_setlist_id = self.settings_manager.create_setlist("My First DJ Set")
            else:
                self.active_setlist_id = self.setlists[0]['id']

        for path in file_paths:
            self.settings_manager.add_track_to_setlist(self.active_setlist_id, path)

        self.refresh_active_setlist()
        self.toast_requested.emit(f"Added {len(file_paths)} track(s) to setlist!", "success")

    def insert_suggested_track(self, cand_track: dict):
        if not self.active_setlist_id:
            return
        path = cand_track.get('file_path') or cand_track.get('path')
        if not path:
            return
        self.settings_manager.add_track_to_setlist(self.active_setlist_id, path)
        self.refresh_active_setlist()
        self.toast_requested.emit(f"Inserted '{cand_track.get('title')}' into set!", "success")

    def move_track_up(self, position: int):
        if position > 0 and self.active_setlist_id:
            self.settings_manager.reorder_setlist_track(self.active_setlist_id, position, position - 1)
            self.refresh_active_setlist()

    def move_track_down(self, position: int):
        items = self.current_setlist_data.get('items', []) if self.current_setlist_data else []
        if position < len(items) - 1 and self.active_setlist_id:
            self.settings_manager.reorder_setlist_track(self.active_setlist_id, position, position + 1)
            self.refresh_active_setlist()

    def remove_track(self, position: int):
        if self.active_setlist_id:
            self.settings_manager.remove_track_from_setlist(self.active_setlist_id, position)
            self.refresh_active_setlist()

    def edit_track_note(self, position: int):
        if not self.active_setlist_id or not self.current_setlist_data:
            return
        items = self.current_setlist_data.get('items', [])
        if not (0 <= position < len(items)):
            return
        curr_notes = items[position].get('item_notes', '')
        new_note, ok = QInputDialog.getText(self, "Edit Transition Notes", "Enter transition / cue notes:", text=curr_notes)
        if ok:
            self.settings_manager.update_setlist_item(self.active_setlist_id, position, notes=new_note.strip())
            self.refresh_active_setlist()

    def auto_harmonize_set(self):
        if not self.active_setlist_id or not self.current_setlist_data:
            return
        items = self.current_setlist_data.get('items', [])
        if len(items) < 2:
            self.toast_requested.emit("Setlist needs at least 2 tracks to auto-harmonize.", "info")
            return

        reordered = CamelotMatcher.auto_harmonize_track_order(items)
        reordered_paths = [t['file_path'] for t in reordered]
        self.settings_manager.set_setlist_tracks(self.active_setlist_id, reordered_paths)
        self.refresh_active_setlist()
        self.toast_requested.emit("✨ Auto-harmonized setlist for optimal harmonic energy flow!", "success")

    def show_export_menu(self):
        if not self.current_setlist_data or not self.current_setlist_data.get('items'):
            self.toast_requested.emit("Setlist is empty. Add tracks before exporting.", "error")
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1A24;
                color: #FFFFFF;
                border: 1px solid #2D2D3D;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #29293B;
            }
        """)

        act_serato = menu.addAction("Export to Serato .crate (Native Binary)")
        act_m3u8 = menu.addAction("Export to Rekordbox / M3U8 Playlist (.m3u8)")
        act_csv = menu.addAction("Export to CSV Spreadsheet (.csv)")
        act_txt = menu.addAction("Export 1001Tracklists Timestamps (.txt)")
        act_html = menu.addAction("Export Visual Transition Cheat Sheet (.html)")

        action = menu.exec(QCursor.pos())
        if not action:
            return

        set_name = self.current_setlist_data.get('name', 'Setlist')
        items = self.current_setlist_data.get('items', [])

        if action == act_serato:
            self._export_serato(set_name, items)
        elif action == act_m3u8:
            self._export_m3u8(set_name, items)
        elif action == act_csv:
            self._export_csv(set_name, items)
        elif action == act_txt:
            self._export_txt(set_name, items)
        elif action == act_html:
            self._export_html(set_name, items)

    def _export_serato(self, set_name: str, items: list):
        paths = [t['file_path'] for t in items if os.path.exists(t.get('file_path', ''))]
        try:
            crate_file = SeratoCrateWriter.write_crate(f"SET - {set_name}", paths)
            self.toast_requested.emit(f"Exported Serato crate to: {crate_file}", "success")
        except Exception as e:
            logger.error(f"Error exporting Serato crate: {e}")
            self.toast_requested.emit(f"Failed to export Serato crate: {e}", "error")

    def _export_m3u8(self, set_name: str, items: list):
        path, _ = QFileDialog.getSaveFileName(self, "Export M3U8 Playlist", f"{set_name}.m3u8", "M3U8 Playlists (*.m3u8)")
        if path:
            export_setlist_to_m3u8(set_name, items, path)
            self.toast_requested.emit(f"Exported M3U8 playlist to: {os.path.basename(path)}", "success")

    def _export_csv(self, set_name: str, items: list):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{set_name}.csv", "CSV Files (*.csv)")
        if path:
            export_setlist_to_csv(set_name, items, path)
            self.toast_requested.emit(f"Exported CSV to: {os.path.basename(path)}", "success")

    def _export_txt(self, set_name: str, items: list):
        path, _ = QFileDialog.getSaveFileName(self, "Export Timestamps", f"{set_name}_timestamps.txt", "Text Files (*.txt)")
        if path:
            content = export_setlist_to_tracklist_text(set_name, items)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.toast_requested.emit(f"Exported Tracklist Timestamps to: {os.path.basename(path)}", "success")

    def _export_html(self, set_name: str, items: list):
        path, _ = QFileDialog.getSaveFileName(self, "Export Cheat Sheet HTML", f"{set_name}_cheat_sheet.html", "HTML Files (*.html)")
        if path:
            export_setlist_to_cheat_sheet_html(set_name, items, path)
            self.toast_requested.emit(f"Exported DJ Cheat Sheet to: {os.path.basename(path)}", "success")
