"""
MetadataLoader - QThread để load metadata của MKV files trong background.
"""
from __future__ import annotations

import os
from PySide6 import QtCore


class MetadataLoader(QtCore.QThread):
    """Worker thread để load metadata của các file MKV trong background."""
    
    metadata_loaded_signal = QtCore.Signal(str, bool)  # filepath, success
    
    def __init__(self, file_paths: list[str], parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
    
    def run(self):
        """Load metadata cho từng file trong background."""
        for file_path in self.file_paths:
            if self.isInterruptionRequested():
                break
            
            if not file_path or not os.path.exists(file_path):
                continue
            
            try:
                # Import và load metadata
                from mkvprocessor.ffmpeg_helper import probe_file
                probe = probe_file(file_path)
                
                # Parse tracks
                subs = []
                audios = []
                
                # Parse subtitle tracks
                for stream in probe.get("streams", []):
                    if stream.get("codec_type") == "subtitle":
                        subs.append((
                            stream.get("index", -1),
                            stream.get("tags", {}).get("language", "und"),
                            stream.get("tags", {}).get("title", ""),
                            stream.get("codec_name", "unknown"),
                        ))
                
                # Parse audio tracks
                for order, stream in enumerate(probe.get("streams", [])):
                    if stream.get("codec_type") == "audio":
                        bitrate_raw = stream.get("bit_rate") or stream.get("tags", {}).get("BPS")
                        try:
                            bitrate = int(bitrate_raw) if bitrate_raw else 0
                        except (TypeError, ValueError):
                            bitrate = 0
                        audios.append((
                            stream.get("index", -1),
                            stream.get("channels", 0),
                            stream.get("tags", {}).get("language", "und"),
                            stream.get("tags", {}).get("title", ""),
                            bitrate,
                            order,
                        ))
                
                # Parse resolution
                video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
                resolution = "?"
                if video_stream and "width" in video_stream and "height" in video_stream:
                    w, h = int(video_stream["width"]), int(video_stream["height"])
                    if w >= 7680 or h >= 4320:
                        resolution = "8K"
                    elif w >= 3840 or h >= 2160:
                        resolution = "4K"
                    elif w >= 2560 or h >= 1440:
                        resolution = "2K"
                    elif w >= 1920 or h >= 1080:
                        resolution = "FHD"
                    elif w >= 1280 or h >= 720:
                        resolution = "HD"
                    elif w >= 720 or h >= 480:
                        resolution = "480p"
                    else:
                        resolution = f"{w}p"
                
                # Parse year
                format_tags = probe.get("format", {}).get("tags", {})
                year = format_tags.get("year", "").strip()
                
                # Emit signal với metadata (main_window sẽ gọi ensure_options_metadata để cập nhật options)
                # Chúng ta chỉ parse ở đây để giảm tải cho main thread
                self.metadata_loaded_signal.emit(file_path, True)
                
            except Exception as e:
                # Emit với success=False để đánh dấu lỗi
                print(f"[WARNING] Không thể đọc metadata của {os.path.basename(file_path)}: {e}")
                self.metadata_loaded_signal.emit(file_path, False)

