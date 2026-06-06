"""Hang doi tai-ve -> tach -> upload, kem XOAY VONG DIA (rotation) cho o nho.

Y tuong cot loi (tra loi "lam sao du dung luong"):
  Thu vien nam tren YouTube. Dia local chi la BAN LAM VIEC TAM. Xu ly TUAN TU
  tung link va XOA nguon ngay sau khi upload xong -> bat ky luc nao dia cung chi
  chua ~1 phim, KHONG phai ca kho. Vi the o nho (vai chuc GB) van du cho mot kho
  lon vo han, mien la xu ly dan.

`drain()` tiem cac ham phu thuoc (fetch/process/free_gb/remove/sleep) de test
duoc ma khong can mang hay ffmpeg.
"""
import json
import os
import threading
import time

from . import resources


class JobQueue:
    """Hang doi link an toan thread, kem nhat ky + lich su (xong/loi)."""

    def __init__(self, history_file=None):
        self._items = []
        self._lock = threading.Lock()
        self._extra = {}       # url -> {cookies, referer} (cho link "bat tay")
        self.current = None
        self.running = False
        self.log = []
        self.history = []      # [{url, status: done|error, name?, error?}]
        self.history_file = history_file
        if history_file and os.path.exists(history_file):
            try:
                with open(history_file, encoding="utf-8") as f:
                    self.history = json.load(f) or []
            except (OSError, ValueError):
                self.history = []

    def record_history(self, item):
        with self._lock:
            self.history.append(item)
            self.history = self.history[-300:]
        if not self.history_file:
            return
        try:
            os.makedirs(os.path.dirname(self.history_file) or ".", exist_ok=True)
            tmp = self.history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False)
            os.replace(tmp, self.history_file)
        except OSError:
            pass

    def add(self, url, cookies=None, referer=None) -> bool:
        url = (url or "").strip()
        if not url or url.startswith("#"):
            return False
        with self._lock:
            self._items.append(url)
            if cookies or referer:
                self._extra[url] = {"cookies": cookies, "referer": referer}
        return True

    def extra_for(self, url) -> dict:
        with self._lock:
            return dict(self._extra.get(url) or {})

    def add_many(self, text) -> int:
        return sum(1 for line in (text or "").splitlines() if self.add(line))

    def try_start(self) -> bool:
        """Danh dau 'dang chay' neu dang ranh. True -> nguoi goi phai khoi dong worker.

        Nguyen tu voi pop(): tranh ket link khi vua-them-vua-rut-can hang doi.
        """
        with self._lock:
            if self.running:
                return False
            self.running = True
            return True

    def pop(self):
        """Lay link ke. Het hang -> tu TAT co 'running' (nguyen tu) + tra None."""
        with self._lock:
            if self._items:
                self.current = self._items.pop(0)
                return self.current
            self.running = False
            self.current = None
            return None

    def stop(self):
        """Tat co 'running' (luoi an toan khi worker thoat bat thuong)."""
        with self._lock:
            self.running = False

    def say(self, msg):
        with self._lock:
            self.log.append(str(msg))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "current": self.current,
                "pending": list(self._items),
                "history": list(self.history[-50:]),
                "log": self.log[-300:],
            }


def wait_disk(path, min_free_gb, free_gb_fn, sleep_fn, say, tries=24, every=5) -> bool:
    """Cho den khi du dia (xoay vong). Tra True neu du, False neu het luot cho.

    Khong du sau `tries` luot -> tra False de ben goi tu quyet (van thu tai).
    """
    if not min_free_gb or min_free_gb <= 0:
        return True
    for _ in range(tries):
        free = free_gb_fn(path)
        if free >= min_free_gb:
            return True
        say(f"  (dia) con {free:.1f}GB < {min_free_gb:.0f}GB -> cho don cho...")
        sleep_fn(every)
    return False


def drain(q: JobQueue, cfg: dict, *, fetch_fn, process_fn,
          free_gb_fn=resources.free_gb, remove_fn=os.remove, sleep_fn=time.sleep):
    """Rut can hang doi. Voi moi link: cho-dia -> tai -> tach+upload -> xoa nguon.

    1 link loi -> ghi nhan vao history roi CHAY TIEP link sau (khong dung ca hang).
    """
    dl_dir = cfg.get("downloads_dir") or cfg.get("inbox_dir", "inbox")
    os.makedirs(dl_dir, exist_ok=True)
    min_free = float(cfg.get("min_free_gb", 0) or 0)
    while True:
        url = q.pop()       # pop() tu set q.current + tat 'running' khi het hang (nguyen tu)
        if not url:
            break
        src = None
        try:
            wait_disk(dl_dir, min_free, free_gb_fn, sleep_fn, q.say)
            q.say(f"[tai] {url}")
            ex = q.extra_for(url)
            src = fetch_fn(url, dl_dir, log=q.say, cookies=ex.get("cookies"), referer=ex.get("referer"))
            q.say(f"[da tai] {os.path.basename(src)} -> tach + upload")
            process_fn(src, cfg, log=q.say)
            # rotation: xoa nguon de tra lai dia cho link sau (neu pipeline chua xoa)
            if src and os.path.exists(src):
                try:
                    remove_fn(src)
                    q.say(f"[don] xoa nguon {os.path.basename(src)} -> giai phong dia")
                except OSError as e:
                    q.say(f"  (!) khong xoa duoc nguon: {e}")
            q.record_history({"url": url, "status": "done",
                              "name": os.path.basename(src) if src else url})
            q.say(f"[OK] {url}")
        except Exception as e:        # noqa: BLE001 - 1 link loi khong duoc keo sap ca hang
            q.record_history({"url": url, "status": "error", "error": str(e)})
            q.say(f"[LOI] {url}: {e}")
        finally:
            q.current = None
