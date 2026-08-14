import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, Optional, List
import datetime

from sqlalchemy import create_engine, event, String, Integer, DateTime, ForeignKey, JSON, func, select
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.pool import QueuePool, StaticPool

from djcrate.logger import logger

# --- Custom Database Exceptions ---

class DatabaseError(Exception):
    """Base exception for database operations."""
    def __init__(self, message: str = "Ein Datenbankfehler ist aufgetreten"):
        self.message = message
        super().__init__(self.message)

class DuplicateVideoError(DatabaseError):
    """
    Exception thrown when a duplicate video is added to a playlist.
    Simulates an HTTP 409 Conflict response.
    """
    def __init__(self, message: str = "Das Video ist bereits in dieser Playlist vorhanden"):
        self.message = message
        self.status_code = 409
        super().__init__(message)

class Base(DeclarativeBase):
    pass

# --- SQLAlchemy Models ---

class Track(Base):
    """
    ORM Model representing a music track / video in the library.
    Contains metadata like title, artist, bpm, genre, file_path, duration, and music_key.
    """
    __tablename__ = "tracks"
    
    video_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    artist: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    music_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    history_entries: Mapped[List["HistoryEntry"]] = relationship(
        "HistoryEntry", back_populates="track", cascade="all, delete-orphan"
    )

    @property
    def id(self) -> str:
        """Alias property for video_id to satisfy generic track identifier access."""
        return self.video_id

class Playlist(Base):
    """ORM Model representing a video playlist."""
    __tablename__ = "playlists"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

class PlaylistTrack(Base):
    """ORM association table mapping playlists to videos."""
    __tablename__ = "playlist_tracks"
    
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.video_id", ondelete="CASCADE"), primary_key=True)

class HistoryEntry(Base):
    """ORM Model representing the play history of tracks."""
    __tablename__ = "history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.video_id", ondelete="CASCADE"))
    played_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    track: Mapped["Track"] = relationship("Track", back_populates="history_entries")

class WidgetState(Base):
    """
    ORM Model representing persistent state of UI widgets.
    """
    __tablename__ = "widget_states"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widget_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    state: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

class DJSessionHistory(Base):
    """
    ORM Model representing DJ session history events.
    """
    __tablename__ = "dj_session_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

class Setlist(Base):
    """
    ORM Model representing a curated DJ setlist.
    """
    __tablename__ = "setlists"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    items: Mapped[List["SetlistItem"]] = relationship(
        "SetlistItem", back_populates="setlist", cascade="all, delete-orphan", order_by="SetlistItem.position"
    )

class SetlistItem(Base):
    """
    ORM Model representing an ordered track within a DJ setlist.
    """
    __tablename__ = "setlist_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
    transition_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="")
    cue_in_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    cue_out_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    
    setlist: Mapped["Setlist"] = relationship("Setlist", back_populates="items")

# --- Database Initialization & Connection Pooling ---

_engine_cache = {}

POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))

def init_db(db_path: str = "database.db") -> Any:
    """
    Initializes the database connection pool and creates tables if they don't exist.
    Configures QueuePool with pre-ping for SQLite file DBs and StaticPool for :memory:.
    Activates SQLite PRAGMA foreign_keys = ON.
    Returns the SQLAlchemy Engine instance.
    """
    if db_path in _engine_cache:
        engine = _engine_cache[db_path]
    else:
        db_url = f"sqlite:///{db_path}" if db_path != ":memory:" else "sqlite:///:memory:"
        if db_path == ":memory:":
            engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False
            )
        else:
            engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=QueuePool,
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_recycle=POOL_RECYCLE,
                pool_pre_ping=True,
                echo=False
            )
        
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            if type(dbapi_connection).__module__ == "sqlite3":
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.close()
        
        _engine_cache[db_path] = engine

    Base.metadata.create_all(bind=engine)
    return engine

@contextmanager
def get_db_connection(db_path: str = "database.db") -> Generator[Session, None, None]:
    """
    Provides a clean, thread-safe SQLAlchemy session using connection pooling.
    Handles automatic commit, rollback on error, error logging, and session cleanup.
    """
    engine = init_db(db_path)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = None
    try:
        db = session_factory()
        yield db
    except (DuplicateVideoError, ValueError):
        if db is not None:
            db.rollback()
        raise
    except SQLAlchemyError as e:
        if db is not None:
            db.rollback()
        logger.error(f"Database transaction error: {e}", exc_info=True)
        raise DatabaseError(f"Database operation failed: {e}") from e
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error(f"Unexpected transaction error: {e}", exc_info=True)
        raise
    finally:
        if db is not None:
            db.close()

# Alias for backwards compatibility
get_db = get_db_connection

# --- Track & History CRUD Functions ---

def create_track(
    video_id: str,
    title: str,
    artist: Optional[str] = None,
    bpm: Optional[int] = None,
    genre: Optional[str] = None,
    file_path: Optional[str] = None,
    duration: Optional[int] = None,
    music_key: Optional[str] = None,
    db_path: str = "database.db"
) -> Track:
    """Creates and saves a new track in the database with validation."""
    if not video_id or not isinstance(video_id, str) or not video_id.strip():
        raise ValueError("A valid non-empty 'video_id' / 'id' is required.")
    if not title or not isinstance(title, str) or not title.strip():
        raise ValueError("A valid non-empty 'title' is required.")
    if bpm is not None and (not isinstance(bpm, int) or bpm <= 0):
        raise ValueError("'bpm' must be a positive integer.")

    with get_db_connection(db_path) as db:
        new_track = Track(
            video_id=video_id.strip(),
            title=title.strip(),
            artist=artist.strip() if artist else None,
            bpm=bpm,
            genre=genre.strip() if genre else None,
            file_path=file_path.strip() if file_path else None,
            duration=duration,
            music_key=music_key.strip() if music_key else None
        )
        db.add(new_track)
        db.commit()
        db.refresh(new_track)
        db.expunge(new_track)
        return new_track

def get_track_by_id(video_id: str, db_path: str = "database.db") -> Optional[Track]:
    """Retrieves a single track by its video ID."""
    if not video_id:
        return None
    with get_db_connection(db_path) as db:
        track = db.get(Track, video_id)
        if track:
            db.expunge(track)
        return track

def get_all_tracks(db_path: str = "database.db") -> List[Track]:
    """Retrieves all tracks stored in the library."""
    with get_db_connection(db_path) as db:
        tracks = list(db.scalars(select(Track)).all())
        for track in tracks:
            db.expunge(track)
        return tracks

def update_track(video_id: str, db_path: str = "database.db", **kwargs: Any) -> Optional[Track]:
    """Updates a track's information by video ID."""
    with get_db_connection(db_path) as db:
        track = db.get(Track, video_id)
        if track:
            for key, value in kwargs.items():
                if hasattr(track, key):
                    setattr(track, key, value)
            db.commit()
            db.refresh(track)
            db.expunge(track)
        return track

def delete_track(video_id: str, db_path: str = "database.db") -> bool:
    """Safely deletes a track by its video ID."""
    if not video_id:
        return False
    with get_db_connection(db_path) as db:
        track = db.get(Track, video_id)
        if track:
            db.delete(track)
            db.commit()
            return True
        return False

def add_to_history(video_id: str, status: Optional[str] = None, db_path: str = "database.db") -> HistoryEntry:
    """Adds a track to the play history."""
    with get_db_connection(db_path) as db:
        entry = HistoryEntry(track_id=video_id, status=status)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        db.expunge(entry)
        return entry

def get_history(limit: int = 50, db_path: str = "database.db") -> List[HistoryEntry]:
    """Retrieves the play history, ordered chronologically descending."""
    with get_db_connection(db_path) as db:
        stmt = select(HistoryEntry).order_by(HistoryEntry.played_at.desc()).limit(limit)
        entries = list(db.scalars(stmt).all())
        for entry in entries:
            db.expunge(entry)
        return entries

def delete_history_entry(history_id: int, db_path: str = "database.db") -> bool:
    """Deletes a specific history entry."""
    with get_db_connection(db_path) as db:
        entry = db.get(HistoryEntry, history_id)
        if entry:
            db.delete(entry)
            db.commit()
            return True
        return False

def clear_history(db_path: str = "database.db") -> None:
    """Clears all entries from the play history."""
    with get_db_connection(db_path) as db:
        db.execute(HistoryEntry.__table__.delete())
        db.commit()

def create_playlist(name: str, db_path: str = "database.db") -> Playlist:
    """Creates a new playlist."""
    with get_db_connection(db_path) as db:
        pl = Playlist(name=name)
        db.add(pl)
        db.commit()
        db.refresh(pl)
        db.expunge(pl)
        return pl

def add_video_to_playlist(playlist_id: int, video_id: str, db_path: str = "database.db") -> bool:
    """Adds a video to a playlist. Raises DuplicateVideoError on constraint violation."""
    with get_db_connection(db_path) as db:
        try:
            pt = PlaylistTrack(playlist_id=playlist_id, track_id=video_id)
            db.add(pt)
            db.commit()
            return True
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e.orig).lower()
            if "unique constraint failed" in error_msg or "primary key" in error_msg:
                raise DuplicateVideoError()
            raise

# --- Widget State & DJ Session History Functions ---

def upsert_widget_state(widget_id: str, state: dict, db_path: str = "database.db") -> WidgetState:
    """
    Saves the state of a widget. If widget_id exists, updates state and updated_at,
    otherwise inserts a new record.
    """
    if not widget_id or not isinstance(widget_id, str) or not widget_id.strip():
        raise ValueError("A valid non-empty 'widget_id' is required.")
    if not isinstance(state, dict):
        raise ValueError("'state' must be a valid dictionary.")

    with get_db_connection(db_path) as db:
        stmt = select(WidgetState).where(WidgetState.widget_id == widget_id.strip())
        existing = db.scalars(stmt).first()
        if existing:
            existing.state = state
            existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            db.refresh(existing)
            db.expunge(existing)
            return existing
        else:
            new_state = WidgetState(widget_id=widget_id.strip(), state=state)
            db.add(new_state)
            db.commit()
            db.refresh(new_state)
            db.expunge(new_state)
            return new_state

# CamelCase alias
upsertWidgetState = upsert_widget_state

def log_session_event(session_id: str, event_type: str, payload: dict, db_path: str = "database.db") -> DJSessionHistory:
    """
    Logs a new DJ session event in dj_session_history.
    """
    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("A valid non-empty 'session_id' is required.")
    if not event_type or not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("A valid non-empty 'event_type' is required.")
    if not isinstance(payload, dict):
        raise ValueError("'payload' must be a valid dictionary.")

    with get_db_connection(db_path) as db:
        entry = DJSessionHistory(
            session_id=session_id.strip(),
            event_type=event_type.strip(),
            payload=payload
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        db.expunge(entry)
        return entry

# CamelCase alias
logSessionEvent = log_session_event

def get_session_history(session_id: str, db_path: str = "database.db") -> List[DJSessionHistory]:
    """
    Retrieves all history entries for a given session_id, ordered by created_at ascending.
    """
    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        return []
    with get_db_connection(db_path) as db:
        stmt = (
            select(DJSessionHistory)
            .where(DJSessionHistory.session_id == session_id.strip())
            .order_by(DJSessionHistory.created_at.asc())
        )
        entries = list(db.scalars(stmt).all())
        for entry in entries:
            db.expunge(entry)
        return entries

# CamelCase alias
getSessionHistory = get_session_history


# --- Full DatabaseManager for Settings, Crates & Track Metadata ---

class DatabaseManager:
    """
    High-level SQLite and setting manager providing persistent configuration,
    crates, smart crates, audio metadata caching, and download history.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

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
            
            # Local Tracks table (for metadata and caching)
            c.execute('''
                CREATE TABLE IF NOT EXISTS local_tracks (
                    file_path TEXT PRIMARY KEY,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    bpm REAL,
                    key TEXT,
                    rating INTEGER DEFAULT 0,
                    genre TEXT,
                    year TEXT,
                    duration INTEGER DEFAULT 0,
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
                    FOREIGN KEY(crate_id) REFERENCES crates(id) ON DELETE CASCADE,
                    UNIQUE(crate_id, file_path)
                )
            ''')
            
            # Download History table
            c.execute('''
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    url TEXT,
                    format TEXT,
                    status TEXT,
                    file_path TEXT,
                    date TEXT
                )
            ''')
            
            # Setlists table
            c.execute('''
                CREATE TABLE IF NOT EXISTS setlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Setlist Items table
            c.execute('''
                CREATE TABLE IF NOT EXISTS setlist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setlist_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    notes TEXT DEFAULT '',
                    transition_type TEXT DEFAULT '',
                    cue_in_sec REAL DEFAULT 0,
                    cue_out_sec REAL DEFAULT 0,
                    FOREIGN KEY(setlist_id) REFERENCES setlists(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()

    # Settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = c.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return row[0]
            return default

    def set_setting(self, key: str, value: Any) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            val_str = json.dumps(value)
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))
            conn.commit()

    # Track Metadata
    def get_track(self, file_path: str) -> dict:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM local_tracks WHERE file_path = ?", (file_path,))
            row = c.fetchone()
            return dict(row) if row else {}

    def upsert_track(self, file_path: str, data: dict) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            existing = self.get_track(file_path)
            existing.update(data)
            
            c.execute('''
                INSERT OR REPLACE INTO local_tracks 
                (file_path, title, artist, album, bpm, key, rating, genre, year, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                existing.get('title'),
                existing.get('artist'),
                existing.get('album'),
                existing.get('bpm'),
                existing.get('key'),
                existing.get('rating', 0),
                existing.get('genre'),
                existing.get('year'),
                existing.get('duration', 0)
            ))
            conn.commit()

    # Crates
    def get_manual_crates(self) -> dict:
        crates = {}
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name FROM crates WHERE is_smart = 0")
            for crate_id, name in c.fetchall():
                c.execute("SELECT file_path FROM crate_tracks WHERE crate_id = ?", (crate_id,))
                crates[name] = [r[0] for r in c.fetchall()]
        return crates

    def get_smart_crates(self) -> dict:
        crates = {}
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT name, smart_rules FROM crates WHERE is_smart = 1")
            for name, rules_json in c.fetchall():
                try:
                    crates[name] = json.loads(rules_json)
                except Exception:
                    pass
        return crates

    def add_crate(self, name: str) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO crates (name, is_smart) VALUES (?, 0)", (name,))
            conn.commit()

    def add_smart_crate(self, name: str, rules_dict: dict) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            rules_json = json.dumps(rules_dict)
            c.execute("INSERT OR REPLACE INTO crates (name, is_smart, smart_rules) VALUES (?, 1, ?)", (name, rules_json))
            conn.commit()

    def rename_crate(self, old_name: str, new_name: str) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE crates SET name = ? WHERE name = ?", (new_name, old_name))
            conn.commit()

    def delete_crate(self, name: str) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM crates WHERE name = ?", (name,))
            row = c.fetchone()
            if row:
                c.execute("DELETE FROM crate_tracks WHERE crate_id = ?", (row[0],))
                c.execute("DELETE FROM crates WHERE id = ?", (row[0],))
                conn.commit()

    def add_track_to_crate(self, crate_name: str, file_path: str) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM crates WHERE name = ?", (crate_name,))
            row = c.fetchone()
            if row:
                c.execute("INSERT OR IGNORE INTO local_tracks (file_path) VALUES (?)", (file_path,))
                c.execute("INSERT OR IGNORE INTO crate_tracks (crate_id, file_path) VALUES (?, ?)", (row[0], file_path))
                conn.commit()

    # History
    def get_history(self, limit: int = 200) -> list:
        history = []
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM download_history ORDER BY id DESC LIMIT ?", (limit,))
            for row in c.fetchall():
                history.append(dict(row))
        return history

    def add_history_entry(self, title: str, url: str, fmt: str, status: str, file_path: str, date: str) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO download_history (title, url, format, status, file_path, date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, url, fmt, status, file_path, date))
            conn.commit()

    def clear_history(self) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM download_history")
            conn.commit()

    # Setlists
    def create_setlist(self, name: str, notes: str = "") -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO setlists (name, notes) VALUES (?, ?)", (name.strip(), notes.strip() if notes else ""))
            conn.commit()
            return c.lastrowid

    def get_all_setlists(self) -> list:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT s.id, s.name, s.notes, s.created_at, s.updated_at,
                       COUNT(si.id) as track_count,
                       COALESCE(SUM(lt.duration), 0) as total_duration
                FROM setlists s
                LEFT JOIN setlist_items si ON s.id = si.setlist_id
                LEFT JOIN local_tracks lt ON si.file_path = lt.file_path
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.id DESC
            """)
            return [dict(r) for r in c.fetchall()]

    def get_setlist(self, setlist_id: int) -> Optional[dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM setlists WHERE id = ?", (setlist_id,))
            s_row = c.fetchone()
            if not s_row:
                return None
            res = dict(s_row)
            c.execute("""
                SELECT si.id as item_id, si.position, si.notes as item_notes,
                       si.transition_type, si.cue_in_sec, si.cue_out_sec,
                       lt.file_path, lt.title, lt.artist, lt.album, lt.bpm,
                       lt.key, lt.rating, lt.genre, lt.year, lt.duration
                FROM setlist_items si
                LEFT JOIN local_tracks lt ON si.file_path = lt.file_path
                WHERE si.setlist_id = ?
                ORDER BY si.position ASC
            """, (setlist_id,))
            items = []
            for r in c.fetchall():
                d = dict(r)
                if not d.get('title'):
                    # Fallback title from filename
                    d['title'] = os.path.splitext(os.path.basename(d['file_path']))[0] if d.get('file_path') else 'Unknown'
                items.append(d)
            res['items'] = items
            return res

    def update_setlist(self, setlist_id: int, name: Optional[str] = None, notes: Optional[str] = None) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            if name is not None and notes is not None:
                c.execute("UPDATE setlists SET name = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name.strip(), notes.strip(), setlist_id))
            elif name is not None:
                c.execute("UPDATE setlists SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name.strip(), setlist_id))
            elif notes is not None:
                c.execute("UPDATE setlists SET notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (notes.strip(), setlist_id))
            conn.commit()

    def delete_setlist(self, setlist_id: int) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM setlist_items WHERE setlist_id = ?", (setlist_id,))
            c.execute("DELETE FROM setlists WHERE id = ?", (setlist_id,))
            conn.commit()
            return c.rowcount > 0

    def duplicate_setlist(self, setlist_id: int, new_name: str) -> Optional[int]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT notes FROM setlists WHERE id = ?", (setlist_id,))
            row = c.fetchone()
            if not row:
                return None
            notes = row[0]
            c.execute("INSERT INTO setlists (name, notes) VALUES (?, ?)", (new_name.strip(), notes))
            new_id = c.lastrowid
            c.execute("""
                SELECT file_path, position, notes, transition_type, cue_in_sec, cue_out_sec
                FROM setlist_items WHERE setlist_id = ? ORDER BY position ASC
            """, (setlist_id,))
            items = c.fetchall()
            for item in items:
                c.execute("""
                    INSERT INTO setlist_items (setlist_id, file_path, position, notes, transition_type, cue_in_sec, cue_out_sec)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (new_id, item[0], item[1], item[2], item[3], item[4], item[5]))
            conn.commit()
            return new_id

    def set_setlist_tracks(self, setlist_id: int, track_paths: list) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM setlist_items WHERE setlist_id = ?", (setlist_id,))
            for pos, path in enumerate(track_paths):
                c.execute("INSERT OR IGNORE INTO local_tracks (file_path) VALUES (?)", (path,))
                c.execute("""
                    INSERT INTO setlist_items (setlist_id, file_path, position)
                    VALUES (?, ?, ?)
                """, (setlist_id, path, pos))
            c.execute("UPDATE setlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (setlist_id,))
            conn.commit()

    def add_track_to_setlist(self, setlist_id: int, file_path: str, position: Optional[int] = None, notes: str = "", transition_type: str = "") -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO local_tracks (file_path) VALUES (?)", (file_path,))
            if position is None:
                c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM setlist_items WHERE setlist_id = ?", (setlist_id,))
                position = c.fetchone()[0]
            else:
                c.execute("UPDATE setlist_items SET position = position + 1 WHERE setlist_id = ? AND position >= ?", (setlist_id, position))
            c.execute("""
                INSERT INTO setlist_items (setlist_id, file_path, position, notes, transition_type)
                VALUES (?, ?, ?, ?, ?)
            """, (setlist_id, file_path, position, notes, transition_type))
            c.execute("UPDATE setlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (setlist_id,))
            conn.commit()

    def remove_track_from_setlist(self, setlist_id: int, position: int) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM setlist_items WHERE setlist_id = ? AND position = ?", (setlist_id, position))
            c.execute("UPDATE setlist_items SET position = position - 1 WHERE setlist_id = ? AND position > ?", (setlist_id, position))
            c.execute("UPDATE setlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (setlist_id,))
            conn.commit()

    def reorder_setlist_track(self, setlist_id: int, old_pos: int, new_pos: int) -> None:
        if old_pos == new_pos:
            return
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM setlist_items WHERE setlist_id = ? AND position = ?", (setlist_id, old_pos))
            target_row = c.fetchone()
            if not target_row:
                return
            target_id = target_row[0]
            
            if old_pos < new_pos:
                c.execute("""
                    UPDATE setlist_items
                    SET position = position - 1
                    WHERE setlist_id = ? AND position > ? AND position <= ?
                """, (setlist_id, old_pos, new_pos))
            else:
                c.execute("""
                    UPDATE setlist_items
                    SET position = position + 1
                    WHERE setlist_id = ? AND position >= ? AND position < ?
                """, (setlist_id, new_pos, old_pos))
                
            c.execute("UPDATE setlist_items SET position = ? WHERE id = ?", (new_pos, target_id))
            c.execute("UPDATE setlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (setlist_id,))
            conn.commit()

    def update_setlist_item(self, setlist_id: int, position: int, notes: Optional[str] = None, transition_type: Optional[str] = None) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            if notes is not None and transition_type is not None:
                c.execute("UPDATE setlist_items SET notes = ?, transition_type = ? WHERE setlist_id = ? AND position = ?", (notes, transition_type, setlist_id, position))
            elif notes is not None:
                c.execute("UPDATE setlist_items SET notes = ? WHERE setlist_id = ? AND position = ?", (notes, setlist_id, position))
            elif transition_type is not None:
                c.execute("UPDATE setlist_items SET transition_type = ? WHERE setlist_id = ? AND position = ?", (transition_type, setlist_id, position))
            c.execute("UPDATE setlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (setlist_id,))
            conn.commit()

if __name__ == "__main__":
    print("Testing Connection Pooling & Exception Handling...")
    init_db(":memory:")
    print("In-Memory DB initialized successfully with connection pool.")
