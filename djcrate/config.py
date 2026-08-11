import os
import json
from datetime import datetime
from djcrate.logger import logger

class SettingsManager:
    DEFAULT_ACCENT = "#C47D63"

    ACCENT_PRESETS = [
        ("#C47D63", "Rust Orange"),
        ("#00E5FF", "Cyber Cyan"),
        ("#00E676", "Emerald Green"),
        ("#D500F9", "Neon Purple"),
        ("#FFD600", "Electric Gold"),
        ("#FF3D00", "Crimson Red"),
    ]

    def __init__(self):
        self.settings_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate')
        os.makedirs(self.settings_dir, exist_ok=True)
        self.settings_path = os.path.join(self.settings_dir, 'settings.json')

        default_music = os.path.join(os.path.expanduser('~'), 'Music', 'DJ Crate')
        self.settings = {
            'musicPath': default_music,
            'format': 'mp3',
            'crates': {},
            'smartCrates': {},
            'maxConcurrent': 3,
            'history': [],
            'volume': 80,
            'accentColor': self.DEFAULT_ACCENT,
            'theme': 'Dark',
            'ratings': {},
            'trackMetadata': {},
            'trimSilence': False,
            'autoPlayOnLaunch': False,
            'startupView': 'Library'
        }
        self.load()

    def load(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
        self.settings['musicPath'] = os.path.abspath(self.settings['musicPath'])
        os.makedirs(self.settings['musicPath'], exist_ok=True)

    def save(self):
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_rating(self, track_key: str) -> int:
        ratings = self.settings.get('ratings', {})
        return ratings.get(track_key, 0)

    def set_rating(self, track_key: str, rating: int):
        ratings = self.settings.get('ratings', {})
        ratings[track_key] = rating
        self.settings['ratings'] = ratings
        self.save()

    def get_track_meta(self, file_path: str) -> dict:
        meta = self.settings.get('trackMetadata', {})
        return meta.get(file_path, {})

    def set_track_meta(self, file_path: str, data: dict):
        meta = self.settings.get('trackMetadata', {})
        current = meta.get(file_path, {})
        current.update(data)
        meta[file_path] = current
        self.settings['trackMetadata'] = meta
        self.save()

    def add_history_entry(self, title, url, fmt, status, file_path=None):
        history = self.settings.get('history', [])
        history.insert(0, {
            'title': title,
            'url': url,
            'format': fmt,
            'status': status,
            'file_path': file_path or '',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        self.settings['history'] = history[:200]
        self.save()

    def clear_history(self):
        self.settings['history'] = []
        self.save()
