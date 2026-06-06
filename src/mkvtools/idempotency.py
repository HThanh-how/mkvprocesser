"""Chong xu ly trung: nhan dien file bang chu ky noi dung + luu trang thai ben dia.

Thay cho tap 'seen' nam trong RAM cua watch loop (mat khi restart). Chu ky =
kich thuoc + sha256(dau 1MiB + cuoi 1MiB) -> nhanh voi video lon, van du chac
de phan biet file. Ghi trang thai atomic (tmp + os.replace) nen khong hong file
JSON neu bi ngat giua chung.

Port tu logic chu-ky + processed-log cua app cu (file_utils / log_manager),
nhung gon va co test.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

_CHUNK = 1 << 20  # 1 MiB doc o dau va cuoi file


def file_signature(path: str, chunk: int = _CHUNK) -> str:
    """Chu ky on dinh & re: size + sha256(dau chunk + cuoi chunk)."""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk:
            f.seek(max(size - chunk, 0))
            h.update(f.read(chunk))
    return h.hexdigest()


class ProcessedStore:
    """Tap chu ky da xu ly, ben dia (JSON). Tu nap khi khoi tao."""

    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, dict] = {}
        self._titles: set[str] = set()   # tap title_key da xu ly (tra cuu nhanh)
        self.load()

    def load(self) -> ProcessedStore:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._data = data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}  # thieu hoac hong -> coi nhu rong, khong nem loi
        self._titles = {info["title_key"] for info in self._data.values()
                        if isinstance(info, dict) and info.get("title_key")}
        return self

    def has(self, signature: str) -> bool:
        return signature in self._data

    def has_title(self, title_key: str) -> bool:
        """True neu da xu ly file co cung tua (chuan hoa + nam)."""
        return bool(title_key) and title_key in self._titles

    def add(self, signature: str, info: dict | None = None) -> None:
        info = info or {}
        self._data[signature] = info
        tk = info.get("title_key")
        if tk:
            self._titles.add(tk)
        self.save()

    def save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)  # atomic tren cung volume
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def __len__(self) -> int:
        return len(self._data)
