"""
GUI web local (fallback khi muon lam tay). Chay:  python -m mkvtools.webui
Mo http://127.0.0.1:8800 . Liet ke file trong inbox/, phan tich, tach + (tuy chon) upload.
Chay tac vu o thread nen, log poll qua /status.
"""
import os
import threading

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from . import config, ffmpeg_helper, pipeline
from . import uploader as up

cfg = config.load()
app = FastAPI(title="mkvtools GUI")

_job = {"running": False, "log": [], "file": None}
_lock = threading.Lock()


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
    return page(f"""
<div class=card>
<p class=muted>Thu muc inbox: <code>{cfg['inbox_dir']}</code> — {len(files)} file</p>
<form method=post action=/analyze>
  <select name=file>{opts}</select>
  <button {'disabled' if running else ''}>Phan tich</button>
</form>
<form method=post action=/run style=margin-top:10px>
  <select name=file>{opts}</select>
  <label><input type=checkbox name=upload {up_checked}> upload YouTube</label>
  <button {'disabled' if running else ''}>Chay</button>
</form>
</div>
<div class=card><b>Trang thai</b> {'(dang chay...)' if running else ''}
<pre id=log>{chr(10).join(_job['log'][-200:]) or '(chua co)'}</pre></div>
<script>if({str(running).lower()})setTimeout(()=>location.reload(),2000)</script>
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
        yt = up.get_service(cfg["client_secret"], cfg["token_file"]) if do_upload else None
        pipeline.process_file(src, cfg, yt=yt, do_upload=do_upload, log=_log)
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


def main():
    import uvicorn
    if not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe.")
    uvicorn.run(app, host=os.environ.get("MKV_GUI_HOST", "127.0.0.1"),
                port=int(os.environ.get("MKV_GUI_PORT", "8800")))


if __name__ == "__main__":
    main()
