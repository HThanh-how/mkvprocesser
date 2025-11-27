"""
Temporary directory utilities for MKV Processor.

Handles creation of temporary directories in RAM or on disk.
"""
import logging
import os
import platform
import shutil
import tempfile
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


@contextmanager
def temp_directory_in_memory(use_ram: bool = True, file_size_gb: Optional[float] = None):
    """Create temporary directory in RAM or on disk depending on use_ram parameter.
    
    Args:
        use_ram: Whether to use RAM
        file_size_gb: Optional file size in GB, used to calculate required space
    
    Yields:
        Path to temporary directory
    """
    if not use_ram:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Creating temporary directory on disk: {temp_dir}")
            yield temp_dir
        return
    
    # Calculate minimum required space based on file size if available
    # For subtitles, only need a small amount, for video need more
    if file_size_gb:
        # For small files, require at least 400MB
        required_space_gb = max(0.4, file_size_gb * 0.5)
        logger.info(f"Need at least {required_space_gb:.2f} GB for file {file_size_gb:.2f} GB")
    else:
        # Default require 1GB if file size unknown
        required_space_gb = 1.0
    
    # Create list of possible RAM locations
    ram_locations = []
    
    # 1. Ubuntu/Linux: Potential RAM disk locations
    if os.name == 'posix':
        # /dev/shm - usually RAM disk on most Linux systems
        if os.path.exists('/dev/shm') and os.access('/dev/shm', os.W_OK):
            ram_locations.append(('/dev/shm', 'RAM disk'))
        
        # /run/user/<uid> - user directory on systemd, usually in RAM
        uid = os.getuid() if hasattr(os, 'getuid') else None
        if uid is not None:
            user_runtime_dir = f"/run/user/{uid}"
            if os.path.exists(user_runtime_dir) and os.access(user_runtime_dir, os.W_OK):
                ram_locations.append((user_runtime_dir, 'Runtime user directory'))
        
        # /run - runtime directory for system processes
        if os.path.exists('/run') and os.access('/run', os.W_OK):
            ram_locations.append(('/run', 'Runtime directory'))
        
        # /tmp - may be configured as tmpfs on RAM on some systems
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            ram_locations.append(('/tmp', 'Temporary directory'))
    
    # 2. macOS: Try /private/tmp (may be stored in RAM on some configurations)
    if platform.system() == 'Darwin':
        if os.path.exists('/private/tmp') and os.access('/private/tmp', os.W_OK):
            ram_locations.append(('/private/tmp', 'macOS temporary directory'))
    
    # Check each location and find one with most free space
    best_location = None
    best_location_desc = None
    max_free_space = 0
    
    logger.info(f"Searching for temporary storage location (require at least {required_space_gb:.2f} GB)...")
    for location, desc in ram_locations:
        try:
            usage = shutil.disk_usage(location)
            free_space_gb = usage.free / (1024**3)
            logger.debug(f"- {desc} ({location}): {free_space_gb:.2f} GB free")
            
            # Save location with most free space
            if free_space_gb > max_free_space:
                max_free_space = free_space_gb
                best_location = location
                best_location_desc = desc
        except Exception as e:
            logger.warning(f"- {desc} ({location}): Cannot check ({e})")
    
    # Create temporary directory in best location if enough space
    if best_location and max_free_space >= required_space_gb:
        try:
            temp_dir = tempfile.mkdtemp(dir=best_location)
            logger.info(f"Using {best_location_desc} ({max_free_space:.2f} GB free) for RAM processing: {temp_dir}")
            try:
                yield temp_dir
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Removed temporary directory: {temp_dir}")
            return
        except Exception as e:
            logger.error(f"Error creating temporary directory in {best_location}: {e}")
    
    # If no RAM disk available or insufficient space, use disk instead
    try:
        # Try to create temporary directory in /tmp if available
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            temp_dir = tempfile.mkdtemp(dir='/tmp')
        else:
            temp_dir = tempfile.mkdtemp()
        
        if best_location:
            logger.warning(f"NOTICE: Insufficient space in {best_location_desc} ({max_free_space:.2f} GB < {required_space_gb:.2f} GB)")
            logger.info(f"Using disk instead: {temp_dir}")
        else:
            logger.info(f"NOTICE: No suitable RAM disk found. Using disk instead: {temp_dir}")
        
        try:
            yield temp_dir
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.debug(f"Removed temporary directory: {temp_dir}")
    except Exception as e:
        logger.error(f"Error processing temporary directory: {e}")
        # Final fallback: use regular tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Fallback: Using temporary directory on disk: {temp_dir}")
            yield temp_dir

