import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("fastapi")        # can extra [web]
pytest.importorskip("httpx")          # TestClient dung httpx
from fastapi.testclient import TestClient  # noqa: E402

from mkvtools import auth, webui  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # co lap: kho tai khoan rieng trong tmp + phien moi (khong dung secrets/ that)
    monkeypatch.setattr(webui, "USERS", auth.UserStore(str(tmp_path / "users.json")))
    monkeypatch.setattr(webui, "SESS", auth.Sessions())
    webui.USERS.add("admin", "adminpass", role="admin")
    webui.USERS.add("bob", "bobpass", role="user")
    return TestClient(webui.app)


def test_root_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"


def test_login_page_is_public(client):
    r = client.get("/login")
    assert r.status_code == 200 and "Dang nhap" in r.text


def test_bad_login_does_not_authenticate(client):
    r = client.post("/login", data={"username": "admin", "password": "sai"},
                    follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers["location"]
    assert client.get("/", follow_redirects=False).status_code == 302   # van chua vao


def test_good_login_grants_access(client):
    r = client.post("/login", data={"username": "admin", "password": "adminpass"},
                    follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200 and "Dan link" in home.text


def test_admin_page_is_admin_only(client):
    client.post("/login", data={"username": "bob", "password": "bobpass"})   # user thuong
    assert client.get("/admin").status_code == 403
    client.post("/login", data={"username": "admin", "password": "adminpass"})  # admin
    r = client.get("/admin")
    assert r.status_code == 200 and "Quan tri" in r.text


def test_admin_can_add_user(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    client.post("/admin/add", data={"username": "carol", "password": "c123", "role": "user"},
                follow_redirects=False)
    assert webui.USERS.verify("carol", "c123") == {"username": "carol", "role": "user"}


def test_non_admin_cannot_add_user(client):
    client.post("/login", data={"username": "bob", "password": "bobpass"})
    r = client.post("/admin/add", data={"username": "x", "password": "y", "role": "user"},
                    follow_redirects=False)
    assert r.status_code == 403 and webui.USERS.get("x") is None


def test_logout_clears_session(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    assert client.get("/", follow_redirects=False).status_code == 200
    client.get("/logout", follow_redirects=False)
    assert client.get("/", follow_redirects=False).status_code == 302       # da dang xuat


def test_admin_cannot_delete_self(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    client.post("/admin/action", data={"username": "admin", "action": "delete"},
                follow_redirects=False)
    assert webui.USERS.get("admin") is not None     # tu-xoa bi chan -> van con
