"""
Helper module to find and use FFmpeg - prioritizes local bundled FFmpeg.
"""
import logging
import os
import subprocess
import platform
import sys
from pathlib import Path
from typing import Optional, Union, List

logger = logging.getLogger(__name__)

# Windows: Hide CMD window when running subprocess
SUBPROCESS_FLAGS = 0
if platform.system() == "Windows":
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW


def get_bundle_dir() -> Path:
    """Get the directory containing the executable (when running from PyInstaller).
    
    Returns:
        Path to bundle directory. When running from PyInstaller, this is the
        temporary _MEIPASS directory. When running from source, returns the
        parent directory of this module.
    """
    if getattr(sys, 'frozen', False):
        # Running from executable (PyInstaller)
        # PyInstaller creates temporary _MEIPASS directory to extract data files
        if hasattr(sys, '_MEIPASS'):
            # When running from PyInstaller, data files are extracted to _MEIPASS
            # FFmpeg will be in _MEIPASS/ffmpeg_bin/
            bundle_path = Path(sys._MEIPASS)
            # Debug: Print for verification
            if os.getenv('DEBUG_FFMPEG'):
                logger.debug(f"Bundle dir: {bundle_path}")
                logger.debug(f"FFmpeg bin dir: {bundle_path / 'ffmpeg_bin'}")
            return bundle_path
        else:
            # Fallback: directory containing executable
            return Path(sys.executable).parent
    else:
        # Running from source code
        return Path(__file__).parent.parent.parent


def find_ffmpeg_binary() -> Optional[str]:
    """Find FFmpeg binary - prioritizes local bundle.
    
    Search order:
    1. Bundle directory / ffmpeg_bin/
    2. Bundle directory root
    3. System PATH
    
    Returns:
        Path to FFmpeg binary as string, or 'ffmpeg' if found in PATH,
        or None if not found.
    """
    bundle_dir = get_bundle_dir()
    system = platform.system()
    
    # FFmpeg filename by OS
    if system == "Windows":
        ffmpeg_name = "ffmpeg.exe"
        ffprobe_name = "ffprobe.exe"
    else:
        ffmpeg_name = "ffmpeg"
        ffprobe_name = "ffprobe"
    
    # 1. Search in bundle/ffmpeg_bin directory
    local_ffmpeg = bundle_dir / "ffmpeg_bin" / ffmpeg_name
    if local_ffmpeg.exists():
        ffmpeg_path = str(local_ffmpeg.absolute())
        if os.getenv('DEBUG_FFMPEG'):
            logger.debug(f"Found FFmpeg at: {ffmpeg_path}")
        return ffmpeg_path
    
    # 2. Search in bundle directory (same directory as exe)
    local_ffmpeg = bundle_dir / ffmpeg_name
    if local_ffmpeg.exists():
        ffmpeg_path = str(local_ffmpeg.absolute())
        if os.getenv('DEBUG_FFMPEG'):
            logger.debug(f"Found FFmpeg at: {ffmpeg_path}")
        return ffmpeg_path
    
    # 3. Search in PATH (system FFmpeg)
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            check=True,
            timeout=5,
            creationflags=SUBPROCESS_FLAGS
        )
        if os.getenv('DEBUG_FFMPEG'):
            logger.debug("Using system FFmpeg from PATH")
        return 'ffmpeg'  # Use system FFmpeg
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    if os.getenv('DEBUG_FFMPEG'):
        logger.debug(f"FFmpeg not found in: {bundle_dir / 'ffmpeg_bin'}")
        logger.debug(f"FFmpeg not found in: {bundle_dir}")
    
    return None


def find_ffprobe_binary() -> Optional[str]:
    """Find FFprobe binary - prioritizes local bundle.
    
    Search order:
    1. Bundle directory / ffmpeg_bin/
    2. Bundle directory root
    3. System PATH
    
    Returns:
        Path to FFprobe binary as string, or 'ffprobe' if found in PATH,
        or None if not found.
    """
    bundle_dir = get_bundle_dir()
    system = platform.system()
    
    if system == "Windows":
        ffprobe_name = "ffprobe.exe"
    else:
        ffprobe_name = "ffprobe"
    
    # 1. Search in bundle/ffmpeg_bin directory
    local_ffprobe = bundle_dir / "ffmpeg_bin" / ffprobe_name
    if local_ffprobe.exists():
        return str(local_ffprobe.absolute())
    
    # 2. Search in bundle directory
    local_ffprobe = bundle_dir / ffprobe_name
    if local_ffprobe.exists():
        return str(local_ffprobe.absolute())
    
    # 3. Search in PATH
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            check=True,
            creationflags=SUBPROCESS_FLAGS
        )
        return 'ffprobe'
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return None


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available - uses local binary if available.
    
    Returns:
        True if FFmpeg is found and executable, False otherwise.
    """
    ffmpeg_path = find_ffmpeg_binary()
    if ffmpeg_path is None:
        return False
    
    try:
        subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True,
            check=True,
            creationflags=SUBPROCESS_FLAGS
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_ffmpeg_command(cmd: Union[List[str], str]) -> Union[List[str], str]:
    """Replace 'ffmpeg' and 'ffprobe' in command with actual paths.
    
    Args:
        cmd: Command as list of strings or single string.
    
    Returns:
        Command with 'ffmpeg' and 'ffprobe' replaced with actual paths.
        Returns original command if FFmpeg not found (fallback).
    """
    ffmpeg_path = find_ffmpeg_binary()
    if ffmpeg_path is None:
        return cmd  # Fallback to original command
    
    # Replace 'ffmpeg' and 'ffprobe' in command
    if isinstance(cmd, list):
        new_cmd: List[str] = []
        for arg in cmd:
            if arg == 'ffmpeg':
                new_cmd.append(ffmpeg_path)
            elif arg == 'ffprobe':
                ffprobe_path = find_ffprobe_binary()
                if ffprobe_path:
                    new_cmd.append(ffprobe_path)
                else:
                    new_cmd.append(arg)
            else:
                new_cmd.append(arg)
        return new_cmd
    elif isinstance(cmd, str):
        ffprobe_path = find_ffprobe_binary() or 'ffprobe'
        return cmd.replace('ffmpeg', ffmpeg_path).replace('ffprobe', ffprobe_path)
    
    return cmd


def probe_file(file_path: str) -> dict:
    """Probe file with ffprobe, hiding console window on Windows.
    
    This is a replacement for ffmpeg.probe() that doesn't show CMD window.
    
    Args:
        file_path: Path to the video file to probe.
    
    Returns:
        Dictionary containing FFprobe output (format and streams info).
    
    Raises:
        FileNotFoundError: If the input file doesn't exist.
        RuntimeError: If ffprobe fails or returns invalid output.
        subprocess.TimeoutExpired: If ffprobe times out (30 seconds).
    """
    import json
    
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Find ffprobe binary
    ffprobe_path = find_ffprobe_binary()
    if ffprobe_path is None:
        # Try system ffprobe
        ffprobe_path = 'ffprobe'
        # Verify it exists
        try:
            subprocess.run(
                [ffprobe_path, '-version'],
                capture_output=True,
                check=True,
                timeout=5,
                creationflags=SUBPROCESS_FLAGS
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError(
                "ffprobe không được tìm thấy. "
                "Vui lòng đảm bảo ffprobe.exe có trong thư mục ffmpeg_bin hoặc trong PATH."
            )
    
    cmd = [
        ffprobe_path,
        '-v', 'error',  # Show errors for debugging
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]
    
    try:
        logger.debug(f"Running ffprobe: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            creationflags=SUBPROCESS_FLAGS,
            timeout=30  # Timeout 30 seconds
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace').strip()
            if not error_msg:
                error_msg = f"ffprobe returned code {result.returncode}"
            logger.error(f"ffprobe error for {file_path}: {error_msg}")
            raise RuntimeError(f"ffprobe error: {error_msg}")
        
        output = result.stdout.decode('utf-8')
        if not output.strip():
            logger.error(f"ffprobe returned empty output for {file_path}")
            raise RuntimeError("ffprobe returned empty output")
        
        return json.loads(output)
    except subprocess.TimeoutExpired as e:
        logger.error(f"ffprobe timeout for: {file_path}")
        raise RuntimeError(f"ffprobe timeout for: {file_path}") from e
    except json.JSONDecodeError as e:
        logger.error(f"ffprobe JSON parse error for {file_path}: {e}")
        raise RuntimeError(f"ffprobe JSON parse error: {e}") from e
    except FileNotFoundError as e:
        logger.error(f"ffprobe not found: {e}")
        raise RuntimeError(
            f"ffprobe không được tìm thấy. "
            f"Vui lòng đảm bảo ffprobe.exe có trong thư mục ffmpeg_bin hoặc trong PATH."
        ) from e
