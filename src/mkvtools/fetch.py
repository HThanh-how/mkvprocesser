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
            # Clip ĐANG HIEN THI: src cua the <video> dau tien (DOM order) = clip nguoi
            # dung thay, tranh nham voi clip goi-y trang prefetch. Bo qua blob: (MSE/HLS).
            try:
                el = page.query_selector("video")
                primary = page.evaluate("e => e.currentSrc || e.src", el) if el else ""
            except Exception:            # noqa: BLE001
                primary = ""
            if primary and primary.startswith("http"):
                hit = found.get(primary)
                if hit:
                    hit["primary"] = True
                else:
                    found[primary] = {"url": primary, "type": "video/mp4",
                                      "referer": ref["url"], "primary": True}
        except Exception as e:           # noqa: BLE001
            log(f"  (sniff) {e}")
        finally:
            browser.close()
    return list(found.values())


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
