"""
System utility functions for MKV Processor.

Handles system checks: RAM, disk space, FFmpeg availability, etc.
"""
import logging
import subprocess
import threading
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
        
        # Deduct reserved RAM from ResourceMonitor if available
        reserved_ram = 0.0
        try:
            reserved_ram = ResourceMonitor.get_instance().get_reserved_ram_gb()
        except NameError:
            pass # ResourceMonitor not defined yet
            
        return max(0.0, free_memory_gb - reserved_ram)
    except Exception as e:
        logger.error(f"Error checking RAM: {e}")
        return 0.0

class ResourceMonitor:
    """Singleton thread-safe class to monitor and reserve RAM/Disk storage for parallel processing."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        if ResourceMonitor._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            self.reserved_ram_gb = 0.0
            self.reserved_disk_gb = 0.0
            self.resource_lock = threading.Lock()
            
            # Tự động khởi tạo lại instance
            ResourceMonitor._instance = self
            
    @classmethod
    def get_instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls()
        return cls._instance
        
    def get_reserved_ram_gb(self) -> float:
        """Get total RAM reserved by other threads."""
        with self.resource_lock:
            return self.reserved_ram_gb
            
    def reserve_ram(self, amount_gb: float) -> bool:
        """Attempt to reserve an amount of RAM for a thread.
        Returns True if successful, False if insufficient RAM is available.
        """
        with self.resource_lock:
            # Check current total available RAM (ignores this class's currently reserved memory
            # so we use psutil directly here).
            try:
                memory = psutil.virtual_memory()
                free_memory_gb = memory.available / (1024 ** 3)
            except Exception as e:
                logger.error(f"Cannot check actual RAM: {e}")
                free_memory_gb = 0.0
                
            available_after_reservations = free_memory_gb - self.reserved_ram_gb
            
            if available_after_reservations >= amount_gb:
                self.reserved_ram_gb += amount_gb
                logger.debug(f"[RESOURCE] Reserved {amount_gb:.2f}GB RAM. Total Reserved: {self.reserved_ram_gb:.2f}GB. Actual Free: {free_memory_gb:.2f}GB.")
                return True
            else:
                logger.warning(f"[RESOURCE] Insufficient RAM. Requested: {amount_gb:.2f}GB, Available (After Reservations): {available_after_reservations:.2f}GB.")
                return False
                
    def release_ram(self, amount_gb: float):
        """Release reserved RAM back to the pool."""
        with self.resource_lock:
            self.reserved_ram_gb = max(0.0, self.reserved_ram_gb - amount_gb)
            logger.debug(f"[RESOURCE] Released {amount_gb:.2f}GB RAM. Total Reserved: {self.reserved_ram_gb:.2f}GB.")
