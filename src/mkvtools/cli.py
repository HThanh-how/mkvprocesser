"""CLI: phan tich / tach / tach+upload / theo doi thu muc."""
import argparse
import os
import time
import traceback

from . import config, ffmpeg_helper, idempotency, pipeline, titlematch


def _service(cfg):
    from . import uploader as up  # nap khi can -> probe/split khong can google libs
    return up.get_service(cfg["client_secret"], cfg["token_file"])


def cmd_probe(cfg, args):
    p = pipeline.analyze_file(os.path.abspath(args.file), cfg)
    print(f"{p['base']}  [{p['res']}{(' ' + p['year']) if p['year'] else ''}]")
    for o in p["outputs"]:
        sub = os.path.basename(o["srt"]) if o["srt"] else "khong co sub"
        print(f"  - {o['lang'] or '?'} ({o['ch']}ch) -> {os.path.basename(o['out'])} | {sub}")


def cmd_once(cfg, args):
    yt = _service(cfg) if (cfg.get("upload", True) and not args.no_upload) else None
    # `once` la lenh tay cho 1 file -> luon chay (force) nhung van ghi lai de watch khong lam lai
    pipeline.process_file(os.path.abspath(args.file), cfg, yt=yt,
                          do_upload=not args.no_upload, force=True)


def cmd_watch(cfg, args):
    inbox = cfg["inbox_dir"]
    os.makedirs(inbox, exist_ok=True)
    yt = _service(cfg) if cfg.get("upload", True) else None
    exts = tuple(cfg["watch_ext"])
    store = idempotency.ProcessedStore(cfg["state_file"]) if cfg.get("skip_processed", True) else None
    extra = f" (da nho {len(store)} file)" if store is not None else ""
    print(f"Theo doi {inbox} ...{extra} (Ctrl+C de dung)")
    seen, cache = set(), {}
    while True:
        for name in sorted(os.listdir(inbox)):
            p = os.path.join(inbox, name)
            if not name.lower().endswith(exts) or p in seen:
                continue
            sz = os.path.getsize(p)
            time.sleep(3)
            if not os.path.exists(p) or os.path.getsize(p) != sz:
                continue
            seen.add(p)
            try:
                pipeline.process_file(p, cfg, yt=yt, pl_cache=cache, store=store)
            except Exception:
                print("LOI:", p)
                traceback.print_exc()
        time.sleep(int(cfg["poll_seconds"]))


def cmd_sync_titles(cfg, args):
    """Keo tua cac video da upload tren YouTube vao index chong trung (re, ~1 unit/50)."""
    from . import uploader as up
    yt = _service(cfg)
    titles = up.list_uploaded_titles(yt)
    store = idempotency.ProcessedStore(cfg["state_file"])
    added = 0
    for t in titles:
        tk = titlematch.title_key(t)
        if tk and not store.has_title(tk):
            store.add(f"yt:{tk}", {"title_key": tk, "name": t, "source": "youtube"})
            added += 1
    print(f"YouTube: {len(titles)} video. Them {added} tua moi vao index ({cfg['state_file']}).")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mkvtools", description="Tach MKV nhieu audio + upload YouTube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe", help="phan tich, in track + ke hoach")
    sp.add_argument("file")
    so = sub.add_parser("once", help="xu ly 1 file")
    so.add_argument("file")
    so.add_argument("--no-upload", action="store_true")
    sub.add_parser("watch", help="theo doi inbox/")
    sub.add_parser("sync-titles", help="keo tua da upload tren YouTube vao index chong trung")
    args = ap.parse_args(argv)
    if args.cmd != "sync-titles" and not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe. Cai ffmpeg hoac de vao ffmpeg_bin/.")
    cfg = config.load()
    {"probe": cmd_probe, "once": cmd_once, "watch": cmd_watch,
     "sync-titles": cmd_sync_titles}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
