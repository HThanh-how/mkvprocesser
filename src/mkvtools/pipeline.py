"""Ghep: plan -> split -> (upload + caption + playlist). Dung chung cho CLI lan GUI."""
import os
import re
import shutil

from . import idempotency, metadata, resources, splitter, titlematch


def _meta_kw(p, out=None):
    """Placeholder cho template tieu de/playlist: {base} {title} {res} {year} {lang} {label}.

    {title} = tua DA CHUAN HOA (bo rac ban phat hanh) -> sach, khong phai ten file tho.
    """
    base = p["base"]
    if out and out["lang"]:
        lang = metadata.lang_abbr(out["lang"])
    else:
        lang = (out["label"] if out else "") or ""
    return {
        "base": base,
        "title": titlematch.normalize_title(base).title() or base,
        "res": p.get("res") or "",
        "year": p.get("year") or "",
        "lang": lang,
        "label": (out["label"] if out else "") or "",
    }


def _fmt(tmpl, kw):
    """Dien template + don ngoac/dau rong (vd thieu nam) + cat 100 ky tu (gioi han YouTube)."""
    t = tmpl.format(**kw)
    t = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", "", t)   # bo ngoac rong
    t = re.sub(r"([_|-])\1+", r"\1", t)             # gop dau phan cach lap (vd __ -> _)
    return re.sub(r"\s{2,}", " ", t).strip(" -|_")[:100]


def title_for(cfg, p, out):
    return _fmt(cfg.get("title_template") or "{res}_{lang}_{year}_{title}", _meta_kw(p, out))


def _record(store, sig, tkey, name, outs, res_rank=0, note=""):
    """Ghi vao store de chong trung lan sau (khoa = sig neu co, khong thi theo tua/ten)."""
    if store is None:
        return
    key = sig or (f"title:{tkey}" if tkey else f"name:{name}")
    info = {"name": name, "title_key": tkey, "res_rank": res_rank, "outputs": outs}
    if note:
        info["note"] = note
    store.add(key, info)


def analyze_file(src, cfg, log=print):
    """Chi phan tich + len ke hoach (cho GUI xem truoc, khong chay ffmpeg)."""
    return splitter.plan(src, cfg["work_dir"], cfg["subtitle_mode"], cfg["container"],
                         cfg.get("audio_per_lang", "best"))


def process_file(src, cfg, yt=None, pl_cache=None, do_upload=None, log=print,
                 store=None, force=False):
    """Tach + (tuy chon) upload. yt=None -> chi tach. do_upload override cfg['upload'].

    store : ProcessedStore de chong xu ly trung (None -> tu tao theo cfg neu bat).
    force : bo qua kiem tra da-xu-ly (van ghi lai sau khi xong).
    """
    pl_cache = pl_cache if pl_cache is not None else {}
    do_upload = cfg.get("upload", True) if do_upload is None else do_upload
    up = None
    if do_upload and yt:
        from . import uploader as up  # nap khi can -> cai headless khong keo google libs
    skip_on = cfg.get("skip_processed", True)
    title_on = cfg.get("dedup_by_title", True)
    if store is None and (skip_on or title_on):
        store = idempotency.ProcessedStore(cfg.get("state_file", "work/processed.json"))

    name = os.path.basename(src)
    # (1) Chong trung theo TUA DE (nhe nhat: chi doc ten file, khong dung video).
    #     Phan biet Phan 1/2/3 (tua khac) nhung bat ban re-encode (cung tua).
    tkey = titlematch.title_key(name) if (store is not None and title_on) else ""
    rrank = titlematch.resolution_rank(name) if tkey else 0
    if tkey and not force and store.has_title(tkey):
        old = store.title_res(tkey)
        if cfg.get("upgrade_on_higher_res", True) and rrank > old:
            log(f"[{name}] da co ({tkey}) o {old or '?'}p, ban moi {rrank}p cao hon -> up nang cap")
        else:
            mode = cfg.get("on_title_match", "skip")
            log(f"[{name}] da co theo tua ({tkey}) -> {'bo qua' if mode == 'skip' else 'van xu ly'}")
            if mode == "skip":
                return {"base": os.path.splitext(name)[0], "outputs": [], "skipped": "title"}

    # (2) Chong trung theo NOI DUNG (sha256 dau/cuoi) -> bat file y het tung byte.
    sig = idempotency.file_signature(src) if (store is not None and skip_on) else None
    if sig is not None and not force and store.has(sig):
        log(f"[{name}] da xu ly truoc do -> bo qua")
        return {"base": os.path.splitext(name)[0], "outputs": [], "skipped": True}

    ok, msg = resources.preflight(src, cfg.get("work_dir", "work"),
                                  float(cfg.get("min_free_gb_factor", 1.5)))
    if not ok:
        log(f"  (!) {msg}")

    os.makedirs(cfg["work_dir"], exist_ok=True)
    p = splitter.plan(src, cfg["work_dir"], cfg["subtitle_mode"], cfg["container"],
                      cfg.get("audio_per_lang", "best"))
    outs = p["outputs"]
    log(f"[{name}] -> {len(outs)} ban audio")
    if not outs:
        log("  (!) khong co audio track")
        _record(store, sig, tkey, name, [], res_rank=rrank, note="no-audio")
        return p

    pid = None
    if do_upload and yt and cfg["make_playlist"]:
        pid = up.get_or_create_playlist(
            yt, pl_cache, _fmt(cfg.get("playlist_template") or "{title} ({year})", _meta_kw(p)),
            privacy=cfg["privacy"], log=log)
    mpid = None
    if do_upload and yt and cfg.get("master_playlist"):   # playlist tong (de tim/lay lai)
        mpid = up.get_or_create_playlist(yt, pl_cache, cfg["master_playlist"],
                                         privacy=cfg["privacy"], log=log)

    # Rut TAT CA phu de chu 1 lan (dung chung cho moi video). captions: all (het) | paired (cung lang)
    caps = []
    if cfg.get("subtitle_mode", "caption") in ("caption", "both"):
        for s in p.get("subs", []):
            if splitter.extract_sub(src, s["sidx"], s["srt"], log=log):
                caps.append(s)
    cap_all = cfg.get("captions", "all") == "all"
    # Khong co sub chu nhung + bat auto -> tu tim sub (vi/en) nhieu nguon (SubDL + OpenSubtitles)
    if not caps and cfg.get("auto_fetch_subs") and do_upload and yt:
        from . import subfetch
        langs = [x.strip() for x in str(cfg.get("sub_langs", "vi,en")).split(",") if x.strip()]
        for srt, lg in subfetch.fetch_subs(
                src, cfg.get("work_dir", "work"), langs=langs,
                subdl_api_key=cfg.get("subdl_api_key", ""),
                os_api_key=cfg.get("opensubtitles_api_key", ""),
                os_user=cfg.get("opensubtitles_user", ""),
                os_pass=cfg.get("opensubtitles_pass", ""), log=log):
            caps.append({"srt": srt, "lang": lg, "sidx": -1, "label": lg})
        if caps:
            cap_all = True
    if cfg.get("subs_repo_dir") and caps:                  # day sub len git repo rieng
        from . import subrepo
        kw = _meta_kw(p)
        movie = f"{kw['title']} ({p['year']})" if p.get("year") else kw["title"]
        subrepo.push_subs([(s["srt"], s.get("lang")) for s in caps], movie,
                          cfg["subs_repo_dir"], push=cfg.get("subs_repo_push", True), log=log)

    thumb_path = None                          # poster TMDB lam thumbnail (chung cho moi video)
    if do_upload and yt and cfg.get("tmdb_thumbnail") and cfg.get("tmdb_api_key"):
        from . import tmdb
        kw = _meta_kw(p)
        thumb_path = tmdb.make_thumbnail(kw["title"], p.get("year"), cfg["tmdb_api_key"],
                                         cfg.get("work_dir", "work"), log=log)

    for out in outs:
        splitter.execute(src, out, log=log)
        if do_upload and yt:
            vid = up.upload_video(yt, out["out"], title_for(cfg, p, out),
                                  description=cfg.get("description", ""),
                                  tags=cfg.get("tags", []), privacy=cfg["privacy"],
                                  category_id=cfg.get("category_id", 22),
                                  language=out["lang"] or None, log=log)
            if thumb_path:
                up.set_thumbnail(yt, vid, thumb_path, log=log)
            wanted = caps if cap_all else [s for s in caps if s["sidx"] == out["sidx"]]
            for s in wanted:
                try:
                    up.upload_caption(yt, vid, s["srt"],
                                      language=s["lang"] or cfg["default_caption_lang"],
                                      name=metadata.lang_abbr(s["lang"]) if s["lang"] else "sub",
                                      log=log)
                except Exception as e:
                    log(f"  (!) loi up sub [{s['lang'] or '?'}]: {e}")
            if pid:
                up.add_to_playlist(yt, pid, vid, log=log)
            if mpid:
                up.add_to_playlist(yt, mpid, vid, log=log)
            if cfg.get("cleanup_outputs", True) and os.path.exists(out["out"]):
                os.remove(out["out"])
    if do_upload and yt and cfg.get("cleanup_outputs", True):
        for s in caps:                       # don srt dung chung sau khi da up het video
            if os.path.exists(s["srt"]):
                os.remove(s["srt"])
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
    if do_upload and yt:
        if cfg.get("delete_source") and os.path.exists(src):
            os.remove(src)                       # rotation o nho: xoa nguon thay vi giu done/
            log(f"[{name}] da xoa nguon (rotation)")
        elif cfg.get("done_dir"):
            os.makedirs(cfg["done_dir"], exist_ok=True)
            shutil.move(src, os.path.join(cfg["done_dir"], os.path.basename(src)))
    _record(store, sig, tkey, name, [o["out"] for o in outs], res_rank=rrank)
    log(f"[{name}] XONG")
    return p
