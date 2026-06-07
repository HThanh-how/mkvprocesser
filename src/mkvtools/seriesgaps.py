"""Doi chieu thu vien da upload voi TMDB collection -> liet ke phim THIEU trong series.

`mkvtools series-gaps`: doc tua video da upload tren YouTube, tach (nam, tua), tra TMDB
tim collection (series) cua tung phim, roi liet ke phan con thieu cua tung collection.
Logic thuan (inject `tget` de test); phan goi mang gate bang tmdb_api_key.
"""
import json
import re
import urllib.parse
import urllib.request

API = "https://api.themoviedb.org/3"
UA = "mkvtools/3.0"
# tua YouTube theo template {res}_{lang}_{year}_{title} (vd 4K_JPN_2024_Detective Conan Movie 27)
_TITLE_RX = re.compile(r"^(?:4K|2K|FHD|HD|SD)_[A-Z]{2,5}_((?:19|20)\d{2})_(.+)$")


def parse_title(raw):
    """Tach tua YouTube -> (year, title). Khong khop template -> (None, raw da strip)."""
    m = _TITLE_RX.match((raw or "").strip())
    if m:
        return m.group(1), m.group(2).strip()
    return None, (raw or "").strip()


def _tget(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:  # noqa: S310
        return json.loads(r.read())


def analyze(titles, tmdb_key, tget=_tget, log=print):
    """Tra ve (collections, unmatched).

    collections: list dict {id, name, total, have:[title], missing:[{title, year}]} —
    sap xep theo so phim thieu giam dan. unmatched: list tua khong tim thay tren TMDB.
    """
    k = urllib.parse.quote(tmdb_key)
    have_ids = set()
    cols = {}                 # collection_id -> name
    unmatched = []
    for raw in titles:
        year, title = parse_title(raw)
        if not title:
            continue
        try:
            q = f"{API}/search/movie?api_key={k}&query={urllib.parse.quote(title)}"
            if year:
                q += f"&year={year}"
            res = tget(q).get("results") or []
            if not res:
                unmatched.append(raw)
                continue
            mv = res[0]
            have_ids.add(mv["id"])
            col = tget(f"{API}/movie/{mv['id']}?api_key={k}").get("belongs_to_collection")
            if col:
                cols[col["id"]] = col["name"]
        except Exception as e:        # noqa: BLE001
            log(f"  (tmdb) loi '{title}': {e}")
            unmatched.append(raw)
    out = []
    for cid, cname in cols.items():
        try:
            parts = tget(f"{API}/collection/{cid}?api_key={k}").get("parts") or []
        except Exception as e:        # noqa: BLE001
            log(f"  (tmdb) loi collection {cid}: {e}")
            continue
        have = [p.get("title") for p in parts if p.get("id") in have_ids]
        missing = [{"title": p.get("title"), "year": (p.get("release_date") or "")[:4]}
                   for p in parts if p.get("id") not in have_ids]
        out.append({"id": cid, "name": cname, "total": len(parts),
                    "have": have, "missing": missing})
    out.sort(key=lambda c: len(c["missing"]), reverse=True)
    return out, unmatched
