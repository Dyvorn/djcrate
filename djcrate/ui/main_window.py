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
    QGridLayout, QSizePolicy, QDialog, QApplication, QColorDialog
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
    DraggableTrackList, DroppableCrateTab, QueueItemRow, HistoryItemRow, TitleBar, FadingStackedWidget,
    TrackInspectorWidget, KeyboardShortcutsDialog
)
from djcrate.ui.dialogs import SmartCrateDialog, LogDialog, MetadataEditorDialog, BulkMetadataEditorDialog, MixSplitterDialog
from djcrate.ui.mini_player import MiniPlayerWindow
from djcrate.workers import (
    SearchThread, ThumbnailDownloader, DownloadThread, StreamResolverThread,
    MetadataProbeThread, AnalysisThread, AutoTagThread, WaveformGeneratorThread, MixSplitterThread
)
from djcrate.updater import AutoUpdaterThread, UpdateDownloaderThread, launch_installer_and_exit
from djcrate.serato import SeratoCrateWriter
from djcrate.obs_overlay import ObsOverlayWriter
from djcrate.ui.clipboard_widget import ClipboardGrabberWidget, _derive_title_from_url
from djcrate.ui.gig_matcher_widget import GigMatcherWidget
from djcrate.ui.set_builder_widget import SetBuilderPage

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

        self.active_camelot_key = "ALL"
        self.active_format_filter = "ALL"
        self.camelot_pill_buttons = {}
        self.format_chip_buttons = {}

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
        density = self.settings_manager.get('density', 'standard')
        qss = ThemeEngine.generate_qss(accent, theme, density)
        self.setStyleSheet(qss)
        self._play_glow.setColor(QColor(accent))
        if hasattr(self, 'title_bar'):
            self.title_bar.set_accent_color(accent)
        if hasattr(self, 'equalizer'):
            self.equalizer.set_accent_color(accent)
        if hasattr(self, 'seek_slider'):
            self.seek_slider.set_accent_color(accent)
        if hasattr(self, 'active_camelot_pill') and self.active_camelot_pill:
            self._update_camelot_pill_styles()

    def _check_for_updates(self):
        self.updater_thread = AutoUpdaterThread(repo_owner="Dyvorn", repo_name="djcrate", parent=self)
        self.updater_thread.update_available.connect(self._on_update_available)
        self.updater_thread.start()

    def _on_update_available(self, version, notes, url, installer_url=""):
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(f"<h3>A new version of DJ Crate ({version}) is available!</h3>")
        informative_text = (
            "Installing this update will seamlessly remove old application binaries while "
            "safely preserving all your crates, cue points, playlists, metadata, and settings."
        )
        msg.setInformativeText(informative_text)
        msg.setIcon(QMessageBox.Icon.Information)

        btn_update = None
        if installer_url:
            btn_update = msg.addButton("⚡ Update Now", QMessageBox.ButtonRole.AcceptRole)
        btn_page = msg.addButton("🌐 View Release", QMessageBox.ButtonRole.ActionRole)
        btn_later = msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_update if btn_update else btn_page)

        msg.exec()
        clicked = msg.clickedButton()

        if btn_update and clicked == btn_update:
            self._start_update_download(installer_url, version)
        elif clicked == btn_page:
            QDesktopServices.openUrl(QUrl(url))

    def _start_update_download(self, installer_url: str, version: str):
        self.toast_manager.show_toast(f"Downloading DJ Crate {version}...", "info", duration_ms=4000)
        self.downloader_thread = UpdateDownloaderThread(installer_url, version=version, parent=self)

        def on_progress(downloaded, total):
            if total > 0:
                pct = int((downloaded / total) * 100)
                if pct % 25 == 0 and pct > 0 and pct < 100:
                    self.toast_manager.show_toast(f"Downloading update: {pct}%", "info", duration_ms=1500)

        def on_completed(dest_path):
            self.toast_manager.show_toast("Download complete! Launching updater...", "success", duration_ms=3000)
            launch_installer_and_exit(dest_path)

        def on_failed(error_msg):
            self.toast_manager.show_toast(f"Update download failed: {error_msg}", "error", duration_ms=5000)

        self.downloader_thread.progress.connect(on_progress)
        self.downloader_thread.download_completed.connect(on_completed)
        self.downloader_thread.download_failed.connect(on_failed)
        self.downloader_thread.start()

    def setup_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1120, 720)
        self.toast_manager = ToastManager(self)

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
        self.btn_set_builder = create_nav_btn("fa5s.layer-group", "Set Builder", 3)
        self.btn_queue = create_nav_btn("fa5s.list", "Queue", 4)
        self.btn_settings = create_nav_btn("fa5s.cog", "Settings", 5)

        self.btn_search.setChecked(True)

        sb_layout.addWidget(self.btn_search)
        sb_layout.addWidget(self.btn_library)
        sb_layout.addWidget(self.btn_crates)
        sb_layout.addWidget(self.btn_set_builder)
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
        self.page_set_builder = SetBuilderPage(self.settings_manager, parent=self)
        self.page_set_builder.track_preview_requested.connect(self.preview_track)
        self.page_set_builder.toast_requested.connect(self.toast_manager.show_toast)
        self.page_queue = self._create_queue_page()
        self.page_settings = self._create_settings_page()

        self.stacked_widget.addWidget(self.page_search)
        self.stacked_widget.addWidget(self.page_library)
        self.stacked_widget.addWidget(self.page_crates)
        self.stacked_widget.addWidget(self.page_set_builder)
        self.stacked_widget.addWidget(self.page_queue)
        self.stacked_widget.addWidget(self.page_settings)

        body_layout.addWidget(self.stacked_widget, 1)
        main_layout.addWidget(body, 1)

        self.player_bar = self._create_player_bar()
        main_layout.addWidget(self.player_bar)

        self.setCentralWidget(central)

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
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)

        # Row 1: Search & Sorting
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.lib_search_input = QLineEdit()
        self.lib_search_input.setPlaceholderText("Filter library tracks by title, artist, or tags...")
        self.lib_search_input.setFixedHeight(34)
        self.lib_search_input.textChanged.connect(self.filter_library)

        self.lib_sort_combo = QComboBox()
        self.lib_sort_combo.addItems(["Date Added", "Title", "Artist", "BPM", "Duration", "Size", "Rating"])
        self.lib_sort_combo.setFixedHeight(34)
        self.lib_sort_combo.currentIndexChanged.connect(self.filter_library)

        top_row.addWidget(self.lib_search_input, 1)
        top_row.addWidget(QLabel("Sort:"))
        top_row.addWidget(self.lib_sort_combo)
        layout.addLayout(top_row)

        # Row 2: Interactive Camelot Harmonic Key Quick-Filter Strip
        camelot_scroll = QScrollArea()
        camelot_scroll.setFixedHeight(32)
        camelot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        camelot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        camelot_scroll.setWidgetResizable(True)
        camelot_scroll_w = QWidget()
        camelot_strip = QHBoxLayout(camelot_scroll_w)
        camelot_strip.setContentsMargins(0, 0, 0, 0)
        camelot_strip.setSpacing(4)

        keys = ["ALL", "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B",
                "7A", "7B", "8A", "8B", "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"]
        for k in keys:
            btn = QPushButton(k)
            btn.setCheckable(True)
            btn.setProperty("filter_chip", "true")
            btn.setFixedHeight(24)
            if k == "ALL":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, key=k: self._on_camelot_pill_clicked(key))
            camelot_strip.addWidget(btn)
            self.camelot_pill_buttons[k] = btn
        camelot_strip.addStretch()
        camelot_scroll.setWidget(camelot_scroll_w)
        layout.addWidget(camelot_scroll)

        # Row 3: Format & Status Filter Chips
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips = ["ALL", "MP3", "WAV", "FLAC", "4★+", "Needs Analysis"]
        for c in chips:
            btn = QPushButton(c)
            btn.setCheckable(True)
            btn.setProperty("filter_chip", "true")
            btn.setFixedHeight(22)
            if c == "ALL":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, chip=c: self._on_format_chip_clicked(chip))
            chips_row.addWidget(btn)
            self.format_chip_buttons[c] = btn
        chips_row.addStretch()
        layout.addLayout(chips_row)

        # Row 4: Action Toolbar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.btn_match_assistant = QPushButton(" Match Assistant")
        self.btn_match_assistant.setIcon(qta.icon("fa5s.bolt", color="#00E676"))
        self.btn_match_assistant.setCheckable(True)
        self.btn_match_assistant.setFixedHeight(30)
        self.btn_match_assistant.setToolTip("Harmonically match tracks in key, BPM & vibe with currently playing track")
        self.btn_match_assistant.toggled.connect(self.on_match_assistant_toggled)

        self.btn_gig_matcher = QPushButton(" Gig Overlay")
        self.btn_gig_matcher.setIcon(qta.icon("fa5s.external-link-alt", color="#00E676"))
        self.btn_gig_matcher.setFixedHeight(30)
        self.btn_gig_matcher.setToolTip("Launch live harmonic gig matcher overlay")
        self.btn_gig_matcher.clicked.connect(self.toggle_gig_matcher_overlay)

        self.btn_analyze_lib = QPushButton(" Analyze BPM/Key")
        self.btn_analyze_lib.setIcon(qta.icon("fa5s.wave-square", color="#00E5FF"))
        self.btn_analyze_lib.setFixedHeight(30)
        self.btn_analyze_lib.setToolTip("Auto-detect BPM and Camelot Key for unanalyzed tracks")
        self.btn_analyze_lib.clicked.connect(self.start_library_analysis)

        self.btn_split_mix = QPushButton(" Split Mix")
        self.btn_split_mix.setIcon(qta.icon("fa5s.cut", color="#FF9800"))
        self.btn_split_mix.setFixedHeight(30)
        self.btn_split_mix.clicked.connect(self.open_mix_splitter)

        self.btn_toggle_inspector = QPushButton(" Inspector")
        self.btn_toggle_inspector.setIcon(qta.icon("fa5s.info-circle", color="#EDEDED"))
        self.btn_toggle_inspector.setCheckable(True)
        self.btn_toggle_inspector.setChecked(True)
        self.btn_toggle_inspector.setFixedHeight(30)
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)

        self.btn_clean_lib = QPushButton(" Clean")
        self.btn_clean_lib.setIcon(qta.icon("fa5s.broom", color="#A39E9A"))
        self.btn_clean_lib.setFixedHeight(30)
        self.btn_clean_lib.clicked.connect(self.clean_library)

        action_bar.addWidget(self.btn_match_assistant)
        action_bar.addWidget(self.btn_gig_matcher)
        action_bar.addWidget(self.btn_analyze_lib)
        action_bar.addWidget(self.btn_split_mix)
        action_bar.addWidget(self.btn_toggle_inspector)
        action_bar.addStretch()
        action_bar.addWidget(self.btn_clean_lib)
        layout.addLayout(action_bar)

        self.lib_stats_label = QLabel("0 tracks · Total Duration: 0:00 · 0 MB")
        self.lib_stats_label.setStyleSheet("color: #8E8E98; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.lib_stats_label)

        self.lib_header = LibraryHeaderWidget()
        self.lib_header.sort_requested.connect(self.on_header_sort_requested)
        layout.addWidget(self.lib_header)

        # Track List + Inspector split view
        list_container = QHBoxLayout()
        list_container.setContentsMargins(0, 0, 0, 0)
        list_container.setSpacing(8)

        self.track_list = DraggableTrackList()
        self.track_list.double_clicked_track.connect(self.preview_track)
        self.track_list.itemClicked.connect(self._on_track_item_clicked)
        self.track_list.menu_requested.connect(self.show_track_context_menu)
        list_container.addWidget(self.track_list, 1)

        self.track_inspector = TrackInspectorWidget(self)
        self.track_inspector.analyze_requested.connect(lambda p: self._run_analysis_thread([p]))
        self.track_inspector.edit_tags_requested.connect(self._open_single_tag_editor)
        self.track_inspector.reveal_requested.connect(self.reveal_in_explorer)
        self.track_inspector.close_requested.connect(lambda: (self.track_inspector.hide(), self.btn_toggle_inspector.setChecked(False)))
        list_container.addWidget(self.track_inspector)

        layout.addLayout(list_container, 1)

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

        # Accent Color with Preset and Custom Color Picker
        accent_box = QHBoxLayout()
        accent_box.addWidget(QLabel("Accent Color:"))
        
        self.accent_combo = QComboBox()
        for hex_val, name in ThemeEngine.ACCENT_PRESETS:
            self.accent_combo.addItem(f"{name} ({hex_val})", hex_val)
        
        idx = self.accent_combo.findData(self.settings_manager.get('accentColor', '#C47D63'))
        if idx >= 0:
            self.accent_combo.setCurrentIndex(idx)
        self.accent_combo.currentIndexChanged.connect(self.on_accent_changed)
        accent_box.addWidget(self.accent_combo)

        self.btn_custom_color = QPushButton(" Custom Color...")
        self.btn_custom_color.setIcon(qta.icon("fa5s.palette", color="#EDEDED"))
        self.btn_custom_color.clicked.connect(self._pick_custom_color)
        accent_box.addWidget(self.btn_custom_color)
        accent_box.addStretch()
        c_layout.addLayout(accent_box)

        # Theme Selector & Library Density
        theme_box = QHBoxLayout()
        theme_box.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "OLED Black", "Soft Slate"])
        self.theme_combo.setCurrentText(self.settings_manager.get('theme', 'Dark'))
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_box.addWidget(self.theme_combo)

        theme_box.addSpacing(16)
        theme_box.addWidget(QLabel("Library Density:"))
        self.density_combo = QComboBox()
        self.density_combo.addItems(["Standard", "Compact (DJ Laptop)", "Comfortable"])
        density_val = self.settings_manager.get('density', 'standard')
        density_label_map = {"standard": "Standard", "compact": "Compact (DJ Laptop)", "comfortable": "Comfortable"}
        self.density_combo.setCurrentText(density_label_map.get(density_val, "Standard"))
        self.density_combo.currentTextChanged.connect(self._on_density_changed)
        theme_box.addWidget(self.density_combo)
        theme_box.addStretch()
        c_layout.addLayout(theme_box)

        # Window Opacity & Always on Top
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

        # Shortcuts Cheat Sheet Quick Launcher
        shortcuts_box = QHBoxLayout()
        self.btn_show_shortcuts = QPushButton(" Open Keyboard Shortcuts Cheat Sheet (F1)")
        self.btn_show_shortcuts.setIcon(qta.icon("fa5s.keyboard", color="#EDEDED"))
        self.btn_show_shortcuts.clicked.connect(self.show_shortcuts_dialog)
        shortcuts_box.addWidget(self.btn_show_shortcuts)
        shortcuts_box.addStretch()
        c_layout.addLayout(shortcuts_box)

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
        tool_box.addWidget(self.cookies_input, 2, 1)
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

        # ── Row 1: Track Info, Play Controls, Jump Buttons & Volume ──
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

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

        # Center Controls with Quick Jump Buttons
        ctrls = QHBoxLayout()
        ctrls.setSpacing(5)
        ctrls.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_skip_back_30 = QPushButton("-30s")
        self.btn_skip_back_30.setFixedSize(38, 26)
        self.btn_skip_back_30.setToolTip("Jump back 30 seconds (Shift + Left)")
        self.btn_skip_back_30.clicked.connect(lambda: self._seek_relative(-30))

        self.btn_skip_back_10 = QPushButton("-10s")
        self.btn_skip_back_10.setFixedSize(38, 26)
        self.btn_skip_back_10.setToolTip("Jump back 10 seconds (Left)")
        self.btn_skip_back_10.clicked.connect(lambda: self._seek_relative(-10))

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

        self.btn_skip_fwd_10 = QPushButton("+10s")
        self.btn_skip_fwd_10.setFixedSize(38, 26)
        self.btn_skip_fwd_10.setToolTip("Jump forward 10 seconds (Right)")
        self.btn_skip_fwd_10.clicked.connect(lambda: self._seek_relative(10))

        self.btn_skip_fwd_30 = QPushButton("+30s")
        self.btn_skip_fwd_30.setFixedSize(38, 26)
        self.btn_skip_fwd_30.setToolTip("Jump forward 30 seconds (Shift + Right)")
        self.btn_skip_fwd_30.clicked.connect(lambda: self._seek_relative(30))

        ctrls.addWidget(self.btn_skip_back_30)
        ctrls.addWidget(self.btn_skip_back_10)
        ctrls.addWidget(self.play_btn)
        ctrls.addWidget(self.stop_btn)
        ctrls.addWidget(self.btn_skip_fwd_10)
        ctrls.addWidget(self.btn_skip_fwd_30)
        top_row.addLayout(ctrls)

        # Right Meter, Pitch with Nudge & Volume with Mute
        right = QHBoxLayout()
        right.setSpacing(8)

        self.loudness_meter = LoudnessMeterWidget()
        right.addWidget(self.loudness_meter)

        pitch_box = QHBoxLayout()
        pitch_box.setSpacing(3)
        pitch_lbl = QLabel("PITCH")
        pitch_lbl.setStyleSheet("color: #8E8E98; font-size: 10px; font-weight: bold;")

        self.btn_nudge_down = QPushButton("-1%")
        self.btn_nudge_down.setFixedSize(30, 20)
        self.btn_nudge_down.setStyleSheet("font-size: 9px; padding: 0;")
        self.btn_nudge_down.setToolTip("Nudge pitch down 1%")
        self.btn_nudge_down.clicked.connect(lambda: self.pitch_slider.setValue(self.pitch_slider.value() - 1))

        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-20, 20)
        self.pitch_slider.setValue(0)
        self.pitch_slider.setFixedWidth(64)
        self.pitch_slider.setToolTip("Tempo adjustment (-20% to +20%)")
        self.pitch_slider.valueChanged.connect(self.on_pitch_changed)

        self.btn_nudge_up = QPushButton("+1%")
        self.btn_nudge_up.setFixedSize(30, 20)
        self.btn_nudge_up.setStyleSheet("font-size: 9px; padding: 0;")
        self.btn_nudge_up.setToolTip("Nudge pitch up 1%")
        self.btn_nudge_up.clicked.connect(lambda: self.pitch_slider.setValue(self.pitch_slider.value() + 1))

        self.pitch_val_lbl = QLabel("0.0%")
        self.pitch_val_lbl.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.pitch_val_lbl.setFixedWidth(38)

        self.btn_reset_pitch = QPushButton("RST")
        self.btn_reset_pitch.setFixedSize(26, 18)
        self.btn_reset_pitch.setStyleSheet("background: #24242C; color: #8E8E98; font-size: 9px; font-weight: bold; border-radius: 3px;")
        self.btn_reset_pitch.clicked.connect(lambda: self.pitch_slider.setValue(0))

        pitch_box.addWidget(pitch_lbl)
        pitch_box.addWidget(self.btn_nudge_down)
        pitch_box.addWidget(self.pitch_slider)
        pitch_box.addWidget(self.btn_nudge_up)
        pitch_box.addWidget(self.pitch_val_lbl)
        pitch_box.addWidget(self.btn_reset_pitch)
        right.addLayout(pitch_box)

        # Mute Toggle & Volume Slider
        self.btn_mute = QPushButton()
        self.btn_mute.setFixedSize(26, 26)
        self.btn_mute.setIcon(qta.icon("fa5s.volume-up", color="#EDEDED"))
        self.btn_mute.setStyleSheet("background: transparent; border: none;")
        self.btn_mute.setToolTip("Toggle Mute (M)")
        self.btn_mute.clicked.connect(self.toggle_mute)

        self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)

        right.addWidget(self.btn_mute)
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
        QShortcut(QKeySequence("M"), self, self.toggle_mute)
        # Seek
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._seek_relative(10))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._seek_relative(-10))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self._seek_relative(30))
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self._seek_relative(-30))
        # Volume
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self._adjust_volume(5))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self._adjust_volume(-5))
        # Navigation
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.stacked_widget.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.stacked_widget.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.stacked_widget.setCurrentIndex(2))
        QShortcut(QKeySequence("Ctrl+4"), self, lambda: self.stacked_widget.setCurrentIndex(3))
        QShortcut(QKeySequence("Ctrl+5"), self, lambda: self.stacked_widget.setCurrentIndex(4))
        QShortcut(QKeySequence("Ctrl+6"), self, lambda: self.stacked_widget.setCurrentIndex(5))
        # Focus search & Help
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.stacked_widget.setCurrentIndex(0), self.search_input.setFocus()))
        QShortcut(QKeySequence("F1"), self, self.show_shortcuts_dialog)
        QShortcut(QKeySequence("?"), self, self.show_shortcuts_dialog)

    def toggle_mute(self):
        if self._is_muted:
            self._is_muted = False
            vol = self._pre_mute_volume if self._pre_mute_volume > 0 else 80
            self.audio_output.setVolume(vol / 100.0)
            self.volume_slider.setValue(vol)
            self.btn_mute.setIcon(qta.icon("fa5s.volume-up", color="#EDEDED"))
        else:
            self._is_muted = True
            self._pre_mute_volume = self.volume_slider.value()
            self.audio_output.setVolume(0.0)
            self.volume_slider.setValue(0)
            self.btn_mute.setIcon(qta.icon("fa5s.volume-mute", color="#FF3B30"))

    def show_shortcuts_dialog(self):
        dlg = KeyboardShortcutsDialog(self)
        dlg.exec()

    def _pick_custom_color(self):
        curr_hex = self.settings_manager.get('accentColor', '#C47D63')
        color = QColorDialog.getColor(QColor(curr_hex), self, "Select DJ Console Accent Color")
        if color.isValid():
            hex_val = color.name()
            self.settings_manager.set('accentColor', hex_val)
            self.apply_theme()
            if self.mini_player:
                self.mini_player.set_accent_color(hex_val)
            self.toast_manager.show_toast(f"Accent color updated: {hex_val}", toast_type="success")

    def _on_density_changed(self, text):
        mapping = {"Standard": "standard", "Compact (DJ Laptop)": "compact", "Comfortable": "comfortable"}
        val = mapping.get(text, "standard")
        self.settings_manager.set('density', val)
        self.apply_theme()
        self.refresh_library()

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
        
        trending_tracks = [
            {
                'id': 'lOtl4W_ZCu4',
                'title': 'Mau P - Drugs From Amsterdam',
                'artist': 'Mau P',
                'duration': '5:24',
                'durationSecs': 324,
                'url': 'https://www.youtube.com/watch?v=lOtl4W_ZCu4',
                'thumbnail': 'https://img.youtube.com/vi/lOtl4W_ZCu4/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'u31thuMehjM',
                'title': 'FISHER - Losing It',
                'artist': 'FISHER',
                'duration': '4:09',
                'durationSecs': 249,
                'url': 'https://www.youtube.com/watch?v=u31thuMehjM',
                'thumbnail': 'https://img.youtube.com/vi/u31thuMehjM/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': '5BqjhUmldDc',
                'title': 'John Summit & Hayla - Where You Are',
                'artist': 'John Summit & Hayla',
                'duration': '3:56',
                'durationSecs': 236,
                'url': 'https://www.youtube.com/watch?v=5BqjhUmldDc',
                'thumbnail': 'https://img.youtube.com/vi/5BqjhUmldDc/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'tyd-Vs0MHH4',
                'title': 'Peggy Gou - (It Goes Like) Nanana',
                'artist': 'Peggy Gou',
                'duration': '6:08',
                'durationSecs': 368,
                'url': 'https://www.youtube.com/watch?v=tyd-Vs0MHH4',
                'thumbnail': 'https://img.youtube.com/vi/tyd-Vs0MHH4/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'Q22MCFC0CP0',
                'title': 'Fred again.. x Swedish House Mafia - Turn On The Lights again..',
                'artist': 'Fred again..',
                'duration': '4:25',
                'durationSecs': 265,
                'url': 'https://www.youtube.com/watch?v=Q22MCFC0CP0',
                'thumbnail': 'https://img.youtube.com/vi/Q22MCFC0CP0/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'OvW5y3lZ7rc',
                'title': 'MK, Dom Dolla - Rhyme Dust',
                'artist': 'MK, Dom Dolla',
                'duration': '3:02',
                'durationSecs': 182,
                'url': 'https://www.youtube.com/watch?v=OvW5y3lZ7rc',
                'thumbnail': 'https://img.youtube.com/vi/OvW5y3lZ7rc/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'ahSdkFlepJg',
                'title': 'Chris Lake ft. Alexis Roberts - Turn Off The Lights',
                'artist': 'Chris Lake',
                'duration': '3:33',
                'durationSecs': 213,
                'url': 'https://www.youtube.com/watch?v=ahSdkFlepJg',
                'thumbnail': 'https://img.youtube.com/vi/ahSdkFlepJg/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'AthmfqjAtQE',
                'title': 'Mochakk - Jealous',
                'artist': 'Mochakk',
                'duration': '4:17',
                'durationSecs': 257,
                'url': 'https://www.youtube.com/watch?v=AthmfqjAtQE',
                'thumbnail': 'https://img.youtube.com/vi/AthmfqjAtQE/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': '4cCi6-16HR4',
                'title': 'James Hype, Miggy Dela Rosa - Ferrari',
                'artist': 'James Hype',
                'duration': '3:06',
                'durationSecs': 186,
                'url': 'https://www.youtube.com/watch?v=4cCi6-16HR4',
                'thumbnail': 'https://img.youtube.com/vi/4cCi6-16HR4/hqdefault.jpg',
                'source': 'YouTube'
            },
            {
                'id': 'o5PVzsGRbm8',
                'title': 'CamelPhat & Elderbrook - Cola',
                'artist': 'CamelPhat',
                'duration': '3:44',
                'durationSecs': 224,
                'url': 'https://www.youtube.com/watch?v=o5PVzsGRbm8',
                'thumbnail': 'https://img.youtube.com/vi/o5PVzsGRbm8/hqdefault.jpg',
                'source': 'YouTube'
            }
        ]
        self.on_search_results(trending_tracks)

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

    def _on_thumb_downloaded(self, card, local_path):
        if os.path.exists(local_path):
            card.set_thumbnail(local_path)

    def on_search_results(self, results):
        while self.search_results_layout.count() > 1:
            item = self.search_results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.search_cards.clear()

        for res in results:
            card = SearchResultCard(res, default_format=self.settings_manager.get('format', 'mp3'))
            card.download_requested.connect(self.start_download)
            card.preview_requested.connect(self.preview_track)
            self.search_results_layout.insertWidget(self.search_results_layout.count() - 1, card)
            if res.get('url'):
                self.search_cards[res['url']] = card

            # Asynchronously download and set real thumbnail artwork
            thumb_url = res.get('thumbnail')
            vid_id = res.get('id') or (res.get('url', '').split('v=')[-1] if 'v=' in res.get('url', '') else '')
            if thumb_url or vid_id:
                t_loader = ThumbnailDownloader(vid_id, thumb_url, parent=self)
                t_loader.downloaded.connect(lambda vid, path, c=card: self._on_thumb_downloaded(c, path))
                t_loader.start()
                self._running_threads.append(t_loader)
                t_loader.downloaded.connect(lambda vid, path, c=card: self._on_thumb_downloaded(c, path))
                t_loader.start()
                self._running_threads.append(t_loader)

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
        if hasattr(self, 'page_set_builder'):
            self.page_set_builder.set_library_tracks(self.library_tracks)

        # Auto-trigger background analysis for unanalyzed tracks
        if unanalyzed_count > 0 and not self._analysis_in_progress:
            self.start_library_analysis(force_all=False)

    def _toggle_inspector(self):
        if self.btn_toggle_inspector.isChecked():
            self.track_inspector.show()
        else:
            self.track_inspector.hide()

    def _on_track_item_clicked(self, item):
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.track_inspector.set_track(track)

    def _open_single_tag_editor(self, file_path):
        dlg = MetadataEditorDialog(file_path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_library()

    def reveal_in_explorer(self, file_path):
        if sys.platform == 'win32' and os.path.exists(file_path):
            subprocess.run(['explorer', '/select,', os.path.normpath(file_path)])

    def _on_camelot_pill_clicked(self, key):
        self.active_camelot_key = key
        for k, btn in self.camelot_pill_buttons.items():
            btn.setChecked(k == key)
        self.filter_library()

    def _on_format_chip_clicked(self, chip):
        self.active_format_filter = chip
        for c, btn in self.format_chip_buttons.items():
            btn.setChecked(c == chip)
        self.filter_library()

    def filter_library(self):
        self.track_list.clear()
        query = self.lib_search_input.text().lower()
        sort_by = self.lib_sort_combo.currentText()
        is_matching = self.btn_match_assistant.isChecked() and self.player_track is not None

        filtered = []
        for t in self.library_tracks:
            # Query match
            if query and query not in t['title'].lower() and query not in t['artist'].lower():
                continue
            
            # Camelot Key filter
            if self.active_camelot_key != "ALL":
                track_key = str(t.get('key', '')).strip().upper()
                if track_key != self.active_camelot_key:
                    continue

            # Format/Status filter
            if self.active_format_filter == "MP3" and t.get('format', '').lower() != 'mp3':
                continue
            elif self.active_format_filter == "WAV" and t.get('format', '').lower() != 'wav':
                continue
            elif self.active_format_filter == "FLAC" and t.get('format', '').lower() != 'flac':
                continue
            elif self.active_format_filter == "4★+" and t.get('rating', 0) < 4:
                continue
            elif self.active_format_filter == "Needs Analysis" and (t.get('bpm') and t.get('key')):
                continue

            filtered.append(t)

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
        if not track:
            return

        local_path = track.get('path')
        if local_path and os.path.exists(local_path):
            self.player_track = track
            self.media_player.setSource(QUrl.fromLocalFile(local_path))
            self.media_player.play()
            self.player_title_label.setText(track.get('title', 'Unknown'))
            self.player_artist_label.setText(track.get('artist', 'Unknown'))
            self.equalizer.set_playing(True)
            self.play_btn.setIcon(qta.icon("fa5s.pause", color="#FFFFFF"))

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
                self.mini_player.update_track(track.get('title', ''), track.get('artist', ''), True)

            if self.btn_match_assistant.isChecked():
                self.filter_library()

            cache_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate', 'waveforms')
            wf_thread = WaveformGeneratorThread(
                local_path, cache_dir,
                ffmpeg_path=self.settings_manager.get('ffmpegPath', 'ffmpeg'),
                accent_color=self.settings_manager.get('accentColor', '#FF5500')
            )
            wf_thread.waveform_ready.connect(self.on_waveform_ready)
            wf_thread.peaks_ready.connect(self.on_peaks_ready)
            wf_thread.loudness_ready.connect(self.on_loudness_ready)
            wf_thread.start()
            self._running_threads.append(wf_thread)
            return

        # If online / not downloaded track (has URL)
        url = track.get('url')
        if url:
            self.player_track = track
            self.player_title_label.setText(track.get('title', 'Buffering...'))
            self.player_artist_label.setText(f"Streaming: {track.get('artist', 'Online')}")
            self.equalizer.set_playing(True)
            self.toast_manager.show_toast(f"Connecting audio stream for: {track.get('title', '')}...", toast_type="info")

            resolver = StreamResolverThread(
                track,
                ytdlp_path=self.settings_manager.get('ytdlpPath', 'yt-dlp'),
                cookies_path=self.settings_manager.get('cookiesPath', ''),
                parent=self
            )
            resolver.stream_ready.connect(self._on_stream_ready)
            resolver.error_occurred.connect(self._on_stream_error)
            resolver.start()
            self._running_threads.append(resolver)

    def _on_stream_ready(self, track, stream_url):
        if self.player_track and self.player_track.get('url') == track.get('url'):
            self.media_player.setSource(QUrl(stream_url))
            self.media_player.play()
            self.play_btn.setIcon(qta.icon("fa5s.pause", color="#FFFFFF"))
            self.equalizer.set_playing(True)
            self.player_title_label.setText(track.get('title', 'Playing'))
            self.player_artist_label.setText(track.get('artist', 'Online Stream'))
            if self._glow_seq.state() != QSequentialAnimationGroup.State.Running:
                self._glow_seq.start()

    def _on_stream_error(self, err_msg):
        self.equalizer.set_playing(False)
        self.toast_manager.show_toast(err_msg, toast_type="error")

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
        add_to_setlist = menu.addAction("Add to Active Setlist")
        analyze_track = menu.addAction("Analyze BPM & Key Tags")
        edit_meta = menu.addAction("Edit Metadata Tags...")
        bulk_edit = None
        if len(selected_paths) > 1:
            bulk_edit = menu.addAction(f"Bulk Edit {len(selected_paths)} Selected Tracks...")

        reveal = menu.addAction("Reveal in File Explorer")
        delete = menu.addAction("Delete Track File")

        action = menu.exec(pos)
        if action == add_to_setlist:
            targets = selected_paths if selected_paths else [track['path']]
            self.page_set_builder.add_tracks_to_setlist(targets)
        elif action == analyze_track:
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
            self.btn_set_builder.setText("")
            self.btn_queue.setText("")
            self.btn_settings.setText("")
            self.btn_mini_player.setText("")
        else:
            self.sidebar.setFixedWidth(200)
            self.btn_toggle_sidebar.setIcon(qta.icon("fa5s.angle-double-left", color="#A39E9A"))
            self.btn_search.setText("  Search")
            self.btn_library.setText("  Library")
            self.btn_crates.setText("  Crates")
            self.btn_set_builder.setText("  Set Builder")
            self.btn_queue.setText("  Queue")
            self.btn_settings.setText("  Settings")
            self.btn_mini_player.setText(" Mini Player")

    def on_pitch_changed(self, val):
        rate = 1.0 + (val / 100.0)
        self.media_player.setPlaybackRate(rate)
        sign = "+" if val > 0 else ""
        self.pitch_val_lbl.setText(f"{sign}{val}%")

        if self.player_track:
            bpm = self.player_track.get('bpm', '')
            key = self.player_track.get('key', '')
            pitch_info = CamelotMatcher.calculate_pitch_shifted_state(bpm, key, val)
            
            base_artist = self.player_track.get('artist', '') or 'DJ Crate Audio Previewer'
            if pitch_info.get('bpm_str') and val != 0:
                transposed_badge = f" · {pitch_info['transposed_key']} ({pitch_info['semitones']:+.1f}st)" if pitch_info['is_transposed'] else (f" · Key {key}" if key else "")
                self.player_artist_label.setText(f"{base_artist}  [{pitch_info['bpm_str']}{transposed_badge}]")
            else:
                self.player_artist_label.setText(base_artist)

            ObsOverlayWriter.update_now_playing(
                self.player_track.get('title', ''),
                base_artist,
                pitch_info.get('bpm_str', '').replace(' BPM', '') or bpm,
                pitch_info.get('transposed_key', key),
                accent_color=self.settings_manager.get('accentColor', '#FF5500')
            )

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
        smart_crates = self.settings_manager.get('smartCrates', {})
        paths = []
        if target_crate in crates:
            paths = crates.get(target_crate, [])
        elif target_crate in smart_crates:
            for i in range(self.crate_track_list.count()):
                item = self.crate_track_list.item(i)
                t = item.data(Qt.ItemDataRole.UserRole) if item else None
                if t and t.get('path'):
                    paths.append(t['path'])

        if not paths:
            self.toast_manager.show_toast(f"Crate '{target_crate}' has no tracks to export.", toast_type="info")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Export Crate '{target_crate}'", f"{target_crate}.m3u8",
            "M3U8 Playlist (*.m3u8);;M3U Playlist (*.m3u);;CSV Tracklist (*.csv);;Text Tracklist (*.txt)"
        )
        if save_path:
            try:
                ext = os.path.splitext(save_path)[1].lower()
                if ext == '.csv':
                    import csv
                    with open(save_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["#", "Title", "Artist", "BPM", "Key", "Duration", "Genre", "Year", "Path"])
                        for idx, p in enumerate(paths, 1):
                            t = self._find_library_track(p) or {}
                            writer.writerow([
                                idx,
                                t.get('title', os.path.basename(p)),
                                t.get('artist', 'Unknown Artist'),
                                t.get('bpm', ''),
                                t.get('key', ''),
                                t.get('duration_str', ''),
                                t.get('genre', ''),
                                t.get('year', ''),
                                os.path.abspath(p)
                            ])
                elif ext == '.txt':
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(f"=== DJ Crate Tracklist: {target_crate} ===\n")
                        f.write(f"Total Tracks: {len(paths)}\n\n")
                        for idx, p in enumerate(paths, 1):
                            t = self._find_library_track(p) or {}
                            title = t.get('title', os.path.basename(p))
                            artist = t.get('artist', 'Unknown Artist')
                            bpm = f" [{t.get('bpm')} BPM]" if t.get('bpm') else ""
                            key = f" [{t.get('key')}]" if t.get('key') else ""
                            f.write(f"{idx:02d}. {artist} - {title}{bpm}{key}\n")
                else:
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
        field = rule.get('field', '').lower().strip()
        op = rule.get('operator', 'contains').strip()
        val = str(rule.get('value', '')).lower().strip()

        for track in self.library_tracks:
            match = False
            raw_track_val = track.get(field, '')
            track_val = str(raw_track_val).lower().strip()

            if op == 'compatible_with' or (field == 'key' and op == 'compatible_with'):
                target_key = rule.get('value', '').strip().upper()
                track_key = str(track.get('key', '')).strip().upper()
                if track_key and target_key:
                    compat = CamelotMatcher.get_compatible_keys(target_key)
                    if track_key in compat.get('all_keys', []):
                        match = True
            elif op == 'contains':
                if val in track_val:
                    match = True
            elif op == '=':
                if track_val == val:
                    match = True
            elif op == '>=':
                try:
                    t_num = float(raw_track_val)
                    v_num = float(val)
                    if t_num >= v_num:
                        match = True
                except (ValueError, TypeError):
                    if track_val >= val:
                        match = True
            elif op == '<=':
                try:
                    t_num = float(raw_track_val)
                    v_num = float(val)
                    if t_num <= v_num:
                        match = True
                except (ValueError, TypeError):
                    if track_val <= val:
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
        create_setlist_action = menu.addAction("Create Setlist from Crate...")
        serato_action = menu.addAction("Sync to Serato (.crate)...")
        export_action = menu.addAction("Export Crate to M3U Playlist...")
        rename_action = menu.addAction("Rename Crate")
        delete_action = menu.addAction("Delete Crate")
        action = menu.exec(pos)
        if action == create_setlist_action:
            crates = self.settings_manager.get('crates', {})
            paths = crates.get(crate_name, [])
            if paths:
                new_id = self.settings_manager.create_setlist(f"Set - {crate_name}")
                self.settings_manager.set_setlist_tracks(new_id, paths)
                self.page_set_builder.load_setlists()
                self.page_set_builder.active_setlist_id = new_id
                self.page_set_builder.refresh_active_setlist()
                self.toast_manager.show_toast(f"Created setlist from crate '{crate_name}'!", toast_type="success")
            else:
                self.toast_manager.show_toast(f"Crate '{crate_name}' is empty.", toast_type="info")
        elif action == serato_action:
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
