import os
import tempfile
import pytest

from djcrate.database import DatabaseManager, init_db, Setlist, SetlistItem
from djcrate.utils import (
    CamelotMatcher,
    export_setlist_to_m3u8,
    export_setlist_to_csv,
    export_setlist_to_tracklist_text,
    export_setlist_to_cheat_sheet_html
)


# --- 1. Database & Persistence Tests ---

def test_setlist_crud_database_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_djcrate.db")
        db = DatabaseManager(db_path)

        # 1. Create setlist
        set_id = db.create_setlist("Peak Time Techno 135", notes="Festival mainstage set")
        assert set_id is not None
        assert set_id > 0

        # 2. Get all setlists
        setlists = db.get_all_setlists()
        assert len(setlists) == 1
        assert setlists[0]['name'] == "Peak Time Techno 135"
        assert setlists[0]['notes'] == "Festival mainstage set"

        # 3. Add tracks
        db.add_track_to_setlist(set_id, "C:\\Music\\Track1.mp3", notes="Intro filter sweep")
        db.add_track_to_setlist(set_id, "C:\\Music\\Track2.flac", notes="Drop on 1")
        db.add_track_to_setlist(set_id, "C:\\Music\\Track3.wav")

        setlist_data = db.get_setlist(set_id)
        assert setlist_data is not None
        assert len(setlist_data['items']) == 3
        assert setlist_data['items'][0]['file_path'] == "C:\\Music\\Track1.mp3"
        assert setlist_data['items'][0]['item_notes'] == "Intro filter sweep"
        assert setlist_data['items'][1]['file_path'] == "C:\\Music\\Track2.flac"

        # 4. Reorder tracks (move track at pos 2 to pos 0)
        db.reorder_setlist_track(set_id, old_pos=2, new_pos=0)
        updated_data = db.get_setlist(set_id)
        assert updated_data['items'][0]['file_path'] == "C:\\Music\\Track3.wav"
        assert updated_data['items'][1]['file_path'] == "C:\\Music\\Track1.mp3"
        assert updated_data['items'][2]['file_path'] == "C:\\Music\\Track2.flac"

        # 5. Update setlist track note
        db.update_setlist_item(set_id, position=0, notes="New cue note")
        updated_data2 = db.get_setlist(set_id)
        assert updated_data2['items'][0]['item_notes'] == "New cue note"

        # 6. Duplicate setlist
        dup_id = db.duplicate_setlist(set_id, "Peak Time Techno (Backup)")
        assert dup_id is not None
        dup_data = db.get_setlist(dup_id)
        assert dup_data['name'] == "Peak Time Techno (Backup)"
        assert len(dup_data['items']) == 3

        # 7. Remove a track
        db.remove_track_from_setlist(set_id, position=1)
        after_remove = db.get_setlist(set_id)
        assert len(after_remove['items']) == 2

        # 8. Delete setlist
        deleted = db.delete_setlist(set_id)
        assert deleted is True
        assert db.get_setlist(set_id) is None


# --- 2. Transition Analysis Math Tests ---

def test_transition_exact_key_match():
    t1 = {'title': 'Track A', 'key': '8A', 'bpm': '126'}
    t2 = {'title': 'Track B', 'key': '8A', 'bpm': '126'}

    res = CamelotMatcher.calculate_transition_analysis(t1, t2)
    assert res['key_score'] == 1.0
    assert res['key_label'] == "Exact Key Match"
    assert res['is_clash'] is False
    assert res['pitch_delta_pct'] == 0.0
    assert res['overall_score'] >= 90
    assert res['quality'] == "Harmonic Match"
    assert "Long Blend" in res['technique']


def test_transition_relative_and_adjacent_key_matches():
    # 8A -> 8B (Relative Major)
    t1 = {'title': 'Track A', 'key': '8A', 'bpm': '128'}
    t2 = {'title': 'Track B', 'key': '8B', 'bpm': '128'}
    res_rel = CamelotMatcher.calculate_transition_analysis(t1, t2)
    assert res_rel['key_score'] == 0.95
    assert res_rel['is_clash'] is False

    # 8A -> 9A (Harmonic Shift +1)
    t3 = {'title': 'Track C', 'key': '9A', 'bpm': '130'}
    res_adj = CamelotMatcher.calculate_transition_analysis(t1, t3)
    assert res_adj['key_score'] == 0.90
    assert res_adj['pitch_delta_pct'] == pytest.approx(1.56, rel=1e-2)
    assert res_adj['is_clash'] is False


def test_transition_key_clash_detection():
    # 8A (A minor) vs 11A (F# minor) -> 3 steps away (incompatible clash)
    t1 = {'title': 'Track A', 'key': '8A', 'bpm': '124'}
    t2 = {'title': 'Track B', 'key': '11A', 'bpm': '124'}

    res = CamelotMatcher.calculate_transition_analysis(t1, t2)
    assert res['is_clash'] is True
    assert res['key_score'] < 0.65
    assert "Clash" in res['quality']
    assert "Echo Out" in res['technique']


def test_transition_pitch_delta_and_semitone_shifts():
    # 120 BPM -> 126 BPM = +5.0% pitch
    t1 = {'title': 'Track A', 'key': '8A', 'bpm': '120'}
    t2 = {'title': 'Track B', 'key': '8A', 'bpm': '126'}

    res = CamelotMatcher.calculate_transition_analysis(t1, t2)
    assert res['pitch_delta_pct'] == 5.0
    assert res['deck_a_pitch_pct'] == 5.0
    assert res['semitones_shift'] > 0


# --- 3. Setlist Flow & Metrics Tests ---

def test_calculate_setlist_flow_metrics():
    tracks = [
        {'title': 'Intro Track', 'artist': 'Artist 1', 'key': '8A', 'bpm': 124, 'duration': 180},
        {'title': 'Build Track', 'artist': 'Artist 2', 'key': '8B', 'bpm': 126, 'duration': 240},
        {'title': 'Peak Track', 'artist': 'Artist 3', 'key': '9A', 'bpm': 128, 'duration': 300},
    ]

    flow = CamelotMatcher.calculate_setlist_flow(tracks)
    assert flow['track_count'] == 3
    assert flow['total_duration_secs'] == 720
    assert flow['total_duration_str'] == "12m 00s"
    assert flow['cumulative_start_times'] == [0, 180, 420]
    assert flow['formatted_start_times'] == ["00:00", "03:00", "07:00"]
    assert len(flow['transitions']) == 2
    assert flow['clash_count'] == 0
    assert flow['harmonic_flow_score'] >= 85
    assert len(flow['energy_curve']) == 3


def test_auto_harmonize_ordering():
    # Provide scrambled keys: 1A, 8A, 2A, 12A
    tracks = [
        {'title': 'Track 1', 'key': '1A', 'bpm': 125},
        {'title': 'Track 2', 'key': '8A', 'bpm': 125},
        {'title': 'Track 3', 'key': '2A', 'bpm': 125},
        {'title': 'Track 4', 'key': '12A', 'bpm': 125},
    ]

    reordered = CamelotMatcher.auto_harmonize_track_order(tracks)
    assert len(reordered) == 4
    # Starting from 1A, next nearest harmonic step should be 2A or 12A
    assert reordered[0]['key'] == '1A'
    assert reordered[1]['key'] in ('2A', '12A')


# --- 4. Setlist Exporters Tests ---

def test_export_setlist_m3u8_and_csv():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tracks = [
            {'title': 'Language', 'artist': 'Porter Robinson', 'key': '8B', 'bpm': '128', 'duration': 360, 'file_path': 'C:\\Music\\Language.mp3'},
            {'title': 'Shelter', 'artist': 'Madeon', 'key': '9B', 'bpm': '128', 'duration': 240, 'file_path': 'C:\\Music\\Shelter.mp3'}
        ]

        m3u_path = os.path.join(tmp_dir, "festival_set.m3u8")
        csv_path = os.path.join(tmp_dir, "festival_set.csv")

        export_setlist_to_m3u8("Festival Set", tracks, m3u_path)
        export_setlist_to_csv("Festival Set", tracks, csv_path)

        assert os.path.exists(m3u_path)
        with open(m3u_path, 'r', encoding='utf-8') as f:
            m3u_content = f.read()
            assert "#EXTM3U" in m3u_content
            assert "Porter Robinson - Language" in m3u_content

        assert os.path.exists(csv_path)
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
            assert "Title,Artist,BPM,Key" in csv_content
            assert "Language,Porter Robinson,128,8B" in csv_content


def test_export_tracklist_text_and_html_cheat_sheet():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tracks = [
            {'title': 'Track One', 'artist': 'DJ A', 'key': '8A', 'bpm': '125', 'duration': 200, 'file_path': 'C:\\Music\\t1.mp3'},
            {'title': 'Track Two', 'artist': 'DJ B', 'key': '9A', 'bpm': '127', 'duration': 220, 'file_path': 'C:\\Music\\t2.mp3'}
        ]

        txt_content = export_setlist_to_tracklist_text("Club Mix", tracks)
        assert "=== DJ SET: CLUB MIX ===" in txt_content
        assert "[00:00] 01. DJ A - Track One" in txt_content
        assert "↳ Transition:" in txt_content

        html_path = os.path.join(tmp_dir, "cheat_sheet.html")
        export_setlist_to_cheat_sheet_html("Club Mix", tracks, html_path)
        assert os.path.exists(html_path)

        with open(html_path, 'r', encoding='utf-8') as f:
            html_text = f.read()
            assert "DJ CRATE — SETLIST CHEAT SHEET" in html_text
            assert "Track One" in html_text
            assert "key-pill" in html_text
