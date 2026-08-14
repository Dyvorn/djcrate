import pytest
from djcrate.utils import CamelotMatcher, extract_file_audio_metadata

def test_camelot_parse_key():
    assert CamelotMatcher.parse_key("8A") == (8, "A")
    assert CamelotMatcher.parse_key("11B") == (11, "B")
    assert CamelotMatcher.parse_key("1a") == (1, "A")
    assert CamelotMatcher.parse_key("12b") == (12, "B")
    assert CamelotMatcher.parse_key("") == (None, None)
    assert CamelotMatcher.parse_key("13A") == (None, None)
    assert CamelotMatcher.parse_key("0B") == (None, None)
    assert CamelotMatcher.parse_key("C Minor") == (None, None)

def test_camelot_colors():
    assert CamelotMatcher.get_camelot_color("1A") == "#00E5FF"
    assert CamelotMatcher.get_camelot_color("8A") == "#FF5252"
    assert CamelotMatcher.get_camelot_color("12B") == "#00E676"
    assert CamelotMatcher.get_camelot_color("invalid") == "#8A8580"

def test_camelot_compatible_keys():
    compat_8a = CamelotMatcher.get_compatible_keys("8A")
    assert compat_8a["exact"] == "8A"
    assert compat_8a["relative"] == "8B"
    assert compat_8a["energy_plus"] == "9A"
    assert compat_8a["energy_minus"] == "7A"
    assert "8A" in compat_8a["all_keys"]
    assert "8B" in compat_8a["all_keys"]
    assert "9A" in compat_8a["all_keys"]
    assert "7A" in compat_8a["all_keys"]

    compat_12b = CamelotMatcher.get_compatible_keys("12B")
    assert compat_12b["exact"] == "12B"
    assert compat_12b["relative"] == "12A"
    assert compat_12b["energy_plus"] == "1B"
    assert compat_12b["energy_minus"] == "11B"

def test_camelot_pitch_shift_calculation():
    # 128 BPM at 0%
    state_0 = CamelotMatcher.calculate_pitch_shifted_state(128, "8A", 0.0)
    assert state_0["effective_bpm"] == 128.0
    assert state_0["bpm_diff"] == 0.0
    assert state_0["transposed_key"] == "8A"

    # 128 BPM at +4.0%
    state_plus = CamelotMatcher.calculate_pitch_shifted_state(128, "8A", 4.0)
    assert state_plus["effective_bpm"] == 133.1
    assert state_plus["bpm_diff"] == 5.1
    assert state_plus["rate"] == 1.04

    # 100 BPM at +6.0% (around 1 semitone up -> 8A becomes 3A)
    state_semi = CamelotMatcher.calculate_pitch_shifted_state(100, "8A", 6.0)
    assert state_semi["semitones_rounded"] == 1
    assert state_semi["transposed_key"] == "3A"

def test_camelot_key_matching_scores():
    # Exact Match
    score, label = CamelotMatcher.calculate_key_match("8A", "8A")
    assert score == 1.0
    assert "Exact" in label

    # Relative Major/Minor
    score, label = CamelotMatcher.calculate_key_match("8A", "8B")
    assert score == 0.95
    assert "Relative" in label

    # Harmonic Shift (+1 / -1)
    score, label = CamelotMatcher.calculate_key_match("8A", "9A")
    assert score == 0.90

    score, label = CamelotMatcher.calculate_key_match("12A", "1A")
    assert score == 0.90

    # Energy Boost (+7 / +5 steps)
    score, label = CamelotMatcher.calculate_key_match("1A", "8A")
    assert score == 0.85

    # Distant Key
    score, label = CamelotMatcher.calculate_key_match("1A", "4B")
    assert score == 0.40

def test_camelot_bpm_matching():
    # Exact BPM
    score, label = CamelotMatcher.calculate_bpm_match(128, 128)
    assert score == 1.0
    assert "Perfect" in label

    # Half-time (140 to 70)
    score, label = CamelotMatcher.calculate_bpm_match(140, 70)
    assert score == 1.0
    assert "Half-time" in label

    # Double-time (75 to 150)
    score, label = CamelotMatcher.calculate_bpm_match(75, 150)
    assert score == 1.0
    assert "Double-time" in label

    # Small tempo drift (128 to 130)
    score, label = CamelotMatcher.calculate_bpm_match(128, 130)
    assert score >= 0.90

def test_camelot_track_match_and_score():
    t1 = {"path": "/t1.mp3", "key": "8A", "bpm": "126", "rating": 5}
    t2 = {"path": "/t2.mp3", "key": "8A", "bpm": "126", "rating": 5}
    t3 = {"path": "/t3.mp3", "key": "8B", "bpm": "127", "rating": 4}

    # Same track returns score 0
    res_same = CamelotMatcher.calculate_track_match(t1, t1)
    assert res_same["score"] == 0

    # High match
    res_high = CamelotMatcher.calculate_track_match(t1, t3)
    assert res_high["score"] >= 85
    assert res_high["quality"] == "Perfect Mix"
    assert res_high["is_harmonic"] is True

    # Flat score
    score, k_qual, b_qual = CamelotMatcher.calculate_match_score("8A", "126", "8A", "126")
    assert score >= 85
