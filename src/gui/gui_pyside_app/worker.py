"""
Worker - QThread for processing MKV files in background.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import traceback

from PySide6 import QtCore


class Worker(QtCore.QThread):
    """Worker thread for processing MKV files."""

    log_signal = QtCore.Signal(str, str)  # text, level
    progress_signal = QtCore.Signal(int, int, str)  # current, total, filename
    finished_signal = QtCore.Signal(bool)  # success

    def __init__(self, folder: str, selected_files: list[str] | None = None):
        super().__init__()
        self.folder = folder
        self.selected_files = selected_files or []

    def run(self):
        selected_backup = None
        try:
            # Try importing from new package, fallback to legacy names
            module_candidates = [
                "mkvprocessor.processing_core",
                "mkvprocessor.script",
                "processing_core",
                "script",
            ]
            script = None
            for module_name in module_candidates:
                try:
                    script = importlib.import_module(module_name)
                    break
                except ModuleNotFoundError:
                    continue
            if script is None:
                raise ImportError("Cannot import processing_core module")
            selected_backup = os.environ.get("MKV_SELECTED_FILES")
            if self.selected_files:
                os.environ["MKV_SELECTED_FILES"] = json.dumps(self.selected_files)

            worker_ref = self

            class Redirect:
                def __init__(self, level: str, signal: QtCore.SignalInstance):
                    self.level = level
                    self.signal = signal

                def write(self, text: str):
                    text = text.strip()
                    if text:
                        self.signal.emit(text, self.level)
                        # Detect progress from log
                        if text.startswith("Processing file") or text.startswith("Đang xử lý file"):
                            # Parse "Processing file X/Y: filename"
                            import re
                            match = re.search(r"(\d+)/(\d+):\s*(.+)", text)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                filename = match.group(3)
                                worker_ref.progress_signal.emit(current, total, filename)

                def flush(self):
                    pass

            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = Redirect("INFO", self.log_signal)
            sys.stderr = Redirect("ERROR", self.log_signal)

            # Emit initial progress
            total = len(self.selected_files) if self.selected_files else 0
            if total > 0:
                self.progress_signal.emit(0, total, "Starting...")

            script.main(self.folder)
            self.finished_signal.emit(True)
        except Exception as exc:
            self.log_signal.emit(str(exc), "ERROR")
            self.log_signal.emit(traceback.format_exc(), "ERROR")
            self.finished_signal.emit(False)
        finally:
            if self.selected_files:
                if selected_backup is None:
                    os.environ.pop("MKV_SELECTED_FILES", None)
                else:
                    os.environ["MKV_SELECTED_FILES"] = selected_backup
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
