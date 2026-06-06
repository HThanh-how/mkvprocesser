import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import catch, fetch  # noqa: E402


def test_cookies_to_netscape_roundtrips_with_loader(tmp_path):
    cookies = [
        {"name": "sid", "value": "ABC", "domain": ".example.com", "path": "/",
         "secure": True, "expires": 1893456000},
        {"name": "t", "value": "x", "domain": "host.com", "path": "/p",
         "secure": False, "expires": -1},
    ]
    p = tmp_path / "c.txt"
    p.write_text(catch.cookies_to_netscape(cookies), encoding="utf-8")
    back = fetch.load_cookies_txt(str(p))               # doc lai bang loader cua fetch
    assert len(back) == 2
    sid = next(c for c in back if c["name"] == "sid")
    assert sid["value"] == "ABC" and sid["domain"] == ".example.com" and sid["secure"] is True
    assert "expires" in sid
    t = next(c for c in back if c["name"] == "t")
    assert t["secure"] is False and "expires" not in t  # expiry <= 0 -> cookie phien


def test_catch_session_state_without_browser():
    s = catch.CatchSession("http://127.0.0.1:1")        # CDP khong ton tai
    assert s.running() is False
    assert s.captured() == []
    snap = s.snapshot()
    assert snap["running"] is False and snap["media"] == [] and snap["error"] == ""
    s.clear()                                           # khong nem loi khi rong
