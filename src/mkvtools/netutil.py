"""Phan tich URL proxy. Thuan (khong phu thuoc google/httplib2) -> test duoc.

Ho tro: http://, https://, socks5://, socks5h://, socks4://, hoac chi 'host:port'
(mac dinh http). Co the kem user:pass@.
"""
from __future__ import annotations

from urllib.parse import urlparse


def parse_proxy(url: str | None) -> dict | None:
    """url -> {scheme, host, port, user, pass} hoac None neu rong/khong hop le."""
    if not url or not url.strip():
        return None
    raw = url.strip()
    if "://" not in raw:
        raw = "http://" + raw                 # 'host:port' -> mac dinh http
    u = urlparse(raw)
    if not u.hostname:
        return None
    scheme = (u.scheme or "http").lower()
    default_port = 1080 if scheme.startswith("socks") else 8080
    return {
        "scheme": scheme,
        "host": u.hostname,
        "port": u.port or default_port,
        "user": u.username,
        "pass": u.password,
    }
