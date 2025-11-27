"""
Git utility functions for MKV Processor.

Handles Git executable finding, downloading, and command execution.
"""
import logging
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

import requests

from ..config_manager import get_config_dir

logger = logging.getLogger(__name__)

# Windows flag to hide console window
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0

GIT_RELEASE_API = "https://api.github.com/repos/git-for-windows/git/releases/latest"
GIT_CACHED_PATH: Optional[str] = None


def run_git_command(git_cmd: str, args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run git command with console window hidden on Windows.
    
    Args:
        git_cmd: Path to git executable
        args: List of arguments to pass to git
        **kwargs: Additional arguments for subprocess.run
    
    Returns:
        CompletedProcess object from subprocess.run
    """
    kwargs.setdefault('capture_output', True)
    if platform.system() == "Windows":
        kwargs.setdefault('creationflags', CREATE_NO_WINDOW)
    return subprocess.run([git_cmd] + args, **kwargs)


def find_git_executable() -> Optional[str]:
    """Find git executable path (portable or system).
    
    Search order:
    1. GIT_PORTABLE_PATH environment variable
    2. Portable git in config directory
    3. Portable git bundled with executable
    4. System git in PATH
    
    Returns:
        Path to git executable as string, or None if not found
    """
    git_env = os.getenv("GIT_PORTABLE_PATH")
    if git_env:
        git_env_path = Path(git_env)
        if git_env_path.is_dir():
            git_env_path = git_env_path / "bin" / ("git.exe" if os.name == "nt" else "git")
        if git_env_path.exists():
            return str(git_env_path)

    # Check portable git downloaded in config dir (IMPORTANT!)
    config_git_dir = get_config_dir() / "git_portable"
    possible_paths = [
        config_git_dir / "cmd" / "git.exe",
        config_git_dir / "bin" / "git.exe",
        config_git_dir / "mingw64" / "bin" / "git.exe",
    ]
    for candidate in possible_paths:
        if candidate.exists():
            return str(candidate)

    # Check portable git in executable (if bundled)
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    portable_git = base_dir / "git_portable" / "bin" / ("git.exe" if os.name == "nt" else "git")
    if portable_git.exists():
        return str(portable_git)

    # Finally check system git
    system_git = shutil.which("git")
    if system_git:
        return system_git
    return None


def download_git_portable() -> Optional[str]:
    """Download MinGit (64-bit) to config directory and return path to git.exe.
    
    Returns:
        Path to git.exe as string, or None if download/extraction fails.
        Only works on Windows (NT).
    """
    if os.name != "nt":
        return None
    tools_dir = get_config_dir() / "git_portable"
    git_exe = tools_dir / "bin" / "git.exe"
    if git_exe.exists():
        return str(git_exe)

    try:
        logger.info("[AUTO-COMMIT] Downloading Git portable...")
        response = requests.get(GIT_RELEASE_API, timeout=30)
        response.raise_for_status()
        release = response.json()
        assets = release.get("assets", [])
        mingit_asset = None
        for asset in assets:
            name = asset.get("name", "")
            if (
                "MinGit" in name
                and "64-bit" in name
                and name.endswith(".zip")
            ):
                mingit_asset = asset
                break
        if not mingit_asset:
            logger.warning("[AUTO-COMMIT] MinGit 64-bit asset not found in latest release.")
            return None

        download_url = mingit_asset.get("browser_download_url")
        if not download_url:
            return None

        tools_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip = tools_dir / "mingit.zip"
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        temp_extract = tools_dir / "_tmp_extract"
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        with zipfile.ZipFile(tmp_zip, "r") as zip_ref:
            zip_ref.extractall(temp_extract)
        tmp_zip.unlink(missing_ok=True)

        # Some MinGit versions have a wrapper root directory, move contents up
        candidates = list(temp_extract.iterdir())
        if len(candidates) == 1 and candidates[0].is_dir():
            src_root = candidates[0]
        else:
            src_root = temp_extract

        for item in src_root.iterdir():
            dest = tools_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), dest)
        shutil.rmtree(temp_extract, ignore_errors=True)

        # Check multiple possible locations for git.exe (cmd/, bin/, mingw64/bin/)
        possible_paths = [
            tools_dir / "cmd" / "git.exe",
            tools_dir / "bin" / "git.exe",
            tools_dir / "mingw64" / "bin" / "git.exe",
        ]
        for candidate in possible_paths:
            if candidate.exists():
                logger.info("[AUTO-COMMIT] Successfully downloaded Git portable.")
                return str(candidate)

        logger.error("[AUTO-COMMIT] git.exe not found after extraction.")
        return None
    except (requests.RequestException, IOError, zipfile.BadZipFile) as exc:
        logger.error(f"[AUTO-COMMIT] Failed to download Git portable: {exc}")
        return None


def ensure_git_available() -> Optional[str]:
    """Ensure Git is available, download if needed.
    
    Returns:
        Path to git executable, or None if not available
    """
    git_path = find_git_executable()
    if git_path:
        return git_path
    
    if os.name == "nt":
        return download_git_portable()
    
    return None


def check_git_available() -> bool:
    """Check if Git is available.
    
    Returns:
        True if Git is available, False otherwise
    """
    return find_git_executable() is not None

