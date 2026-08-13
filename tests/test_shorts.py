import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mkvtools import shorts


def test_short_title_cleans_and_tags():
    assert shorts.short_title("My_Cool_Clip.mp4") == "My Cool Clip #Shorts"
    assert shorts.short_title("").endswith("#Shorts")
    # cat 100 ky tu (ke ca ' #Shorts')
    long = "a" * 200 + ".mp4"
    assert len(shorts.short_title(long)) <= 100
    assert shorts.short_title(long).endswith("#Shorts")


def test_add_and_snapshot_order_newest_first():
    m = shorts.ShortsManager("work/shorts")
    j1 = m.add("https://a", "download")
    j2 = m.add("https://b", "upload")
    assert j1["id"] != j2["id"] and j2["mode"] == "upload"
    snap = m.snapshot()
    assert [j["id"] for j in snap["jobs"]] == [j2["id"], j1["id"]]   # moi nhat truoc


def test_add_rejects_empty_and_comment():
    m = shorts.ShortsManager("work/shorts")
    assert m.add("", "download") is None
    assert m.add("   ", "upload") is None
    assert m.add("# ghi chu", "download") is None


def test_add_defaults_invalid_mode_to_download():
    m = shorts.ShortsManager("work/shorts")
    assert m.add("https://a", "nonsense")["mode"] == "download"


def test_add_probe_and_media_url():
    m = shorts.ShortsManager("work/shorts")
    p = m.add("https://page", "probe")
    assert p["mode"] == "probe" and p["candidates"] == []
    g = m.add("https://page", "download", media_url="https://cdn/v.mp4",
              referer="https://page", label="720x1280")
    assert g["media_url"] == "https://cdn/v.mp4" and g["referer"] == "https://page"
    assert g["name"] == "720x1280"


def test_add_batch_keeps_media_items():
    m = shorts.ShortsManager("work/shorts")
    items = [{"url": "https://cdn/1.mp4", "referer": "https://threads/@u/post/1"}]
    job = m.add("https://threads/@u", "batch", label="threads_u_videos.zip",
                media_items=items)
    assert job["mode"] == "batch"
    assert job["media_items"] == items


def test_worker_lifecycle_try_start_next_stop():
    m = shorts.ShortsManager("work/shorts")
    m.add("https://a", "download")
    assert m.try_start() is True
    assert m.try_start() is False           # da chay -> khong khoi dong lai
    job = m.next_job()
    assert job["status"] == "running"
    assert m.next_job() is None             # het hang -> tu tat running
    assert m.try_start() is True            # gio ranh lai


def test_remove():
    m = shorts.ShortsManager("work/shorts")
    j = m.add("https://a", "download")
    assert m.remove(j["id"]) is True
    assert m.remove(j["id"]) is False
    assert m.snapshot()["jobs"] == []
