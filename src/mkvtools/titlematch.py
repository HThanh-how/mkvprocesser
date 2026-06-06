"""Chong trung theo TUA DE (nhe: chi doc ten file, khong dung video).

Y tuong: chuan hoa ten -> bo cac token "rac" cua ban phat hanh (do phan giai,
codec, nguon, audio...) + tach nam ra rieng. Khoa = "tua_chuan_hoa|nam".

- Bat duoc ban re-encode/doi rip (cung tua, khac bytes).
- Phan biet Phan 1/2/3 (tua khac nhau -> khoa khac nhau).
- So khop DUNG (exact) sau chuan hoa -> KHONG fuzzy -> khong nham "gan giong".
- KHONG bao gio bo so/tu ngan co nghia (vd "part 5") -> tranh nham cac phan.
"""
from __future__ import annotations

import os
import re

# Token "rac" cua ban phat hanh -> bo di. KHONG chua so tran -> giu "part 1".
_JUNK = {
    # do phan giai
    "480p", "576p", "720p", "1080p", "1080i", "2160p", "4k", "8k", "uhd",
    "hd", "fhd", "qhd", "hq",
    # nguon
    "bluray", "bdrip", "brrip", "webrip", "webdl", "web", "hdrip", "hdtv",
    "dvdrip", "dvd", "remux", "cam", "telesync", "hdcam", "vodrip",
    # codec
    "x264", "x265", "h264", "h265", "hevc", "avc", "av1", "xvid", "divx",
    "10bit", "8bit",
    # audio
    "aac", "ac3", "eac3", "ddp", "dts", "dtshd", "truehd", "atmos", "flac",
    "mp3", "opus",
    # khac
    "proper", "repack", "extended", "uncut", "remastered", "remaster",
    "internal", "limited", "imax", "hdr", "hdr10", "sdr", "dovi", "dolby",
    "vision", "multi", "dual",
}
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_EXT = re.compile(r"\.[a-z0-9]{2,4}$", re.IGNORECASE)


def parse_year(name: str) -> str:
    """Nam phat hanh = nam (19xx/20xx) xuat hien CUOI cung trong ten, '' neu khong co."""
    years = _YEAR.findall(_EXT.sub("", os.path.basename(name)))
    return years[-1] if years else ""


def normalize_title(name: str) -> str:
    """Chuan hoa tua: cat tai MARKER dau tien (nam HOAC token rac phat hanh).

    'Avengers.Endgame.2019.1080p.x264-GRP'  -> 'avengers endgame'
    'Money.Heist.Part.1.2017.1080p'         -> 'money heist part 1'  (giu phan/tap
                                               vi chung dung truoc nam -> phan biet phan 2)
    Moi ban rip cua cung phim -> cung tua (vi rac sau marker bi cat het).
    """
    s = _EXT.sub("", os.path.basename(name)).lower()
    s = re.sub(r"[\[\(\{].*?[\]\)\}]", " ", s)         # bo () [] {} (thuong chua nam/nhom)
    s = re.sub(r"[._\-]+", " ", s)                      # tach . _ -
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)   # bo dau cau con lai
    out = []
    for tok in s.split():
        if _YEAR.fullmatch(tok) or tok in _JUNK:
            break                                       # gap nam/rac -> phan sau la metadata
        out.append(tok)
    return " ".join(out).strip()


def title_key(name: str, year: str | None = None) -> str:
    """Khoa chong trung = tua chuan hoa + nam. '' neu khong rut duoc tua."""
    base = normalize_title(os.path.basename(name))
    if not base:
        return ""
    y = (year if year is not None else parse_year(os.path.basename(name))).strip()
    return f"{base}|{y}"
