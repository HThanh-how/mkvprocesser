"""
File utility functions for MKV Processor.

Handles file operations, naming, signatures, and file system utilities.
"""
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

import ffmpeg  # type: ignore

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename to avoid FFmpeg errors.
    
    Args:
        name: Original filename
    
    Returns:
        Sanitized filename with invalid characters replaced by underscore
    """
    # Replace invalid characters with underscore
    return re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)


def get_file_size_gb(file_path: Union[str, Path]) -> float:
    """Get file size in GB.
    
    Args:
        file_path: Path to file
    
    Returns:
        File size in GB, or 0.0 if check fails
    """
    try:
        file_size = os.path.getsize(file_path)
        file_size_gb = file_size / (1024 ** 3)  # Convert to GB
        return file_size_gb
    except (OSError, IOError) as e:
        logger.error(f"Error getting file size: {e}")
        return 0.0


def get_file_size_mb(file_path: Union[str, Path]) -> float:
    """Get file size in MB.
    
    Args:
        file_path: Path to file
    
    Returns:
        File size in MB, or 0.0 if check fails
    """
    try:
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 ** 2)  # Convert to MB
        return file_size_mb
    except (OSError, IOError) as e:
        logger.error(f"Error getting file size: {e}")
        return 0.0


def get_file_signature(file_path: Union[str, Path], include_hash: bool = False) -> Optional[str]:
    """Get file signature to identify duplicate files.
    
    Format: {size}_{duration}_{sub_count}_{sub_langs}[_{first_1mb_hash}]
    
    Example: 8589934592_7200.5_3_vie,eng,chi_a1b2c3d4
    
    Args:
        file_path: Path to video file
        include_hash: Whether to include hash of first 1MB for higher accuracy
    
    Returns:
        File signature string, or None if error occurs
    """
    try:
        file_size = os.path.getsize(file_path)
        probe = ffmpeg.probe(file_path)
        duration = probe.get('format', {}).get('duration', '0')
        
        # Count subtitle tracks and languages
        sub_streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'subtitle']
        sub_count = len(sub_streams)
        sub_langs = sorted(set(
            s.get('tags', {}).get('language', 'und') 
            for s in sub_streams
        ))
        sub_langs_str = ','.join(sub_langs) if sub_langs else 'none'
        
        signature = f"{file_size}_{duration}_{sub_count}_{sub_langs_str}"
        
        # Optional: add hash of first 1MB for higher accuracy
        if include_hash:
            try:
                with open(file_path, 'rb') as f:
                    first_mb = f.read(1024 * 1024)  # 1MB
                    hash_str = hashlib.md5(first_mb).hexdigest()[:8]
                    signature += f"_{hash_str}"
            except (IOError, OSError):
                pass
        
        return signature
    except (OSError, IOError, KeyError, ValueError) as e:
        logger.error(f"Error getting file signature: {e}")
        return None


def create_folder(folder_name: Union[str, Path]) -> None:
    """Create folder if it doesn't exist.
    
    Args:
        folder_name: Path to folder to create
    """
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

