"""Tai file tu link theo 4 tang "bat link thong minh" (uu tien bat duoc nhieu nhat).

  T1. URL tro THANG toi file (.mkv/.mp4...)            -> tai HTTP streaming.
  T2. yt-dlp: YouTube + 1800+ trang stream/file-host + Google Drive + tu quet
      trang generic tim m3u8/mp4. Ho tro cookie + referer.                (extra [fetch])
  T3. Trinh duyet an (Playwright) "nghe len" network -> bat URL media that
      su (.m3u8/.mp4...) tu player JS/obfuscate, roi giao lai yt-dlp/HTTP.  (extra [browser])
  T4. resolve(): chay cac tang o che do CHI DO (khong tai) -> bao bat duoc gi.

Cookie: truyen file cookies.txt (dinh dang Netscape) cho trang can dang nhap.
Gioi han that su: CAPTCHA / DRM -> khong tool nao qua duoc.

Cac ham doan URL / xep hang media / doc cookie la thuan (pure) -> de test.
"""
import os
import re
import urllib.parse
import urllib.request

VIDEO_EXTS = (".mkv", ".mp4", ".ts", ".mov", ".webm", ".avi", ".m4v", ".flv", ".wmv", ".m2ts")
MANIFEST_EXTS = (".m3u8", ".mpd")
MEDIA_EXTS = VIDEO_EXTS + MANIFEST_EXTS
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

# Nut "play"/"download" hay gap -> bam de kich hoat player tai media (T3).
PLAY_SELECTORS = (
    "button[aria-label*='play' i]", ".vjs-big-play-button", ".jw-icon-display",
    ".plyr__control--overlaid", ".html5-main-video", "video",
    "button:has-text('Download')", "a:has-text('Download')", "a:has-text('Tai')",
)


# ----------------------------------------------------------------- pure helpers
def guess_name(url: str) -> str:
    """Doan ten file tu phan duoi cua URL. Tra '' neu khong ro (vd watch?v=...)."""
    name = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))
    return name if (name and "." in name) else ""


def is_direct_media(url: str) -> bool:
    """URL tro THANG toi 1 file video (theo duoi mo rong, bo qua manifest)?"""
    return urllib.parse.urlparse(url).path.lower().endswith(VIDEO_EXTS)


def is_torrent(url: str) -> bool:
    """Magnet hoac link .torrent?"""
    u = (url or "").strip().lower()
    return u.startswith("magnet:") or u.split("?")[0].endswith(".torrent")


def _all_videos(d: str) -> list:
    out = []
    for root, _, files in os.walk(d):
        for f in files:
            if f.lower().endswith(VIDEO_EXTS):
                out.append(os.path.join(root, f))
    return out


def is_media_url(url: str, content_type: str = "") -> bool:
    """URL nay la media (file video / manifest HLS-DASH) theo duoi hoac content-type?"""
    if urllib.parse.urlparse(url).path.lower().endswith(MEDIA_EXTS):
        return True
    ct = (content_type or "").lower()
    return ct.startswith("video/") or "mpegurl" in ct or "dash+xml" in ct


_MEDIA_RANK = {".m3u8": 5, ".mpd": 5, ".mkv": 4, ".mp4": 4, ".m4v": 3, ".webm": 3,
               ".mov": 3, ".ts": 1}


def rank_media(cands: list):
    """Chon ung vien media tot nhat. Uu tien clip ĐANG HIEN THI (primary, lay tu the
    <video> chinh) -> tranh tai nham clip khac/goi-y ma trang prefetch. Sau do:
    manifest (m3u8/mpd) > mp4/mkv > ts. None neu rong."""
    def score(c):
        path = urllib.parse.urlparse(c.get("url", "")).path.lower()
        ext = next((e for e in MEDIA_EXTS if path.endswith(e)), "")
        return (1000 if c.get("primary") else 0) + _MEDIA_RANK.get(ext, 0)
    return sorted(cands, key=score, reverse=True)[0] if cands else None


def safe_name(name: str) -> str:
    """Bo ky tu cam tren ten file (Windows + POSIX)."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "download"


def media_signature(data: bytes) -> str:
    """Nhan dang nhanh media tu magic bytes, khong tin moi Content-Type cua CDN."""
    head = bytes(data or b"")[:64]
    stripped = head.lstrip()
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if head.startswith(b"FLV"):
        return "flv"
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return "avi"
    if head.startswith(b"G"):
        return "mpegts"
    if stripped.startswith(b"#EXTM3U"):
        return "hls"
    if stripped.startswith((b"<MPD", b"<?xml")) and b"MPD" in head:
        return "dash"
    if stripped.upper().startswith((b"WEBVTT", b"<!DOCTYPE", b"<HTML", b"{")):
        return "text"
    return ""


def verify_media_candidate(candidate: dict, timeout: int = 12) -> tuple[bool, str]:
    """Doc 64 byte dau de loai subtitle/HTML gia video truoc khi hien cho nguoi dung."""
    url = candidate.get("url") or ""
    headers = {"User-Agent": UA, "Range": "bytes=0-63"}
    if candidate.get("referer"):
        headers["Referer"] = candidate["referer"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=timeout) as response:  # noqa: S310
            head = response.read(64)
            ctype = (response.headers.get("Content-Type") or "").lower()
            content_range = response.headers.get("Content-Range") or ""
            match = re.search(r"/(\d+)$", content_range)
            total = int(match.group(1)) if match else int(response.headers.get("Content-Length") or 0)
    except Exception as exc:  # noqa: BLE001 - candidate het han/bi CDN chan thi bo qua
        return False, f"HTTP: {exc}"

    kind = media_signature(head)
    if kind == "text" or ctype.startswith(("text/", "application/json")):
        return False, f"noi dung {kind or ctype}"
    if total and total < 4096 and kind not in ("hls", "dash"):
        return False, f"file qua nho ({total} byte)"
    if kind:
        return True, kind
    return False, "khong nhan ra dinh dang video"


def valid_video_file(path: str) -> bool:
    """Chi chap nhan file co video stream that; chan VTT/HTML bi dat nham duoi .mp4."""
    import shutil
    import subprocess

    try:
        if os.path.getsize(path) < 4096:
            return False
        with open(path, "rb") as stream:
            if media_signature(stream.read(64)) == "text":
                return False
    except OSError:
        return False

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        with open(path, "rb") as stream:
            return media_signature(stream.read(64)) not in ("", "text")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "video" in result.stdout.splitlines()


def load_cookies_txt(path: str) -> list:
    """Doc cookies.txt (Netscape) -> list dict cho Playwright. Bo dong rong/comment."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, cpath, secure, expiry, name, value = parts[:7]
            ck = {"name": name, "value": value, "domain": domain, "path": cpath or "/",
                  "secure": secure.strip().upper() == "TRUE"}
            try:
                if int(expiry) > 0:
                    ck["expires"] = int(expiry)
            except ValueError:
                pass
            out.append(ck)
    return out


# ----------------------------------------------------------------- T1: HTTP truc tiep
def http_download(url: str, dest_dir: str, log=print, chunk: int = 1 << 20,
                  referer: str = None) -> str:
    """Tai file truc tiep qua HTTP. Dung aria2c (da luong + resume) neu co; nguoc lai urllib."""
    import shutil
    os.makedirs(dest_dir, exist_ok=True)
    name = safe_name(guess_name(url) or "download.bin")
    dest = os.path.join(dest_dir, name)
    if shutil.which("aria2c"):
        import subprocess
        cmd = ["aria2c", f"--dir={dest_dir}", "-o", name, "-x16", "-s16",
               "--continue=true", "--auto-file-renaming=false", "--max-tries=5",
               "--retry-wait=5", "--summary-interval=20", "--console-log-level=warn",
               f"--user-agent={UA}"]
        if referer:
            cmd.append(f"--referer={referer}")
        cmd.append(url)
        log("  aria2c: tai HTTP (da luong + resume)...")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log("  " + line)
        if proc.wait() == 0 and os.path.exists(dest):
            log(f"  tai xong -> {name}")
            return dest
        log("  (!) aria2 loi -> chuyen urllib")
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
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


# ----------------------------------------------------------------- T0: torrent/magnet
def torrent_download(url: str, dest_dir: str, log=print, upload_limit="1K", seed_time=0) -> str:
    """Keo torrent/magnet bang aria2c, LEECH-ONLY (tai xong KHONG seed/share).

    Tra ve file video LON NHAT trong noi dung tai ve (bo qua sample/nfo).
    """
    import shutil
    import subprocess
    if not shutil.which("aria2c"):
        raise RuntimeError("Chua cai aria2 (apt install aria2) de keo torrent")
    os.makedirs(dest_dir, exist_ok=True)
    before = set(_all_videos(dest_dir))
    cmd = [
        "aria2c", f"--dir={dest_dir}",
        f"--seed-time={seed_time}",                  # 0 = tai xong KHONG seed (khong share)
        f"--max-overall-upload-limit={upload_limit}",
        "--bt-stop-timeout=600", "--bt-max-peers=80",
        "--summary-interval=20", "--console-log-level=warn", url,
    ]
    log("  aria2c: keo torrent (leech-only, khong share)...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:                          # day tien do aria2 ra log GUI
        line = line.rstrip()
        if line:
            log("  " + line)
    proc.wait()
    new = [f for f in _all_videos(dest_dir) if f not in before] or _all_videos(dest_dir)
    if not new:
        raise RuntimeError("Torrent xong nhung khong tim thay file video.")
    best = max(new, key=lambda f: os.path.getsize(f))
    log(f"  torrent xong -> {os.path.basename(best)} ({os.path.getsize(best) / 1e9:.2f} GB)")
    return best


# ----------------------------------------------------------------- T2: yt-dlp
def _ydl_progress(log):
    def hook(d):
        if d.get("status") == "downloading":
            pct = (d.get("_percent_str") or "").strip()
            spd = (d.get("_speed_str") or "").strip()
            if pct:
                log(f"  {pct} {spd}")
    return hook


def ytdlp_download(url: str, dest_dir: str, log=print, cookies: str = None,
                   referer: str = None) -> str:
    """Tai qua yt-dlp (YouTube/stream/file-host/HLS). Tra ve duong dan file da tai."""
    import yt_dlp  # extra [fetch]

    os.makedirs(dest_dir, exist_ok=True)
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    opts = {
        "outtmpl": os.path.join(dest_dir, "%(title).200B.%(ext)s"),
        "merge_output_format": "mkv",
        "quiet": True, "no_warnings": True, "noprogress": True,
        "progress_hooks": [_ydl_progress(log)],
        "restrictfilenames": True,
        "retries": 10, "fragment_retries": 10,
        "http_headers": headers,
    }
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        rd = (info.get("requested_downloads") or [{}])[0]
        return rd.get("filepath") or ydl.prepare_filename(info)


def ytdlp_probe(url: str, cookies: str = None):
    """Hoi yt-dlp xem co rut duoc media khong (KHONG tai). Tra info dict hoac None."""
    import yt_dlp  # extra [fetch]

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except Exception:        # noqa: BLE001 - trang khong duoc ho tro -> de tang sau lo
            return None


# ----------------------------------------------------------------- T3: trinh duyet sniff
def browser_sniff(url: str, log=print, cookies: str = None, wait: int = 8,
                  timeout: int = 60) -> list:
    """Mo trang bang Chromium an, "nghe len" network -> list URL media bat duoc."""
    from playwright.sync_api import sync_playwright  # extra [browser]

    found = {}
    ref = {"url": url}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, ignore_https_errors=True)
        if cookies and os.path.exists(cookies):
            try:
                ctx.add_cookies(load_cookies_txt(cookies))
            except Exception as e:       # noqa: BLE001
                log(f"  (sniff) cookie loi: {e}")
        page = ctx.new_page()

        def on_resp(resp):
            try:
                u, ct = resp.url, resp.headers.get("content-type", "")
            except Exception:            # noqa: BLE001
                return
            if u not in found and is_media_url(u, ct):
                found[u] = {"url": u, "type": ct, "referer": ref["url"]}

        page.on("response", on_resp)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            ref["url"] = page.url
            for sel in PLAY_SELECTORS:           # thu kich hoat player
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click(timeout=1500)
                except Exception:        # noqa: BLE001
                    pass
            page.wait_for_timeout(wait * 1000)   # cho media request bay ra
            # The <video> trong DOM: lay src + kich thuoc + poster de NGUOI DUNG nhin thay
            # va chon clip dung. Video DAU TIEN (DOM order) = clip dang hien thi -> primary.
            # Bo qua blob: (MSE/HLS khong tai truc tiep duoc).
            try:
                vids = page.eval_on_selector_all(
                    "video",
                    "els => els.map(e => ({src: e.currentSrc || e.src, "
                    "w: e.videoWidth, h: e.videoHeight, poster: e.poster}))")
            except Exception:            # noqa: BLE001
                vids = []
            for i, v in enumerate(vids):
                u = v.get("src") or ""
                if not u.startswith("http"):
                    continue
                rec = found.get(u) or {"url": u, "type": "video/mp4", "referer": ref["url"]}
                rec["width"] = v.get("w") or rec.get("width") or 0
                rec["height"] = v.get("h") or rec.get("height") or 0
                rec["dom_video"] = True
                if v.get("poster"):
                    rec["poster"] = v["poster"]
                if i == 0:                # clip dang hien thi
                    rec["primary"] = True
                found[u] = rec
        except Exception as e:           # noqa: BLE001
            log(f"  (sniff) {e}")
        finally:
            browser.close()
    return list(found.values())


def list_video_candidates(url: str, log=print, cookies: str = None) -> list:
    """Liet ke MOI clip bat duoc tu trang (cho UI hien ra de nguoi dung chon).

    Tra ve list dict: {url, width, height, poster, primary, referer}. Clip dang hien
    thi (primary) + do phan giai cao len truoc. Rong neu khong bat duoc / chua co Playwright.
    """
    try:
        cands = browser_sniff(url, log=log, cookies=cookies)
    except ImportError:
        log("  (!) chua cai Playwright -> khong liet ke duoc")
        return []
    out, seen = [], set()
    for c in cands:
        u = c.get("url", "")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append({"url": u, "width": c.get("width") or 0, "height": c.get("height") or 0,
                    "poster": c.get("poster") or "", "primary": bool(c.get("primary")),
                    "referer": c.get("referer") or url,
                    "_dom_video": bool(c.get("dom_video"))})
    out.sort(key=lambda c: (c["primary"], c["width"] * c["height"]), reverse=True)
    verified = []
    for candidate in out:
        ok, reason = verify_media_candidate(candidate)
        if ok:
            verified.append(candidate)
        else:
            log(f"  (bo qua) candidate khong phai video: {reason}")
    # Threads/Instagram thuong prefetch video lien quan va nhieu ban CDN cua cung clip.
    # Giu TOAN BO video that trong DOM (ke ca bai carousel nhieu video), chi bo cac
    # request media tai nen khong gan voi video cua bai. Neu DOM khong lo media (mot
    # so TikTok), fallback ve candidate network da xac minh.
    dom_verified = [candidate for candidate in verified if candidate.get("_dom_video")]
    selected = dom_verified or verified
    for candidate in selected:
        candidate.pop("_dom_video", None)
    return selected


def download_media_url(url: str, dest_dir: str, log=print, referer: str = None,
                       cookies: str = None) -> str:
    """Tai 1 URL media DA CHON (truc tiep, vd tu list_video_candidates). file -> HTTP;
    khac -> yt-dlp. Dung khi nguoi dung bam tai 1 clip cu the tren UI."""
    return _download_resolved({"url": url, "referer": referer}, dest_dir, log, cookies)


# ----------------------------------------------------------------- dieu phoi
def _download_resolved(media: dict, dest_dir: str, log, cookies: str):
    """Tai 1 URL media da sniff: file truc tiep -> HTTP; manifest/khac -> yt-dlp."""
    u, ref = media["url"], media.get("referer")
    if is_direct_media(u):
        try:
            return http_download(u, dest_dir, log=log, referer=ref)
        except Exception as e:           # noqa: BLE001 - CDN chan? thu yt-dlp
            log(f"  (sniff) HTTP that bai ({e}) -> yt-dlp")
    return ytdlp_download(u, dest_dir, log=log, cookies=cookies, referer=ref)


def fetch(url: str, dest_dir: str, log=print, cookies: str = None, referer: str = None) -> str:
    """Tu chon cach tai theo 4 tang (xem docstring module). Tra ve duong dan file."""
    url = (url or "").strip()
    if is_torrent(url):                                      # T0: torrent/magnet (leech-only)
        return torrent_download(url, dest_dir, log=log)
    if is_direct_media(url):                                  # T1
        return http_download(url, dest_dir, log=log, referer=referer)
    try:                                                     # T2: yt-dlp
        return ytdlp_download(url, dest_dir, log=log, cookies=cookies, referer=referer)
    except ImportError:
        log("  (!) chua cai yt-dlp (pip install 'mkvtools[fetch]')")
    except Exception as e:               # noqa: BLE001
        log(f"  (!) yt-dlp khong tai duoc: {e} -> thu trinh duyet an")
    try:                                                     # T3: trinh duyet sniff
        cands = browser_sniff(url, log=log, cookies=cookies)
    except ImportError:
        log("  (!) chua cai Playwright (pip install 'mkvtools[browser]' && playwright install chromium)")
        cands = []
    best = rank_media(cands)
    if best:
        log(f"  (sniff) bat duoc media -> {best['url'][:90]}")
        return _download_resolved(best, dest_dir, log, cookies)
    raise RuntimeError("Khong bat duoc media tu link (co the player JS chan, CAPTCHA, hoac DRM).")


def resolve(url: str, log=print, cookies: str = None) -> dict:
    """Che do CHI DO: bao bat duoc gi tu link (khong tai). Dung cho lenh `resolve`."""
    url = (url or "").strip()
    if is_torrent(url):                                      # T0
        return {"ok": True, "tier": "torrent", "media": url, "kind": "torrent"}
    if is_direct_media(url):                                  # T1
        return {"ok": True, "tier": "direct", "media": url, "kind": "file"}
    try:                                                     # T2
        info = ytdlp_probe(url, cookies=cookies)
    except ImportError:
        info = None
    if info:
        return {"ok": True, "tier": "yt-dlp", "title": info.get("title"),
                "ext": info.get("ext"), "media": info.get("url") or info.get("webpage_url"),
                "kind": "ytdlp"}
    try:                                                     # T3
        cands = browser_sniff(url, log=log, cookies=cookies)
    except ImportError:
        cands = []
    best = rank_media(cands)
    if best:
        return {"ok": True, "tier": "browser", "media": best["url"],
                "candidates": [c["url"] for c in cands], "kind": "sniff"}
    return {"ok": False, "tier": None, "media": None}
