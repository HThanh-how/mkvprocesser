import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import subfetch as S  # noqa: E402


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
