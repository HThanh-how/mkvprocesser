"""
Auto-update manager for MKV Processor.
Checks for updates from GitHub Releases and handles download/installation.
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
            import subprocess
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
    
    def check_for_updates(self, timeout: int = 10, prefer_beta: Optional[bool] = None) -> Tuple[bool, Optional[dict]]:
        """
        Check for available updates from GitHub Releases.
        
        Args:
            timeout: Request timeout in seconds
            prefer_beta: If True, check for beta releases. If None, use self._prefer_beta
            
        Returns:
            Tuple of (has_update, release_info)
            - has_update: True if newer version is available
            - release_info: Dict with release info (tag_name, html_url, assets, etc.) or None
        """
        try:
            # Determine if we want beta or stable
            want_beta = prefer_beta if prefer_beta is not None else self._prefer_beta
            
            if want_beta:
                # Get all releases and find latest beta
                response = requests.get(self.releases_url, timeout=timeout)
                response.raise_for_status()
                releases = response.json()
                
                # Filter for beta releases (contain "beta" in tag_name or name)
                beta_releases = [
                    r for r in releases 
                    if "beta" in r.get("tag_name", "").lower() or "beta" in r.get("name", "").lower()
                ]
                
                if not beta_releases:
                    # No beta releases, fall back to latest stable
                    response = requests.get(self.api_url, timeout=timeout)
                    response.raise_for_status()
                    release_data = response.json()
                else:
                    # Get latest beta (first in list, sorted by published_at desc)
                    release_data = beta_releases[0]
            else:
                # Get latest stable release
                response = requests.get(self.api_url, timeout=timeout)
                response.raise_for_status()
                release_data = response.json()
            
            latest_version = release_data.get("tag_name", "").lstrip('vV')
            
            if not latest_version:
                return False, None
            
            # Get current version (may update from GitHub)
            current_version = self.get_current_version()
            
            # Compare versions
            comparison = self.compare_versions(current_version, latest_version)
            
            if comparison < 0:
                # Newer version available
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
                # Already up to date
                return False, None
                
        except requests.exceptions.RequestException as e:
            print(f"[UPDATE] Error checking for updates: {e}")
            return False, None
        except Exception as e:
            print(f"[UPDATE] Unexpected error: {e}")
            return False, None
    
    def find_exe_asset(self, assets: list) -> Optional[dict]:
        """
        Find the executable asset for current platform.
        
        Args:
            assets: List of asset dicts from GitHub API
            
        Returns:
            Asset dict for current platform, or None if not found
        """
        system = platform.system().lower()
        
        for asset in assets:
            name = asset.get("name", "").lower()
            # Look for Windows .exe
            if system == "windows" and name.endswith(".exe"):
                return asset
            # Look for macOS .app or .dmg
            elif system == "darwin" and (name.endswith(".app") or name.endswith(".dmg")):
                return asset
            # Look for Linux binary
            elif system == "linux" and (name.endswith(".bin") or not name.endswith(".exe")):
                return asset
        
        return None
    
    def download_update(self, asset: dict, progress_callback=None) -> Optional[Path]:
        """
        Download update file to temporary location.
        
        Args:
            asset: Asset dict from GitHub API
            progress_callback: Optional callback function(url, downloaded, total) for progress
            
        Returns:
            Path to downloaded file, or None if failed
        """
        download_url = asset.get("browser_download_url")
        if not download_url:
            return None
        
        file_name = asset.get("name", "update.exe")
        file_size = asset.get("size", 0)
        
        try:
            # Create temp directory
            temp_dir = Path(tempfile.gettempdir()) / "mkvprocessor_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            download_path = temp_dir / file_name
            
            print(f"[UPDATE] Downloading {file_name} ({file_size / 1024 / 1024:.2f} MB)...")
            
            # Download with progress
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
                        elif downloaded % (1024 * 1024) == 0:  # Print every MB
                            print(f"[UPDATE] Downloaded {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB")
            
            print(f"[UPDATE] Download complete: {download_path}")
            return download_path
            
        except Exception as e:
            print(f"[UPDATE] Error downloading update: {e}")
            return None
    
    def install_update(self, update_file: Path) -> bool:
        """
        Install the update by replacing current executable.
        
        Args:
            update_file: Path to downloaded update file
            
        Returns:
            True if installation successful, False otherwise
        """
        if not update_file.exists():
            return False
        
        try:
            # Get current executable path
            if hasattr(sys, '_MEIPASS'):
                # Running from PyInstaller bundle
                # Current exe is sys.executable
                current_exe = Path(sys.executable)
            else:
                # Running from source - can't update
                print("[UPDATE] Cannot update when running from source")
                return False
            
            if not current_exe.exists():
                print(f"[UPDATE] Current executable not found: {current_exe}")
                return False
            
            # On Windows, we can't replace a running exe directly
            # We need to use a batch script to do it after exit
            if platform.system() == "Windows":
                return self._install_update_windows(current_exe, update_file)
            else:
                # Unix-like systems
                # Create backup
                backup_path = current_exe.parent / f"{current_exe.stem}_backup{current_exe.suffix}"
                print(f"[UPDATE] Creating backup: {backup_path}")
                shutil.copy2(current_exe, backup_path)
                
                # Replace executable
                print(f"[UPDATE] Installing update: {current_exe}")
                shutil.copy2(update_file, current_exe)
                
                # Make executable
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
            # Create backup
            backup_path = current_exe.parent / f"{current_exe.stem}_backup{current_exe.suffix}"
            print(f"[UPDATE] Creating backup: {backup_path}")
            shutil.copy2(current_exe, backup_path)
            
            # Get working directory (where exe is located)
            exe_dir = current_exe.parent.resolve()  # Use resolve() to get absolute path
            exe_path = current_exe.resolve()
            update_file_path = update_file.resolve()
            
            # Create batch script to replace exe after current process exits
            # Use a separate temp directory to avoid holding files in _MEIPASS
            batch_script = exe_dir / "update_installer.bat"
            with open(batch_script, 'w', encoding='utf-8') as f:
                f.write("@echo off\n")
                f.write("setlocal enabledelayedexpansion\n")  # Enable delayed expansion for variables
                f.write(f'cd /d "{exe_dir}"\n')  # Set working directory
                f.write("\n")
                f.write("REM Wait for application to fully close and PyInstaller cleanup\n")
                f.write("REM Increase wait time to allow PyInstaller to clean up _MEIPASS\n")
                f.write("timeout /t 5 /nobreak >nul\n")  # Wait 5 seconds for app to close and cleanup
                f.write("\n")
                f.write("REM Try to copy update file\n")
                f.write(f'if exist "{update_file_path}" (\n')
                f.write(f'    copy /Y "{update_file_path}" "{exe_path}" >nul 2>&1\n')
                f.write(f'    if !ERRORLEVEL! EQU 0 (\n')
                f.write(f'        REM Delete batch script first\n')
                f.write(f'        del "{batch_script}" >nul 2>&1\n')
                f.write(f'        REM Start application with correct working directory\n')
                f.write(f'        cd /d "{exe_dir}"\n')
                f.write(f'        start "" /D "{exe_dir}" "{exe_path}"\n')
                f.write(f'        exit /b 0\n')
                f.write(f'    ) else (\n')
                f.write(f'        echo Update installation failed: Copy error\n')
                f.write(f'        pause\n')
                f.write(f'        exit /b 1\n')
                f.write(f'    )\n')
                f.write(f') else (\n')
                f.write(f'    echo Update file not found: {update_file_path}\n')
                f.write(f'    pause\n')
                f.write(f'    exit /b 1\n')
                f.write(f')\n')
            
            # Run batch script in background with DETACHED_PROCESS to avoid holding _MEIPASS
            # This ensures the batch script runs independently and doesn't block PyInstaller cleanup
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [str(batch_script)],
                creationflags=subprocess.CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                shell=True,
                cwd=str(exe_dir),  # Set working directory for the batch script
                close_fds=True  # Close file descriptors to avoid holding _MEIPASS files
            )
            
            print("[UPDATE] Update will be installed after application closes")
            print(f"[UPDATE] Backup saved at: {backup_path}")
            print(f"[UPDATE] Update file: {update_file_path}")
            print(f"[UPDATE] Target exe: {exe_path}")
            return True
            
        except Exception as e:
            print(f"[UPDATE] Error creating update script: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def restart_application(self) -> None:
        """Restart the application after update."""
        try:
            if hasattr(sys, '_MEIPASS'):
                # Running from PyInstaller bundle
                exe_path = Path(sys.executable)
            else:
                # Running from source
                exe_path = Path(sys.executable)
            
            # Get working directory (where exe is located)
            exe_dir = exe_path.parent
            
            # Restart with correct working directory
            if platform.system() == "Windows":
                # Use start command with working directory to ensure proper initialization
                subprocess.Popen(
                    ["cmd", "/c", "start", "", "/D", str(exe_dir), str(exe_path)],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.Popen(
                    [str(exe_path)],
                    cwd=str(exe_dir)  # Set working directory
                )
            
            # Exit current instance
            sys.exit(0)
            
        except Exception as e:
            print(f"[UPDATE] Error restarting application: {e}")
            import traceback
            traceback.print_exc()

