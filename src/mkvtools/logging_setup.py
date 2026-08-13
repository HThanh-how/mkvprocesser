"""Cau hinh logging cho service (khong dung cho CLI).

Truoc day chi ffmpeg_helper co logger; phan con lai cua service khong cau hinh
logging gi ca, nen log ra journald la van bang tron uvicorn, khong co request
id, khong loc duoc theo muc, khong parse duoc bang may.

`print()` trong cli.py KHONG phai muc tieu cua module nay — do la output cho
nguoi dung go lenh, dung nguyen la dung.

Bat JSON bang MKV_LOG_JSON=1 (mac dinh: JSON khi khong chay tren terminal, tuc
la khi chay duoi systemd). Muc log: MKV_LOG_LEVEL (mac dinh INFO).
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time

# Request id cua request dang xu ly; middleware set, formatter tu doc.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "asctime", "message", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Mot dong JSON moi ban ghi; field phu truyen qua logger.info(..., extra=)."""

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            out["request_id"] = rid
        for k, v in record.__dict__.items():        # extra={...} do goi ham truyen
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Ban de doc bang mat khi chay tay trong terminal."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get()
        prefix = f"[{rid}] " if rid else ""
        return f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {prefix}" \
               f"{record.name}: {record.getMessage()}"


def configure(level: str | None = None, json_mode: bool | None = None) -> None:
    """Dung mot handler duy nhat tren root logger. Goi lai an toan (idempotent)."""
    if json_mode is None:
        env = os.environ.get("MKV_LOG_JSON")
        json_mode = (env == "1") if env else not sys.stderr.isatty()
    level = (level or os.environ.get("MKV_LOG_LEVEL") or "INFO").upper()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_mode else TextFormatter())
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn tu gan handler rieng -> tat propagate cua no de khong in hai lan.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
