"""
History Manager - Quản lý lịch sử xử lý file với JSONL format.

Format JSONL (mỗi dòng là 1 JSON object):
{"id": "uuid", "old_name": "...", "new_name": "...", "timestamp": "...", "signature": "..."}

Ưu điểm:
- Append-only: không bao giờ conflict khi merge
- Dễ đọc từng dòng mà không cần parse toàn bộ file
- Dễ dedupe bằng signature hoặc id
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


class HistoryManager:
    """Quản lý lịch sử xử lý file."""
    
    def __init__(self, base_dir: str):
        """
        Args:
            base_dir: Thư mục gốc (thường là Subtitles/)
        """
        self.base_dir = Path(base_dir)
        self.history_dir = self.base_dir / "history"
        self.history_file = self.history_dir / "processed.jsonl"
        self.index_file = self.history_dir / "index.json"
        
        # In-memory index
        self._by_signature: Dict[str, dict] = {}
        self._by_name: Dict[str, str] = {}  # name -> signature
        self._loaded = False
    
    def ensure_dir(self):
        """Tạo thư mục history nếu chưa có."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self):
        """Load lịch sử vào memory."""
        if self._loaded:
            return
        
        self._by_signature = {}
        self._by_name = {}
        
        # 1. Load từ JSONL file
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
            except Exception:
                pass
        
        # 2. Load từ index file (nếu có, để lookup nhanh)
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                    # Merge với data từ JSONL
                    for sig, entry in index.get("by_signature", {}).items():
                        if sig not in self._by_signature:
                            self._by_signature[sig] = entry
                    for name, sig in index.get("by_name", {}).items():
                        if name not in self._by_name:
                            self._by_name[name] = sig
            except Exception:
                pass
        
        self._loaded = True
    
    def save_index(self):
        """Lưu index để lookup nhanh."""
        self.ensure_dir()
        index = {
            "by_signature": self._by_signature,
            "by_name": self._by_name,
            "updated": datetime.utcnow().isoformat()
        }
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def add_entry(
        self,
        old_name: str,
        new_name: str,
        signature: str,
        **metadata
    ) -> dict:
        """
        Thêm entry mới vào lịch sử.
        
        Returns:
            Entry đã được thêm
        """
        self.load()
        self.ensure_dir()
        
        # Tạo entry
        entry = {
            "id": str(uuid.uuid4()),
            "old_name": old_name,
            "new_name": new_name,
            "signature": signature,
            "timestamp": datetime.utcnow().isoformat(),
            **metadata
        }
        
        # Append vào JSONL file
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[HISTORY] Lỗi ghi lịch sử: {e}")
        
        # Update index
        self._by_signature[signature] = entry
        self._by_name[old_name] = signature
        self._by_name[new_name] = signature
        
        return entry
    
    def has_signature(self, signature: str) -> bool:
        """Kiểm tra signature đã tồn tại chưa."""
        self.load()
        return signature in self._by_signature
    
    def has_name(self, name: str) -> bool:
        """Kiểm tra tên file đã tồn tại chưa."""
        self.load()
        return name in self._by_name
    
    def get_by_signature(self, signature: str) -> Optional[dict]:
        """Lấy entry theo signature."""
        self.load()
        return self._by_signature.get(signature)
    
    def get_by_name(self, name: str) -> Optional[dict]:
        """Lấy entry theo tên file."""
        self.load()
        sig = self._by_name.get(name)
        if sig:
            return self._by_signature.get(sig)
        return None
    
    def get_all_entries(self) -> List[dict]:
        """Lấy tất cả entries."""
        self.load()
        return list(self._by_signature.values())
    
    def get_all_signatures(self) -> Set[str]:
        """Lấy tất cả signatures."""
        self.load()
        return set(self._by_signature.keys())
    
    def get_all_names(self) -> Set[str]:
        """Lấy tất cả tên file."""
        self.load()
        return set(self._by_name.keys())
    
    def import_legacy_log(self, log_path: str) -> int:
        """
        Import từ processed_files.log cũ.
        
        Returns:
            Số entries đã import
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
                        
                        # Chỉ import nếu chưa có
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
                            # Không có signature, dùng tên để check
                            self.add_entry(
                                old_name=old_name,
                                new_name=new_name,
                                signature=f"legacy_{old_name}",
                                imported_from="legacy_log",
                                original_timestamp=timestamp
                            )
                            count += 1
        except Exception as e:
            print(f"[HISTORY] Lỗi import legacy log: {e}")
        
        if count > 0:
            self.save_index()
        
        return count
    
    def import_json_logs(self, logs_dir: str) -> int:
        """
        Import từ logs/*.json.
        
        Returns:
            Số entries đã import
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
            except Exception:
                continue
        
        if count > 0:
            self.save_index()
        
        return count


def merge_history_files(files: List[str], output_file: str) -> int:
    """
    Merge nhiều file JSONL thành 1, dedupe bằng signature.
    Dùng cho GitHub merge.
    
    Returns:
        Số entries sau khi merge
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
        except Exception:
            continue
    
    # Sắp xếp theo timestamp
    entries.sort(key=lambda x: x.get("timestamp", ""))
    
    # Ghi ra file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[HISTORY] Lỗi merge: {e}")
        return 0
    
    return len(entries)

