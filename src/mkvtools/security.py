"""Ba lop phong thu dung chung cho web GUI: CSRF, header bao mat, chan SSRF.

Tach khoi webui.py de test duoc tung phan ma khong can dung server.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
import socket
import urllib.parse

# ---------------------------------------------------------------------- CSRF
#
# Kieu "double-submit cookie": server dat cookie `mkv_csrf` (KHONG httponly de
# JS doc duoc), moi request thay doi trang thai phai gui lai dung gia tri do
# qua field `csrf_token` hoac header `X-CSRF-Token`. Trang khac domain doc
# duoc cookie cua ta, nen khong biet gia tri de gui kem.
#
# Han che da biet: neu ke tan cong kiem soat mot subdomain cung site, ho co
# the ghi de cookie nay. Trien khai hien tai chi chay tren mot host (localhost
# hoac Tailscale) nen chua thanh van de; neu sau nay dat sau ten mien co
# subdomain khong tin cay thi phai chuyen sang token ky HMAC theo phien.
CSRF_COOKIE = "mkv_csrf"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

# Method khong doi trang thai -> khong can token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(cookie_value: str | None, sent_value: str | None) -> bool:
    """So token trong cookie voi token client gui len (chong-timing)."""
    if not cookie_value or not sent_value:
        return False
    return hmac.compare_digest(str(cookie_value), str(sent_value))


# ------------------------------------------------------------------- headers
#
# CSP o day CO 'unsafe-inline'/'unsafe-eval' vi giao dien hien nay nap Tailwind
# tu CDN (JIT compiler can eval) va dung <script> inline trong tung trang.
# Cac directive con lai van co gia tri that: frame-ancestors chan clickjacking,
# form-action chan cuop form, base-uri chan chen <base>, object-src chan plugin.
# Muon CSP that chat thi phai bundle Tailwind vao /web/ va tach script inline
# ra file — xem ROADMAP.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Trang nay khong dung cac API do; tat de giam be mat tan cong.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


def apply_security_headers(headers, https: bool = False) -> None:
    """Gan header bao mat vao response (khong ghi de neu route da tu dat)."""
    for k, v in SECURITY_HEADERS.items():
        headers.setdefault(k, v)
    if https:
        # Chi gui HSTS tren HTTPS: gui tren HTTP la vo nghia va de gay nham.
        headers.setdefault("Strict-Transport-Security",
                           "max-age=31536000; includeSubDomains")


# ---------------------------------------------------------------------- SSRF
#
# /shorts/preview nhan mot URL bat ky roi SERVER tu tai va tra noi dung ve
# trinh duyet. Neu khong chan, mot tai khoan `user` co the doc dich vu noi bo
# ma may chu nhin thay nhung ho thi khong: Chrome CDP o 127.0.0.1:9222 (dieu
# khien duoc ca trinh duyet!), 169.254.169.254 cua cloud metadata, hay bat ky
# service nao trong LAN.
_ALLOWED_SCHEMES = ("http", "https")


class UnsafeURL(ValueError):
    """URL tro toi dia chi noi bo / khong duoc phep tai ho."""


def _ip_is_public(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def assert_public_http_url(url: str, resolver=None) -> str:
    """Kiem URL truoc khi server tu di tai. Nem UnsafeURL neu khong dat.

    resolver: ham (host) -> danh sach IP dang chuoi; mac dinh dung DNS that.
    Tach ra de test khong can mang.

    Luu y con lai (DNS rebinding): giua luc kiem va luc ket noi, ban ghi DNS co
    the doi. Chan triet de doi phai ghim IP vao socket luc connect; o muc rui ro
    cua cong cu nay, kiem sau khi resolve la du va duoc ghi nhan ro o day.
    """
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURL("chi chap nhan http/https")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("URL thieu hostname")
    if os.environ.get("MKV_ALLOW_PRIVATE_FETCH") == "1":
        return url          # thoat hiem cho lab/test noi bo, mac dinh TAT
    resolve = resolver or _resolve
    try:
        addrs = resolve(host)
    except OSError as e:
        raise UnsafeURL(f"khong phan giai duoc ten mien: {host}") from e
    if not addrs:
        raise UnsafeURL(f"khong phan giai duoc ten mien: {host}")
    for a in addrs:
        if not _ip_is_public(a):
            raise UnsafeURL(f"dia chi noi bo bi chan: {host} -> {a}")
    return url


def _resolve(host: str) -> list:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [i[4][0] for i in infos]
