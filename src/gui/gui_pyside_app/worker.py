"""
Worker - QThread for processing MKV files in background.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import traceback

from PySide6 import QtCore


class QtSignalLogHandler(logging.Handler):
    """Custom logging handler that emits log messages via Qt signal."""
    
    def __init__(self, signal: QtCore.SignalInstance):
        super().__init__()
        self.signal = signal
    
    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            # Map logging levels to our signal levels
            if level in ("ERROR", "CRITICAL"):
                signal_level = "ERROR"
            elif level == "WARNING":
                signal_level = "WARNING"
            else:
                signal_level = "INFO"
            self.signal.emit(msg, signal_level)
        except Exception:
            # Ignore errors in logging handler to avoid infinite loops
            pass


class Worker(QtCore.QThread):
    """Worker thread for processing MKV files."""

    log_signal = QtCore.Signal(str, str)  # text, level
    progress_signal = QtCore.Signal(int, int, str)  # current, total, filename
    finished_signal = QtCore.Signal(bool)  # success

    def __init__(self, folder: str, selected_files: list[str] | None = None):
        super().__init__()
        self.folder = folder
        self.selected_files = selected_files or []
        self.log_handler = None

    def run(self):
        selected_backup = None
        old_handlers = []
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

            # Setup custom logging handler
            root_logger = logging.getLogger()
            # Remove existing StreamHandlers that might have None streams
            for handler in root_logger.handlers[:]:
                if isinstance(handler, logging.StreamHandler):
                    try:
                        # Check if stream is valid
                        if handler.stream is None or (hasattr(handler.stream, 'write') and handler.stream.write is None):
                            root_logger.removeHandler(handler)
                            handler.close()
                        else:
                            old_handlers.append(handler)
                    except Exception:
                        # If we can't check, remove it to be safe
                        root_logger.removeHandler(handler)
                        handler.close()
            
            # Add our custom handler
            self.log_handler = QtSignalLogHandler(self.log_signal)
            self.log_handler.setFormatter(logging.Formatter('%(message)s'))
            self.log_handler.setLevel(logging.INFO)
            root_logger.addHandler(self.log_handler)
            root_logger.setLevel(logging.INFO)

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

            # Backup original stdout/stderr
            old_stdout = sys.stdout if sys.stdout and hasattr(sys.stdout, 'write') else None
            old_stderr = sys.stderr if sys.stderr and hasattr(sys.stderr, 'write') else None
            
            # Only redirect if we have valid streams to restore
            if old_stdout is not None:
                sys.stdout = Redirect("INFO", self.log_signal)
            if old_stderr is not None:
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
            # Restore environment
            if self.selected_files:
                if selected_backup is None:
                    os.environ.pop("MKV_SELECTED_FILES", None)
                else:
                    os.environ["MKV_SELECTED_FILES"] = selected_backup
            
            # Remove our custom handler
            if self.log_handler:
                root_logger = logging.getLogger()
                root_logger.removeHandler(self.log_handler)
                self.log_handler.close()
                self.log_handler = None
            
            # Restore old handlers
            for handler in old_handlers:
                root_logger.addHandler(handler)
            
            # Restore stdout/stderr safely
            if old_stdout is not None:
                sys.stdout = old_stdout
            elif sys.__stdout__ is not None and hasattr(sys.__stdout__, 'write'):
                sys.stdout = sys.__stdout__
            
            if old_stderr is not None:
                sys.stderr = old_stderr
            elif sys.__stderr__ is not None and hasattr(sys.__stderr__, 'write'):
                sys.stderr = sys.__stderr__
