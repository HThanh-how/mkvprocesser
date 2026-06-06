import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import cache as C  # noqa: E402


def test_file_cache_set_get_ttl_and_stale(tmp_path):
    clock = {"t": 1000.0}
    c = C.Cache(redis_url="", file_dir=str(tmp_path / "cache"), ttl=100, now=lambda: clock["t"])
    assert c.backend() == "file"
    c.set("videos:list", [{"id": "a"}])
    val, age = c.get("videos:list")
    assert val == [{"id": "a"}] and age == 0 and c.fresh(age) is True
    clock["t"] = 1050.0
    _, age = c.get("videos:list")
    assert age == 50 and c.fresh(age) is True                 # con han
    clock["t"] = 1200.0
    val, age = c.get("videos:list")
    assert val == [{"id": "a"}] and age == 200                # van tra value (de phuc vu stale)
    assert c.fresh(age) is False                              # nhung da het han
    assert c.fresh(age, ttl=1000) is True                     # ttl override (admin chinh)


def test_file_cache_miss(tmp_path):
    c = C.Cache(file_dir=str(tmp_path / "c"), ttl=10, now=lambda: 5.0)
    assert c.get("nope") == (None, None)
    assert c.fresh(None) is False
