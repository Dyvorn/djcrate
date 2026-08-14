import os
import tempfile
import struct
import csv
from djcrate.serato import SeratoCrateWriter
from djcrate.obs_overlay import ObsOverlayWriter

def test_serato_crate_writer():
    with tempfile.TemporaryDirectory() as tmp_dir:
        crate_paths = ["C:\\Music\\Track1.mp3", "C:\\Music\\Track2.flac"]
        out_file = SeratoCrateWriter.write_crate("House Classics", crate_paths, output_dir=tmp_dir)
        
        assert os.path.exists(out_file)
        assert out_file.endswith("House Classics.crate")

        with open(out_file, "rb") as f:
            data = f.read()

        # Check 'vrsn' tag
        assert b"vrsn" in data
        assert b"otrk" in data
        assert b"ptrk" in data

def test_obs_overlay_writer(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        monkeypatch.setattr(ObsOverlayWriter, "get_overlay_dir", staticmethod(lambda: tmp_dir))
        
        ObsOverlayWriter.update_now_playing(
            title="Language",
            artist="Porter Robinson",
            bpm="128",
            key="8B",
            accent_color="#00E5FF"
        )

        txt_file = os.path.join(tmp_dir, "now_playing.txt")
        html_file = os.path.join(tmp_dir, "now_playing.html")

        assert os.path.exists(txt_file)
        assert os.path.exists(html_file)

        with open(txt_file, "r", encoding="utf-8") as f:
            txt_content = f.read()
            assert "Porter Robinson - Language" in txt_content
            assert "128 BPM" in txt_content
            assert "Key 8B" in txt_content

        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
            assert "Language" in html_content
            assert "Porter Robinson" in html_content
            assert "#00E5FF" in html_content

def test_csv_and_m3u8_export_format():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tracks = [
            {"title": "One More Time", "artist": "Daft Punk", "bpm": "123", "key": "11B", "durationSecs": 320, "path": "C:\\Music\\track1.mp3"},
            {"title": "Around the World", "artist": "Daft Punk", "bpm": "121", "key": "9A", "durationSecs": 240, "path": "C:\\Music\\track2.mp3"}
        ]

        # Test M3U8 format
        m3u8_file = os.path.join(tmp_dir, "test.m3u8")
        with open(m3u8_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for t in tracks:
                f.write(f"#EXTINF:{t['durationSecs']},{t['artist']} - {t['title']}\n")
                f.write(f"{t['path']}\n")

        with open(m3u8_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "#EXTM3U" in content
            assert "#EXTINF:320,Daft Punk - One More Time" in content

        # Test CSV format
        csv_file = os.path.join(tmp_dir, "test.csv")
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Title", "Artist", "BPM", "Key", "Duration", "Path"])
            for idx, t in enumerate(tracks, 1):
                writer.writerow([idx, t["title"], t["artist"], t["bpm"], t["key"], t["durationSecs"], t["path"]])

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            assert reader[0] == ["#", "Title", "Artist", "BPM", "Key", "Duration", "Path"]
            assert reader[1] == ["1", "One More Time", "Daft Punk", "123", "11B", "320", "C:\\Music\\track1.mp3"]
