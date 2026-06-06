import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import fetch as F  # noqa: E402


def test_guess_name():
    assert F.guess_name("https://host/path/My.Movie.2011.1080p.mkv") == "My.Movie.2011.1080p.mkv"
    assert F.guess_name("https://host/dl/phim%20hay.mp4") == "phim hay.mp4"  # giai ma %20
    assert F.guess_name("https://youtube.com/watch?v=abc") == ""             # khong co ten file


def test_is_direct_media():
    assert F.is_direct_media("https://host/a/b.mkv")
    assert F.is_direct_media("https://host/a/b.MP4?token=x")                 # hoa + query van nhan
    assert not F.is_direct_media("https://youtube.com/watch?v=abc")
    assert not F.is_direct_media("https://drive.google.com/file/d/XYZ/view")


def test_safe_name():
    assert F.safe_name('a:b/c\\d?e*f') == "a_b_c_d_e_f"
    assert F.safe_name("") == "download"


def test_fetch_dispatches_direct_to_http(monkeypatch):
    called = {}
    monkeypatch.setattr(F, "http_download", lambda u, d, log=print: called.setdefault("http", u) or "f.mkv")
    monkeypatch.setattr(F, "ytdlp_download", lambda u, d, log=print: called.setdefault("ytdlp", u) or "f.mkv")
    F.fetch("https://host/x/movie.mkv", "/tmp")
    assert "http" in called and "ytdlp" not in called


def test_fetch_dispatches_page_to_ytdlp(monkeypatch):
    called = {}
    monkeypatch.setattr(F, "http_download", lambda u, d, log=print: called.setdefault("http", u) or "f.mkv")
    monkeypatch.setattr(F, "ytdlp_download", lambda u, d, log=print: called.setdefault("ytdlp", u) or "f.mkv")
    F.fetch("https://youtube.com/watch?v=abc", "/tmp")
    assert "ytdlp" in called and "http" not in called


def test_fetch_falls_back_to_http_when_ytdlp_missing(monkeypatch):
    called = {}

    def no_ytdlp(u, d, log=print):
        raise ImportError("no yt_dlp")

    monkeypatch.setattr(F, "ytdlp_download", no_ytdlp)
    monkeypatch.setattr(F, "http_download", lambda u, d, log=print: called.setdefault("http", u) or "f.bin")
    F.fetch("https://site/stream/page", "/tmp")
    assert "http" in called      # yt-dlp thieu -> roi xuong HTTP
