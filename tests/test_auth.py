import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import auth  # noqa: E402


def test_hash_and_verify_roundtrip():
    h = auth.hash_password("s3cret")
    assert h.startswith("pbkdf2_sha256$") and h.count("$") == 3
    assert auth.verify_password("s3cret", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("s3cret", "rac-khong-dung-dinh-dang")


def test_hash_salt_makes_distinct_outputs():
    assert auth.hash_password("same") != auth.hash_password("same")   # salt ngau nhien


def test_userstore_add_verify_persist(tmp_path):
    path = str(tmp_path / "users.json")
    s = auth.UserStore(path)
    s.add("an", "matkhau", role="admin")
    assert s.verify("an", "matkhau") == {"username": "an", "role": "admin"}
    assert s.verify("an", "sai") is None
    assert os.path.exists(path)
    s2 = auth.UserStore(path)                      # nap lai tu dia
    assert s2.verify("an", "matkhau")["role"] == "admin"


def test_userstore_duplicate_and_bad_role(tmp_path):
    s = auth.UserStore(str(tmp_path / "u.json"))
    s.add("a", "p")
    with pytest.raises(ValueError):
        s.add("a", "p2")                  # trung ten
    with pytest.raises(ValueError):
        s.add("b", "p", role="root")      # role sai


def test_userstore_disabled_blocks_login(tmp_path):
    s = auth.UserStore(str(tmp_path / "u.json"))
    s.add("a", "p")
    s.set_disabled("a", True)
    assert s.verify("a", "p") is None             # bi khoa -> khong vao duoc
    s.set_disabled("a", False)
    assert s.verify("a", "p")


def test_userstore_role_password_remove_and_admincount(tmp_path):
    s = auth.UserStore(str(tmp_path / "u.json"))
    s.add("a", "p", role="admin")
    s.add("b", "q", role="user")
    assert s.count_admins() == 1
    s.set_role("b", "admin")
    assert s.count_admins() == 2
    s.change_password("a", "new")
    assert s.verify("a", "new") and not s.verify("a", "p")
    s.remove("b")
    assert s.get("b") is None and s.count_admins() == 1
    assert [u["username"] for u in s.list()] == ["a"]


def test_sessions_create_get_expire_destroy():
    clock = {"t": 1000.0}
    sess = auth.Sessions(ttl=100, now=lambda: clock["t"])
    tok = sess.create("an")
    assert sess.get(tok) == "an"
    clock["t"] = 1101.0                            # qua han
    assert sess.get(tok) is None
    tok2 = sess.create("bo")
    sess.destroy(tok2)
    assert sess.get(tok2) is None
    assert sess.get(None) is None


def test_bootstrap_admin_creates_when_empty_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("MKV_ADMIN_PASS", raising=False)
    monkeypatch.setenv("MKV_ADMIN_USER", "boss")
    s = auth.UserStore(str(tmp_path / "u.json"))
    info = auth.bootstrap_admin(s, log=lambda *a: None)
    assert info["username"] == "boss" and info["password"]     # sinh mat khau ngau nhien
    assert s.verify("boss", info["password"])["role"] == "admin"
    assert auth.bootstrap_admin(s, log=lambda *a: None) is None  # da co user -> khong tao nua


def test_bootstrap_admin_uses_env_password(tmp_path, monkeypatch):
    monkeypatch.setenv("MKV_ADMIN_USER", "root")
    monkeypatch.setenv("MKV_ADMIN_PASS", "fixed-pass")
    s = auth.UserStore(str(tmp_path / "u.json"))
    info = auth.bootstrap_admin(s, log=lambda *a: None)
    assert info is None                                         # dung env -> khong tra mk sinh
    assert s.verify("root", "fixed-pass")["role"] == "admin"
