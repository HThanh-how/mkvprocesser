"""Tai file ve tu link.

- Link file truc tiep (.mkv/.mp4/...) -> tai HTTP streaming (ghi thang ra dia,
  khong gom vao RAM -> hop o nho).
- Con lai (YouTube, trang stream, file-host kieu "phai bam nut") -> yt-dlp (extra
  [fetch], lazy import). yt-dlp tu phan tich trang va tim link media that su, nen
  nhung link "bam bam moi tai" thuong van bat duoc.

Cac ham doan ten/loai URL la thuan (pure) -> de test khong can mang.
"""
import os
import re
import urllib.parse
import urllib.request

VIDEO_EXTS = (".mkv", ".mp4", ".ts", ".mov", ".webm", ".avi", ".m4v", ".flv", ".wmv", ".m2ts")


def guess_name(url: str) -> str:
    """Doan ten file tu phan duoi cua URL. Tra '' neu khong ro (vd watch?v=...)."""
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(urllib.parse.unquote(path))
    return name if (name and "." in name) else ""


def is_direct_media(url: str) -> bool:
    """URL tro THANG toi 1 file video (theo duoi mo rong)?"""
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith(VIDEO_EXTS)


def safe_name(name: str) -> str:
    """Bo ky tu cam tren ten file (Windows + POSIX)."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "download"


def http_download(url: str, dest_dir: str, log=print, chunk: int = 1 << 20) -> str:
    """Tai file truc tiep qua HTTP, ghi streaming ra dia. Tra ve duong dan file."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, safe_name(guess_name(url) or "download.bin"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:  # noqa: S310
        total = int(r.headers.get("Content-Length") or 0)
        got = step = 0
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)
            got += len(b)
            if total and got - step >= (1 << 28):       # log moi ~256MB
                step = got
                log(f"  tai {got / 1e9:.2f}/{total / 1e9:.2f} GB ({got * 100 // total}%)")
    log(f"  tai xong {got / 1e9:.2f} GB -> {os.path.basename(dest)}")
    return dest


def ytdlp_download(url: str, dest_dir: str, log=print) -> str:
    """Tai qua yt-dlp (YouTube/stream/file-host). Tra ve duong dan file da tai."""
    import yt_dlp  # extra [fetch]

    os.makedirs(dest_dir, exist_ok=True)
    last = {}

    def hook(d):
        if d.get("status") == "downloading":
            pct = (d.get("_percent_str") or "").strip()
            spd = (d.get("_speed_str") or "").strip()
            if pct:
                log(f"  {pct} {spd}")
        elif d.get("status") == "finished":
            last["path"] = d.get("filename")

    opts = {
        "outtmpl": os.path.join(dest_dir, "%(title).200B.%(ext)s"),
        "merge_output_format": "mkv",
        "quiet": True, "no_warnings": True, "noprogress": True,
        "progress_hooks": [hook],
        "restrictfilenames": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        rd = (info.get("requested_downloads") or [{}])[0]
        path = rd.get("filepath") or last.get("path") or ydl.prepare_filename(info)
    return path


def fetch(url: str, dest_dir: str, log=print) -> str:
    """Tu chon cach tai: file truc tiep -> HTTP; con lai -> yt-dlp (fallback HTTP)."""
    url = (url or "").strip()
    if is_direct_media(url):
        return http_download(url, dest_dir, log=log)
    try:
        return ytdlp_download(url, dest_dir, log=log)
    except ImportError:
        log("  (!) chua cai yt-dlp (pip install 'mkvtools[fetch]') -> thu tai HTTP truc tiep")
        return http_download(url, dest_dir, log=log)
