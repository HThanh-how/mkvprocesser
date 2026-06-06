"""
Tim & goi ffmpeg/ffprobe. Uu tien binary bundle (cho ban dong goi),
fallback ve PATH. An cua so CMD tren Windows. (Port tu repo cu, rut gon.)
"""
import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_FLAGS = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
_EXE = ".exe" if platform.system() == "Windows" else ""


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def _find(name: str) -> Optional[str]:
    bd = _bundle_dir()
    for cand in (bd / "ffmpeg_bin" / f"{name}{_EXE}", bd / f"{name}{_EXE}"):
        if cand.exists():
            return str(cand.absolute())
    try:
        subprocess.run([name, "-version"], capture_output=True, check=True,
                       timeout=5, creationflags=_FLAGS)
        return name
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def find_ffmpeg() -> Optional[str]:
    return _find("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return _find("ffprobe")


def available() -> bool:
    return find_ffmpeg() is not None and find_ffprobe() is not None


def probe(path: str) -> dict:
    """Thay cho ffmpeg.probe(): khong hien CMD, co timeout + loi ro rang."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    fp = find_ffprobe()
    if not fp:
        raise RuntimeError("Khong tim thay ffprobe (bundle hoac PATH).")
    cmd = [fp, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=_FLAGS)
    if r.returncode != 0:
        raise RuntimeError("ffprobe loi: " + r.stderr.decode("utf-8", "replace").strip())
    return json.loads(r.stdout.decode("utf-8"))


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Chay 1 lenh, tu thay 'ffmpeg'/'ffprobe' bang path that."""
    ff, fp = find_ffmpeg() or "ffmpeg", find_ffprobe() or "ffprobe"
    cmd = [ff if a == "ffmpeg" else fp if a == "ffprobe" else a for a in cmd]
    return subprocess.run(cmd, creationflags=_FLAGS, **kw)
