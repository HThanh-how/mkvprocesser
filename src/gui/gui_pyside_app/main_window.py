"""
MainWindow - Cửa sổ chính của ứng dụng PySide6 GUI.
Tương tự MKVToolNix với đầy đủ tính năng.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from PySide6 import QtCore, QtGui, QtWidgets

# Add src to sys.path to import mkvprocessor
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mkvprocessor.config_manager import (
    get_config_path,
    load_raw_user_config,
    load_user_config,
    save_user_config,
)

# Hỗ trợ import khi chạy như package module hoặc chạy trực tiếp file
try:
    from .file_options import FileOptions
    from .theme import DARK_THEME, get_status_color
    from .worker import Worker
    from .metadata_loader import MetadataLoader
except ImportError:
    from file_options import FileOptions  # type: ignore
    from theme import DARK_THEME, get_status_color  # type: ignore
    from worker import Worker  # type: ignore
    from metadata_loader import MetadataLoader  # type: ignore

from components.processing_tab import ProcessingTab
from components.settings_tab import SettingsTab
from components.log_tab import LogTab



class DraggableListWidget(QtWidgets.QListWidget):
    """QListWidget hỗ trợ drag & drop để đổi thứ tự"""
    orderChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.model().rowsMoved.connect(self._on_rows_moved)

    def _on_rows_moved(self):
        self.orderChanged.emit()


class UpdateDownloadWorker(QtCore.QThread):
    """Worker thread để download update trong background."""
    
    progress_signal = QtCore.Signal(int, int, int)  # downloaded, total, percent
    finished_signal = QtCore.Signal(object)  # download_path or None
    error_signal = QtCore.Signal(str)  # error message
    
    def __init__(self, update_manager, exe_asset, parent=None):
        super().__init__(parent)
        self.update_manager = update_manager
        self.exe_asset = exe_asset
    
    def run(self):
        """Download update file in background thread."""
        try:
            def progress_callback(url, downloaded, total):
                if total > 0:
                    percent = int((downloaded / total) * 100)
                    # Emit signal to update UI (thread-safe)
                    self.progress_signal.emit(downloaded, total, percent)
            
            download_path = self.update_manager.download_update(self.exe_asset, progress_callback)
            self.finished_signal.emit(download_path)
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(None)


class MainWindow(QtWidgets.QMainWindow):
    """Cửa sổ chính của ứng dụng"""
    
    # Supported video file extensions
    SUPPORTED_VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".webm")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MKV Processor (PySide6)")
        self.resize(1200, 800)
        self.setMinimumSize(600, 400)  # Allow window to be resized smaller
        self.config = load_user_config()
        # Đảm bảo luôn có thuộc tính select_folder để connect signal an toàn
        # Hàm thực tế sẽ sử dụng folder_edit sau khi build_ui tạo xong.
        def _select_folder_fallback():
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Chọn thư mục")
            if folder:
                # folder_edit sẽ tồn tại sau khi build_ui chạy xong
                if hasattr(self, "folder_edit"):
                    self.folder_edit.setText(folder)
                self.config["input_folder"] = folder
                save_user_config(self.config)
                if hasattr(self, "refresh_file_list"):
                    self.refresh_file_list()
        self.select_folder = _select_folder_fallback
        # Lazy import processing_core - chỉ import khi thực sự cần để tăng tốc khởi động
        self.script = None
        self._script_module_name = None
        self.worker: Worker | None = None
        self.file_options: dict[str, FileOptions] = {}
        self.current_file_path: str | None = None
        self.session_log_file: Path | None = None
        self.log_view: QtWidgets.QPlainTextEdit | None = None
        self.current_selected_path: str | None = None
        self.metadata_loader_thread: QtCore.QThread | None = None  # Thread để load metadata background
        
        # Khởi tạo processing_files_map để tránh AttributeError
        self.processing_files_map: dict[str, str] = {}  # normalized_filepath -> original_filepath
        
        # Lazy import UpdateManager - chỉ import khi cần check updates
        self.update_manager = None
        self._update_manager_imported = False
        
        # Update download worker thread
        self.update_download_worker = None

        self.build_ui()
        # Gọi apply_theme an toàn (tránh crash nếu có lỗi nhỏ về theme)
        apply_theme_fn = getattr(self, "apply_theme", None)
        if callable(apply_theme_fn):
            apply_theme_fn()
        # refresh_file_list chạy ngay nhưng tối ưu - chỉ hiển thị file list, metadata lazy load
        # Delay lại một lát để UI load xong
        QtCore.QTimer.singleShot(
            100, 
            lambda: self._lazy_refresh_file_list()
        )

        # refresh_file_list chạy ngay nhưng tối ưu - chỉ hiển thị file list, metadata lazy load
        QtCore.QTimer.singleShot(
            100,
            lambda: self._lazy_refresh_file_list()
        )
    
    def _create_message_box(self, icon: QtWidgets.QMessageBox.Icon, title: str, text: str, 
                           buttons: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.Ok,
                           default_button: QtWidgets.QMessageBox.StandardButton | None = None) -> QtWidgets.QMessageBox:
        """Create a QMessageBox with dark theme applied."""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setStyleSheet(DARK_THEME)  # Apply dark theme
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(buttons)
        if default_button:
            msg_box.setDefaultButton(default_button)
        return msg_box
    
    def show_info_message(self, title: str, message: str) -> None:
        """Show information dialog with theme."""
        msg_box = self._create_message_box(
            QtWidgets.QMessageBox.Information,
            title,
            message
        )
        msg_box.exec()
    
    def _get_script_module(self):
        """Lazy load processing_core module - chỉ import khi cần"""
        if self.script is None:
            module_candidates = [
                "mkvprocessor.processing_core",
                "mkvprocessor.legacy_api",
                "processing_core",
                "legacy_api",
            ]
            for module_name in module_candidates:
                try:
                    self.script = importlib.import_module(module_name)
                    self._script_module_name = module_name
                    break
                except ModuleNotFoundError:
                    continue
            if self.script is None:
                raise ImportError("Cannot import processing_core module")
        return self.script
    
    def _get_update_manager(self):
        """Lazy load UpdateManager - chỉ import khi cần"""
        if not self._update_manager_imported:
            try:
                # Check if requests is available first
                try:
                    import requests
                except ImportError:
                    error_msg = "[WARNING] Thư viện 'requests' chưa được cài đặt. Cài đặt bằng: pip install requests"
                    print(error_msg)
                    if self.log_view:
                        self.log_view.appendPlainText(error_msg)
                    self.update_manager = None
                    self._update_manager_imported = True
                    return None
                
                # Try multiple import paths (support both source and exe)
                UpdateManager = None
                
                # If running from exe, try to load file directly
                if hasattr(sys, '_MEIPASS'):
                    meipass_path = Path(sys._MEIPASS)
                    # Try to add _MEIPASS to path if not already there
                    if str(meipass_path) not in sys.path:
                        sys.path.insert(0, str(meipass_path))
                    # Also try src path
                    src_path = meipass_path / "src"
                    if src_path.exists() and str(src_path) not in sys.path:
                        sys.path.insert(0, str(src_path))
                    # Try package folder directly (common in PyInstaller onefile)
                    meipass_mkv = meipass_path / "mkvprocessor"
                    if meipass_mkv.exists() and str(meipass_mkv) not in sys.path:
                        sys.path.insert(0, str(meipass_mkv))
                    meipass_lib_mkv = meipass_path / "lib" / "mkvprocessor"
                    if meipass_lib_mkv.exists() and str(meipass_lib_mkv) not in sys.path:
                        sys.path.insert(0, str(meipass_lib_mkv))
                    
                    # Try loading from base_library.zip if present
                    base_zip = meipass_path / "base_library.zip"
                    if base_zip.exists():
                        try:
                            import zipfile, tempfile
                            with zipfile.ZipFile(base_zip, "r") as zf:
                                for candidate in [
                                    "mkvprocessor/update_manager.py",
                                    "mkvprocessor/update_manager.pyc",
                                    "update_manager.py",
                                    "update_manager.pyc",
                                ]:
                                    if candidate in zf.namelist():
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(candidate).suffix) as tmp:
                                            tmp.write(zf.read(candidate))
                                            tmp_path = Path(tmp.name)
                                        import importlib.util as importlib_util
                                        spec = importlib_util.spec_from_file_location("update_manager", str(tmp_path))
                                        if spec and spec.loader:
                                            module = importlib_util.module_from_spec(spec)
                                            spec.loader.exec_module(module)
                                            UpdateManager = getattr(module, 'UpdateManager', None)
                                            if UpdateManager:
                                                log_msg = f"[INFO] Loaded UpdateManager from base_library.zip:{candidate}"
                                                print(log_msg)
                                                if self.log_view:
                                                    self.log_view.appendPlainText(log_msg)
                                                break
                        except Exception as e:
                            print(f"[DEBUG] Failed to load UpdateManager from base_library.zip: {e}")
                    
                    # Try to load update_manager.py directly from file
                    possible_paths = [
                        meipass_path / "mkvprocessor" / "update_manager.py",
                        meipass_path / "src" / "mkvprocessor" / "update_manager.py",
                        meipass_path / "lib" / "mkvprocessor" / "update_manager.py",
                        meipass_path / "update_manager.py",
                    ]
                    
                    for update_manager_path in possible_paths:
                        if update_manager_path.exists():
                            try:
                                # Use importlib.util from global scope, not import locally
                                import importlib.util as importlib_util
                                spec = importlib_util.spec_from_file_location(
                                    "update_manager", str(update_manager_path)
                                )
                                if spec and spec.loader:
                                    module = importlib_util.module_from_spec(spec)
                                    spec.loader.exec_module(module)
                                    UpdateManager = getattr(module, 'UpdateManager', None)
                                    if UpdateManager:
                                        log_msg = f"[INFO] Loaded UpdateManager from: {update_manager_path}"
                                        print(log_msg)
                                        if self.log_view:
                                            self.log_view.appendPlainText(log_msg)
                                        break
                            except Exception as e:
                                log_msg = f"[DEBUG] Failed to load from {update_manager_path}: {e}"
                                print(log_msg)
                                continue
                
                # If not loaded yet, try normal import (importlib is already imported at top)
                if not UpdateManager:
                    import_candidates = [
                        "mkvprocessor.update_manager",
                        "update_manager",
                    ]
                    
                    for module_name in import_candidates:
                        try:
                            # Use importlib from global scope (imported at top of file)
                            module = importlib.import_module(module_name)
                            UpdateManager = getattr(module, 'UpdateManager', None)
                            if UpdateManager:
                                break
                        except (ImportError, AttributeError):
                            continue
                
                # Final fallback: use embedded copy bundled with GUI
                if not UpdateManager:
                    try:
                        from . import update_manager_fallback  # type: ignore
                        UpdateManager = getattr(update_manager_fallback, "UpdateManager", None)
                        if UpdateManager:
                            log_msg = "[INFO] Loaded embedded update_manager_fallback"
                            print(log_msg)
                            if self.log_view:
                                self.log_view.appendPlainText(log_msg)
                    except Exception as e:
                        print(f"[DEBUG] Failed to load embedded update_manager_fallback: {e}")
                
                if not UpdateManager:
                    # Log available paths for debugging
                    debug_info = "Cannot import UpdateManager. Available paths:\n"
                    if hasattr(sys, '_MEIPASS'):
                        debug_info += f"  _MEIPASS: {sys._MEIPASS}\n"
                        meipass_path = Path(sys._MEIPASS)
                        debug_info += f"  Files in _MEIPASS: {list(meipass_path.iterdir())[:10]}\n"
                    debug_info += f"  sys.path: {sys.path[:5]}\n"
                    print(debug_info)
                    if self.log_view:
                        self.log_view.appendPlainText(debug_info)
                    raise ImportError(f"Cannot import UpdateManager")
                
                self.update_manager = UpdateManager()
                success_msg = "[INFO] UpdateManager đã được khởi tạo thành công"
                print(success_msg)
                if self.log_view:
                    self.log_view.appendPlainText(success_msg)
            except ImportError as e:
                error_msg = f"[WARNING] UpdateManager không khả dụng (ImportError): {e}"
                print(error_msg)
                if self.log_view:
                    self.log_view.appendPlainText(error_msg)
                import traceback
                traceback.print_exc()
                if self.log_view:
                    self.log_view.appendPlainText(traceback.format_exc())
                self.update_manager = None
            except Exception as e:
                error_msg = f"[WARNING] Lỗi khởi tạo UpdateManager: {e}"
                print(error_msg)
                if self.log_view:
                    self.log_view.appendPlainText(error_msg)
                import traceback
                traceback.print_exc()
                if self.log_view:
                    self.log_view.appendPlainText(traceback.format_exc())
                self.update_manager = None
            finally:
                self._update_manager_imported = True
        return self.update_manager
    
    def _lazy_refresh_file_list(self):
        """Chỉ refresh file list nếu đã có folder được chọn"""
        folder = self.folder_edit.text().strip()
        if folder and os.path.exists(folder):
            self.refresh_file_list()

    def build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.processing_tab = ProcessingTab(self)
        self.tabs.addTab(self.processing_tab, "Trình xử lý")
        
        self.log_tab = LogTab(self)
        self.tabs.addTab(self.log_tab, "Log")
        
        self.settings_tab = SettingsTab(self)
        self.tabs.addTab(self.settings_tab, "Settings")

        # === Wiring & Aliases (Backward Compatibility) ===
        # Processing Tab
        self.folder_edit = self.processing_tab.folder_edit
        self.browse_btn = self.processing_tab.browse_btn
        self.edit_folder_btn = self.processing_tab.edit_folder_btn
        self.file_tree = self.processing_tab.file_tree
        self.select_all_cb = self.processing_tab.select_all_cb
        self.file_count_label = self.processing_tab.file_count_label
        self.reload_btn = self.processing_tab.reload_btn
        self.start_btn = self.processing_tab.start_btn
        self.stop_btn = self.processing_tab.stop_btn
        self.file_progress = self.processing_tab.file_progress
        self.total_progress = self.processing_tab.total_progress
        
        # Connect Processing Signals
        self.browse_btn.clicked.connect(self.select_folder)
        self.edit_folder_btn.clicked.connect(self.enable_folder_manual_edit)
        self.reload_btn.clicked.connect(lambda: self.refresh_file_list())
        self.select_all_cb.clicked.connect(self.on_select_all_clicked)
        self.start_btn.clicked.connect(lambda: self.start_processing())
        self.stop_btn.clicked.connect(lambda: self.stop_processing())

        # Settings Tab
        self.language_combo = self.settings_tab.language_combo
        self.auto_upload_cb = self.settings_tab.auto_upload_cb
        self.repo_edit = self.settings_tab.repo_edit
        self.token_edit = self.settings_tab.token_edit
        
        # Connect Settings Signals
        self.language_combo.currentIndexChanged.connect(lambda index: self.on_language_changed(index))

        # Log Tab
        self.log_view = self.log_tab.log_view
        self.history_table = self.log_tab.history_table
        self.errors_view = self.log_tab.errors_view


        
        # Track update badge state
        self._has_update_badge = False

        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    # DELETED build_processing_tab (Moved to components/processing_tab.py)


    # DELETED on_github_link_clicked (Handled in components/processing_tab.py or simplified)


    def on_select_all_clicked(self, checked: bool):
        """Xử lý khi user click vào checkbox select all"""
        # checked = True nếu checkbox được check, False nếu uncheck
        self.file_tree.blockSignals(True)
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            if item is None:
                continue
            item.setCheckState(0, QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            path = item.data(0, QtCore.Qt.UserRole)
            if isinstance(path, str) and path in self.file_options:
                self.file_options[path].process_enabled = checked
        self.file_tree.blockSignals(False)
        self.update_select_all_state()

    def update_select_all_state(self):
        total = self.file_tree.topLevelItemCount()
        if total == 0:
            self.select_all_cb.blockSignals(True)
            self.select_all_cb.setCheckState(QtCore.Qt.Unchecked)
            self.select_all_cb.blockSignals(False)
            return
        
        checked = sum(1 for i in range(total) 
                     if (item := self.file_tree.topLevelItem(i)) is not None 
                     and item.checkState(0) == QtCore.Qt.Checked)
        
        self.select_all_cb.blockSignals(True)
        if checked == 0:
            self.select_all_cb.setCheckState(QtCore.Qt.Unchecked)
        elif checked == total:
            self.select_all_cb.setCheckState(QtCore.Qt.Checked)
        else:
            self.select_all_cb.setCheckState(QtCore.Qt.PartiallyChecked)
        self.select_all_cb.blockSignals(False)

    def enable_folder_manual_edit(self):
        self.folder_edit.setReadOnly(False)
        self.folder_edit.setFocus()

    def on_folder_edit_finished(self):
        self.folder_edit.setReadOnly(True)
        folder = self.folder_edit.text().strip()
        if folder:
            self.config["input_folder"] = folder
            save_user_config(self.config)
            self.refresh_file_list()

    # DELETED build_settings_tab (Moved to components/settings_tab.py)


    # DELETED toggle_token_visibility (Moved to components/settings_tab.py)


    # DELETED on_language_changed (Moved to components/settings_tab.py)


    # DELETED build_log_tab (Moved to components/log_tab.py)


    def apply_theme(self):
        self.setAcceptDrops(True)
        self.setStyleSheet(DARK_THEME)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.folder_edit.setText(path)
                self.config["input_folder"] = path
                save_user_config(self.config)
                self.refresh_file_list()
                break

    def select_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if folder:
            self.folder_edit.setText(folder)
            self.config["input_folder"] = folder
            save_user_config(self.config)
            self.refresh_file_list()

    def format_file_size(self, size_bytes: int) -> str:
        size: float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
            size /= 1024
        return f"{size:.1f}TB"

    def is_already_processed_by_name(self, filename: str) -> bool:
        """Kiểm tra file đã được xử lý dựa trên tiền tố tên file"""
        import re
        # Các tiền tố resolution: 8K_, 4K_, 2K_, FHD_, HD_, 480p_
        pattern = r"^(8K|4K|2K|FHD|HD|480p)_"
        return bool(re.match(pattern, filename))

    def probe_tracks(self, file_path: str) -> tuple[list, list]:
        from mkvprocessor.ffmpeg_helper import probe_file

        try:
            probe = probe_file(file_path)
        except Exception as e:
            print(f"[ERROR] Không thể probe file {file_path}: {e}")
            return [], []
        
        if "streams" not in probe:
            print(f"[WARNING] Probe không có streams: {file_path}")
            return [], []
        
        subs = []
        try:
            for stream in probe["streams"]:
                if stream.get("codec_type") == "subtitle":
                    subs.append((
                        stream.get("index", -1),
                        stream.get("tags", {}).get("language", "und"),
                        stream.get("tags", {}).get("title", ""),
                        stream.get("codec_name", ""),
                    ))
        except Exception as e:
            print(f"[ERROR] Lỗi khi đọc subtitle tracks: {e}")

        audios = []
        try:
            for order, stream in enumerate(probe["streams"]):
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
        except Exception as e:
            print(f"[ERROR] Lỗi khi đọc audio tracks: {e}")
            
        return subs, audios

    def ensure_options_metadata(self, file_path: str, options: FileOptions) -> bool:
        if options.metadata_ready and options.cached_subs and options.cached_audios:
            return True
        
        # Kiểm tra file có tồn tại không
        if not os.path.exists(file_path):
            print(f"[ERROR] File không tồn tại: {file_path}")
            options.cached_subs = []
            options.cached_audios = []
            options.cached_resolution = "?"
            options.metadata_ready = True
            return False
            
        try:
            from mkvprocessor.ffmpeg_helper import probe_file
            print(f"[DEBUG] Đang đọc metadata của: {os.path.basename(file_path)}")
            probe = probe_file(file_path)
            print(f"[DEBUG] Đã đọc probe thành công, có {len(probe.get('streams', []))} streams")
            
            subs, audios = self.probe_tracks(file_path)
            print(f"[DEBUG] Tìm thấy {len(subs)} subtitle tracks và {len(audios)} audio tracks")
            
            # Cache resolution - ALWAYS try to get it, even if cached_resolution exists
            # (because it might be "?" from previous failed attempt)
            video_stream = None
            # Try to find video stream
            for stream in probe.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if video_stream:
                # Try multiple ways to get width/height
                w = None
                h = None
                
                # Method 1: Direct width/height
                if "width" in video_stream and "height" in video_stream:
                    try:
                        w = int(video_stream["width"])
                        h = int(video_stream["height"])
                    except (ValueError, TypeError) as e:
                        log_msg = f"[DEBUG] Failed to parse width/height: {e}"
                        print(log_msg)
                
                # Method 2: coded_width/coded_height (for some codecs)
                if (w is None or h is None) and "coded_width" in video_stream and "coded_height" in video_stream:
                    try:
                        w = int(video_stream["coded_width"])
                        h = int(video_stream["coded_height"])
                    except (ValueError, TypeError):
                        pass
                
                # Method 3: display_aspect_ratio and sample_aspect_ratio (fallback)
                if w is None or h is None:
                    # Try to get from tags or other metadata
                    tags = video_stream.get("tags", {})
                    if "width" in tags:
                        try:
                            w = int(tags["width"])
                        except (ValueError, TypeError):
                            pass
                    if "height" in tags:
                        try:
                            h = int(tags["height"])
                        except (ValueError, TypeError):
                            pass
                
                if w and h:
                    if w >= 7680 or h >= 4320:
                        options.cached_resolution = "8K"
                    elif w >= 3840 or h >= 2160:
                        options.cached_resolution = "4K"
                    elif w >= 2560 or h >= 1440:
                        options.cached_resolution = "2K"
                    elif w >= 1920 or h >= 1080:
                        options.cached_resolution = "FHD"
                    elif w >= 1280 or h >= 720:
                        options.cached_resolution = "HD"
                    elif w >= 720 or h >= 480:
                        options.cached_resolution = "480p"
                    else:
                        options.cached_resolution = f"{w}p"
                    log_msg = f"[INFO] Đã lấy resolution: {options.cached_resolution} ({w}x{h}) từ {os.path.basename(file_path)}"
                    print(log_msg)
                    if self.log_view:
                        self.log_view.appendPlainText(log_msg)
                else:
                    # Log warning if can't get resolution
                    log_msg = f"[WARNING] Không thể lấy resolution từ {os.path.basename(file_path)}: width={w}, height={h}"
                    print(log_msg)
                    if self.log_view:
                        self.log_view.appendPlainText(log_msg)
                        self.log_view.appendPlainText(
                            f"[DEBUG] video_stream keys: {list(video_stream.keys())[:20]}"
                        )
                    options.cached_resolution = "unknown"
            else:
                # No video stream found
                log_msg = f"[WARNING] Không tìm thấy video stream trong {os.path.basename(file_path)}"
                print(log_msg)
                if self.log_view:
                    self.log_view.appendPlainText(log_msg)
                    self.log_view.appendPlainText(
                        f"[DEBUG] Streams: {[s.get('codec_type') for s in probe.get('streams', [])]}"
                    )
                options.cached_resolution = "unknown"
            
            # Cache year
            if not options.cached_year:
                format_tags = probe.get("format", {}).get("tags", {})
                options.cached_year = format_tags.get("year", "").strip()
                
            # Lưu vào options
            options.cached_subs = subs
            options.cached_audios = audios
        except FileNotFoundError as e:
            print(f"[ERROR] File không tìm thấy: {file_path} - {e}")
            options.cached_subs = []
            options.cached_audios = []
            options.cached_resolution = "?"
            options.metadata_ready = True
            return False
        except Exception as e:
            # Fallback: không có metadata nhưng vẫn hiển thị file
            import traceback
            print(f"[ERROR] Lỗi khi đọc metadata của {os.path.basename(file_path)}: {e}")
            print(f"[ERROR] Chi tiết: {traceback.format_exc()}")
            options.cached_subs = []
            options.cached_audios = []
            options.cached_resolution = "?"
            options.metadata_ready = True
            return False

        options.cached_subs = subs
        options.cached_audios = audios
        options.subtitle_meta = {
            idx: {"lang": lang, "title": title, "codec": codec}
            for idx, lang, title, codec in subs
        }
        options.audio_meta = {
            idx: {"lang": lang, "title": title, "channels": channels}
            for idx, channels, lang, title, *_ in audios
        }

        if subs:
            default_subs = [idx for idx, lang, *_ in subs if lang == "vie"] or [subs[0][0]]
            if not options.export_subtitle_indices:
                options.export_subtitle_indices = default_subs.copy()
            if not options.mux_subtitle_indices:
                options.mux_subtitle_indices = default_subs.copy()
        if audios and not options.selected_audio_indices:
            options.selected_audio_indices = self.pick_default_audio(audios)

        options.metadata_ready = True
        return True

    def summarize_list(self, indices: list[int], meta: dict[int, dict], limit: int = 3, with_channels: bool = False) -> str:
        if not indices:
            return "-"
        labels: list[str] = []
        for idx in indices:
            info = meta.get(idx)
            if not info:
                labels.append(f"#{idx}")
                continue
            lang = info.get("lang", "und").upper()
            if with_channels:
                ch = info.get("channels")
                if ch:
                    lang += f"({ch}ch)"
            title = info.get("title")
            if title:
                lang += f"/{title}"
            labels.append(lang)
        if len(labels) > limit:
            return ", ".join(labels[:limit]) + "…"
        return ", ".join(labels)

    def get_language_abbreviation(self, language_code: str) -> str:
        """Trả về tên viết tắt của ngôn ngữ"""
        lang_map = {
            'eng': 'ENG', 'vie': 'VIE', 'und': 'UNK', 'chi': 'CHI', 'zho': 'CHI',
            'jpn': 'JPN', 'kor': 'KOR', 'fra': 'FRA', 'deu': 'DEU', 'spa': 'SPA',
            'ita': 'ITA', 'rus': 'RUS', 'tha': 'THA', 'ind': 'IND', 'msa': 'MSA',
        }
        return lang_map.get(language_code.lower(), language_code.upper()[:3])

    def get_rename_preview(self, options: FileOptions) -> str:
        """Tính toán và trả về tên file mới sẽ được đổi"""
        if not options.rename_enabled:
            return ""
        
        # Đảm bảo metadata đã được load
        if not self.ensure_options_metadata(options.file_path, options):
            return ""
        
        resolution = options.cached_resolution or "unknown"
        year = options.cached_year
        base_name = os.path.splitext(os.path.basename(options.file_path))[0]
        
        # Lấy audio đầu tiên được chọn
        lang_part = None
        if options.selected_audio_indices and options.audio_meta:
            first_audio_idx = options.selected_audio_indices[0]
            audio_info = options.audio_meta.get(first_audio_idx)
            if audio_info:
                lang = audio_info.get("lang", "und")
                # Chỉ thêm lang_part nếu có language hợp lệ (không phải "und" hoặc "UNK")
                if lang and lang.lower() != "und":
                    title = audio_info.get("title", "")
                    lang_abbr = self.get_language_abbreviation(lang)
                    # Chỉ thêm nếu không phải UNK
                    if lang_abbr != "UNK":
                        if title and title != lang_abbr:
                            lang_part = f"{lang_abbr}_{title}"
                        else:
                            lang_part = lang_abbr
        
        # Tạo tên file mới
        parts = []
        if resolution and resolution != "unknown" and resolution != "?":
            parts.append(resolution)
        if lang_part:
            parts.append(lang_part)
        if year:
            parts.append(year)
        parts.append(base_name)
        
        new_name = "_".join(parts) + ".mkv"
        
        # Rút gọn nếu quá dài
        if len(new_name) > 50:
            new_name = new_name[:47] + "..."
        
        return new_name

    def get_file_config_summary(self, options: FileOptions) -> str:
        parts = []
        
        # Kiểm tra có subtitle không
        has_subs = bool(options.cached_subs) or bool(options.subtitle_meta)
        
        # Xuất SRT (độc lập)
        if has_subs:
            if options.export_subtitles:
                summary = self.summarize_list(options.export_subtitle_indices, options.subtitle_meta)
                parts.append(f"SRT↗ {summary}")
            else:
                parts.append("SRT↗ off")
        else:
            parts.append("SRT -")

        # Mux (audio + SRT gộp chung)
        if options.mux_audio:
            mux_parts = []
            if options.selected_audio_indices:
                summary = self.summarize_list(
                    options.selected_audio_indices,
                    options.audio_meta,
                    with_channels=True,
                )
                mux_parts.append(f"Audio {summary}")
            else:
                mux_parts.append("Audio auto")
            
            if has_subs and options.mux_subtitles:
                summary = self.summarize_list(options.mux_subtitle_indices, options.subtitle_meta)
                mux_parts.append(f"SRT→ {summary}")
            
            parts.append("Mux: " + " | ".join(mux_parts))
        else:
            parts.append("Mux off")

        if options.rename_enabled:
            rename_preview = self.get_rename_preview(options)
            if rename_preview:
                parts.append(f"Rename: {rename_preview}")
            else:
                parts.append("Rename ✓")
        return " | ".join(parts)

    def refresh_file_list(self):
        # Log start
        log_msg = "[INFO] Bắt đầu refresh file list..."
        print(log_msg)
        if self.log_view:
            self.log_view.appendPlainText(log_msg)
        
        # Không refresh nếu đang xử lý (tránh mất trạng thái đang xử lý)
        if self.worker and self.worker.isRunning():
            msg = "Không thể làm mới danh sách khi đang xử lý file.\nVui lòng đợi hoàn thành hoặc dừng xử lý."
            self.show_info_message("Đang xử lý", msg)
            return
        
        # Disable nút và hiển thị đang refresh
        if hasattr(self, 'reload_btn'):
            self.reload_btn.setEnabled(False)
            self.reload_btn.setText("⏳")
            self.reload_btn.setToolTip("Đang làm mới...")
        
        # Cập nhật file count label để hiển thị đang refresh
        if hasattr(self, 'file_count_label'):
            old_text = self.file_count_label.text()
            self.file_count_label.setText("Đang tải...")
            # Force update UI ngay lập tức
            QtWidgets.QApplication.processEvents()
        
        folder = self.folder_edit.text().strip()
        log_msg = f"[INFO] Folder được chọn: {folder}"
        print(log_msg)
        if self.log_view:
            self.log_view.appendPlainText(log_msg)
        
        if not folder:
            log_msg = "[WARNING] Chưa chọn folder"
            print(log_msg)
            if self.log_view:
                self.log_view.appendPlainText(log_msg)
            self.file_tree.clear()
            self.update_select_all_state()
            # Re-enable nút
            if hasattr(self, 'reload_btn'):
                self.reload_btn.setEnabled(True)
                self.reload_btn.setText("🔄")
                self.reload_btn.setToolTip("Làm mới")
            if hasattr(self, 'file_count_label'):
                self.file_count_label.setText("0 file")
            return
        
        if not os.path.exists(folder):
            log_msg = f"[ERROR] Folder không tồn tại: {folder}"
            print(log_msg)
            if self.log_view:
                self.log_view.appendPlainText(log_msg)
            self.file_tree.clear()
            self.update_select_all_state()
            # Re-enable nút
            if hasattr(self, 'reload_btn'):
                self.reload_btn.setEnabled(True)
                self.reload_btn.setText("🔄")
                self.reload_btn.setToolTip("Làm mới")
            if hasattr(self, 'file_count_label'):
                self.file_count_label.setText("0 file")
            QtWidgets.QMessageBox.warning(self, "Lỗi", f"Folder không tồn tại:\n{folder}")
            return

        try:
            # Load processed files log (lịch sử xử lý file)
            processed_old_names = set()  # Tên file cũ đã xử lý
            processed_new_names = set()  # Tên file mới (đã rename)
            processed_info = {}  # Thông tin chi tiết
            
            # 1. Đọc từ processed_files.log (format cũ)
            log_file = os.path.join(folder, "Subtitles", "processed_files.log")
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            parts = line.strip().split("|")
                            if len(parts) >= 2:
                                old_name = parts[0]
                                new_name = parts[1]
                                time_processed = parts[2] if len(parts) > 2 else ""
                                
                                processed_old_names.add(old_name)
                                processed_new_names.add(new_name)
                                processed_info[old_name] = {"new": new_name, "time": time_processed}
                                processed_info[new_name] = {"new": new_name, "time": time_processed}
                except Exception as e:
                    print(f"[WARNING] Không thể đọc processed_files.log: {e}")
            
            # 2. Đọc từ logs/*.json (format mới)
            logs_dir = Path(folder) / "Subtitles" / "logs"
            if logs_dir.exists():
                for json_file in logs_dir.glob("*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            entries = json.load(f)
                            if isinstance(entries, list):
                                for entry in entries:
                                    old_name = entry.get("old_name", "")
                                    new_name = entry.get("new_name", "")
                                    timestamp = entry.get("timestamp", "")
                                    if old_name:
                                        processed_old_names.add(old_name)
                                        processed_info[old_name] = {"new": new_name, "time": timestamp}
                                    if new_name:
                                        processed_new_names.add(new_name)
                                        processed_info[new_name] = {"new": new_name, "time": timestamp}
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"[WARNING] Không thể đọc {json_file}: {e}")

            # Đọc danh sách file video từ thư mục
            try:
                all_files = os.listdir(folder)
                log_msg = f"[INFO] Tìm thấy {len(all_files)} file trong thư mục: {folder}"
                print(log_msg)
                if self.log_view:
                    self.log_view.appendPlainText(log_msg)
                
                video_files = sorted(
                    f for f in all_files 
                    if any(f.lower().endswith(ext) for ext in self.SUPPORTED_VIDEO_EXTENSIONS)
                )
                log_msg = f"[INFO] Tìm thấy {len(video_files)} file video (hỗ trợ: {', '.join(self.SUPPORTED_VIDEO_EXTENSIONS)})"
                print(log_msg)
                if self.log_view:
                    self.log_view.appendPlainText(log_msg)
            except PermissionError as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Lỗi quyền truy cập", 
                    f"Không có quyền đọc thư mục:\n{folder}\n\nLỗi: {e}"
                )
                return
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Lỗi đọc thư mục", 
                    f"Không thể đọc thư mục:\n{folder}\n\nLỗi: {e}"
                )
                return

            # Phân loại: đã xử lý (có tiền tố HOẶC có trong log) vs chưa xử lý
            processed_files = []
            pending_files = []
            for video_file in video_files:
                # Check: có tiền tố resolution HOẶC có trong log (cả old_name và new_name)
                has_prefix = self.is_already_processed_by_name(video_file)
                in_log = video_file in processed_old_names or video_file in processed_new_names
                
                if has_prefix or in_log:
                    processed_files.append(video_file)
                else:
                    pending_files.append(video_file)

            self.file_tree.blockSignals(True)
            self.file_tree.clear()
            
            # Hiển thị file chưa xử lý trước (màu vàng)
            # Tối ưu: Không đọc metadata ngay, chỉ hiển thị file list nhanh
            # Metadata sẽ được đọc lazy khi user expand item
            for video_file in pending_files:
                file_path = os.path.abspath(os.path.join(folder, video_file))
                if not os.path.exists(file_path):
                    print(f"[WARNING] File không tồn tại: {file_path}")
                    continue
                    
                options = self.file_options.setdefault(file_path, FileOptions(file_path))

                # Chỉ đọc metadata nếu đã có cache (từ lần trước), không đọc mới
                # Metadata sẽ được đọc khi user expand item (lazy load)
                if not options.metadata_ready:
                    # Set default values để hiển thị ngay
                    options.cached_subs = []
                    options.cached_audios = []
                    options.cached_resolution = "?"
                    options.cached_year = ""

                try:
                    size = self.format_file_size(os.path.getsize(file_path))
                except Exception as e:
                    print(f"[WARNING] Không thể đọc kích thước file {video_file}: {e}")
                    size = "?"
                
                item = QtWidgets.QTreeWidgetItem(self.file_tree)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.Checked if options.process_enabled else QtCore.Qt.Unchecked)
                
                item.setText(0, f"{video_file} ({size})")
                # Hiển thị summary đơn giản nếu chưa có metadata
                if options.metadata_ready:
                    item.setText(1, self.get_file_config_summary(options))
                else:
                    item.setText(1, "Chưa load metadata...")
                item.setData(0, QtCore.Qt.UserRole, file_path)
                
                # Màu vàng cho file chưa xử lý
                fg = QtGui.QColor("#facc15")
                bg = QtGui.QColor("#2f1b09")
                for col in range(2):
                    # Sử dụng setData trước để đảm bảo màu được áp dụng
                    item.setData(col, QtCore.Qt.ForegroundRole, fg)
                    item.setData(col, QtCore.Qt.BackgroundRole, bg)
                    item.setForeground(col, fg)
                    item.setBackground(col, bg)
                
                # Placeholder for expand
                ph = QtWidgets.QTreeWidgetItem(item)
                ph.setData(0, QtCore.Qt.UserRole, "placeholder")
                ph.setText(0, "Loading...")

            # Hiển thị file đã xử lý sau (màu xanh)
            # Tối ưu: Không đọc metadata ngay, chỉ hiển thị file list nhanh
            for video_file in processed_files:
                file_path = os.path.abspath(os.path.join(folder, video_file))
                if not os.path.exists(file_path):
                    print(f"[WARNING] File không tồn tại: {file_path}")
                    continue
                    
                options = self.file_options.setdefault(file_path, FileOptions(file_path))

                # Chỉ đọc metadata nếu đã có cache (từ lần trước), không đọc mới
                # Metadata sẽ được đọc khi user expand item (lazy load)
                if not options.metadata_ready:
                    # Set default values để hiển thị ngay
                    options.cached_subs = []
                    options.cached_audios = []
                    options.cached_resolution = "?"
                    options.cached_year = ""

                try:
                    size = self.format_file_size(os.path.getsize(file_path))
                except Exception as e:
                    print(f"[WARNING] Không thể đọc kích thước file {video_file}: {e}")
                    size = "?"
                
                item = QtWidgets.QTreeWidgetItem(self.file_tree)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                # File đã xử lý mặc định bỏ chọn
                options.process_enabled = False
                item.setCheckState(0, QtCore.Qt.Unchecked)
                
                item.setText(0, f"✓ {video_file} ({size})")
                # Hiển thị summary đơn giản nếu chưa có metadata
                if options.metadata_ready:
                    item.setText(1, self.get_file_config_summary(options))
                else:
                    item.setText(1, "Đã xử lý")
                item.setData(0, QtCore.Qt.UserRole, file_path)
                
                # Màu xanh cho file đã xử lý
                fg = QtGui.QColor("#bbf7d0")
                bg = QtGui.QColor("#0f2f1a")
                for col in range(2):
                    # Sử dụng setData trước để đảm bảo màu được áp dụng
                    item.setData(col, QtCore.Qt.ForegroundRole, fg)
                    item.setData(col, QtCore.Qt.BackgroundRole, bg)
                    item.setForeground(col, fg)
                    item.setBackground(col, bg)
                
                # Placeholder for expand
                ph = QtWidgets.QTreeWidgetItem(item)
                ph.setData(0, QtCore.Qt.UserRole, "placeholder")
                ph.setText(0, "Loading...")

            self.file_count_label.setText(f"{len(processed_files)}/{len(video_files)}")
            
            # Start background metadata loader sau khi hiển thị file list
            # Lấy danh sách file paths cần load metadata
            files_to_load_metadata = []
            for i in range(self.file_tree.topLevelItemCount()):
                item = self.file_tree.topLevelItem(i)
                if item is None:
                    continue
                path = item.data(0, QtCore.Qt.UserRole)
                if path and isinstance(path, str) and path not in ("placeholder", "options"):
                    options = self.file_options.get(path)
                    if options and not options.metadata_ready:
                        files_to_load_metadata.append(path)
            
            # Start background loader nếu có file cần load
            if files_to_load_metadata:
                self._start_metadata_loader(files_to_load_metadata)

        except Exception as e:
            import traceback
            error_msg = f"Lỗi khi đọc danh sách file:\n\n{str(e)}\n\n"
            error_msg += f"Chi tiết:\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            QtWidgets.QMessageBox.warning(self, "Lỗi", error_msg)
        finally:
            self.file_tree.blockSignals(False)
            self.update_select_all_state()
            # Re-enable nút và khôi phục icon
            if hasattr(self, 'reload_btn'):
                self.reload_btn.setEnabled(True)
                self.reload_btn.setText("🔄")
                self.reload_btn.setToolTip("Làm mới")
    
    def _start_metadata_loader(self, file_paths: list[str]):
        """Start background thread để load metadata cho các file."""
        # Stop loader cũ nếu đang chạy
        if self.metadata_loader_thread and self.metadata_loader_thread.isRunning():
            self.metadata_loader_thread.requestInterruption()
            self.metadata_loader_thread.wait(1000)  # Đợi tối đa 1 giây
        
        # Tạo loader mới
        self.metadata_loader_thread = MetadataLoader(file_paths)
        self.metadata_loader_thread.metadata_loaded_signal.connect(self._on_metadata_loaded)
        self.metadata_loader_thread.start()
    
    def _on_metadata_loaded(self, file_path: str, success: bool):
        """Callback khi metadata đã được load xong trong background."""
        if not file_path or file_path not in self.file_options:
            return
        
        options = self.file_options[file_path]
        
        # Nếu chưa có metadata, load lại để cập nhật vào options
        if not options.metadata_ready:
            try:
                self.ensure_options_metadata(file_path, options)
            except Exception as e:
                print(f"[WARNING] Không thể cập nhật metadata cho {os.path.basename(file_path)}: {e}")
                return
        
        # Tìm item trong tree và cập nhật summary
        normalized_filepath = os.path.normpath(os.path.abspath(file_path))
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            if item is None:
                continue
            path = item.data(0, QtCore.Qt.UserRole)
            if not path or not isinstance(path, str):
                continue
            
            item_normalized = os.path.normpath(os.path.abspath(path))
            if item_normalized == normalized_filepath:
                # Cập nhật summary khi metadata đã ready
                if options.metadata_ready:
                    item.setText(1, self.get_file_config_summary(options))
                break

    def on_file_item_clicked(self, item, column):
        """Single click - mở config khi click vào column 1 (Cấu hình)"""
        path = item.data(0, QtCore.Qt.UserRole)
        if path and isinstance(path, str) and path not in ("placeholder", "options"):
            # Click vào column 1 (Cấu hình) → mở config
            # Click vào column 0 (checkbox) → chỉ toggle checkbox (qua itemChanged)
            if column == 1:
                # Đóng tất cả các item khác trước khi mở item này
                for i in range(self.file_tree.topLevelItemCount()):
                    other_item = self.file_tree.topLevelItem(i)
                    if other_item is not None and other_item != item and other_item.isExpanded():
                        other_item.setExpanded(False)
                
                # Toggle expand (mở/đóng config)
                item.setExpanded(not item.isExpanded())

    def on_file_double_clicked(self, item, column):
        """Double click - mở/đóng config (bất kỳ column nào)"""
        path = item.data(0, QtCore.Qt.UserRole)
        if path and isinstance(path, str) and path not in ("placeholder", "options"):
            # Đóng tất cả các item khác trước khi mở item này
            for i in range(self.file_tree.topLevelItemCount()):
                other_item = self.file_tree.topLevelItem(i)
                if other_item is not None and other_item != item and other_item.isExpanded():
                    other_item.setExpanded(False)
            
            # Toggle expand (mở/đóng config)
            item.setExpanded(not item.isExpanded())

    def on_file_expanded(self, item):
        file_path = item.data(0, QtCore.Qt.UserRole)
        if not file_path or not isinstance(file_path, str) or not os.path.exists(file_path):
            return

        # Clear placeholder
        while item.childCount() > 0:
            child = item.child(0)
            if child and child.data(0, QtCore.Qt.UserRole) in ("placeholder", "loading"):
                item.removeChild(child)
            else:
                break

        options = self.file_options.setdefault(file_path, FileOptions(file_path))

        # Lazy load metadata - chỉ đọc khi user expand item
        # Đây là tối ưu quan trọng: không đọc metadata cho tất cả file ngay
        try:
            if not options.metadata_ready:
                # Hiển thị "Loading..." trong khi đọc metadata
                loading_item = QtWidgets.QTreeWidgetItem(item)
                loading_item.setData(0, QtCore.Qt.UserRole, "loading")
                loading_item.setText(0, "⏳ Đang đọc metadata...")
                self.file_tree.viewport().update()
                QtWidgets.QApplication.processEvents()  # Force update UI để hiển thị loading
            
            if not self.ensure_options_metadata(file_path, options):
                raise RuntimeError("Cannot read metadata")
            
            # Xóa loading item nếu có
            for i in range(item.childCount()):
                child = item.child(i)
                if child and child.data(0, QtCore.Qt.UserRole) == "loading":
                    item.removeChild(child)
                    break

            subs = options.cached_subs
            audios = options.cached_audios
            
            # Cập nhật summary trong tree sau khi có metadata
            item.setText(1, self.get_file_config_summary(options))

            widget = self.create_options_widget(file_path, subs, audios, options, item)
            child = QtWidgets.QTreeWidgetItem(item)
            child.setData(0, QtCore.Qt.UserRole, "options")
            child.setFirstColumnSpanned(True)
            self.file_tree.setItemWidget(child, 0, widget)
            
            # Force resize để widget hiển thị đầy đủ
            widget.adjustSize()
            child.setSizeHint(0, widget.sizeHint())

        except Exception as e:
            err = QtWidgets.QTreeWidgetItem(item)
            err.setText(0, f"❌ {e}")
            err.setForeground(0, QtGui.QColor("#f87171"))

    def on_file_collapsed(self, item):
        while item.childCount() > 0:
            item.removeChild(item.child(0))
        ph = QtWidgets.QTreeWidgetItem(item)
        ph.setData(0, QtCore.Qt.UserRole, "placeholder")
        ph.setText(0, "Loading...")

    def on_file_item_changed(self, item, column):
        path = item.data(0, QtCore.Qt.UserRole)
        if path and isinstance(path, str) and path not in ("placeholder", "options"):
            if path in self.file_options:
                self.file_options[path].process_enabled = item.checkState(0) == QtCore.Qt.Checked
            self.update_select_all_state()

    def create_options_widget(self, file_path: str, subs: list, audios: list, 
                              options: FileOptions, parent_item: QtWidgets.QTreeWidgetItem):
        """Tạo widget options với 2 danh sách SRT riêng biệt"""
        widget = QtWidgets.QWidget()
        widget.setObjectName("optionsWidget")
        widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)

        # Row 1: Basic toggles
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(16)
        
        force_cb = QtWidgets.QCheckBox("⚡ Ép xử lý lại")
        force_cb.setChecked(options.force_process)
        
        # Hàm kiểm tra xem có option nào được chọn không
        def has_any_option_selected():
            has_export = len(options.export_subtitle_indices) > 0
            has_mux_audio = options.mux_audio and len(options.selected_audio_indices) > 0
            has_mux_sub = len(options.mux_subtitle_indices) > 0
            has_rename = options.rename_enabled
            return has_export or has_mux_audio or has_mux_sub or has_rename
        
        # Hàm cập nhật trạng thái force_cb
        def update_force_process_state():
            has_option = has_any_option_selected()
            force_cb.setEnabled(has_option)
            if not has_option and options.force_process:
                # Tự động uncheck nếu không có option nào
                force_cb.setChecked(False)
                options.force_process = False
        
        # Kiểm tra ban đầu
        update_force_process_state()
        
        force_cb.toggled.connect(lambda c: setattr(options, "force_process", c))
        row1.addWidget(force_cb)

        rename_cb = QtWidgets.QCheckBox("✏️ Đổi tên")
        rename_cb.setChecked(options.rename_enabled)
        rename_cb.toggled.connect(lambda c: (setattr(options, "rename_enabled", c), 
                                              self.update_item_summary(file_path, parent_item),
                                              update_force_process_state()))
        row1.addWidget(rename_cb)
        row1.addStretch()
        layout.addLayout(row1)

        # === SUBTITLE SECTIONS (2 cột) ===
        sub_row = QtWidgets.QHBoxLayout()
        sub_row.setSpacing(16)

        # Column 1: Xuất SRT
        export_group = QtWidgets.QGroupBox()
        export_group.setObjectName("optionsGroup")
        export_layout = QtWidgets.QVBoxLayout(export_group)
        export_layout.setSpacing(4)
        
        # Header: Label và All/None cùng hàng
        export_header = QtWidgets.QHBoxLayout()
        export_label = QtWidgets.QLabel("📤 Xuất file SRT")
        export_label.setObjectName("sectionLabel")
        export_header.addWidget(export_label)
        export_header.addStretch()
        export_all_btn = QtWidgets.QPushButton("All")
        export_all_btn.setObjectName("miniButton")
        export_none_btn = QtWidgets.QPushButton("None")
        export_none_btn.setObjectName("miniButton")
        export_header.addWidget(export_all_btn)
        export_header.addWidget(export_none_btn)
        export_layout.addLayout(export_header)

        # Tạo scroll area cho export list để tránh scroll giật khi có nhiều subtitle
        export_scroll = QtWidgets.QScrollArea()
        export_scroll.setWidgetResizable(True)
        export_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        export_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        export_scroll.setMaximumHeight(300)  # Giới hạn chiều cao tối đa
        export_scroll.setMinimumHeight(80)
        export_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        export_list = QtWidgets.QWidget()
        export_list.setStyleSheet("background: #0d1117;")
        export_list_layout = QtWidgets.QVBoxLayout(export_list)
        export_list_layout.setSpacing(2)
        export_list_layout.setContentsMargins(0, 0, 0, 0)
        export_cbs = []
        
        for idx, lang, title, codec in subs:
            cb = QtWidgets.QCheckBox(f"{lang}" + (f" ({title})" if title else "") + f" [{codec}]")
            # Tự động chọn mặc định (Vietnamese hoặc đầu tiên)
            is_default = idx in options.export_subtitle_indices
            cb.setChecked(is_default)
            cb.setProperty("track_index", idx)
            cb.toggled.connect(lambda c, i=idx: (self.toggle_export_sub(options, i, c, file_path, parent_item),
                                                  update_force_process_state()))
            export_list_layout.addWidget(cb)
            export_cbs.append(cb)
        
        export_list_layout.addStretch()  # Thêm stretch để các checkbox không bị kéo dãn
        export_scroll.setWidget(export_list)
        export_layout.addWidget(export_scroll)
        
        def select_all_export():
            for cb in export_cbs:
                cb.setChecked(True)
            update_force_process_state()
        
        def select_none_export():
            for cb in export_cbs:
                cb.setChecked(False)
            update_force_process_state()
        
        export_all_btn.clicked.connect(select_all_export)
        export_none_btn.clicked.connect(select_none_export)
        
        sub_row.addWidget(export_group, 1)
        layout.addLayout(sub_row)

        # === MUX SECTION (Audio + SRT gộp chung) ===
        mux_container = QtWidgets.QWidget()
        mux_container.setObjectName("optionsGroup")
        mux_layout = QtWidgets.QVBoxLayout(mux_container)
        mux_layout.setSpacing(4)
        mux_layout.setContentsMargins(12, 8, 12, 12)
        
        # Checkbox làm title
        mux_audio_cb = QtWidgets.QCheckBox("📦 Mux (tạo video output)")
        mux_audio_cb.setChecked(options.mux_audio)
        mux_audio_cb.setObjectName("groupTitleCheckbox")
        mux_layout.addWidget(mux_audio_cb)
        
        # 2 cột: Audio và SRT
        mux_columns = QtWidgets.QHBoxLayout()
        mux_columns.setSpacing(16)
        
        # === CỘT 1: AUDIO ===
        audio_col = QtWidgets.QWidget()
        audio_col_layout = QtWidgets.QVBoxLayout(audio_col)
        audio_col_layout.setContentsMargins(0, 0, 0, 0)
        audio_col_layout.setSpacing(4)
        
        # Audio label và All/None cùng hàng
        audio_header = QtWidgets.QHBoxLayout()
        audio_label = QtWidgets.QLabel("🎧 Audio (kéo thả đổi thứ tự):")
        audio_label.setObjectName("sectionLabel")
        audio_header.addWidget(audio_label)
        audio_header.addStretch()
        audio_all_btn = QtWidgets.QPushButton("All")
        audio_all_btn.setObjectName("miniButton")
        audio_none_btn = QtWidgets.QPushButton("None")
        audio_none_btn.setObjectName("miniButton")
        audio_header.addWidget(audio_all_btn)
        audio_header.addWidget(audio_none_btn)
        audio_col_layout.addLayout(audio_header)

        audio_list = DraggableListWidget()
        audio_list.setObjectName("audioList")
        # Giới hạn chiều cao để tránh scroll giật, sử dụng scrollbar tự động khi cần
        audio_list.setMaximumHeight(300)
        audio_list.setMinimumHeight(80)

        # Order: selected first, then others
        ordered = []
        for idx in options.selected_audio_indices:
            for a in audios:
                if a[0] == idx:
                    ordered.append(a)
                    break
        for a in audios:
            if a[0] not in options.selected_audio_indices:
                ordered.append(a)

        for idx, ch, lang, title, br, _ in ordered:
            kbps = f"{br // 1000}k" if br else "?"
            text = f"[{idx}] {lang.upper()} · {ch}ch · {kbps}" + (f" · {title}" if title else "")
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, idx)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if idx in options.selected_audio_indices else QtCore.Qt.Unchecked)
            audio_list.addItem(item)

        audio_list.setEnabled(options.mux_audio)
        audio_col_layout.addWidget(audio_list)
        
        # === CỘT 2: SRT ===
        srt_col = QtWidgets.QWidget()
        srt_col_layout = QtWidgets.QVBoxLayout(srt_col)
        srt_col_layout.setContentsMargins(0, 0, 0, 0)
        srt_col_layout.setSpacing(4)
        
        # SRT label và All/None cùng hàng (bỏ checkbox riêng)
        srt_mux_header = QtWidgets.QHBoxLayout()
        srt_label = QtWidgets.QLabel("📝 SRT (mux vào video):")
        srt_label.setObjectName("sectionLabel")
        srt_mux_header.addWidget(srt_label)
        srt_mux_header.addStretch()
        srt_mux_all_btn = QtWidgets.QPushButton("All")
        srt_mux_all_btn.setObjectName("miniButton")
        srt_mux_none_btn = QtWidgets.QPushButton("None")
        srt_mux_none_btn.setObjectName("miniButton")
        srt_mux_header.addWidget(srt_mux_all_btn)
        srt_mux_header.addWidget(srt_mux_none_btn)
        srt_col_layout.addLayout(srt_mux_header)

        # Tạo scroll area cho srt mux list để tránh scroll giật khi có nhiều subtitle
        srt_mux_scroll = QtWidgets.QScrollArea()
        srt_mux_scroll.setWidgetResizable(True)
        srt_mux_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        srt_mux_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        srt_mux_scroll.setMaximumHeight(300)  # Giới hạn chiều cao tối đa
        srt_mux_scroll.setMinimumHeight(80)
        srt_mux_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        srt_mux_list = QtWidgets.QWidget()
        srt_mux_list.setStyleSheet("background: #0d1117;")
        srt_mux_list_layout = QtWidgets.QVBoxLayout(srt_mux_list)
        srt_mux_list_layout.setSpacing(2)
        srt_mux_list_layout.setContentsMargins(0, 0, 0, 0)
        srt_mux_cbs = []
        
        for idx, lang, title, codec in subs:
            cb = QtWidgets.QCheckBox(f"{lang}" + (f" ({title})" if title else "") + f" [{codec}]")
            # Tự động chọn mặc định (Vietnamese hoặc đầu tiên)
            is_default = idx in options.mux_subtitle_indices
            cb.setChecked(is_default)
            cb.setProperty("track_index", idx)
            cb.toggled.connect(lambda c, i=idx: (self.toggle_mux_sub(options, i, c, file_path, parent_item),
                                                 update_force_process_state()))
            srt_mux_list_layout.addWidget(cb)
            srt_mux_cbs.append(cb)
        
        srt_mux_list_layout.addStretch()  # Thêm stretch để các checkbox không bị kéo dãn
        srt_mux_scroll.setWidget(srt_mux_list)
        srt_col_layout.addWidget(srt_mux_scroll)
        
        # Enable/disable dựa trên mux_audio (không cần check mux_subtitles vì đã bỏ checkbox riêng)
        srt_mux_scroll.setEnabled(options.mux_audio)
        
        # Thêm 2 cột vào layout
        mux_columns.addWidget(audio_col, 1)
        mux_columns.addWidget(srt_col, 1)
        mux_layout.addLayout(mux_columns)

        def on_mux_audio_toggle(c):
            options.mux_audio = c
            audio_list.setEnabled(c)
            srt_mux_scroll.setEnabled(c)
            # Nếu tắt mux, bỏ chọn tất cả audio và SRT
            if not c:
                for i in range(audio_list.count()):
                    audio_list.item(i).setCheckState(QtCore.Qt.Unchecked)
                for cb in srt_mux_cbs:
                    cb.setChecked(False)
            self.update_item_summary(file_path, parent_item)
            update_force_process_state()

        def on_audio_changed(item):
            self.sync_audio_from_list(options, audio_list)
            # Kiểm tra: nếu không có audio nào được chọn -> tự động tắt mux
            selected_count = sum(1 for i in range(audio_list.count()) 
                               if audio_list.item(i).checkState() == QtCore.Qt.Checked)
            if selected_count == 0 and options.mux_audio:
                # Tự động tắt mux
                mux_audio_cb.setChecked(False)
                options.mux_audio = False
                audio_list.setEnabled(False)
                srt_mux_scroll.setEnabled(False)
            elif selected_count > 0 and not options.mux_audio:
                # Tự động bật mux nếu có audio được chọn
                mux_audio_cb.setChecked(True)
                options.mux_audio = True
                audio_list.setEnabled(True)
                srt_mux_scroll.setEnabled(True)
            self.update_item_summary(file_path, parent_item)
            update_force_process_state()

        def on_audio_reorder():
            self.sync_audio_from_list(options, audio_list)
            self.update_item_summary(file_path, parent_item)

        def select_all_audio():
            for i in range(audio_list.count()):
                audio_list.item(i).setCheckState(QtCore.Qt.Checked)
            update_force_process_state()

        def select_none_audio():
            for i in range(audio_list.count()):
                audio_list.item(i).setCheckState(QtCore.Qt.Unchecked)
            update_force_process_state()
        
        def select_all_srt_mux():
            for cb in srt_mux_cbs:
                cb.setChecked(True)
            update_force_process_state()
        
        def select_none_srt_mux():
            for cb in srt_mux_cbs:
                cb.setChecked(False)
            update_force_process_state()

        mux_audio_cb.toggled.connect(on_mux_audio_toggle)
        audio_list.itemChanged.connect(on_audio_changed)
        audio_list.orderChanged.connect(on_audio_reorder)
        audio_all_btn.clicked.connect(select_all_audio)
        audio_none_btn.clicked.connect(select_none_audio)
        srt_mux_all_btn.clicked.connect(select_all_srt_mux)
        srt_mux_none_btn.clicked.connect(select_none_srt_mux)
        
        hint = QtWidgets.QLabel("💡 Track đầu tiên = mặc định")
        hint.setObjectName("hintLabel")
        mux_layout.addWidget(hint)
        
        layout.addWidget(mux_container)

        return widget

    def toggle_export_sub(self, options: FileOptions, idx: int, checked: bool, file_path: str, parent_item):
        if checked:
            if idx not in options.export_subtitle_indices:
                options.export_subtitle_indices.append(idx)
        else:
            if idx in options.export_subtitle_indices:
                options.export_subtitle_indices.remove(idx)
        # Tự động cập nhật export_subtitles dựa trên có checkbox nào được chọn
        options.export_subtitles = len(options.export_subtitle_indices) > 0
        self.update_item_summary(file_path, parent_item)

    def toggle_mux_sub(self, options: FileOptions, idx: int, checked: bool, file_path: str, parent_item):
        if checked:
            if idx not in options.mux_subtitle_indices:
                options.mux_subtitle_indices.append(idx)
        else:
            if idx in options.mux_subtitle_indices:
                options.mux_subtitle_indices.remove(idx)
        # Tự động cập nhật mux_subtitles dựa trên có checkbox nào được chọn
        options.mux_subtitles = len(options.mux_subtitle_indices) > 0
        self.update_item_summary(file_path, parent_item)

    def sync_audio_from_list(self, options: FileOptions, audio_list: QtWidgets.QListWidget):
        selected = []
        for i in range(audio_list.count()):
            item = audio_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selected.append(item.data(QtCore.Qt.UserRole))
        options.selected_audio_indices = selected

    def update_item_summary(self, file_path: str, parent_item: QtWidgets.QTreeWidgetItem):
        if file_path in self.file_options:
            parent_item.setText(1, self.get_file_config_summary(self.file_options[file_path]))

    def pick_default_audio(self, audios: list) -> list[int]:
        if not audios:
            return []
        
        ordered = sorted(audios, key=lambda x: x[5])
        first_lang = ordered[0][2]
        
        def quality(a):
            return a[1], a[4]
        
        vie = sorted([a for a in audios if a[2] == "vie"], key=quality, reverse=True)
        others = sorted([a for a in audios if a[2] != "vie"], key=quality, reverse=True)
        
        if first_lang == "eng" and vie:
            return [vie[0][0]]
        if first_lang == "vie":
            picks = [vie[0][0]] if vie else []
            if others:
                picks.append(others[0][0])
            return picks
        if vie:
            return [vie[0][0]]
        if others:
            return [others[0][0]]
        return [ordered[0][0]]

    def start_processing(self):
        # Đảm bảo script module đã được load
        try:
            self._get_script_module()
        except ImportError as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Không thể import processing module:\n{e}")
            return
        
        folder = self.folder_edit.text().strip()
        if not folder:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select a folder first.")
            return
        if self.worker and self.worker.isRunning():
            return

        selected = []
        options_data = {}
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            if item is None:
                continue
            path = item.data(0, QtCore.Qt.UserRole)
            if item.checkState(0) == QtCore.Qt.Checked and path and os.path.exists(path):
                selected.append(path)
                if path in self.file_options:
                    # Lấy options hiện tại (có thể chưa có metadata, backend sẽ tự đọc khi cần)
                    options_data[path] = self.file_options[path].to_dict()

        if not selected:
            self.show_info_message("Info", "Chọn ít nhất 1 file.")
            return

        if self.log_view:
            self.log_view.clear()

        # Setup log directory
        logs_dir = Path(folder) / "Subtitles" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_log_file = logs_dir / "session.log"
        self.session_log_file.write_text("", encoding="utf-8")

        # Pass options to backend via environment
        os.environ["MKV_FILE_OPTIONS"] = json.dumps(options_data)

        self.worker = Worker(folder, selected)
        self.worker.log_signal.connect(self.log_message)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.file_status_signal.connect(self.update_file_status)
        self.worker.finished_signal.connect(self.finish_processing)
        self.worker.start()
        
        # Lưu mapping filepath (normalized) -> filepath để cập nhật UI
        # Dùng filepath thay vì filename để tránh collision khi có file cùng tên ở folder khác
        self.processing_files_map.clear()  # Clear trước khi thêm mới
        for filepath in selected:
            try:
                normalized = os.path.normpath(os.path.abspath(filepath))
                self.processing_files_map[normalized] = filepath
            except Exception as e:
                print(f"[ERROR] Không thể normalize path {filepath}: {e}")
        
        # Setup progress bar với range thực tế
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress.setFormat("%v/%m")
        self.progress.setVisible(True)
        self.start_btn.setVisible(False)  # Ẩn nút Bắt đầu
        self.stop_btn.setVisible(True)    # Hiện nút Dừng
        self.status_bar.showMessage(f"Processing 0/{len(selected)} files…")

    def stop_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.terminate()
        self.progress.setVisible(False)
        self.start_btn.setVisible(True)   # Hiện nút Bắt đầu
        self.stop_btn.setVisible(False)  # Ẩn nút Dừng
        self.status_bar.showMessage("Đã dừng", 3000)

    def update_progress(self, current: int, total: int, filename: str):
        """Cập nhật thanh tiến độ và UI của file đang xử lý"""
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        # Rút gọn tên file nếu quá dài
        short_name = filename if len(filename) <= 40 else filename[:37] + "..."
        self.status_bar.showMessage(f"[{current}/{total}] {short_name}")
        
        # Tìm filepath từ filename (có thể có nhiều file cùng tên, lấy file đầu tiên match)
        # Ưu tiên file đang trong processing_files_map
        matched_filepath = None
        for normalized_path, original_path in self.processing_files_map.items():
            try:
                if os.path.basename(original_path) == filename:
                    matched_filepath = original_path
                    break
            except Exception as e:
                print(f"[ERROR] Lỗi khi so sánh filename {original_path}: {e}")
                continue
        
        # Nếu không tìm thấy, thử tìm trong tree
        if not matched_filepath:
            folder = self.folder_edit.text().strip()
            if folder:
                try:
                    potential_path = os.path.normpath(os.path.abspath(os.path.join(folder, filename)))
                    if potential_path in self.processing_files_map:
                        matched_filepath = self.processing_files_map[potential_path]
                except Exception as e:
                    print(f"[ERROR] Lỗi khi tìm file {filename} trong folder {folder}: {e}")
        
        if matched_filepath:
            self.update_file_status(matched_filepath, "started")
        else:
            print(f"[WARNING] Không tìm thấy filepath cho filename: {filename}")

    def finish_processing(self, success: bool):
        self.progress.setVisible(False)
        self.start_btn.setVisible(True)   # Hiện nút Bắt đầu
        self.stop_btn.setVisible(False)  # Ẩn nút Dừng
        os.environ.pop("MKV_FILE_OPTIONS", None)
        
        # Đánh dấu tất cả file còn lại trong processing_files_map là completed (nếu success)
        # File đã được đánh dấu completed trong quá trình xử lý sẽ không bị override
        if success:
            for filepath in self.processing_files_map.values():
                # Chỉ đánh dấu nếu file chưa được đánh dấu (tránh override failed status)
                normalized = os.path.normpath(os.path.abspath(filepath))
                # Kiểm tra xem file có đang ở trạng thái failed không
                for i in range(self.file_tree.topLevelItemCount()):
                    item = self.file_tree.topLevelItem(i)
                    if item is None:
                        continue
                    path = item.data(0, QtCore.Qt.UserRole)
                    if path and isinstance(path, str):
                        item_normalized = os.path.normpath(os.path.abspath(path))
                        if item_normalized == normalized:
                            # Nếu file không có icon ❌, đánh dấu completed
                            text = item.text(0)
                            if not text.startswith("❌"):
                                self.update_file_status(filepath, "completed")
                            break
        
        self.processing_files_map.clear()
        # Refresh để cập nhật danh sách (file đã xử lý sẽ chuyển sang màu xanh)
        QtCore.QTimer.singleShot(500, self.refresh_file_list)  # Delay một chút để đảm bảo file đã được ghi log
        self.status_bar.showMessage("Completed" if success else "Error - see log", 5000)
    
    def update_file_status(self, filepath: str, status: str):
        """Cập nhật trạng thái hiển thị của file trong tree"""
        if not filepath:
            return
        
        # Normalize filepath để so sánh chính xác
        try:
            normalized_filepath = os.path.normpath(os.path.abspath(filepath))
        except Exception as e:
            print(f"[ERROR] Không thể normalize path {filepath}: {e}")
            return
        
        # Nếu file không tồn tại và status là completed, vẫn cho phép (file có thể đã được rename)
        if status != "completed" and not os.path.exists(filepath):
            print(f"[WARNING] File không tồn tại: {filepath}")
            return
        
        # Tìm item trong tree theo filepath (so sánh normalized paths)
        found_item = None
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            if item is None:
                continue
            path = item.data(0, QtCore.Qt.UserRole)
            if not path or not isinstance(path, str):
                continue
            
            # Normalize path từ tree để so sánh
            try:
                normalized_path = os.path.normpath(os.path.abspath(path))
            except Exception as e:
                print(f"[ERROR] Không thể normalize path từ tree {path}: {e}")
                continue
                
            # So sánh cả normalized path và filename để tìm chính xác
            if normalized_path == normalized_filepath or path == filepath:
                found_item = item
                break
        
        # Nếu không tìm thấy bằng path, thử tìm bằng filename
        if found_item is None:
            filename = os.path.basename(filepath)
            for i in range(self.file_tree.topLevelItemCount()):
                item = self.file_tree.topLevelItem(i)
                if item is None:
                    continue
                item_text = item.text(0)
                # Loại bỏ icon và size để so sánh filename
                item_filename = item_text.lstrip("✓❌⏳").strip()
                if " (" in item_filename:
                    item_filename = item_filename.split(" (")[0]
                if item_filename == filename or item_filename.endswith(filename):
                    found_item = item
                    break
        
        if found_item is None:
            print(f"[WARNING] Không tìm thấy file trong tree: {filepath}")
            return
        
        item = found_item
        path = item.data(0, QtCore.Qt.UserRole)
        
        if status == "started":
            # Màu cam cho file đang xử lý
            fg = QtGui.QColor("#fb923c")  # Cam
            bg = QtGui.QColor("#431407")  # Nền cam đậm
            # Thêm icon ⏳ vào đầu tên file
            text = item.text(0)
            if not text.startswith("⏳"):
                # Loại bỏ các icon cũ
                text = text.lstrip("✓❌⏳").strip()
                item.setText(0, f"⏳ {text}")
        elif status == "completed":
            # Màu xanh cho file đã xử lý
            fg = QtGui.QColor("#bbf7d0")  # Xanh lá
            bg = QtGui.QColor("#0f2f1a")  # Nền xanh đậm
            # Thêm icon ✓ vào đầu tên file
            text = item.text(0)
            # Loại bỏ các icon cũ
            text = text.lstrip("✓❌⏳").strip()
            if not text.startswith("✓"):
                item.setText(0, f"✓ {text}")
            # Bỏ chọn file đã xử lý
            item.setCheckState(0, QtCore.Qt.Unchecked)
            if path and isinstance(path, str) and path in self.file_options:
                self.file_options[path].process_enabled = False
        elif status == "failed":
            # Màu đỏ cho file xử lý lỗi
            fg = QtGui.QColor("#f87171")  # Đỏ
            bg = QtGui.QColor("#431407")  # Nền đỏ đậm
            # Thêm icon ❌ vào đầu tên file
            text = item.text(0)
            # Loại bỏ các icon cũ
            text = text.lstrip("✓❌⏳").strip()
            if not text.startswith("❌"):
                item.setText(0, f"❌ {text}")
        
        # Áp dụng màu sắc - đảm bảo override theme
        # Sử dụng setData trước để đảm bảo màu được áp dụng
        for col in range(2):
            item.setData(col, QtCore.Qt.ForegroundRole, fg)
            item.setData(col, QtCore.Qt.BackgroundRole, bg)
            item.setForeground(col, fg)
            item.setBackground(col, bg)
        
        # Bỏ selection của item này để màu riêng được hiển thị (tránh bị override bởi selected style)
        # Chỉ clear selection nếu item này đang được selected
        current_item = self.file_tree.currentItem()
        if current_item == item:
            self.file_tree.clearSelection()
        
        # Force update UI - cần repaint để màu hiển thị
        item.setData(0, QtCore.Qt.UserRole, path)  # Giữ lại path
        self.file_tree.viewport().update()
        self.file_tree.repaint()
        QtWidgets.QApplication.processEvents()

    def log_message(self, text: str, level: str = "INFO"):
        if self.session_log_file:
            try:
                with self.session_log_file.open("a", encoding="utf-8") as f:
                    f.write(f"[{level}] {text}\n")
            except Exception as e:
                # Log nhưng không crash nếu không thể ghi log
                print(f"[WARNING] Không thể ghi log: {e}")
        
        # Phân loại log
        is_srt_log = text.endswith('.srt') or '.srt (' in text or '_vie)' in text or '_und)' in text
        is_error = level == "ERROR"
        is_progress = text.startswith("Processing file") or "ĐANG XỬ LÝ" in text
        
        # Log SRT -> chỉ vào tab SRT, không vào Session
        if is_srt_log and hasattr(self, 'srt_view') and self.srt_view:
            self.srt_view.appendPlainText(text.replace("[INFO] - ", ""))
            self.srt_view.moveCursor(QtGui.QTextCursor.End)
            # Cập nhật counter
            if hasattr(self, 'srt_count'):
                self.srt_count += 1
                if hasattr(self, 'log_tabs'):
                    self.log_tabs.setTabText(3, f"📄 SRT ({self.srt_count})")
            return  # Không hiển thị trong Session
        
        # Log thường -> Session
        if self.log_view:
            # Highlight progress
            if is_progress:
                self.log_view.appendPlainText(f"▶ {text}")
            else:
                self.log_view.appendPlainText(f"[{level}] {text}")
            self.log_view.moveCursor(QtGui.QTextCursor.End)
        
        # Lỗi -> tab Errors
        if is_error and hasattr(self, 'errors_view') and self.errors_view:
            self.errors_view.appendPlainText(f"[{level}] {text}")
            self.errors_view.moveCursor(QtGui.QTextCursor.End)
            if hasattr(self, 'log_tabs'):
                self.log_tabs.setTabText(2, "⚠️ Errors ●")

    def copy_log(self):
        if self.log_view:
            QtWidgets.QApplication.clipboard().setText(self.log_view.toPlainText())
            # Đổi icon để báo đã copy
            if hasattr(self, 'copy_log_btn'):
                self.copy_log_btn.setText("✅")
                # Đổi lại sau 2 giây
                QtCore.QTimer.singleShot(2000, lambda: self.copy_log_btn.setText("📋"))

    def clear_log(self):
        if self.log_view:
            self.log_view.clear()

    def clear_errors(self):
        """Xóa tab Errors"""
        if hasattr(self, 'errors_view') and self.errors_view:
            self.errors_view.clear()
            if hasattr(self, 'log_tabs'):
                self.log_tabs.setTabText(2, "⚠️ Errors")

    def clear_srt_log(self):
        """Xóa tab SRT"""
        if hasattr(self, 'srt_view') and self.srt_view:
            self.srt_view.clear()
            self.srt_count = 0
            if hasattr(self, 'log_tabs'):
                self.log_tabs.setTabText(3, "📄 SRT (0)")

    def refresh_history_view(self):
        """Refresh bảng lịch sử xử lý và auto-migrate data cũ"""
        if not hasattr(self, 'history_table'):
            return
        
        self.history_table.setRowCount(0)
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.exists(folder):
            return
        
        # Auto-migrate: nếu có data cũ và chưa có history mới, migrate
        try:
            from mkvprocessor.history_manager import HistoryManager
            history = HistoryManager(os.path.join(folder, "Subtitles"))
            
            # Import từ legacy log nếu có
            legacy_log = os.path.join(folder, "Subtitles", "processed_files.log")
            if os.path.exists(legacy_log):
                imported = history.import_legacy_log(legacy_log)
                if imported > 0:
                    self.log_message(f"Đã migrate {imported} entries từ processed_files.log", "INFO")
            
            # Import từ logs/*.json nếu có
            logs_dir = os.path.join(folder, "Subtitles", "logs")
            if os.path.exists(logs_dir):
                imported = history.import_json_logs(logs_dir)
                if imported > 0:
                    self.log_message(f"Đã migrate {imported} entries từ logs/*.json", "INFO")
            
            # Lưu index
            history.save_index()
            
            # Lấy entries từ history manager
            entries = history.get_all_entries()
        except ImportError:
            # Fallback nếu không có history_manager
            entries = []
            
            # 1. Đọc từ processed_files.log
            log_file = os.path.join(folder, "Subtitles", "processed_files.log")
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            parts = line.strip().split("|")
                            if len(parts) >= 2:
                                entries.append({
                                    "old_name": parts[0],
                                    "new_name": parts[1],
                                    "time": parts[2] if len(parts) > 2 else "",
                                    "signature": parts[3] if len(parts) > 3 else ""
                                })
                except Exception:
                    pass
        
            # 2. Đọc từ logs/*.json
            logs_dir = Path(folder) / "Subtitles" / "logs"
            if logs_dir.exists():
                for json_file in logs_dir.glob("*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                for entry in data:
                                    entries.append({
                                        "old_name": entry.get("old_name", ""),
                                        "new_name": entry.get("new_name", ""),
                                        "time": entry.get("timestamp", ""),
                                        "signature": entry.get("signature", "")
                                    })
                    except Exception:
                        pass
        
        # Sắp xếp theo thời gian (mới nhất trước)
        entries.sort(key=lambda x: x.get("time", ""), reverse=True)
        
        # Hiển thị trong bảng
        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.history_table.setItem(row, 0, QtWidgets.QTableWidgetItem(entry.get("old_name", "")))
            self.history_table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry.get("new_name", "")))
            self.history_table.setItem(row, 2, QtWidgets.QTableWidgetItem(entry.get("time", "")))
            sig = entry.get("signature", "")
            # Rút gọn signature
            short_sig = sig[:20] + "..." if len(sig) > 20 else sig
            self.history_table.setItem(row, 3, QtWidgets.QTableWidgetItem(short_sig))

    def open_logs_folder(self):
        folder = self.folder_edit.text().strip()
        logs_dir = Path(folder) / "Subtitles" / "logs" if folder else Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(logs_dir.resolve())))

    def _browse_output_folder(self, folder_type: str):
        """Browse for output folder and update the corresponding field."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, f"Chọn thư mục {folder_type}")
        if folder:
            if folder_type == "dubbed":
                self.dubbed_folder_edit.setText(folder)
            elif folder_type == "subtitles":
                self.subs_folder_edit.setText(folder)
            elif folder_type == "original":
                self.original_folder_edit.setText(folder)
            elif folder_type == "cache":
                self.cache_dir_edit.setText(folder)

    def save_settings(self):
        # Save language if available
        try:
            if hasattr(self, 'language_combo'):
                lang_code = self.language_combo.currentData()
                if lang_code:
                    self.config["language"] = lang_code
                    from mkvprocessor.i18n import set_language
                    set_language(lang_code)
        except (ImportError, AttributeError):
            pass
        
        self.config.update({
            "input_folder": self.folder_edit.text(),
            "auto_upload": self.auto_upload_cb.isChecked(),
            "repo": self.repo_edit.text(),
            "repo_url": self.repo_url_edit.text(),
            "branch": self.branch_edit.text(),
            "token": self.token_edit.text(),
            "force_reprocess": self.force_reprocess_cb.isChecked(),
            "prefer_beta_updates": self.beta_stable_combo.currentData() == "beta" if hasattr(self, 'beta_stable_combo') else False,
            "auto_download_updates": self.auto_download_cb.isChecked() if hasattr(self, 'auto_download_cb') else False,
            # Output folder settings
            "output_folder_dubbed": self.dubbed_folder_edit.text().strip() if hasattr(self, 'dubbed_folder_edit') else "",
            "output_folder_subtitles": self.subs_folder_edit.text().strip() if hasattr(self, 'subs_folder_edit') else "",
            "output_folder_original": self.original_folder_edit.text().strip() if hasattr(self, 'original_folder_edit') else "",
            # SSD Cache settings
            "use_ssd_cache": self.use_ssd_cache_cb.isChecked() if hasattr(self, 'use_ssd_cache_cb') else True,
            "temp_cache_dir": self.cache_dir_edit.text().strip() if hasattr(self, 'cache_dir_edit') else "",
        })
        save_user_config(self.config)
        self.settings_status.setText("✅ Saved")
        self.refresh_system_status()

    def test_token(self):
        token, repo = self.token_edit.text().strip(), self.repo_edit.text().strip()
        if not token or not repo:
            QtWidgets.QMessageBox.warning(self, "Error", "Token and repo are required.")
            return
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}", 
                           headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if r.status_code == 200:
                self.show_info_message("OK", "Token hợp lệ!")
            else:
                QtWidgets.QMessageBox.critical(self, "Error", f"Status code {r.status_code}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def refresh_system_status(self):
        """Refresh system status - lazy load script module"""
        try:
            script = self._get_script_module()
            ok = script.check_ffmpeg_available()
            self.status_labels["ffmpeg"].setText(f"FFmpeg: {'✓' if ok else '✗'}")
            self.status_labels["ffmpeg"].setStyleSheet(f"color: {get_status_color('success' if ok else 'warning')};")
        except Exception as e:
            print(f"[WARNING] Không thể kiểm tra FFmpeg: {e}")
            self.status_labels["ffmpeg"].setText("FFmpeg: ?")

        try:
            script = self._get_script_module()
            ram = script.check_available_ram()
            self.status_labels["ram"].setText(f"RAM: {ram:.1f}GB")
            self.status_labels["ram"].setStyleSheet(f"color: {get_status_color('info')};")
        except Exception as e:
            print(f"[WARNING] Không thể kiểm tra RAM: {e}")
            self.status_labels["ram"].setText("RAM: ?")

        has_config = get_config_path().exists()
        if not has_config or not self.config.get("token"):
            self.status_labels["github"].setText("GitHub: Cấu hình →")
            self.status_labels["github"].setStyleSheet(f"color: {get_status_color('warning')}; text-decoration: underline;")
        elif self.config.get("auto_upload"):
            self.status_labels["github"].setText("GitHub: ✓ Auto")
            self.status_labels["github"].setStyleSheet(f"color: {get_status_color('success')};")
        else:
            self.status_labels["github"].setText("GitHub: Tắt")
            self.status_labels["github"].setStyleSheet(f"color: {get_status_color('warning')};")

        QtCore.QTimer.singleShot(60000, self.refresh_system_status)
    
    def check_for_updates(self):
        """Manually check for updates."""
        update_manager = self._get_update_manager()
        if not update_manager:
            QtWidgets.QMessageBox.warning(
                self, 
                "Update Manager", 
                "Update manager không khả dụng.\n\n"
                "Có thể do:\n"
                "- Thiếu thư viện requests (pip install requests)\n"
                "- Lỗi import module\n\n"
                "Vui lòng kiểm tra console để xem chi tiết lỗi."
            )
            return
        
        self.update_manager = update_manager
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("Checking...")
        
        try:
            # Show checking status
            self.update_status_label.setText("Đang kiểm tra...")
            QtWidgets.QApplication.processEvents()
            
            # Get prefer_beta setting
            prefer_beta = self.config.get("prefer_beta_updates", False)
            update_manager.set_prefer_beta(prefer_beta)
            
            has_update, release_info = update_manager.check_for_updates(prefer_beta=prefer_beta)
            
            if has_update and release_info:
                version = release_info.get("version", "new version")
                is_beta = release_info.get("is_beta", False)
                version_type = "Beta" if is_beta else "Stable"
                
                # Update latest version label
                self.latest_version_label.setText(
                    f"📥 Bản sắp update: <b style='color: #10b981;'>{version}</b> <span style='color: #8b949e;'>({version_type})</span>"
                )
                name = release_info.get("name", "")
                body = release_info.get("body", "")
                html_url = release_info.get("html_url", "")
                
                # Update UI
                self.update_status_label.setText(
                    f"<b style='color: #10b981;'>Update available: {version}</b><br/>"
                    f"{name}<br/>"
                    f"<a href='{html_url}'>View on GitHub</a>"
                )
                if hasattr(self, '_set_update_buttons'):
                    self._set_update_buttons(download_enabled=True, restart_enabled=False)
                else:
                    self.download_update_btn.setEnabled(True)
                self.latest_release_info = release_info
                
                # Show message box with theme
                msg = QtWidgets.QMessageBox(self)
                msg.setStyleSheet(DARK_THEME)  # Apply dark theme
                msg.setIcon(QtWidgets.QMessageBox.Information)
                msg.setWindowTitle("Update Available")
                msg.setText(f"New version {version} is available!")
                msg.setInformativeText(f"{name}\n\nDo you want to download it now?")
                msg.setStandardButtons(
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
                
                if msg.exec() == QtWidgets.QMessageBox.Yes:
                    self.download_update()
            else:
                # No update available
                current_version = update_manager.get_current_version()
                is_current_beta = "beta" in current_version.lower()
                version_type = "Beta" if is_current_beta else "Stable"
                self.update_status_label.setText(
                    f"<b style='color: #10b981;'>Bạn đang dùng phiên bản mới nhất: {current_version} ({version_type})</b>"
                )
                self.latest_version_label.setText(
                    f"📥 Bản sắp update: <span style='color: #8b949e;'>Không có bản mới</span>"
                )
                self.download_update_btn.setEnabled(False)
                if hasattr(self, '_set_update_buttons'):
                    self._set_update_buttons(download_enabled=False, restart_enabled=False)
                else:
                    self.restart_update_btn.setEnabled(False)
                self.show_info_message(
                    "Up to Date",
                    f"Bạn đang dùng phiên bản mới nhất: "
                    f"{current_version} ({version_type})"
                )
                
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Lỗi khi check updates: {error_msg}")
            import traceback
            traceback.print_exc()
            
            self.update_status_label.setText(
                f"<b style='color: #ef4444;'>Lỗi: {error_msg}</b>"
            )
            QtWidgets.QMessageBox.warning(
                self, "Update Error",
                f"Không thể kiểm tra cập nhật:\n{error_msg}\n\n"
                "Kiểm tra:\n"
                "- Kết nối internet\n"
                "- GitHub API có thể truy cập\n"
                "- Xem console để biết chi tiết lỗi"
            )
        finally:
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText("🔍 Check for Updates")
    
    def download_update(self):
        """Download update file (but don't install yet - user will click Restart to install)."""
        update_manager = self._get_update_manager()
        if not update_manager or not hasattr(self, 'latest_release_info'):
            QtWidgets.QMessageBox.warning(self, "Error", "No update information available")
            return
        
        release_info = self.latest_release_info
        assets = release_info.get("assets", [])
        
        if not assets:
            QtWidgets.QMessageBox.warning(self, "Error", "No download available for this release")
            return
        
        # Find executable asset
        exe_asset = update_manager.find_exe_asset(assets)
        if not exe_asset:
            QtWidgets.QMessageBox.warning(
                self, "Error", 
                "No compatible executable found for your platform.\n"
                "Please download manually from GitHub."
            )
            return
        
        # Confirm download (skip if auto download is enabled)
        auto_download = self.config.get("auto_download_updates", False)
        if not auto_download:
            file_name = exe_asset.get("name", "update.exe")
            file_size = exe_asset.get("size", 0)
            size_mb = file_size / 1024 / 1024
            
            reply = QtWidgets.QMessageBox.question(
                self, "Download Update",
                f"Download {file_name} ({size_mb:.1f} MB)?\n\n"
                "Sau khi download, nhấn nút 'Restart & Update' để cài đặt.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply != QtWidgets.QMessageBox.Yes:
                return
        
        # Download with progress in background thread
        self.download_update_btn.setEnabled(False)
        self.update_progress_bar.setVisible(True)
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        
        # Stop any existing download worker
        if self.update_download_worker and self.update_download_worker.isRunning():
            self.update_download_worker.terminate()
            self.update_download_worker.wait()
        
        # Create and start download worker thread
        self.update_download_worker = UpdateDownloadWorker(update_manager, exe_asset, self)
        self.update_download_worker.progress_signal.connect(self._on_download_progress)
        self.update_download_worker.finished_signal.connect(self._on_download_finished)
        self.update_download_worker.error_signal.connect(self._on_download_error)
        self.update_download_worker.start()
    
    def _on_download_progress(self, downloaded: int, total: int, percent: int):
        """Update progress bar and status label from download worker."""
        self.update_progress_bar.setValue(percent)
        self.update_status_label.setText(
            f"Downloading: {downloaded / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB"
        )
        # Process events to keep UI responsive
        QtWidgets.QApplication.processEvents()
    
    def _on_download_finished(self, download_path):
        """Handle download completion."""
        self.update_progress_bar.setVisible(False)
        
        if not download_path:
            self.update_status_label.setText(
                "<b style='color: #ef4444;'>Download thất bại!</b>"
            )
            if hasattr(self, '_set_update_buttons'):
                self._set_update_buttons(download_enabled=True, restart_enabled=False)
            else:
                self.download_update_btn.setEnabled(True)
            return
        
        # Save downloaded file path for later installation
        self.downloaded_update_file = download_path
        self.update_status_label.setText(
            f"<b style='color: #10b981;'>Download hoàn tất!</b><br/>"
            f"File: {download_path.name}<br/>"
            f"Nhấn nút 'Restart & Update' để cài đặt."
        )
        self.update_progress_bar.setValue(100)
        if hasattr(self, '_set_update_buttons'):
            self._set_update_buttons(download_enabled=False, restart_enabled=True)
        else:
            self.restart_update_btn.setEnabled(True)
            self.download_update_btn.setEnabled(False)
    
    def _on_download_error(self, error_msg: str):
        """Handle download error."""
        self.update_status_label.setText(
            f"<b style='color: #ef4444;'>Error: {error_msg}</b>"
        )
        QtWidgets.QMessageBox.critical(
            self, "Update Error",
            f"Failed to download update:\n{error_msg}\n\n"
            "Please try downloading manually from GitHub."
        )
        self.update_progress_bar.setVisible(False)
        if hasattr(self, '_set_update_buttons'):
            self._set_update_buttons(download_enabled=True, restart_enabled=False)
        else:
            self.download_update_btn.setEnabled(True)
    
    def restart_and_update(self):
        """Install downloaded update and restart application."""
        if not hasattr(self, 'downloaded_update_file') or self.downloaded_update_file is None:
            QtWidgets.QMessageBox.warning(self, "Error", "No update file downloaded. Please download first.")
            return
        
        update_manager = self._get_update_manager()
        if not update_manager:
            QtWidgets.QMessageBox.warning(self, "Error", "Update manager not available")
            return
        
        # Confirm restart
        reply = QtWidgets.QMessageBox.question(
            self, "Restart & Update",
            "Cài đặt update và khởi động lại ứng dụng?\n\n"
            "Ứng dụng sẽ tự động đóng và khởi động lại.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        try:
            self.update_status_label.setText("Đang cài đặt update...")
            QtWidgets.QApplication.processEvents()
            
            if update_manager.install_update(self.downloaded_update_file):
                self.update_status_label.setText(
                    "<b style='color: #10b981;'>Cài đặt thành công! Đang khởi động lại...</b>"
                )
                QtWidgets.QApplication.processEvents()
                
                # Small delay to show message
                QtCore.QTimer.singleShot(1000, lambda: update_manager.restart_application())
            else:
                raise Exception("Cài đặt thất bại")
                
        except Exception as e:
            self.update_status_label.setText(
                f"<b style='color: #ef4444;'>Lỗi: {str(e)}</b>"
            )
            QtWidgets.QMessageBox.critical(
                self, "Update Error",
                f"Không thể cài đặt update:\n{str(e)}\n\n"
                "Vui lòng thử tải lại hoặc cài đặt thủ công."
            )
    
    def on_beta_stable_changed(self, index: int):
        """Handle beta/stable selection change."""
        prefer_beta = self.beta_stable_combo.currentData() == "beta"
        self.config["prefer_beta_updates"] = prefer_beta
        save_user_config(self.config)
        
        # Update UpdateManager preference
        update_manager = self._get_update_manager()
        if update_manager:
            update_manager.set_prefer_beta(prefer_beta)
    
    def on_auto_download_changed(self, checked: bool):
        """Handle auto download checkbox change."""
        self.config["auto_download_updates"] = checked
        save_user_config(self.config)
    
    def auto_check_for_updates(self):
        """Silently check for updates on startup (non-blocking)."""
        update_manager = self._get_update_manager()
        if not update_manager:
            print("[UPDATE] UpdateManager not available")
            return
        
        # Check in background thread to avoid blocking UI
        def check_in_background():
            try:
                print("[UPDATE] Checking for updates...")
                prefer_beta = self.config.get("prefer_beta_updates", False)
                update_manager.set_prefer_beta(prefer_beta)
                
                has_update, release_info = update_manager.check_for_updates(timeout=10, prefer_beta=prefer_beta)
                print(f"[UPDATE] Check result: has_update={has_update}, release_info={release_info is not None}")
                
                if has_update and release_info:
                    version = release_info.get('version', 'unknown')
                    is_beta = release_info.get('is_beta', False)
                    version_type = "Beta" if is_beta else "Stable"
                    print(f"[UPDATE] Update available: {version} ({version_type})")
                    
                    # Update UI in main thread
                    QtCore.QTimer.singleShot(0, lambda: self._show_update_notification(release_info))
                    
                    # Auto download if enabled
                    auto_download = self.config.get("auto_download_updates", False)
                    if auto_download:
                        print("[UPDATE] Auto download enabled, starting download...")
                        QtCore.QTimer.singleShot(1000, lambda: self._auto_download_update(release_info))
                else:
                    print("[UPDATE] No update available or already up to date")
            except Exception as e:
                # Log error but don't show to user (silent fail)
                print(f"[UPDATE] Error during auto-check: {e}")
                import traceback
                traceback.print_exc()
        
        # Run in background
        import threading
        thread = threading.Thread(target=check_in_background, daemon=True)
        thread.start()
    
    def _auto_download_update(self, release_info: dict):
        """Auto download update in background."""
        try:
            self.latest_release_info = release_info
            assets = release_info.get("assets", [])
            if not assets:
                return
            
            update_manager = self._get_update_manager()
            if not update_manager:
                return
            
            exe_asset = update_manager.find_exe_asset(assets)
            if not exe_asset:
                return
            
            # Show progress bar
            if hasattr(self, 'update_progress_bar'):
                self.update_progress_bar.setVisible(True)
                self.update_progress_bar.setRange(0, 100)
                self.update_progress_bar.setValue(0)
            
            # Stop any existing download worker
            if self.update_download_worker and self.update_download_worker.isRunning():
                self.update_download_worker.terminate()
                self.update_download_worker.wait()
            
            # Create and start download worker thread
            self.update_download_worker = UpdateDownloadWorker(update_manager, exe_asset, self)
            self.update_download_worker.progress_signal.connect(self._on_auto_download_progress)
            self.update_download_worker.finished_signal.connect(self._on_auto_download_finished)
            self.update_download_worker.error_signal.connect(self._on_auto_download_error)
            self.update_download_worker.start()
        except Exception as e:
            print(f"[UPDATE] Error during auto download: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_auto_download_progress(self, downloaded: int, total: int, percent: int):
        """Update progress for auto download."""
        if hasattr(self, 'update_progress_bar'):
            self.update_progress_bar.setValue(percent)
        if hasattr(self, 'update_status_label'):
            self.update_status_label.setText(
                f"Đang tự động tải: {downloaded / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB"
            )
        QtWidgets.QApplication.processEvents()
    
    def _on_auto_download_finished(self, download_path):
        """Handle auto download completion."""
        if download_path:
            self.downloaded_update_file = download_path
            if hasattr(self, '_set_update_buttons'):
                self._set_update_buttons(download_enabled=False, restart_enabled=True)
            elif hasattr(self, 'restart_update_btn'):
                self.restart_update_btn.setEnabled(True)
            if hasattr(self, 'update_status_label'):
                version = self.latest_release_info.get("version", "unknown") if hasattr(self, 'latest_release_info') else "unknown"
                self.update_status_label.setText(
                    f"<b style='color: #10b981;'>Đã tải xong {version}!</b><br/>"
                    f"Nhấn 'Restart & Update' để cài đặt."
                )
            print(f"[UPDATE] Auto download completed: {download_path}")
    
    def _on_auto_download_error(self, error_msg: str):
        """Handle auto download error."""
        if hasattr(self, 'update_status_label'):
            self.update_status_label.setText(
                f"<b style='color: #ef4444;'>Lỗi tự động tải: {error_msg}</b>"
            )
        print(f"[UPDATE] Error during auto download: {error_msg}")
    
    def _show_update_notification(self, release_info: dict):
        """Show update notification (called from background thread)."""
        version = release_info.get("version", "new version")
        is_beta = release_info.get("is_beta", False)
        version_type = "Beta" if is_beta else "Stable"
        name = release_info.get("name", "")
        html_url = release_info.get("html_url", "")
        
        # Update latest version label
        if hasattr(self, 'latest_version_label'):
            self.latest_version_label.setText(
                f"📥 Bản sắp update: <b style='color: #10b981;'>{version}</b> <span style='color: #8b949e;'>({version_type})</span>"
            )
        
        # Update UI
        if hasattr(self, 'update_status_label'):
            self.update_status_label.setText(
                f"<b style='color: #10b981;'>Update available: {version} ({version_type})</b><br/>"
                f"{name}<br/>"
                f"<a href='{html_url}'>View on GitHub</a>"
            )
        
        if hasattr(self, 'download_update_btn'):
            self.download_update_btn.setEnabled(True)
        
        self.latest_release_info = release_info
        
        # Show red dot badge on Settings tab
        self._show_update_badge(True)
        
        # Mark as shown (to avoid showing multiple times)
        self._update_notification_shown = True
    
    def _show_update_badge(self, show: bool):
        """Show or hide red dot badge on Settings tab."""
        if not hasattr(self, 'settings_tab_index') or self.settings_tab_index is None:
            return
        
        tab_index = self.settings_tab_index
        if show and not self._has_update_badge:
            # Add red dot to tab text
            current_text = self.tabs.tabText(tab_index)
            if "●" not in current_text:
                self.tabs.setTabText(tab_index, f"Settings ●")
                # Style the tab to show red dot
                self.tabs.tabBar().setTabTextColor(tab_index, QtGui.QColor("#ef4444"))
                self._has_update_badge = True
        elif not show and self._has_update_badge:
            # Remove red dot
            current_text = self.tabs.tabText(tab_index)
            self.tabs.setTabText(tab_index, current_text.replace(" ●", ""))
            self.tabs.tabBar().setTabTextColor(tab_index, QtGui.QColor())  # Reset to default
            self._has_update_badge = False


if __name__ == "__main__":
    # Cho phép chạy trực tiếp file này để mở UI
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
