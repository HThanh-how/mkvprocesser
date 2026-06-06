"""Tien ich tai nguyen (da nen tang): dia trong, RAM, chon thu muc lam viec.

shutil.disk_usage chay tren Windows/macOS/Linux. psutil la tuy chon (extra
[desktop]); neu thieu thi available_ram_gb() tra ve None thay vi nem loi.

Port y tuong tu app cu (system_utils + chien luoc SSD-cache trong processing_core),
nhung khong cung nhac vao /dev/shm hay Windows.
"""
from __future__ import annotations

import os
import shutil


def free_gb(path: str = ".") -> float:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return 0.0


def file_size_gb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 ** 3)
    except OSError:
        return 0.0


def enough_space(path: str, need_gb: float) -> bool:
    return free_gb(path) >= need_gb


def available_ram_gb() -> float | None:
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        return None  # psutil khong cai -> khong biet, khong sao


def pick_work_dir(primary: str, fallback: str, need_gb: float) -> str:
    """Chon `primary` (vd SSD cache) neu du cho, nguoc lai dung `fallback`."""
    if primary and enough_space(primary, need_gb):
        return primary
    return fallback


def preflight(src: str, work_dir: str, factor: float = 1.5) -> tuple[bool, str]:
    """Kiem tra du dia truoc khi tach. Tra (ok, message); khong nem loi."""
    need = file_size_gb(src) * factor
    have = free_gb(work_dir or ".")
    if have < need:
        return False, f"Thieu dia: can ~{need:.1f}GB tai {work_dir or '.'}, con {have:.1f}GB"
    return True, ""
