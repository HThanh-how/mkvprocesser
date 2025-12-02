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
    file_status_signal = QtCore.Signal(str, str)  # filepath, status (started/completed)
    finished_signal = QtCore.Signal(bool)  # success

    def __init__(self, folder: str, selected_files: list[str] | None = None):
        super().__init__()
        self.folder = folder
        self.selected_files = selected_files or []
        self.log_handler = None
        self._current_processing_file = None  # Track file đang xử lý

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
                        # Check if stream is valid by trying to access it
                        stream = handler.stream
                        if stream is None:
                            root_logger.removeHandler(handler)
                            handler.close()
                        elif not hasattr(stream, 'write'):
                            root_logger.removeHandler(handler)
                            handler.close()
                        else:
                            # Try to call write to verify it's callable
                            try:
                                # Just check if it's callable, don't actually write
                                if not callable(getattr(stream, 'write', None)):
                                    root_logger.removeHandler(handler)
                                    handler.close()
                                else:
                                    old_handlers.append(handler)
                            except Exception:
                                # If we can't verify, remove it to be safe
                                root_logger.removeHandler(handler)
                                handler.close()
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
                        import re
                        # Detect progress from log
                        if text.startswith("Processing file") or text.startswith("Đang xử lý file"):
                            # Parse "Processing file X/Y: filename"
                            match = re.search(r"(\d+)/(\d+):\s*(.+)", text)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                filename = match.group(3)
                                worker_ref.progress_signal.emit(current, total, filename)
                        # Detect file started processing
                        elif "PROCESSING FILE:" in text:
                            # Parse "===== PROCESSING FILE: /path/to/file.mkv ====="
                            match = re.search(r"PROCESSING FILE:\s*(.+)", text)
                            if match:
                                import os
                                filepath = match.group(1).strip()
                                # Normalize filepath để đảm bảo consistency
                                normalized_filepath = os.path.normpath(os.path.abspath(filepath))
                                worker_ref.file_status_signal.emit(normalized_filepath, "started")
                                # Nếu có file trước đó đang xử lý, đánh dấu nó đã xong
                                if hasattr(worker_ref, '_current_processing_file'):
                                    if worker_ref._current_processing_file:
                                        worker_ref.file_status_signal.emit(worker_ref._current_processing_file, "completed")
                                worker_ref._current_processing_file = normalized_filepath
                        # Detect overall completion
                        elif "PROCESSING COMPLETED" in text:
                            # Đánh dấu file cuối cùng đã xong
                            if hasattr(worker_ref, '_current_processing_file'):
                                if worker_ref._current_processing_file:
                                    worker_ref.file_status_signal.emit(worker_ref._current_processing_file, "completed")
                                    worker_ref._current_processing_file = None
                        # Detect errors (có thể thêm pattern khác nếu cần)
                        elif "ERROR" in text.upper() or "FAILED" in text.upper() or "Exception" in text:
                            # Nếu có file đang xử lý, đánh dấu failed
                            if hasattr(worker_ref, '_current_processing_file'):
                                if worker_ref._current_processing_file:
                                    worker_ref.file_status_signal.emit(worker_ref._current_processing_file, "failed")

                def flush(self):
                    pass

            # Backup original stdout/stderr - check if they're valid
            def is_valid_stream(stream):
                """Check if a stream is valid for writing."""
                try:
                    return (stream is not None and 
                           hasattr(stream, 'write') and 
                           callable(getattr(stream, 'write', None)))
                except Exception:
                    return False
            
            old_stdout = sys.stdout if is_valid_stream(sys.stdout) else None
            old_stderr = sys.stderr if is_valid_stream(sys.stderr) else None
            
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
            
            # Restore stdout/stderr FIRST before restoring handlers
            # This ensures handlers have valid streams
            def is_valid_stream(stream):
                """Check if a stream is valid for writing."""
                try:
                    return (stream is not None and 
                           hasattr(stream, 'write') and 
                           callable(getattr(stream, 'write', None)))
                except Exception:
                    return False
            
            if old_stdout is not None:
                sys.stdout = old_stdout
            elif is_valid_stream(sys.__stdout__):
                sys.stdout = sys.__stdout__
            
            if old_stderr is not None:
                sys.stderr = old_stderr
            elif is_valid_stream(sys.__stderr__):
                sys.stderr = sys.__stderr__
            
            # Remove our custom handler
            root_logger = logging.getLogger()
            if self.log_handler:
                try:
                    root_logger.removeHandler(self.log_handler)
                    self.log_handler.close()
                except Exception:
                    pass  # Ignore errors when removing handler
                self.log_handler = None
            
            # Restore old handlers - but only if they're still valid
            for handler in old_handlers:
                try:
                    # Check if handler is still valid before restoring
                    if isinstance(handler, logging.StreamHandler):
                        # For StreamHandler, check if stream is valid
                        stream = handler.stream
                        if stream is not None and hasattr(stream, 'write') and callable(getattr(stream, 'write', None)):
                            # Check if handler already exists
                            if handler not in root_logger.handlers:
                                root_logger.addHandler(handler)
                    else:
                        # For other handlers, just add if not exists
                        if handler not in root_logger.handlers:
                            root_logger.addHandler(handler)
                except Exception:
                    # Skip invalid handlers
                    pass
