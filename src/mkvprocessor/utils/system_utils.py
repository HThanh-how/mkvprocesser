"""
System utility functions for MKV Processor.

Handles system checks: RAM, disk space, FFmpeg availability, etc.
"""
import logging
import subprocess
from typing import Optional

import psutil  # type: ignore

from ..ffmpeg_helper import check_ffmpeg_available as check_local_ffmpeg

logger = logging.getLogger(__name__)


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available - uses helper to find local FFmpeg.
    
    Returns:
        True if FFmpeg is found and executable, False otherwise
    """
    try:
        return check_local_ffmpeg()
    except ImportError:
        # Fallback if helper not available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


def check_available_ram() -> float:
    """Check available RAM in the system.
    
    Returns:
        Available RAM in GB, or 0.0 if check fails
    """
    try:
        memory = psutil.virtual_memory()
        free_memory_gb = memory.available / (1024 ** 3)  # Convert to GB
        logger.info(f"Available RAM: {free_memory_gb:.2f} GB")
        return free_memory_gb
    except Exception as e:
        logger.error(f"Error checking RAM: {e}")
        return 0.0

