"""Legacy API shim for backwards compatibility."""

from __future__ import annotations

from .processing_core import *  # noqa: F401,F403
"""
Main script for MKV video processing.

This module handles video file processing, metadata extraction, subtitle extraction,
and file organization with support for Vietnamese audio/subtitle detection.
"""
import os
import sys
import json
import logging
import subprocess
import platform
import re
import datetime
import tempfile
import io
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple

import requests
import argparse

from .config_manager import load_user_config, get_config_dir
from .github_sync import build_auto_push_config, RemoteSyncManager
from .i18n import set_language, t, get_language
from .log_manager import (
    log_processed_file,
    read_processed_files,
    convert_legacy_log_file,
    write_run_log_snapshot,
    set_remote_sync,
)
from .utils.git_utils import (
    run_git_command,
    find_git_executable,
    download_git_portable,
    ensure_git_available,
    check_git_available,
)
from .utils.file_utils import (
    sanitize_filename,
    get_file_size_gb,
    get_file_size_mb,
    get_file_signature,
    create_folder,
)
from .utils.metadata_utils import (
    get_video_resolution_label,
    get_movie_year,
    get_language_abbreviation,
    get_subtitle_info,
)
from .utils.system_utils import check_ffmpeg_available, check_available_ram
from .utils.temp_utils import temp_directory_in_memory
from .video_processor import (
    rename_simple,
    rename_file,
    process_video,
    extract_video_with_audio,
)
from .subtitle_extractor import extract_subtitle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global variables - these are now managed by log_manager and git_utils
# REMOTE_SYNC is managed by log_manager.set_remote_sync()
# GIT_CACHED_PATH is managed by git_utils

# Windows flag to hide console window
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0



# IMPORTANT: Set FFmpeg binary path BEFORE importing ffmpeg
# ffmpeg-python library will use these environment variables
try:
    from .ffmpeg_helper import find_ffmpeg_binary, find_ffprobe_binary
    ffmpeg_path = find_ffmpeg_binary()
    ffprobe_path = find_ffprobe_binary()
    
    if ffmpeg_path:
        os.environ['FFMPEG_BINARY'] = ffmpeg_path
        # Add to PATH so ffmpeg-python can find it
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
        if ffmpeg_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
    
    if ffprobe_path:
        os.environ['FFPROBE_BINARY'] = ffprobe_path
        # Add to PATH
        ffprobe_dir = os.path.dirname(ffprobe_path)
        if ffprobe_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = ffprobe_dir + os.pathsep + os.environ.get('PATH', '')
except ImportError:
    pass  # If import fails, will use system FFmpeg

# Helper to run FFmpeg with local path if available
def run_ffmpeg_command(cmd: Union[List[str], str], **kwargs) -> subprocess.CompletedProcess:
    """Wrapper for subprocess.run to automatically use local FFmpeg if available and hide console.
    
    Args:
        cmd: FFmpeg command as list of strings or single string
        **kwargs: Additional arguments for subprocess.run
    
    Returns:
        CompletedProcess object from subprocess.run
    """
    try:
        from .ffmpeg_helper import get_ffmpeg_command
        cmd = get_ffmpeg_command(cmd)
    except ImportError:
        pass  # Fallback to original command
    # Hide console window on Windows
    if platform.system() == "Windows":
        kwargs.setdefault('creationflags', CREATE_NO_WINDOW)
    return subprocess.run(cmd, **kwargs)

# Kiểm tra và hướng dẫn cài đặt các package cần thiết
if __name__ == '__main__':
    try:
        # Thử import các module cần thiết
        try:
            import ffmpeg  # type: ignore
            import psutil  # type: ignore
            # Nếu import thành công, tiếp tục chạy script
            print("Đã tìm thấy các thư viện cần thiết.")
        except ImportError as e:
            # Nếu không import được, hiển thị hướng dẫn cài đặt
            print(f"\n{'='*50}")
            print("HƯỚNG DẪN CÀI ĐẶT THƯ VIỆN".center(50))
            print(f"{'='*50}")
            print(f"\nKhông thể tìm thấy thư viện: {e}")
            print("\nVui lòng cài đặt các thư viện cần thiết bằng một trong các cách sau:")
            
            # Hướng dẫn cài đặt trên hệ thống Linux
            if platform.system() == "Linux":
                print("\n--- CHO UBUNTU/DEBIAN ---")
                print("1. Cài đặt python3-pip và ffmpeg:")
                print("   sudo apt update")
                print("   sudo apt install -y python3-pip ffmpeg")
                print("\n2. Cài đặt các thư viện Python:")
                print("   python3 -m pip install ffmpeg-python psutil --user")
                
                print("\n--- CHO FEDORA/RHEL ---")
                print("1. Cài đặt python3-pip và ffmpeg:")
                print("   sudo dnf install -y python3-pip ffmpeg")
                print("\n2. Cài đặt các thư viện Python:")
                print("   python3 -m pip install ffmpeg-python psutil --user")
                
                print("\n--- SỬ DỤNG SNAP (NẾU CÓ) ---")
                print("1. Cài đặt ffmpeg qua snap:")
                print("   sudo snap install ffmpeg")
            
            # Hướng dẫn cài đặt trên MacOS
            elif platform.system() == "Darwin":
                print("\n--- CHO MACOS ---")
                print("1. Cài đặt Homebrew (nếu chưa có):")
                print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                print("\n2. Cài đặt ffmpeg:")
                print("   brew install ffmpeg")
                print("\n3. Cài đặt các thư viện Python:")
                print("   pip3 install ffmpeg-python psutil")
            
            # Hướng dẫn cài đặt trên Windows
            elif platform.system() == "Windows":
                print("\n--- CHO WINDOWS ---")
                print("1. Tải và cài đặt FFmpeg từ trang chủ:")
                print("   https://ffmpeg.org/download.html")
                print("\n2. Thêm đường dẫn FFmpeg vào biến môi trường PATH")
                print("\n3. Cài đặt các thư viện Python:")
                print("   pip install ffmpeg-python psutil")
            
            # Hướng dẫn chung
            print("\n--- CÁCH NHANH NHẤT (TẤT CẢ HỆ ĐIỀU HÀNH) ---")
            print("Sử dụng môi trường ảo (khuyến nghị):")
            print("1. Tạo môi trường ảo:")
            print("   python3 -m venv venv")
            print("\n2. Kích hoạt môi trường ảo:")
            print("   - Linux/MacOS: source venv/bin/activate")
            print("   - Windows: venv\\Scripts\\activate")
            print("\n3. Cài đặt các thư viện:")
            print("   pip install ffmpeg-python psutil")
            print("\n4. Chạy script trong môi trường ảo:")
            print("   python script.py")
            
            print(f"\n{'='*50}")
            print("LƯU Ý: Script này cần FFmpeg để xử lý video.")
            print("Vui lòng đảm bảo FFmpeg đã được cài đặt và có sẵn trong PATH")
            
            sys.exit(1)
            
        # Kiểm tra FFmpeg đã được cài đặt chưa
        try:
            # Sử dụng helper để tìm FFmpeg local
            try:
                from ffmpeg_helper import find_ffmpeg_binary
                ffmpeg_path = find_ffmpeg_binary()
                if ffmpeg_path:
                    subprocess.check_call([ffmpeg_path, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except ImportError:
                subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Đã tìm thấy FFmpeg trên hệ thống.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\nCẢNH BÁO: Không tìm thấy FFmpeg trên hệ thống!")
            print("Script này yêu cầu FFmpeg để xử lý video.")
            
            print("\nHướng dẫn cài đặt FFmpeg:")
            if platform.system() == "Linux":
                print("- Ubuntu/Debian: sudo add-apt-repository universe && sudo apt update && sudo apt install -y ffmpeg")
                print("- Fedora/RHEL: sudo dnf install -y ffmpeg")
                print("- Sử dụng snap: sudo snap install ffmpeg")
            elif platform.system() == "Darwin":
                print("- macOS: brew install ffmpeg")
            elif platform.system() == "Windows":
                print("- Windows: Tải từ https://ffmpeg.org/download.html và thêm vào PATH")
            
            response = input("\nBạn có muốn tiếp tục mà không có FFmpeg không? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
                
        # Nếu mọi thứ đã sẵn sàng, tiếp tục thực hiện script
        print("\nMọi thư viện đã sẵn sàng. Bắt đầu xử lý...")
        
    except Exception as e:
        print(f"Lỗi: {e}")
        sys.exit(1)

# Import các thư viện cần thiết
import ffmpeg  # type: ignore
import psutil  # type: ignore

import re
import datetime
import tempfile
import io
import shutil
from contextlib import contextmanager























# Git functions moved to utils/git_utils.py - these are legacy wrappers


# File size function moved to utils/file_utils.py

def auto_commit_subtitles(subtitle_folder, settings: Optional[Dict[str, Any]] = None):
    """Automatically commit subtitle files and logs to git."""
    git_cmd = check_git_available()
    if not git_cmd:
        return False
    
    # Load settings if not provided
    if settings is None:
        settings = load_user_config()
    
    # Check config
    repo_url = settings.get("repo_url", "").strip()
    branch = settings.get("branch", "main").strip()
    token = settings.get("token", "").strip()
    
    if not repo_url:
        logger.warning("[AUTO-COMMIT] Repo URL not configured. Skipping auto-commit.")
        return False
    
    try:
        # Step 1: Check and copy subtitle files first (ensure files are created)
        subtitle_path = Path(subtitle_folder).resolve()
        if not subtitle_path.exists():
            logger.warning(f"[AUTO-COMMIT] Directory {subtitle_folder} does not exist.")
            return False
        
        # Copy subtitle files to directory (if no git, will copy to current directory)
        logger.info(f"[AUTO-COMMIT] Checking subtitle files...")
        subtitle_files = []
        for root, dirs, files in os.walk(subtitle_path):
            for file in files:
                if file.endswith('.srt'):
                    subtitle_files.append(Path(root) / file)
        
        if not subtitle_files:
            logger.info("[AUTO-COMMIT] No subtitle files to commit.")
            return True
        
        # work_dir is Subtitles/ (not parent directory)
        # Subtitle files will be committed in Subtitles/ on GitHub
        work_dir = subtitle_path
        
        # Step 2: Check if it's a git repository
        result = run_git_command(git_cmd, ['rev-parse', '--git-dir'], cwd=str(work_dir))
        is_git_repo = result.returncode == 0
        
        if not is_git_repo:
            # Create URL with token if available
            if token and "github.com" in repo_url:
                # Format: https://token@github.com/user/repo.git
                url_parts = repo_url.replace("https://", "").replace("http://", "").split("/")
                if len(url_parts) >= 2:
                    auth_url = f"https://{token}@{'/'.join(url_parts)}"
                else:
                    auth_url = repo_url
            else:
                auth_url = repo_url
            
            # Check if directory already exists
            if work_dir.exists():
                # Directory exists -> init git and pull (DON'T clone as it will error)
                logger.info(f"[AUTO-COMMIT] Directory already exists. Initializing git and pulling...")
                try:
                    # Init git repo
                    run_git_command(git_cmd, ['init'], cwd=str(work_dir), check=True)
                    
                    # Add remote (nếu chưa có)
                    remote_check = run_git_command(git_cmd, ['remote', 'get-url', 'origin'], cwd=str(work_dir))
                    if remote_check.returncode != 0:
                        run_git_command(git_cmd, ['remote', 'add', 'origin', auth_url], cwd=str(work_dir), check=True)
                    else:
                        # Nếu remote đã tồn tại, set lại URL
                        run_git_command(git_cmd, ['remote', 'set-url', 'origin', auth_url], cwd=str(work_dir), check=True)
                    
                    # Enable sparse checkout - chỉ pull logs/ và processed_files.log
                    # KHÔNG pull thư mục subtitles/ từ remote để tránh tạo Subtitles/subtitles/
                    run_git_command(git_cmd, ['sparse-checkout', 'init', '--cone'], cwd=str(work_dir), check=True)
                    run_git_command(git_cmd, ['sparse-checkout', 'set', 'logs', 'processed_files.log'], cwd=str(work_dir), check=True)
                    
                    # Fetch và pull
                    run_git_command(git_cmd, ['fetch', 'origin', branch], cwd=str(work_dir), check=True, timeout=60)
                    run_git_command(git_cmd, ['checkout', '-b', branch, f'origin/{branch}'], cwd=str(work_dir), check=False)
                    run_git_command(git_cmd, ['pull', 'origin', branch], cwd=str(work_dir), check=False, timeout=60)
                    
                    logger.info(f"[AUTO-COMMIT] Successfully initialized git and pulled.")
                    
                except Exception as init_err:
                    logger.error(f"[AUTO-COMMIT] Error initializing git: {init_err}")
                    return False
            else:
                # Directory doesn't exist -> clone normally
                logger.info(f"[AUTO-COMMIT] Cloning repo to {work_dir} (sparse: only logs/ and processed_files.log)...")
                try:
                    clone_cmd = [
                        git_cmd, 'clone',
                        '--filter=blob:none',  # Chỉ clone metadata, không clone file lớn
                        '--sparse',
                        '--depth=1',
                        '--branch', branch,
                        auth_url,
                        str(work_dir)
                    ]
                    
                    # Clone với console ẩn
                    clone_kwargs = {'capture_output': True, 'text': True, 'timeout': 120}
                    if platform.system() == "Windows":
                        clone_kwargs['creationflags'] = CREATE_NO_WINDOW
                    clone_result = subprocess.run(clone_cmd, **clone_kwargs)
                    
                    if clone_result.returncode != 0:
                        logger.error(f"[AUTO-COMMIT] Error cloning: {clone_result.stderr}")
                        return False
                    
                    # Sparse checkout only logs/ and processed_files.log (old log)
                    run_git_command(git_cmd, ['sparse-checkout', 'set', 'logs', 'processed_files.log'], cwd=str(work_dir), check=True)
                    
                    logger.info(f"[AUTO-COMMIT] Successfully cloned repo.")
                    
                except Exception as clone_err:
                    logger.error(f"[AUTO-COMMIT] Cannot clone repo: {clone_err}")
                    return False
        else:
            # Already a git repo, pull to update logs/ and processed_files.log
            logger.info(f"[AUTO-COMMIT] Already a git repo. Pulling (only logs/ and processed_files.log)...")
            try:
                run_git_command(git_cmd, ['pull'], cwd=str(work_dir), check=True, timeout=60)
            except Exception:
                pass  # Bỏ qua lỗi pull
        
        # Setup git config
        git_user = settings.get("git_user_name", "MKV Processor Bot")
        git_email = settings.get("git_user_email", "bot@example.com")
        run_git_command(git_cmd, ['config', 'user.name', git_user], cwd=str(work_dir), check=False)
        run_git_command(git_cmd, ['config', 'user.email', git_email], cwd=str(work_dir), check=False)
        
        # Step 3: Convert old processed_files.log to JSON if exists (after git is available)
        processed_log_path = work_dir / "processed_files.log"
        logs_dir = work_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if processed_files.log exists in git but was deleted locally
        deleted_log_file = None
        if processed_log_path.exists():
            logger.info("[AUTO-COMMIT] Detected old processed_files.log. Converting to JSON...")
            try:
                converted = convert_legacy_log_file(processed_log_path, logs_dir)
                if converted:
                    logger.info(f"[AUTO-COMMIT] Converted old log to {converted.name}")
                    # File was deleted after convert, need to add to staging
                    deleted_log_file = "processed_files.log"
            except Exception as convert_err:
                logger.error(f"[AUTO-COMMIT] Error converting old log: {convert_err}")
        else:
            # Check if file exists in git but was deleted locally
            check_result = run_git_command(git_cmd, ['ls-files', 'processed_files.log'], cwd=str(work_dir))
            if check_result.returncode == 0 and check_result.stdout.strip():
                # File exists in git but not locally (was deleted)
                deleted_log_file = "processed_files.log"
        
        # Step 4: Get list of subtitle and log files to commit
        # Subtitle files are in Subtitles directory (work_dir = subtitle_path)
        subtitle_files_to_commit = []
        log_files = []
        skipped_files = []
        
        # Get .srt (subtitle) files in Subtitles directory (work_dir)
        for file_path in work_dir.glob("*.srt"):
            if file_path.is_file():
                file_size_mb = get_file_size_mb(str(file_path))
                
                if file_size_mb < 1.0:  # < 1MB
                    # Relative path from work_dir (Subtitles/) to subtitle file
                    # Result: just filename (file.srt), no subdirectories
                    relative_path = file_path.relative_to(work_dir)
                    subtitle_files_to_commit.append((str(relative_path), file_path.stem))
                else:
                    skipped_files.append((file_path.name, file_size_mb))
        
        # Get JSON log files in logs/ directory
        logs_dir = work_dir / "logs"
        if logs_dir.exists():
            for file_path in logs_dir.glob("*.json"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(work_dir)
                    log_files.append(str(relative_path))
        
        files_to_commit = [f[0] for f in subtitle_files_to_commit] + log_files
        
        if not files_to_commit:
            logger.info("[AUTO-COMMIT] No files to commit.")
            return True
        
        logger.info(f"\n=== AUTO-COMMIT SUBTITLES & LOGS ===")
        logger.info(f"Will commit {len(subtitle_files_to_commit)} subtitle(s) and {len(log_files)} log file(s):")
        for file_path, movie_name in subtitle_files_to_commit:
            logger.info(f"  - {file_path} ({movie_name})")
        for file_path in log_files:
            logger.info(f"  - {file_path}")
        
        if skipped_files:
            logger.info(f"\nSkipping {len(skipped_files)} subtitle file(s) >= 1MB:")
            for file_name, size_mb in skipped_files:
                logger.info(f"  - {file_name} ({size_mb:.2f} MB)")
        
        # Add files to git (including deleted file if any)
        if deleted_log_file:
            # Add deleted file to staging
            rm_result = run_git_command(git_cmd, ['rm', deleted_log_file], cwd=str(work_dir))
            if rm_result.returncode != 0:
                # If rm fails, try add to stage deletion
                add_result = run_git_command(git_cmd, ['add', deleted_log_file], cwd=str(work_dir))
                if add_result.returncode != 0:
                    logger.warning(f"[AUTO-COMMIT] Warning: Cannot stage deleted file {deleted_log_file}")
        
        # Add new files
        for file_path in files_to_commit:
            add_result = run_git_command(git_cmd, ['add', file_path], cwd=str(work_dir))
            if add_result.returncode != 0:
                err_text = add_result.stderr.decode('utf-8', errors='replace') if add_result.stderr else "Unknown error"
                logger.error(f"[AUTO-COMMIT] Error adding file {file_path}: {err_text}")
                return False
        
        # Check if there are changes to commit
        status_result = run_git_command(git_cmd, ['status', '--porcelain'], cwd=str(work_dir))
        status_text = status_result.stdout.decode('utf-8', errors='replace').strip() if status_result.stdout else ""
        
        if not status_text:
            logger.info("[AUTO-COMMIT] No new changes to commit.")
            return True
        
        # Check if any files are staged (starting with A, M, D, R)
        staged_changes = [line for line in status_text.split('\n') if line and line[0] in 'AMD R']
        if not staged_changes:
            logger.info("[AUTO-COMMIT] No files staged for commit.")
            logger.debug(f"[DEBUG] Git status: {status_text}")
            return True
        
        # Tạo commit message chi tiết với ngày và danh sách phim
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Lấy tên phim từ file subtitle (bỏ đuôi .srt và các phần không cần thiết)
        movie_names = []
        language_suffixes = ['_vie', '_eng', '_chi', '_jpn', '_kor', '_und', '_fre', '_spa', '_ger', 
                            '_fra', '_deu', '_ita', '_rus', '_tha', '_ind', '_msa', '_ara', '_hin', 
                            '_por', '_nld', '_pol', '_tur', '_swe', '_nor', '_dan', '_fin', '_ukr',
                            '_ces', '_hun', '_ron', '_bul', '_hrv', '_srp', '_slv', '_ell', '_heb',
                            '_kat', '_lat', '_cmn', '_yue', '_nan', '_khm', '_lao', '_mya', '_ben',
                            '_tam', '_tel', '_mal', '_kan', '_mar', '_pan', '_guj', '_ori', '_asm',
                            '_urd', '_fas', '_pus', '_kur']
        
        for _, movie_name in subtitle_files_to_commit:
            # Làm sạch tên phim: bỏ các phần như _vie, _eng, etc.
            clean_name = movie_name
            # Bỏ các suffix ngôn ngữ (case-insensitive)
            for suffix in language_suffixes:
                if clean_name.lower().endswith(suffix.lower()):
                    clean_name = clean_name[:-len(suffix)]
                    break  # Chỉ bỏ 1 suffix đầu tiên tìm thấy
            # Nếu tên quá dài, rút gọn
            if len(clean_name) > 50:
                clean_name = clean_name[:47] + "..."
            if clean_name:  # Chỉ thêm nếu tên không rỗng
                movie_names.append(clean_name)
        
        # Loại bỏ trùng lặp nhưng giữ thứ tự
        seen = set()
        unique_movie_names = []
        for name in movie_names:
            if name not in seen:
                seen.add(name)
                unique_movie_names.append(name)
        movie_names = unique_movie_names
        
        # Create clear commit message
        if subtitle_files_to_commit:
            if len(movie_names) == 1:
                commit_message = f"📅 {current_date} | 🎬 {movie_names[0]} | {len(subtitle_files_to_commit)} subtitle(s)"
            elif len(movie_names) <= 3:
                movies_str = ", ".join(movie_names)
                commit_message = f"📅 {current_date} | 🎬 {movies_str} | {len(subtitle_files_to_commit)} subtitle(s)"
            else:
                movies_str = ", ".join(movie_names[:3]) + f" and {len(movie_names) - 3} more"
                commit_message = f"📅 {current_date} | 🎬 {movies_str} | {len(subtitle_files_to_commit)} subtitle(s)"
            
            if log_files:
                commit_message += f" + {len(log_files)} log file(s)"
        else:
            commit_message = f"📅 {current_date} | 📝 Update {len(log_files)} log file(s)"
        
        commit_message += f" | ⏰ {current_time}"
        
        commit_result = run_git_command(git_cmd, ['commit', '-m', commit_message], cwd=str(work_dir))
        
        if commit_result.returncode == 0:
            logger.info(f"✅ Successfully committed: {commit_message}")
            
            # Try push, if conflict then auto-resolve
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    push_result = run_git_command(git_cmd, ['push'], cwd=str(work_dir), timeout=60)
                    if push_result.returncode == 0:
                        logger.info("✅ Successfully pushed to remote repository.")
                        return True
                    else:
                        # Get error message from both stderr and stdout
                        err_parts = []
                        if push_result.stderr:
                            err_parts.append(push_result.stderr.decode('utf-8', errors='replace').strip())
                        if push_result.stdout:
                            stdout_text = push_result.stdout.decode('utf-8', errors='replace').strip()
                            if stdout_text and stdout_text not in err_parts:
                                err_parts.append(stdout_text)
                        err_msg = " | ".join(err_parts) if err_parts else f"Exit code: {push_result.returncode}"
                        
                        if "conflict" in err_msg.lower() or "non-fast-forward" in err_msg.lower():
                            logger.info(f"[AUTO-COMMIT] Conflict detected. Pulling and merging (attempt {attempt + 1}/{max_retries})...")
                            # Pull to merge
                            pull_result = run_git_command(git_cmd, ['pull', '--no-edit'], cwd=str(work_dir), timeout=60)
                            if pull_result.returncode == 0:
                                # Commit again after merge
                                commit_result = run_git_command(git_cmd, ['commit', '-m', commit_message], cwd=str(work_dir))
                                if commit_result.returncode == 0:
                                    continue  # Try push again
                            else:
                                # If merge fails, use strategy ours to keep local version
                                logger.warning("[AUTO-COMMIT] Merge failed. Using strategy ours...")
                                run_git_command(git_cmd, ['pull', '--strategy=ours', '--no-edit'], cwd=str(work_dir), timeout=60)
                                continue
                        else:
                            logger.warning(f"⚠️ Commit successful but cannot push: {err_msg}")
                            return False
                except Exception as push_err:
                    logger.error(f"⚠️ Error pushing: {push_err}")
                    if attempt < max_retries - 1:
                        logger.info(f"[AUTO-COMMIT] Retrying...")
                        continue
                    return False
            
            logger.error("⚠️ Cannot push after multiple attempts.")
            return False
        else:
            # Get error message from both stderr and stdout
            err_parts = []
            if commit_result.stderr:
                err_parts.append(commit_result.stderr.decode('utf-8', errors='replace').strip())
            if commit_result.stdout:
                stdout_text = commit_result.stdout.decode('utf-8', errors='replace').strip()
                if stdout_text and stdout_text not in err_parts:
                    err_parts.append(stdout_text)
            err_msg = " | ".join(err_parts) if err_parts else f"Exit code: {commit_result.returncode}"
            
            logger.error(f"❌ Error committing (returncode={commit_result.returncode}): {err_msg}")
            
            # Debug: Check git status to see if any files need committing
            status_result = run_git_command(git_cmd, ['status', '--short'], cwd=str(work_dir))
            if status_result.stdout:
                status_text = status_result.stdout.decode('utf-8', errors='replace').strip()
                if status_text:
                    logger.debug(f"[DEBUG] Git status: {status_text}")
            
            return False
            
    except Exception as e:
        logger.error(f"Error during auto-commit: {e}")
        return False

def main(input_folder=None, force_reprocess: Optional[bool] = None, dry_run: bool = False):
    """
    Main function for video processing.
    
    Args:
        input_folder: Directory containing MKV files to process.
                     If None, uses current directory.
        force_reprocess: Force reprocessing of all files, ignoring logs
        dry_run: Only list file status without processing
    """
    # Load user config and set language
    settings = load_user_config()
    language = settings.get("language", "en")
    set_language(language)
    
    if not check_ffmpeg_available():
        logger.error(t("errors.ffmpeg_not_found"))
        return
    
    # Use specified folder or current directory
    if input_folder is None:
        input_folder = "."
    
    # Ensure absolute path
    input_folder = os.path.abspath(input_folder)
    
    # Change working directory if needed
    original_cwd = os.getcwd()
    need_restore_cwd = False
    if input_folder != original_cwd:
        os.chdir(input_folder)
        need_restore_cwd = True
        logger.info(f"Changed to directory: {input_folder}")
    
    # Use i18n for folder names
    from .i18n import t
    vn_folder = t("folders.vietnamese_audio")
    original_folder = t("folders.original")
    subtitle_folder = os.path.join(".", t("folders.subtitles"))
    log_file = os.path.join(subtitle_folder, "processed_files.log")

    # Create necessary directories
    create_folder(vn_folder)
    create_folder(original_folder)
    create_folder(subtitle_folder)

    # Check disk space
    try:
        disk_usage = shutil.disk_usage(".")
        total_gb = disk_usage.total / (1024**3)
        free_gb = disk_usage.free / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        percent_free = (free_gb / total_gb) * 100
        
        logger.info(f"=== SYSTEM INFORMATION ===")
        logger.info(f"Disk:")
        logger.info(f"  Total capacity: {total_gb:.2f} GB")
        logger.info(f"  Used: {used_gb:.2f} GB")
        logger.info(f"  Free: {free_gb:.2f} GB ({percent_free:.1f}%)")
        
        if percent_free < 10:
            logger.warning("\nWARNING: Very little free disk space remaining. May encounter errors when processing large files.")
    except Exception as e:
        logger.error(f"Cannot check disk space: {e}")

    # Check and display RAM information
    available_ram = check_available_ram()
    logger.info(f"\nAvailable RAM: {available_ram:.2f} GB")
    
    # Check space in /dev/shm if available
    if os.path.exists('/dev/shm'):
        try:
            shm_usage = shutil.disk_usage('/dev/shm')
            shm_free_gb = shm_usage.free / (1024**3)
            shm_total_gb = shm_usage.total / (1024**3)
            logger.info(f"RAM disk (/dev/shm): {shm_total_gb:.2f} GB, free: {shm_free_gb:.2f} GB")
        except Exception as e:
            logger.error(f"Cannot check /dev/shm: {e}")
    
    # Display processing strategy information
    logger.info(f"\n=== PROCESSING STRATEGY ===")
    logger.info(f"1. Prioritize RAM processing for optimal speed")
    logger.info(f"2. If sufficient RAM (200% of file size), will process in RAM")
    logger.info(f"3. If RAM processing fails, will automatically switch to disk processing")
    logger.info(f"4. Extract subtitles directly to destination folder")
    logger.info(f"======================\n")

    # Read list of processed files
    if force_reprocess:
        processed_files, processed_signatures = {}, {}
        logger.info("[FORCE] Ignoring old log – will reprocess all files in directory.")
    else:
        processed_files, processed_signatures = read_processed_files(log_file)

    # Load user configuration
    # If force_reprocess is passed, override value from config
    if force_reprocess is not None:
        settings["force_reprocess"] = force_reprocess

    logs_dir = Path(settings.get("logs_dir", "logs"))

    # Initialize GitHub sync if configured
    from .log_manager import set_remote_sync
    remote_entries = []
    auto_config = build_auto_push_config(settings)
    if auto_config:
        logger.info("\n[AUTO PUSH] GitHub subtitle sync enabled.")
        remote_sync = RemoteSyncManager(auto_config)
        set_remote_sync(remote_sync)
        # Convert legacy log on remote if exists
        remote_sync.convert_remote_legacy_log()
        remote_entries = remote_sync.load_remote_logs()
        if remote_entries:
            logs_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = logs_dir / f"remote_sync_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            snapshot_path.write_text(json.dumps(remote_entries, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[AUTO PUSH] Saved log from repo at {snapshot_path}")
        if not force_reprocess:
            for entry in remote_entries:
                if entry.get("category") != "video":
                    continue
                info = {
                    "new_name": entry.get("new_name", ""),
                    "time": entry.get("timestamp", ""),
                    "signature": entry.get("signature", ""),
                }
                processed_files[entry.get("old_name", "")] = info
                signature = entry.get("signature")
                if signature:
                    processed_signatures[signature] = info
    else:
        set_remote_sync(None)

    # If local still has old log -> convert
    legacy_json = convert_legacy_log_file(Path(log_file), logs_dir)
    if legacy_json and legacy_json.exists() and not force_reprocess:
        try:
            legacy_entries = json.loads(legacy_json.read_text(encoding="utf-8"))
            for entry in legacy_entries:
                info = {
                    "new_name": entry.get("new_name", ""),
                    "time": entry.get("timestamp", ""),
                    "signature": entry.get("signature", ""),
                }
                processed_files[entry.get("old_name", "")] = info
                signature = entry.get("signature")
                if signature:
                    processed_signatures[signature] = info
        except Exception as exc:
            logger.error(f"[LOG] Cannot read converted log: {exc}")

    # Read file options from GUI
    file_options_map = {}  # {file_path: options_dict}
    options_env = os.environ.get("MKV_FILE_OPTIONS")
    if options_env:
        try:
            options_data = json.loads(options_env)
            for file_path, opts in options_data.items():
                file_options_map[os.path.abspath(file_path)] = opts
        except json.JSONDecodeError:
            logger.warning("[GUI] Cannot parse file options. Will use defaults.")

    try:
        mkv_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".mkv")]
        selected_env = os.environ.get("MKV_SELECTED_FILES")
        if selected_env:
            try:
                selected_paths = json.loads(selected_env)
                selected_abs = {os.path.abspath(path) for path in selected_paths}
                mkv_files = [
                    f for f in mkv_files
                    if os.path.abspath(os.path.join(input_folder, f)) in selected_abs
                ]
            except json.JSONDecodeError:
                logger.warning("[GUI] Cannot parse selected file list. Will process all.")
        if not mkv_files:
            logger.warning(t("messages.no_files_found"))
            return

        total_files = len(mkv_files)
        for file_idx, mkv_file in enumerate(mkv_files, 1):
            file_path = os.path.join(input_folder, mkv_file)
            logger.info(t("messages.processing_file", current=file_idx, total=total_files, filename=mkv_file))
            logger.info(f"\n===== PROCESSING FILE: {file_path} =====")
            
            # Hiển thị kích thước file
            file_size = get_file_size_gb(file_path)
            
            # Kiểm tra file đã xử lý bằng tên và signature
            file_signature = get_file_signature(file_path)
            file_abs_path = os.path.abspath(file_path)
            file_opts = file_options_map.get(file_abs_path, {})
            rename_enabled = file_opts.get("rename_enabled", False)
            force_rename = file_opts.get("force_process", False) or rename_enabled
            
            # If file already processed but only needs rename (no force_reprocess), still continue
            skip_file = False
            if not force_reprocess and not force_rename:
                if mkv_file in processed_files:
                    logger.info(f"File {mkv_file} already processed as {processed_files[mkv_file]['new_name']} at {processed_files[mkv_file]['time']}. Skipping.")
                    skip_file = True
                elif file_signature and file_signature in processed_signatures:
                    logger.info(f"File {mkv_file} has same content as already processed file {processed_signatures[file_signature]['new_name']}. Skipping.")
                    skip_file = True
            elif mkv_file in processed_files and rename_enabled:
                # File already processed but only needs rename, skip extract but still rename
                logger.info(f"File {mkv_file} already processed. Only performing rename as requested...")
                skip_file = False  # Don't skip, will rename at end
                skip_extract = True  # Skip extract, only rename
            else:
                skip_extract = False
            
            if skip_file:
                continue

            # Check free disk space before processing
            try:
                disk_usage = shutil.disk_usage(".")
                free_gb = disk_usage.free / (1024**3)
                if free_gb < file_size * 1.5:
                    logger.warning(f"WARNING: Insufficient free disk space for safe processing. Need at least {file_size * 1.5:.2f} GB, currently have {free_gb:.2f} GB")
                    if not dry_run:
                        response = input("Do you want to continue despite possible errors? (y/n): ")
                        if response.lower() != 'y':
                            logger.info("Skipping this file.")
                            continue
            except Exception as e:
                logger.error(f"Cannot check disk space: {e}")

            # Read file information once
            try:
                probe_data = ffmpeg.probe(file_path)
                audio_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'audio']
                subtitle_streams = [stream for stream in probe_data['streams'] if stream['codec_type'] == 'subtitle']
                
                # Print stream information for user
                logger.debug("\nStream information:")
                logger.debug("- Video streams:")
                for i, stream in enumerate([s for s in probe_data['streams'] if s['codec_type'] == 'video']):
                    width = stream.get('width', 'N/A')
                    height = stream.get('height', 'N/A')
                    codec = stream.get('codec_name', 'N/A')
                    logger.debug(f"  Stream #{i}: {codec}, {width}x{height}")
                
                logger.debug("- Audio streams:")
                for i, stream in enumerate(audio_streams):
                    lang = stream.get('tags', {}).get('language', 'und')
                    title = stream.get('tags', {}).get('title', '')
                    channels = stream.get('channels', 'N/A')
                    codec = stream.get('codec_name', 'N/A')
                    lang_display = f"{get_language_abbreviation(lang)}"
                    if title:
                        lang_display += f" - {title}"
                    logger.debug(f"  Stream #{stream.get('index', i)}: {codec}, {channels} channels, {lang_display}")
                
                logger.debug("- Subtitle streams:")
                for i, stream in enumerate(subtitle_streams):
                    lang = stream.get('tags', {}).get('language', 'und')
                    title = stream.get('tags', {}).get('title', '')
                    codec = stream.get('codec_name', 'N/A')
                    lang_display = f"{get_language_abbreviation(lang)}"
                    if title:
                        lang_display += f" - {title}"
                    logger.debug(f"  Stream #{stream.get('index', i)}: {codec}, {lang_display}")
                
            except Exception as e:
                logger.error(f"Error reading file information {file_path}: {e}")
                # If cannot read file information, only rename if rename_enabled = True
                if rename_enabled:
                    try:
                        new_path = rename_simple(file_path)
                        log_processed_file(
                            log_file,
                            mkv_file,
                            os.path.basename(new_path),
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(new_path),
                            },
                        )
                    except Exception as rename_err:
                        logger.error(f"Cannot rename: {rename_err}")
                continue 

            # Check for Vietnamese subtitle and audio
            has_vie_subtitle = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                                 for stream in subtitle_streams)
            has_vie_audio = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                               for stream in audio_streams)

            processed = False  # Flag to mark file as processed
            
            # Check for Vietnamese subtitle and audio (needed for rename logic too)
            has_vie_subtitle = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                                 for stream in subtitle_streams)
            has_vie_audio = any(stream.get('tags', {}).get('language', 'und') == 'vie' 
                               for stream in audio_streams)

            # If only need rename (file already processed), skip extract
            if not skip_extract:
                # Process Vietnamese subtitles
                vie_subtitle_streams = [stream for stream in subtitle_streams
                                        if stream.get('tags', {}).get('language', 'und') == 'vie']
                if vie_subtitle_streams:
                    logger.info(t("messages.extracting_subtitle", language=f"{len(vie_subtitle_streams)} Vietnamese"))
                for stream in vie_subtitle_streams:
                    subtitle_info = (
                        stream['index'],
                        'vie',
                        stream.get('tags', {}).get('title', ''),
                        stream.get('codec_name', '')
                    )
                    extract_subtitle(file_path, subtitle_info, log_file, probe_data, file_signature=file_signature)

            # Process video if has Vietnamese audio
            if has_vie_audio:
                try:
                    logger.info("\nDetected Vietnamese audio. Starting processing...")
                    # Find Vietnamese audio track with most channels
                    vie_audio_tracks = [(stream.get('index', i), stream.get('channels', 0), 'vie', 
                                      stream.get('tags', {}).get('title', 'VIE'))
                                      for i, stream in enumerate(audio_streams)
                                      if stream.get('tags', {}).get('language', 'und') == 'vie']
                    if vie_audio_tracks:
                        # Sort by channel count descending
                        vie_audio_tracks.sort(key=lambda x: x[1], reverse=True)
                        selected_track = vie_audio_tracks[0]
                        logger.info(f"Selected Vietnamese audio track index={selected_track[0]} with {selected_track[1]} channels")
                        extract_video_with_audio(
                            file_path,
                            vn_folder,
                            original_folder,
                            log_file,
                            probe_data,
                            file_signature=file_signature,
                            rename_enabled=rename_enabled,
                        )
                        processed = True  # Mark file as processed
                except Exception as e:
                    logger.error(f"Error processing audio: {e}")

            # Check rename_enabled option
            rename_enabled = file_opts.get("rename_enabled", False)
            force_reprocess_file = file_opts.get("force_process", False)
            
            # Only rename when:
            # 1. force_reprocess = True (force reprocess) AND rename_enabled = True
            # 2. File not processed AND rename_enabled = True
            file_already_processed = mkv_file in processed_files or (file_signature and file_signature in processed_signatures)
            should_rename = rename_enabled and (force_reprocess_file or not file_already_processed)
            
            # If only extract SRT (no VIE audio) and should_rename = True, rename video file
            if not processed and has_vie_subtitle and not has_vie_audio and should_rename:
                logger.info(f"\nExtracted subtitle. Renaming video file as requested...")
                try:
                    new_path = rename_simple(file_path)
                    log_processed_file(
                        log_file,
                        mkv_file,
                        os.path.basename(new_path),
                        signature=file_signature,
                        metadata={
                            "category": "video",
                            "source_path": file_path,
                            "output_path": os.path.abspath(new_path),
                        },
                    )
                    logger.info(t("messages.renamed_file", old=mkv_file, new=os.path.basename(new_path)))
                except Exception as rename_err:
                    logger.error(f"Cannot rename: {rename_err}")
            # If no Vietnamese subtitle and audio OR audio processing failed
            # Only rename if should_rename = True
            elif (not has_vie_subtitle and not has_vie_audio) or (not processed and not should_rename):
                if not has_vie_subtitle and not has_vie_audio and should_rename:
                    logger.info(f"\nNo Vietnamese subtitle or audio found. Only renaming file...")
                    try:
                        new_path = rename_simple(file_path)
                        log_processed_file(
                            log_file,
                            mkv_file,
                            os.path.basename(new_path),
                            signature=file_signature,
                            metadata={
                                "category": "video",
                                "source_path": file_path,
                                "output_path": os.path.abspath(new_path),
                            },
                        )
                    except Exception as rename_err:
                        logger.error(f"Cannot rename: {rename_err}")

        # Auto-commit subtitles after processing all files
        logger.info("\n=== PROCESSING COMPLETED ===")
        logger.info("Starting auto-commit of subtitle files...")
        auto_commit_subtitles(subtitle_folder, settings)

        from .log_manager import REMOTE_SYNC
        if REMOTE_SYNC:
            REMOTE_SYNC.flush()
        write_run_log_snapshot(logs_dir)

    except Exception as e:
        logger.error(f"Error accessing directory '{input_folder}': {e}")
    finally:
        # Restore original working directory
        if need_restore_cwd:
            try:
                os.chdir(original_cwd)
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MKV Processor CLI")
    parser.add_argument("folder", nargs="?", help="Directory containing MKV files")
    parser.add_argument("--force", action="store_true", help="Ignore old log, reprocess all")
    parser.add_argument("--dry-run", action="store_true", help="Only list file status (no processing)")
    args = parser.parse_args()

    if args.folder:
        main(args.folder, force_reprocess=args.force, dry_run=args.dry_run)
    else:
        main(force_reprocess=args.force, dry_run=args.dry_run)