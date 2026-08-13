"""
GUI web local (fallback khi muon lam tay). Chay:  python -m mkvtools.webui
Mo http://127.0.0.1:8800 . Liet ke file trong inbox/, phan tich, tach + (tuy chon) upload.
Chay tac vu o thread nen, log poll qua /status.
"""
import hmac
import json
import logging
import os
import pathlib
import re
import secrets as _secrets
import threading
import time
import urllib.parse
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)

from . import (
    auth,
    cache,
    catch,
    config,
    fetch,
    ffmpeg_helper,
    idempotency,
    jobs,
    logging_setup,
    observability,
    pipeline,
    resources,
    security,
    shorts,
    templating,
)

logger = logging.getLogger("mkvtools.webui")
_STARTED_AT = time.time()

_WEBDIR = pathlib.Path(__file__).parent / "web"


def _web(name: str) -> str:
    """Doc file giao dien tinh (Tailwind) trong package/web/. Doc moi lan -> sua file la thay."""
    return (_WEBDIR / name).read_text(encoding="utf-8")

cfg = config.load()
app = FastAPI(title="mkvtools GUI")

_RUNTIME_DIR_KEYS = ("inbox_dir", "work_dir", "done_dir", "downloads_dir")


def _ensure_runtime_dirs(config_data=None):
    """Tao lai cac thu muc runtime neu bi cleanup/xoa sau reboot hoặc migrate storage."""
    active = cfg if config_data is None else config_data
    for key in _RUNTIME_DIR_KEYS:
        path = active.get(key)
        if path:
            pathlib.Path(path).mkdir(parents=True, exist_ok=True)

# Dang nhap + phan quyen: tai khoan luu o cfg['users_file'], phien giu trong RAM.
# Lan dau chua co user -> tao admin (env MKV_ADMIN_USER/PASS hoac sinh ngau nhien).
USERS = auth.UserStore(cfg.get("users_file", "secrets/users.json"))
# Phien ghi xuong dia: may bi tat theo lich (vd 19:25 hang ngay) ma khong bat
# moi nguoi dang nhap lai sang hom sau. File chi chua hash cua token.
SESS = auth.Sessions(path=os.path.join(cfg.get("work_dir", "work"), "sessions.json"))
THROTTLE = auth.LoginThrottle()     # chong do mat khau (theo IP)
# Duong dan khong can dang nhap (bootstrap admin o main()). /web/csrf.js phai
# mo vi chinh trang dang nhap can no de gan token vao form.
_PUBLIC = {"/login", "/web/csrf.js", "/healthz"}

_job = {"running": False, "log": [], "file": None}
_lock = threading.Lock()

# Hang doi link: dan URL -> tu tai -> tach -> upload -> xoay vong dia (xoa nguon).
Q = jobs.JobQueue(
    history_file=os.path.join(cfg.get("work_dir", "work"), "queue_history.json"),
    queue_file=os.path.join(cfg.get("work_dir", "work"), "queue.json"),
    node_id=cfg.get("node_id", "local"),
)
# Che do "Bat tay": gan vao Chromium dieu khien-tay (noVNC) + sniff media qua CDP.
CATCH = catch.CatchSession(cfg.get("catch_cdp", "http://127.0.0.1:9222"))
# Cache YouTube (tiet kiem quota): lay 1 lan/ngay roi doc cache.
VIDEOCACHE = cache.Cache(redis_url=cfg.get("redis_url", ""),
                         file_dir=os.path.join(cfg.get("work_dir", "work"), "cache"),
                         ttl=int(cfg.get("cache_ttl", 86400) or 0))
# Video ngan (Short): tai ve giu lai cho nguoi dung tai ve may, hoac up YouTube Short.
SHORTS = shorts.ShortsManager(os.path.join(cfg.get("work_dir", "work"), "shorts"))


def _worker_allowed(now=None):
    """Node chi claim job trong ca cua no; job dang chay duoc phep ket thuc sach."""
    if not cfg.get("worker_enabled", True):
        return False
    if cfg.get("upload", True) and not os.path.exists(cfg.get("token_file", "") or ""):
        return False
    hour = (now or datetime.now()).hour
    start = int(cfg.get("worker_start_hour", 0))
    stop = int(cfg.get("worker_stop_hour", 24))
    if start == stop or (start == 0 and stop == 24):
        return True
    if start < stop:
        return start <= hour < stop
    return hour >= start or hour < stop


def _start_drain():
    """Khoi dong worker rut hang doi neu dang ranh (1 luong, xu ly tuan tu)."""
    if not _worker_allowed():
        return
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

            jobs.drain(Q, rcfg, fetch_fn=fetch_fn, process_fn=process_fn,
                       should_continue_fn=_worker_allowed)
        except Exception as e:                          # noqa: BLE001
            Q.say(f"LOI worker: {e}")
        finally:
            Q.stop()             # luoi an toan neu thoat bat thuong (binh thuong pop() da tat)

    threading.Thread(target=runner, daemon=True).start()


def _queue_scheduler():
    """Danh thuc worker khi den ca, ke ca job duoc import hoac khoi phuc sau reboot."""
    while True:
        try:
            if Q.snapshot()["pending"]:
                _start_drain()
        except Exception as e:  # noqa: BLE001 - scheduler phai song qua loi tam thoi
            Q.say(f"(!) scheduler: {e}")
        time.sleep(10)


def _start_shorts():
    """Worker rieng cho video ngan: tai 1 clip -> giu file (download) hoac up Short."""
    if not SHORTS.try_start():       # da co worker chay -> no se nhat job moi them
        return

    def runner():
        yt = None
        cookies = cfg.get("cookies_file") or None
        os.makedirs(SHORTS.dest_dir, exist_ok=True)
        try:
            while True:
                job = SHORTS.next_job()
                if not job:
                    break

                def log(m, _j=job):
                    SHORTS.log(_j, m)

                def require_video(path):
                    if fetch.valid_video_file(path):
                        return path
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    raise RuntimeError("CDN tra ve file khong phai video; hay chon clip khac")

                try:
                    if job["mode"] == "probe":
                        log(f"[tim] {job['url']}")
                        cands = fetch.list_video_candidates(job["url"], log=log, cookies=cookies)
                        job["candidates"] = cands
                        job["status"] = "ready"
                        log(f"[OK] tim thay {len(cands)} video")
                    elif job["mode"] == "batch":
                        import shutil
                        import zipfile

                        items = job.get("media_items") or []
                        if not items:
                            raise RuntimeError("Khong co video nao de tai hang loat")
                        tmp_root = os.path.join(SHORTS.dest_dir, f"_batch_{job['id']}")
                        os.makedirs(tmp_root, exist_ok=True)
                        zip_path = os.path.join(
                            SHORTS.dest_dir, f"batch_{job['id']}_{fetch.safe_name(job['name'])}")
                        used_names = set()
                        try:
                            # MP4 da nen san; ZIP_STORED dong goi nhanh va khong ton CPU vo ich.
                            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as archive:
                                for index, item in enumerate(items, 1):
                                    log(f"[tai {index}/{len(items)}] {item.get('referer') or item['url']}")
                                    item_dir = os.path.join(tmp_root, str(index))
                                    os.makedirs(item_dir, exist_ok=True)
                                    src = fetch.download_media_url(
                                        item["url"], item_dir, log=log,
                                        referer=item.get("referer"), cookies=cookies)
                                    src = require_video(src)
                                    entry = _short_download_name(
                                        {"url": item.get("referer") or job["url"],
                                         "name": item.get("label") or ""}, src)
                                    base, ext = os.path.splitext(entry)
                                    suffix = 2
                                    while entry.lower() in used_names:
                                        entry = f"{base}_{suffix}{ext}"
                                        suffix += 1
                                    used_names.add(entry.lower())
                                    archive.write(src, arcname=entry)
                        except Exception:
                            try:
                                os.remove(zip_path)
                            except OSError:
                                pass
                            raise
                        finally:
                            shutil.rmtree(tmp_root, ignore_errors=True)
                        job["file"] = zip_path
                        job["status"] = "done"
                        log(f"[OK] da dong goi {len(items)} video thanh ZIP")
                    elif job["mode"] == "upload":
                        log(f"[tai] {job.get('media_url') or job['url']}")
                        tmp = os.path.join(SHORTS.dest_dir, "_tmp")
                        os.makedirs(tmp, exist_ok=True)
                        if job.get("media_url"):           # clip da chon -> tai thang
                            src = fetch.download_media_url(job["media_url"], tmp, log=log,
                                                           referer=job.get("referer"), cookies=cookies)
                        else:
                            src = fetch.fetch(job["url"], tmp, log=log, cookies=cookies)
                        src = require_video(src)
                        from . import uploader as up
                        if yt is None:
                            yt = up.get_service(cfg["client_secret"], cfg["token_file"],
                                                proxy=cfg.get("proxy", ""))
                        title = shorts.short_title(job.get("name") or src)
                        log(f"[up] YouTube Short: {title}")
                        vid = up.upload_video(
                            yt, src, title, description=shorts.SHORTS_DESC,
                            tags=shorts.SHORTS_TAGS, privacy=cfg.get("privacy", "private"),
                            category_id=cfg.get("category_id", 22), log=log)
                        job["video_url"] = f"https://youtu.be/{vid}"
                        if os.path.exists(src):
                            os.remove(src)                # up xong -> khong giu file tam
                        job["status"] = "done"
                        log(f"[OK] {job['video_url']}")
                    else:
                        log(f"[tai] {job.get('media_url') or job['url']}")
                        if job.get("media_url"):           # clip da chon -> tai thang
                            src = fetch.download_media_url(job["media_url"], SHORTS.dest_dir,
                                                           log=log, referer=job.get("referer"),
                                                           cookies=cookies)
                        else:
                            src = fetch.fetch(job["url"], SHORTS.dest_dir, log=log, cookies=cookies)
                        src = require_video(src)
                        job["file"] = src
                        if not job.get("name"):
                            job["name"] = os.path.basename(src)
                        job["status"] = "done"
                        log(f"[OK] tai xong {os.path.basename(src)}")
                except Exception as e:        # noqa: BLE001 - 1 job loi khong keo sap worker
                    job["status"] = "error"
                    job["error"] = str(e)
                    log(f"[LOI] {e}")
        finally:
            SHORTS.stop()

    threading.Thread(target=runner, daemon=True).start()


def _current_user(request):
    """{username, role} tu cookie phien, hoac None neu chua/het dang nhap."""
    uname = SESS.get(request.cookies.get("mkv_sess"))
    u = USERS.get(uname) if uname else None
    # UserStore.get() van tra ve dict cho tai khoan bi khoa (chi verify() moi
    # chan dang nhap moi). Neu khong loc o day thi "khoa tai khoan" khong duoi
    # duoc phien dang mo — nguoi bi khoa van dung tiep den khi phien het han.
    if u and u.get("disabled"):
        return None
    return u


async def _sent_csrf(request):
    """Token client gui len: uu tien header (fetch), roi den field form."""
    header = request.headers.get(security.CSRF_HEADER)
    if header:
        return header
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype in ("application/x-www-form-urlencoded", "multipart/form-data"):
        # Phai goi body() TRUOC form(): Starlette parse form qua stream(), va
        # neu stream bi tieu thu ma _body chua duoc cache thi middleware base se
        # day body RONG xuong route (route se 422). Goi body() truoc lam _body
        # duoc cache, sau do stream() phat lai duoc cho ca ta lan route.
        try:
            await request.body()
            form = await request.form()
        except Exception:        # noqa: BLE001 - body hong thi coi nhu thieu token
            return None
        return form.get(security.CSRF_FIELD)
    return None


def _finish(request, response, csrf_token, need_cookie):
    """Gan cookie CSRF (neu chua co) + header bao mat cho moi response."""
    if need_cookie:
        response.set_cookie(security.CSRF_COOKIE, csrf_token, httponly=False,
                            samesite="lax", secure=request.url.scheme == "https",
                            path="/")
    security.apply_security_headers(response.headers,
                                    https=request.url.scheme == "https")
    return response


@app.middleware("http")
async def _guard(request: Request, call_next):
    # API bang giao may-may: xac thuc bang token rieng trong header, khong dung
    # cookie -> trinh duyet khong the tu dong gui ho, nen khong can CSRF.
    if request.url.path.startswith("/api/handoff/"):
        expected = str(cfg.get("handoff_token") or "")
        supplied = request.headers.get("x-mkv-handoff-token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            return PlainTextResponse("handoff token khong hop le", status_code=401)
        resp = await call_next(request)
        security.apply_security_headers(resp.headers,
                                        https=request.url.scheme == "https")
        return resp

    # /metrics: cho phep may quet dung chinh handoff_token thay vi cookie phien
    # (khong bay them mot secret moi chi de scrape).
    if request.url.path == "/metrics":
        expected = str(cfg.get("handoff_token") or "")
        supplied = request.headers.get("x-mkv-handoff-token", "")
        if expected and supplied and hmac.compare_digest(expected, supplied):
            resp = await call_next(request)
            security.apply_security_headers(resp.headers,
                                            https=request.url.scheme == "https")
            return resp
        # khong co token hop le -> kiem tra phien dang nhap nhu binh thuong

    cookie_token = request.cookies.get(security.CSRF_COOKIE)
    csrf_token = cookie_token or security.new_csrf_token()
    request.state.csrf_token = csrf_token     # template doc de dien vao form

    user = _current_user(request)
    request.state.user = user            # route doc qua request.state.user
    if request.url.path not in _PUBLIC and user is None:
        return _finish(request, RedirectResponse("/login", status_code=302),
                       csrf_token, not cookie_token)

    if request.method not in security.SAFE_METHODS and not security.csrf_ok(
            cookie_token, await _sent_csrf(request)):
        return _finish(request, PlainTextResponse(
            "CSRF token thieu hoac khong khop; tai lai trang roi thu lai.",
            status_code=403), csrf_token, not cookie_token)

    resp = await call_next(request)
    return _finish(request, resp, csrf_token, not cookie_token)


# Dang ky SAU _guard => chay NGOAI _guard, nen ghi log duoc ca request bi chan
# (302 chua dang nhap, 403 sai CSRF) chu khong chi request vao duoc route.
@app.middleware("http")
async def _access_log(request: Request, call_next):
    rid = request.headers.get("x-request-id") or _secrets.token_hex(8)
    token = logging_setup.request_id_var.set(rid)
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
    except Exception:
        logger.exception("request loi", extra={"method": request.method,
                                               "path": request.url.path})
        logging_setup.request_id_var.reset(token)
        raise
    ms = (time.perf_counter() - t0) * 1000
    user = getattr(request.state, "user", None) or {}
    # Muc log theo ket qua: 5xx la ERROR, 4xx la WARNING, con lai INFO — de
    # `journalctl -p warning` loc ra ngay cai dang hong.
    level = (logging.ERROR if resp.status_code >= 500
             else logging.WARNING if resp.status_code >= 400 else logging.INFO)
    logger.log(level, "%s %s -> %s", request.method, request.url.path, resp.status_code,
               extra={"method": request.method, "path": request.url.path,
                      "status": resp.status_code, "duration_ms": round(ms, 1),
                      "user": user.get("username") or "-"})
    resp.headers.setdefault("X-Request-ID", rid)
    logging_setup.request_id_var.reset(token)
    return resp


def _require_admin(request):
    """None neu la admin; nguoc lai tra response 403 de route return luon."""
    u = getattr(request.state, "user", None)
    if not u or u.get("role") != "admin":
        return PlainTextResponse("Chi admin moi vao duoc trang nay.", status_code=403)
    return None


def _log(msg):
    with _lock:
        _job["log"].append(str(msg))


def _inbox_files():
    d = cfg["inbox_dir"]
    if not os.path.isdir(d):
        return []
    exts = tuple(cfg["watch_ext"])
    return sorted(f for f in os.listdir(d) if f.lower().endswith(exts))


def _message(message, link_href="/", link_text="« ve", status_code=200):
    """Trang thong bao 1 the. Noi dung duoc Jinja escape -> an toan voi loi tu ffmpeg."""
    return HTMLResponse(
        templating.render("message.html", message=message,
                          link_href=link_href, link_text=link_text),
        status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Trang mac dinh: tai video ngan tu Threads, Instagram va TikTok."""
    return HTMLResponse(_web("shorts.html"))


@app.get("/queue-ui", response_class=HTMLResponse)
def queue_page(request: Request):
    """Dashboard pipeline MKV cu, tach khoi landing tai video ngan."""
    return HTMLResponse(_web("dashboard.html"))


@app.get("/classic", response_class=HTMLResponse)
def home_classic(request: Request):
    files = _inbox_files()
    running = _job["running"]
    snap = Q.snapshot()
    pend = snap["pending"]
    return HTMLResponse(templating.render(
        "classic.html",
        user=getattr(request.state, "user", None) or {},
        csrf_token=getattr(request.state, "csrf_token", ""),
        files=files,
        inbox_dir=cfg["inbox_dir"],
        upload_on=cfg.get("upload", True),
        running=running,
        current=snap["current"],
        pending=pend,
        history=list(reversed(snap["history"])),
        queue_log=snap["log"][-120:],
        job_log=_job["log"][-120:],
        poll=bool(running or snap["running"] or pend),
    ))


@app.post("/analyze", response_class=HTMLResponse)
def analyze(file: str = Form(...)):
    src = os.path.join(cfg["inbox_dir"], file)
    try:
        p = pipeline.analyze_file(src, cfg)
    except Exception as e:        # noqa: BLE001 - loi ffmpeg/parse hien thi cho nguoi dung
        return _message(f"Loi: {e}")
    return HTMLResponse(templating.render(
        "analyze.html",
        base=p["base"], res=p["res"], year=p["year"],
        outputs=[{"lang": o["lang"], "ch": o["ch"],
                  "out_name": os.path.basename(o["out"]),
                  "srt_name": os.path.basename(o["srt"]) if o["srt"] else ""}
                 for o in p["outputs"]],
    ))


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
            return _message("Dang co tac vu chay.", link_text="ve")
        _job.update(running=True, log=[], file=file)
    src = os.path.join(cfg["inbox_dir"], file)
    threading.Thread(target=_worker, args=(src, upload is not None), daemon=True).start()
    return _message("Da bat dau.", link_text="Theo doi tien trinh »")


@app.get("/status")
def status():
    return {"running": _job["running"], "log": _job["log"][-200:]}


def _disk_free_gb():
    _ensure_runtime_dirs()
    d = cfg.get("downloads_dir") or cfg.get("inbox_dir", "inbox")
    try:
        return round(resources.free_gb(d), 1)
    except OSError:
        return None


@app.get("/healthz")
def healthz():
    """Cong khai, co tinh toi gian: chi 'con phuc vu duoc khong' + 200/503.

    Khong dat sau dang nhap vi day la thu systemd/uptime-check goi; cung khong
    tra chi tiet hang doi de trang cong khai nay khong lo thong tin van hanh —
    chi tiet nam o /metrics (co xac thuc).
    """
    body, code = observability.health(
        ffmpeg_ok=ffmpeg_helper.available(),
        disk_free_gb=_disk_free_gb(),
        min_free_gb=float(cfg.get("min_free_gb", 0) or 0),
        queue=Q.snapshot(),
        uptime_seconds=time.time() - _STARTED_AT,
    )
    return JSONResponse({k: v for k, v in body.items() if k != "checks"},
                        status_code=code)


@app.get("/metrics")
def metrics():
    """Phoi bay Prometheus. Can dang nhap HOAC header x-mkv-handoff-token."""
    return PlainTextResponse(observability.render_prometheus(
        ffmpeg_ok=ffmpeg_helper.available(),
        disk_free_gb=_disk_free_gb(),
        queue=Q.snapshot(),
        shorts=SHORTS.snapshot(),
        sessions=len(SESS),
        worker_allowed=_worker_allowed(),
        node_id=cfg.get("node_id", "local"),
        uptime_seconds=time.time() - _STARTED_AT,
    ), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/enqueue", response_class=HTMLResponse)
def enqueue(links: str = Form(...)):
    n = Q.add_many(links)
    if n:
        _start_drain()
    return _message(f"Da them {n} link vao hang doi.",
                    link_text="Theo doi tien trinh »")


@app.post("/enqueue-torrent")
async def enqueue_torrent(files: list[UploadFile] = File(...)):
    """Nhan file .torrent upload tu trinh duyet -> luu vao work/torrents/ -> vao hang doi.
    fetch.is_torrent() nhan duong dan ket thuc .torrent, aria2c doc truc tiep file local."""
    tor_dir = os.path.join(cfg.get("work_dir", "work"), "torrents")
    os.makedirs(tor_dir, exist_ok=True)
    n = 0
    for f in files:
        name = os.path.basename(f.filename or "")
        if not name.lower().endswith(".torrent"):
            continue
        data = await f.read()
        if not data:
            continue
        path = os.path.join(tor_dir, name)
        if os.path.exists(path):                       # tranh ghi de khi trung ten
            stem, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(path):
                path = os.path.join(tor_dir, f"{stem}_{i}{ext}")
                i += 1
        with open(path, "wb") as out:
            out.write(data)
        Q.add(path)
        n += 1
    if n:
        _start_drain()
    return {"ok": True, "added": n}


@app.get("/queue")
def queue():
    snap = Q.snapshot()
    _ensure_runtime_dirs()
    dl = cfg.get("downloads_dir") or cfg.get("inbox_dir", "inbox")
    snap["disk_free_gb"] = round(resources.free_gb(dl), 1)
    snap["node"] = cfg.get("node_id", "local")
    snap["worker_allowed"] = _worker_allowed()
    return snap


@app.get("/api/handoff/export")
def handoff_export():
    """Bundle chi gom URL/magnet; khong day video lon hay cookie local qua Tailscale."""
    return {"version": 1, "source": cfg.get("node_id", "local"),
            "jobs": Q.export_pending()}


@app.post("/api/handoff/import")
async def handoff_import(request: Request):
    data = await request.json()
    ids = Q.import_jobs((data or {}).get("jobs") or [])
    if ids:
        _start_drain()
    return {"ok": True, "accepted": ids, "node": cfg.get("node_id", "local")}


@app.post("/api/handoff/ack")
async def handoff_ack(request: Request):
    data = await request.json()
    removed = Q.acknowledge((data or {}).get("ids") or [])
    return {"ok": True, "removed": removed}


@app.get("/shorts", response_class=HTMLResponse)
def shorts_page(request: Request):
    # Giu URL cu cho bookmark, nhung chi co mot URL canonical cho giao dien tai video.
    return RedirectResponse("/", status_code=302)


@app.post("/shorts/enqueue")
def shorts_enqueue(url: str = Form(...), mode: str = Form("download")):
    """Them link video ngan vao hang doi short. mode: download (giu file) | upload (YouTube Short)."""
    n = 0
    for line in (url or "").splitlines():
        if SHORTS.add(line, mode):
            n += 1
    if n:
        _start_shorts()
    return {"ok": True, "added": n}


@app.post("/shorts/grab")
def shorts_grab(media_url: str = Form(...), referer: str = Form(""), mode: str = Form("download"),
                label: str = Form("")):
    """Tai 1 clip CU THE da chon tu danh sach (probe). mode: download | upload."""
    if mode not in ("download", "upload"):
        mode = "download"
    job = SHORTS.add(referer or media_url, mode, media_url=media_url,
                     referer=referer or None, label=label)
    if job:
        _start_shorts()
    return {"ok": bool(job), "id": job["id"] if job else None}


@app.post("/shorts/grab-batch")
def shorts_grab_batch(source_url: str = Form(...), items: str = Form(...)):
    """Tai cac candidate da tim thay va dong goi thanh mot ZIP duy nhat."""
    try:
        raw_items = json.loads(items)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Danh sach video khong hop le") from exc
    if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 100:
        raise HTTPException(status_code=400, detail="Chi ho tro 1-100 video moi lan")
    clean_items = []
    for item in raw_items:
        if not isinstance(item, dict) or not str(item.get("url") or "").startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Link video khong hop le")
        clean_items.append({
            "url": str(item["url"]),
            "referer": str(item.get("referer") or source_url),
            "label": str(item.get("label") or "")[:30],
        })
    profile = fetch.threads_profile_target(source_url)
    account = profile[0] if profile else "videos"
    filename = fetch.safe_name(f"threads_{account}_videos.zip")
    job = SHORTS.add(source_url, "batch", label=filename, media_items=clean_items)
    if job:
        _start_shorts()
    return {"ok": bool(job), "id": job["id"] if job else None, "count": len(clean_items)}


@app.get("/shorts/preview")
def shorts_preview(request: Request, url: str, referer: str = ""):
    """Phat thu 1 clip trong UI: proxy stream tu CDN (kem UA/referer) -> tranh CORS/chan
    referer khi nhung <video> truc tiep. Ho tro Range de tua. Sau khi xem moi tai."""
    import urllib.request

    from fastapi.responses import StreamingResponse
    # Server tu di tai roi tra noi dung ve trinh duyet -> day la SSRF neu khong
    # chan: mot tai khoan `user` co the doc 127.0.0.1:9222 (Chrome CDP, dieu
    # khien duoc ca trinh duyet), metadata cloud, hay dich vu bat ky trong LAN.
    try:
        security.assert_public_http_url(url)
    except security.UnsafeURL as e:
        return PlainTextResponse(f"url khong hop le: {e}", status_code=400)
    headers = {"User-Agent": fetch.UA}
    if referer:
        headers["Referer"] = referer
    rng = request.headers.get("range")
    if rng:
        headers["Range"] = rng
    try:
        up = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30)  # noqa: S310
    except Exception as e:        # noqa: BLE001
        return PlainTextResponse(f"khong phat duoc: {e}", status_code=502)
    out_headers = {}
    for h in ("Content-Length", "Content-Range", "Accept-Ranges"):
        v = up.headers.get(h)
        if v:
            out_headers[h] = v
    ctype = up.headers.get("Content-Type") or "video/mp4"

    def gen():
        try:
            while True:
                b = up.read(65536)
                if not b:
                    break
                yield b
        finally:
            up.close()

    return StreamingResponse(gen(), status_code=up.status, media_type=ctype, headers=out_headers)


@app.get("/shorts/status")
def shorts_status():
    return SHORTS.snapshot()


def _short_download_name(job: dict, path: str) -> str:
    """Ten de doc cho file CDN: platform_user_postcode_resolution.ext."""
    parsed = urllib.parse.urlparse(job.get("url") or "")
    host = (parsed.hostname or "").lower()
    platform = next((p for p in ("threads", "instagram", "tiktok") if p in host), "video")
    segments = [urllib.parse.unquote(s) for s in parsed.path.split("/") if s]
    account = next((s.lstrip("@") for s in segments if s.startswith("@")), "")
    code = ""
    for marker in ("post", "reel", "video"):
        if marker in segments and segments.index(marker) + 1 < len(segments):
            code = segments[segments.index(marker) + 1]
            break
    label = str(job.get("name") or "").replace("×", "x")
    if not re.fullmatch(r"\d+x\d+", label):
        label = ""
    ext = os.path.splitext(path)[1].lower()
    if ext not in fetch.VIDEO_EXTS:
        ext = ".mp4"
    parts = [p for p in (platform, account, code, label) if p]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", "_".join(parts)).strip("-_.") or "video"
    return fetch.safe_name(stem[:180] + ext)


@app.get("/shorts/file/{jid}")
def shorts_file(jid: int):
    """Tai file clip da-tai ve may nguoi dung (chi job download da xong)."""
    job = SHORTS.get(jid)
    if not job or job.get("mode") not in ("download", "batch") or job.get("status") != "done":
        return PlainTextResponse("file chua san sang", status_code=404)
    path = job.get("file") or ""
    if not path or not os.path.isfile(path):
        return PlainTextResponse("khong tim thay file", status_code=404)
    import mimetypes
    filename = (fetch.safe_name(job.get("name") or "videos.zip")
                if job.get("mode") == "batch" else _short_download_name(job, path))
    # iOS/in-app browser se mo player neu nhan video/mp4, du Content-Disposition la
    # attachment. Ep video ve binary download + nosniff de nut "Luu vao Tep" tai file.
    media_type = (mimetypes.guess_type(filename)[0] or "application/zip"
                  if job.get("mode") == "batch" else "application/octet-stream")
    return FileResponse(path, filename=filename, media_type=media_type,
                        headers={"X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "private, no-store"})


@app.post("/shorts/delete")
def shorts_delete(jid: int = Form(...)):
    """Xoa 1 job short khoi danh sach + xoa file da tai (neu co)."""
    job = SHORTS.get(jid)
    if job and job.get("mode") in ("download", "batch") and job.get("file"):
        try:
            if os.path.isfile(job["file"]):
                os.remove(job["file"])
        except OSError:
            pass
    return {"ok": SHORTS.remove(jid)}


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
    "auto_fetch_subs", "sub_langs", "subs_repo_dir", "subs_repo_push",
    "subdl_api_key", "opensubtitles_api_key", "opensubtitles_user", "opensubtitles_pass",
    "tmdb_api_key", "tmdb_thumbnail",
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
        # Moi hanh dong thu hoi quyen deu phai HUY PHIEN dang mo, neu khong
        # nguoi bi khoa/xoa/doi mat khau van dung tiep bang cookie cu.
        if action == "disable":
            USERS.set_disabled(username, True)
            msg = f"Da khoa {username} ({SESS.destroy_all(username)} phien bi dong)"
        elif action == "enable":
            USERS.set_disabled(username, False)
            msg = f"Da mo khoa {username}"
        elif action == "role":
            USERS.set_role(username, value)
            SESS.destroy_all(username)      # doi quyen -> bat dang nhap lai
            msg = f"{username} -> {value}"
        elif action == "delete":
            USERS.remove(username)
            SESS.destroy_all(username)
            msg = f"Da xoa {username}"
        elif action == "reset":
            if not value:
                raise ValueError("mat khau moi rong")
            USERS.change_password(username, value)
            SESS.destroy_all(username)
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
    logging_setup.configure()            # JSON khi chay duoi systemd, text khi chay tay
    _ensure_runtime_dirs()
    logger.info("mkvtools-gui khoi dong", extra={"node": cfg.get("node_id", "local")})
    if not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe.")
    auth.bootstrap_admin(USERS)          # lan dau: tao admin (env hoac mat khau ngau nhien in ra)
    threading.Thread(target=_queue_scheduler, daemon=True).start()
    uvicorn.run(app, host=os.environ.get("MKV_GUI_HOST", "127.0.0.1"),
                port=int(os.environ.get("MKV_GUI_PORT", "8800")))


if __name__ == "__main__":
    main()
