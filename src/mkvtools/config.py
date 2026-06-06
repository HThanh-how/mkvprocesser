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
    "make_playlist": True, "default_caption_lang": "vi",
    "description": "", "tags": [],
    "title_template": "{base} [{lang}]", "playlist_template": "{base}",
    "watch_ext": [".mkv", ".mp4", ".ts", ".mov", ".webm"], "poll_seconds": 10,
    # Idempotency: bo qua file da xu ly (theo chu ky noi dung), trang thai ben dia.
    "skip_processed": True, "state_file": "work/processed.json",
    # An toan dia: can free >= kich_thuoc_file * min_free_gb_factor truoc khi tach.
    "min_free_gb_factor": 1.5,
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


def load(path=None):
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if path is None:
        for c in ("config.yaml", "config.example.yaml"):
            p = os.path.join(base, c)
            if os.path.exists(p):
                path = p
                break
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
