import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import netutil as N  # noqa: E402


def test_empty_or_none_returns_none():
    assert N.parse_proxy("") is None
    assert N.parse_proxy(None) is None
    assert N.parse_proxy("   ") is None


def test_http_with_port():
    p = N.parse_proxy("http://127.0.0.1:8080")
    assert p["scheme"] == "http" and p["host"] == "127.0.0.1" and p["port"] == 8080
    assert p["user"] is None and p["pass"] is None


def test_socks5_with_auth():
    p = N.parse_proxy("socks5://bob:secret@proxy.local:1080")
    assert p["scheme"] == "socks5" and p["host"] == "proxy.local" and p["port"] == 1080
    assert p["user"] == "bob" and p["pass"] == "secret"


def test_bare_host_port_defaults_http():
    p = N.parse_proxy("10.0.0.1:3128")
    assert p["scheme"] == "http" and p["host"] == "10.0.0.1" and p["port"] == 3128


def test_default_ports_by_scheme():
    assert N.parse_proxy("http://h")["port"] == 8080
    assert N.parse_proxy("socks5://h")["port"] == 1080
