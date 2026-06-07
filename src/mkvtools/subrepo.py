"""Day phu de (da rut/tai) len 1 git repo rieng (vd github.com/HThanh-how/Subtitles).

Yeu cau: repo da duoc CLONE san tai subs_repo_dir + cau hinh push auth tren may
(PAT trong remote URL, hoac SSH key). Module chi copy .srt vao repo roi git
add/commit/push. Khong nem loi (loi git -> log + tra 0).
"""
import os
import re
import shutil
import subprocess


def safe_dir(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip() or "movie"


def _git(repo, *args, log=print):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)  # noqa: S603,S607
    err = (p.stderr or "").strip()
    if p.returncode != 0 and err and "nothing to commit" not in err:
        log(f"  (subrepo) git {args[0]}: {err[:160]}")
    return p


def push_subs(srt_items, movie_name, repo_dir, push=True, log=print) -> int:
    """Copy cac (srt_path, lang) vao repo_dir/<phim>/<lang>.srt -> commit (+push).

    Tra ve so file da them. repo_dir phai la 1 git repo (co .git). 0 neu chua cau hinh.
    """
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        log("  (subrepo) chua cau hinh repo sub (subs_repo_dir tro toi 1 clone) -> bo qua")
        return 0
    folder = safe_dir(movie_name)
    dest = os.path.join(repo_dir, folder)
    os.makedirs(dest, exist_ok=True)
    n = 0
    for srt, lang in srt_items:
        if srt and os.path.exists(srt):
            shutil.copy2(srt, os.path.join(dest, f"{(lang or 'sub')}.srt"))
            n += 1
    if not n:
        return 0
    _git(repo_dir, "add", "--", folder, log=log)
    _git(repo_dir, "commit", "-m", f"subs: {movie_name}", log=log)
    if push:
        _git(repo_dir, "push", log=log)
    log(f"  (subrepo) da day {n} sub cua '{movie_name}' len repo")
    return n
