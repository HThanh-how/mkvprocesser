import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import resources as R  # noqa: E402


def test_free_gb_positive():
    assert R.free_gb(".") > 0


def test_free_gb_bad_path_is_zero():
    assert R.free_gb("/no/such/path/really") == 0.0


def test_enough_space_and_pick_work_dir(monkeypatch):
    monkeypatch.setattr(R, "free_gb", lambda p: 10.0)
    assert R.enough_space("/x", 5)
    assert not R.enough_space("/x", 20)
    assert R.pick_work_dir("/ssd", "/hdd", 5) == "/ssd"     # primary du cho
    monkeypatch.setattr(R, "free_gb", lambda p: 1.0)
    assert R.pick_work_dir("/ssd", "/hdd", 5) == "/hdd"     # primary thieu -> fallback


def test_pick_work_dir_no_primary():
    assert R.pick_work_dir("", "/hdd", 5) == "/hdd"


def test_preflight(tmp_path, monkeypatch):
    f = tmp_path / "v.mkv"
    f.write_bytes(b"0" * 4096)
    monkeypatch.setattr(R, "free_gb", lambda p: 100.0)
    ok, msg = R.preflight(str(f), str(tmp_path))
    assert ok and msg == ""
    monkeypatch.setattr(R, "free_gb", lambda p: 0.0)
    ok, msg = R.preflight(str(f), str(tmp_path))
    assert not ok and "dia" in msg.lower()


def test_available_ram_gb_type():
    val = R.available_ram_gb()
    assert val is None or val > 0
