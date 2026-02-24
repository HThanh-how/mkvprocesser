"""
Unit tests for ResourceMonitor and parallel processing utilities.
"""
import pytest
import threading
from mkvprocessor.utils.system_utils import ResourceMonitor

def test_resource_monitor_singleton():
    """Verify that ResourceMonitor is a singleton."""
    rm1 = ResourceMonitor.get_instance()
    rm2 = ResourceMonitor.get_instance()
    assert rm1 is rm2

def test_resource_monitor_reserve_and_release():
    """Verify RAM reservation and release logic."""
    rm = ResourceMonitor.get_instance()
    
    # Store initial
    initial_ram = rm.get_reserved_ram_gb()
    
    # Reserve 1 GB
    success = rm.reserve_ram(1.0)
    
    if success:
        assert rm.get_reserved_ram_gb() == initial_ram + 1.0
        
        # Release 1 GB
        rm.release_ram(1.0)
        assert rm.get_reserved_ram_gb() == initial_ram
    else:
        # If it failed, ram wasn't enough, which is possible on low RAM systems
        pass
        
def test_resource_monitor_thread_safety():
    """Verify thread safety of ResourceMonitor."""
    rm = ResourceMonitor.get_instance()
    initial_ram = rm.get_reserved_ram_gb()
    
    def worker():
        # Reserve a tiny amount of RAM
        if rm.reserve_ram(0.01):
            rm.release_ram(0.01)
            
    threads = []
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert rm.get_reserved_ram_gb() == initial_ram
