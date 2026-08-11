import os
import random
import math
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSlider,
    QProgressBar, QStackedWidget, QComboBox, QListWidget, QDialog,
    QTextEdit, QApplication, QGraphicsOpacityEffect, QGridLayout
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPoint, QRect, QTimer, QUrl, QMimeData,
    QPropertyAnimation, QEasingCurve, QVariantAnimation
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QPixmap,
    QDrag, QDesktopServices, QFont
)
from PyQt6.QtMultimedia import QMediaPlayer
import qtawesome as qta

# ─── SoundCloud-Style Waveform Player Scrubber ─────────────────────────────

class PlayerSlider(QSlider):
    """
    Exact SoundCloud Waveform Scrubber.
    Renders tall rounded vertical top bars and mirrored bottom reflection bars over a baseline.
    Unplayed state is crisp solid white peaks with light gray reflection.
    Played state turns into SoundCloud Orange / Vibrant Accent Color with lighter orange reflection.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.waveform_pixmap = None
        self.peaks = []
        self.accent_color = "#FF5500"
        self.hover_x = -1
        self.total_duration_secs = 0
        self.setFixedHeight(70)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_waveform(self, pixmap):
        self.waveform_pixmap = pixmap
        self.update()

    def set_peaks(self, peaks_list):
        self.peaks = peaks_list
        self.update()

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color or "#FF5500"
        self.update()

    def set_duration(self, secs):
        self.total_duration_secs = secs
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = int((event.pos().x() / max(1, self.width())) * (self.maximum() - self.minimum())) + self.minimum()
            val = max(self.minimum(), min(self.maximum(), val))
            self.setValue(val)
            self.sliderMoved.emit(val)
            self.sliderPressed.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hover_x = event.pos().x()
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = int((event.pos().x() / max(1, self.width())) * (self.maximum() - self.minimum())) + self.minimum()
            val = max(self.minimum(), min(self.maximum(), val))
            self.setValue(val)
            self.sliderMoved.emit(val)
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_x = -1
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 10 if delta > 0 else -10
        new_val = max(self.minimum(), min(self.maximum(), self.value() + step))
        self.setValue(new_val)
        self.sliderMoved.emit(new_val)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(0)
            self.sliderMoved.emit(0)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        progress_ratio = (self.value() - self.minimum()) / max(1, (self.maximum() - self.minimum()))
        progress_x = int(progress_ratio * w)

        # SoundCloud Tall Peak Geometry
        y_base = int(h * 0.64)
        max_top_h = int(h * 0.56)
        max_bot_h = int(h * 0.24)

        bar_w = 4
        gap = 2
        total_step = bar_w + gap
        num_bars = max(1, w // total_step)

        accent_qcolor = QColor(self.accent_color)
        accent_refl = QColor(self.accent_color)
        accent_refl.setAlpha(170)

        unplayed_top = QColor("#FFFFFF")
        unplayed_refl = QColor("rgba(255, 255, 255, 0.45)")

        # Render Peak Bars
        for i in range(num_bars):
            bx = i * total_step

            # Peak sample calculation
            if self.peaks and len(self.peaks) > 0:
                idx = int((i / num_bars) * len(self.peaks))
                idx = max(0, min(len(self.peaks) - 1, idx))
                val = self.peaks[idx]
            else:
                val = (math.sin(i * 0.18) * 0.35 + math.cos(i * 0.45) * 0.25 + math.sin(i * 0.85) * 0.15 + 0.5)

            top_h = max(4, int(val * max_top_h))
            bot_h = max(2, int(val * max_bot_h))

            if bx <= progress_x:
                # PLAYED STATE: Vibrant SoundCloud Orange
                painter.setBrush(accent_qcolor)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(bx, y_base - top_h, bar_w, top_h, 1, 1)

                painter.setBrush(accent_refl)
                painter.drawRoundedRect(bx, y_base + 2, bar_w, bot_h, 1, 1)
            else:
                # UNPLAYED STATE: Pure Solid White top + muted gray reflection
                painter.setBrush(unplayed_top)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(bx, y_base - top_h, bar_w, top_h, 1, 1)

                painter.setBrush(unplayed_refl)
                painter.drawRoundedRect(bx, y_base + 2, bar_w, bot_h, 1, 1)

        # Center Baseline
        painter.setPen(QPen(QColor("#2C2A29"), 1))
        painter.drawLine(0, y_base + 1, w, y_base + 1)

        # Hover position line
        if self.hover_x >= 0 and self.hover_x != progress_x:
            hover_pen = QPen(QColor("rgba(255, 255, 255, 0.6)"))
            hover_pen.setWidth(1)
            hover_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(hover_pen)
            painter.setOpacity(0.8)
            painter.drawLine(self.hover_x, 0, self.hover_x, h)

        # Timestamp Badges (SoundCloud style)
        if self.isEnabled() and self.total_duration_secs > 0:
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)

            curr_secs = int(progress_ratio * self.total_duration_secs)
            rem_secs = max(0, self.total_duration_secs - curr_secs)

            curr_str = f"{curr_secs // 60}:{curr_secs % 60:02d}"
            rem_str = f"-{rem_secs // 60}:{rem_secs % 60:02d}"

            # Left played timestamp badge
            if progress_x > 15:
                badge_rect = QRect(0, y_base - 16, 34, 16)
                painter.setBrush(QColor("#000000"))
                painter.setPen(QPen(accent_qcolor, 1))
                painter.drawRoundedRect(badge_rect, 3, 3)
                painter.setPen(accent_qcolor)
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, curr_str)

            # Right remaining timestamp badge
            badge_rem_rect = QRect(w - 38, y_base - 16, 38, 16)
            painter.setBrush(QColor("rgba(0, 0, 0, 0.85)"))
            painter.setPen(QPen(QColor("#383432"), 1))
            painter.drawRoundedRect(badge_rem_rect, 3, 3)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rem_rect, Qt.AlignmentFlag.AlignCenter, rem_str)

        painter.end()


class VolumeSlider(QSlider):
    """Volume slider with 5% per scroll-wheel step."""
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 5 if delta > 0 else -5
        new_val = max(0, min(100, self.value() + step))
        self.setValue(new_val)
        event.accept()


class ClickableLabel(QLabel):
    """Label that emits a signal when clicked."""
    clicked = pyqtSignal()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class LoadingSpinner(QWidget):
    def __init__(self, accent_color="#C47D63", parent=None):
        super().__init__(parent)
        self.angle = 0
        self.accent_color = accent_color
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setFixedSize(40, 40)

    def start(self):
        if not self.timer.isActive():
            self.timer.start(16)

    def stop(self):
        self.timer.stop()

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color
        self.update()

    def rotate(self):
        self.angle = (self.angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        pen_bg = QPen(QColor("#3B3633"), 4)
        painter.setPen(pen_bg)
        painter.drawEllipse(rect)
        pen_fg = QPen(QColor(self.accent_color), 4)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        painter.drawArc(rect, self.angle * 16, 120 * 16)


class ToastNotification(QWidget):
    closed = pyqtSignal()

    def __init__(self, message, toast_type="success", parent=None, action_label=None, action_callback=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)

        icons_map = {
            "success": ("fa5s.check-circle", "#788566"),
            "error": ("fa5s.exclamation-circle", "#B35959"),
            "info": ("fa5s.info-circle", "#6A8FA7"),
        }
        icon_name, color = icons_map.get(toast_type, icons_map["info"])

        bg_map = {
            "success": "rgba(120, 133, 102, 0.15)",
            "error": "rgba(179, 89, 89, 0.15)",
            "info": "rgba(106, 143, 167, 0.15)",
        }
        border_map = {
            "success": "rgba(120, 133, 102, 0.5)",
            "error": "rgba(179, 89, 89, 0.5)",
            "info": "rgba(106, 143, 167, 0.5)",
        }

        self.setStyleSheet(f"""
            ToastNotification {{
                background-color: {bg_map.get(toast_type, bg_map['info'])};
                border: 1px solid {border_map.get(toast_type, border_map['info'])};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=color).pixmap(18, 18))
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #E8E3DF; font-size: 13px; font-family: 'Inter', 'Segoe UI', sans-serif; background: transparent; border: none;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl, 1)

        if action_label and action_callback:
            action_btn = QPushButton(action_label)
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: #E8E3DF;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            def on_action_clicked():
                action_callback()
                self.dismiss()
                
            action_btn.clicked.connect(on_action_clicked)
            layout.addWidget(action_btn)

        close_btn = QPushButton()
        close_btn.setIcon(qta.icon("fa5s.times", color="#7A7470"))
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("background: transparent; border: none;")
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)

        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)
        self.dismiss_timer.start(4500)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(250)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_in.start()

    def dismiss(self):
        self.dismiss_timer.stop()
        fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        fade_out.setDuration(200)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade_out.finished.connect(self._on_fade_done)
        self._fade_out_anim = fade_out
        fade_out.start()

    def _on_fade_done(self):
        self.closed.emit()
        self.deleteLater()


class ToastManager:
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.toasts = []

    def show_toast(self, message, toast_type="success", action_label=None, action_callback=None):
        toast = ToastNotification(message, toast_type, self.parent, action_label, action_callback)
        toast.closed.connect(lambda t=toast: self._remove_toast(t))
        self.toasts.append(toast)
        toast.show()
        self._reposition()

    def _remove_toast(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        self._reposition()

    def _reposition(self):
        margin = 16
        bottom = self.parent.height() - 90
        for i, toast in enumerate(reversed(self.toasts)):
            toast.adjustSize()
            x = self.parent.width() - toast.width() - margin
            y = bottom - (i + 1) * (toast.height() + 8)
            toast.move(x, y)
            toast.raise_()


class EqualizerWidget(QWidget):
    def __init__(self, accent_color="#C47D63", parent=None, bar_count=7):
        super().__init__(parent)
        self.bar_count = bar_count
        self.bar_heights = [0.0] * bar_count
        self.target_heights = [0.0] * bar_count
        self.is_playing = False
        self.accent_color = accent_color
        self.setFixedSize(60, 36)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate)
        self.anim_timer.start(50)

        self._change_timer = QTimer(self)
        self._change_timer.timeout.connect(self._new_targets)
        self._change_timer.start(180)

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color
        self.update()

    def set_playing(self, playing):
        self.is_playing = playing
        if playing:
            if not self.anim_timer.isActive():
                self.anim_timer.start(50)
            if not self._change_timer.isActive():
                self._change_timer.start(180)
        else:
            self.target_heights = [0.0] * self.bar_count

    def _new_targets(self):
        if self.is_playing:
            self.target_heights = [random.uniform(0.2, 1.0) for _ in range(self.bar_count)]

    def _animate(self):
        changed = False
        for i in range(self.bar_count):
            diff = self.target_heights[i] - self.bar_heights[i]
            if abs(diff) > 0.01:
                self.bar_heights[i] += diff * 0.35
                changed = True
            else:
                self.bar_heights[i] = self.target_heights[i]
        if changed:
            self.update()
        elif not self.is_playing:
            self.anim_timer.stop()
            self._change_timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_w = max(3, (w - (self.bar_count - 1) * 2) // self.bar_count)
        spacing = 2

        for i in range(self.bar_count):
            bar_h = max(2, int(self.bar_heights[i] * (h - 4)))
            x = i * (bar_w + spacing)
            y = h - bar_h - 2

            grad = QLinearGradient(x, y, x, h - 2)
            grad.setColorAt(0.0, QColor(self.accent_color).lighter(120))
            grad.setColorAt(1.0, QColor(self.accent_color))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(x, y, bar_w, bar_h, 1, 1)


class LoudnessMeterWidget(QWidget):
    """
    Dual LED Loudness & Peak dBFS Meter with clipping warning.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_db = -12.0
        self.mean_db = -18.0
        self.setFixedSize(84, 30)
        self.setToolTip("Auto-Gain Loudness & Peak dBFS Analyzer")

    def set_loudness(self, max_db: float, mean_db: float):
        self.max_db = max_db
        self.mean_db = mean_db
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        is_clipping = self.max_db >= 0.0

        bg_color = QColor("rgba(179, 89, 89, 0.25)") if is_clipping else QColor("#181716")
        border_color = QColor("#B35959") if is_clipping else QColor("#2E2C2B")

        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(rect, 4, 4)

        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)

        if is_clipping:
            painter.setPen(QColor("#FF4D4D"))
            txt = f"⚠️ CLIP {self.max_db:+.1f}dB"
        else:
            painter.setPen(QColor("#00E676") if self.max_db < -1.0 else QColor("#FFD600"))
            txt = f"{self.max_db:+.1f} dBFS"

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)


class NowPlayingIndicator(QWidget):
    def __init__(self, accent_color="#C47D63", parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 14)
        self.accent_color = accent_color
        self.bars = [0.3, 0.6, 0.4]
        self.targets = [0.3, 0.6, 0.4]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(80)

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color
        self.update()

    def _animate(self):
        self.targets = [random.uniform(0.2, 1.0) for _ in range(3)]
        for i in range(3):
            self.bars[i] += (self.targets[i] - self.bars[i]) * 0.4
        self.update()

    def showEvent(self, event):
        if not self.timer.isActive():
            self.timer.start(80)
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.accent_color))
        h = self.height()
        for i, val in enumerate(self.bars):
            bh = max(2, int(val * (h - 2)))
            painter.drawRoundedRect(i * 5 + 1, h - bh, 3, bh, 1, 1)


class SearchResultCard(QWidget):
    download_requested = pyqtSignal(str, str, int, str)

    def __init__(self, result, default_format='MP3', parent=None):
        super().__init__(parent)
        self.result = result
        self.default_format = default_format
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setup_ui()

    def enterEvent(self, event):
        self.setStyleSheet("SearchResultCard { background-color: #282423; border-radius: 8px; }")
        if hasattr(self, 'thumb_overlay'):
            self.thumb_overlay.show()
        if hasattr(self, 'thumb_label') and hasattr(self.thumb_label, 'zoom_in'):
            self.thumb_label.zoom_in()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("")
        if hasattr(self, 'thumb_overlay'):
            self.thumb_overlay.hide()
        if hasattr(self, 'thumb_label') and hasattr(self.thumb_label, 'zoom_out'):
            self.thumb_label.zoom_out()
        super().leaveEvent(event)

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        self.thumb_container = QWidget()
        self.thumb_container.setFixedSize(88, 50)
        thumb_layout = QGridLayout(self.thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        
        self.thumb_label = ZoomingThumbnail()
        self.thumb_label.setFixedSize(88, 50)
        self.thumb_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.thumb_label.setStyleSheet("background-color: #141424; border-radius: 4px;")
        self.thumb_label.set_pixmap(qta.icon("fa5s.music", color="#7A7470").pixmap(24, 24))
        
        self.thumb_overlay = QLabel()
        self.thumb_overlay.setFixedSize(88, 50)
        self.thumb_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 150); border-radius: 4px;")
        self.thumb_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_overlay.setPixmap(qta.icon("fa5s.play", color="#ffffff").pixmap(20, 20))
        self.thumb_overlay.hide()
        
        thumb_layout.addWidget(self.thumb_label, 0, 0)
        thumb_layout.addWidget(self.thumb_overlay, 0, 0)
        layout.addWidget(self.thumb_container)

        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self.result['title'])
        self.title_label.setObjectName("result-title")
        self.title_label.setWordWrap(True)
        details_layout.addWidget(self.title_label)

        source = self.result.get('source', 'YouTube')
        source_icon = '▶' if source == 'YouTube' else '☁' if source == 'SoundCloud' else '♫'
        self.meta_label = QLabel(f"{source_icon} {source}  ·  {self.result['artist']}  ·  {self.result['duration']}")
        self.meta_label.setObjectName("result-meta")
        details_layout.addWidget(self.meta_label)

        layout.addLayout(details_layout, 1)

        self.actions_container = QStackedWidget()
        self.actions_container.setFixedWidth(140)

        dl_actions_widget = QWidget()
        dl_actions_layout = QVBoxLayout(dl_actions_widget)
        dl_actions_layout.setContentsMargins(0, 0, 0, 0)
        dl_actions_layout.setSpacing(4)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(['MP3', 'WAV', 'FLAC', 'AAC', 'OGG', 'M4A', 'MP4 (Video)'])
        self.format_combo.setFixedHeight(22)
        self.format_combo.setStyleSheet("QComboBox { background-color: #2F2B2A; border: 1px solid #3F3B3A; border-radius: 4px; color: #A39E9A; font-size: 10px; } QComboBox::drop-down { border: none; }")
        idx = self.format_combo.findText(self.default_format, Qt.MatchFlag.MatchStartsWith)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

        self.dl_btn = QPushButton(" Download")
        self.dl_btn.setIcon(qta.icon("fa5s.download", color="#E8E3DF"))
        self.dl_btn.setObjectName("download-btn")
        self.dl_btn.clicked.connect(self.on_download_clicked)
        
        dl_actions_layout.addWidget(self.format_combo)
        dl_actions_layout.addWidget(self.dl_btn)

        self.progress_widget = QWidget()
        prog_layout = QVBoxLayout(self.progress_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(4)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(8)

        self.prog_label = QLabel("0%")
        self.prog_label.setObjectName("progress-percent-label")
        self.prog_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prog_layout.addWidget(self.prog_bar)
        prog_layout.addWidget(self.prog_label)

        self.in_lib_label = QWidget()
        in_lib_layout = QHBoxLayout(self.in_lib_label)
        in_lib_layout.setContentsMargins(8, 4, 8, 4)
        in_lib_layout.setSpacing(6)
        in_lib_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        in_lib_icon = QLabel()
        in_lib_icon.setPixmap(qta.icon("fa5s.check-circle", color="#788566").pixmap(14, 14))
        in_lib_text = QLabel("IN LIBRARY")
        in_lib_text.setObjectName("in-library-text")
        in_lib_layout.addWidget(in_lib_icon)
        in_lib_layout.addWidget(in_lib_text)
        self.in_lib_label.setObjectName("in-library-badge")

        self.queued_label = QWidget()
        queued_layout = QHBoxLayout(self.queued_label)
        queued_layout.setContentsMargins(8, 4, 8, 4)
        queued_layout.setSpacing(6)
        queued_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queued_icon = QLabel()
        queued_icon.setPixmap(qta.icon("fa5s.clock", color="#A39E9A").pixmap(14, 14))
        queued_text = QLabel("QUEUED")
        queued_text.setObjectName("queued-text")
        queued_layout.addWidget(queued_icon)
        queued_layout.addWidget(queued_text)
        self.queued_label.setObjectName("queued-badge")

        self.actions_container.addWidget(dl_actions_widget)
        self.actions_container.addWidget(self.progress_widget)
        self.actions_container.addWidget(self.in_lib_label)
        self.actions_container.addWidget(self.queued_label)

        self.copy_btn = QPushButton()
        self.copy_btn.setIcon(qta.icon("fa5s.clipboard", color="#A39E9A"))
        self.copy_btn.setFixedSize(30, 30)
        self.copy_btn.setToolTip("Copy URL")
        self.copy_btn.setProperty("class", "icon-btn")
        self.copy_btn.clicked.connect(self.on_copy_clicked)

        self.browser_btn = QPushButton()
        self.browser_btn.setIcon(qta.icon("fa5s.external-link-alt", color="#A39E9A"))
        self.browser_btn.setFixedSize(30, 30)
        self.browser_btn.setToolTip("Open in Browser")
        self.browser_btn.setProperty("class", "icon-btn")
        self.browser_btn.clicked.connect(self.on_browser_clicked)

        layout.addWidget(self.copy_btn)
        layout.addWidget(self.browser_btn)
        layout.addWidget(self.actions_container)

    def on_copy_clicked(self):
        QApplication.clipboard().setText(self.result['url'])
        
    def on_browser_clicked(self):
        QDesktopServices.openUrl(QUrl(self.result['url']))

    def set_thumbnail(self, path):
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            if hasattr(self.thumb_label, 'set_pixmap'):
                self.thumb_label.set_pixmap(scaled)
            else:
                self.thumb_label.setPixmap(scaled)

    def on_download_clicked(self):
        fmt = self.format_combo.currentText().split(' ')[0].lower()
        self.download_requested.emit(self.result['url'], self.result['title'], self.result.get('durationSecs', 0), fmt)

    def set_downloading(self):
        self.actions_container.setCurrentIndex(1)
        self.prog_bar.setRange(0, 0)
        self.prog_label.setText("Starting...")

    def update_progress(self, val, speed="", eta=""):
        if self.prog_bar.maximum() == 0:
            self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(int(val))
        if speed and eta:
            self.prog_label.setText(f"{int(val)}% ({speed} · ETA {eta})")
        elif speed:
            self.prog_label.setText(f"{int(val)}% ({speed})")
        else:
            self.prog_label.setText(f"{int(val)}%")

    def set_in_library(self):
        self.actions_container.setCurrentIndex(2)

    def set_available(self):
        self.actions_container.setCurrentIndex(0)

    def set_queued(self):
        self.actions_container.setCurrentIndex(3)


class StarRatingWidget(QWidget):
    rating_changed = pyqtSignal(int)
    
    def __init__(self, rating=0, parent=None):
        super().__init__(parent)
        self.rating = rating
        self.hover_rating = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.stars = []
        for i in range(1, 6):
            lbl = ClickableLabel("☆")
            lbl.setStyleSheet("color: #5C544D; font-size: 14px; font-weight: bold;")
            lbl.clicked.connect(lambda _, r=i: self._set_rating(r))
            lbl.setMouseTracking(True)
            self.stars.append(lbl)
            layout.addWidget(lbl)
        self.setMouseTracking(True)
        self._update_stars()

    def _set_rating(self, r):
        self.rating = r
        self.rating_changed.emit(self.rating)
        self._update_stars()

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        w = self.width()
        self.hover_rating = max(1, min(5, int((x / max(1, w)) * 5) + 1))
        self._update_stars(self.hover_rating)
        
    def leaveEvent(self, event):
        self.hover_rating = 0
        self._update_stars()

    def _update_stars(self, display_rating=None):
        val = display_rating if display_rating is not None else self.rating
        for i, lbl in enumerate(self.stars):
            if i < val:
                lbl.setText("★")
                lbl.setStyleSheet("color: #EDC948; font-size: 14px; font-weight: bold;")
            else:
                lbl.setText("☆")
                lbl.setStyleSheet("color: #5C544D; font-size: 14px; font-weight: bold;")


class LibraryHeaderWidget(QWidget):
    """Sortable Column Header Row for Library List"""
    sort_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("""
            LibraryHeaderWidget {
                background-color: #1A1A1A;
                border-bottom: 1px solid #2A2A2A;
                border-radius: 4px;
            }
            QPushButton.hdrBtn {
                background: transparent;
                border: none;
                color: #8A8580;
                font-size: 11px;
                font-weight: 700;
                text-align: left;
                padding-left: 4px;
            }
            QPushButton.hdrBtn:hover {
                color: #FFFFFF;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        handle_space = QLabel()
        handle_space.setFixedWidth(24)
        layout.addWidget(handle_space)

        btn_title = QPushButton("TRACK TITLE")
        btn_title.setProperty("class", "hdrBtn")
        btn_title.clicked.connect(lambda: self.sort_requested.emit("Title"))
        layout.addWidget(btn_title, 1)

        btn_artist = QPushButton("ARTIST")
        btn_artist.setProperty("class", "hdrBtn")
        btn_artist.setFixedWidth(130)
        btn_artist.clicked.connect(lambda: self.sort_requested.emit("Artist"))
        layout.addWidget(btn_artist)

        btn_bpm = QPushButton("BPM")
        btn_bpm.setProperty("class", "hdrBtn")
        btn_bpm.setFixedWidth(64)
        btn_bpm.clicked.connect(lambda: self.sort_requested.emit("BPM"))
        layout.addWidget(btn_bpm)

        btn_key = QPushButton("KEY")
        btn_key.setProperty("class", "hdrBtn")
        btn_key.setFixedWidth(48)
        btn_key.clicked.connect(lambda: self.sort_requested.emit("Key"))
        layout.addWidget(btn_key)

        btn_dur = QPushButton("TIME")
        btn_dur.setProperty("class", "hdrBtn")
        btn_dur.setFixedWidth(50)
        btn_dur.clicked.connect(lambda: self.sort_requested.emit("Duration"))
        layout.addWidget(btn_dur)

        btn_fmt = QPushButton("FMT")
        btn_fmt.setProperty("class", "hdrBtn")
        btn_fmt.setFixedWidth(48)
        layout.addWidget(btn_fmt)

        btn_rating = QPushButton("RATING")
        btn_rating.setProperty("class", "hdrBtn")
        btn_rating.setFixedWidth(80)
        btn_rating.clicked.connect(lambda: self.sort_requested.emit("Rating"))
        layout.addWidget(btn_rating)

        btn_size = QPushButton("SIZE")
        btn_size.setProperty("class", "hdrBtn")
        btn_size.setFixedWidth(60)
        btn_size.clicked.connect(lambda: self.sort_requested.emit("Size"))
        layout.addWidget(btn_size)

        menu_space = QLabel()
        menu_space.setFixedWidth(28)
        layout.addWidget(menu_space)


class LibraryTrackRow(QWidget):
    rating_changed = pyqtSignal(str, int)
    
    def __init__(self, parent_list, track, list_item, is_playing=False, is_missing=False, is_duplicate=False, match_info=None, accent_color="#C47D63"):
        super().__init__()
        self.parent_list = parent_list
        self.track = track
        self.list_item = list_item
        self.drag_start_position = QPoint()
        self.is_playing = is_playing
        self.is_missing = is_missing
        self.is_duplicate = is_duplicate
        self.match_info = match_info
        self.accent_color = accent_color
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        if self.is_missing:
            warn = QLabel()
            warn.setPixmap(qta.icon("fa5s.exclamation-triangle", color="#B35959").pixmap(14, 14))
            warn.setToolTip("File not found on disk")
            warn.setFixedWidth(24)
            layout.addWidget(warn)
        elif self.is_playing:
            self.indicator = NowPlayingIndicator(accent_color=self.accent_color)
            self.indicator.setFixedWidth(24)
            layout.addWidget(self.indicator)
        else:
            self.handle_label = QLabel("⠿")
            self.handle_label.setObjectName("track-drag-handle")
            self.handle_label.setFixedWidth(24)
            layout.addWidget(self.handle_label)

        if self.is_duplicate:
            dup_icon = QLabel()
            dup_icon.setPixmap(qta.icon("fa5s.copy", color=self.accent_color).pixmap(12, 12))
            dup_icon.setToolTip("Duplicate title detected in library")
            dup_icon.setFixedWidth(16)
            layout.addWidget(dup_icon)

        # DJ Match Badge — expanded with key + BPM inline
        if self.match_info and self.match_info.get('score', 0) > 0:
            score = self.match_info['score']
            quality = self.match_info.get('quality', '')

            if score >= 85:
                badge_color = "#00E676"
                bg_color = "rgba(0, 230, 118, 0.15)"
            elif score >= 60:
                badge_color = "#FFD600"
                bg_color = "rgba(255, 214, 0, 0.12)"
            else:
                badge_color = "#A0A0A0"
                bg_color = "rgba(160, 160, 160, 0.10)"

            # Build rich badge text: ⚡ 92% · 8A→8B · 128
            parts = [f"\u26a1 {score}%"]
            src_key = self.match_info.get('source_key', '')
            tgt_key = self.match_info.get('target_key', '')
            if src_key and tgt_key:
                parts.append(f"{src_key}\u2192{tgt_key}")
            elif tgt_key:
                parts.append(tgt_key)
            tgt_bpm = self.match_info.get('target_bpm', '')
            if tgt_bpm:
                parts.append(tgt_bpm)
            badge_text = " \u00b7 ".join(parts)

            match_btn = QLabel(badge_text)
            match_btn.setStyleSheet(f"color: {badge_color}; background-color: {bg_color}; border: 1px solid {badge_color}; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 800;")
            tooltip = f"{quality}\n{self.match_info.get('key_label', '')} \u00b7 {self.match_info.get('bpm_label', '')}"
            match_btn.setToolTip(tooltip.strip())
            layout.addWidget(match_btn)

        # Title
        self.title_label = QLabel(self.track['title'])
        if self.is_missing:
            self.title_label.setObjectName("track-row-title-missing")
        elif self.is_playing:
            self.title_label.setObjectName("track-row-title-playing")
        else:
            self.title_label.setObjectName("track-row-title")
        self.title_label.setToolTip(self.track['path'])
        layout.addWidget(self.title_label, 1)

        # Artist
        artist = self.track.get('artist', 'Unknown Artist')
        self.artist_label = QLabel(artist)
        self.artist_label.setStyleSheet("color: #8A8580; font-size: 12px; font-weight: 500;")
        self.artist_label.setFixedWidth(130)
        layout.addWidget(self.artist_label)

        # BPM
        bpm = self.track.get('bpm', '')
        bpm_str = f"{bpm} BPM" if bpm else "—"
        bpm_lbl = QLabel(bpm_str)
        bpm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bpm_lbl.setFixedWidth(64)
        if bpm:
            bpm_lbl.setStyleSheet(f"color: {self.accent_color}; background-color: rgba(196, 125, 99, 0.12); border: 1px solid rgba(196, 125, 99, 0.25); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        else:
            bpm_lbl.setStyleSheet("color: #5C544D; font-size: 11px;")
        layout.addWidget(bpm_lbl)

        # Key
        key = self.track.get('key', '')
        key_str = key if key else "—"
        key_lbl = QLabel(key_str)
        key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        key_lbl.setFixedWidth(48)
        if key:
            key_lbl.setStyleSheet("color: #00E5FF; background-color: rgba(0, 229, 255, 0.12); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        else:
            key_lbl.setStyleSheet("color: #5C544D; font-size: 11px;")
        layout.addWidget(key_lbl)

        # Duration
        dur_str = self.track.get('duration_str', '—')
        self.dur_label = QLabel(dur_str)
        self.dur_label.setObjectName("track-row-duration")
        self.dur_label.setFixedWidth(50)
        self.dur_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.dur_label)

        # Format Badge
        self.fmt_badge = QLabel(self.track['format'].upper())
        self.fmt_badge.setFixedWidth(48)
        self.fmt_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmt = self.track['format'].lower()
        if fmt == 'mp3':
            self.fmt_badge.setStyleSheet("color: #6A8FA7; background-color: rgba(106, 143, 167, 0.1); border: 1px solid rgba(106, 143, 167, 0.2); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        elif fmt == 'wav':
            self.fmt_badge.setStyleSheet("color: #B35959; background-color: rgba(179, 89, 89, 0.1); border: 1px solid rgba(179, 89, 89, 0.2); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        elif fmt == 'flac':
            self.fmt_badge.setStyleSheet("color: #9B7AC4; background-color: rgba(155, 122, 196, 0.1); border: 1px solid rgba(155, 122, 196, 0.2); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        else:
            self.fmt_badge.setStyleSheet("color: #8a8a9d; background-color: rgba(138, 138, 157, 0.08); border: 1px solid rgba(138, 138, 157, 0.15); border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: 700;")
        layout.addWidget(self.fmt_badge)

        # Rating
        self.star_widget = StarRatingWidget(self.track.get('rating', 0))
        self.star_widget.setFixedWidth(80)
        self.star_widget.rating_changed.connect(lambda r: self.rating_changed.emit(self.track['path'], r))
        layout.addWidget(self.star_widget)

        # Size
        self.size_label = QLabel(self.fmt_size(self.track.get('size', 0)))
        self.size_label.setObjectName("track-row-size")
        self.size_label.setFixedWidth(60)
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.size_label)

        # Menu Button
        self.menu_btn = QPushButton("⋯")
        self.menu_btn.setObjectName("track-menu-btn")
        self.menu_btn.setFixedSize(28, 28)
        self.menu_btn.clicked.connect(self.show_track_menu)
        layout.addWidget(self.menu_btn)

    def fmt_size(self, bytes_val):
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.0f} KB"
        else:
            return f"{bytes_val / (1024 * 1024):.1f} MB"

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self.drag_start_position).manhattanLength() > QApplication.startDragDistance():
                selected_items = self.parent_list.selectedItems()
                paths = []
                for item in selected_items:
                    t = item.data(Qt.ItemDataRole.UserRole)
                    if t and t.get('path') and os.path.exists(t['path']):
                        paths.append(t['path'])
                if not paths and self.track.get('path') and os.path.exists(self.track['path']):
                    paths = [self.track['path']]
                if paths:
                    self.parent_list.initiate_drag(paths)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_list.on_item_double_clicked(self.list_item)
        super().mouseDoubleClickEvent(event)

    def show_track_menu(self):
        self.parent_list.show_menu_for_track(self.track, self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height())))


class DraggableTrackList(QListWidget):
    menu_requested = pyqtSignal(dict, QPoint)
    double_clicked_track = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.itemDoubleClicked.connect(self.on_item_double_clicked)

    def initiate_drag(self, track_paths):
        if isinstance(track_paths, str):
            track_paths = [track_paths]
        urls = [QUrl.fromLocalFile(p) for p in track_paths if p and os.path.exists(p)]
        if not urls:
            return
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls(urls)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)

    def on_item_double_clicked(self, item):
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.double_clicked_track.emit(track)

    def show_menu_for_track(self, track, pos):
        self.menu_requested.emit(track, pos)


class DroppableCrateTab(QPushButton):
    track_dropped = pyqtSignal(str, str)

    def __init__(self, crate_name, text, parent=None):
        super().__init__(text, parent)
        self.crate_name = crate_name
        self.setAcceptDrops(True)
        self._drag_over = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_over = True
            self.setProperty("drag-over", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self._drag_over = False
        self.setProperty("drag-over", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self._drag_over = False
        self.setProperty("drag-over", False)
        self.style().unpolish(self)
        self.style().polish(self)

        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.exists(path):
                self.track_dropped.emit(self.crate_name, path)
        event.acceptProposedAction()


class QueueItemRow(QWidget):
    cancel_requested = pyqtSignal(str)
    retry_requested  = pyqtSignal(str, str)
    view_log_requested = pyqtSignal(str)

    def __init__(self, item_data, accent_color="#C47D63", parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.accent_color = accent_color
        self.setup_ui()

    def setup_ui(self):
        status = self.item_data.get('status', 'queued')

        border_colors = {
            'queued':      '#5C544D',
            'downloading': self.accent_color,
            'completed':   '#788566',
            'failed':      '#B35959',
            'cancelled':   '#3B3633',
        }
        border_color = border_colors.get(status, '#5C544D')
        self.setStyleSheet(f"""
            QueueItemRow {{
                border-left: 3px solid {border_color};
                border-radius: 0px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        icon_map = {
            'queued':      ("fa5s.clock",             "#A39E9A"),
            'downloading': ("fa5s.arrow-down",        self.accent_color),
            'completed':   ("fa5s.check-circle",      "#788566"),
            'failed':      ("fa5s.exclamation-circle","#B35959"),
            'cancelled':   ("fa5s.ban",               "#7A7470"),
        }
        icon_name, icon_color = icon_map.get(status, icon_map['queued'])
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(16, 16))
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(self.item_data.get('title', 'Unknown'))
        title_lbl.setObjectName("queue-item-title")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl, 1)

        if status == 'downloading':
            pct = self.item_data.get('progress', 0)
            prog = QProgressBar()
            prog.setRange(0, 100)
            prog.setValue(int(pct))
            prog.setFixedSize(100, 8)
            layout.addWidget(prog)

            pct_lbl = QLabel(f"{int(pct)}%")
            pct_lbl.setObjectName("queue-item-pct")
            pct_lbl.setFixedWidth(40)
            layout.addWidget(pct_lbl)
        else:
            status_text = {
                'queued':    'Waiting...',
                'completed': 'Done',
                'failed':    'Failed',
                'cancelled': 'Cancelled',
            }
            s_lbl = QLabel(status_text.get(status, ''))
            s_lbl.setObjectName("queue-item-status")
            s_lbl.setFixedWidth(80)
            layout.addWidget(s_lbl)

        if status in ('queued', 'downloading'):
            cancel_btn = QPushButton()
            cancel_btn.setIcon(qta.icon("fa5s.times", color="#B35959"))
            cancel_btn.setFixedSize(24, 24)
            cancel_btn.setObjectName("queue-cancel-btn")
            cancel_btn.setToolTip("Cancel")
            cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.item_data.get('url', '')))
            layout.addWidget(cancel_btn)
        elif status == 'failed':
            retry_btn = QPushButton()
            retry_btn.setIcon(qta.icon("fa5s.redo", color=self.accent_color))
            retry_btn.setFixedSize(24, 24)
            retry_btn.setObjectName("queue-retry-btn")
            retry_btn.setToolTip("Retry download")
            retry_btn.clicked.connect(lambda: self.retry_requested.emit(
                self.item_data.get('url', ''), self.item_data.get('title', '')
            ))
            layout.addWidget(retry_btn)

        log_btn = QPushButton()
        log_btn.setIcon(qta.icon("fa5s.terminal", color="#A39E9A"))
        log_btn.setFixedSize(24, 24)
        log_btn.setObjectName("queue-log-btn")
        log_btn.setToolTip("View Log")
        log_btn.clicked.connect(lambda: self.view_log_requested.emit(self.item_data.get('url', '')))
        layout.addWidget(log_btn)


class HistoryItemRow(QWidget):
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        if self.entry.get('status') == 'completed':
            icon_lbl = QLabel()
            icon_lbl.setPixmap(qta.icon("fa5s.check-circle", color="#788566").pixmap(16, 16))
        else:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(qta.icon("fa5s.exclamation-circle", color="#B35959").pixmap(16, 16))
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        info_layout.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(self.entry.get('title', 'Unknown'))
        title_lbl.setObjectName("history-item-title")
        title_lbl.setWordWrap(True)
        info_layout.addWidget(title_lbl)

        date_lbl = QLabel(self.entry.get('date', ''))
        date_lbl.setObjectName("history-item-date")
        info_layout.addWidget(date_lbl)

        layout.addLayout(info_layout, 1)

        fmt = self.entry.get('format', '').upper()
        if fmt:
            fmt_lbl = QLabel(fmt)
            fmt_lbl.setObjectName("history-item-fmt")
            fmt_lbl.setStyleSheet("color: #A39E9A; background-color: rgba(163, 158, 154, 0.1); border: 1px solid rgba(163, 158, 154, 0.2); border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 700; font-family: 'Inter', sans-serif;")
            layout.addWidget(fmt_lbl)


class TitleBar(QWidget):
    def __init__(self, parent=None, accent_color="#C47D63"):
        super().__init__(parent)
        self.parent = parent
        self.accent_color = accent_color
        self.is_moving = False
        self.drag_position = QPoint()
        self.setup_ui()

    def set_accent_color(self, hex_color):
        self.accent_color = hex_color
        if hasattr(self, 'logo'):
            self.logo.setPixmap(qta.icon("fa5s.compact-disc", color=self.accent_color).pixmap(20, 20))

    def setup_ui(self):
        self.setObjectName("titlebar")
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        left_layout = QHBoxLayout()
        left_layout.setSpacing(8)

        self.logo = QLabel()
        self.logo.setPixmap(qta.icon("fa5s.compact-disc", color=self.accent_color).pixmap(20, 20))

        app_name = QLabel("DJ Crate")
        app_name.setStyleSheet("color: #ffffff; font-weight: 800; font-size: 14px; font-family: 'Inter', 'Segoe UI';")

        from djcrate import __version__
        app_version = QLabel(f"v{__version__}")
        app_version.setStyleSheet("color: #5C544D; font-weight: 600; font-size: 11px;")

        left_layout.addWidget(self.logo)
        left_layout.addWidget(app_name)
        left_layout.addWidget(app_version)

        layout.addLayout(left_layout)
        layout.addStretch()

        right_layout = QHBoxLayout()
        right_layout.setSpacing(4)

        self.min_btn = QPushButton()
        self.min_btn.setIcon(qta.icon("fa5s.minus", color="#A39E9A"))
        self.min_btn.setObjectName("win-btn")
        self.min_btn.setFixedSize(28, 28)
        self.min_btn.clicked.connect(self.parent.showMinimized)

        self.max_btn = QPushButton()
        self.max_btn.setIcon(qta.icon("fa5s.square", color="#A39E9A"))
        self.max_btn.setObjectName("win-btn")
        self.max_btn.setFixedSize(28, 28)
        self.max_btn.clicked.connect(self.toggle_max)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(qta.icon("fa5s.times", color="#A39E9A"))
        self.close_btn.setObjectName("win-btn-close")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.clicked.connect(self.parent.close)

        right_layout.addWidget(self.min_btn)
        right_layout.addWidget(self.max_btn)
        right_layout.addWidget(self.close_btn)

        layout.addLayout(right_layout)

    def toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setIcon(qta.icon("fa5s.square", color="#A39E9A"))
        else:
            self.parent.showMaximized()
            self.max_btn.setIcon(qta.icon("fa5s.clone", color="#A39E9A"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_moving = True
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_moving and event.buttons() == Qt.MouseButton.LeftButton:
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_max()
            event.accept()


class ZoomingThumbnail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scale = 1.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(200)
        self.anim.valueChanged.connect(self.set_scale)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_scale(self, scale):
        self._scale = scale
        self.update()

    def paintEvent(self, event):
        if not self._pixmap:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        cw, ch = self.width(), self.height()
        pw = int(cw * self._scale)
        ph = int(ch * self._scale)
        x = (cw - pw) // 2
        y = (ch - ph) // 2
        
        painter.drawPixmap(QRect(x, y, pw, ph), self._pixmap)

    def zoom_in(self):
        self.anim.setStartValue(self._scale)
        self.anim.setEndValue(1.15)
        self.anim.start()

    def zoom_out(self):
        self.anim.setStartValue(self._scale)
        self.anim.setEndValue(1.0)
        self.anim.start()

class FadingStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_duration = 180
        self.fade_anim = None
        self.overlay_label = QLabel(self)
        self.overlay_label.hide()
        self.overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def setCurrentIndex(self, index):
        if index == self.currentIndex():
            return
            
        current_widget = self.currentWidget()
        if current_widget:
            # Grab current widget as pixmap
            pix = current_widget.grab()
            self.overlay_label.setPixmap(pix)
            self.overlay_label.resize(self.size())
            self.overlay_label.show()
            self.overlay_label.raise_()
            
            # Switch to new widget immediately
            super().setCurrentIndex(index)
            
            # Fade out the overlay
            effect = QGraphicsOpacityEffect(self.overlay_label)
            self.overlay_label.setGraphicsEffect(effect)
            
            self.fade_anim = QPropertyAnimation(effect, b'opacity')
            self.fade_anim.setDuration(self._fade_duration)
            self.fade_anim.setStartValue(1.0)
            self.fade_anim.setEndValue(0.0)
            self.fade_anim.finished.connect(self.overlay_label.hide)
            self.fade_anim.start()
        else:
            super().setCurrentIndex(index)
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay_label.resize(self.size())
