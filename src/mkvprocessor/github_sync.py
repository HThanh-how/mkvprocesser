"""
Module for syncing subtitles and logs to GitHub using personal access token.
Reads configuration from auto_push_config.json or environment variables.
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


@dataclass
class AutoPushConfig:
    """Configuration for auto-push to GitHub."""
    token: str
    repo: str
    branch: str = "main"
    log_path: str = "logs/processed.json"
    subtitle_dir: str = "subtitles"
    logs_dir: str = "logs"
    enabled: bool = True


def build_auto_push_config(settings: Dict[str, Any]) -> Optional[AutoPushConfig]:
    """Build AutoPushConfig from settings dictionary.
    
    Args:
        settings: Dictionary containing configuration settings
    
    Returns:
        AutoPushConfig instance if valid settings found, None otherwise
    """
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
    """Simple client for GitHub Content API."""

    def __init__(self, config: AutoPushConfig):
        """Initialize GitHub client.
        
        Args:
            config: AutoPushConfig instance with authentication and repo info
        """
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
        """Make HTTP request to GitHub API.
        
        Args:
            method: HTTP method (GET, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/repos/owner/repo/contents/path")
            params: Optional query parameters
            json_data: Optional JSON payload
        
        Returns:
            Response object from requests
        
        Raises:
            RuntimeError: If API returns error status code
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, params=params, json=json_data, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API error {response.status_code}: {response.text}")
        return response

    def get_content(self, path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get file content (base64) from repository.
        
        Args:
            path: File path in repository
        
        Returns:
            Tuple of (content bytes, sha string). Returns (None, None) if file not found.
        """
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
        """Upload (or update) file to repository. Returns new sha.
        
        Args:
            path: File path in repository
            content: File content as bytes
            message: Commit message
            sha: Optional existing file sha (for updates)
        
        Returns:
            New file sha after upload
        """
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
        """Delete file from repository.
        
        Args:
            path: File path in repository
            sha: File sha (required for deletion)
            message: Commit message
        """
        payload = {"message": message, "sha": sha, "branch": self.config.branch}
        self._request(
            "DELETE",
            f"/repos/{self.config.repo}/contents/{path}",
            json_data=payload,
        )


class RemoteSyncManager:
    """
    Manage logs and upload subtitles to GitHub.
    - Logs are stored at log_path (JSON list).
    - Subtitles are stored in subtitle_dir.
    """

    def __init__(self, config: AutoPushConfig):
        """Initialize RemoteSyncManager.
        
        Args:
            config: AutoPushConfig instance
        """
        self.config = config
        self.client = GitHubClient(config)
        self.log_entries: List[Dict[str, Any]] = []
        self.log_sha: Optional[str] = None
        self.pending_entries: List[Dict[str, Any]] = []
        self.signatures: Dict[str, Dict[str, Any]] = {}

    def load_remote_logs(self) -> List[Dict[str, Any]]:
        """Load current logs from GitHub.
        
        Returns:
            List of log entries from GitHub
        """
        try:
            content, sha = self.client.get_content(self.config.log_path)
        except (RuntimeError, requests.RequestException) as exc:
            logger.error(f"[AUTO PUSH] Failed to load log from GitHub: {exc}")
            return []

        self.log_sha = sha
        if not content:
            self.log_entries = []
        else:
            try:
                self.log_entries = json.loads(content.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("[AUTO PUSH] Invalid log from GitHub. Starting with empty list.")
                self.log_entries = []

        self.signatures = {
            entry["signature"]: entry
            for entry in self.log_entries
            if entry.get("category") == "video" and entry.get("signature")
        }
        return self.log_entries

    def convert_remote_legacy_log(self, legacy_path: str = "Subtitles/processed_files.log") -> Optional[List[Dict[str, Any]]]:
        """If repository still has old format log, convert to JSON and delete old file.
        
        Args:
            legacy_path: Path to legacy log file in repository
        
        Returns:
            List of converted entries, or None if conversion not needed
        """
        try:
            content, sha = self.client.get_content(legacy_path)
        except (RuntimeError, requests.RequestException):
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
        logger.info(f"[AUTO PUSH] Converted {legacy_path} to {remote_path}")
        return converted

    def has_signature(self, signature: Optional[str]) -> bool:
        """Check if signature exists in remote logs.
        
        Args:
            signature: File signature to check
        
        Returns:
            True if signature exists, False otherwise
        """
        if not signature:
            return False
        return signature in self.signatures

    def record_entry(self, entry: Dict[str, Any], local_path: Optional[str] = None, local_file: Optional[str] = None) -> None:
        """
        Record an entry and upload file if needed.
        Entry must contain `category`.
        
        Args:
            entry: Dictionary with entry data (must have 'category')
            local_path: Optional local file path for upload
            local_file: Optional local file path (alias for local_path)
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
        """Upload all pending entries to log on GitHub."""
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
            logger.info("[AUTO PUSH] Synced log to GitHub.")
        except (RuntimeError, requests.RequestException) as exc:
            logger.error(f"[AUTO PUSH] Failed to update log: {exc}")

    def _upload_file(self, local_path: str, prefix: str) -> str:
        """Upload file and return remote path.
        
        Args:
            local_path: Path to local file
            prefix: Remote directory prefix
        
        Returns:
            Remote path where file was uploaded
        """
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
            logger.info(f"[AUTO PUSH] Uploaded file {file_name} to {remote_path}")
        except (IOError, OSError, RuntimeError, requests.RequestException) as exc:
            logger.error(f"[AUTO PUSH] Failed to upload {local_path}: {exc}")
        return remote_path

    def upload_log_snapshot(self, entries: List[Dict[str, Any]], filename_prefix: str = "run") -> Optional[str]:
        """Upload log snapshot to GitHub.
        
        Args:
            entries: List of log entries
            filename_prefix: Prefix for snapshot filename
        
        Returns:
            Remote path of uploaded snapshot, or None if upload fails
        """
        if not entries:
            return None
        remote_path = f"{self.config.logs_dir}/{filename_prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            self.client.put_content(
                remote_path,
                json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8"),
                message=f"Upload {filename_prefix} log snapshot",
            )
            logger.info(f"[AUTO PUSH] Uploaded log snapshot to {remote_path}")
            return remote_path
        except (RuntimeError, requests.RequestException) as exc:
            logger.error(f"[AUTO PUSH] Failed to upload log snapshot: {exc}")
            return None
