import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("fastapi")        # can extra [web]
pytest.importorskip("httpx")          # TestClient dung httpx
from fastapi.testclient import TestClient  # noqa: E402

from mkvtools import auth, shorts, webui  # noqa: E402


def test_ensure_runtime_dirs_recreates_missing_paths(tmp_path):
    paths = {key: str(tmp_path / key) for key in webui._RUNTIME_DIR_KEYS}
    webui._ensure_runtime_dirs(paths)
    assert all((tmp_path / key).is_dir() for key in webui._RUNTIME_DIR_KEYS)


def test_short_download_name_is_human_readable():
    job = {
        "url": "https://www.threads.com/@bear.3391933/post/DXQyMRrEzMn",
        "name": "716×1272",
    }
    assert webui._short_download_name(job, "/tmp/AQO9hash.mp4") == (
        "threads_bear.3391933_DXQyMRrEzMn_716x1272.mp4"
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    # co lap: kho tai khoan rieng trong tmp + phien moi (khong dung secrets/ that)
    monkeypatch.setattr(webui, "USERS", auth.UserStore(str(tmp_path / "users.json")))
    monkeypatch.setattr(webui, "SESS", auth.Sessions())
    monkeypatch.setattr(webui, "THROTTLE", auth.LoginThrottle())   # co lap throttle moi test
    webui.USERS.add("admin", "adminpass", role="admin")
    webui.USERS.add("bob", "bobpass", role="user")
    return TestClient(webui.app)


def test_root_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"


def test_login_page_is_public(client):
    r = client.get("/login")
    assert r.status_code == 200 and "MKVTOOLS" in r.text and 'action="/login"' in r.text


def test_bad_login_does_not_authenticate(client):
    r = client.post("/login", data={"username": "admin", "password": "sai"},
                    follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers["location"]
    assert client.get("/", follow_redirects=False).status_code == 302   # van chua vao


def test_login_throttled_after_many_fails(client):
    for _ in range(6):
        client.post("/login", data={"username": "admin", "password": "sai"}, follow_redirects=False)
    r = client.post("/login", data={"username": "admin", "password": "adminpass"},
                    follow_redirects=False)
    assert r.headers["location"].startswith("/login")     # bi khoa du dung mat khau


def test_good_login_grants_access(client):
    r = client.post("/login", data={"username": "admin", "password": "adminpass"},
                    follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200 and "Threads, Instagram và TikTok" in home.text
    dashboard = client.get("/queue-ui")
    assert dashboard.status_code == 200 and "Hàng đợi" in dashboard.text
    assert "IS_IOS" in home.text and "Lưu vào Tệp" in home.text
    assert client.get("/shorts", follow_redirects=False).headers["location"] == "/"
    q = client.get("/queue").json()
    assert "disk_free_gb" in q and "pending" in q                # dashboard nap du lieu tu day


def test_batch_grab_creates_one_zip_job(client, tmp_path, monkeypatch):
    manager = shorts.ShortsManager(str(tmp_path / "shorts"))
    monkeypatch.setattr(webui, "SHORTS", manager)
    monkeypatch.setattr(webui, "_start_shorts", lambda: None)
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    items = [{
        "url": "https://cdn.example/one.mp4",
        "referer": "https://www.threads.com/@bear.3391933/post/one",
        "label": "720×1280",
    }]
    r = client.post("/shorts/grab-batch", data={
        "source_url": "https://www.threads.com/@bear.3391933",
        "items": __import__("json").dumps(items),
    })
    assert r.status_code == 200 and r.json()["count"] == 1
    job = manager.snapshot()["jobs"][0]
    assert job["mode"] == "batch"
    assert job["name"] == "threads_bear.3391933_videos.zip"
    assert job["media_items"] == items


def test_batch_grab_rejects_empty_list(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    r = client.post("/shorts/grab-batch", data={"source_url": "https://threads.com/@u",
                                                 "items": "[]"})
    assert r.status_code == 400


def test_video_file_forces_binary_attachment_for_ios(client, tmp_path, monkeypatch):
    manager = shorts.ShortsManager(str(tmp_path / "shorts"))
    monkeypatch.setattr(webui, "SHORTS", manager)
    video = tmp_path / "cdn-name.mp4"
    video.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"0" * 128)
    job = manager.add(
        "https://www.threads.com/@bear.3391933/post/CODE", "download",
        label="720×1280")
    job["status"] = "done"
    job["file"] = str(video)
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    r = client.get(f"/shorts/file/{job['id']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in r.headers["content-disposition"]
    assert "threads_bear.3391933_CODE_720x1280.mp4" in r.headers["content-disposition"]


def test_admin_page_is_admin_only(client):
    client.post("/login", data={"username": "bob", "password": "bobpass"})   # user thuong
    assert client.get("/admin").status_code == 403
    client.post("/login", data={"username": "admin", "password": "adminpass"})  # admin
    r = client.get("/admin")
    assert r.status_code == 200 and 'action="/admin/add"' in r.text
    u = client.get("/admin/users").json()
    assert u["me"] == "admin" and any(x["username"] == "bob" for x in u["users"])


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


def test_me_and_self_password_change(client):
    client.post("/login", data={"username": "bob", "password": "bobpass"})   # user thuong
    assert client.get("/me").json()["username"] == "bob"
    r = client.post("/me/password", data={"password": "newbobpass"}, follow_redirects=False)
    assert r.json()["ok"] is True
    assert webui.USERS.verify("bob", "newbobpass")                           # da doi
    assert client.post("/me/password", data={"password": "x"}).json()["ok"] is False  # qua ngan


def test_catch_page_and_captured_json(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    r = client.get("/catch")
    assert r.status_code == 200 and "MKVTOOLS" in r.text and "/catch/captured" in r.text
    cfgj = client.get("/catch/config").json()
    assert "novnc_port" in cfgj
    j = client.get("/catch/captured").json()
    assert j["running"] is False and j["media"] == []     # chua start -> rong, khong loi


def test_videos_page_and_list(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    assert client.get("/videos").status_code == 200 and "MKVTOOLS" in client.get("/videos").text
    j = client.get("/videos/list").json()
    assert "ok" in j           # khong co token YouTube trong test -> ok False, KHONG crash


def test_settings_admin_only_and_save(client, tmp_path, monkeypatch):
    from mkvtools import config
    monkeypatch.setattr(config, "ui_settings_path", lambda: str(tmp_path / "ui.json"))
    client.post("/login", data={"username": "bob", "password": "bobpass"})        # user thuong
    assert client.get("/settings/get").status_code == 403
    client.post("/login", data={"username": "admin", "password": "adminpass"})    # admin
    g = client.get("/settings/get").json()
    assert "privacy" in g and "master_playlist" in g
    r = client.post("/settings/save", json={"min_free_gb": 9, "privacy": "private",
                                            "master_playlist": "X", "upload": True})
    assert r.json()["ok"] is True
    assert webui.cfg["master_playlist"] == "X" and webui.cfg["min_free_gb"] == 9.0


def test_settings_save_rejects_bad_enum(client, tmp_path, monkeypatch):
    from mkvtools import config
    monkeypatch.setattr(config, "ui_settings_path", lambda: str(tmp_path / "ui.json"))
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    r = client.post("/settings/save", json={"privacy": "bogus"})
    assert r.json()["ok"] is False                                  # enum sai -> tu choi


def test_admin_cannot_delete_self(client):
    client.post("/login", data={"username": "admin", "password": "adminpass"})
    client.post("/admin/action", data={"username": "admin", "action": "delete"},
                follow_redirects=False)
    assert webui.USERS.get("admin") is not None     # tu-xoa bi chan -> van con
