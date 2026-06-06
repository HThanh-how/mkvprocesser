"""Doc cau hinh tu config.yaml (fallback config.example.yaml) + override bang env."""
import os

import yaml

_DEFAULTS = {
    "client_secret": "secrets/client_secret.json",
    "token_file": "secrets/token.json",
    "inbox_dir": "inbox", "work_dir": "work", "done_dir": "done",
    "cleanup_outputs": True, "upload": True,
    "privacy": "private", "category_id": 22,
    "subtitle_mode": "caption", "container": "mp4",
    "audio_per_lang": "best",   # best = moi ngon ngu giu 1 audio tot nhat | all = giu het
    "make_playlist": True, "default_caption_lang": "vi",
    "description": "", "tags": [],
    # Placeholder: {res} {lang} {year} {title}(da chuan hoa) {label} {base}(ten file tho)
    "title_template": "[{res}][{lang}] {title} ({year})",
    "playlist_template": "{title} ({year})",
    "watch_ext": [".mkv", ".mp4", ".ts", ".mov", ".webm"], "poll_seconds": 10,
    # Idempotency: bo qua file da xu ly (theo chu ky noi dung), trang thai ben dia.
    "skip_processed": True, "state_file": "work/processed.json",
    # An toan dia: can free >= kich_thuoc_file * min_free_gb_factor truoc khi tach.
    "min_free_gb_factor": 1.5,
    # Chong trung theo TUA DE (nhe, phan biet Phan 1/2/3). on_title_match: skip|warn.
    "dedup_by_title": True, "on_title_match": "skip",
    # Da co phim nhung ban moi do phan giai CAO HON -> van up (nang cap).
    "upgrade_on_higher_res": True,
    # Proxy cho upload/API YouTube (rong = khong dung). VD http://host:8080, socks5://host:1080
    "proxy": "",
}


def _coerce(default, raw: str):
    """Ep gia tri env (luon la str) ve dung kieu cua default."""
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, list):
        return [s for s in (x.strip() for x in raw.split(",")) if s]
    return raw


_ENUMS = {
    "privacy": {"private", "unlisted", "public"},
    "subtitle_mode": {"caption", "burn", "both"},
    "container": {"mp4", "mkv"},
    "on_title_match": {"skip", "warn"},
    "audio_per_lang": {"best", "all"},
}


def validate(cfg: dict) -> dict:
    """Kiem tra enum + so duong. Nem ValueError ro rang neu cau hinh sai."""
    for key, allowed in _ENUMS.items():
        val = cfg.get(key)
        if val is not None and val not in allowed:
            raise ValueError(f"config: {key}={val!r} khong hop le, phai thuoc {sorted(allowed)}")
    ps = cfg.get("poll_seconds", 10)
    try:
        ps_int = int(ps)
    except (TypeError, ValueError):
        raise ValueError(f"config: poll_seconds={ps!r} khong phai so") from None
    if ps_int <= 0:
        raise ValueError("config: poll_seconds phai > 0")
    return cfg


def _find_config(path=None):
    """Tim file config: arg -> $MKV_CONFIG -> ./ (thu muc chay) -> repo-root (dev).

    Quan trong cho ban cai bang pip / Docker: truoc day chi tim theo duong dan
    module nen config.yaml mount o /app (CWD) khong duoc nhan.
    """
    if path:
        return path
    env = os.environ.get("MKV_CONFIG")
    if env:
        return env
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name in ("config.yaml", "config.example.yaml"):
        for d in (os.getcwd(), base):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def load(path=None):
    path = _find_config(path)
    cfg = dict(_DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})
    # env override (MKV_PRIVACY, MKV_UPLOAD, ...), ep kieu theo default tuong ung
    for k in cfg:
        env = os.environ.get("MKV_" + k.upper())
        if env is not None:
            cfg[k] = _coerce(_DEFAULTS.get(k, ""), env)
    return validate(cfg)
