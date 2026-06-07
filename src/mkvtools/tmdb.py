"""Tim phim tren TMDB -> tai poster/backdrop -> ghep thumbnail YouTube 1280x720.

Dung urllib stdlib (khong them dependency). Ghep anh bang ffmpeg (nen mo + anh giua)
de poster doc (2:3) thanh thumbnail 16:9 dep. Gate bang tmdb_api_key (free).
"""
import json
import os
import urllib.parse
import urllib.request

from . import ffmpeg_helper

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
UA = "mkvtools/3.0"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:  # noqa: S310
        return json.loads(r.read())


def image_url(path, size="w780"):
    """URL anh TMDB tu poster_path/backdrop_path. None neu path rong."""
    return f"{IMG}/{size}{path}" if path else None


def search_movie(title, year="", api_key=""):
    """Tra ve phim dau tien khop (dict: id, title, poster_path, backdrop_path) hoac None."""
    if not (title and api_key):
        return None
    q = f"{API}/search/movie?api_key={urllib.parse.quote(api_key)}&query={urllib.parse.quote(title)}"
    if year:
        q += f"&year={year}"
    try:
        results = _get(q).get("results") or []
    except Exception:        # noqa: BLE001
        return None
    return results[0] if results else None


def fetch_image(title, year, api_key, dest_path, prefer="poster", log=print):
    """Tim phim + tai anh (poster hoac backdrop) ve dest_path. Tra dest_path hoac None."""
    m = search_movie(title, year, api_key)
    if not m:
        log(f"  (tmdb) khong thay phim: {title} ({year})")
        return None
    order = (["poster_path", "backdrop_path"] if prefer == "poster"
             else ["backdrop_path", "poster_path"])
    size = {"poster_path": "w780", "backdrop_path": "w1280"}
    for key in order:
        p = m.get(key)
        if not p:
            continue
        try:
            req = urllib.request.Request(image_url(p, size[key]), headers={"User-Agent": UA})
            with urllib.request.urlopen(req) as r, open(dest_path, "wb") as f:  # noqa: S310
                f.write(r.read())
            log(f"  (tmdb) tai {key.split('_')[0]} cho '{m.get('title', title)}'")
            return dest_path
        except Exception as e:        # noqa: BLE001
            log(f"  (tmdb) loi tai anh: {e}")
    log(f"  (tmdb) phim '{m.get('title', title)}' khong co anh")
    return None


# ffmpeg: nen = poster phong to + blur lap day 1280x720; tien canh = poster fit chieu cao, giua
_VF = ("[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,boxblur=24:6[bg];"
       "[0:v]scale=-2:720[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def make_thumbnail(title, year, api_key, work_dir, prefer="poster", log=print):
    """Tim phim TMDB -> tai anh -> ghep thumbnail 1280x720. Tra path anh (.jpg) hoac None."""
    if not (title and api_key):
        return None
    os.makedirs(work_dir, exist_ok=True)
    raw = os.path.join(work_dir, "_tmdb_raw.jpg")
    if not fetch_image(title, year, api_key, raw, prefer=prefer, log=log):
        return None
    thumb = os.path.join(work_dir, "_tmdb_thumb.jpg")
    try:
        r = ffmpeg_helper.run(["ffmpeg", "-y", "-i", raw, "-filter_complex", _VF,
                               "-frames:v", "1", thumb], capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.exists(thumb) and os.path.getsize(thumb) > 0:
            os.remove(raw)
            return thumb
        log("  (tmdb) ghep thumbnail loi -> dung anh goc")
    except Exception as e:        # noqa: BLE001
        log(f"  (tmdb) ffmpeg loi: {e} -> dung anh goc")
    return raw          # fallback: anh goc (YouTube van nhan, co the bi vien)
