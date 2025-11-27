"""
Module hỗ trợ đồng bộ subtitle và log lên GitHub bằng token cá nhân.
Đọc cấu hình từ auto_push_config.json hoặc biến môi trường.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass
class AutoPushConfig:
    token: str
    repo: str
    branch: str = "main"
    log_path: str = "logs/processed.json"
    subtitle_dir: str = "subtitles"
    logs_dir: str = "logs"
    enabled: bool = True


def build_auto_push_config(settings: Dict[str, Any]) -> Optional[AutoPushConfig]:
    token = (settings.get("token") or "").strip()
    repo = (settings.get("repo") or "").strip()
    if not token or not repo:
        return None
    if not settings.get("auto_upload", False):
        return None
    return AutoPushConfig(
        token=token,
        repo=repo,
        branch=(settings.get("branch") or "main").strip(),
        log_path=(settings.get("log_path") or f"{settings.get('logs_dir', 'logs')}/processed.json").strip(),
        subtitle_dir=(settings.get("subtitle_dir") or "subtitles").strip(),
        logs_dir=(settings.get("logs_dir") or "logs").strip(),
    )


class GitHubClient:
    """Client đơn giản gọi GitHub Content API."""

    def __init__(self, config: AutoPushConfig):
        self.config = config
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {config.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _request(
        self, method: str, endpoint: str, *, params: Optional[Dict[str, Any]] = None, json_data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, params=params, json=json_data, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API error {response.status_code}: {response.text}")
        return response

    def get_content(self, path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Lấy nội dung file (base64) từ repo."""
        try:
            response = self._request(
                "GET",
                f"/repos/{self.config.repo}/contents/{path}",
                params={"ref": self.config.branch},
            )
        except RuntimeError as exc:
            if "404" in str(exc):
                return None, None
            raise

        data = response.json()
        content = base64.b64decode(data["content"]) if "content" in data else None
        sha = data.get("sha")
        return content, sha

    def put_content(self, path: str, content: bytes, message: str, sha: Optional[str] = None) -> str:
        """Upload (hoặc cập nhật) file lên repo. Trả về sha mới."""
        encoded = base64.b64encode(content).decode("utf-8")
        payload: Dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": self.config.branch,
        }
        if sha:
            payload["sha"] = sha

        response = self._request(
            "PUT",
            f"/repos/{self.config.repo}/contents/{path}",
            json_data=payload,
        )
        resp_json = response.json()
        return resp_json.get("content", {}).get("sha", "")

    def delete_content(self, path: str, sha: str, message: str) -> None:
        payload = {"message": message, "sha": sha, "branch": self.config.branch}
        self._request(
            "DELETE",
            f"/repos/{self.config.repo}/contents/{path}",
            json_data=payload,
        )


class RemoteSyncManager:
    """
    Quản lý log và upload subtitle lên GitHub.
    - Log được lưu tại log_path (JSON list).
    - Subtitle lưu trong subtitle_dir.
    """

    def __init__(self, config: AutoPushConfig):
        self.config = config
        self.client = GitHubClient(config)
        self.log_entries: List[Dict[str, Any]] = []
        self.log_sha: Optional[str] = None
        self.pending_entries: List[Dict[str, Any]] = []
        self.signatures: Dict[str, Dict[str, Any]] = {}

    def load_remote_logs(self) -> List[Dict[str, Any]]:
        """Tải log hiện tại từ GitHub."""
        try:
            content, sha = self.client.get_content(self.config.log_path)
        except Exception as exc:
            print(f"[AUTO PUSH] Không thể tải log từ GitHub: {exc}")
            return []

        self.log_sha = sha
        if not content:
            self.log_entries = []
        else:
            try:
                self.log_entries = json.loads(content.decode("utf-8"))
            except json.JSONDecodeError:
                print("[AUTO PUSH] Log từ GitHub không hợp lệ. Bắt đầu bằng danh sách rỗng.")
                self.log_entries = []

        self.signatures = {
            entry["signature"]: entry
            for entry in self.log_entries
            if entry.get("category") == "video" and entry.get("signature")
        }
        return self.log_entries

    def convert_remote_legacy_log(self, legacy_path: str = "Subtitles/processed_files.log") -> Optional[List[Dict[str, Any]]]:
        """Nếu repo còn log dạng cũ, chuyển sang JSON và xóa file cũ."""
        try:
            content, sha = self.client.get_content(legacy_path)
        except Exception:
            return None
        if not content:
            return None

        lines = content.decode("utf-8").strip().splitlines()
        converted: List[Dict[str, Any]] = []
        for line in lines:
            parts = line.split("|")
            if len(parts) < 2:
                continue
            old_name = parts[0]
            new_name = parts[1]
            timestamp = parts[2] if len(parts) > 2 else ""
            signature = parts[3] if len(parts) > 3 else ""
            converted.append(
                {
                    "old_name": old_name,
                    "new_name": new_name,
                    "timestamp": timestamp or datetime.datetime.utcnow().isoformat(),
                    "signature": signature,
                    "category": "video",
                }
            )

        if not converted:
            return None

        remote_path = f"{self.config.logs_dir}/legacy_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        self.client.put_content(
            remote_path,
            json.dumps(converted, ensure_ascii=False, indent=2).encode("utf-8"),
            message="Convert legacy processed_files log",
        )
        if sha:
            self.client.delete_content(legacy_path, sha, message="Remove legacy processed_files.log")
        print(f"[AUTO PUSH] Đã chuyển đổi {legacy_path} thành {remote_path}")
        return converted

    def has_signature(self, signature: Optional[str]) -> bool:
        if not signature:
            return False
        return signature in self.signatures

    def record_entry(self, entry: Dict[str, Any], local_path: Optional[str] = None, local_file: Optional[str] = None) -> None:
        """
        Ghi nhận một entry và upload file nếu cần.
        entry phải chứa `category`.
        """
        category = entry.get("category", "video")
        file_path = local_path or local_file

        if category == "video":
            signature = entry.get("signature")
            if signature and signature in self.signatures:
                return
            self.signatures[signature] = entry
            self.pending_entries.append(entry)
        elif category == "subtitle":
            if file_path and os.path.exists(file_path):
                remote_path = self._upload_file(file_path, prefix=self.config.subtitle_dir)
                entry["remote_path"] = remote_path
            self.pending_entries.append(entry)
        else:
            self.pending_entries.append(entry)

    def flush(self) -> None:
        """Upload toàn bộ pending entries vào log trên GitHub."""
        if not self.pending_entries:
            return

        merged_entries = self.log_entries + self.pending_entries
        try:
            new_sha = self.client.put_content(
                self.config.log_path,
                json.dumps(merged_entries, ensure_ascii=False, indent=2).encode("utf-8"),
                message=f"Update logs ({len(self.pending_entries)} entries)",
                sha=self.log_sha,
            )
            self.log_entries = merged_entries
            self.log_sha = new_sha
            self.pending_entries = []
            print("[AUTO PUSH] Đã đồng bộ log lên GitHub.")
        except Exception as exc:
            print(f"[AUTO PUSH] Không thể cập nhật log: {exc}")

    def _upload_file(self, local_path: str, prefix: str) -> str:
        """Upload file và trả về đường dẫn remote."""
        file_name = os.path.basename(local_path)
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        remote_path = f"{prefix}/{timestamp}_{file_name}"
        try:
            with open(local_path, "rb") as f:
                content = f.read()
            self.client.put_content(
                remote_path,
                content,
                message=f"Upload {file_name}",
            )
            print(f"[AUTO PUSH] Đã upload file {file_name} lên {remote_path}")
        except Exception as exc:
            print(f"[AUTO PUSH] Không thể upload {local_path}: {exc}")
        return remote_path

    def upload_log_snapshot(self, entries: List[Dict[str, Any]], filename_prefix: str = "run") -> Optional[str]:
        if not entries:
            return None
        remote_path = f"{self.config.logs_dir}/{filename_prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            self.client.put_content(
                remote_path,
                json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8"),
                message=f"Upload {filename_prefix} log snapshot",
            )
            print(f"[AUTO PUSH] Đã upload log snapshot tới {remote_path}")
            return remote_path
        except Exception as exc:
            print(f"[AUTO PUSH] Không thể upload log snapshot: {exc}")
            return None

