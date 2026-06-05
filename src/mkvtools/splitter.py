"""
Tach 1 video nhieu audio -> moi audio 1 file + rut sub text cung ngon ngu.
Cac ham build_* la PURE (chi tao argv) -> test duoc khong can ffmpeg.
"""
import os
import re

from . import ffmpeg_helper, metadata

TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}


def _lang(s):
    return (s.get("tags", {}) or {}).get("language", "") or ""


def _title(s):
    return (s.get("tags", {}) or {}).get("title", "") or ""


def analyze(info: dict) -> dict:
    audio, subs = [], []
    ai = si = 0
    for s in info.get("streams", []):
        ct = s.get("codec_type")
        if ct == "audio":
            audio.append({"rel": ai, "lang": _lang(s), "title": _title(s),
                          "codec": s.get("codec_name", ""), "ch": s.get("channels", 0)})
            ai += 1
        elif ct == "subtitle":
            cn = s.get("codec_name", "")
            subs.append({"rel": si, "lang": _lang(s), "title": _title(s),
                         "codec": cn, "text": cn in TEXT_SUB_CODECS})
            si += 1
    return {"audio": audio, "subs": subs, "streams": info.get("streams", [])}


def pair_tracks(analysis: dict) -> list[dict]:
    text_subs = [s for s in analysis["subs"] if s["text"]]
    jobs, used = [], set()
    for a in analysis["audio"]:
        match = None
        if a["lang"]:
            match = next((s for s in text_subs
                          if s["rel"] not in used and s["lang"] == a["lang"]), None)
        if match is None:
            match = next((s for s in text_subs
                          if s["rel"] not in used and s["rel"] == a["rel"]), None)
        if match:
            used.add(match["rel"])
        jobs.append({"aidx": a["rel"], "lang": a["lang"], "title": a["title"],
                     "acodec": a["codec"], "ch": a["ch"],
                     "sidx": match["rel"] if match else None})
    return jobs


def safe(s: str) -> str:
    s = re.sub(r"[^\w.\- ]+", "", s or "", flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", s) or "track"


def label_for(job: dict, idx: int) -> str:
    return job["lang"] or job["title"] or f"audio{idx + 1}"


def build_split_cmd(src, out, aidx, acodec, container="mp4"):
    cmd = ["ffmpeg", "-y", "-i", src, "-map", "0:v:0", "-map", f"0:a:{aidx}",
           "-map_metadata", "0", "-c:v", "copy"]
    cmd += ["-c:a", "copy"] if acodec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    if container == "mkv":
        cmd += ["-map", "0:t?"]          # giu attachment/font (cho sub ASS)
    else:
        cmd += ["-movflags", "+faststart"]  # mp4: phat/cast muot
    cmd += [out]
    return cmd


def build_extract_sub_cmd(src, out_srt, sidx):
    return ["ffmpeg", "-y", "-i", src, "-map", f"0:s:{sidx}", out_srt]


def build_burn_cmd(src, out, aidx, sidx, acodec):
    cmd = ["ffmpeg", "-y", "-i", src, "-map", "0:v:0", "-map", f"0:a:{aidx}",
           "-vf", f"subtitles='{src}':si={sidx}",
           "-c:v", "libx264", "-crf", "20", "-preset", "medium"]
    cmd += ["-c:a", "copy"] if acodec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", out]
    return cmd


def plan(src, outdir, sub_mode="caption", container="mp4") -> tuple:
    base = os.path.splitext(os.path.basename(src))[0]
    info = ffmpeg_helper.probe(src)
    a = analyze(info)
    res = metadata.resolution_label(a["streams"])
    year = metadata.movie_year(info)
    jobs = pair_tracks(a)
    outs = []
    for i, job in enumerate(jobs):
        label = label_for(job, i)
        parts = [res, metadata.lang_abbr(job["lang"]) if job["lang"] else safe(label)]
        if year:
            parts.append(year)
        parts.append(safe(base))
        stem = "_".join(p for p in parts if p)
        ext = "mkv" if container == "mkv" else "mp4"
        mp4 = os.path.join(outdir, f"{stem}.{ext}")
        srt = os.path.join(outdir, f"{stem}.srt") if job["sidx"] is not None else None
        outs.append({"label": label, "lang": job["lang"], "ch": job["ch"],
                     "out": mp4, "srt": srt, "aidx": job["aidx"], "sidx": job["sidx"],
                     "acodec": job["acodec"], "sub_mode": sub_mode, "container": container,
                     "burn": sub_mode in ("burn", "both")})
    return {"base": base, "res": res, "year": year, "outputs": outs}


def execute(src, out, log=print):
    if out["burn"] and out["sidx"] is not None:
        log(f"  burn  -> {os.path.basename(out['out'])}")
        cmd = build_burn_cmd(src, out["out"], out["aidx"], out["sidx"], out["acodec"])
    else:
        log(f"  split -> {os.path.basename(out['out'])}")
        cmd = build_split_cmd(src, out["out"], out["aidx"], out["acodec"], out["container"])
    r = ffmpeg_helper.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg loi: " + r.stderr.decode("utf-8", "replace")[-800:])
    if out["srt"] and out["sub_mode"] in ("caption", "both"):
        log(f"  sub   -> {os.path.basename(out['srt'])}")
        rs = ffmpeg_helper.run(build_extract_sub_cmd(src, out["srt"], out["sidx"]),
                               capture_output=True)
        if rs.returncode != 0:
            log("  (!) khong rut duoc sub (co the la sub anh) - bo qua")
            out["srt"] = None
    return out
