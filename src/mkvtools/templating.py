"""Render HTML phia server bang Jinja2, autoescape BAT san.

Vi sao doi tu f-string sang day: cac trang co (/classic, /analyze) ghep chuoi
truc tiep, nen ten file trong inbox va URL do nguoi dung dan vao hang doi di
thang vao HTML. Mot tai khoan `user` chi can them link dang

    https://x/"><script>fetch('/admin/add',{method:'POST',...})</script>

la doan script do chay trong PHIEN CUA ADMIN ngay khi admin mo /classic — tuc
la leo tu quyen user len quyen admin. Autoescape dong ca lop loi nay lai o mot
cho, thay vi phai nho goi html.escape() dung tung diem noi chuoi.

Module tach rieng khoi webui de test render duoc ma khong can dung FastAPI.
"""
from __future__ import annotations

import pathlib
from typing import Any

import jinja2

TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,          # KHONG tat: xem docstring o tren
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(name: str, **ctx: Any) -> str:
    """Render template trong mkvtools/templates/ thanh chuoi HTML da escape."""
    return _env.get_template(name).render(**ctx)


def env() -> jinja2.Environment:
    """Truy cap Environment (dung cho test kiem tra autoescape van bat)."""
    return _env
