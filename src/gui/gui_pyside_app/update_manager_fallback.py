"""
Fallback UpdateManager for bundled GUI when mkvprocessor.update_manager cannot be imported.

This is a direct copy of src/mkvprocessor/update_manager.py to ensure the
update feature still works inside PyInstaller bundles even if the package
isn't collected properly.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import requests

# Fallback version if cannot get from anywhere
FALLBACK_VERSION = "unknown"

# GitHub repository info
GITHUB_REPO = "HThanh-how/mkvprocesser"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"


class UpdateManager:
    """Manages application updates from GitHub Releases."""
    
    def __init__(self):
        self.repo = GITHUB_REPO
        self.api_url = GITHUB_API_URL
        self.releases_url = GITHUB_RELEASES_URL
        self._current_version = None  # Lazy load
        self._prefer_beta = False  # Default to stable releases
        
    def _get_version_from_file(self) -> Optional[str]:
        """Try to get version from bundled version.txt file."""
        try:
            # Check if running from PyInstaller bundle
            if hasattr(sys, '_MEIPASS'):
                version_file = Path(sys._MEIPASS) / "version.txt"
            else:
                # Running from source - check project root
                version_file = Path(__file__).parent.parent.parent / "version.txt"
            
            if version_file.exists():
                version = version_file.read_text(encoding='utf-8').strip()
                if version:
                    return version.lstrip('vV')
        except Exception:
            pass
        return None
    
    def _get_version_from_git(self) -> Optional[str]:
        """Try to get version from git tag."""
        try:
            project_root = Path(__file__).parent.parent.parent
            
            # First, try to get exact tag if we're on a tag
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=project_root
            )
            if result.returncode == 0:
                tag = result.stdout.strip().lstrip('vV')
                if tag:
                    return tag
            
            # If not on exact tag, try to get latest tag
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=project_root
            )
            if result.returncode == 0:
                tag = result.stdout.strip().lstrip('vV')
                if tag:
                    return tag
        except Exception:
            pass
        return None
    
    def _get_version_from_github_latest(self) -> Optional[str]:
        """Get latest version from GitHub releases (not current, but latest available)."""
        try:
            response = requests.get(self.api_url, timeout=5)
            response.raise_for_status()
            release_data = response.json()
            tag_name = release_data.get("tag_name", "")
            if tag_name:
                return tag_name.lstrip('vV')
        except Exception:
            pass
        return None
    
    def get_current_version(self) -> str:
        """
        Get current application version.
        Priority:
        1. version.txt file (bundled with executable)
        2. Git tag (for development builds)
        3. GitHub latest release (assume we're running latest)
        4. Fallback to "unknown"
        """
        if self._current_version is None:
            # 1. Try version.txt file first (most reliable - bundled with executable)
            version = self._get_version_from_file()
            
            # 2. Try git tag (for development builds)
            if not version:
                version = self._get_version_from_git()
            
            # 3. Try GitHub latest release (assume we're running latest if no version file)
            if not version:
                version = self._get_version_from_github_latest()
            
            # 4. Fallback
            if not version:
                version = FALLBACK_VERSION
            
            self._current_version = version
        
        return self._current_version
    
    def parse_version(self, version_str: str) -> Tuple[int, ...]:
        """
        Parse version string to tuple for comparison.
        
        Examples:
            "1.11.28.11" -> (1, 11, 28, 11)
            "1.11.28.beta-11" -> (1, 11, 28, -1, 11)  # beta = -1
            "v1.2.3" -> (1, 2, 3)
        """
        # Remove 'v' prefix if present
        version_str = version_str.lstrip('vV')
        
        # Handle beta versions: "1.11.28.beta-11" -> split by "beta-"
        is_beta = False
        beta_number = 0
        if '.beta-' in version_str.lower():
            parts_beta = version_str.lower().split('.beta-')
            version_str = parts_beta[0]  # "1.11.28"
            is_beta = True
            if len(parts_beta) > 1:
                try:
                    beta_number = int(parts_beta[1])  # "11"
                except ValueError:
                    beta_number = 0
        
        # Split by dots and convert to int
        parts = version_str.split('.')
        try:
            version_tuple = tuple(int(part) for part in parts)
            # Append beta indicator: -1 for beta, then beta number
            if is_beta:
                version_tuple = version_tuple + (-1, beta_number)
            return version_tuple
        except ValueError:
            # If parsing fails, return (0,)
            return (0,)
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings.
        
        Returns:
            -1 if version1 < version2
            0 if version1 == version2
            1 if version1 > version2
        """
        v1 = self.parse_version(version1)
        v2 = self.parse_version(version2)
        
        # Compare tuples
        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        else:
            return 0
    
    def set_prefer_beta(self, prefer_beta: bool):
        """Set whether to prefer beta releases over stable."""
        self._prefer_beta = prefer_beta
    
    def check_for_updates(self, timeout: int = 10, prefer_beta: Optional[bool] = None):
        """
        Check for available updates from GitHub Releases.
        
        Returns: (has_update, release_info)
        """
        try:
            want_beta = prefer_beta if prefer_beta is not None else self._prefer_beta
            
            if want_beta:
                response = requests.get(self.releases_url, timeout=timeout)
                response.raise_for_status()
                releases = response.json()
                beta_releases = [
                    r for r in releases 
                    if "beta" in r.get("tag_name", "").lower() or "beta" in r.get("name", "").lower()
                ]
                if not beta_releases:
                    response = requests.get(self.api_url, timeout=timeout)
                    response.raise_for_status()
                    release_data = response.json()
                else:
                    release_data = beta_releases[0]
            else:
                response = requests.get(self.api_url, timeout=timeout)
                response.raise_for_status()
                release_data = response.json()
            
            latest_version = release_data.get("tag_name", "").lstrip('vV')
            if not latest_version:
                return False, None
            
            current_version = self.get_current_version()
            comparison = self.compare_versions(current_version, latest_version)
            
            if comparison < 0:
                is_beta = "beta" in latest_version.lower() or "beta" in release_data.get("name", "").lower()
                return True, {
                    "tag_name": release_data.get("tag_name", ""),
                    "version": latest_version,
                    "name": release_data.get("name", ""),
                    "body": release_data.get("body", ""),
                    "html_url": release_data.get("html_url", ""),
                    "published_at": release_data.get("published_at", ""),
                    "assets": release_data.get("assets", []),
                    "is_beta": is_beta,
                    "prerelease": release_data.get("prerelease", False),
                }
            else:
                return False, None
        except requests.exceptions.RequestException as e:
            print(f"[UPDATE] Error checking for updates: {e}")
            return False, None
        except Exception as e:
            print(f"[UPDATE] Unexpected error: {e}")
            return False, None
    
    def find_exe_asset(self, assets: list):
        """Find the executable asset for current platform."""
        system = platform.system().lower()
        
        for asset in assets:
            name = asset.get("name", "").lower()
            if system == "windows" and name.endswith(".exe"):
                return asset
            elif system == "darwin" and (name.endswith(".app") or name.endswith(".dmg")):
                return asset
            elif system == "linux" and (name.endswith(".bin") or not name.endswith(".exe")):
                return asset
        return None
    
    def download_update(self, asset: dict, progress_callback=None):
        """Download update file to temporary location."""
        download_url = asset.get("browser_download_url")
        if not download_url:
            return None
        
        file_name = asset.get("name", "update.exe")
        file_size = asset.get("size", 0)
        
        try:
            temp_dir = Path(tempfile.gettempdir()) / "mkvprocessor_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            download_path = temp_dir / file_name
            print(f"[UPDATE] Downloading {file_name} ({file_size / 1024 / 1024:.2f} MB)...")
            
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', file_size))
            downloaded = 0
            
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(download_url, downloaded, total_size)
                        elif downloaded % (1024 * 1024) == 0:
                            print(f"[UPDATE] Downloaded {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB")
            
            print(f"[UPDATE] Download complete: {download_path}")
            return download_path
        except Exception as e:
            print(f"[UPDATE] Error downloading update: {e}")
            return None
    
    def install_update(self, update_file: Path) -> bool:
        """Install the update by replacing current executable."""
        if not update_file.exists():
            return False
        
        try:
            if hasattr(sys, '_MEIPASS'):
                current_exe = Path(sys.executable)
            else:
                print("[UPDATE] Cannot update when running from source")
                return False
            
            if not current_exe.exists():
                print(f"[UPDATE] Current executable not found: {current_exe}")
                return False
            
            if platform.system() == "Windows":
                return self._install_update_windows(current_exe, update_file)
            else:
                backup_path = current_exe.parent / f"{current_exe.stem}_backup{current_exe.suffix}"
                print(f"[UPDATE] Creating backup: {backup_path}")
                shutil.copy2(current_exe, backup_path)
                print(f"[UPDATE] Installing update: {current_exe}")
                shutil.copy2(update_file, current_exe)
                os.chmod(current_exe, 0o755)
                print("[UPDATE] Update installed successfully!")
                print(f"[UPDATE] Backup saved at: {backup_path}")
                return True
        except Exception as e:
            print(f"[UPDATE] Error installing update: {e}")
            return False
    
    def _install_update_windows(self, current_exe: Path, update_file: Path) -> bool:
        """Install update on Windows using a batch script."""
        try:
            backup_path = current_exe.parent / f"{current_exe.stem}_backup{current_exe.suffix}"
            print(f"[UPDATE] Creating backup: {backup_path}")
            shutil.copy2(current_exe, backup_path)
            
            batch_script = current_exe.parent / "update_installer.bat"
            with open(batch_script, 'w') as f:
                f.write("@echo off\n")
                f.write("timeout /t 2 /nobreak >nul\n")
                f.write(f'copy /Y "{update_file}" "{current_exe}"\n')
                f.write(f'if %ERRORLEVEL% EQU 0 (\n')
                f.write(f'    del "{batch_script}"\n')
                f.write(f'    start "" "{current_exe}"\n')
                f.write(f')\n')
            
            subprocess.Popen(
                [str(batch_script)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                shell=True
            )
            
            print("[UPDATE] Update will be installed after application closes")
            print(f"[UPDATE] Backup saved at: {backup_path}")
            return True
        except Exception as e:
            print(f"[UPDATE] Error creating update script: {e}")
            return False
    
    def restart_application(self) -> None:
        """Restart the application after update."""
        try:
            exe_path = sys.executable
            if platform.system() == "Windows":
                subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen([exe_path])
            sys.exit(0)
        except Exception as e:
            print(f"[UPDATE] Error restarting application: {e}")

