"""
Legacy CLI entry point.

Kept for backwards compatibility; prefer `python -m mkvprocessor.cli_main`.
"""
import sys
from pathlib import Path

# Thêm src vào sys.path nếu chưa có
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import và re-export từ module mới
from mkvprocessor.legacy_api import *  # noqa: F401,F403
from mkvprocessor.cli_main import run_cli


if __name__ == "__main__":
    run_cli()
