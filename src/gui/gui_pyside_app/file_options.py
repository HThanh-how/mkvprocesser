"""
FileOptions - Lưu trữ options cho một file MKV.
"""
from __future__ import annotations


class FileOptions:
    """Lưu trữ options cho một file MKV"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.force_process = False
        self.process_enabled = True
        
        # Subtitle options - 2 danh sách riêng biệt
        self.export_subtitles = True  # Xuất ra file SRT
        self.export_subtitle_indices: list[int] = []  # Track indices để xuất SRT
        
        self.mux_subtitles = True  # Mux subtitle vào video output
        self.mux_subtitle_indices: list[int] = []  # Track indices để mux
        
        # Audio options
        self.mux_audio = True
        self.selected_audio_indices: list[int] = []  # Theo thứ tự (có thể kéo thả)
        
        # Output options
        self.rename_enabled = True
        self.custom_output_name = ""

        # Metadata caches (không cần serialize)
        self.metadata_ready = False
        self.subtitle_meta: dict[int, dict] = {}
        self.audio_meta: dict[int, dict] = {}
        self.cached_subs: list[tuple] = []
        self.cached_audios: list[tuple] = []
        self.cached_resolution: str = ""
        self.cached_year: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "force_process": self.force_process,
            "process_enabled": self.process_enabled,
            "export_subtitles": self.export_subtitles,
            "export_subtitle_indices": self.export_subtitle_indices,
            "mux_subtitles": self.mux_subtitles,
            "mux_subtitle_indices": self.mux_subtitle_indices,
            "mux_audio": self.mux_audio,
            "selected_audio_indices": self.selected_audio_indices,
            "rename_enabled": self.rename_enabled,
            "custom_output_name": self.custom_output_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileOptions":
        options = cls(data.get("file_path", ""))
        options.force_process = data.get("force_process", False)
        options.process_enabled = data.get("process_enabled", True)
        options.export_subtitles = data.get("export_subtitles", True)
        options.export_subtitle_indices = data.get("export_subtitle_indices", [])
        options.mux_subtitles = data.get("mux_subtitles", True)
        options.mux_subtitle_indices = data.get("mux_subtitle_indices", [])
        options.mux_audio = data.get("mux_audio", True)
        options.selected_audio_indices = data.get("selected_audio_indices", [])
        options.rename_enabled = data.get("rename_enabled", True)
        options.custom_output_name = data.get("custom_output_name", "")
        options.metadata_ready = False
        options.subtitle_meta = {}
        options.audio_meta = {}
        options.cached_subs = []
        options.cached_audios = []
        options.cached_resolution = ""
        options.cached_year = ""
        return options
