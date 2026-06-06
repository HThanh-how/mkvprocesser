"""CLI: phan tich / tach / tach+upload / theo doi thu muc."""
import argparse
import os
import time
import traceback

from . import config, ffmpeg_helper, idempotency, pipeline, titlematch


def _service(cfg):
    from . import uploader as up  # nap khi can -> probe/split khong can google libs
    return up.get_service(cfg["client_secret"], cfg["token_file"], proxy=cfg.get("proxy", ""))


def cmd_probe(cfg, args):
    p = pipeline.analyze_file(os.path.abspath(args.file), cfg)
    print(f"{p['base']}  [{p['res']}{(' ' + p['year']) if p['year'] else ''}]")
    for o in p["outputs"]:
        print(f"  - audio {o['lang'] or '?'} ({o['ch']}ch, {o['acodec']}) -> {os.path.basename(o['out'])}")
    subs = p.get("subs", [])
    if subs:
        print(f"  + {len(subs)} phu de chu (up het): " + ", ".join(s["lang"] or "?" for s in subs))
    else:
        print("  (khong co phu de chu de up)")


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


def cmd_fetch(cfg, args):
    """Tai 1 link ve -> tach + (tuy chon) upload -> xoa nguon (rotation o nho)."""
    from . import fetch
    yt = _service(cfg) if (cfg.get("upload", True) and not args.no_upload) else None
    dl = cfg.get("downloads_dir") or cfg["inbox_dir"]
    cookies = args.cookies or cfg.get("cookies_file") or None
    print(f"Tai: {args.url}")
    src = fetch.fetch(args.url, dl, cookies=cookies)
    rcfg = {**cfg, "delete_source": not args.keep}
    pipeline.process_file(src, rcfg, yt=yt, do_upload=not args.no_upload, force=args.force)


def cmd_resolve(cfg, args):
    """Chi DO link bat duoc media gi (khong tai) -> in tang + URL media."""
    from . import fetch
    cookies = args.cookies or cfg.get("cookies_file") or None
    r = fetch.resolve(args.url, cookies=cookies)
    if not r.get("ok"):
        raise SystemExit("KHONG bat duoc media (co the player JS chan, CAPTCHA, hoac DRM).")
    print(f"OK  tang={r['tier']}  kind={r.get('kind')}")
    if r.get("title"):
        print(f"  tua: {r['title']}")
    print(f"  media: {r.get('media')}")
    for c in r.get("candidates", [])[1:]:
        print(f"  + {c}")


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


def cmd_organize(cfg, args):
    """Don kenh: ep private + add moi video vao playlist tong (+ playlist phim)."""
    import re

    from googleapiclient.errors import HttpError

    from . import uploader as up
    yt = _service(cfg)
    vids = up.list_uploaded_videos(yt, limit=2000)
    print(f"Tong {len(vids)} video tren kenh.")
    cache = up.list_playlists(yt)                          # {title: id} -> tai dung, khong tao trung
    master = args.master or cfg.get("master_playlist") or "MKVTOOLS - Tat ca"
    master_id = up.get_or_create_playlist(yt, cache, master, privacy="private")
    master_have = up.playlist_video_ids(yt, master_id)
    movie_have = {}
    struct = re.compile(r"^(?:4K|2K|FHD|HD|SD)_[A-Z]{2,4}_((?:19|20)\d{2})_(.+)$")
    npriv = nmaster = nmovie = 0
    budget = args.budget if args.budget is not None else cfg.get("organize_budget", 2000)
    budget = max(0, budget)             # gioi han quota/lan (0 = khong gioi han)
    spent = 80                          # uoc luong quota cho cac lenh doc ban dau
    reason = ""
    for v in vids:
        if budget and spent >= budget:
            reason = "budget"
            break
        try:
            if not args.keep_privacy and v["privacy"] != "private" and up.set_privacy(yt, v["id"], "private"):
                npriv += 1
                spent += 51
                print(f"  -> private: {v['title'][:55]}")
            if v["id"] not in master_have:
                up.add_to_playlist(yt, master_id, v["id"])
                master_have.add(v["id"])
                nmaster += 1
                spent += 50
            if not args.no_per_movie:
                m = struct.match(v["title"])
                if m:
                    pl = f"{m.group(2).strip()} ({m.group(1)})"
                    if pl not in cache:
                        spent += 50
                    pid = up.get_or_create_playlist(yt, cache, pl, privacy="private")
                    if pid not in movie_have:
                        movie_have[pid] = up.playlist_video_ids(yt, pid)
                        spent += 1
                    if v["id"] not in movie_have[pid]:
                        up.add_to_playlist(yt, pid, v["id"])
                        movie_have[pid].add(v["id"])
                        nmovie += 1
                        spent += 50
        except HttpError as e:
            if e.resp.status == 403 or "quota" in str(e).lower():
                reason = "quota"
                break
            raise
    if reason == "budget":
        print(f"  (!) Dat han muc ~{budget} quota/lan -> dung (de danh quota cho upload). Chay lai de tiep.")
    elif reason == "quota":
        print("  (!) Het quota YouTube -> dung. Chay lai sau de tiep.")
    tag = "DUNG (resume)" if reason else "XONG"
    print(f"{tag}: ~{spent} quota | private {npriv} | +tong {nmaster} | +phim {nmovie}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mkvtools", description="Tach MKV nhieu audio + upload YouTube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe", help="phan tich, in track + ke hoach")
    sp.add_argument("file")
    so = sub.add_parser("once", help="xu ly 1 file")
    so.add_argument("file")
    so.add_argument("--no-upload", action="store_true")
    sub.add_parser("watch", help="theo doi inbox/")
    sf = sub.add_parser("fetch", help="tai 1 link ve roi tach + upload (xoay vong dia)")
    sf.add_argument("url")
    sf.add_argument("--no-upload", action="store_true")
    sf.add_argument("--keep", action="store_true", help="giu file nguon (khong xoa sau upload)")
    sf.add_argument("--force", action="store_true", help="bo qua chong-trung")
    sf.add_argument("--cookies", help="file cookies.txt cho trang can dang nhap")
    sr = sub.add_parser("resolve", help="chi DO link bat duoc media gi (khong tai)")
    sr.add_argument("url")
    sr.add_argument("--cookies", help="file cookies.txt cho trang can dang nhap")
    sub.add_parser("sync-titles", help="keo tua da upload tren YouTube vao index chong trung")
    so = sub.add_parser("organize", help="don kenh: ep private + add video vao playlist tong/phim")
    so.add_argument("--master", help="ten playlist tong (mac dinh: cfg hoac 'MKVTOOLS - Tat ca')")
    so.add_argument("--keep-privacy", action="store_true", help="khong ep private")
    so.add_argument("--no-per-movie", action="store_true", help="chi playlist tong, khong tao playlist phim")
    so.add_argument("--budget", type=int, default=None,
                    help="gioi han quota moi lan (mac dinh: cfg organize_budget; 0 = khong gioi han)")
    args = ap.parse_args(argv)
    if args.cmd not in ("sync-titles", "resolve", "organize") and not ffmpeg_helper.available():
        raise SystemExit("Khong tim thay ffmpeg/ffprobe. Cai ffmpeg hoac de vao ffmpeg_bin/.")
    cfg = config.load()
    {"probe": cmd_probe, "once": cmd_once, "watch": cmd_watch, "fetch": cmd_fetch,
     "resolve": cmd_resolve, "sync-titles": cmd_sync_titles, "organize": cmd_organize}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
