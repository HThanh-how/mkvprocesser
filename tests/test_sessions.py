"""Phien dang nhap: ben vung qua restart, luu an toan, thu hoi duoc."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mkvtools import auth  # noqa: E402


def test_session_survives_restart(tmp_path):
    """May tat theo lich moi toi -> sang hom sau khong bat dang nhap lai."""
    path = str(tmp_path / "sessions.json")
    tok = auth.Sessions(path=path).create("bob")
    # "restart": doi tuong moi hoan toan, chi con file tren dia
    assert auth.Sessions(path=path).get(tok) == "bob"


def test_session_file_does_not_store_raw_token(tmp_path):
    """Doc trom file phien khong the mao danh: chi co hash."""
    path = str(tmp_path / "sessions.json")
    tok = auth.Sessions(path=path).create("bob")
    raw = json.loads(open(path, encoding="utf-8").read())
    assert tok not in json.dumps(raw)
    (stored_key,) = raw["sessions"].keys()
    assert len(stored_key) == 64 and stored_key != tok       # sha256 hex


def test_expired_session_is_not_restored(tmp_path):
    path = str(tmp_path / "sessions.json")
    clock = [1000.0]
    s = auth.Sessions(ttl=60, now=lambda: clock[0], path=path)
    tok = s.create("bob")
    clock[0] += 61
    assert auth.Sessions(ttl=60, now=lambda: clock[0], path=path).get(tok) is None


def test_destroy_and_destroy_all(tmp_path):
    path = str(tmp_path / "sessions.json")
    s = auth.Sessions(path=path)
    a, b, other = s.create("bob"), s.create("bob"), s.create("alice")
    s.destroy(a)
    assert s.get(a) is None and s.get(b) == "bob"
    assert s.destroy_all("bob") == 1              # con lai dung 1 phien cua bob
    assert s.get(b) is None and s.get(other) == "alice"


def test_sessions_without_path_stay_in_memory(tmp_path, monkeypatch):
    """Khong truyen path -> khong dung toi dia (test cu van chay nhu cu)."""
    monkeypatch.chdir(tmp_path)
    s = auth.Sessions()
    tok = s.create("bob")
    assert s.get(tok) == "bob"
    assert list(tmp_path.iterdir()) == []


def test_corrupt_session_file_is_ignored(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text("{khong-phai-json", encoding="utf-8")
    s = auth.Sessions(path=str(path))            # khong duoc nem loi
    assert len(s) == 0
    assert s.get(s.create("bob")) == "bob"       # van dung duoc binh thuong
