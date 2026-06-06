import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mkvtools import idempotency, pipeline  # noqa: E402


def _cfg(tmp_path, **over):
    cfg = {
        "work_dir": str(tmp_path / "work"),
        "subtitle_mode": "caption",
        "container": "mp4",
        "skip_processed": True,
        "state_file": str(tmp_path / "state.json"),
        "min_free_gb_factor": 1.5,
        "make_playlist": False,
        "upload": False,
    }
    cfg.update(over)
    return cfg


def _fake_output(tmp_path):
    return {"out": str(tmp_path / "o.mp4"), "srt": None, "lang": "vie", "label": "vie",
            "ch": 2, "aidx": 0, "sidx": None, "acodec": "aac", "sub_mode": "caption",
            "container": "mp4", "burn": False}


def test_skips_already_processed(tmp_path, monkeypatch):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"some video bytes")
    cfg = _cfg(tmp_path)
    store = idempotency.ProcessedStore(cfg["state_file"])
    store.add(idempotency.file_signature(str(src)), {"name": "movie.mkv"})

    called = {"plan": False}

    def fake_plan(*a, **k):
        called["plan"] = True
        return {"base": "movie", "outputs": []}

    monkeypatch.setattr(pipeline.splitter, "plan", fake_plan)
    res = pipeline.process_file(str(src), cfg, store=store)
    assert res.get("skipped") is True
    assert called["plan"] is False          # da bo qua truoc khi tach


def test_records_after_success(tmp_path, monkeypatch):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"some video bytes")
    cfg = _cfg(tmp_path)
    out = _fake_output(tmp_path)
    monkeypatch.setattr(pipeline.splitter, "plan",
                        lambda *a, **k: {"base": "movie", "outputs": [out]})
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)

    res = pipeline.process_file(str(src), cfg, do_upload=False)   # store auto-tao tu cfg
    assert "skipped" not in res
    sig = idempotency.file_signature(str(src))
    assert idempotency.ProcessedStore(cfg["state_file"]).has(sig)   # da ghi xuong dia


def test_force_bypasses_skip(tmp_path, monkeypatch):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"some video bytes")
    cfg = _cfg(tmp_path)
    store = idempotency.ProcessedStore(cfg["state_file"])
    store.add(idempotency.file_signature(str(src)), {"name": "movie.mkv"})
    out = _fake_output(tmp_path)
    called = {"plan": False}

    def fake_plan(*a, **k):
        called["plan"] = True
        return {"base": "movie", "outputs": [out]}

    monkeypatch.setattr(pipeline.splitter, "plan", fake_plan)
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)
    res = pipeline.process_file(str(src), cfg, do_upload=False, store=store, force=True)
    assert called["plan"] is True           # force -> van chay du da ghi
    assert "skipped" not in res


def test_low_disk_warns_but_proceeds(tmp_path, monkeypatch):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"some video bytes")
    cfg = _cfg(tmp_path)
    out = _fake_output(tmp_path)
    monkeypatch.setattr(pipeline.splitter, "plan",
                        lambda *a, **k: {"base": "movie", "outputs": [out]})
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)
    monkeypatch.setattr(pipeline.resources, "free_gb", lambda p: 0.0)  # gia lap het dia

    logs = []
    res = pipeline.process_file(str(src), cfg, do_upload=False, log=logs.append)
    assert "skipped" not in res                       # canh bao nhung van chay
    assert any("dia" in m.lower() for m in logs)


def test_title_dedup_skips_same_movie_but_not_part2(tmp_path, monkeypatch):
    f1 = tmp_path / "Movie.2020.1080p.x264.mkv"
    f1.write_bytes(b"aaaa")
    f2 = tmp_path / "Movie.2020.1080p.HEVC.mkv"     # cung phim, cung res, rip khac (bytes khac)
    f2.write_bytes(b"different bytes here")
    f3 = tmp_path / "Movie.Part.2.2020.1080p.mkv"   # PHAN 2 -> phai chay
    f3.write_bytes(b"part two content")
    cfg = _cfg(tmp_path, on_title_match="skip")
    out = _fake_output(tmp_path)
    monkeypatch.setattr(pipeline.splitter, "plan", lambda *a, **k: {"base": "x", "outputs": [out]})
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)
    store = idempotency.ProcessedStore(cfg["state_file"])

    pipeline.process_file(str(f1), cfg, do_upload=False, store=store)
    r2 = pipeline.process_file(str(f2), cfg, do_upload=False, store=store)
    r3 = pipeline.process_file(str(f3), cfg, do_upload=False, store=store)
    assert r2.get("skipped") == "title"             # cung tua -> bo qua
    assert "skipped" not in r3                       # Phan 2 -> van chay


def test_title_dedup_warn_mode_still_processes(tmp_path, monkeypatch):
    f1 = tmp_path / "A.2020.1080p.mkv"
    f1.write_bytes(b"x")
    f2 = tmp_path / "A.2020.720p.mkv"
    f2.write_bytes(b"yy")
    cfg = _cfg(tmp_path, on_title_match="warn")
    out = _fake_output(tmp_path)
    monkeypatch.setattr(pipeline.splitter, "plan", lambda *a, **k: {"base": "x", "outputs": [out]})
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)
    store = idempotency.ProcessedStore(cfg["state_file"])
    logs = []
    pipeline.process_file(str(f1), cfg, do_upload=False, store=store, log=logs.append)
    r2 = pipeline.process_file(str(f2), cfg, do_upload=False, store=store, log=logs.append)
    assert "skipped" not in r2                       # warn -> van xu ly
    assert any("da co theo tua" in m for m in logs)


def test_title_dedup_allows_higher_resolution_upgrade(tmp_path, monkeypatch):
    f_lo = tmp_path / "Film.2019.1080p.x264.mkv"
    f_lo.write_bytes(b"lo")
    f_hi = tmp_path / "Film.2019.2160p.x265.mkv"     # cung phim, res CAO HON -> van up
    f_hi.write_bytes(b"hi")
    f_same = tmp_path / "Film.2019.1080p.WEB.mkv"    # cung phim, res bang -> bo qua
    f_same.write_bytes(b"same-res")
    cfg = _cfg(tmp_path, on_title_match="skip")
    out = _fake_output(tmp_path)
    monkeypatch.setattr(pipeline.splitter, "plan", lambda *a, **k: {"base": "x", "outputs": [out]})
    monkeypatch.setattr(pipeline.splitter, "execute", lambda s, o, log=print: o)
    store = idempotency.ProcessedStore(cfg["state_file"])

    pipeline.process_file(str(f_lo), cfg, do_upload=False, store=store)        # ghi 1080p
    r_hi = pipeline.process_file(str(f_hi), cfg, do_upload=False, store=store)   # 2160p -> nang cap
    r_same = pipeline.process_file(str(f_same), cfg, do_upload=False, store=store)  # 1080p -> skip
    assert "skipped" not in r_hi                     # res cao hon -> van chay
    assert r_same.get("skipped") == "title"          # bang res -> bo qua

