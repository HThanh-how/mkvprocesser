"""Quản lý cấu hình người dùng cho MKV Processor."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "input_folder": ".",
    "auto_upload": False,
    "repo": "HThanh-how/Subtitles",
    "repo_url": "https://github.com/HThanh-how/Subtitles.git",
    "branch": "main",
    "logs_dir": "logs",
    "subtitle_dir": "subtitles",
    "token": "",
    "force_reprocess": False,
    "git_repo_path": "",
    "git_sparse_paths": ["logs"],
    "git_user_name": "MKV Processor Bot",
    "git_user_email": "bot@example.com",
}


def get_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif xdg := os.getenv("XDG_CONFIG_HOME"):
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    config_dir = base / "MKVProcessor"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_logs_repo_dir() -> Path:
    repo_dir = get_config_dir() / "logs_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_user_config() -> Dict[str, Any]:
    """Load config, merge với default nếu chưa có config file."""
    config = DEFAULT_CONFIG.copy()
    path = get_config_path()
    if path.exists():
        try:
            user_cfg = json.loads(path.read_text(encoding="utf-8"))
            config.update(user_cfg)
        except Exception as exc:
            print(f"[CONFIG] Không thể đọc config: {exc}")
    return config


def load_raw_user_config() -> Dict[str, Any]:
    """Load config từ file (nếu có), không merge với default."""
    path = get_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[CONFIG] Không thể đọc config: {exc}")
    return {}


def save_user_config(data: Dict[str, Any]) -> None:
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    path = get_config_path()
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_config() -> None:
    path = get_config_path()
    if path.exists():
        path.unlink()

