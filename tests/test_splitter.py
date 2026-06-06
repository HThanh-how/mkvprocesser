import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import splitter as S
from mkvtools import metadata as M


def test_analyze_and_pair_by_language():
    info = {"streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "vie"}},
        {"codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "vie"}},
        {"codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle", "tags": {"language": "eng"}},
    ]}
    a = S.analyze(info)
    assert len(a["audio"]) == 2 and len(a["subs"]) == 3
    jobs = S.pair_tracks(a)
    assert jobs[0]["lang"] == "vie" and jobs[0]["sidx"] == 1
    assert jobs[1]["lang"] == "eng" and jobs[1]["sidx"] == 0


def test_build_cmds():
    c = S.build_split_cmd("in.mkv", "o.mp4", 1, "ac3", "mp4")
    assert "0:a:1" in c and "aac" in c and "+faststart" in c and "-map_metadata" in c
    c2 = S.build_split_cmd("in.mkv", "o.mkv", 0, "aac", "mkv")
    assert c2[c2.index("-c:a") + 1] == "copy" and "0:t?" in c2
    assert S.build_extract_sub_cmd("in.mkv", "o.srt", 2)[-1] == "o.srt"
    b = S.build_burn_cmd("in.mkv", "o.mp4", 0, 1, "aac")
    assert any("subtitles=" in x for x in b) and "libx264" in b


def test_plan_naming(monkeypatch):
    info = {"format": {"tags": {"year": "2023"}}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 3840, "height": 2160},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "vie"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "vie"}},
    ]}
    monkeypatch.setattr(S.ffmpeg_helper, "probe", lambda p: info)
    p = S.plan("/x/My Movie.mkv", "/out", "caption", "mp4")
    assert p["res"] == "4K" and p["year"] == "2023"
    o = p["outputs"][0]
    assert o["lang"] == "vie" and o["out"].endswith(".mp4") and o["srt"].endswith(".srt")
    assert "4K" in o["out"] and "VIE" in o["out"] and "2023" in o["out"]


def test_metadata_helpers():
    assert M.bcp47("vie") == "vi" and M.bcp47("en") == "en" and M.bcp47("xyz") == "und"
    assert M.lang_abbr("eng") == "ENG"
    assert M.resolution_label([{"codec_type": "video", "width": 1920, "height": 1080}]) == "FHD"


def test_no_lang_fallback_by_order():
    info = {"streams": [
        {"codec_type": "video"},
        {"codec_type": "audio", "codec_name": "aac"},
        {"codec_type": "audio", "codec_name": "aac"},
        {"codec_type": "subtitle", "codec_name": "ass"},
        {"codec_type": "subtitle", "codec_name": "ass"},
    ]}
    j = S.pair_tracks(S.analyze(info))
    assert j[0]["sidx"] == 0 and j[1]["sidx"] == 1
