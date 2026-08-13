"""Test cho lop phong thu web: CSRF, escaping HTML, header bao mat, chan SSRF."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("jinja2")
from fastapi.testclient import TestClient  # noqa: E402

from mkvtools import auth, jobs, security, templating, webui  # noqa: E402

XSS = '"><script>alert(1)</script>'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "USERS", auth.UserStore(str(tmp_path / "users.json")))
    monkeypatch.setattr(webui, "SESS", auth.Sessions())
    monkeypatch.setattr(webui, "THROTTLE", auth.LoginThrottle())
    monkeypatch.setattr(webui, "Q", jobs.JobQueue())
    webui.USERS.add("admin", "adminpass", role="admin")
    return TestClient(webui.app)


def _csrf(c):
    """Lay token nhu trinh duyet: mo mot trang roi doc cookie."""
    c.get("/login")
    return c.cookies.get(security.CSRF_COOKIE)


def _login(c):
    tok = _csrf(c)
    c.headers.update({security.CSRF_HEADER: tok})
    c.post("/login", data={"username": "admin", "password": "adminpass"})
    return tok


# --------------------------------------------------------------------- CSRF
def test_post_without_csrf_token_is_rejected(client):
    _login(client)
    client.headers.pop(security.CSRF_HEADER)          # bo token di
    r = client.post("/enqueue", data={"links": "https://example.com/a.mkv"})
    assert r.status_code == 403
    assert webui.Q.snapshot()["pending"] == []        # khong co gi lot vao hang doi


def test_post_with_wrong_csrf_token_is_rejected(client):
    _login(client)
    client.headers.update({security.CSRF_HEADER: "token-gia"})
    r = client.post("/enqueue", data={"links": "https://example.com/a.mkv"})
    assert r.status_code == 403
    assert webui.Q.snapshot()["pending"] == []


def test_post_with_valid_csrf_token_passes(client, monkeypatch):
    monkeypatch.setattr(webui, "_start_drain", lambda: None)
    _login(client)
    r = client.post("/enqueue", data={"links": "https://example.com/a.mkv"})
    assert r.status_code == 200
    assert webui.Q.snapshot()["pending"] == ["https://example.com/a.mkv"]


def test_csrf_token_accepted_from_form_field(client, monkeypatch):
    """Form HTML thuong (khong qua fetch) gui token o field an."""
    monkeypatch.setattr(webui, "_start_drain", lambda: None)
    tok = _login(client)
    client.headers.pop(security.CSRF_HEADER)
    r = client.post("/enqueue", data={"links": "https://example.com/b.mkv",
                                      "csrf_token": tok})
    assert r.status_code == 200
    assert webui.Q.snapshot()["pending"] == ["https://example.com/b.mkv"]


def test_handoff_api_is_exempt_from_csrf_but_needs_token(client, monkeypatch):
    """API may-may xac thuc bang header rieng, khong dung cookie -> khong can CSRF."""
    monkeypatch.setitem(webui.cfg, "handoff_token", "bi-mat")
    r = client.post("/api/handoff/ack", json={"ids": []})
    assert r.status_code == 401                        # thieu token handoff
    r = client.post("/api/handoff/ack", json={"ids": []},
                    headers={"x-mkv-handoff-token": "bi-mat"})
    assert r.status_code == 200 and r.json()["ok"] is True


# ------------------------------------------------------------------ XSS/escape
def test_classic_page_escapes_url_from_queue(client, monkeypatch):
    """Hoi quy cho lo leo quyen: user thuong dan link co <script>, admin mo
    /classic thi script KHONG duoc chay trong phien admin."""
    monkeypatch.setattr(webui, "_start_drain", lambda: None)
    _login(client)
    webui.Q.add(f"https://evil.test/{XSS}")
    body = client.get("/classic").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_classic_page_escapes_inbox_filename(client, monkeypatch):
    monkeypatch.setattr(webui, "_inbox_files", lambda: [f"phim{XSS}.mkv"])
    _login(client)
    body = client.get("/classic").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_classic_page_escapes_history_error(client, monkeypatch):
    monkeypatch.setattr(webui, "_start_drain", lambda: None)
    _login(client)
    webui.Q.record_history({"url": "https://x.test/a", "status": "error",
                            "error": XSS})
    body = client.get("/classic").text
    assert "<script>alert(1)</script>" not in body


def test_templating_autoescape_is_on():
    assert templating.env().autoescape is True
    out = templating.render("message.html", message=XSS, link_href="/", link_text="ve")
    assert "<script>" not in out and "&lt;script&gt;" in out


# ---------------------------------------------------------------- header bao mat
def test_security_headers_on_html_response(client):
    _login(client)
    h = client.get("/classic").headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "form-action 'self'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"


def test_no_hsts_header_on_plain_http(client):
    """HSTS tren HTTP la vo nghia; chi gui khi that su chay HTTPS."""
    assert "strict-transport-security" not in client.get("/login").headers


# ---------------------------------------------------------------------- SSRF
@pytest.mark.parametrize("host_ip", [
    "127.0.0.1",        # Chrome CDP nghe o day
    "10.1.2.3",
    "192.168.1.10",
    "172.16.0.5",
    "169.254.169.254",  # metadata cloud
    "::1",
    "0.0.0.0",
])
def test_ssrf_guard_blocks_internal_addresses(host_ip):
    with pytest.raises(security.UnsafeURL):
        security.assert_public_http_url("http://target.test/x",
                                        resolver=lambda h: [host_ip])


def test_ssrf_guard_allows_public_address():
    url = "https://cdn.example.com/v.mp4"
    assert security.assert_public_http_url(url, resolver=lambda h: ["93.184.216.34"]) == url


def test_ssrf_guard_blocks_when_any_resolved_ip_is_internal():
    """Ten mien tra ve nhieu IP: chi can mot cai noi bo la chan."""
    with pytest.raises(security.UnsafeURL):
        security.assert_public_http_url(
            "http://mixed.test/x", resolver=lambda h: ["93.184.216.34", "127.0.0.1"])


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/1", "ftp://x/y", ""])
def test_ssrf_guard_blocks_non_http_schemes(url):
    with pytest.raises(security.UnsafeURL):
        security.assert_public_http_url(url, resolver=lambda h: ["93.184.216.34"])


def test_shorts_preview_rejects_loopback_url(client):
    _login(client)
    r = client.get("/shorts/preview", params={"url": "http://127.0.0.1:9222/json"})
    assert r.status_code == 400 and "noi bo" in r.text
