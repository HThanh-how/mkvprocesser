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
}


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
    # env override (MKV_PRIVACY, MKV_UPLOAD, ...)
    for k in cfg:
        env = os.environ.get("MKV_" + k.upper())
        if env is not None:
            cfg[k] = env
    return cfg
