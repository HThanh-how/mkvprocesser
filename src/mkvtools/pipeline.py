"""Ghep: plan -> split -> (upload + caption + playlist). Dung chung cho CLI lan GUI."""
import os
import shutil

from . import splitter
from . import uploader as up


def title_for(cfg, base, out):
    return cfg["title_template"].format(base=base, lang=out["lang"] or "audio",
                                        label=out["label"])


def analyze_file(src, cfg, log=print):
    """Chi phan tich + len ke hoach (cho GUI xem truoc, khong chay ffmpeg)."""
    return splitter.plan(src, cfg["work_dir"], cfg["subtitle_mode"], cfg["container"])


def process_file(src, cfg, yt=None, pl_cache=None, do_upload=None, log=print):
    """Tach + (tuy chon) upload. yt=None -> chi tach. do_upload override cfg['upload']."""
    pl_cache = pl_cache if pl_cache is not None else {}
    do_upload = cfg.get("upload", True) if do_upload is None else do_upload
    os.makedirs(cfg["work_dir"], exist_ok=True)
    p = splitter.plan(src, cfg["work_dir"], cfg["subtitle_mode"], cfg["container"])
    base, outs = p["base"], p["outputs"]
    log(f"[{os.path.basename(src)}] -> {len(outs)} ban audio")
    if not outs:
        log("  (!) khong co audio track")
        return p

    pid = None
    if do_upload and yt and cfg["make_playlist"]:
        pid = up.get_or_create_playlist(yt, pl_cache,
                                        cfg["playlist_template"].format(base=base),
                                        privacy=cfg["privacy"], log=log)
    for out in outs:
        splitter.execute(src, out, log=log)
        if do_upload and yt:
            vid = up.upload_video(yt, out["out"], title_for(cfg, base, out),
                                  description=cfg.get("description", ""),
                                  tags=cfg.get("tags", []), privacy=cfg["privacy"],
                                  category_id=cfg.get("category_id", 22),
                                  language=out["lang"] or None, log=log)
            if out["srt"]:
                try:
                    up.upload_caption(yt, vid, out["srt"],
                                      language=out["lang"] or cfg["default_caption_lang"],
                                      name=out["label"], log=log)
                except Exception as e:
                    log(f"  (!) loi up sub: {e}")
            if pid:
                up.add_to_playlist(yt, pid, vid, log=log)
            if cfg.get("cleanup_outputs", True):
                for f in (out["out"], out["srt"]):
                    if f and os.path.exists(f):
                        os.remove(f)
    if do_upload and yt and cfg.get("done_dir"):
        os.makedirs(cfg["done_dir"], exist_ok=True)
        shutil.move(src, os.path.join(cfg["done_dir"], os.path.basename(src)))
    log(f"[{os.path.basename(src)}] XONG")
    return p
