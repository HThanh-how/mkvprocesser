"""Tai khoan + dang nhap cho GUI: login + phan quyen (admin / user).

- Mat khau bam bang pbkdf2_hmac (stdlib) -> KHONG them dependency.
- Nguoi dung luu JSON tren dia (ghi nguyen tu). Phien (session) giu trong RAM,
  restart server = dang nhap lai (chap nhan duoc cho cong cu ca nhan).
- Bootstrap: chua co user nao -> tao admin tu env MKV_ADMIN_USER/MKV_ADMIN_PASS,
  neu khong dat MKV_ADMIN_PASS thi sinh mat khau ngau nhien va in ra console.

Cac ham bam/kiem mat khau + UserStore + Sessions deu thuan, de unit-test.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

ROLES = ("admin", "user")
_ITER = 200_000


def hash_password(pw: str, salt: bytes | None = None) -> str:
    """Bam mat khau -> chuoi 'pbkdf2_sha256$iter$salt_hex$hash_hex'."""
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    """So mat khau voi chuoi da bam (so sanh chong-timing)."""
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


class UserStore:
    """Kho tai khoan tren dia (JSON). An toan thread, ghi nguyen tu."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.users: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.users = (json.load(f) or {}).get("users", {})

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def add(self, username: str, password: str, role: str = "user"):
        username = (username or "").strip()
        if not username:
            raise ValueError("ten dang nhap rong")
        if role not in ROLES:
            raise ValueError(f"role khong hop le: {role!r}")
        with self._lock:
            if username in self.users:
                raise ValueError(f"da co tai khoan {username!r}")
            self.users[username] = {"pw": hash_password(password), "role": role, "disabled": False}
            self._save()

    def verify(self, username: str, password: str):
        """Tra {username, role} neu dung va khong bi khoa, nguoc lai None."""
        u = self.users.get(username)
        if not u or u.get("disabled"):
            return None
        if verify_password(password, u.get("pw", "")):
            return {"username": username, "role": u.get("role", "user")}
        return None

    def get(self, username: str):
        u = self.users.get(username)
        if not u:
            return None
        return {"username": username, "role": u.get("role", "user"),
                "disabled": bool(u.get("disabled"))}

    def set_role(self, username: str, role: str):
        if role not in ROLES:
            raise ValueError(f"role khong hop le: {role!r}")
        with self._lock:
            if username not in self.users:
                raise ValueError(f"khong co tai khoan {username!r}")
            self.users[username]["role"] = role
            self._save()

    def set_disabled(self, username: str, disabled: bool):
        with self._lock:
            if username not in self.users:
                raise ValueError(f"khong co tai khoan {username!r}")
            self.users[username]["disabled"] = bool(disabled)
            self._save()

    def change_password(self, username: str, password: str):
        with self._lock:
            if username not in self.users:
                raise ValueError(f"khong co tai khoan {username!r}")
            self.users[username]["pw"] = hash_password(password)
            self._save()

    def remove(self, username: str):
        with self._lock:
            self.users.pop(username, None)
            self._save()

    def count_admins(self) -> int:
        return sum(1 for u in self.users.values()
                   if u.get("role") == "admin" and not u.get("disabled"))

    def list(self) -> list:
        return [{"username": k, "role": v.get("role", "user"),
                 "disabled": bool(v.get("disabled"))}
                for k, v in sorted(self.users.items())]

    def __len__(self):
        return len(self.users)


def _token_key(token: str) -> str:
    """Khoa luu tren dia = SHA-256 cua token.

    Khong luu token goc: file phien bi doc trom cung khong dung lai duoc de mao
    danh, giong nguyen tac khong luu mat khau dang ro.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class Sessions:
    """Phien dang nhap. Co `path` -> ghi xuong dia de restart khong dang xuat.

    Truoc day phien chi nam trong RAM, nen may vnpt tat sach luc 19:25 moi ngay
    la sang hom sau ai cung phai dang nhap lai. Voi `path`, phien song qua
    restart; khong truyen `path` (vd trong test) thi van la RAM thuan.

    Tren dia luu {hash(token): [username, han]} — xem _token_key().
    """

    def __init__(self, ttl: float = 7 * 24 * 3600, now=time.time, path: str | None = None):
        self._d: dict = {}
        self._lock = threading.Lock()
        self.ttl = ttl
        self._now = now
        self.path = path
        self._load()

    # -- dia -----------------------------------------------------------------
    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = (json.load(f) or {}).get("sessions", {})
        except (OSError, ValueError):
            return                      # file hong -> coi nhu chua co phien nao
        now = self._now()
        self._d = {k: (v[0], v[1]) for k, v in raw.items()
                   if isinstance(v, list) and len(v) == 2 and v[1] > now}

    def _save_locked(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"sessions": {k: [u, e] for k, (u, e) in self._d.items()}}, f)
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
        except OSError:
            pass          # mat tinh ben vung thi dang nhap lai, khong the sap service

    # -- API -----------------------------------------------------------------
    def create(self, username: str) -> str:
        tok = secrets.token_urlsafe(32)
        with self._lock:
            self._d[_token_key(tok)] = (username, self._now() + self.ttl)
            self._prune_locked()
            self._save_locked()
        return tok

    def get(self, token):
        if not token:
            return None
        key = _token_key(token)
        with self._lock:
            v = self._d.get(key)
            if not v:
                return None
            username, exp = v
            if self._now() > exp:
                del self._d[key]
                self._save_locked()
                return None
            return username

    def destroy(self, token):
        if not token:
            return
        with self._lock:
            if self._d.pop(_token_key(token), None) is not None:
                self._save_locked()

    def destroy_all(self, username: str) -> int:
        """Dang xuat moi phien cua mot tai khoan (dung khi khoa/doi mat khau)."""
        with self._lock:
            gone = [k for k, (u, _e) in self._d.items() if u == username]
            for k in gone:
                del self._d[k]
            if gone:
                self._save_locked()
            return len(gone)

    def _prune_locked(self):
        now = self._now()
        for k in [k for k, (_u, e) in self._d.items() if e <= now]:
            del self._d[k]

    def __len__(self):
        return len(self._d)


class LoginThrottle:
    """Chong do mat khau: khoa tam theo key (IP) sau nhieu lan dang nhap sai."""

    def __init__(self, max_fail=5, window=300, lock=300, now=time.time):
        self.max_fail = max_fail
        self.window = window        # cua so dem lan sai (giay)
        self.lock = lock            # thoi gian khoa sau khi vuot nguong (giay)
        self._now = now
        self._fails = {}
        self._lock = threading.Lock()

    def blocked(self, key) -> int:
        """Tra so giay con phai cho neu dang bi khoa, 0 neu duoc thu."""
        with self._lock:
            recent = [t for t in self._fails.get(key, []) if self._now() - t < self.window]
            self._fails[key] = recent
            if len(recent) >= self.max_fail:
                return max(0, int(self.lock - (self._now() - recent[-1])))
            return 0

    def record_fail(self, key):
        with self._lock:
            self._fails.setdefault(key, []).append(self._now())

    def reset(self, key):
        with self._lock:
            self._fails.pop(key, None)


def bootstrap_admin(store: UserStore, log=print):
    """Chua co tai khoan nao -> tao admin (tu env hoac sinh mat khau ngau nhien).

    Tra ve dict {username, password} neu mat khau duoc SINH (de nhac nguoi van
    hanh doi), nguoc lai None.
    """
    if len(store):
        return None
    user = os.environ.get("MKV_ADMIN_USER", "admin")
    pw = os.environ.get("MKV_ADMIN_PASS")
    generated = not pw
    if generated:
        pw = secrets.token_urlsafe(12)
    store.add(user, pw, role="admin")
    if generated:
        log(f"[auth] Da tao admin '{user}' voi mat khau ngau nhien: {pw}")
        log("[auth] Hay dang nhap va doi mat khau ngay.")
        return {"username": user, "password": pw}
    log(f"[auth] Da tao admin '{user}' tu MKV_ADMIN_PASS.")
    return None
