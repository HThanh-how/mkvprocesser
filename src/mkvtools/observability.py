"""Health check + metrics Prometheus.

Ham o day THUAN (nhan so lieu, tra du lieu) de test duoc ma khong can dung
server — webui chi lo thu thap so lieu roi goi vao day.

Vi sao can: truoc day service khong co cach nao de biet "song nhung treo".
systemd Restart=always chi bat duoc tien trinh chet han; mot worker ket cung
hay het dia thi process van chay va systemd van bao active.
"""
from __future__ import annotations

from . import __version__


def health(*, ffmpeg_ok: bool, disk_free_gb: float | None, min_free_gb: float,
           queue: dict, uptime_seconds: float) -> tuple[dict, int]:
    """Tra (body, http_status). 503 khi khong con phuc vu duoc viec chinh.

    Het dia LA tinh trang degraded that: pipeline tach file se dung, nen phai
    bao ra ngoai chu khong am tham xep hang.
    """
    problems = []
    if not ffmpeg_ok:
        problems.append("khong tim thay ffmpeg/ffprobe")
    if disk_free_gb is not None and min_free_gb and disk_free_gb < min_free_gb:
        problems.append(f"dia trong {disk_free_gb:.1f}GB < nguong {min_free_gb}GB")

    body = {
        "status": "ok" if not problems else "degraded",
        "version": __version__,
        "uptime_seconds": round(uptime_seconds, 1),
    }
    if problems:
        body["problems"] = problems
    body["checks"] = {
        "ffmpeg": ffmpeg_ok,
        "disk_free_gb": disk_free_gb,
        "queue_pending": len(queue.get("pending") or []),
        "queue_running": bool(queue.get("running")),
    }
    return body, (200 if not problems else 503)


def _line(name: str, value, labels: str = "") -> str:
    if isinstance(value, bool):
        value = 1 if value else 0
    return f"{name}{labels} {value}"


def render_prometheus(*, ffmpeg_ok: bool, disk_free_gb: float | None, queue: dict,
                      shorts: dict, sessions: int, worker_allowed: bool,
                      node_id: str, uptime_seconds: float) -> str:
    """Sinh phoi bay Prometheus dang text (khong can thu vien client)."""
    history = queue.get("history") or []
    done = sum(1 for h in history if h.get("status") == "done")
    error = sum(1 for h in history if h.get("status") == "error")
    shorts_jobs = shorts.get("jobs") or []

    out = [
        "# HELP mkvtools_build_info Phien ban dang chay.",
        "# TYPE mkvtools_build_info gauge",
        _line("mkvtools_build_info", 1, f'{{version="{__version__}",node="{node_id}"}}'),
        "# HELP mkvtools_uptime_seconds Thoi gian tien trinh da chay.",
        "# TYPE mkvtools_uptime_seconds gauge",
        _line("mkvtools_uptime_seconds", round(uptime_seconds, 1)),
        "# HELP mkvtools_ffmpeg_available ffmpeg/ffprobe co dung duoc khong.",
        "# TYPE mkvtools_ffmpeg_available gauge",
        _line("mkvtools_ffmpeg_available", ffmpeg_ok),
        "# HELP mkvtools_queue_pending So link dang cho trong hang doi.",
        "# TYPE mkvtools_queue_pending gauge",
        _line("mkvtools_queue_pending", len(queue.get("pending") or [])),
        "# HELP mkvtools_queue_running Worker dang xu ly job hay khong.",
        "# TYPE mkvtools_queue_running gauge",
        _line("mkvtools_queue_running", bool(queue.get("running"))),
        "# HELP mkvtools_worker_allowed Node dang trong ca lam viec cua no.",
        "# TYPE mkvtools_worker_allowed gauge",
        _line("mkvtools_worker_allowed", worker_allowed),
        "# HELP mkvtools_jobs_total So job da ket thuc (trong lich su con giu).",
        "# TYPE mkvtools_jobs_total gauge",
        _line("mkvtools_jobs_total", done, '{status="done"}'),
        _line("mkvtools_jobs_total", error, '{status="error"}'),
        "# HELP mkvtools_shorts_jobs So job tai video ngan theo trang thai.",
        "# TYPE mkvtools_shorts_jobs gauge",
    ]
    for status in ("queued", "running", "ready", "done", "error"):
        n = sum(1 for j in shorts_jobs if j.get("status") == status)
        out.append(_line("mkvtools_shorts_jobs", n, f'{{status="{status}"}}'))
    out += [
        "# HELP mkvtools_sessions_active So phien dang nhap con hieu luc.",
        "# TYPE mkvtools_sessions_active gauge",
        _line("mkvtools_sessions_active", sessions),
    ]
    if disk_free_gb is not None:
        out += [
            "# HELP mkvtools_disk_free_bytes Dung luong trong o thu muc tai ve.",
            "# TYPE mkvtools_disk_free_bytes gauge",
            _line("mkvtools_disk_free_bytes", int(disk_free_gb * 1024 ** 3)),
        ]
    return "\n".join(out) + "\n"
