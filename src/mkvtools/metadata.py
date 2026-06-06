"""Tien ich metadata: do phan giai, nam, ma ngon ngu."""

_LANG_ABBR = {
    "eng": "ENG", "vie": "VIE", "und": "UNK", "chi": "CHI", "zho": "CHI",
    "jpn": "JPN", "kor": "KOR", "fra": "FRA", "fre": "FRA", "deu": "DEU",
    "ger": "DEU", "spa": "SPA", "ita": "ITA", "rus": "RUS", "tha": "THA",
    "ind": "IND", "msa": "MSA", "ara": "ARA", "hin": "HIN", "por": "POR",
    "nld": "NLD", "yue": "YUE", "cmn": "CMN", "khm": "KHM", "lao": "LAO",
}
# ISO 639-2 -> BCP-47 (YouTube API)
_BCP47 = {
    "vie": "vi", "eng": "en", "jpn": "ja", "kor": "ko", "zho": "zh", "chi": "zh",
    "fra": "fr", "fre": "fr", "deu": "de", "ger": "de", "spa": "es", "rus": "ru",
    "tha": "th", "ind": "id", "por": "pt", "ita": "it", "hin": "hi", "ara": "ar",
}


def lang_abbr(code: str) -> str:
    if not code:
        return "UNK"
    return _LANG_ABBR.get(code.lower(), code.upper()[:3])


def bcp47(code: str, default: str = "und") -> str:
    if not code:
        return default
    code = code.lower()
    return code if len(code) == 2 else _BCP47.get(code, default)


def resolution_label(streams: list[dict]) -> str:
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        return "unknown"
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    if w >= 7680 or h >= 4320:
        return "8K"
    if w >= 3840 or h >= 2160:
        return "4K"
    if w >= 2560 or h >= 1440:
        return "2K"
    if w >= 1920 or h >= 1080:
        return "FHD"
    if w >= 1280 or h >= 720:
        return "HD"
    if w >= 720 or h >= 480:
        return "480p"
    return f"{h}p" if h else "unknown"


def movie_year(info: dict) -> str:
    tags = (info.get("format", {}) or {}).get("tags", {}) or {}
    for k in ("year", "date", "creation_time"):
        v = tags.get(k, "")
        if v and v[:4].isdigit():
            return v[:4]
    return ""
