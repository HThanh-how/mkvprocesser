"""
Command-line entry point for MKV Processor.

This module keeps dependency checks and argument parsing separate from the
core processing logic so the rest of the package stays import-friendly.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

from .processing_core import main
from .ffmpeg_helper import find_ffmpeg_binary


def _ensure_python_dependencies() -> List[str]:
    """Return list of missing Python packages."""
    missing: List[str] = []
    try:
        import ffmpeg  # type: ignore  # noqa: F401
    except ImportError:
        missing.append("ffmpeg-python")
    try:
        import psutil  # type: ignore  # noqa: F401
    except ImportError:
        missing.append("psutil")
    return missing


def _print_python_install_instructions(packages: List[str]) -> None:
    pkg_str = ", ".join(packages)
    print("\n" + "=" * 50)
    print("Python dependency installation guide".center(50))
    print("=" * 50)
    print(f"\nMissing packages: {pkg_str}")
    print("\nRecommended (all platforms):")
    print("  python -m venv venv")
    print("  # Activate venv, then run:")
    print(f"  pip install {pkg_str}")


def _ensure_system_ffmpeg() -> bool:
    """Check whether an FFmpeg executable is available."""
    candidate = find_ffmpeg_binary() or shutil.which("ffmpeg")
    if candidate:
        try:
            subprocess.check_call(
                [candidate, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    return False


def _print_ffmpeg_instructions() -> None:
    system = platform.system()
    print("\n⚠️  FFmpeg is required but was not detected.")
    if system == "Linux":
        print("  sudo apt update && sudo apt install -y ffmpeg  # Debian/Ubuntu")
        print("  sudo dnf install -y ffmpeg                      # Fedora/RHEL")
    elif system == "Darwin":
        print("  brew install ffmpeg")
    elif system == "Windows":
        print("  choco install ffmpeg  # or download from https://ffmpeg.org/download.html")
        print("  Ensure ffmpeg.exe is available in PATH")
    else:
        print("  Please install from https://ffmpeg.org/download.html and update PATH.")


def check_dependencies(interactive: bool = True) -> None:
    """Ensure Python deps and FFmpeg exist. Exit if user declines to continue."""
    missing = _ensure_python_dependencies()
    if missing:
        _print_python_install_instructions(missing)
        if not interactive:
            raise SystemExit(1)
        response = input("\nContinue without installing missing packages? (y/N): ").strip().lower()
        if response != "y":
            raise SystemExit(1)

    if not _ensure_system_ffmpeg():
        _print_ffmpeg_instructions()
        if not interactive:
            raise SystemExit(1)
        response = input("\nContinue without FFmpeg? (y/N): ").strip().lower()
        if response != "y":
            raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MKV Processor CLI")
    parser.add_argument("folder", nargs="?", help="Folder containing MKV files")
    parser.add_argument("--force", action="store_true", help="Ignore history and process everything")
    parser.add_argument("--dry-run", action="store_true", help="Inspect files without processing")
    return parser


def run_cli(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    check_dependencies(interactive=True)

    if args.folder:
        main(args.folder, force_reprocess=args.force, dry_run=args.dry_run)
    else:
        main(force_reprocess=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    run_cli()

