"""
GUI web local (fallback khi muon lam tay). Chay:  python -m mkvtools.webui
Mo http://127.0.0.1:8800 . Liet ke file trong inbox/, phan tich, tach + (tuy chon) upload.
Chay tac vu o thread nen, log poll qua /status.
"""
import os
import threading

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from . import config, fetch, ffmpeg_helper, idempotency, jobs, pipeline

cfg = config.load()
app = FastAPI(title="mkvtools GUI")

# Auth tuy chon: dat MKV_GUI_TOKEN de bao ve khi mo ra 0.0.0.0 (vd qua Docker).
# Khong dat -> khong chan (mac dinh chay localhost, giu nguyen hanh vi cu).
_TOKEN = os.environ.get("MKV_GUI_TOKEN", "")

_job = {"running": False, "log": [], "file": None}
_lock = threading.Lock()

# Hang doi link: dan URL -> tu tai -> tach -> upload -> xoay vong dia (xoa nguon).
Q = jobs.JobQueue()


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

            jobs.drain(Q, rcfg, fetch_fn=fetch.fetch, process_fn=process_fn)
        except Exception as e:                          # noqa: BLE001
            Q.say(f"LOI worker: {e}")
        finally:
            Q.stop()             # luoi an toan neu thoat bat thuong (binh thuong pop() da tat)

    threading.Thread(target=runner, daemon=True).start()


def token_ok(expected: str, supplied) -> bool:
    """True neu khong bat auth (expected rong), hoac token khop."""
    return (not expected) or (supplied == expected)


@app.middleware("http")
async def _auth(request, call_next):
    if _TOKEN:
        supplied = request.query_params.get("token") or request.cookies.get("mkv_token")
        if not token_ok(_TOKEN, supplied):
            from starlette.responses import PlainTextResponse
            return PlainTextResponse("Unauthorized: them ?token=... vao URL", status_code=401)
        resp = await call_next(request)
        if request.query_params.get("token") == _TOKEN:  # nho token qua cookie
            resp.set_cookie("mkv_token", _TOKEN, httponly=True, samesite="lax")
        return resp
    return await call_next(request)


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
def home():
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
    return page(f"""
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
    return Q.snapshot()


def main():
    import uvicorn
    if not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe.")
    uvicorn.run(app, host=os.environ.get("MKV_GUI_HOST", "127.0.0.1"),
                port=int(os.environ.get("MKV_GUI_PORT", "8800")))


if __name__ == "__main__":
    main()
