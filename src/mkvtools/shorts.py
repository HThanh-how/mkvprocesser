"""Video NGAN (Threads/Reels/TikTok/YouTube Short...): tai ve -> hoac GIU file cho
nguoi dung tai ve may, hoac UP thang len YouTube dang Short.

Khac voi pipeline phim: KHONG tach audio nhieu ngon ngu, KHONG xoay vong dia. Moi job
chi tai 1 clip ngan roi giu lai (download) hoac day len YouTube (upload). Hang doi
rieng, xu ly tuan tu o 1 luong nen.

Manager thuan trang thai (khong import mang/google) -> de test; webui tiem fetch/upload.
"""
import os
import re
import threading

# Mo ta + tag gan vao Short khi up (YouTube tu phan loai Short neu clip doc & <= 3 phut).
SHORTS_DESC = "#Shorts"
SHORTS_TAGS = ["Shorts", "Short"]


def short_title(src: str) -> str:
    """Tieu de Short tu ten file da tai (bo duoi, gach duoi -> khoang trang) + #Shorts.

    Gioi han 100 ky tu (gioi han YouTube), chua ca duoi ' #Shorts'.
    """
    base = os.path.splitext(os.path.basename(src or ""))[0]
    base = re.sub(r"[_]+", " ", base).strip()
    base = re.sub(r"\s{2,}", " ", base) or "Short"
    tag = " #Shorts"
    return (base[: 100 - len(tag)]).strip() + tag


class ShortsManager:
    """Hang doi job video ngan (download | upload), an toan thread.

    Moi job: {id, url, mode, status(queued|running|done|error),
              name, file, video_url, error, log:[...]}
    """

    def __init__(self, dest_dir: str):
        self.dest_dir = dest_dir
        self._jobs = {}        # id -> job dict
        self._order = []       # id theo thu tu them (cho hien thi)
        self._queue = []       # id dang cho xu ly
        self._lock = threading.Lock()
        self._running = False
        self._seq = 0

    def add(self, url: str, mode: str, media_url: str = None, referer: str = None,
            label: str = ""):
        """Them job. mode: download | upload | probe.

        media_url: neu co (vd clip da chon tu danh sach) -> tai THANG url nay,
        khong sniff lai. label: ten hien thi (vd '720x1280').
        """
        url = (url or "").strip()
        if not url or url.startswith("#"):
            return None
        if mode not in ("download", "upload", "probe"):
            mode = "download"
        with self._lock:
            self._seq += 1
            jid = self._seq
            job = {"id": jid, "url": url, "mode": mode, "status": "queued",
                   "name": label or "", "file": None, "video_url": "", "error": "",
                   "media_url": media_url, "referer": referer, "candidates": [], "log": []}
            self._jobs[jid] = job
            self._order.append(jid)
            self._queue.append(jid)
        return job

    def try_start(self) -> bool:
        """Danh dau 'dang chay' neu dang ranh. True -> nguoi goi khoi dong worker."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            return True

    def next_job(self):
        """Lay job ke (danh dau running). Het hang -> tat 'running' + tra None (nguyen tu)."""
        with self._lock:
            while self._queue:
                job = self._jobs.get(self._queue.pop(0))
                if job:
                    job["status"] = "running"
                    return job
            self._running = False
            return None

    def stop(self):
        with self._lock:
            self._running = False

    def log(self, job, msg):
        with self._lock:
            job["log"].append(str(msg))
            job["log"] = job["log"][-120:]

    def get(self, jid):
        try:
            jid = int(jid)
        except (TypeError, ValueError):
            return None
        with self._lock:
            return self._jobs.get(jid)

    def remove(self, jid) -> bool:
        try:
            jid = int(jid)
        except (TypeError, ValueError):
            return False
        with self._lock:
            if jid not in self._jobs:
                return False
            self._jobs.pop(jid, None)
            if jid in self._order:
                self._order.remove(jid)
            if jid in self._queue:
                self._queue.remove(jid)
            return True

    def snapshot(self) -> dict:
        with self._lock:
            jobs = []
            for i in self._order:
                j = self._jobs.get(i)
                if not j:
                    continue
                jobs.append({**j, "log": j["log"][-40:]})
            return {"running": self._running, "jobs": list(reversed(jobs))}
