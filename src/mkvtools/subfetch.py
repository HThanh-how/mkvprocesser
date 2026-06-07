"""Tu tim & tai phu de (uu tien vi + en) cho phim KHONG co sub nhung, qua
OpenSubtitles.com REST API (dung urllib stdlib -> khong them dependency).

Can: API key + tai khoan (username/password) tu opensubtitles.com (free).
Cac ham osdb_hash / pick_best / norm_langs la thuan -> de test; phan goi mang
gate bang creds.
"""
import json
import os
import struct
import urllib.parse
import urllib.request

API = "https://api.opensubtitles.com/api/v1"
UA = "mkvtools/3.0"
# alias -> ma 2 ky tu OpenSubtitles dung trong tham so languages
_LANG = {"vi": "vi", "vie": "vi", "vietnamese": "vi",
         "en": "en", "eng": "en", "english": "en"}


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
