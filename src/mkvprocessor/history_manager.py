"""
History Manager - Manage processing history with JSONL format.

JSONL format (each line is 1 JSON object):
{"id": "uuid", "old_name": "...", "new_name": "...", "timestamp": "...", "signature": "..."}

Advantages:
- Append-only: never conflicts when merging
- Easy to read line by line without parsing entire file
- Easy to dedupe by signature or id
"""
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manage processing history."""
    
    def __init__(self, base_dir: str):
        """Initialize HistoryManager.
        
        Args:
            base_dir: Base directory (usually Subtitles/)
        """
        self.base_dir = Path(base_dir)
        self.history_dir = self.base_dir / "history"
        self.history_file = self.history_dir / "processed.jsonl"
        self.index_file = self.history_dir / "index.json"
        
        # In-memory index
        self._by_signature: Dict[str, dict] = {}
        self._by_name: Dict[str, str] = {}  # name -> signature
        self._loaded = False
    
    def ensure_dir(self) -> None:
        """Create history directory if it doesn't exist."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> None:
        """Load history into memory."""
        if self._loaded:
            return
        
        self._by_signature = {}
        self._by_name = {}
        
        # 1. Load from JSONL file
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            sig = entry.get("signature", "")
                            if sig:
                                self._by_signature[sig] = entry
                                old_name = entry.get("old_name", "")
                                new_name = entry.get("new_name", "")
                                if old_name:
                                    self._by_name[old_name] = sig
                                if new_name:
                                    self._by_name[new_name] = sig
                        except json.JSONDecodeError:
                            continue
            except (IOError, OSError) as e:
                logger.error(f"Failed to load history file: {e}")
        
        # 2. Load from index file (if exists, for fast lookup)
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                    # Merge with data from JSONL
                    for sig, entry in index.get("by_signature", {}).items():
                        if sig not in self._by_signature:
                            self._by_signature[sig] = entry
                    for name, sig in index.get("by_name", {}).items():
                        if name not in self._by_name:
                            self._by_name[name] = sig
            except (IOError, OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to load index file: {e}")
        
        self._loaded = True
    
    def save_index(self) -> None:
        """Save index for fast lookup."""
        self.ensure_dir()
        index = {
            "by_signature": self._by_signature,
            "by_name": self._by_name,
            "updated": datetime.utcnow().isoformat()
        }
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            logger.error(f"Failed to save index: {e}")
    
    def add_entry(
        self,
        old_name: str,
        new_name: str,
        signature: str,
        **metadata
    ) -> dict:
        """
        Add new entry to history.
        
        Args:
            old_name: Original filename
            new_name: New filename after processing
            signature: File signature for deduplication
            **metadata: Additional metadata fields
        
        Returns:
            Entry that was added
        """
        self.load()
        self.ensure_dir()
        
        # Create entry
        entry = {
            "id": str(uuid.uuid4()),
            "old_name": old_name,
            "new_name": new_name,
            "signature": signature,
            "timestamp": datetime.utcnow().isoformat(),
            **metadata
        }
        
        # Append to JSONL file
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (IOError, OSError) as e:
            logger.error(f"[HISTORY] Error writing history: {e}")
        
        # Update index
        self._by_signature[signature] = entry
        self._by_name[old_name] = signature
        self._by_name[new_name] = signature
        
        return entry
    
    def has_signature(self, signature: str) -> bool:
        """Check if signature already exists.
        
        Args:
            signature: File signature to check
        
        Returns:
            True if signature exists, False otherwise
        """
        self.load()
        return signature in self._by_signature
    
    def has_name(self, name: str) -> bool:
        """Check if filename already exists.
        
        Args:
            name: Filename to check
        
        Returns:
            True if name exists, False otherwise
        """
        self.load()
        return name in self._by_name
    
    def get_by_signature(self, signature: str) -> Optional[dict]:
        """Get entry by signature.
        
        Args:
            signature: File signature
        
        Returns:
            Entry dictionary or None if not found
        """
        self.load()
        return self._by_signature.get(signature)
    
    def get_by_name(self, name: str) -> Optional[dict]:
        """Get entry by filename.
        
        Args:
            name: Filename (old or new)
        
        Returns:
            Entry dictionary or None if not found
        """
        self.load()
        sig = self._by_name.get(name)
        if sig:
            return self._by_signature.get(sig)
        return None
    
    def get_all_entries(self) -> List[dict]:
        """Get all entries.
        
        Returns:
            List of all entry dictionaries
        """
        self.load()
        return list(self._by_signature.values())
    
    def get_all_signatures(self) -> Set[str]:
        """Get all signatures.
        
        Returns:
            Set of all signatures
        """
        self.load()
        return set(self._by_signature.keys())
    
    def get_all_names(self) -> Set[str]:
        """Get all filenames.
        
        Returns:
            Set of all filenames (old and new)
        """
        self.load()
        return set(self._by_name.keys())
    
    def import_legacy_log(self, log_path: str) -> int:
        """
        Import from old processed_files.log.
        
        Args:
            log_path: Path to legacy log file
        
        Returns:
            Number of entries imported
        """
        if not os.path.exists(log_path):
            return 0
        
        count = 0
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) >= 2:
                        old_name = parts[0]
                        new_name = parts[1]
                        timestamp = parts[2] if len(parts) > 2 else ""
                        signature = parts[3] if len(parts) > 3 else ""
                        
                        # Only import if not already exists
                        if signature and not self.has_signature(signature):
                            self.add_entry(
                                old_name=old_name,
                                new_name=new_name,
                                signature=signature,
                                imported_from="legacy_log",
                                original_timestamp=timestamp
                            )
                            count += 1
                        elif not signature and not self.has_name(old_name):
                            # No signature, use name to check
                            self.add_entry(
                                old_name=old_name,
                                new_name=new_name,
                                signature=f"legacy_{old_name}",
                                imported_from="legacy_log",
                                original_timestamp=timestamp
                            )
                            count += 1
        except (IOError, OSError) as e:
            logger.error(f"[HISTORY] Error importing legacy log: {e}")
        
        if count > 0:
            self.save_index()
        
        return count
    
    def import_json_logs(self, logs_dir: str) -> int:
        """
        Import from logs/*.json files.
        
        Args:
            logs_dir: Directory containing JSON log files
        
        Returns:
            Number of entries imported
        """
        logs_path = Path(logs_dir)
        if not logs_path.exists():
            return 0
        
        count = 0
        for json_file in logs_path.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for entry in data:
                            sig = entry.get("signature", "")
                            if sig and not self.has_signature(sig):
                                self.add_entry(
                                    old_name=entry.get("old_name", ""),
                                    new_name=entry.get("new_name", ""),
                                    signature=sig,
                                    imported_from=json_file.name,
                                    original_timestamp=entry.get("timestamp", ""),
                                    category=entry.get("category", "video")
                                )
                                count += 1
            except (IOError, OSError, json.JSONDecodeError):
                continue
        
        if count > 0:
            self.save_index()
        
        return count


def merge_history_files(files: List[str], output_file: str) -> int:
    """
    Merge multiple JSONL files into one, dedupe by signature.
    Used for GitHub merge.
    
    Args:
        files: List of JSONL file paths to merge
        output_file: Output file path
    
    Returns:
        Number of entries after merge
    """
    seen_signatures: Set[str] = set()
    entries: List[dict] = []
    
    for file_path in files:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        sig = entry.get("signature", "")
                        if sig and sig not in seen_signatures:
                            seen_signatures.add(sig)
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except (IOError, OSError):
            continue
    
    # Sort by timestamp
    entries.sort(key=lambda x: x.get("timestamp", ""))
    
    # Write to file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (IOError, OSError) as e:
        logger.error(f"[HISTORY] Error merging: {e}")
        return 0
    
    return len(entries)
