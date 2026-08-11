import os
import sys
import json
import glob
import time
import math
import random
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QProgressBar, QSlider,
    QComboBox, QFileDialog, QFrame, QStackedWidget, QScrollArea, QMenu,
    QMessageBox, QSizeGrip, QInputDialog, QSpinBox, QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect, QCheckBox, QSystemTrayIcon, QButtonGroup,
    QGridLayout, QSizePolicy, QDialog, QApplication
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QPoint, QSize, QUrl, QMimeData, QTimer,
    QPropertyAnimation, QSequentialAnimationGroup, QParallelAnimationGroup,
    QEasingCurve, QRect, QEvent
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QDrag, QColor, QPainter, QAction, QPen, QKeySequence,
    QShortcut, QBrush, QLinearGradient, QDesktopServices
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import qtawesome as qta

from djcrate.logger import logger
from djcrate.config import SettingsManager
from djcrate.utils import check_dependency, show_dependency_warning, extract_file_audio_metadata, CamelotMatcher
from djcrate.ui.theme import ThemeEngine
from djcrate.ui.widgets import (
    PlayerSlider, VolumeSlider, ClickableLabel, LoadingSpinner,
    ToastNotification, ToastManager, EqualizerWidget, NowPlayingIndicator,
    LoudnessMeterWidget, SearchResultCard, StarRatingWidget, LibraryTrackRow, LibraryHeaderWidget,
    DraggableTrackList, DroppableCrateTab, QueueItemRow, HistoryItemRow, TitleBar, FadingStackedWidget
)
from djcrate.ui.dialogs import SmartCrateDialog, LogDialog, MetadataEditorDialog, BulkMetadataEditorDialog, MixSplitterDialog
from djcrate.ui.mini_player import MiniPlayerWindow
from djcrate.workers import (
    SearchThread, ThumbnailDownloader, DownloadThread,
    MetadataProbeThread, AnalysisThread, AutoTagThread, WaveformGeneratorThread, MixSplitterThread
)
from djcrate.updater import AutoUpdaterThread
from djcrate.serato import SeratoCrateWriter
from djcrate.obs_overlay import ObsOverlayWriter
from djcrate.ui.clipboard_widget import ClipboardGrabberWidget, _derive_title_from_url
from djcrate.ui.gig_matcher_widget import GigMatcherWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.thumbnail_loaders = {}
        self.search_cards = {}
        self.active_downloads = {}
        self.library_tracks = []
        self.filtered_tracks = []
        self.active_crate = None
        self.duration_cache = {}
        self.artist_cache = {}
        self.search_results = []
        self._running_threads = []
        self._queue_rows: dict = {}  # url -> QueueItemRow; for in-place progress updates
        self._sidebar_collapsed = False
        self.gig_matcher = None

        self.clipboard_grabber = ClipboardGrabberWidget(accent_color=self.settings_manager.get('accentColor', '#FF5500'))
        self.clipboard_grabber.download_requested.connect(self.quick_download_url)
        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.timeout.connect(self.clipboard_grabber.check_clipboard)
        self._clipboard_timer.start(1500)

        self.download_queue = []
        self.download_threads = {}

        self.shuffle_enabled = False
        self.loop_mode = 0

        self._is_muted = False
        self._pre_mute_volume = 80

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.player_track = None
        self.slider_pressed = False
        self._manual_stop = False

        self._disc_angle = 0
        self._disc_timer = QTimer(self)
        self._disc_timer.timeout.connect(self._rotate_disc)
        self._disc_timer.setInterval(40)

        self._play_glow = QGraphicsDropShadowEffect()
        self._play_glow.setColor(QColor(self.settings_manager.get('accentColor', '#FF5500')))
        self._play_glow.setOffset(0, 0)
        self._play_glow.setBlurRadius(0)

        _glow_fwd = QPropertyAnimation(self._play_glow, b"blurRadius")
        _glow_fwd.setDuration(900)
        _glow_fwd.setStartValue(3)
        _glow_fwd.setEndValue(22)
        _glow_fwd.setEasingCurve(QEasingCurve.Type.InOutSine)

        _glow_back = QPropertyAnimation(self._play_glow, b"blurRadius")
        _glow_back.setDuration(900)
        _glow_back.setStartValue(22)
        _glow_back.setEndValue(3)
        _glow_back.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._glow_seq = QSequentialAnimationGroup(self)
        self._glow_seq.addAnimation(_glow_fwd)
        self._glow_seq.addAnimation(_glow_back)
        self._glow_seq.setLoopCount(-1)

        self._last_clipboard_url = ""

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(500)
        self._search_debounce_timer.timeout.connect(self.perform_search)

        self.sleep_timer = QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.timeout.connect(self.on_sleep_timer_fired)
        if self.settings_manager.get('sleepTimerMinutes', 0) > 0:
            self.sleep_timer.start(self.settings_manager.get('sleepTimerMinutes', 0) * 60 * 1000)

        self.lib_search_text = ""
        self.lib_sort_field = "modified"
        self.lib_sort_ascending = False
        self.lib_format_filters = set()
        self._queue_render_pending = False
        self._analysis_in_progress = False

        self.mini_player = None

        self.setup_ui()
        QTimer.singleShot(600, self.load_trending_tracks)
        self.setup_connections()
        self.setup_shortcuts()
        self._restore_geometry()
        self.apply_theme()
        self._render_crate_tabs()
        
        if self.settings_manager.get('alwaysOnTop', False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.show()

        QTimer.singleShot(200, self.refresh_library)

        saved_volume = self.settings_manager.get('volume', 80)
        self.volume_slider.setValue(int(saved_volume))
        self.audio_output.setVolume(int(saved_volume) / 100.0)
        
        opacity = self.settings_manager.get('windowOpacity', 100)
        self.setWindowOpacity(opacity / 100.0)

        QTimer.singleShot(2500, self._check_for_updates)

    def apply_theme(self):
        accent = self.settings_manager.get('accentColor', '#FF5500')
        theme = self.settings_manager.get('theme', 'Dark')
        qss = ThemeEngine.generate_qss(accent, theme)
        self.setStyleSheet(qss)
        self._play_glow.setColor(QColor(accent))
        if hasattr(self, 'title_bar'):
            self.title_bar.set_accent_color(accent)
        if hasattr(self, 'equalizer'):
            self.equalizer.set_accent_color(accent)
        if hasattr(self, 'seek_slider'):
            self.seek_slider.set_accent_color(accent)

    def _check_for_updates(self):
        self.updater_thread = AutoUpdaterThread(repo_owner="Dyvorn", repo_name="djcrate", parent=self)
        self.updater_thread.update_available.connect(self._on_update_available)
        self.updater_thread.start()

    def _on_update_available(self, version, notes, url):
        reply = QMessageBox.question(
            self,
            "Update Available",
            f"A new version of DJ Crate ({version}) is available!\n\nWould you like to open the download page?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(url))

    def setup_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1120, 720)

        central = QWidget()
        central.setObjectName("centralWidget")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        accent = self.settings_manager.get('accentColor', '#FF5500')
        self.title_bar = TitleBar(self, accent_color=accent)
        main_layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(6)

        self.btn_toggle_sidebar = QPushButton()
        self.btn_toggle_sidebar.setIcon(qta.icon("fa5s.bars", color="#A39E9A"))
        self.btn_toggle_sidebar.setFixedSize(32, 32)
        self.btn_toggle_sidebar.setStyleSheet("background: transparent; border: none;")
        self.btn_toggle_sidebar.setToolTip("Toggle Collapsible Sidebar")
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        sb_layout.addWidget(self.btn_toggle_sidebar)

        self.nav_btn_group = QButtonGroup(self)

        def create_nav_btn(icon_name, text, index):
            btn = QPushButton(f"  {text}")
            btn.setIcon(qta.icon(icon_name, color="#A39E9A"))
            btn.setCheckable(True)
            btn.setProperty("nav", "true")
            self.nav_btn_group.addButton(btn, index)
            return btn

        self.btn_search = create_nav_btn("fa5s.search", "Search", 0)
        self.btn_library = create_nav_btn("fa5s.music", "Library", 1)
        self.btn_crates = create_nav_btn("fa5s.folder", "Crates", 2)
        self.btn_queue = create_nav_btn("fa5s.list", "Queue", 3)
        self.btn_settings = create_nav_btn("fa5s.cog", "Settings", 4)

        self.btn_search.setChecked(True)

        sb_layout.addWidget(self.btn_search)
        sb_layout.addWidget(self.btn_library)
        sb_layout.addWidget(self.btn_crates)
        sb_layout.addWidget(self.btn_queue)
        sb_layout.addStretch()

        self.btn_mini_player = QPushButton(" Mini Player")
        self.btn_mini_player.setIcon(qta.icon("fa5s.compress-alt", color="#A39E9A"))
        self.btn_mini_player.clicked.connect(self.toggle_mini_player)
        sb_layout.addWidget(self.btn_mini_player)

        sb_layout.addWidget(self.btn_settings)
        body_layout.addWidget(self.sidebar)

        self.stacked_widget = FadingStackedWidget()
        
        self.page_search = self._create_search_page()
        self.page_library = self._create_library_page()
        self.page_crates = self._create_crates_page()
        self.page_queue = self._create_queue_page()
        self.page_settings = self._create_settings_page()

        self.stacked_widget.addWidget(self.page_search)
        self.stacked_widget.addWidget(self.page_library)
        self.stacked_widget.addWidget(self.page_crates)
        self.stacked_widget.addWidget(self.page_queue)
        self.stacked_widget.addWidget(self.page_settings)

        body_layout.addWidget(self.stacked_widget, 1)
        main_layout.addWidget(body, 1)

        self.player_bar = self._create_player_bar()
        main_layout.addWidget(self.player_bar)

        self.setCentralWidget(central)
        self.toast_manager = ToastManager(self)

    def _create_search_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tracks, artists, or paste YouTube/SoundCloud/Bandcamp URL...")
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.source_combo = QComboBox()
        self.source_combo.addItems(["YouTube", "SoundCloud", "Bandcamp", "All Sources"])
        self.source_combo.setFixedHeight(36)

        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["Any Duration", "Short (< 5m)", "Medium (5-10m)", "Long (> 10m)"])
        self.duration_combo.setFixedHeight(36)

        self.search_btn = QPushButton(" Search")
        self.search_btn.setIcon(qta.icon("fa5s.search", color="#E8E3DF"))
        self.search_btn.setFixedHeight(36)
        self.search_btn.clicked.connect(self.perform_search)

        top_bar.addWidget(self.search_input, 1)
        top_bar.addWidget(self.source_combo)
        top_bar.addWidget(self.duration_combo)
        top_bar.addWidget(self.search_btn)
        layout.addLayout(top_bar)

        self.search_header_box = QHBoxLayout()
        self.search_header_box.setSpacing(6)
        hdr_icon = QLabel()
        hdr_icon.setPixmap(qta.icon("fa5s.fire", color=self.settings_manager.get('accentColor', '#FF5500')).pixmap(14, 14))
        self.search_header_lbl = QLabel("TOP 10 TRENDING DJ COMMUNITY TRACKS TODAY")
        self.search_header_lbl.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {self.settings_manager.get('accentColor', '#FF5500')}; letter-spacing: 0.5px;")

        self.search_header_box.addWidget(hdr_icon)
        self.search_header_box.addWidget(self.search_header_lbl, 1)
        layout.addLayout(self.search_header_box)

        self.search_scroll = QScrollArea()
        self.search_scroll.setWidgetResizable(True)
        self.search_scroll_content = QWidget()
        self.search_results_layout = QVBoxLayout(self.search_scroll_content)
        self.search_results_layout.setContentsMargins(0, 0, 0, 0)
        self.search_results_layout.setSpacing(8)
        self.search_results_layout.addStretch()

        self.search_scroll.setWidget(self.search_scroll_content)
        layout.addWidget(self.search_scroll, 1)

        return page

    def _create_library_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Row 1: Search & Sorting
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.lib_search_input = QLineEdit()
        self.lib_search_input.setPlaceholderText("Filter library tracks by title or artist...")
        self.lib_search_input.setFixedHeight(36)
        self.lib_search_input.textChanged.connect(self.filter_library)

        self.lib_sort_combo = QComboBox()
        self.lib_sort_combo.addItems(["Date Added", "Title", "Artist", "BPM", "Duration", "Size", "Rating"])
        self.lib_sort_combo.setFixedHeight(36)
        self.lib_sort_combo.currentIndexChanged.connect(self.filter_library)

        top_row.addWidget(self.lib_search_input, 1)
        top_row.addWidget(QLabel("Sort By:"))
        top_row.addWidget(self.lib_sort_combo)
        layout.addLayout(top_row)

        # Row 2: Action Toolbar (spacious, un-cramped)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.btn_match_assistant = QPushButton(" Match Assistant")
        self.btn_match_assistant.setIcon(qta.icon("fa5s.bolt", color="#00E676"))
        self.btn_match_assistant.setCheckable(True)
        self.btn_match_assistant.setFixedHeight(32)
        self.btn_match_assistant.setToolTip("Harmonically match tracks in key, BPM & vibe with currently playing track")
        self.btn_match_assistant.toggled.connect(self.on_match_assistant_toggled)

        self.btn_gig_matcher = QPushButton(" Gig Overlay")
        self.btn_gig_matcher.setIcon(qta.icon("fa5s.external-link-alt", color="#00E676"))
        self.btn_gig_matcher.setFixedHeight(32)
        self.btn_gig_matcher.setToolTip("Launch ultra-compact live gig matcher overlay for Serato/Rekordbox")
        self.btn_gig_matcher.clicked.connect(self.toggle_gig_matcher_overlay)

        self.btn_analyze_lib = QPushButton(" Analyze BPM & Keys")
        self.btn_analyze_lib.setIcon(qta.icon("fa5s.wave-square", color="#00E5FF"))
        self.btn_analyze_lib.setFixedHeight(32)
        self.btn_analyze_lib.setToolTip("Auto-detect BPM and Camelot Key for all unanalyzed tracks")
        self.btn_analyze_lib.clicked.connect(self.start_library_analysis)

        self.btn_split_mix = QPushButton(" Split Mix")
        self.btn_split_mix.setIcon(qta.icon("fa5s.cut", color="#FF9800"))
        self.btn_split_mix.setFixedHeight(32)
        self.btn_split_mix.setToolTip("Parse timestamps & split long audio DJ sets into tracks")
        self.btn_split_mix.clicked.connect(self.open_mix_splitter)

        self.btn_clean_lib = QPushButton(" Clean Library")
        self.btn_clean_lib.setIcon(qta.icon("fa5s.broom", color="#A39E9A"))
        self.btn_clean_lib.setFixedHeight(32)
        self.btn_clean_lib.clicked.connect(self.clean_library)

        action_bar.addWidget(self.btn_match_assistant)
        action_bar.addWidget(self.btn_gig_matcher)
        action_bar.addWidget(self.btn_analyze_lib)
        action_bar.addWidget(self.btn_split_mix)
        action_bar.addStretch()
        action_bar.addWidget(self.btn_clean_lib)
        layout.addLayout(action_bar)

        self.lib_stats_label = QLabel("0 tracks · Total Duration: 0:00 · 0 MB")
        self.lib_stats_label.setStyleSheet("color: #8A8580; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.lib_stats_label)

        self.lib_header = LibraryHeaderWidget()
        self.lib_header.sort_requested.connect(self.on_header_sort_requested)
        layout.addWidget(self.lib_header)

        self.track_list = DraggableTrackList()
        self.track_list.double_clicked_track.connect(self.preview_track)
        self.track_list.menu_requested.connect(self.show_track_context_menu)
        layout.addWidget(self.track_list, 1)

        return page

    def start_library_analysis(self, force_all=False):
        if self._analysis_in_progress:
            self.toast_manager.show_toast("Library BPM & Key analysis is already running in background...", toast_type="info")
            return

        unanalyzed = [
            t['path'] for t in self.library_tracks
            if force_all or not (t.get('bpm') and t.get('key'))
        ]

        if not unanalyzed:
            self.toast_manager.show_toast("All tracks in your library already have BPM & Key tags!", toast_type="success")
            return

        self._analysis_in_progress = True
        self.btn_analyze_lib.setEnabled(False)
        self._run_analysis_thread(unanalyzed)

    def _run_analysis_thread(self, targets: list):
        """
        Create and start an ``AnalysisThread`` for the given file paths.

        Centralises the thread-start boilerplate that was previously duplicated
        between ``start_library_analysis`` and the context-menu analysis path.
        Also ensures the ``_analysis_in_progress`` guard is respected.
        """
        if not targets:
            return
        self._analysis_in_progress = True
        analysis_thread = AnalysisThread(targets)
        analysis_thread.completed.connect(self.on_analysis_track_completed)
        analysis_thread.all_finished.connect(self.on_analysis_finished)
        analysis_thread.finished.connect(lambda t=analysis_thread: self._prune_thread(t))
        analysis_thread.start()
        self._running_threads.append(analysis_thread)
        self.toast_manager.show_toast(f"Analyzing {len(targets)} track(s)...", toast_type="info")

    def on_analysis_track_completed(self, path, data):
        self.settings_manager.set_track_meta(path, data)
        for t in self.library_tracks:
            if t['path'] == path:
                t['bpm'] = data.get('bpm', t.get('bpm', ''))
                t['key'] = data.get('key', t.get('key', ''))
                break

    def on_analysis_finished(self):
        self._analysis_in_progress = False
        self.btn_analyze_lib.setEnabled(True)
        self.toast_manager.show_toast("BPM & Key analysis complete!", toast_type="success")
        self.filter_library()

    def on_match_assistant_toggled(self, checked):
        if checked and not self.player_track:
            self.toast_manager.show_toast("Play a track to enable DJ Match Assistant suggestions!", toast_type="info")
        self.filter_library()

    def on_header_sort_requested(self, sort_field):
        idx = self.lib_sort_combo.findText(sort_field)
        if idx >= 0:
            self.lib_sort_combo.setCurrentIndex(idx)
        else:
            self.filter_library()

    def on_track_rating_changed(self, track_path, new_rating):
        self.settings_manager.set_rating(track_path, new_rating)
        for t in self.library_tracks:
            if t['path'] == track_path:
                t['rating'] = new_rating
                break

    def _create_crates_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hdr = QHBoxLayout()
        hdr_lbl = QLabel("CRATE MANAGEMENT")
        hdr_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px;")

        self.btn_add_crate = QPushButton(" New Crate")
        self.btn_add_crate.setIcon(qta.icon("fa5s.plus", color="#E8E3DF"))
        self.btn_add_crate.clicked.connect(self.add_crate_dialog)

        self.btn_smart_crate = QPushButton(" Smart Crate")
        self.btn_smart_crate.setIcon(qta.icon("fa5s.magic", color="#E8E3DF"))
        self.btn_smart_crate.clicked.connect(self.add_smart_crate_dialog)

        self.btn_export_crate = QPushButton(" Export M3U")
        self.btn_export_crate.setIcon(qta.icon("fa5s.file-export", color="#E8E3DF"))
        self.btn_export_crate.setToolTip("Export current crate as .m3u8 playlist for Rekordbox/Serato")
        self.btn_export_crate.clicked.connect(lambda: self.export_current_crate())

        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(self.btn_add_crate)
        hdr.addWidget(self.btn_smart_crate)
        hdr.addWidget(self.btn_export_crate)
        layout.addLayout(hdr)

        self.crate_tab_bar = QHBoxLayout()
        self.crate_tab_bar.setSpacing(8)
        layout.addLayout(self.crate_tab_bar)

        self.crate_track_list = DraggableTrackList()
        self.crate_track_list.double_clicked_track.connect(self.preview_track)
        layout.addWidget(self.crate_track_list, 1)

        return page

    def _create_queue_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hdr = QHBoxLayout()
        hdr_title = QLabel("DOWNLOAD QUEUE")
        hdr_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF;")
        
        self.btn_clear_completed = QPushButton("Clear Completed")
        self.btn_clear_completed.clicked.connect(self.clear_completed_queue)

        hdr.addWidget(hdr_title)
        hdr.addStretch()
        hdr.addWidget(self.btn_clear_completed)
        layout.addLayout(hdr)

        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet("QListWidget { background-color: #141212; border: 1px solid #282423; border-radius: 8px; }")
        layout.addWidget(self.queue_list, 1)

        return page

    def _create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(18)

        theme_lbl = QLabel("APPEARANCE & THEME")
        theme_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #C47D63; letter-spacing: 1px;")
        c_layout.addWidget(theme_lbl)

        accent_box = QHBoxLayout()
        accent_box.addWidget(QLabel("Accent Color:"))
        
        self.accent_combo = QComboBox()
        for hex_val, name in SettingsManager.ACCENT_PRESETS:
            self.accent_combo.addItem(f"{name} ({hex_val})", hex_val)
        
        idx = self.accent_combo.findData(self.settings_manager.get('accentColor', '#FF5500'))
        if idx >= 0:
            self.accent_combo.setCurrentIndex(idx)
        self.accent_combo.currentIndexChanged.connect(self.on_accent_changed)

        accent_box.addWidget(self.accent_combo)
        accent_box.addStretch()
        c_layout.addLayout(accent_box)

        # Theme Selector
        theme_box = QHBoxLayout()
        theme_box.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "OLED Black", "Soft Slate"])
        self.theme_combo.setCurrentText(self.settings_manager.get('theme', 'Dark'))
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_box.addWidget(self.theme_combo)
        theme_box.addStretch()
        c_layout.addLayout(theme_box)

        # Window Opacity
        opacity_box = QHBoxLayout()
        opacity_box.addWidget(QLabel("Window Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(self.settings_manager.get('windowOpacity', 100))
        self.opacity_slider.setFixedWidth(150)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_box.addWidget(self.opacity_slider)
        
        self.always_on_top_cb = QCheckBox("Always on Top")
        self.always_on_top_cb.setChecked(self.settings_manager.get('alwaysOnTop', False))
        self.always_on_top_cb.stateChanged.connect(self._on_always_on_top_changed)
        opacity_box.addWidget(self.always_on_top_cb)
        opacity_box.addStretch()
        c_layout.addLayout(opacity_box)

        path_lbl = QLabel("STORAGE & DOWNLOADS")
        path_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #C47D63; letter-spacing: 1px;")
        c_layout.addWidget(path_lbl)

        path_box = QHBoxLayout()
        self.music_path_input = QLineEdit(self.settings_manager.get('musicPath'))
        self.music_path_btn = QPushButton("Browse...")
        self.music_path_btn.clicked.connect(self.browse_music_path)
        path_box.addWidget(self.music_path_input, 1)
        path_box.addWidget(self.music_path_btn)
        c_layout.addLayout(path_box)

        # Format & Concurrency
        fmt_box = QHBoxLayout()
        fmt_box.addWidget(QLabel("Default Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp3', 'wav', 'flac', 'm4a'])
        self.format_combo.setCurrentText(self.settings_manager.get('format', 'mp3'))
        self.format_combo.currentTextChanged.connect(lambda t: self.settings_manager.set('format', t))
        fmt_box.addWidget(self.format_combo)

        fmt_box.addWidget(QLabel("Max Concurrent DLs:"))
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.settings_manager.get('maxConcurrent', 3))
        self.concurrent_spin.valueChanged.connect(lambda v: self.settings_manager.set('maxConcurrent', v))
        fmt_box.addWidget(self.concurrent_spin)
        
        fmt_box.addWidget(QLabel("Max Search Results:"))
        self.search_spin = QSpinBox()
        self.search_spin.setRange(5, 50)
        self.search_spin.setValue(self.settings_manager.get('maxSearchResults', 15))
        self.search_spin.valueChanged.connect(lambda v: self.settings_manager.set('maxSearchResults', v))
        fmt_box.addWidget(self.search_spin)
        
        fmt_box.addStretch()
        c_layout.addLayout(fmt_box)

        # yt-dlp & ffmpeg paths
        tool_box = QGridLayout()
        tool_box.addWidget(QLabel("yt-dlp path:"), 0, 0)
        self.ytdlp_input = QLineEdit(self.settings_manager.get('ytdlpPath', 'yt-dlp'))
        self.ytdlp_input.textChanged.connect(lambda t: self.settings_manager.set('ytdlpPath', t))
        tool_box.addWidget(self.ytdlp_input, 0, 1)

        tool_box.addWidget(QLabel("ffmpeg path:"), 1, 0)
        self.ffmpeg_input = QLineEdit(self.settings_manager.get('ffmpegPath', 'ffmpeg'))
        self.ffmpeg_input.textChanged.connect(lambda t: self.settings_manager.set('ffmpegPath', t))
        tool_box.addWidget(self.ffmpeg_input, 1, 1)

        tool_box.addWidget(QLabel("Cookies file:"), 2, 0)
        self.cookies_input = QLineEdit(self.settings_manager.get('cookiesPath', ''))
        self.cookies_input.textChanged.connect(lambda t: self.settings_manager.set('cookiesPath', t))
        c_layout.addLayout(tool_box)

        # Quick Actions Header
        quick_hdr = QLabel("DATA & FOLDER SHORTCUTS")
        quick_hdr.setStyleSheet("font-size: 14px; font-weight: 800; color: #C47D63; letter-spacing: 1px; margin-top: 10px;")
        c_layout.addWidget(quick_hdr)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_open_music = QPushButton(" Open Music Directory")
        btn_open_music.setIcon(qta.icon("fa5s.folder-open", color="#E8E3DF"))
        btn_open_music.clicked.connect(self._open_music_dir)

        btn_open_appdata = QPushButton(" Open OBS & Data Directory")
        btn_open_appdata.setIcon(qta.icon("fa5s.cogs", color="#E8E3DF"))
        btn_open_appdata.clicked.connect(self._open_appdata_dir)

        btn_row.addWidget(btn_open_music)
        btn_row.addWidget(btn_open_appdata)
        btn_row.addStretch()
        c_layout.addLayout(btn_row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return page

    def _create_player_bar(self):
        bar = QWidget()
        bar.setObjectName("playerBar")
        bar.setFixedHeight(130)

        main_vbox = QVBoxLayout(bar)
        main_vbox.setContentsMargins(16, 10, 16, 10)
        main_vbox.setSpacing(8)

        # ── Row 1: Track Info, Play Controls & Volume ──
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Left Info
        left_info = QHBoxLayout()
        left_info.setSpacing(10)
        self.equalizer = EqualizerWidget(accent_color=self.settings_manager.get('accentColor', '#FF5500'))
        
        info = QVBoxLayout()
        info.setSpacing(1)
        self.player_title_label = QLabel("No track playing")
        self.player_title_label.setObjectName("player-title")
        self.player_artist_label = QLabel("DJ Crate Audio Previewer")
        self.player_artist_label.setObjectName("player-artist")
        info.addWidget(self.player_title_label)
        info.addWidget(self.player_artist_label)

        left_info.addWidget(self.equalizer)
        left_info.addLayout(info)
        top_row.addLayout(left_info, 1)

        # Center Controls
        ctrls = QHBoxLayout()
        ctrls.setSpacing(10)
        ctrls.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.play_btn = QPushButton()
        self.play_btn.setObjectName("play-btn")
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
        self.play_btn.setGraphicsEffect(self._play_glow)
        self.play_btn.clicked.connect(self.toggle_play)

        self.stop_btn = QPushButton()
        self.stop_btn.setObjectName("control-btn")
        self.stop_btn.setFixedSize(28, 28)
        self.stop_btn.setIcon(qta.icon("fa5s.stop", color="#A39E9A"))
        self.stop_btn.clicked.connect(self.stop_playback)

        ctrls.addWidget(self.play_btn)
        ctrls.addWidget(self.stop_btn)
        top_row.addLayout(ctrls)

        # Right Meter, Pitch & Volume
        right = QHBoxLayout()
        right.setSpacing(8)

        self.loudness_meter = LoudnessMeterWidget()
        right.addWidget(self.loudness_meter)

        pitch_box = QHBoxLayout()
        pitch_box.setSpacing(4)
        pitch_lbl = QLabel("PITCH")
        pitch_lbl.setStyleSheet("color: #8A8580; font-size: 10px; font-weight: bold;")

        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-20, 20)
        self.pitch_slider.setValue(0)
        self.pitch_slider.setFixedWidth(70)
        self.pitch_slider.setToolTip("Tempo adjustment (-20% to +20%)")
        self.pitch_slider.valueChanged.connect(self.on_pitch_changed)

        self.pitch_val_lbl = QLabel("0.0%")
        self.pitch_val_lbl.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.pitch_val_lbl.setFixedWidth(40)

        self.btn_reset_pitch = QPushButton("RST")
        self.btn_reset_pitch.setFixedSize(28, 18)
        self.btn_reset_pitch.setStyleSheet("background: #2A2725; color: #A39E9A; font-size: 9px; font-weight: bold; border-radius: 3px;")
        self.btn_reset_pitch.clicked.connect(lambda: self.pitch_slider.setValue(0))

        pitch_box.addWidget(pitch_lbl)
        pitch_box.addWidget(self.pitch_slider)
        pitch_box.addWidget(self.pitch_val_lbl)
        pitch_box.addWidget(self.btn_reset_pitch)
        right.addLayout(pitch_box)

        self.vol_icon = QLabel()
        self.vol_icon.setPixmap(qta.icon("fa5s.volume-up", color="#A39E9A").pixmap(16, 16))
        self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)

        right.addWidget(self.vol_icon)
        right.addWidget(self.volume_slider)
        top_row.addLayout(right, 1)

        main_vbox.addLayout(top_row)

        # ── Row 2: Dedicated Full-Height SoundCloud Waveform Scrubber ──
        seek_box = QHBoxLayout()
        seek_box.setSpacing(8)

        self.curr_time_label = QLabel("0:00")
        self.curr_time_label.setStyleSheet("color: #8A8580; font-size: 11px; font-family: monospace;")
        
        self.seek_slider = PlayerSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("playerSlider")
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.set_accent_color(self.settings_manager.get('accentColor', '#FF5500'))
        self.seek_slider.sliderMoved.connect(self.on_seek_moved)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, 'slider_pressed', True))
        self.seek_slider.sliderReleased.connect(self.on_seek_released)
        
        self.total_time_label = QLabel("0:00")
        self.total_time_label.setStyleSheet("color: #8A8580; font-size: 11px; font-family: monospace;")

        seek_box.addWidget(self.curr_time_label)
        seek_box.addWidget(self.seek_slider, 1)
        seek_box.addWidget(self.total_time_label)
        main_vbox.addLayout(seek_box)

        return bar

    def setup_connections(self):
        self.nav_btn_group.idClicked.connect(self.stacked_widget.setCurrentIndex)
        self.media_player.positionChanged.connect(self.on_player_position_changed)
        self.media_player.durationChanged.connect(self.on_player_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

    def setup_shortcuts(self):
        # Playback
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.stop_playback)
        # Seek
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._seek_relative(5))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._seek_relative(-5))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self._seek_relative(1))
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self._seek_relative(-1))
        # Volume
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self._adjust_volume(5))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self._adjust_volume(-5))
        # Navigation
        QShortcut(QKeySequence("1"), self, lambda: self.stacked_widget.setCurrentIndex(0))
        QShortcut(QKeySequence("2"), self, lambda: self.stacked_widget.setCurrentIndex(1))
        QShortcut(QKeySequence("3"), self, lambda: self.stacked_widget.setCurrentIndex(2))
        QShortcut(QKeySequence("4"), self, lambda: self.stacked_widget.setCurrentIndex(3))
        QShortcut(QKeySequence("5"), self, lambda: self.stacked_widget.setCurrentIndex(4))
        # Focus search
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.stacked_widget.setCurrentIndex(0), self.search_input.setFocus()))

    def _seek_relative(self, seconds):
        dur = self.media_player.duration()
        if dur > 0:
            new_pos = max(0, min(dur, self.media_player.position() + seconds * 1000))
            self.media_player.setPosition(int(new_pos))

    def _adjust_volume(self, delta):
        new_vol = max(0, min(100, self.volume_slider.value() + delta))
        self.volume_slider.setValue(new_vol)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'toast_manager'):
            self.toast_manager._reposition()

    def on_accent_changed(self, idx):
        hex_val = self.accent_combo.currentData()
        if hex_val:
            self.settings_manager.set('accentColor', hex_val)
            self.apply_theme()
            if self.mini_player:
                self.mini_player.set_accent_color(hex_val)

    def _on_theme_changed(self, text):
        self.settings_manager.set('theme', text)
        self.apply_theme()

    def _on_opacity_changed(self, value):
        self.settings_manager.set('windowOpacity', value)
        self.setWindowOpacity(value / 100.0)

    def _on_always_on_top_changed(self, state):
        is_checked = state == 2
        self.settings_manager.set('alwaysOnTop', is_checked)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, is_checked)
        self.show()

    def toggle_mini_player(self):
        if not self.mini_player:
            self.mini_player = MiniPlayerWindow(self, accent_color=self.settings_manager.get('accentColor', '#FF5500'))
            self.mini_player.play_pause_clicked.connect(self.toggle_play)
            self.mini_player.stop_clicked.connect(self.stop_playback)
            self.mini_player.expand_clicked.connect(self.restore_from_mini_player)

        if self.player_track:
            self.mini_player.update_track(
                self.player_track.get('title', ''),
                self.player_track.get('artist', ''),
                self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )

        self.hide()
        self.mini_player.show()

    def restore_from_mini_player(self):
        if self.mini_player:
            self.mini_player.hide()
        self.show()

    def browse_music_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Music Directory", self.music_path_input.text())
        if dir_path:
            self.music_path_input.setText(dir_path)
            self.settings_manager.set('musicPath', dir_path)
            self.refresh_library()

    def _open_music_dir(self):
        music_path = self.settings_manager.get('musicPath')
        if os.path.exists(music_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(music_path))
        else:
            self.toast_manager.show_toast("Music directory does not exist.", toast_type="error")

    def _open_appdata_dir(self):
        app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate')
        os.makedirs(app_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(app_dir))

    def _on_search_text_changed(self, text):
        if text.strip():
            self.search_header_lbl.setText("SEARCH RESULTS")
            self._search_debounce_timer.start()
        else:
            self.load_trending_tracks()

    def load_trending_tracks(self):
        if self.search_input.text().strip():
            return
        self.search_header_lbl.setText("TOP 10 TRENDING DJ COMMUNITY TRACKS TODAY")
        thread = SearchThread(
            "Beatport Top 10 Dance Electronic Club Bangers",
            source=self.source_combo.currentText(),
            duration_filter="Any Duration",
            max_results=10,
            ytdlp_path=self.settings_manager.get('ytdlpPath', 'yt-dlp'),
            cookies_path=self.settings_manager.get('cookiesPath', '')
        )
        thread.results_ready.connect(self.on_search_results)
        thread.error_occurred.connect(self.on_search_error)
        thread.start()
        self._running_threads.append(thread)

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            self.load_trending_tracks()
            return
        
        self.search_header_lbl.setText(f"SEARCH RESULTS FOR '{query.upper()}'")
        self.search_btn.setEnabled(False)
        thread = SearchThread(
            query,
            source=self.source_combo.currentText(),
            duration_filter=self.duration_combo.currentText(),
            max_results=self.settings_manager.get('maxResults', 10),
            ytdlp_path=self.settings_manager.get('ytdlpPath', 'yt-dlp'),
            cookies_path=self.settings_manager.get('cookiesPath', '')
        )
        thread.results_ready.connect(self.on_search_results)
        thread.error_occurred.connect(self.on_search_error)
        thread.finished.connect(lambda: self.search_btn.setEnabled(True))
        thread.start()
        self._running_threads.append(thread)

    def on_search_results(self, results):
        while self.search_results_layout.count() > 1:
            item = self.search_results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.search_cards.clear()

        for res in results:
            card = SearchResultCard(res, default_format=self.settings_manager.get('format', 'mp3'))
            card.download_requested.connect(self.start_download)
            self.search_results_layout.insertWidget(self.search_results_layout.count() - 1, card)
            # Track card by URL for download progress updates
            if res.get('url'):
                self.search_cards[res['url']] = card

    def on_search_error(self, err_msg):
        self.toast_manager.show_toast(err_msg, toast_type="error")

    def start_download(self, url, title, duration, fmt):
        dl_thread = DownloadThread(
            url, title, self.settings_manager.get('musicPath'), fmt,
            ytdlp_path=self.settings_manager.get('ytdlpPath', 'yt-dlp'),
            ffmpeg_path=self.settings_manager.get('ffmpegPath', 'ffmpeg'),
            cookies_path=self.settings_manager.get('cookiesPath', ''),
            use_archive=self.settings_manager.get('useArchive', False)
        )
        dl_thread.progress.connect(self.on_download_progress)
        dl_thread.completed.connect(self.on_download_completed)
        dl_thread.finished.connect(lambda t=dl_thread: self._prune_thread(t))
        dl_thread.start()
        self._running_threads.append(dl_thread)
        self.download_threads[url] = dl_thread
        self.toast_manager.show_toast(f"Started download: {title}", toast_type="info")

        # Update search card state if visible
        if url in self.search_cards:
            self.search_cards[url].set_downloading()

        # Add to download queue page and track the row for in-place updates
        queue_data = {'url': url, 'title': title, 'status': 'downloading', 'progress': 0}
        item = QListWidgetItem(self.queue_list)
        row = QueueItemRow(queue_data, accent_color=self.settings_manager.get('accentColor', '#FF5500'))
        row.cancel_requested.connect(self._cancel_download)
        item.setSizeHint(row.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, url)
        self.queue_list.setItemWidget(item, row)
        self._queue_rows[url] = row

    def _cancel_download(self, url):
        if url in self.download_threads:
            self.download_threads[url].is_cancelled = True

    def on_download_progress(self, url, pct, speed, eta):
        # Update search card
        if url in self.search_cards:
            self.search_cards[url].update_progress(pct, speed, eta)

        # Update queue row in-place (avoids widget recreation on every % tick)
        if url in self._queue_rows:
            self._queue_rows[url].update_progress(pct)

    def on_download_completed(self, url, ok, result):
        # Update search card
        if url in self.search_cards:
            if ok:
                self.search_cards[url].set_in_library()
            else:
                self.search_cards[url].set_available()

        # Update queue list item to reflect final status
        if url in self._queue_rows:
            queue_data = {
                'url': url,
                'title': os.path.basename(result) if ok else result,
                'status': 'completed' if ok else 'failed',
                'progress': 100 if ok else 0
            }
            new_row = QueueItemRow(queue_data, accent_color=self.settings_manager.get('accentColor', '#FF5500'))
            # Find the list item and swap the widget
            for i in range(self.queue_list.count()):
                item = self.queue_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == url:
                    item.setSizeHint(new_row.sizeHint())
                    self.queue_list.setItemWidget(item, new_row)
                    break
            del self._queue_rows[url]

        # Clean up thread reference
        self.download_threads.pop(url, None)

        if ok:
            self.toast_manager.show_toast(f"Downloaded successfully: {os.path.basename(result)}", toast_type="success")
            self.settings_manager.add_history_entry(
                os.path.basename(result), url, result.rsplit('.', 1)[-1] if '.' in result else '', 'completed', result
            )
            
            # Start iTunes Metadata Fetching
            tag_thread = AutoTagThread([result])
            tag_thread.completed.connect(self._on_autotag_completed)
            tag_thread.start()
            self._running_threads.append(tag_thread)
        else:
            self.toast_manager.show_toast(f"Download failed: {result}", toast_type="error")
            self.settings_manager.add_history_entry(result, url, '', 'failed')

    def _on_autotag_completed(self, path, data):
        self.settings_manager.set_track_meta(path, data)
        self.refresh_library()
        self.start_library_analysis(force_all=False)

    def refresh_library(self):
        path = self.settings_manager.get('musicPath')
        if not os.path.exists(path):
            return

        self.library_tracks.clear()
        extensions = ('*.mp3', '*.wav', '*.flac', '*.m4a', '*.aac', '*.ogg')
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(path, ext)))
            files.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
        files = list(set(files))  # Deduplicate

        total_bytes = 0
        total_secs = 0
        unanalyzed_count = 0

        for f in files:
            size = os.path.getsize(f)
            total_bytes += size
            meta = extract_file_audio_metadata(f)
            cached_meta = self.settings_manager.get_track_meta(f)

            bpm = meta.get('bpm') or cached_meta.get('bpm', '')
            key = meta.get('key') or cached_meta.get('key', '')

            if not (bpm and key):
                unanalyzed_count += 1

            dur = meta.get('duration', 0)
            total_secs += dur

            m = dur // 60
            s = dur % 60
            dur_str = f"{m}:{s:02d}" if dur > 0 else ""

            track_info = {
                'path': f,
                'title': meta.get('title') or os.path.basename(f).rsplit('.', 1)[0],
                'artist': meta.get('artist', 'Unknown Artist'),
                'bpm': bpm,
                'key': key,
                'duration_str': dur_str,
                'durationSecs': dur,
                'format': f.rsplit('.', 1)[-1],
                'size': size,
                'rating': self.settings_manager.get_rating(f),
                'mtime': os.path.getmtime(f)
            }
            self.library_tracks.append(track_info)

        self.lib_stats_label.setText(
            f"{len(self.library_tracks)} tracks  ·  Total Duration: {total_secs // 60} mins  ·  {total_bytes / (1024*1024):.1f} MB"
        )
        self.filter_library()

        # Auto-trigger background analysis for unanalyzed tracks
        if unanalyzed_count > 0 and not self._analysis_in_progress:
            self.start_library_analysis(force_all=False)

    def filter_library(self):
        self.track_list.clear()
        query = self.lib_search_input.text().lower()
        sort_by = self.lib_sort_combo.currentText()
        is_matching = self.btn_match_assistant.isChecked() and self.player_track is not None

        filtered = [
            t for t in self.library_tracks
            if query in t['title'].lower() or query in t['artist'].lower()
        ]

        matches_map = {}
        if is_matching:
            for t in filtered:
                matches_map[t['path']] = CamelotMatcher.calculate_track_match(self.player_track, t)
            filtered.sort(key=lambda x: matches_map[x['path']]['score'], reverse=True)
        elif sort_by == 'Title':
            filtered.sort(key=lambda x: x['title'].lower())
        elif sort_by == 'Artist':
            filtered.sort(key=lambda x: x['artist'].lower())
        elif sort_by == 'BPM':
            filtered.sort(key=lambda x: int(x['bpm']) if str(x['bpm']).isdigit() else 0, reverse=True)
        elif sort_by == 'Duration':
            filtered.sort(key=lambda x: x['durationSecs'], reverse=True)
        elif sort_by == 'Rating':
            filtered.sort(key=lambda x: x['rating'], reverse=True)
        elif sort_by == 'Size':
            filtered.sort(key=lambda x: x['size'], reverse=True)
        else:
            filtered.sort(key=lambda x: x['mtime'], reverse=True)

        for track in filtered:
            item = QListWidgetItem(self.track_list)
            item.setData(Qt.ItemDataRole.UserRole, track)
            match_info = matches_map.get(track['path']) if is_matching else None
            row = self._add_track_row_to_list(
                self.track_list, track, item,
                is_playing=(self.player_track and self.player_track['path'] == track['path']),
                match_info=match_info
            )
            row.rating_changed.connect(self.on_track_rating_changed)

    def _add_track_row_to_list(self, list_widget, track, item, is_playing=False, match_info=None):
        """
        Create and attach a ``LibraryTrackRow`` widget to ``list_widget``.

        Centralises the boilerplate that was previously duplicated across
        ``filter_library``, ``_on_crate_selected``, and ``_on_smart_crate_selected``.

        Returns
        -------
        LibraryTrackRow
            The created row widget, so callers can connect additional signals.
        """
        row = LibraryTrackRow(
            list_widget, track, item,
            is_playing=is_playing,
            match_info=match_info,
            accent_color=self.settings_manager.get('accentColor', '#FF5500')
        )
        item.setSizeHint(row.sizeHint())
        list_widget.setItemWidget(item, row)
        return row

    def preview_track(self, track):
        if not track or not os.path.exists(track['path']):
            return
        self.player_track = track
        self.media_player.setSource(QUrl.fromLocalFile(track['path']))
        self.media_player.play()
        self.player_title_label.setText(track['title'])
        self.player_artist_label.setText(track['artist'])
        self.equalizer.set_playing(True)

        # Update OBS Streamer Overlay
        ObsOverlayWriter.update_now_playing(
            track.get('title', ''),
            track.get('artist', ''),
            track.get('bpm', ''),
            track.get('key', ''),
            accent_color=self.settings_manager.get('accentColor', '#FF5500')
        )

        if self._glow_seq.state() != QSequentialAnimationGroup.State.Running:
            self._glow_seq.start()

        if self.mini_player:
            self.mini_player.update_track(track['title'], track['artist'], True)

        if self.btn_match_assistant.isChecked():
            self.filter_library()

        cache_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate', 'waveforms')
        wf_thread = WaveformGeneratorThread(
            track['path'], cache_dir,
            ffmpeg_path=self.settings_manager.get('ffmpegPath', 'ffmpeg'),
            accent_color=self.settings_manager.get('accentColor', '#FF5500')
        )
        wf_thread.waveform_ready.connect(self.on_waveform_ready)
        wf_thread.peaks_ready.connect(self.on_peaks_ready)
        wf_thread.loudness_ready.connect(self.on_loudness_ready)
        wf_thread.start()
        self._running_threads.append(wf_thread)

    def toggle_gig_matcher_overlay(self):
        if not self.gig_matcher:
            self.gig_matcher = GigMatcherWidget(
                library_tracks=self.library_tracks,
                accent_color=self.settings_manager.get('accentColor', '#FF5500')
            )
            self.gig_matcher.track_preview_requested.connect(self.preview_track)
        else:
            self.gig_matcher.set_library_tracks(self.library_tracks)

        if self.gig_matcher.isVisible():
            self.gig_matcher.hide()
        else:
            self.gig_matcher.show()

    def quick_download_url(self, url, fmt):
        """Handle a quick download triggered from the clipboard HUD."""
        title = _derive_title_from_url(url)
        self.toast_manager.show_toast(
            f"Quick Capture download started ({fmt.upper()})...", toast_type="info"
        )
        self.start_download(url, title, 0, fmt)

    def on_waveform_ready(self, file_path, img_path):
        if self.player_track and self.player_track['path'] == file_path:
            pix = QPixmap(img_path)
            if not pix.isNull():
                self.seek_slider.set_waveform(pix)

    def on_peaks_ready(self, file_path, peaks):
        if self.player_track and self.player_track['path'] == file_path:
            self.seek_slider.set_peaks(peaks)

    def on_loudness_ready(self, file_path, max_db, mean_db):
        if self.player_track and self.player_track['path'] == file_path:
            self.loudness_meter.set_loudness(max_db, mean_db)

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.equalizer.set_playing(False)
            self.play_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
            if self.mini_player and self.player_track:
                self.mini_player.update_track(self.player_track['title'], self.player_track['artist'], False)
        else:
            if self.player_track:
                self.media_player.play()
                self.equalizer.set_playing(True)
                self.play_btn.setIcon(qta.icon("fa5s.pause", color="#FFFFFF"))
                if self.mini_player:
                    self.mini_player.update_track(self.player_track['title'], self.player_track['artist'], True)

    def stop_playback(self):
        self.media_player.stop()
        self.equalizer.set_playing(False)
        self.play_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
        self._glow_seq.stop()
        if self.mini_player:
            self.mini_player.update_track("DJ Crate", "Stopped", False)

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.equalizer.set_playing(False)
            self.play_btn.setIcon(qta.icon("fa5s.play", color="#FFFFFF"))
            self._glow_seq.stop()
            self._play_glow.setBlurRadius(0)
            self._disc_timer.stop()

    def on_player_position_changed(self, pos):
        if not self.slider_pressed and self.media_player.duration() > 0:
            val = int((pos / self.media_player.duration()) * 1000)
            self.seek_slider.setValue(val)
            self.curr_time_label.setText(self.format_time(pos // 1000))

    def on_player_duration_changed(self, dur):
        dur_secs = dur // 1000
        self.total_time_label.setText(self.format_time(dur_secs))
        self.seek_slider.set_duration(dur_secs)

    def on_seek_moved(self, val):
        dur = self.media_player.duration()
        if dur > 0:
            target = int((val / 1000) * dur)
            self.curr_time_label.setText(self.format_time(target // 1000))
            self.media_player.setPosition(target)

    def on_seek_released(self):
        self.slider_pressed = False
        dur = self.media_player.duration()
        if dur > 0:
            target = int((self.seek_slider.value() / 1000) * dur)
            self.media_player.setPosition(target)

    def on_volume_changed(self, val):
        self.audio_output.setVolume(val / 100.0)
        self.settings_manager.set('volume', val)

    def format_time(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"

    def show_track_context_menu(self, track, pos):
        selected_items = self.track_list.selectedItems()
        selected_paths = [
            item.data(Qt.ItemDataRole.UserRole)['path']
            for item in selected_items
            if item.data(Qt.ItemDataRole.UserRole) and
               os.path.exists(item.data(Qt.ItemDataRole.UserRole).get('path', ''))
        ]

        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_style())
        analyze_track = menu.addAction("Analyze BPM & Key Tags")
        edit_meta = menu.addAction("Edit Metadata Tags...")
        bulk_edit = None
        if len(selected_paths) > 1:
            bulk_edit = menu.addAction(f"Bulk Edit {len(selected_paths)} Selected Tracks...")

        reveal = menu.addAction("Reveal in File Explorer")
        delete = menu.addAction("Delete Track File")

        action = menu.exec(pos)
        if action == analyze_track:
            targets = selected_paths if selected_paths else [track['path']]
            self._run_analysis_thread(targets)
        elif action == edit_meta:
            dlg = MetadataEditorDialog(track['path'], self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.refresh_library()
        elif bulk_edit and action == bulk_edit:
            dlg = BulkMetadataEditorDialog(selected_paths, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.toast_manager.show_toast(f"Updated metadata for {len(selected_paths)} tracks!", toast_type="success")
                self.refresh_library()
        elif action == reveal:
            if sys.platform == 'win32':
                subprocess.run(['explorer', '/select,', os.path.normpath(track['path'])])
        elif action == delete:
            targets = selected_paths if selected_paths else [track['path']]
            if QMessageBox.question(self, "Delete Track(s)", f"Delete {len(targets)} selected track(s) from disk?") == QMessageBox.StandardButton.Yes:
                for p in targets:
                    try:
                        os.remove(p)
                    except Exception as e:
                        logger.error(f"Error deleting {p}: {e}")
                self.refresh_library()

    def toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        if self._sidebar_collapsed:
            self.sidebar.setFixedWidth(64)
            self.btn_toggle_sidebar.setIcon(qta.icon("fa5s.angle-double-right", color="#A39E9A"))
            self.btn_search.setText("")
            self.btn_library.setText("")
            self.btn_crates.setText("")
            self.btn_queue.setText("")
            self.btn_settings.setText("")
            self.btn_mini_player.setText("")
        else:
            self.sidebar.setFixedWidth(200)
            self.btn_toggle_sidebar.setIcon(qta.icon("fa5s.angle-double-left", color="#A39E9A"))
            self.btn_search.setText("  Search")
            self.btn_library.setText("  Library")
            self.btn_crates.setText("  Crates")
            self.btn_queue.setText("  Queue")
            self.btn_settings.setText("  Settings")
            self.btn_mini_player.setText(" Mini Player")

    def on_pitch_changed(self, val):
        rate = 1.0 + (val / 100.0)
        self.media_player.setPlaybackRate(rate)
        sign = "+" if val > 0 else ""
        self.pitch_val_lbl.setText(f"{sign}{val}%")

    def _context_menu_style(self) -> str:
        """Return the shared QSS string for context menus."""
        return (
            "QMenu { background-color: #212133; color: #E8E3DF; "
            "border: 1px solid #3B3633; padding: 4px; border-radius: 4px; } "
            "QMenu::item:selected { background-color: #3B3633; }"
        )

    def _prune_thread(self, thread):
        """Remove a finished thread from ``_running_threads`` to prevent memory leaks."""
        try:
            self._running_threads.remove(thread)
        except ValueError:
            pass

    def export_current_crate(self, crate_name=None):
        target_crate = crate_name or self.active_crate
        if not target_crate:
            self.toast_manager.show_toast("Select a crate to export!", toast_type="info")
            return

        crates = self.settings_manager.get('crates', {})
        paths = crates.get(target_crate, [])
        if not paths:
            self.toast_manager.show_toast(f"Crate '{target_crate}' is empty.", toast_type="info")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Export Crate '{target_crate}'", f"{target_crate}.m3u8", "M3U8 Playlist (*.m3u8);;M3U Playlist (*.m3u)"
        )
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for p in paths:
                        if os.path.exists(p):
                            t = self._find_library_track(p)
                            title = t.get('title', os.path.basename(p)) if t else os.path.basename(p)
                            artist = t.get('artist', 'Unknown') if t else 'Unknown'
                            dur = t.get('durationSecs', 0) if t else 0
                            f.write(f"#EXTINF:{int(dur)},{artist} - {title}\n")
                            f.write(f"{os.path.abspath(p)}\n")
                self.toast_manager.show_toast(f"Exported crate '{target_crate}' to {os.path.basename(save_path)}!", toast_type="success")
            except Exception as e:
                self.toast_manager.show_toast(f"Failed to export playlist: {e}", toast_type="error")

    def open_mix_splitter(self):
        dlg = MixSplitterDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            input_file, tracks_info = dlg.get_parsed_data()
            if not input_file or not os.path.exists(input_file):
                self.toast_manager.show_toast("Invalid audio file selected.", toast_type="error")
                return
            if not tracks_info:
                self.toast_manager.show_toast("No valid timestamps parsed.", toast_type="error")
                return

            out_dir = os.path.join(self.settings_manager.get('musicPath'), "Splits")
            self.toast_manager.show_toast(f"Splitting mix into {len(tracks_info)} tracks...", toast_type="info")

            splitter_thread = MixSplitterThread(
                input_file, tracks_info, out_dir,
                ffmpeg_path=self.settings_manager.get('ffmpegPath', 'ffmpeg'),
                parent=self
            )
            splitter_thread.all_finished.connect(self._on_mix_split_finished)
            splitter_thread.start()
            self._running_threads.append(splitter_thread)

    def _on_mix_split_finished(self, output_paths):
        self.toast_manager.show_toast(f"Mix split into {len(output_paths)} tracks!", toast_type="success")
        self.refresh_library()

    def clean_library(self):
        missing_count = 0
        for track in self.library_tracks:
            if not os.path.exists(track['path']):
                missing_count += 1
        self.refresh_library()
        self.toast_manager.show_toast(f"Library refreshed. {missing_count} stale entries removed.", toast_type="info")

    def add_crate_dialog(self):
        text, ok = QInputDialog.getText(self, "New Crate", "Crate Name:")
        if ok and text.strip():
            self.settings_manager.db.add_crate(text.strip())
            self.toast_manager.show_toast(f"Created crate: {text.strip()}", toast_type="success")
            self._render_crate_tabs()

    def add_smart_crate_dialog(self):
        dlg = SmartCrateDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data['name']:
                self.settings_manager.db.add_smart_crate(data['name'], data)
                self.toast_manager.show_toast(f"Created smart crate: {data['name']}", toast_type="success")
                self._render_crate_tabs()

    def _render_crate_tabs(self):
        # Clear existing tabs
        while self.crate_tab_bar.count() > 0:
            item = self.crate_tab_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        crates = self.settings_manager.get('crates', {})
        smart_crates = self.settings_manager.get('smartCrates', {})

        for name in crates:
            tab = DroppableCrateTab(name, f" {name} ({len(crates[name])})")
            tab.setIcon(qta.icon("fa5s.folder", color="#A39E9A"))
            tab.setCheckable(True)
            tab.clicked.connect(lambda checked, n=name: self._on_crate_selected(n))
            tab.track_dropped.connect(self._on_track_dropped_to_crate)
            tab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tab.customContextMenuRequested.connect(lambda pos, n=name, b=tab: self._show_crate_context_menu(n, b.mapToGlobal(pos)))
            self.crate_tab_bar.addWidget(tab)

        for name in smart_crates:
            tab = QPushButton(f" {name}")
            tab.setIcon(qta.icon("fa5s.magic", color="#00E676"))
            tab.setCheckable(True)
            tab.clicked.connect(lambda checked, n=name: self._on_smart_crate_selected(n))
            self.crate_tab_bar.addWidget(tab)

        self.crate_tab_bar.addStretch()

    def _on_crate_selected(self, crate_name):
        self.active_crate = crate_name
        self.crate_track_list.clear()
        crates = self.settings_manager.get('crates', {})
        paths = crates.get(crate_name, [])
        for path in paths:
            if os.path.exists(path):
                track = self._find_library_track(path)
                if track:
                    item = QListWidgetItem(self.crate_track_list)
                    item.setData(Qt.ItemDataRole.UserRole, track)
                    self._add_track_row_to_list(self.crate_track_list, track, item)

    def _on_smart_crate_selected(self, crate_name):
        self.active_crate = crate_name
        self.crate_track_list.clear()
        smart_crates = self.settings_manager.get('smartCrates', {})
        rule = smart_crates.get(crate_name, {})
        field = rule.get('field', '').lower()
        op = rule.get('operator', 'contains')
        val = rule.get('value', '').lower()

        for track in self.library_tracks:
            track_val = str(track.get(field, '')).lower()
            match = False
            if op == 'contains' and val in track_val:
                match = True
            elif op == '=' and track_val == val:
                match = True
            elif op == '>=' and track_val.isdigit() and val.isdigit() and int(track_val) >= int(val):
                match = True
            elif op == '<=' and track_val.isdigit() and val.isdigit() and int(track_val) <= int(val):
                match = True

            if match:
                item = QListWidgetItem(self.crate_track_list)
                item.setData(Qt.ItemDataRole.UserRole, track)
                self._add_track_row_to_list(self.crate_track_list, track, item)

    def _on_track_dropped_to_crate(self, crate_name, track_path):
        crates = self.settings_manager.get('crates', {})
        if crate_name in crates:
            if track_path not in crates[crate_name]:
                self.settings_manager.db.add_track_to_crate(crate_name, track_path)
                self.toast_manager.show_toast(f"Added to {crate_name}", toast_type="success")
                self._render_crate_tabs()
                if self.active_crate == crate_name:
                    self._on_crate_selected(crate_name)
                # Auto-sync to Serato
                self.sync_crate_to_serato(crate_name)

    def sync_crate_to_serato(self, crate_name):
        crates = self.settings_manager.get('crates', {})
        paths = crates.get(crate_name, [])
        if not paths:
            self.toast_manager.show_toast(f"Crate '{crate_name}' has no tracks.", toast_type="info")
            return
        try:
            crate_file = SeratoCrateWriter.write_crate(crate_name, paths)
            self.toast_manager.show_toast(f"Synced '{crate_name}' to Serato: {os.path.basename(crate_file)}", toast_type="success")
        except Exception as e:
            self.toast_manager.show_toast(f"Failed to sync Serato crate: {e}", toast_type="error")

    def _show_crate_context_menu(self, crate_name, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_style())
        serato_action = menu.addAction("Sync to Serato (.crate)...")
        export_action = menu.addAction("Export Crate to M3U Playlist...")
        rename_action = menu.addAction("Rename Crate")
        delete_action = menu.addAction("Delete Crate")
        action = menu.exec(pos)
        if action == serato_action:
            self.sync_crate_to_serato(crate_name)
        elif action == export_action:
            self.export_current_crate(crate_name)
        elif action == delete_action:
            if QMessageBox.question(self, "Delete Crate", f"Delete crate '{crate_name}'?") == QMessageBox.StandardButton.Yes:
                self.settings_manager.db.delete_crate(crate_name)
                self.toast_manager.show_toast(f"Deleted crate: {crate_name}", toast_type="info")
                self._render_crate_tabs()
                self.crate_track_list.clear()
        elif action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename Crate", "New Name:", text=crate_name)
            if ok and new_name.strip() and new_name.strip() != crate_name:
                self.settings_manager.db.rename_crate(crate_name, new_name.strip())
                self._render_crate_tabs()

    def _find_library_track(self, path):
        for t in self.library_tracks:
            if t['path'] == path:
                return t
        return None

    def clear_completed_queue(self):
        # Remove only completed and failed items, keep active downloads
        items_to_remove = []
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            url = item.data(Qt.ItemDataRole.UserRole) if item else None
            if url and url not in self.download_threads:
                items_to_remove.append(i)
        for i in reversed(items_to_remove):
            self.queue_list.takeItem(i)

    def on_sleep_timer_fired(self):
        self.stop_playback()
        self.toast_manager.show_toast("Sleep timer fired. Playback stopped.", toast_type="info")

    def _rotate_disc(self):
        self._disc_angle = (self._disc_angle + 5) % 360

    def _restore_geometry(self):
        geo = self.settings_manager.get('windowGeometry')
        if geo and isinstance(geo, list) and len(geo) == 4:
            self.setGeometry(QRect(*geo))

    def closeEvent(self, event):
        # Save window geometry
        geo = self.geometry()
        self.settings_manager.set('windowGeometry', [geo.x(), geo.y(), geo.width(), geo.height()])
        self.settings_manager.save()
        if self.mini_player:
            self.mini_player.close()
        for t in self._running_threads:
            if t.isRunning():
                t.quit()
        event.accept()
