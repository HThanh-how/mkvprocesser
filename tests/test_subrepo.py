import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import subrepo  # noqa: E402


def test_safe_dir():
    assert subrepo.safe_dir('A:b/c?') == "A_b_c_"
    assert subrepo.safe_dir("") == "movie"


def test_push_subs_no_repo(tmp_path):
    # tmp_path khong phai git repo -> 0, khong nem loi
    assert subrepo.push_subs([("x.srt", "vi")], "Movie", str(tmp_path), log=lambda *a: None) == 0


def test_push_subs_commits_local(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for c in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *c], check=True)
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    n = subrepo.push_subs([(str(srt), "vi"), (None, "en")], "My Movie (2020)", str(repo),
                          push=False, log=lambda *a: None)
    assert n == 1                                              # chi vi.srt (en None bo qua)
    assert (repo / "My Movie (2020)" / "vi.srt").exists()
    out = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "subs:" in out                                     # da commit
