import pytest
from sqlalchemy import select

from djcrate.database import (
    Track, Playlist, PlaylistTrack, HistoryEntry, WidgetState, DJSessionHistory,
    create_track, get_track_by_id, get_all_tracks, update_track, delete_track,
    add_to_history, get_history, delete_history_entry, clear_history,
    create_playlist, add_video_to_playlist, DuplicateVideoError, DatabaseError,
    upsert_widget_state, upsertWidgetState, log_session_event, logSessionEvent,
    get_session_history, getSessionHistory, get_db_connection, DatabaseManager
)
import tempfile
import os

TEST_DB = ":memory:"

# --- 1. CREATE TESTS ---

def test_create_track_success():
    track = create_track(
        video_id="vid_101",
        title="Deep Tech House",
        artist="DJ Apex",
        bpm=126,
        genre="Tech House",
        file_path="/tracks/deep_tech.mp3",
        duration=360,
        music_key="11A",
        db_path=TEST_DB
    )
    assert track.video_id == "vid_101"
    assert track.id == "vid_101"
    assert track.title == "Deep Tech House"
    assert track.artist == "DJ Apex"
    assert track.bpm == 126
    assert track.genre == "Tech House"
    assert track.file_path == "/tracks/deep_tech.mp3"
    assert track.duration == 360
    assert track.music_key == "11A"

def test_create_playlist_success():
    playlist = create_playlist(name="Peak Hour Tracks", db_path=TEST_DB)
    assert playlist.id is not None
    assert playlist.name == "Peak Hour Tracks"

def test_create_widget_state_success():
    state = upsertWidgetState(widget_id="eq_master", state={"high": 2, "mid": 0, "low": -1}, db_path=TEST_DB)
    assert state.id is not None
    assert state.widget_id == "eq_master"
    assert state.state == {"high": 2, "mid": 0, "low": -1}

def test_create_session_history_success():
    event = logSessionEvent(session_id="sess_001", event_type="track_start", payload={"bpm": 128}, db_path=TEST_DB)
    assert event.id is not None
    assert event.session_id == "sess_001"
    assert event.event_type == "track_start"
    assert event.payload == {"bpm": 128}

# --- 2. READ TESTS ---

def test_get_track_by_id_and_all_tracks():
    create_track(video_id="vid_r1", title="Track One", db_path=TEST_DB)
    create_track(video_id="vid_r2", title="Track Two", db_path=TEST_DB)

    track1 = get_track_by_id("vid_r1", db_path=TEST_DB)
    assert track1 is not None
    assert track1.title == "Track One"

    all_tracks = get_all_tracks(db_path=TEST_DB)
    assert len(all_tracks) == 2
    assert {t.video_id for t in all_tracks} == {"vid_r1", "vid_r2"}

    assert get_track_by_id("non_existent_id", db_path=TEST_DB) is None

def test_get_session_history_sorting():
    log_session_event("sess_sort", "event_1", {"seq": 1}, db_path=TEST_DB)
    log_session_event("sess_sort", "event_2", {"seq": 2}, db_path=TEST_DB)

    history = get_session_history("sess_sort", db_path=TEST_DB)
    assert len(history) == 2
    assert history[0].event_type == "event_1"
    assert history[1].event_type == "event_2"

# --- 3. UPDATE TESTS ---

def test_update_track_fields():
    create_track(video_id="vid_u1", title="Original Title", bpm=120, db_path=TEST_DB)

    updated = update_track("vid_u1", db_path=TEST_DB, title="Updated Title", bpm=128, genre="Nu Disco")
    assert updated is not None
    assert updated.title == "Updated Title"
    assert updated.bpm == 128
    assert updated.genre == "Nu Disco"

    fetched = get_track_by_id("vid_u1", db_path=TEST_DB)
    assert fetched.title == "Updated Title"

def test_upsert_widget_state_update():
    upsert_widget_state("deck_a", {"play": False}, db_path=TEST_DB)
    updated_state = upsert_widget_state("deck_a", {"play": True, "cue": True}, db_path=TEST_DB)

    assert updated_state.widget_id == "deck_a"
    assert updated_state.state == {"play": True, "cue": True}

# --- 4. DELETE TESTS ---

def test_delete_track():
    create_track(video_id="vid_d1", title="Delete Me", db_path=TEST_DB)

    assert delete_track("vid_d1", db_path=TEST_DB) is True
    assert get_track_by_id("vid_d1", db_path=TEST_DB) is None
    assert delete_track("vid_d1", db_path=TEST_DB) is False

def test_delete_history_entry_and_clear_history():
    create_track(video_id="vid_h1", title="Hist Track", db_path=TEST_DB)
    entry1 = add_to_history("vid_h1", status="played", db_path=TEST_DB)
    entry2 = add_to_history("vid_h1", status="queued", db_path=TEST_DB)

    assert len(get_history(db_path=TEST_DB)) == 2
    assert delete_history_entry(entry1.id, db_path=TEST_DB) is True
    assert len(get_history(db_path=TEST_DB)) == 1

    clear_history(db_path=TEST_DB)
    assert len(get_history(db_path=TEST_DB)) == 0

# --- 5. DATA INTEGRITY & CONSTRAINT TESTS ---

def test_not_null_constraint():
    """Verifies that inserting a Track with NULL title raises a DatabaseError due to NOT NULL constraint."""
    with pytest.raises(DatabaseError):
        with get_db_connection(TEST_DB) as session:
            bad_track = Track(video_id="vid_null", title=None)
            session.add(bad_track)
            session.commit()

def test_unique_constraint_playlist():
    """Verifies that duplicate playlist names violate UNIQUE constraint."""
    create_playlist("House Hits", db_path=TEST_DB)

    with pytest.raises(DatabaseError):
        with get_db_connection(TEST_DB) as session:
            dup_playlist = Playlist(name="House Hits")
            session.add(dup_playlist)
            session.commit()

def test_duplicate_video_in_playlist_error():
    """Verifies that adding the same video twice to a playlist raises DuplicateVideoError."""
    pl = create_playlist("Techno Favorites", db_path=TEST_DB)
    create_track(video_id="vid_dup", title="Techno Track", db_path=TEST_DB)

    assert add_video_to_playlist(pl.id, "vid_dup", db_path=TEST_DB) is True

    with pytest.raises(DuplicateVideoError) as exc_info:
        add_video_to_playlist(pl.id, "vid_dup", db_path=TEST_DB)

    assert exc_info.value.status_code == 409

def test_foreign_key_constraint():
    """Verifies that adding a history entry for a non-existent video_id violates Foreign Key constraint."""
    with pytest.raises(DatabaseError):
        with get_db_connection(TEST_DB) as session:
            entry = HistoryEntry(track_id="vid_non_existent", status="played")
            session.add(entry)
            session.commit()

def test_foreign_key_cascade_delete():
    """Verifies that deleting a Track cascades and deletes associated HistoryEntry and PlaylistTrack rows."""
    create_track(video_id="vid_casc", title="Cascading Track", db_path=TEST_DB)
    pl = create_playlist("Cascade List", db_path=TEST_DB)

    add_to_history("vid_casc", status="played", db_path=TEST_DB)
    add_video_to_playlist(pl.id, "vid_casc", db_path=TEST_DB)

    assert len(get_history(db_path=TEST_DB)) == 1

    delete_track("vid_casc", db_path=TEST_DB)

    assert len(get_history(db_path=TEST_DB)) == 0

    with get_db_connection(TEST_DB) as session:
        pt_count = len(list(session.scalars(select(PlaylistTrack)).all()))
        assert pt_count == 0

def test_input_validation_errors():
    """Verifies validation logic in CRUD functions."""
    with pytest.raises(ValueError, match="video_id"):
        create_track(video_id="", title="Valid Title", db_path=TEST_DB)

    with pytest.raises(ValueError, match="title"):
        create_track(video_id="vid_val", title=" ", db_path=TEST_DB)

    with pytest.raises(ValueError, match="bpm"):
        create_track(video_id="vid_val", title="Valid Title", bpm=-5, db_path=TEST_DB)

# --- 6. DATABASE MANAGER TESTS ---

def test_database_manager_settings_and_tracks():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = os.path.join(tmp_dir, "test_mgr.db")
        mgr = DatabaseManager(db_file)
        
        # Settings
        mgr.set_setting("accentColor", "#00E5FF")
        mgr.set_setting("volume", 85)
        assert mgr.get_setting("accentColor") == "#00E5FF"
        assert mgr.get_setting("volume") == 85
        assert mgr.get_setting("non_existent", "default_val") == "default_val"

        # Tracks upsert and get
        mgr.upsert_track("/music/track1.mp3", {
            "title": "Strobe",
            "artist": "deadmau5",
            "bpm": 128,
            "key": "8B",
            "rating": 5
        })
        track_data = mgr.get_track("/music/track1.mp3")
        assert track_data.get("title") == "Strobe"
        assert track_data.get("artist") == "deadmau5"
        assert track_data.get("bpm") == 128.0
        assert track_data.get("key") == "8B"
        assert track_data.get("rating") == 5

def test_database_manager_crates_and_history():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = os.path.join(tmp_dir, "test_crates.db")
        mgr = DatabaseManager(db_file)

        # Manual Crates
        mgr.add_crate("Festival Anthems")
        mgr.add_track_to_crate("Festival Anthems", "/music/anthem1.mp3")
        mgr.add_track_to_crate("Festival Anthems", "/music/anthem2.mp3")
        
        crates = mgr.get_manual_crates()
        assert "Festival Anthems" in crates
        assert len(crates["Festival Anthems"]) == 2

        mgr.rename_crate("Festival Anthems", "Mainstage Bangers")
        crates = mgr.get_manual_crates()
        assert "Mainstage Bangers" in crates
        assert "Festival Anthems" not in crates

        mgr.delete_crate("Mainstage Bangers")
        crates = mgr.get_manual_crates()
        assert "Mainstage Bangers" not in crates

        # Smart Crates
        mgr.add_smart_crate("128 BPM Tech", {"field": "bpm", "operator": ">=", "value": "128"})
        smart_crates = mgr.get_smart_crates()
        assert "128 BPM Tech" in smart_crates
        assert smart_crates["128 BPM Tech"]["value"] == "128"

        # Download History
        mgr.add_history_entry("Live Set", "https://youtube.com/watch?v=123", "mp3", "Completed", "/music/set.mp3", "2026-08-14 12:00")
        hist = mgr.get_history()
        assert len(hist) == 1
        assert hist[0]["title"] == "Live Set"

        mgr.clear_history()
        assert len(mgr.get_history()) == 0
