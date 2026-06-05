"""CLI: phan tich / tach / tach+upload / theo doi thu muc."""
import argparse
import os
import time
import traceback

from . import config, ffmpeg_helper, pipeline
from . import uploader as up


def _service(cfg):
    return up.get_service(cfg["client_secret"], cfg["token_file"])


def cmd_probe(cfg, args):
    p = pipeline.analyze_file(os.path.abspath(args.file), cfg)
    print(f"{p['base']}  [{p['res']}{(' ' + p['year']) if p['year'] else ''}]")
    for o in p["outputs"]:
        sub = os.path.basename(o["srt"]) if o["srt"] else "khong co sub"
        print(f"  - {o['lang'] or '?'} ({o['ch']}ch) -> {os.path.basename(o['out'])} | {sub}")


def cmd_once(cfg, args):
    yt = _service(cfg) if (cfg.get("upload", True) and not args.no_upload) else None
    pipeline.process_file(os.path.abspath(args.file), cfg, yt=yt,
                          do_upload=not args.no_upload)


def cmd_watch(cfg, args):
    inbox = cfg["inbox_dir"]
    os.makedirs(inbox, exist_ok=True)
    yt = _service(cfg) if cfg.get("upload", True) else None
    exts = tuple(cfg["watch_ext"])
    print(f"Theo doi {inbox} ... (Ctrl+C de dung)")
    seen, cache = set(), {}
    while True:
        for name in sorted(os.listdir(inbox)):
            p = os.path.join(inbox, name)
            if not name.lower().endswith(exts) or p in seen:
                continue
            sz = os.path.getsize(p)
            time.sleep(3)
            if os.path.getsize(p) != sz:
                continue
            seen.add(p)
            try:
                pipeline.process_file(p, cfg, yt=yt, pl_cache=cache)
            except Exception:
                print("LOI:", p)
                traceback.print_exc()
        time.sleep(int(cfg["poll_seconds"]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mkvtools", description="Tach MKV nhieu audio + upload YouTube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe", help="phan tich, in track + ke hoach")
    sp.add_argument("file")
    so = sub.add_parser("once", help="xu ly 1 file")
    so.add_argument("file")
    so.add_argument("--no-upload", action="store_true")
    sub.add_parser("watch", help="theo doi inbox/")
    args = ap.parse_args(argv)
    if not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe. Cai ffmpeg hoac de vao ffmpeg_bin/.")
    cfg = config.load()
    {"probe": cmd_probe, "once": cmd_once, "watch": cmd_watch}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
