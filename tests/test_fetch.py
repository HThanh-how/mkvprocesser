import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import fetch as F  # noqa: E402


# ---------------------------------------------------------------- pure helpers
def test_guess_name():
    assert F.guess_name("https://host/path/My.Movie.2011.1080p.mkv") == "My.Movie.2011.1080p.mkv"
    assert F.guess_name("https://host/dl/phim%20hay.mp4") == "phim hay.mp4"     # giai ma %20
    assert F.guess_name("https://youtube.com/watch?v=abc") == ""               # khong co ten file


def test_is_direct_media():
    assert F.is_direct_media("https://host/a/b.mkv")
    assert F.is_direct_media("https://host/a/b.MP4?token=x")                    # hoa + query van nhan
    assert not F.is_direct_media("https://host/a/master.m3u8")                  # manifest != file truc tiep
    assert not F.is_direct_media("https://youtube.com/watch?v=abc")


def test_is_torrent():
    assert F.is_torrent("magnet:?xt=urn:btih:ABC123")
    assert F.is_torrent("https://site/x/movie.torrent")
    assert F.is_torrent("https://site/x/movie.torrent?token=1")
    assert not F.is_torrent("https://site/x/movie.mkv")
    assert not F.is_torrent("https://youtube.com/watch?v=a")


def test_is_media_url():
    assert F.is_media_url("https://c/x/master.m3u8")                            # theo duoi
    assert F.is_media_url("https://c/x/seg?_=1", "application/vnd.apple.mpegurl")  # theo content-type
    assert F.is_media_url("https://c/x/v", "video/mp4")
    assert not F.is_media_url("https://c/x/page.html", "text/html")


def test_media_signature_distinguishes_video_from_fake_mp4():
    assert F.media_signature(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00") == "mp4"
    assert F.media_signature(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000") == "text"
    assert F.media_signature(b"<HTML><HEAD><TITLE>Access Denied") == "text"


def test_valid_video_file_rejects_tiny_vtt_with_mp4_suffix(tmp_path):
    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello")
    assert not F.valid_video_file(str(fake))


def test_verify_candidate_rejects_vtt_even_when_cdn_says_mp4(monkeypatch):
    class FakeResponse:
        headers = {"Content-Type": "video/mp4", "Content-Range": "bytes 0-63/138"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b"WEBVTT\n\n00:00:00.840 --> 00:00:02.000"

    monkeypatch.setattr(F.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    ok, reason = F.verify_media_candidate({"url": "https://cdn.example/video/"})
    assert not ok
    assert "text" in reason


def test_candidate_list_keeps_all_dom_videos_and_drops_network_prefetch(monkeypatch):
    monkeypatch.setattr(F, "browser_sniff", lambda *_args, **_kwargs: [
        {"url": "https://cdn/related.mp4", "referer": "https://threads/post/1"},
        {"url": "https://cdn/carousel-1.mp4", "referer": "https://threads/post/1",
         "dom_video": True, "primary": True, "width": 720, "height": 1280},
        {"url": "https://cdn/carousel-2.mp4", "referer": "https://threads/post/1",
         "dom_video": True, "width": 720, "height": 1280},
    ])
    monkeypatch.setattr(F, "verify_media_candidate", lambda _candidate: (True, "mp4"))
    candidates = F.list_video_candidates("https://threads/post/1")
    assert [candidate["url"] for candidate in candidates] == [
        "https://cdn/carousel-1.mp4",
        "https://cdn/carousel-2.mp4",
    ]
    assert all("_dom_video" not in candidate for candidate in candidates)


def test_candidate_list_falls_back_when_dom_video_is_invalid(monkeypatch):
    monkeypatch.setattr(F, "browser_sniff", lambda *_args, **_kwargs: [
        {"url": "https://cdn/video.mp4"},
        {"url": "https://cdn/subtitle.mp4", "dom_video": True},
    ])
    monkeypatch.setattr(
        F, "verify_media_candidate",
        lambda candidate: (candidate["url"].endswith("video.mp4"), "checked"),
    )
    candidates = F.list_video_candidates("https://threads/post/1", log=lambda _msg: None)
    assert [candidate["url"] for candidate in candidates] == ["https://cdn/video.mp4"]


def test_rank_media_prefers_manifest_then_mp4():
    cands = [{"url": "https://c/v.mp4"}, {"url": "https://c/master.m3u8"}, {"url": "https://c/s.ts"}]
    assert F.rank_media(cands)["url"].endswith(".m3u8")
    assert F.rank_media([{"url": "https://c/v.mp4"}, {"url": "https://c/s.ts"}])["url"].endswith(".mp4")
    assert F.rank_media([]) is None


def test_rank_media_primary_beats_others():
    # Clip dang hien thi (primary) thang ca clip khac, ke ca manifest -> tranh tai nham.
    cands = [{"url": "https://c/other.mp4"}, {"url": "https://c/main", "primary": True},
             {"url": "https://c/feed.m3u8"}]
    assert F.rank_media(cands)["url"] == "https://c/main"


def test_safe_name():
    assert F.safe_name('a:b/c\\d?e*f') == "a_b_c_d_e_f"
    assert F.safe_name("") == "download"


def test_load_cookies_txt(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("# Netscape\n\n.example.com\tTRUE\t/\tTRUE\t0\tsid\tABC\n", encoding="utf-8")
    ck = F.load_cookies_txt(str(p))
    assert len(ck) == 1
    assert ck[0]["name"] == "sid" and ck[0]["value"] == "ABC"
    assert ck[0]["domain"] == ".example.com" and ck[0]["secure"] is True
    assert "expires" not in ck[0]                                              # expiry 0 -> session


# ---------------------------------------------------------------- fetch() 4 tang
def _sniff(cands):
    return lambda u, log=print, cookies=None: cands


def test_fetch_t0_torrent_dispatch(monkeypatch):
    seen = {}
    monkeypatch.setattr(F, "torrent_download", lambda u, d, log=print: seen.setdefault("tor", u) or "m.mkv")
    monkeypatch.setattr(F, "http_download", lambda *a, **k: seen.setdefault("http", 1))
    monkeypatch.setattr(F, "ytdlp_download", lambda *a, **k: seen.setdefault("yt", 1))
    F.fetch("magnet:?xt=urn:btih:ABC", "/tmp")
    assert "tor" in seen and "http" not in seen and "yt" not in seen


def test_resolve_torrent():
    r = F.resolve("magnet:?xt=urn:btih:ABC")
    assert r["ok"] and r["tier"] == "torrent"


def test_fetch_t1_direct_to_http(monkeypatch):
    seen = {}
    monkeypatch.setattr(F, "http_download",
                        lambda u, d, log=print, referer=None: seen.setdefault("http", u) or "f.mkv")
    monkeypatch.setattr(F, "ytdlp_download", lambda *a, **k: seen.setdefault("yt", 1))
    F.fetch("https://host/x/movie.mkv", "/tmp")
    assert "http" in seen and "yt" not in seen


def test_fetch_t2_page_to_ytdlp(monkeypatch):
    seen = {}
    monkeypatch.setattr(F, "ytdlp_download",
                        lambda u, d, log=print, cookies=None, referer=None: seen.setdefault("yt", u) or "f.mkv")
    monkeypatch.setattr(F, "http_download", lambda *a, **k: seen.setdefault("http", 1))
    F.fetch("https://youtube.com/watch?v=abc", "/tmp")
    assert "yt" in seen and "http" not in seen


def test_fetch_t3_sniff_direct_falls_to_http(monkeypatch):
    seen = {}

    def yt_boom(u, d, log=print, cookies=None, referer=None):
        raise RuntimeError("yt-dlp thua")

    def fake_http(u, d, log=print, referer=None):
        seen["http"] = (u, referer)
        return "v.mp4"

    monkeypatch.setattr(F, "ytdlp_download", yt_boom)
    monkeypatch.setattr(F, "browser_sniff", _sniff([{"url": "https://cdn/a/v.mp4", "referer": "r"}]))
    monkeypatch.setattr(F, "http_download", fake_http)
    out = F.fetch("https://site/embed/page", "/tmp")
    assert out == "v.mp4" and seen["http"] == ("https://cdn/a/v.mp4", "r")     # sniff -> tai HTTP file


def test_fetch_t3_sniff_manifest_uses_ytdlp(monkeypatch):
    def yt(u, d, log=print, cookies=None, referer=None):
        if "page" in u:
            raise RuntimeError("trang khong tai duoc")
        return "stream.mkv"                                                    # tai manifest OK

    monkeypatch.setattr(F, "ytdlp_download", yt)
    monkeypatch.setattr(F, "browser_sniff", _sniff([{"url": "https://cdn/master.m3u8", "referer": "r"}]))
    assert F.fetch("https://site/page", "/tmp") == "stream.mkv"


def test_fetch_all_tiers_fail_raises(monkeypatch):
    def yt_boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(F, "ytdlp_download", yt_boom)
    monkeypatch.setattr(F, "browser_sniff", _sniff([]))
    with pytest.raises(RuntimeError):
        F.fetch("https://site/page", "/tmp")


# ---------------------------------------------------------------- resolve() (chi do)
def test_resolve_direct():
    r = F.resolve("https://h/x/movie.mkv")
    assert r["ok"] and r["tier"] == "direct" and r["media"].endswith(".mkv")


def test_resolve_ytdlp(monkeypatch):
    monkeypatch.setattr(F, "ytdlp_probe", lambda u, cookies=None: {"title": "Phim", "ext": "mp4", "url": "u"})
    r = F.resolve("https://youtube.com/watch?v=a")
    assert r["tier"] == "yt-dlp" and r["title"] == "Phim"


def test_resolve_browser(monkeypatch):
    monkeypatch.setattr(F, "ytdlp_probe", lambda u, cookies=None: None)
    monkeypatch.setattr(F, "browser_sniff", _sniff([{"url": "https://c/a.m3u8"}]))
    r = F.resolve("https://site/page")
    assert r["tier"] == "browser" and r["media"].endswith(".m3u8")


def test_resolve_none(monkeypatch):
    monkeypatch.setattr(F, "ytdlp_probe", lambda u, cookies=None: None)
    monkeypatch.setattr(F, "browser_sniff", _sniff([]))
    assert F.resolve("https://site/page")["ok"] is False
