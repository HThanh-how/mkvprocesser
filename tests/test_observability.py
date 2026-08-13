"""Health check, metrics Prometheus va logging co cau truc."""
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mkvtools import logging_setup, observability  # noqa: E402

EMPTY_Q = {"pending": [], "running": False, "history": []}


# ------------------------------------------------------------------- health
def test_health_ok_when_everything_fine():
    body, code = observability.health(ffmpeg_ok=True, disk_free_gb=100.0,
                                      min_free_gb=5, queue=EMPTY_Q, uptime_seconds=12.3)
    assert code == 200 and body["status"] == "ok" and "problems" not in body


def test_health_503_when_ffmpeg_missing():
    body, code = observability.health(ffmpeg_ok=False, disk_free_gb=100.0,
                                      min_free_gb=5, queue=EMPTY_Q, uptime_seconds=1)
    assert code == 503 and body["status"] == "degraded"
    assert any("ffmpeg" in p for p in body["problems"])


def test_health_503_when_disk_below_threshold():
    """Het dia = pipeline tach file se dung -> phai bao ra, khong am tham xep hang."""
    body, code = observability.health(ffmpeg_ok=True, disk_free_gb=1.2,
                                      min_free_gb=5, queue=EMPTY_Q, uptime_seconds=1)
    assert code == 503 and any("dia trong" in p for p in body["problems"])


def test_health_ignores_disk_when_no_threshold_set():
    _body, code = observability.health(ffmpeg_ok=True, disk_free_gb=0.1,
                                       min_free_gb=0, queue=EMPTY_Q, uptime_seconds=1)
    assert code == 200


# ------------------------------------------------------------------ metrics
def _metrics(**kw):
    base = dict(ffmpeg_ok=True, disk_free_gb=10.0, queue=EMPTY_Q, shorts={"jobs": []},
                sessions=0, worker_allowed=True, node_id="vnpt", uptime_seconds=5)
    base.update(kw)
    return observability.render_prometheus(**base)


def test_metrics_exposes_core_series():
    out = _metrics(queue={"pending": ["a", "b"], "running": True,
                          "history": [{"status": "done"}, {"status": "error"},
                                      {"status": "done"}]},
                   sessions=3)
    assert "mkvtools_queue_pending 2" in out
    assert "mkvtools_queue_running 1" in out
    assert 'mkvtools_jobs_total{status="done"} 2' in out
    assert 'mkvtools_jobs_total{status="error"} 1' in out
    assert "mkvtools_sessions_active 3" in out
    assert 'node="vnpt"' in out


def test_metrics_counts_shorts_by_status():
    out = _metrics(shorts={"jobs": [{"status": "done"}, {"status": "done"},
                                    {"status": "error"}]})
    assert 'mkvtools_shorts_jobs{status="done"} 2' in out
    assert 'mkvtools_shorts_jobs{status="error"} 1' in out
    assert 'mkvtools_shorts_jobs{status="queued"} 0' in out


def test_metrics_omits_disk_when_unknown():
    assert "mkvtools_disk_free_bytes" not in _metrics(disk_free_gb=None)
    assert "mkvtools_disk_free_bytes 10737418240" in _metrics(disk_free_gb=10.0)


def test_metrics_format_is_parseable():
    """Moi dong khong phai comment phai la '<ten>[{nhan}] <so>'."""
    for line in _metrics().strip().splitlines():
        if line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        assert name and float(value) is not None


# ------------------------------------------------------------------ logging
def test_json_formatter_emits_one_json_object_per_record():
    rec = logging.LogRecord("mkvtools.test", logging.INFO, __file__, 1,
                            "da tai %s", ("phim.mkv",), None)
    rec.status = 200
    out = json.loads(logging_setup.JsonFormatter().format(rec))
    assert out["level"] == "INFO" and out["logger"] == "mkvtools.test"
    assert out["msg"] == "da tai phim.mkv"
    assert out["status"] == 200            # field phu tu extra={...}
    assert out["ts"].endswith("Z")


def test_json_formatter_includes_request_id():
    token = logging_setup.request_id_var.set("abc123")
    try:
        rec = logging.LogRecord("t", logging.INFO, __file__, 1, "x", (), None)
        assert json.loads(logging_setup.JsonFormatter().format(rec))["request_id"] == "abc123"
    finally:
        logging_setup.request_id_var.reset(token)


@pytest.mark.parametrize("json_mode,expect_json", [(True, True), (False, False)])
def test_configure_installs_single_handler(json_mode, expect_json):
    logging_setup.configure(level="DEBUG", json_mode=json_mode)
    root = logging.getLogger()
    assert len(root.handlers) == 1 and root.level == logging.DEBUG
    is_json = isinstance(root.handlers[0].formatter, logging_setup.JsonFormatter)
    assert is_json is expect_json
    logging_setup.configure(level="INFO", json_mode=False)   # tra lai trang thai goc
