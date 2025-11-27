"""
FFmpeg runner helper.

Provides a thin wrapper around subprocess.run that ensures the bundled
FFmpeg binary (if any) is used and the Windows console window stays hidden.
"""
from __future__ import annotations

import platform
import subprocess
from typing import List, Union

from ..ffmpeg_helper import get_ffmpeg_command

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


def run_ffmpeg_command(cmd: Union[List[str], str], **kwargs) -> subprocess.CompletedProcess:
    """
    Execute an FFmpeg command with consistent behaviour across platforms.

    Args:
        cmd: FFmpeg command as list of args or string.
        **kwargs: Extra subprocess.run kwargs.

    Returns:
        subprocess.CompletedProcess
    """
    try:
        cmd = get_ffmpeg_command(cmd)
    except ImportError:
        pass

    if platform.system() == "Windows":
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)

    return subprocess.run(cmd, **kwargs)

