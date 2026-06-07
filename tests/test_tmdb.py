import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import tmdb as T  # noqa: E402


class _R:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_image_url():
    assert T.image_url("/abc.jpg") == "https://image.tmdb.org/t/p/w780/abc.jpg"
    assert T.image_url("/x.jpg", "w1280") == "https://image.tmdb.org/t/p/w1280/x.jpg"
    assert T.image_url("") is None
    assert T.image_url(None) is None


def test_search_movie_no_key_or_title():
    assert T.search_movie("Inception", "2010", "") is None      # thieu key
    assert T.search_movie("", "2010", "KEY") is None            # thieu tua


def test_search_movie_picks_first(monkeypatch):
    monkeypatch.setattr(T, "_get", lambda url: {"results": [
        {"id": 27205, "title": "Inception", "poster_path": "/p.jpg"}, {"id": 1}]})
    m = T.search_movie("Inception", "2010", "KEY")
    assert m["id"] == 27205 and m["title"] == "Inception"


def test_search_movie_empty(monkeypatch):
    monkeypatch.setattr(T, "_get", lambda url: {"results": []})
    assert T.search_movie("Khong Ton Tai", "", "KEY") is None


def test_fetch_image_no_movie(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "search_movie", lambda *a, **k: None)
    assert T.fetch_image("X", "2020", "KEY", str(tmp_path / "o.jpg"), log=lambda *a: None) is None


def test_fetch_image_downloads_poster(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "search_movie",
                        lambda *a, **k: {"title": "M", "poster_path": "/p.jpg", "backdrop_path": None})
    monkeypatch.setattr(T.urllib.request, "urlopen", lambda req: _R(b"JPGDATA"))
    dest = tmp_path / "o.jpg"
    out = T.fetch_image("M", "2020", "KEY", str(dest), prefer="poster", log=lambda *a: None)
    assert out == str(dest) and dest.read_bytes() == b"JPGDATA"


def test_make_thumbnail_no_key():
    # khong key/tua -> None ngay, khong tao thu muc / goi mang
    assert T.make_thumbnail("M", "2020", "", "x", log=lambda *a: None) is None
    assert T.make_thumbnail("", "2020", "KEY", "x", log=lambda *a: None) is None
