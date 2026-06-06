"""Che do "Bat tay": gan vao Chromium dieu khien-tay (qua noVNC) bang CDP, "nghe
len" network de bat URL media nguoi dung phat, + xuat cookie de tai dung session.

Chromium chay san ben ngoai (systemd, headful tren Xvfb, CDP 127.0.0.1:9222) va
nguoi dung dieu khien qua noVNC. Module nay KHONG mo trinh duyet — chi GAN vao
qua connect_over_cdp, lang nghe response, va loc media bang fetch.is_media_url.

Vi sao chay tren server: nhieu stream khoa theo IP/session/token -> phai tai TU
CHINH may da mo trang. Bat tay tren server -> cookie + IP khop -> tai duoc.
"""
import threading
import time

from . import fetch


def cookies_to_netscape(cookies: list) -> str:
    """Doi list cookie (kieu Playwright) -> noi dung cookies.txt (Netscape)."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if c.get("secure") else "FALSE"
        try:
            expiry = int(c.get("expires") or 0)
        except (TypeError, ValueError):
            expiry = 0
        lines.append("\t".join([domain, flag, c.get("path", "/") or "/", secure,
                                str(max(expiry, 0)), c.get("name", ""), c.get("value", "")]))
    return "\n".join(lines) + "\n"


class CatchSession:
    """Phien "bat tay": lang nghe CDP, tich luy URL media nguoi dung phat."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self._lock = threading.Lock()
        self._media = {}          # url -> {url, type, referer}
        self._running = False
        self._stop = threading.Event()
        self._err = ""

    # ---- trang thai (an toan thread) ----
    def running(self) -> bool:
        with self._lock:
            return self._running

    def captured(self) -> list:
        with self._lock:
            return list(self._media.values())

    def clear(self):
        with self._lock:
            self._media.clear()

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": self._running, "error": self._err,
                    "media": list(self._media.values())}

    # ---- vong doi ----
    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._err = ""
        self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def stop(self):
        self._stop.set()

    def _record(self, resp):
        try:
            u = resp.url
            ct = resp.headers.get("content-type", "")
        except Exception:        # noqa: BLE001
            return
        if not fetch.is_media_url(u, ct):
            return
        try:
            ref = resp.request.headers.get("referer") or resp.frame.url
        except Exception:        # noqa: BLE001
            ref = ""
        with self._lock:
            if u not in self._media:
                self._media[u] = {"url": u, "type": ct, "referer": ref}

    def _run(self):
        try:
            from playwright.sync_api import sync_playwright  # extra [browser]
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(self.cdp_url)
                browser.on("disconnected", lambda *_: self._stop.set())
                for ctx in browser.contexts:
                    ctx.on("response", self._record)
                    ctx.on("page", lambda pg: pg.on("response", self._record))
                while not self._stop.is_set():
                    time.sleep(0.5)
                browser.close()
        except Exception as e:        # noqa: BLE001
            with self._lock:
                self._err = str(e)
        finally:
            with self._lock:
                self._running = False

    # ---- xuat cookie phien hien tai -> cookies.txt (tai dung session) ----
    def export_cookies(self, path: str) -> int:
        """Lay cookie cua Chromium qua CDP, ghi cookies.txt. Tra so cookie."""
        from playwright.sync_api import sync_playwright  # extra [browser]
        cookies = []
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(self.cdp_url)
            for ctx in browser.contexts:
                cookies += ctx.cookies()
            browser.close()
        with open(path, "w", encoding="utf-8") as f:
            f.write(cookies_to_netscape(cookies))
        return len(cookies)
