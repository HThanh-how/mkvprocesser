import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import jobs  # noqa: E402


def test_history_persists_across_restart(tmp_path):
    import os
    hf = str(tmp_path / "hist.json")
    q = jobs.JobQueue(history_file=hf)
    q.record_history({"url": "u1", "status": "done", "name": "a.mkv"})
    assert os.path.exists(hf)
    q2 = jobs.JobQueue(history_file=hf)                 # nap lai (gia lap restart)
    assert q2.snapshot()["history"][-1]["url"] == "u1"


def test_queue_add_pop_and_filters():
    q = jobs.JobQueue()
    assert q.add_many("u1\n\n  u2  \n# ghi chu\nu3") == 3      # bo dong rong + comment
    assert q.pop() == "u1" and q.pop() == "u2" and q.pop() == "u3"
    assert q.pop() is None


def test_try_start_exclusive_until_drained():
    q = jobs.JobQueue()
    q.add("u1")
    assert q.try_start() is True       # gianh duoc quyen chay
    assert q.try_start() is False      # da co worker -> khong khoi dong cai thu 2
    assert q.pop() == "u1"
    assert q.pop() is None             # het hang -> pop() tu tat 'running' (nguyen tu)
    assert q.try_start() is True       # ranh lai -> gianh duoc


def test_wait_disk_returns_true_when_enough():
    seen = []
    ok = jobs.wait_disk("/x", 10, lambda p: 50.0, lambda s: seen.append(s), print)
    assert ok is True and seen == []        # du ngay -> khong cho


def test_wait_disk_polls_then_gives_up():
    slept = []
    ok = jobs.wait_disk("/x", 10, lambda p: 1.0, lambda s: slept.append(s), print, tries=3)
    assert ok is False and len(slept) == 3  # luon thieu -> cho het luot roi tra False


def test_drain_fetch_process_then_delete_source(tmp_path):
    q = jobs.JobQueue()
    q.add("https://host/movie.mkv")
    processed = []

    def fake_fetch(url, d, log, cookies=None, referer=None):
        p = os.path.join(d, "movie.mkv")
        with open(p, "wb") as f:
            f.write(b"x")
        return p

    jobs.drain(q, {"downloads_dir": str(tmp_path), "min_free_gb": 0},
               fetch_fn=fake_fetch, process_fn=lambda s, c, log: processed.append(s),
               free_gb_fn=lambda p: 999.0, sleep_fn=lambda s: None)

    assert processed and not os.path.exists(os.path.join(str(tmp_path), "movie.mkv"))  # da xoa nguon
    snap = q.snapshot()
    assert snap["history"][-1]["status"] == "done" and snap["current"] is None


def test_drain_continues_after_one_link_fails(tmp_path):
    q = jobs.JobQueue()
    q.add("bad")
    q.add("good")
    done = []

    def fake_fetch(url, d, log, cookies=None, referer=None):
        if url == "bad":
            raise RuntimeError("tai loi")
        p = os.path.join(d, "ok.mkv")
        with open(p, "wb") as f:
            f.write(b"y")
        return p

    jobs.drain(q, {"downloads_dir": str(tmp_path), "min_free_gb": 0},
               fetch_fn=fake_fetch, process_fn=lambda s, c, log: done.append(s),
               free_gb_fn=lambda p: 999.0, sleep_fn=lambda s: None)

    h = q.snapshot()["history"]
    assert h[0]["status"] == "error" and h[1]["status"] == "done"
    assert len(done) == 1                    # link loi khong chan link sau


def test_drain_waits_for_disk_before_download(tmp_path):
    q = jobs.JobQueue()
    q.add("https://host/m.mkv")
    state = {"n": 0}

    def free(p):                             # 2 lan dau thieu, sau du -> xoay vong
        state["n"] += 1
        return 1.0 if state["n"] < 3 else 99.0

    slept = []

    def fake_fetch(url, d, log, cookies=None, referer=None):
        p = os.path.join(d, "m.mkv")
        with open(p, "wb") as f:
            f.write(b"z")
        return p

    jobs.drain(q, {"downloads_dir": str(tmp_path), "min_free_gb": 20},
               fetch_fn=fake_fetch, process_fn=lambda s, c, log: None,
               free_gb_fn=free, sleep_fn=lambda s: slept.append(s))

    assert slept                              # da phai cho dia truoc khi tai
    assert q.snapshot()["history"][-1]["status"] == "done"
