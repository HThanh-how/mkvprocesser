"""
Core MKV processing modules
"""
import sys as _sys

from .processing_core import main, auto_commit_subtitles
from .utils.system_utils import check_ffmpeg_available, check_available_ram
from .utils.file_utils import get_file_size_gb, create_folder
from .log_manager import read_processed_files
from . import legacy_api as _legacy_api

# Backwards compatibility: allow `import mkvprocessor.script`
_sys.modules[__name__ + ".script"] = _legacy_api

__all__ = [
    'main',
    'auto_commit_subtitles',
    'check_ffmpeg_available',
    'check_available_ram',
    'get_file_size_gb',
    'read_processed_files',
    'create_folder',
]

