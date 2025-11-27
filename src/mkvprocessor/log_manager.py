"""
Log management for MKV Processor.

Handles logging processed files, converting legacy logs, and managing log snapshots.
"""
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .config_manager import get_config_dir
from .github_sync import RemoteSyncManager

logger = logging.getLogger(__name__)

# Global variables
REMOTE_SYNC: Optional[RemoteSyncManager] = None
RUN_LOG_ENTRIES: List[Dict[str, Any]] = []


def set_remote_sync(sync_manager: Optional[RemoteSyncManager]) -> None:
    """Set the remote sync manager.
    
    Args:
        sync_manager: RemoteSyncManager instance or None
    """
    global REMOTE_SYNC
    REMOTE_SYNC = sync_manager


def log_processed_file(
    log_file: Union[str, Path],
    old_name: str,
    new_name: str,
    *,
    signature: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log processed file and sync to GitHub if configured.
    
    Args:
        log_file: Path to log file
        old_name: Original filename
        new_name: New filename after processing
        signature: Optional file signature for deduplication
        metadata: Optional dictionary with additional metadata
    """
    global RUN_LOG_ENTRIES
    metadata = metadata or {}
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if signature is None:
        signature = metadata.get("signature")
    source_path = metadata.get("source_path")
    if signature is None and source_path and os.path.exists(source_path):
        from .utils.file_utils import get_file_signature
        signature = get_file_signature(source_path)

    file_path = os.path.join(".", old_name)
    fallback_signature = ""
    if signature:
        fallback_signature = signature
    elif os.path.exists(file_path):
        from .utils.file_utils import get_file_signature
        fallback_signature = get_file_signature(file_path) or ""

    try:
        with open(log_file, "a", encoding='utf-8') as f:
            f.write(f"{old_name}|{new_name}|{current_time}|{fallback_signature}\n")
    except (IOError, OSError) as e:
        logger.error(f"Failed to write to log file: {e}")
        return

    # Sync to GitHub if configured
    remote_entry = {
        "old_name": old_name,
        "new_name": new_name,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "signature": signature or fallback_signature,
        "category": metadata.get("category", "video"),
        "output_path": metadata.get("output_path"),
        "language": metadata.get("language"),
        "notes": metadata.get("notes"),
    }
    RUN_LOG_ENTRIES.append(remote_entry)

    if REMOTE_SYNC:
        local_path = metadata.get("local_path") or metadata.get("output_path")
        try:
            REMOTE_SYNC.record_entry(remote_entry, local_path=local_path)
        except Exception as sync_err:
            logger.error(f"[AUTO PUSH] Failed to write log to GitHub: {sync_err}")


def read_processed_files(log_file: Union[str, Path]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """Read list of processed files from log.
    
    Args:
        log_file: Path to log file
    
    Returns:
        Tuple of (processed_files dict, processed_signatures dict)
    """
    processed_files: Dict[str, Dict[str, str]] = {}
    processed_signatures: Dict[str, Dict[str, str]] = {}
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) >= 2:
                        old_name = parts[0]
                        new_name = parts[1]
                        time_processed = parts[2] if len(parts) > 2 else ""
                        signature = parts[3] if len(parts) > 3 else ""
                        
                        info = {"new_name": new_name, "time": time_processed, "signature": signature}
                        processed_files[old_name] = info
                        processed_files[new_name] = info
                        if signature:
                            processed_signatures[signature] = info
        except (IOError, OSError) as e:
            logger.error(f"Failed to read log file: {e}")
    return processed_files, processed_signatures


def convert_legacy_log_file(log_path: Path, logs_dir: Path) -> Optional[Path]:
    """Convert old processed_files.log to JSON and delete old file.
    
    Args:
        log_path: Path to legacy log file
        logs_dir: Directory to save converted JSON file
    
    Returns:
        Path to converted JSON file, or None if conversion not needed
    """
    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except (IOError, OSError) as exc:
        logger.error(f"[LOG] Failed to read {log_path}: {exc}")
        return None

    entries = []
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) < 2:
            continue
        entries.append(
            {
                "old_name": parts[0],
                "new_name": parts[1],
                "timestamp": parts[2] if len(parts) > 2 else datetime.datetime.utcnow().isoformat(),
                "signature": parts[3] if len(parts) > 3 else "",
                "category": "video",
            }
        )

    if not entries:
        return None

    logs_dir.mkdir(parents=True, exist_ok=True)
    file_path = logs_dir / f"legacy_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    file_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    log_path.unlink(missing_ok=True)
    logger.info(f"[LOG] Converted legacy log to {file_path}")
    return file_path


def write_run_log_snapshot(logs_dir: Path, prefix: str = "run") -> Optional[Path]:
    """Write run log snapshot to file.
    
    Args:
        logs_dir: Directory to save log snapshot
        prefix: Filename prefix for snapshot
    
    Returns:
        Path to saved log file, or None if no entries
    """
    global RUN_LOG_ENTRIES
    if not RUN_LOG_ENTRIES:
        return None
    
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_path = logs_dir / f"{prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    file_path.write_text(json.dumps(RUN_LOG_ENTRIES, ensure_ascii=False, indent=2), encoding="utf-8")
    if REMOTE_SYNC:
        REMOTE_SYNC.upload_log_snapshot(RUN_LOG_ENTRIES, filename_prefix=prefix)
    RUN_LOG_ENTRIES = []
    logger.info(f"[LOG] Saved session log to {file_path}")
    return file_path

