"""User configuration management for MKV Processor."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

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
    # Output folder settings (empty = use default from i18n)
    "output_folder_dubbed": "",      # Thư mục lồng tiếng/thuyết minh
    "output_folder_subtitles": "",   # Thư mục subtitles
    "output_folder_original": "",    # Thư mục original
    "language": "vi",  # Language code: 'en' for English, 'vi' for Vietnamese
}


def get_config_dir() -> Path:
    """Get the configuration directory path.
    
    Returns:
        Path to the configuration directory. Creates the directory if it doesn't exist.
        On Windows: %APPDATA%/MKVProcessor
        On Linux/macOS: ~/.config/MKVProcessor or $XDG_CONFIG_HOME/MKVProcessor
    """
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
    """Get the logs repository directory path.
    
    Returns:
        Path to the logs repository directory. Creates the directory if it doesn't exist.
    """
    repo_dir = get_config_dir() / "logs_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


def get_config_path() -> Path:
    """Get the path to the configuration file.
    
    Returns:
        Path to config.json in the configuration directory.
    """
    return get_config_dir() / "config.json"


def load_user_config() -> Dict[str, Any]:
    """Load user configuration, merging with defaults if config file doesn't exist.
    
    Returns:
        Dictionary containing user configuration merged with default values.
        If config file doesn't exist or is invalid, returns default configuration.
    """
    config = DEFAULT_CONFIG.copy()
    path = get_config_path()
    if path.exists():
        try:
            user_cfg = json.loads(path.read_text(encoding="utf-8"))
            config.update(user_cfg)
        except (json.JSONDecodeError, IOError) as exc:
            logger.error(f"Failed to read config file: {exc}")
    return config


def load_raw_user_config() -> Dict[str, Any]:
    """Load configuration from file (if exists), without merging with defaults.
    
    Returns:
        Dictionary containing raw configuration from file, or empty dict if file
        doesn't exist or is invalid.
    """
    path = get_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as exc:
            logger.error(f"Failed to read config file: {exc}")
    return {}


def save_user_config(data: Dict[str, Any]) -> None:
    """Save user configuration to file.
    
    Args:
        data: Configuration dictionary to save. Will be merged with defaults.
    """
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    path = get_config_path()
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_config() -> None:
    """Reset configuration by deleting the config file.
    
    After calling this, the next load_user_config() will return default values.
    """
    path = get_config_path()
    if path.exists():
        path.unlink()
