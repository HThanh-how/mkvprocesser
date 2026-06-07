"""Doc cau hinh tu config.yaml (fallback config.example.yaml) + ghi de bang ui_settings.json
(admin sua tren web) + override bang env."""
import json
import os

import yaml

_DEFAULTS = {
    "client_secret": "secrets/client_secret.json",
    "token_file": "secrets/token.json",
    "inbox_dir": "inbox", "work_dir": "work", "done_dir": "done",
    "cleanup_outputs": True, "upload": True,
    "privacy": "private", "category_id": 22,
    "subtitle_mode": "caption", "container": "mp4",
    "captions": "all",          # all = up MOI phu de chu (moi ngon ngu) | paired = chi sub cung lang
    "audio_per_lang": "best",   # best = moi ngon ngu giu 1 audio tot nhat | all = giu het
    "make_playlist": True, "default_caption_lang": "vi",
    # Playlist tong: moi video upload deu them vao day (de tim/lay lai). Rong = tat.
    "master_playlist": "",
    "organize_budget": 2000,    # quota toi da moi lan chay 'organize' (timer dung)
    "description": "", "tags": [],
    # Placeholder: {res} {lang} {year} {title}(da chuan hoa) {label} {base}(ten file tho)
    "title_template": "{res}_{lang}_{year}_{title}",
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
    # --- Tai tu link + xoay vong dia (UI dan link -> tu tai -> tach -> upload) ---
    "downloads_dir": "inbox",   # noi tai link ve (mac dinh chung inbox)
    "delete_source": False,     # rotation: XOA file nguon sau khi upload (o nho) thay vi move done/
    "min_free_gb": 5.0,         # doi du chung nay GB trong moi tai link tiep (rotation). 0 = tat
    # Dang nhap GUI (login + phan quyen). Tai khoan luu o file nay (JSON).
    "users_file": "secrets/users.json",
    # Cookie (cookies.txt dinh dang Netscape) cho trang can dang nhap khi tai link.
    "cookies_file": "",
    # --- Che do "Bat tay" (dieu khien browser server qua noVNC + sniff CDP) ---
    "catch_cdp": "http://127.0.0.1:9222",   # CDP cua Chromium dieu khien-tay
    "catch_novnc_port": 6080,               # cong noVNC (iframe nhung vao GUI)
    "vnc_password": "",                     # mat khau VNC (dat qua env MKV_VNC_PASSWORD)
    # --- Cache (tiet kiem quota YouTube): lay 1 lan/ngay roi doc cache ---
    "redis_url": "",            # redis://host:6379/0 (rong = cache file tren dia)
    "cache_ttl": 86400,         # TTL cache giay (86400 = lay YouTube 1 lan/ngay)
    # --- Tu tim sub (OpenSubtitles) cho phim KHONG co sub nhung ---
    "auto_fetch_subs": False,   # bat: phim khong co sub chu -> tu tim vi/en va up caption
    "sub_langs": "vi,en",       # ngon ngu uu tien khi tu tim sub
    "opensubtitles_api_key": "",   # tu opensubtitles.com (free)
    "opensubtitles_user": "",
    "opensubtitles_pass": "",
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
    "captions": {"all", "paired"},
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


def ui_settings_path():
    """Duong dan file ghi de cau hinh do admin sua tren web (canh config.yaml)."""
    cp = _find_config()
    base = os.path.dirname(cp) if cp else os.getcwd()
    return os.path.join(base, "ui_settings.json")


def save_ui_settings(changes: dict) -> dict:
    """Ghi/cap nhat cac muc admin sua tren web (JSON, ghi nguyen tu). Tra ve toan bo overrides."""
    uip = ui_settings_path()
    cur = {}
    if os.path.exists(uip):
        try:
            with open(uip, encoding="utf-8") as f:
                cur = json.load(f) or {}
        except (OSError, ValueError):
            cur = {}
    cur.update(changes)
    os.makedirs(os.path.dirname(uip) or ".", exist_ok=True)
    tmp = uip + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    os.replace(tmp, uip)
    return cur


def load(path=None):
    path = _find_config(path)
    cfg = dict(_DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})
    uip = ui_settings_path()                 # admin sua tren web -> ghi de config.yaml
    if os.path.exists(uip):
        try:
            with open(uip, encoding="utf-8") as f:
                cfg.update(json.load(f) or {})
        except (OSError, ValueError):
            pass
    # env override (MKV_PRIVACY, MKV_UPLOAD, ...) cao nhat (cho ha tang), ep kieu theo default
    for k in cfg:
        env = os.environ.get("MKV_" + k.upper())
        if env is not None:
            cfg[k] = _coerce(_DEFAULTS.get(k, ""), env)
    return validate(cfg)
