"""Cache co TTL de han che goi YouTube API (tiet kiem quota): lay 1 lan/ngay roi
moi noi doc cache. Backend: Redis (neu co redis_url + thu vien) hoac file JSON.

- get(key) -> (value, age_giay) neu co (KE CA het han), nguoc lai (None, None).
- fresh(age) -> con han theo TTL khong.
- Loi API (vd het quota) -> ben goi dung cache CU (stale) thay vi chet.
"""
import json
import os
import time


class Cache:
    def __init__(self, redis_url="", file_dir="work/cache", ttl=86400, now=time.time):
        self.ttl = int(ttl or 0)
        self._now = now
        self._dir = file_dir
        self._r = None
        if redis_url:
            try:
                import redis  # extra [cache]
                self._r = redis.from_url(redis_url, decode_responses=True)
                self._r.ping()
            except Exception:        # noqa: BLE001 - khong co redis -> ve file
                self._r = None
        if self._r is None:
            os.makedirs(self._dir, exist_ok=True)

    def backend(self) -> str:
        return "redis" if self._r is not None else "file"

    def _path(self, key):
        return os.path.join(self._dir, key.replace(":", "_").replace("/", "_") + ".json")

    def _read_raw(self, key):
        if self._r is not None:
            return self._r.get(key)
        p = self._path(key)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()

    def get(self, key):
        """Tra (value, age_giay). Co the het han (caller tu kiem fresh)."""
        raw = self._read_raw(key)
        if not raw:
            return None, None
        try:
            obj = json.loads(raw)
        except ValueError:
            return None, None
        return obj.get("v"), max(0.0, self._now() - obj.get("_ts", 0))

    def fresh(self, age, ttl=None) -> bool:
        t = self.ttl if ttl is None else int(ttl or 0)
        return age is not None and (not t or age <= t)

    def set(self, key, value):
        payload = json.dumps({"_ts": self._now(), "v": value}, ensure_ascii=False)
        if self._r is not None:
            self._r.set(key, payload, ex=self.ttl * 3 if self.ttl else None)  # giu de phuc vu stale
            return
        p = self._path(key)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, p)
