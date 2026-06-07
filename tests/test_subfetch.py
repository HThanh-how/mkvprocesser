import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import subfetch as S  # noqa: E402


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_norm_langs():
    assert S.norm_langs(["vi", "en"]) == ["vi", "en"]
    assert S.norm_langs(["Vietnamese", "ENG", "vie", "en"]) == ["vi", "en"]   # alias + dedup
    assert S.norm_langs(["xx", ""]) == []


def test_pick_best_prefers_hash_then_downloads():
    res = [
        {"attributes": {"download_count": 100, "files": [{"file_id": 1}]}},
        {"attributes": {"download_count": 5, "moviehash_match": True, "files": [{"file_id": 2}]}},
        {"attributes": {"download_count": 50, "files": [{"file_id": 3}]}},
    ]
    assert S.pick_best(res) == 2          # khop moviehash -> uu tien
    res2 = [
        {"attributes": {"download_count": 10, "files": [{"file_id": 1}]}},
        {"attributes": {"download_count": 99, "files": [{"file_id": 2}]}},
    ]
    assert S.pick_best(res2) == 2         # khong hash -> nhieu luot tai nhat
    assert S.pick_best([]) is None
    assert S.pick_best([{"attributes": {"files": []}}]) is None   # khong co file


def test_osdb_hash(tmp_path):
    small = tmp_path / "s.bin"
    small.write_bytes(b"x" * 1000)
    assert S.osdb_hash(str(small)) is None                         # < 128KB -> None
    big = tmp_path / "b.bin"
    big.write_bytes(bytes(200000))
    h = S.osdb_hash(str(big))
    assert h is not None and len(h) == 16 and all(c in "0123456789abcdef" for c in h)
    assert h == S.osdb_hash(str(big))                              # deterministic


def test_find_subs_no_creds_returns_empty(tmp_path):
    v = tmp_path / "Movie.2024.mkv"
    v.write_bytes(bytes(200000))
    assert S.find_subs(str(v), str(tmp_path), api_key="", username="", password="",
                       log=lambda *a: None) == []                  # thieu creds -> rong, khong goi mang


# ----------------------------------------------------------------- SubDL
def test_subdl_pick_prefers_movie_then_fallback():
    subs = [{"url": "/a.zip", "full_season": True}, {"url": "/b.zip", "full_season": False}]
    assert S._subdl_pick(subs) == "/b.zip"                         # uu tien phim le
    assert S._subdl_pick([{"url": "/a.zip", "full_season": True}]) == "/a.zip"   # fallback
    assert S._subdl_pick([]) is None
    assert S._subdl_pick([{"full_season": False}]) is None         # khong co url


def test_subdl_extract_zip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "x")
        z.writestr("sub/Movie.srt", "hi")                          # .srt nam trong thu muc con
    out = tmp_path / "o.srt"
    assert S._subdl_extract_zip(buf.getvalue(), str(out)) is True
    assert out.read_text() == "hi"
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as z:
        z.writestr("a.txt", "x")                                   # khong co file sub
    assert S._subdl_extract_zip(buf2.getvalue(), str(tmp_path / "x.srt")) is False


def test_subdl_find_no_key_returns_empty(tmp_path):
    v = tmp_path / "M.mkv"
    v.write_bytes(bytes(1000))
    assert S.subdl_find(str(v), str(tmp_path), langs=["vi"], api_key="", log=lambda *a: None) == []


def test_subdl_find_downloads(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Movie.vi.srt", "1\n00:00:00,000 --> 00:00:01,000\nxin chao\n")
    monkeypatch.setattr(S, "_get",
                        lambda url, headers: {"subtitles": [{"url": "/subtitle/1-2.zip"}]})
    monkeypatch.setattr(S.urllib.request, "urlopen", lambda req: _FakeResp(buf.getvalue()))
    v = tmp_path / "Movie.2024.mkv"
    v.write_bytes(bytes(1000))
    out = S.subdl_find(str(v), str(tmp_path / "out"), langs=["vi"], api_key="KEY",
                       log=lambda *a: None)
    assert len(out) == 1
    srt, lg = out[0]
    assert lg == "vi" and srt.endswith(".vi.srt") and os.path.exists(srt)
    with open(srt, encoding="utf-8") as f:
        assert "xin chao" in f.read()


def test_fetch_subs_no_keys_returns_empty(tmp_path):
    v = tmp_path / "M.2024.mkv"
    v.write_bytes(bytes(1000))
    assert S.fetch_subs(str(v), str(tmp_path), langs=["vi", "en"], log=lambda *a: None) == []


def test_fetch_subs_subdl_first_then_opensubtitles(monkeypatch):
    monkeypatch.setattr(S, "subdl_find", lambda *a, **k: [("/sub/vi.srt", "vi")])
    calls = {}

    def fake_os(video, dest, langs, *a, **k):
        calls["langs"] = list(langs)
        return [("/os/en.srt", "en")]

    monkeypatch.setattr(S, "find_subs", fake_os)
    out = S.fetch_subs("/v/M.mkv", "/out", langs=["vi", "en"], subdl_api_key="K",
                       os_api_key="A", os_user="u", os_pass="p", log=lambda *a: None)
    assert out == [("/sub/vi.srt", "vi"), ("/os/en.srt", "en")]    # dung thu tu vi -> en
    assert calls["langs"] == ["en"]            # OpenSubtitles chi goi cho lang SubDL con thieu
