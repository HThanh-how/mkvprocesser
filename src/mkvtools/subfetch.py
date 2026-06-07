"""Tu tim & tai phu de (uu tien vi + en) cho phim KHONG co sub nhung, qua nhieu nguon:
- SubDL (subdl.com): hau due Subscene, manh sub VI + phim doi moi, version-matching. Can API key (free).
- OpenSubtitles.com: kho sau (phim cu/hiem), bu phan SubDL thieu. Can API key + tai khoan (free).

Dung urllib stdlib -> khong them dependency. `fetch_subs` gop ca 2 nguon (SubDL truoc).
Cac ham osdb_hash / pick_best / norm_langs / _subdl_pick / _subdl_extract_zip la thuan ->
de test; phan goi mang gate bang creds (rong = bo qua nguon do).
"""
import io
import json
import os
import struct
import urllib.parse
import urllib.request
import zipfile

API = "https://api.opensubtitles.com/api/v1"
UA = "mkvtools/3.0"
# alias -> ma 2 ky tu OpenSubtitles dung trong tham so languages
_LANG = {"vi": "vi", "vie": "vi", "vietnamese": "vi",
         "en": "en", "eng": "en", "english": "en"}

# --- SubDL (subdl.com): hau due Subscene, manh sub VI + phim doi moi, co API ---
SUBDL_API = "https://api.subdl.com/api/v1/subtitles"
SUBDL_DL = "https://dl.subdl.com"
_SUBDL_LANG = {"vi": "VI", "en": "EN"}   # alias da chuan hoa -> ma ngon ngu SubDL


def norm_langs(langs):
    """Chuan hoa danh sach ngon ngu -> ma 2 ky tu OpenSubtitles (giu thu tu, bo trung)."""
    out = []
    for c in langs:
        code = _LANG.get(str(c).strip().lower())
        if code and code not in out:
            out.append(code)
    return out


def osdb_hash(path):
    """Hash OpenSubtitles (filesize + 64KB dau + 64KB cuoi). None neu file < 128KB."""
    fmt, size = "<q", struct.calcsize("<q")
    filesize = os.path.getsize(path)
    if filesize < 65536 * 2:
        return None
    h = filesize
    with open(path, "rb") as f:
        for _ in range(65536 // size):
            h = (h + struct.unpack(fmt, f.read(size))[0]) & 0xFFFFFFFFFFFFFFFF
        f.seek(max(0, filesize - 65536), 0)
        for _ in range(65536 // size):
            h = (h + struct.unpack(fmt, f.read(size))[0]) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def pick_best(results):
    """Chon ban sub tot nhat (nhieu luot tai nhat, uu tien khop moviehash)."""
    best = None
    for r in results or []:
        a = r.get("attributes", {}) or {}
        files = a.get("files") or []
        if not files:
            continue
        score = (1 if a.get("moviehash_match") else 0, a.get("download_count", 0) or 0)
        if best is None or score > best[0]:
            best = (score, files[0].get("file_id"))
    return best[1] if best else None


def _post(url, body, headers):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:  # noqa: S310
        return json.loads(r.read())


def _get(url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as r:  # noqa: S310
        return json.loads(r.read())


def find_subs(video_path, dest_dir, langs=("vi", "en"), api_key="", username="", password="",
              log=print):
    """Tim + tai sub cho video. Tra ve list (srt_path, lang2). Rong neu thieu creds/khong thay."""
    langs = norm_langs(langs)
    if not (api_key and username and password) or not langs:
        log("  (sub) thieu OpenSubtitles key/tai khoan hoac ngon ngu -> bo qua tu-tim-sub")
        return []
    base = {"Api-Key": api_key, "User-Agent": UA}
    try:
        token = _post(f"{API}/login", {"username": username, "password": password}, base).get("token")
    except Exception as e:        # noqa: BLE001
        log(f"  (sub) dang nhap OpenSubtitles loi: {e}")
        return []
    auth = {**base, "Authorization": f"Bearer {token}"}
    name = os.path.splitext(os.path.basename(video_path))[0]
    mh = osdb_hash(video_path)
    out = []
    os.makedirs(dest_dir, exist_ok=True)
    for lg in langs:
        try:
            q = f"{API}/subtitles?languages={lg}&query={urllib.parse.quote(name)}"
            if mh:
                q += f"&moviehash={mh}"
            fid = pick_best(_get(q, base).get("data"))
            if not fid:
                log(f"  (sub) khong thay sub {lg}")
                continue
            link = _post(f"{API}/download", {"file_id": fid}, auth).get("link")
            srt = os.path.join(dest_dir, f"{name}.{lg}.srt")
            with urllib.request.urlopen(urllib.request.Request(link, headers=base)) as r, \
                    open(srt, "wb") as f:  # noqa: S310
                f.write(r.read())
            out.append((srt, lg))
            log(f"  (sub) da tai {lg}: {os.path.basename(srt)}")
        except Exception as e:        # noqa: BLE001
            log(f"  (sub) loi tai sub {lg}: {e}")
    return out


def _subdl_pick(subs):
    """Chon 1 ban sub SubDL: uu tien phim le (khong phai full_season), lay cai dau co url."""
    for s in subs or []:
        if not s.get("full_season") and s.get("url"):
            return s["url"]
    for s in subs or []:
        if s.get("url"):
            return s["url"]
    return None


def _subdl_extract_zip(blob, srt_path):
    """Giai nen zip SubDL (bytes), ghi file phu de dau tien (.srt uu tien) ra srt_path."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        srts = [n for n in names if n.lower().endswith(".srt")]
        pick = srts[0] if srts else next(
            (n for n in names if n.lower().endswith((".ass", ".ssa", ".sub", ".vtt"))), None)
        if not pick:
            return False
        with z.open(pick) as src, open(srt_path, "wb") as f:
            f.write(src.read())
    return True


def subdl_find(video_path, dest_dir, langs=("vi", "en"), api_key="", log=print):
    """Tim + tai sub qua SubDL (zip -> srt). Tra ve list (srt_path, lang). [] neu thieu key."""
    langs = norm_langs(langs)
    if not api_key or not langs:
        return []
    name = os.path.splitext(os.path.basename(video_path))[0]
    out = []
    os.makedirs(dest_dir, exist_ok=True)
    for lg in langs:
        code = _SUBDL_LANG.get(lg)
        if not code:
            continue
        try:
            q = (f"{SUBDL_API}?api_key={urllib.parse.quote(api_key)}&languages={code}"
                 f"&type=movie&subs_per_page=30&film_name={urllib.parse.quote(name)}")
            url = _subdl_pick(_get(q, {"User-Agent": UA}).get("subtitles"))
            if not url:
                log(f"  (subdl) khong thay sub {lg}")
                continue
            with urllib.request.urlopen(                       # noqa: S310
                    urllib.request.Request(SUBDL_DL + url, headers={"User-Agent": UA})) as r:
                blob = r.read()
            srt = os.path.join(dest_dir, f"{name}.{lg}.srt")
            if _subdl_extract_zip(blob, srt):
                out.append((srt, lg))
                log(f"  (subdl) da tai {lg}: {os.path.basename(srt)}")
            else:
                log(f"  (subdl) zip {lg} khong co file sub")
        except Exception as e:        # noqa: BLE001
            log(f"  (subdl) loi {lg}: {e}")
    return out


def fetch_subs(video_path, dest_dir, langs=("vi", "en"), *, subdl_api_key="",
               os_api_key="", os_user="", os_pass="", log=print):
    """Tu tim sub nhieu nguon: SubDL truoc (manh VI + phim moi) roi OpenSubtitles bu phan
    con thieu. Tra ve list (srt_path, lang) theo dung thu tu langs (vi truoc en)."""
    want = norm_langs(langs)
    found = {}
    if subdl_api_key:
        for srt, lg in subdl_find(video_path, dest_dir, want, subdl_api_key, log):
            found.setdefault(lg, srt)
    missing = [lg for lg in want if lg not in found]
    if missing and os_api_key and os_user and os_pass:
        for srt, lg in find_subs(video_path, dest_dir, missing, os_api_key, os_user, os_pass, log):
            found.setdefault(lg, srt)
    if not found:
        log("  (sub) khong tim duoc sub (SubDL/OpenSubtitles) hoac thieu key")
    return [(found[lg], lg) for lg in want if lg in found]
