"""
GUI web local (fallback khi muon lam tay). Chay:  python -m mkvtools.webui
Mo http://127.0.0.1:8800 . Liet ke file trong inbox/, phan tich, tach + (tuy chon) upload.
Chay tac vu o thread nen, log poll qua /status.
"""
import os
import pathlib
import threading
import urllib.parse

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from . import (
    auth,
    cache,
    catch,
    config,
    fetch,
    ffmpeg_helper,
    idempotency,
    jobs,
    pipeline,
    resources,
)

_WEBDIR = pathlib.Path(__file__).parent / "web"


def _web(name: str) -> str:
    """Doc file giao dien tinh (Tailwind) trong package/web/. Doc moi lan -> sua file la thay."""
    return (_WEBDIR / name).read_text(encoding="utf-8")

cfg = config.load()
app = FastAPI(title="mkvtools GUI")

# Dang nhap + phan quyen: tai khoan luu o cfg['users_file'], phien giu trong RAM.
# Lan dau chua co user -> tao admin (env MKV_ADMIN_USER/PASS hoac sinh ngau nhien).
USERS = auth.UserStore(cfg.get("users_file", "secrets/users.json"))
SESS = auth.Sessions()
THROTTLE = auth.LoginThrottle()     # chong do mat khau (theo IP)
_PUBLIC = {"/login"}        # duong dan khong can dang nhap (bootstrap admin o main())

_job = {"running": False, "log": [], "file": None}
_lock = threading.Lock()

# Hang doi link: dan URL -> tu tai -> tach -> upload -> xoay vong dia (xoa nguon).
Q = jobs.JobQueue(history_file=os.path.join(cfg.get("work_dir", "work"), "queue_history.json"))
# Che do "Bat tay": gan vao Chromium dieu khien-tay (noVNC) + sniff media qua CDP.
CATCH = catch.CatchSession(cfg.get("catch_cdp", "http://127.0.0.1:9222"))
# Cache YouTube (tiet kiem quota): lay 1 lan/ngay roi doc cache.
VIDEOCACHE = cache.Cache(redis_url=cfg.get("redis_url", ""),
                         file_dir=os.path.join(cfg.get("work_dir", "work"), "cache"),
                         ttl=int(cfg.get("cache_ttl", 86400) or 0))


def _start_drain():
    """Khoi dong worker rut hang doi neu dang ranh (1 luong, xu ly tuan tu)."""
    if not Q.try_start():        # da co worker chay -> no se tu nhat link moi them
        return

    def runner():
        try:
            yt = None
            if cfg.get("upload", True):
                from . import uploader as up
                yt = up.get_service(cfg["client_secret"], cfg["token_file"],
                                    proxy=cfg.get("proxy", ""))
            store = idempotency.ProcessedStore(cfg.get("state_file", "work/processed.json"))
            rcfg = {**cfg, "delete_source": True}      # hang doi luon xoay vong: xoa nguon sau upload

            def process_fn(src, c, log):
                return pipeline.process_file(src, c, yt=yt, do_upload=cfg.get("upload", True),
                                             log=log, store=store)

            default_cookies = cfg.get("cookies_file") or None

            def fetch_fn(u, d, log, cookies=None, referer=None):   # 4 tang + cookie/referer
                return fetch.fetch(u, d, log=log, cookies=cookies or default_cookies,
                                   referer=referer)

            jobs.drain(Q, rcfg, fetch_fn=fetch_fn, process_fn=process_fn)
        except Exception as e:                          # noqa: BLE001
            Q.say(f"LOI worker: {e}")
        finally:
            Q.stop()             # luoi an toan neu thoat bat thuong (binh thuong pop() da tat)

    threading.Thread(target=runner, daemon=True).start()


def _current_user(request):
    """{username, role} tu cookie phien, hoac None neu chua/het dang nhap."""
    uname = SESS.get(request.cookies.get("mkv_sess"))
    return USERS.get(uname) if uname else None


@app.middleware("http")
async def _auth(request: Request, call_next):
    user = _current_user(request)
    request.state.user = user            # route doc qua request.state.user
    if request.url.path not in _PUBLIC and user is None:
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


def _require_admin(request):
    """None neu la admin; nguoc lai tra response 403 de route return luon."""
    u = getattr(request.state, "user", None)
    if not u or u.get("role") != "admin":
        return PlainTextResponse("Chi admin moi vao duoc trang nay.", status_code=403)
    return None


def _userbar(request):
    u = getattr(request.state, "user", None) or {}
    admin_link = " &middot; <a href=/admin>Quan tri</a>" if u.get("role") == "admin" else ""
    return (f"<p class=muted style='text-align:right;margin:-6px 0 6px'>"
            f"{u.get('username', '?')} ({u.get('role', '?')}) "
            f"&middot; <a href=/>Trang chinh</a> &middot; <a href=/catch>Bat tay</a>{admin_link} "
            f"&middot; <a href=/logout>Dang xuat</a></p>")


def _log(msg):
    with _lock:
        _job["log"].append(str(msg))


def _inbox_files():
    d = cfg["inbox_dir"]
    if not os.path.isdir(d):
        return []
    exts = tuple(cfg["watch_ext"])
    return sorted(f for f in os.listdir(d) if f.lower().endswith(exts))


STYLE = """<style>
body{font:15px system-ui,sans-serif;background:#0f1115;color:#e8eaed;max-width:820px;
margin:24px auto;padding:0 16px}h1{font-size:20px}a{color:#7ab4ff}
.card{background:#1a1d24;border:1px solid #2a2f3a;border-radius:12px;padding:18px;margin:14px 0}
button{background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:9px 16px;cursor:pointer;font-size:14px}
select,label{font-size:14px}pre{background:#0b0d11;border:1px solid #2a2f3a;border-radius:8px;
padding:12px;white-space:pre-wrap;max-height:340px;overflow:auto}.muted{color:#9aa0aa}
.t{padding:4px 0;border-bottom:1px solid #20242c}</style>"""


def page(body):
    return f"<!doctype html><meta charset=utf-8><title>mkvtools</title>{STYLE}<h1>mkvtools — GUI</h1>{body}"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return HTMLResponse(_web("dashboard.html"))      # giao dien moi (Tailwind), nap du lieu qua /queue


@app.get("/classic", response_class=HTMLResponse)
def home_classic(request: Request):
    files = _inbox_files()
    opts = "".join(f"<option>{f}</option>" for f in files) or "<option disabled>(inbox trong)</option>"
    up_checked = "checked" if cfg.get("upload", True) else ""
    running = _job["running"]
    snap = Q.snapshot()
    pend = snap["pending"]
    pend_html = "".join(f"<div class=t>&bull; {u}</div>" for u in pend) or "<span class=muted>(trong)</span>"
    hist_html = "".join(
        f"<div class=t>{'&check;' if h['status'] == 'done' else '&cross;'} "
        f"{h.get('name') or h['url']}{(' &mdash; ' + h['error']) if h.get('error') else ''}</div>"
        for h in reversed(snap["history"])) or "<span class=muted>(chua co)</span>"
    poll = str(running or snap["running"] or bool(pend)).lower()
    return page(f"""{_userbar(request)}
<div class=card>
<b>Dan link &rarr; tu tai &rarr; tach &rarr; upload &rarr; xoay vong dia</b>
<form method=post action=/enqueue style=margin-top:8px>
  <textarea name=links rows=4 style="width:100%;box-sizing:border-box;background:#0b0d11;color:#e8eaed;border:1px solid #2a2f3a;border-radius:8px;padding:10px" placeholder="Moi dong 1 link (YouTube / trang stream / file-host / link .mkv .mp4 truc tiep)"></textarea>
  <div style=margin-top:8px><button>Them vao hang doi</button>
  <span class=muted>upload: {'bat' if cfg.get('upload', True) else 'tat'} &middot; xoa nguon sau upload (rotation)</span></div>
</form>
<p class=muted style=margin-top:10px>Dang chay: <b>{snap['current'] or '(khong)'}</b> &middot; cho: {len(pend)} link</p>
<div style="display:flex;gap:14px;flex-wrap:wrap">
  <div style="flex:1;min-width:240px"><b>Hang cho</b>{pend_html}</div>
  <div style="flex:1;min-width:240px"><b>Lich su</b>{hist_html}</div>
</div>
<pre id=qlog>{chr(10).join(snap['log'][-120:]) or '(chua co log)'}</pre>
</div>

<div class=card>
<p class=muted>Hoac xu ly file co san trong inbox: <code>{cfg['inbox_dir']}</code> &mdash; {len(files)} file</p>
<form method=post action=/analyze>
  <select name=file>{opts}</select>
  <button {'disabled' if running else ''}>Phan tich</button>
</form>
<form method=post action=/run style=margin-top:10px>
  <select name=file>{opts}</select>
  <label><input type=checkbox name=upload {up_checked}> upload YouTube</label>
  <button {'disabled' if running else ''}>Chay</button>
</form>
<pre id=log>{chr(10).join(_job['log'][-120:]) or '(chua co)'}</pre>
</div>
<script>if({poll})setTimeout(()=>location.reload(),2500)</script>
""")


@app.post("/analyze", response_class=HTMLResponse)
def analyze(file: str = Form(...)):
    src = os.path.join(cfg["inbox_dir"], file)
    try:
        p = pipeline.analyze_file(src, cfg)
    except Exception as e:
        return page(f"<div class=card>Loi: {e} <p><a href=/>&laquo; ve</a></div>")
    rows = "".join(
        f"<div class=t>{o['lang'] or '?'} ({o['ch']}ch) &rarr; "
        f"{os.path.basename(o['out'])} | {'sub: ' + os.path.basename(o['srt']) if o['srt'] else 'khong sub'}</div>"
        for o in p["outputs"])
    return page(f"""<div class=card><b>{p['base']}</b> [{p['res']}{(' ' + p['year']) if p['year'] else ''}]
<p>{len(p['outputs'])} ban audio:</p>{rows}
<p><a href=/>&laquo; ve</a></div>""")


def _worker(src, do_upload):
    try:
        yt = None
        if do_upload:
            from . import (
                uploader as up,  # nap khi can -> GUI khong upload van chay khong can google
            )
            yt = up.get_service(cfg["client_secret"], cfg["token_file"], proxy=cfg.get("proxy", ""))
        # bam "Chay" tren GUI = thao tac tay -> luon chay (force) du da xu ly truoc do
        pipeline.process_file(src, cfg, yt=yt, do_upload=do_upload, log=_log, force=True)
    except Exception as e:
        _log(f"LOI: {e}")
    finally:
        with _lock:
            _job["running"] = False


@app.post("/run", response_class=HTMLResponse)
def run(file: str = Form(...), upload: str = Form(None)):
    with _lock:
        if _job["running"]:
            return page("<div class=card>Dang co tac vu chay. <a href=/>ve</a></div>")
        _job.update(running=True, log=[], file=file)
    src = os.path.join(cfg["inbox_dir"], file)
    threading.Thread(target=_worker, args=(src, upload is not None), daemon=True).start()
    return page("<div class=card>Da bat dau. <a href=/>Theo doi tien trinh &raquo;</a></div>")


@app.get("/status")
def status():
    return {"running": _job["running"], "log": _job["log"][-200:]}


@app.post("/enqueue", response_class=HTMLResponse)
def enqueue(links: str = Form(...)):
    n = Q.add_many(links)
    if n:
        _start_drain()
    return page(f"<div class=card>Da them <b>{n}</b> link vao hang doi. "
                f"<a href=/>Theo doi tien trinh &raquo;</a></div>")


@app.get("/queue")
def queue():
    snap = Q.snapshot()
    dl = cfg.get("downloads_dir") or cfg.get("inbox_dir", "inbox")
    snap["disk_free_gb"] = round(resources.free_gb(dl), 1)
    return snap


@app.get("/videos", response_class=HTMLResponse)
def videos_page(request: Request):
    return HTMLResponse(_web("videos.html"))


@app.get("/videos/list")
def videos_list(refresh: int = 0):
    """Liet ke video da upload (thu vien). Doc CACHE truoc; chi goi API khi het han
    hoac ?refresh=1. Loi API (vd het quota) -> phuc vu cache cu (stale)."""
    val, age = VIDEOCACHE.get("videos:list")
    if val is not None and not refresh and VIDEOCACHE.fresh(age, cfg.get("cache_ttl")):
        return {"ok": True, "videos": val, "cached": True, "age": int(age),
                "backend": VIDEOCACHE.backend()}
    if not os.path.exists(cfg.get("token_file", "") or ""):
        if val is not None:
            return {"ok": True, "videos": val, "cached": True, "stale": True, "age": int(age)}
        return {"ok": False, "error": "Chua dang nhap YouTube (thieu token)."}
    try:
        from . import uploader as up
        yt = up.get_service(cfg["client_secret"], cfg["token_file"], proxy=cfg.get("proxy", ""))
        vids = up.list_uploaded_videos(yt, limit=2000)
        VIDEOCACHE.set("videos:list", vids)
        return {"ok": True, "videos": vids, "cached": False, "age": 0, "backend": VIDEOCACHE.backend()}
    except Exception as e:        # noqa: BLE001 - vd het quota -> dung cache cu neu co
        if val is not None:
            return {"ok": True, "videos": val, "cached": True, "stale": True, "age": int(age),
                    "error": str(e), "backend": VIDEOCACHE.backend()}
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- dang nhap / quan tri
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_web("login.html"))


@app.get("/me")
def me(request: Request):
    return getattr(request.state, "user", None) or {}


@app.post("/me/password")
def me_password(request: Request, password: str = Form(...)):
    """Nguoi dung tu doi mat khau CUA CHINH MINH (phien hien tai = danh tinh)."""
    u = getattr(request.state, "user", None)
    if not u:
        return PlainTextResponse("chua dang nhap", status_code=401)
    if len(password) < 4:
        return {"ok": False, "error": "mat khau toi thieu 4 ky tu"}
    USERS.change_password(u["username"], password)
    return {"ok": True}


# ---------------------------------------------------------------- cai dat (admin)
# Cac muc admin duoc sua tren web (ghi de config.yaml qua ui_settings.json).
_SETTINGS_KEYS = [
    "upload", "privacy", "make_playlist", "master_playlist", "organize_budget",
    "default_caption_lang", "category_id", "subtitle_mode", "captions", "audio_per_lang",
    "container", "title_template", "playlist_template", "delete_source", "min_free_gb",
    "inbox_dir", "work_dir", "done_dir", "downloads_dir", "skip_processed", "dedup_by_title",
    "on_title_match", "upgrade_on_higher_res", "cookies_file", "proxy", "cache_ttl",
    "auto_fetch_subs", "sub_langs",
]


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    block = _require_admin(request)
    return block or HTMLResponse(_web("settings.html"))


@app.get("/settings/get")
def settings_get(request: Request):
    block = _require_admin(request)
    return block or {k: cfg.get(k) for k in _SETTINGS_KEYS}


@app.post("/settings/save")
async def settings_save(request: Request):
    block = _require_admin(request)
    if block:
        return block
    data = await request.json()
    changes = {}
    for k, v in (data or {}).items():
        if k not in _SETTINGS_KEYS:
            continue
        d = config._DEFAULTS.get(k, "")
        try:
            if isinstance(d, bool):
                changes[k] = bool(v)
            elif isinstance(d, int) and not isinstance(d, bool):
                changes[k] = int(v)
            elif isinstance(d, float):
                changes[k] = float(v)
            else:
                changes[k] = "" if v is None else str(v)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Gia tri khong hop le: {k}={v!r}"}
    try:
        config.validate({**cfg, **changes})           # kiem enum/so truoc khi luu
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    config.save_ui_settings(changes)
    cfg.clear()
    cfg.update(config.load())                          # ap dung ngay cho tac vu sau
    return {"ok": True, "saved": list(changes)}


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    key = request.client.host if request.client else "?"
    wait = THROTTLE.blocked(key)
    if wait:
        return RedirectResponse(
            "/login?err=" + urllib.parse.quote(f"Nhap sai nhieu lan, thu lai sau {wait}s"),
            status_code=302)
    if USERS.verify(username, password):
        THROTTLE.reset(key)
        r = RedirectResponse("/", status_code=302)
        r.set_cookie("mkv_sess", SESS.create(username), httponly=True, samesite="lax",
                     secure=request.url.scheme == "https")
        return r
    THROTTLE.record_fail(key)
    return RedirectResponse("/login?err=" + urllib.parse.quote("Sai tai khoan hoac mat khau"),
                            status_code=302)


@app.get("/logout")
def logout(request: Request):
    SESS.destroy(request.cookies.get("mkv_sess"))
    r = RedirectResponse("/login", status_code=302)
    r.delete_cookie("mkv_sess")
    return r


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    block = _require_admin(request)
    if block:
        return block
    return HTMLResponse(_web("admin.html"))


@app.get("/admin/users")
def admin_users(request: Request):
    block = _require_admin(request)
    if block:
        return block
    return {"me": request.state.user["username"], "users": USERS.list()}


@app.post("/admin/add")
def admin_add(request: Request, username: str = Form(...), password: str = Form(...),
              role: str = Form("user")):
    block = _require_admin(request)
    if block:
        return block
    try:
        USERS.add(username, password, role)
        msg = f"Da them tai khoan {username}"
    except ValueError as e:
        msg = f"Loi: {e}"
    return RedirectResponse("/admin?msg=" + urllib.parse.quote(msg), status_code=302)


@app.post("/admin/action")
def admin_action(request: Request, username: str = Form(...), action: str = Form(...),
                 value: str = Form("")):
    block = _require_admin(request)
    if block:
        return block
    me = request.state.user["username"]
    try:
        if action in ("disable", "delete", "role") and username == me:
            raise ValueError("khong tu thao tac len chinh minh (tranh tu khoa)")
        if action == "disable":
            USERS.set_disabled(username, True)
            msg = f"Da khoa {username}"
        elif action == "enable":
            USERS.set_disabled(username, False)
            msg = f"Da mo khoa {username}"
        elif action == "role":
            USERS.set_role(username, value)
            msg = f"{username} -> {value}"
        elif action == "delete":
            USERS.remove(username)
            msg = f"Da xoa {username}"
        elif action == "reset":
            if not value:
                raise ValueError("mat khau moi rong")
            USERS.change_password(username, value)
            msg = f"Da doi mat khau cho {username}"
        else:
            raise ValueError(f"action khong ro: {action}")
    except ValueError as e:
        msg = f"Loi: {e}"
    return RedirectResponse("/admin?msg=" + urllib.parse.quote(msg), status_code=302)


# ------------------------------------------------------------------- "Bat tay"
@app.get("/catch", response_class=HTMLResponse)
def catch_page(request: Request):
    return HTMLResponse(_web("catch.html"))


@app.get("/catch/config")
def catch_config():
    return {"novnc_port": cfg.get("catch_novnc_port", 6080),
            "vnc_password": cfg.get("vnc_password", "")}


@app.get("/web/{name}")
def web_static(name: str):
    if "/" in name or ".." in name or not name.endswith((".js", ".css")):
        return PlainTextResponse("not found", status_code=404)
    p = _WEBDIR / name
    if not p.exists():
        return PlainTextResponse("not found", status_code=404)
    return Response(p.read_text(encoding="utf-8"),
                    media_type="application/javascript" if name.endswith(".js") else "text/css")


@app.post("/catch/start")
def catch_start():
    started = CATCH.start()
    return {"ok": True, "started": started, "running": CATCH.running()}


@app.post("/catch/stop")
def catch_stop():
    CATCH.stop()
    return {"ok": True}


@app.post("/catch/clear")
def catch_clear():
    CATCH.clear()
    return {"ok": True}


@app.get("/catch/captured")
def catch_captured():
    return CATCH.snapshot()


@app.post("/catch/enqueue")
def catch_enqueue(url: str = Form(...), referer: str = Form("")):
    work = cfg.get("work_dir", "work")
    cookies_path = os.path.join(work, "catch-cookies.txt")
    try:
        os.makedirs(work, exist_ok=True)
        CATCH.export_cookies(cookies_path)
    except Exception as e:        # noqa: BLE001
        Q.say(f"(catch) khong xuat duoc cookie: {e}")
        cookies_path = cfg.get("cookies_file") or None
    Q.add(url, cookies=cookies_path, referer=referer or None)
    _start_drain()
    return {"ok": True}


def main():
    import uvicorn
    if not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe.")
    auth.bootstrap_admin(USERS)          # lan dau: tao admin (env hoac mat khau ngau nhien in ra)
    uvicorn.run(app, host=os.environ.get("MKV_GUI_HOST", "127.0.0.1"),
                port=int(os.environ.get("MKV_GUI_PORT", "8800")))


if __name__ == "__main__":
    main()
