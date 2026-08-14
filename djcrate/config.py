import os
import json
from datetime import datetime
from djcrate.logger import logger
from djcrate.database import DatabaseManager

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
        
        self.db_path = os.path.join(self.settings_dir, 'djcrate.db')
        self.db = DatabaseManager(self.db_path)
        
        self.settings_path = os.path.join(self.settings_dir, 'settings.json')
        
        self.migrate_from_json()

        # Ensure music path exists
        music_path = self.get('musicPath', os.path.join(os.path.expanduser('~'), 'Music', 'DJ Crate'))
        music_path = os.path.abspath(music_path)
        try:
            os.makedirs(music_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create music directory at {music_path}: {e}")
            fallback_dir = os.path.join(self.settings_dir, 'Music')
            os.makedirs(fallback_dir, exist_ok=True)
            music_path = fallback_dir
            
        self.set('musicPath', music_path)

    def migrate_from_json(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    old_settings = json.load(f)
                    
                # Migrate settings
                for k, v in old_settings.items():
                    if k not in ['crates', 'smartCrates', 'history', 'trackMetadata', 'ratings']:
                        self.set(k, v)
                        
                # Migrate crates
                for name, tracks in old_settings.get('crates', {}).items():
                    self.db.add_crate(name)
                    for t in tracks:
                        self.db.add_track_to_crate(name, t)
                        
                for name, rules in old_settings.get('smartCrates', {}).items():
                    self.db.add_smart_crate(name, rules)
                    
                # Migrate history
                for h in reversed(old_settings.get('history', [])):
                    self.db.add_history_entry(
                        h.get('title'), h.get('url'), h.get('format'), 
                        h.get('status'), h.get('file_path'), h.get('date')
                    )
                    
                # Migrate ratings and metadata
                for fp, rating in old_settings.get('ratings', {}).items():
                    self.db.upsert_track(fp, {'rating': rating})
                    
                for fp, meta in old_settings.get('trackMetadata', {}).items():
                    self.db.upsert_track(fp, meta)
                    
                # Rename to backup so we don't migrate again
                os.rename(self.settings_path, self.settings_path + '.bak')
                logger.info("Successfully migrated settings.json to SQLite database")
            except Exception as e:
                logger.error(f"Error migrating from JSON: {e}")

    def load(self):
        pass # Replaced by DB

    def save(self):
        pass # Replaced by DB auto-commit

    def get(self, key, default=None):
        if key == 'crates':
            return self.db.get_manual_crates()
        elif key == 'smartCrates':
            return self.db.get_smart_crates()
        elif key == 'history':
            return self.db.get_history()
        
        # Default settings if none in DB
        defaults = {
            'format': 'mp3',
            'maxConcurrent': 3,
            'volume': 80,
            'accentColor': self.DEFAULT_ACCENT,
            'theme': 'Dark',
            'trimSilence': False,
            'autoPlayOnLaunch': False,
            'startupView': 'Library'
        }
        val = self.db.get_setting(key, None)
        if val is None:
            return default if default is not None else defaults.get(key)
        return val

    def set(self, key, value):
        if key == 'crates':
            # Handle full dict replacement (fallback for legacy code)
            pass 
        elif key == 'smartCrates':
            pass
        else:
            self.db.set_setting(key, value)

    def get_rating(self, track_key: str) -> int:
        track = self.db.get_track(track_key)
        return track.get('rating', 0)

    def set_rating(self, track_key: str, rating: int):
        self.db.upsert_track(track_key, {'rating': rating})

    def get_track_meta(self, file_path: str) -> dict:
        return self.db.get_track(file_path)

    def set_track_meta(self, file_path: str, data: dict):
        self.db.upsert_track(file_path, data)

    def add_history_entry(self, title, url, fmt, status, file_path=None):
        date = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.db.add_history_entry(title, url, fmt, status, file_path or '', date)

    def clear_history(self):
        self.db.clear_history()

    # Setlists
    def get_setlists(self):
        return self.db.get_all_setlists()

    def get_setlist(self, setlist_id):
        return self.db.get_setlist(setlist_id)

    def create_setlist(self, name, notes=""):
        return self.db.create_setlist(name, notes)

    def update_setlist(self, setlist_id, name=None, notes=None):
        self.db.update_setlist(setlist_id, name, notes)

    def delete_setlist(self, setlist_id):
        return self.db.delete_setlist(setlist_id)

    def duplicate_setlist(self, setlist_id, new_name):
        return self.db.duplicate_setlist(setlist_id, new_name)

    def set_setlist_tracks(self, setlist_id, track_paths):
        self.db.set_setlist_tracks(setlist_id, track_paths)

    def add_track_to_setlist(self, setlist_id, file_path, position=None, notes="", transition_type=""):
        self.db.add_track_to_setlist(setlist_id, file_path, position, notes, transition_type)

    def remove_track_from_setlist(self, setlist_id, position):
        self.db.remove_track_from_setlist(setlist_id, position)

    def reorder_setlist_track(self, setlist_id, old_pos, new_pos):
        self.db.reorder_setlist_track(setlist_id, old_pos, new_pos)

    def update_setlist_item(self, setlist_id, position, notes=None, transition_type=None):
        self.db.update_setlist_item(setlist_id, position, notes, transition_type)
