import sqlite3
import os
import json
from djcrate.logger import logger

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            
            # Key-Value settings table
            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Tracks table (for metadata and caching)
            c.execute('''
                CREATE TABLE IF NOT EXISTS tracks (
                    file_path TEXT PRIMARY KEY,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    bpm REAL,
                    key TEXT,
                    rating INTEGER DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Crates table
            c.execute('''
                CREATE TABLE IF NOT EXISTS crates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    is_smart BOOLEAN DEFAULT 0,
                    smart_rules TEXT
                )
            ''')
            
            # Crate Tracks mapping table
            c.execute('''
                CREATE TABLE IF NOT EXISTS crate_tracks (
                    crate_id INTEGER,
                    file_path TEXT,
                    FOREIGN KEY(crate_id) REFERENCES crates(id),
                    FOREIGN KEY(file_path) REFERENCES tracks(file_path),
                    UNIQUE(crate_id, file_path)
                )
            ''')
            
            # History table
            c.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    url TEXT,
                    format TEXT,
                    status TEXT,
                    file_path TEXT,
                    date TEXT
                )
            ''')
            
            conn.commit()

    def get_setting(self, key, default=None):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = c.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except:
                    return row[0]
            return default

    def set_setting(self, key, value):
        with self._get_connection() as conn:
            c = conn.cursor()
            val_str = json.dumps(value)
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))
            conn.commit()

    # Track Metadata
    def get_track(self, file_path):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM tracks WHERE file_path = ?", (file_path,))
            row = c.fetchone()
            return dict(row) if row else {}

    def upsert_track(self, file_path, data: dict):
        with self._get_connection() as conn:
            c = conn.cursor()
            
            existing = self.get_track(file_path)
            existing.update(data)
            
            c.execute('''
                INSERT OR REPLACE INTO tracks 
                (file_path, title, artist, album, bpm, key, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                existing.get('title'),
                existing.get('artist'),
                existing.get('album'),
                existing.get('bpm'),
                existing.get('key'),
                existing.get('rating', 0)
            ))
            conn.commit()

    # Crates
    def get_manual_crates(self):
        crates = {}
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM crates WHERE is_smart = 0")
            for crate_id, name in c.fetchall():
                c.execute("SELECT file_path FROM crate_tracks WHERE crate_id = ?", (crate_id,))
                crates[name] = [r[0] for r in c.fetchall()]
        return crates

    def get_smart_crates(self):
        crates = {}
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT name, smart_rules FROM crates WHERE is_smart = 1")
            for name, rules_json in c.fetchall():
                try:
                    crates[name] = json.loads(rules_json)
                except:
                    pass
        return crates

    def add_crate(self, name):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO crates (name, is_smart) VALUES (?, 0)", (name,))
            conn.commit()

    def add_smart_crate(self, name, rules_dict):
        with self._get_connection() as conn:
            c = conn.cursor()
            rules_json = json.dumps(rules_dict)
            c.execute("INSERT OR REPLACE INTO crates (name, is_smart, smart_rules) VALUES (?, 1, ?)", (name, rules_json))
            conn.commit()

    def rename_crate(self, old_name, new_name):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE crates SET name = ? WHERE name = ?", (new_name, old_name))
            conn.commit()

    def delete_crate(self, name):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM crates WHERE name = ?", (name,))
            row = c.fetchone()
            if row:
                c.execute("DELETE FROM crate_tracks WHERE crate_id = ?", (row[0],))
                c.execute("DELETE FROM crates WHERE id = ?", (row[0],))
                conn.commit()

    def add_track_to_crate(self, crate_name, file_path):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM crates WHERE name = ?", (crate_name,))
            row = c.fetchone()
            if row:
                c.execute("INSERT OR IGNORE INTO tracks (file_path) VALUES (?)", (file_path,))
                c.execute("INSERT OR IGNORE INTO crate_tracks (crate_id, file_path) VALUES (?, ?)", (row[0], file_path))
                conn.commit()

    # History
    def get_history(self, limit=200):
        history = []
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))
            for row in c.fetchall():
                history.append(dict(row))
        return history

    def add_history_entry(self, title, url, fmt, status, file_path, date):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO history (title, url, format, status, file_path, date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, url, fmt, status, file_path, date))
            conn.commit()

    def clear_history(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM history")
            conn.commit()
