"""Hang doi tai-ve -> tach -> upload, kem XOAY VONG DIA (rotation) cho o nho.

Y tuong cot loi (tra loi "lam sao du dung luong"):
  Thu vien nam tren YouTube. Dia local chi la BAN LAM VIEC TAM. Xu ly TUAN TU
  tung link va XOA nguon ngay sau khi upload xong -> bat ky luc nao dia cung chi
  chua ~1 phim, KHONG phai ca kho. Vi the o nho (vai chuc GB) van du cho mot kho
  lon vo han, mien la xu ly dan.

`drain()` tiem cac ham phu thuoc (fetch/process/free_gb/remove/sleep) de test
duoc ma khong can mang hay ffmpeg.
"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone

from . import resources


class JobQueue:
    """Hang doi link an toan thread, kem nhat ky + lich su (xong/loi)."""

    def __init__(self, history_file=None, queue_file=None, node_id=""):
        self._items = []
        self._lock = threading.Lock()
        self._extra = {}       # url -> {cookies, referer} (cho link "bat tay")
        self._current_job = None
        self.current = None
        self.running = False
        self.log = []
        self.history = []      # [{url, status: done|error, name?, error?}]
        self.history_file = history_file
        self.queue_file = queue_file
        self.node_id = node_id or os.environ.get("MKV_NODE_ID", "") or "local"
        if history_file and os.path.exists(history_file):
            try:
                with open(history_file, encoding="utf-8") as f:
                    self.history = json.load(f) or []
            except (OSError, ValueError):
                self.history = []
        self._load_queue()

    @staticmethod
    def _job_id(url, extra=None):
        """ID on dinh de import/bang giao lap lai khong tao job trung."""
        data = {"url": (url or "").strip(), "referer": (extra or {}).get("referer") or ""}
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _write_queue_locked(self):
        if not self.queue_file:
            return
        payload = {
            "version": 1,
            "node": self.node_id,
            "pending": self._items,
            # Neu mat dien khi dang xu ly, job nay se duoc dua lai dau hang khi boot.
            "current": self._current_job,
        }
        try:
            os.makedirs(os.path.dirname(self.queue_file) or ".", exist_ok=True)
            tmp = self.queue_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.queue_file)
        except OSError:
            # Queue van chay trong RAM; log de operator nhin thay loi durability.
            self.log.append(f"(!) khong ghi duoc queue: {self.queue_file}")

    def _load_queue(self):
        if not self.queue_file or not os.path.exists(self.queue_file):
            return
        try:
            with open(self.queue_file, encoding="utf-8") as f:
                data = json.load(f) or {}
            pending = data.get("pending") or []
            current = data.get("current")
            records = ([current] if isinstance(current, dict) else []) + list(pending)
            seen = set()
            for rec in records:
                if not isinstance(rec, dict) or not rec.get("url"):
                    continue
                rec = dict(rec)
                rec.setdefault("extra", {})
                rec.setdefault("id", self._job_id(rec["url"], rec["extra"]))
                if rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                self._items.append(rec)
                if rec["extra"]:
                    self._extra[rec["url"]] = dict(rec["extra"])
            # Xoa trang thai current cu ngay: lan mat dien ke tiep van khong mat job.
            self._write_queue_locked()
        except (OSError, ValueError, TypeError):
            self.log.append(f"(!) queue hong/khong doc duoc: {self.queue_file}")

    def record_history(self, item):
        with self._lock:
            item = dict(item)
            if self._current_job:
                item.setdefault("id", self._current_job.get("id"))
                item.setdefault("node", self.node_id)
                item.setdefault("finished_at", self._now())
            self.history.append(item)
            self.history = self.history[-300:]
            self.current = None
            self._current_job = None
            self._write_queue_locked()
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
        extra = {k: v for k, v in {"cookies": cookies, "referer": referer}.items() if v}
        rec = {"id": self._job_id(url, extra), "url": url, "extra": extra,
               "queued_at": self._now(), "origin": self.node_id}
        with self._lock:
            active_ids = {x.get("id") for x in self._items}
            if self._current_job:
                active_ids.add(self._current_job.get("id"))
            completed_ids = {x.get("id") for x in self.history if x.get("status") == "done"}
            if rec["id"] in active_ids or rec["id"] in completed_ids:
                return False
            self._items.append(rec)
            if extra:
                self._extra[url] = extra
            self._write_queue_locked()
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
                self._current_job = self._items.pop(0)
                self.current = self._current_job["url"]
                self._write_queue_locked()
                return self.current
            self.running = False
            self.current = None
            return None

    def stop(self):
        """Tat co 'running' (luoi an toan khi worker thoat bat thuong)."""
        with self._lock:
            if self._current_job:
                self._items.insert(0, self._current_job)
                self._current_job = None
                self.current = None
            self.running = False
            self._write_queue_locked()

    def say(self, msg):
        with self._lock:
            self.log.append(str(msg))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "current": self.current,
                "pending": [x["url"] for x in self._items],
                "pending_jobs": [dict(x) for x in self._items],
                "history": list(self.history[-50:]),
                "log": self.log[-300:],
            }

    def export_pending(self) -> list:
        """Xuat metadata job co the tu tai o node khac; khong xuat file/torrent local."""
        with self._lock:
            out = []
            for rec in self._items:
                url = rec.get("url", "")
                extra = rec.get("extra") or {}
                if not url.lower().startswith(("http://", "https://", "magnet:")):
                    continue
                if extra.get("cookies"):
                    continue  # duong dan cookie la local, khong hop le tren node dich
                out.append(dict(rec))
            return out

    def import_jobs(self, records) -> list:
        """Nhap bundle tu node khac, idempotent theo job ID. Tra ID da co/da nhap."""
        accepted = []
        for incoming in records or []:
            if not isinstance(incoming, dict):
                continue
            url = (incoming.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://", "magnet:")):
                continue
            extra = dict(incoming.get("extra") or {})
            extra.pop("cookies", None)
            jid = incoming.get("id") or self._job_id(url, extra)
            with self._lock:
                active = {x.get("id") for x in self._items}
                if self._current_job:
                    active.add(self._current_job.get("id"))
                completed = {x.get("id") for x in self.history if x.get("status") == "done"}
                if jid not in active and jid not in completed:
                    self._items.append({
                        "id": jid, "url": url, "extra": extra,
                        "queued_at": incoming.get("queued_at") or self._now(),
                        "origin": incoming.get("origin") or "handoff",
                    })
                    if extra:
                        self._extra[url] = extra
                    self._write_queue_locked()
                accepted.append(jid)
        return accepted

    def acknowledge(self, ids) -> int:
        """Xoa job pending sau khi node dich xac nhan da luu ben vung."""
        wanted = set(ids or [])
        with self._lock:
            before = len(self._items)
            self._items = [x for x in self._items if x.get("id") not in wanted]
            removed = before - len(self._items)
            if removed:
                self._write_queue_locked()
            return removed


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
          free_gb_fn=resources.free_gb, remove_fn=os.remove, sleep_fn=time.sleep,
          should_continue_fn=None):
    """Rut can hang doi. Voi moi link: cho-dia -> tai -> tach+upload -> xoa nguon.

    1 link loi -> ghi nhan vao history roi CHAY TIEP link sau (khong dung ca hang).
    """
    dl_dir = cfg.get("downloads_dir") or cfg.get("inbox_dir", "inbox")
    os.makedirs(dl_dir, exist_ok=True)
    min_free = float(cfg.get("min_free_gb", 0) or 0)
    while True:
        if should_continue_fn is not None and not should_continue_fn():
            q.say("[drain] het ca xu ly; giu job con lai cho node ke tiep")
            q.stop()
            break
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
