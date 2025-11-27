"""
MainWindow - Cửa sổ chính của ứng dụng PySide6 GUI.
Tương tự MKVToolNix với đầy đủ tính năng.
"""
from __future__ import annotations

import importlib
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from PySide6 import QtCore, QtGui, QtWidgets

from config_manager import (
    get_config_path,
    load_raw_user_config,
    load_user_config,
    save_user_config,
)

from .file_options import FileOptions
from .theme import DARK_THEME, get_status_color
from .worker import Worker


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


class MainWindow(QtWidgets.QMainWindow):
    """Cửa sổ chính của ứng dụng"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MKV Processor (PySide6)")
        self.resize(1200, 800)
        self.config = load_user_config()
        self.script = importlib.import_module("script")
        self.worker: Worker | None = None
        self.file_options: dict[str, FileOptions] = {}
        self.current_file_path: str | None = None
        self.session_log_file: Path | None = None
        self.log_view: QtWidgets.QPlainTextEdit | None = None
        self.current_selected_path: str | None = None

        self.build_ui()
        self.apply_theme()
        QtCore.QTimer.singleShot(250, self.refresh_system_status)
        QtCore.QTimer.singleShot(500, self.refresh_file_list)

    def build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.build_processing_tab()
        self.build_settings_tab()
        self.build_log_tab()

        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng")

    def build_processing_tab(self):
        tab = QtWidgets.QWidget()
        tab_layout = QtWidgets.QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(6)

        # Card 1: Folder + Status (super compact - 1 row)
        header_card = QtWidgets.QFrame()
        header_card.setObjectName("compactCard")
        header_layout = QtWidgets.QHBoxLayout(header_card)
        header_layout.setSpacing(12)
        header_layout.setContentsMargins(12, 6, 12, 6)

        # Folder input
        folder_label = QtWidgets.QLabel("📁")
        header_layout.addWidget(folder_label)
        
        self.folder_edit = QtWidgets.QLineEdit(self.config.get("input_folder", "."))
        self.folder_edit.setObjectName("pillInput")
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Chọn thư mục chứa MKV…")
        self.folder_edit.editingFinished.connect(self.on_folder_edit_finished)
        self.folder_edit.setMaximumWidth(400)
        header_layout.addWidget(self.folder_edit)

        edit_folder_btn = QtWidgets.QToolButton()
        edit_folder_btn.setObjectName("tinyButton")
        edit_folder_btn.setText("✏️")
        edit_folder_btn.clicked.connect(self.enable_folder_manual_edit)
        header_layout.addWidget(edit_folder_btn)

        browse_btn = QtWidgets.QToolButton()
        browse_btn.setObjectName("tinyButton")
        browse_btn.setText("📂")
        browse_btn.clicked.connect(self.select_folder)
        header_layout.addWidget(browse_btn)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet("color: #334155;")
        header_layout.addWidget(sep)

        # Status inline
        self.status_labels: dict[str, QtWidgets.QLabel] = {}
        
        for key, title in [("ffmpeg", "FFmpeg"), ("ram", "RAM"), ("github", "GitHub")]:
            lbl = QtWidgets.QLabel(f"{title}: …")
            lbl.setObjectName("statusInline")
            if key == "github":
                lbl.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
                lbl.mousePressEvent = self.on_github_link_clicked
                self.github_link = lbl
            self.status_labels[key] = lbl
            header_layout.addWidget(lbl)

        header_layout.addStretch()
        tab_layout.addWidget(header_card)

        # Card 2: Danh sách file MKV (chiếm phần lớn diện tích)
        file_card = QtWidgets.QFrame()
        file_card.setObjectName("card")
        file_layout = QtWidgets.QVBoxLayout(file_card)
        file_layout.setSpacing(4)
        file_layout.setContentsMargins(8, 6, 8, 6)

        # Header compact
        file_header = QtWidgets.QHBoxLayout()
        file_header.setSpacing(8)
        
        self.select_all_cb = QtWidgets.QCheckBox("MKV Files")
        self.select_all_cb.setObjectName("selectAllCheckbox")
        self.select_all_cb.setTristate(True)
        # Dùng clicked thay vì stateChanged để xử lý user click trực tiếp
        self.select_all_cb.clicked.connect(self.on_select_all_clicked)
        file_header.addWidget(self.select_all_cb)
        
        file_header.addStretch()
        
        self.file_count_label = QtWidgets.QLabel("0 file")
        self.file_count_label.setObjectName("fileCountLabel")
        file_header.addWidget(self.file_count_label)
        
        reload_btn = QtWidgets.QToolButton()
        reload_btn.setObjectName("tinyButton")
        reload_btn.setText("🔄")
        reload_btn.setToolTip("Làm mới")
        reload_btn.clicked.connect(self.refresh_file_list)
        file_header.addWidget(reload_btn)
        
        file_layout.addLayout(file_header)

        # File tree - không giới hạn chiều cao
        self.file_tree = QtWidgets.QTreeWidget()
        self.file_tree.setObjectName("fileTree")
        self.file_tree.setHeaderLabels(["File", "Cấu hình"])
        self.file_tree.setAlternatingRowColors(False)
        self.file_tree.setRootIsDecorated(True)
        self.file_tree.setExpandsOnDoubleClick(False)
        self.file_tree.setAnimated(True)
        self.file_tree.setUniformRowHeights(False)  # Cho phép row có chiều cao khác nhau
        self.file_tree.itemChanged.connect(self.on_file_item_changed)
        self.file_tree.itemClicked.connect(self.on_file_item_clicked)
        self.file_tree.itemDoubleClicked.connect(self.on_file_double_clicked)
        self.file_tree.itemExpanded.connect(self.on_file_expanded)
        self.file_tree.itemCollapsed.connect(self.on_file_collapsed)
        header = self.file_tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.file_tree.setIndentation(16)
        palette = self.file_tree.palette()
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#0f172a"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#f8fafc"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#2563eb"))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        self.file_tree.setPalette(palette)
        file_layout.addWidget(self.file_tree, 1)

        tab_layout.addWidget(file_card, 1)  # stretch = 1 để chiếm nhiều diện tích

        # Card 3: Controls (compact)
        controls_card = QtWidgets.QFrame()
        controls_card.setObjectName("compactCard")
        controls_layout = QtWidgets.QHBoxLayout(controls_card)
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(12, 6, 12, 6)

        self.start_btn = QtWidgets.QPushButton("🚀 Bắt đầu xử lý")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn = QtWidgets.QPushButton("⏹ Dừng")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_processing)

        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setObjectName("progressBar")
        self.progress.setMaximumWidth(200)
        controls_layout.addWidget(self.progress)
        
        controls_layout.addStretch()

        tab_layout.addWidget(controls_card)

        self.tabs.addTab(tab, "Trình xử lý")

    def on_github_link_clicked(self, event):
        has_config = get_config_path().exists()
        if not has_config or not self.config.get("token"):
            self.tabs.setCurrentIndex(1)

    def on_select_all_clicked(self, checked: bool):
        """Xử lý khi user click vào checkbox select all"""
        # checked = True nếu checkbox được check, False nếu uncheck
        self.file_tree.blockSignals(True)
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
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
        
        checked = sum(1 for i in range(total) if self.file_tree.topLevelItem(i).checkState(0) == QtCore.Qt.Checked)
        
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

    def build_settings_tab(self):
        tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(tab)
        form.setSpacing(10)

        self.auto_upload_cb = QtWidgets.QCheckBox("Bật auto upload GitHub")
        self.auto_upload_cb.setChecked(self.config.get("auto_upload", False))
        form.addRow(self.auto_upload_cb)

        self.force_reprocess_cb = QtWidgets.QCheckBox("Luôn xử lý lại (bỏ qua log cũ)")
        self.force_reprocess_cb.setChecked(self.config.get("force_reprocess", False))
        form.addRow(self.force_reprocess_cb)

        has_config_file = get_config_path().exists()
        raw_config = load_raw_user_config() if has_config_file else {}

        self.repo_edit = QtWidgets.QLineEdit(raw_config.get("repo", ""))
        self.repo_edit.setPlaceholderText("vd: HThanh-how/Subtitles")
        form.addRow("Repository", self.repo_edit)

        self.repo_url_edit = QtWidgets.QLineEdit(raw_config.get("repo_url", ""))
        self.repo_url_edit.setPlaceholderText("URL repo Git")
        form.addRow("Repo URL", self.repo_url_edit)

        self.branch_edit = QtWidgets.QLineEdit(raw_config.get("branch", ""))
        self.branch_edit.setPlaceholderText("vd: main")
        form.addRow("Branch", self.branch_edit)

        self.token_edit = QtWidgets.QLineEdit(self.config.get("token", ""))
        self.token_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.token_edit.setPlaceholderText("GitHub Personal Access Token")
        form.addRow("Token", self.token_edit)

        btn_row = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("💾 Lưu")
        save_btn.clicked.connect(self.save_settings)
        test_btn = QtWidgets.QPushButton("🔄 Test")
        test_btn.clicked.connect(self.test_token)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        form.addRow(btn_row)

        self.settings_status = QtWidgets.QLabel("")
        form.addRow(self.settings_status)

        self.tabs.addTab(tab, "Cài đặt")

    def build_log_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Sub-tabs cho Logs
        self.log_tabs = QtWidgets.QTabWidget()
        self.log_tabs.setObjectName("logSubTabs")
        
        # === Sub-tab 1: Session (log hiện tại) ===
        session_tab = QtWidgets.QWidget()
        session_layout = QtWidgets.QVBoxLayout(session_tab)
        session_layout.setContentsMargins(0, 4, 0, 0)
        
        session_header = QtWidgets.QHBoxLayout()
        session_header.addStretch()
        for text, slot in [("📋", self.copy_log), ("🗑", self.clear_log), ("📂", self.open_logs_folder)]:
            btn = QtWidgets.QToolButton()
            btn.setObjectName("tinyButton")
            btn.setText(text)
            btn.clicked.connect(slot)
            session_header.addWidget(btn)
        session_layout.addLayout(session_header)
        
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        self.log_view.setFont(QtGui.QFont("Consolas", 9))
        session_layout.addWidget(self.log_view, 1)
        
        self.log_tabs.addTab(session_tab, "📝 Session")
        
        # === Sub-tab 2: History (lịch sử xử lý) ===
        history_tab = QtWidgets.QWidget()
        history_layout = QtWidgets.QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 4, 0, 0)
        
        history_header = QtWidgets.QHBoxLayout()
        history_header.addStretch()
        refresh_history_btn = QtWidgets.QToolButton()
        refresh_history_btn.setObjectName("tinyButton")
        refresh_history_btn.setText("🔄")
        refresh_history_btn.setToolTip("Refresh lịch sử")
        refresh_history_btn.clicked.connect(self.refresh_history_view)
        history_header.addWidget(refresh_history_btn)
        history_layout.addLayout(history_header)
        
        self.history_table = QtWidgets.QTableWidget()
        self.history_table.setObjectName("historyTable")
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Tên cũ", "Tên mới", "Thời gian", "Signature"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        history_layout.addWidget(self.history_table, 1)
        
        self.log_tabs.addTab(history_tab, "📚 History")
        
        # === Sub-tab 3: Errors (chỉ lỗi) ===
        errors_tab = QtWidgets.QWidget()
        errors_layout = QtWidgets.QVBoxLayout(errors_tab)
        errors_layout.setContentsMargins(0, 4, 0, 0)
        
        errors_header = QtWidgets.QHBoxLayout()
        errors_header.addStretch()
        clear_errors_btn = QtWidgets.QToolButton()
        clear_errors_btn.setObjectName("tinyButton")
        clear_errors_btn.setText("🗑")
        clear_errors_btn.setToolTip("Xóa lỗi")
        clear_errors_btn.clicked.connect(self.clear_errors)
        errors_header.addWidget(clear_errors_btn)
        errors_layout.addLayout(errors_header)
        
        self.errors_view = QtWidgets.QPlainTextEdit()
        self.errors_view.setReadOnly(True)
        self.errors_view.setObjectName("errorsView")
        self.errors_view.setFont(QtGui.QFont("Consolas", 9))
        # Style lỗi với màu đỏ
        palette = self.errors_view.palette()
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#f87171"))
        self.errors_view.setPalette(palette)
        errors_layout.addWidget(self.errors_view, 1)
        
        self.log_tabs.addTab(errors_tab, "⚠️ Errors")
        
        # === Sub-tab 4: SRT (log subtitle riêng) ===
        srt_tab = QtWidgets.QWidget()
        srt_layout = QtWidgets.QVBoxLayout(srt_tab)
        srt_layout.setContentsMargins(0, 4, 0, 0)
        
        srt_header = QtWidgets.QHBoxLayout()
        srt_header.addStretch()
        clear_srt_btn = QtWidgets.QToolButton()
        clear_srt_btn.setObjectName("tinyButton")
        clear_srt_btn.setText("🗑")
        clear_srt_btn.setToolTip("Xóa log SRT")
        clear_srt_btn.clicked.connect(self.clear_srt_log)
        srt_header.addWidget(clear_srt_btn)
        srt_layout.addLayout(srt_header)
        
        self.srt_view = QtWidgets.QPlainTextEdit()
        self.srt_view.setReadOnly(True)
        self.srt_view.setObjectName("srtView")
        self.srt_view.setFont(QtGui.QFont("Consolas", 9))
        # Style SRT với màu xanh lá
        palette = self.srt_view.palette()
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#4ade80"))
        self.srt_view.setPalette(palette)
        srt_layout.addWidget(self.srt_view, 1)
        
        self.srt_count = 0  # Counter cho SRT
        self.log_tabs.addTab(srt_tab, "📄 SRT (0)")
        
        layout.addWidget(self.log_tabs, 1)
        self.tabs.addTab(tab, "Log")

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
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}" if unit != "B" else f"{size_bytes}B"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

    def is_already_processed_by_name(self, filename: str) -> bool:
        """Kiểm tra file đã được xử lý dựa trên tiền tố tên file"""
        import re
        # Các tiền tố resolution: 8K_, 4K_, 2K_, FHD_, HD_, 480p_
        pattern = r"^(8K|4K|2K|FHD|HD|480p)_"
        return bool(re.match(pattern, filename))

    def probe_tracks(self, file_path: str) -> tuple[list, list]:
        from ffmpeg_helper import probe_file

        probe = probe_file(file_path)
        subs = [
            (
                stream.get("index", -1),
                stream.get("tags", {}).get("language", "und"),
                stream.get("tags", {}).get("title", ""),
                stream.get("codec_name", ""),
            )
            for stream in probe["streams"]
            if stream["codec_type"] == "subtitle"
        ]

        audios = []
        for order, stream in enumerate(probe["streams"]):
            if stream["codec_type"] == "audio":
                bitrate_raw = stream.get("bit_rate") or stream.get("tags", {}).get("BPS")
                try:
                    bitrate = int(bitrate_raw) if bitrate_raw else 0
                except (TypeError, ValueError):
                    bitrate = 0
                audios.append(
                    (
                        stream.get("index", -1),
                        stream.get("channels", 0),
                        stream.get("tags", {}).get("language", "und"),
                        stream.get("tags", {}).get("title", ""),
                        bitrate,
                        order,
                    )
                )
        return subs, audios

    def ensure_options_metadata(self, file_path: str, options: FileOptions) -> bool:
        if options.metadata_ready and options.cached_subs and options.cached_audios:
            return True
        try:
            from ffmpeg_helper import probe_file
            probe = probe_file(file_path)
            subs, audios = self.probe_tracks(file_path)
            
            # Cache resolution
            if not options.cached_resolution:
                video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
                if video_stream and "width" in video_stream and "height" in video_stream:
                    w, h = int(video_stream["width"]), int(video_stream["height"])
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
                else:
                    options.cached_resolution = "unknown"
            
            # Cache year
            if not options.cached_year:
                format_tags = probe.get("format", {}).get("tags", {})
                options.cached_year = format_tags.get("year", "").strip()
                
            # Lưu vào options
            options.cached_subs = subs
            options.cached_audios = audios
        except Exception as e:
            # Fallback: không có metadata nhưng vẫn hiển thị file
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
        if options.selected_audio_indices and options.audio_meta:
            first_audio_idx = options.selected_audio_indices[0]
            audio_info = options.audio_meta.get(first_audio_idx)
            if audio_info:
                lang = audio_info.get("lang", "und")
                title = audio_info.get("title", "")
                lang_abbr = self.get_language_abbreviation(lang)
                if title and title != lang_abbr:
                    lang_part = f"{lang_abbr}_{title}"
                else:
                    lang_part = lang_abbr
            else:
                lang_part = "UNK"
        else:
            lang_part = "UNK"
        
        # Tạo tên file mới
        new_name = f"{resolution}_{lang_part}"
        if year:
            new_name += f"_{year}"
        new_name += f"_{base_name}.mkv"
        
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
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.exists(folder):
            self.file_tree.clear()
            self.update_select_all_state()
            return

        try:
            # Load processed files log (lịch sử xử lý file)
            processed_old_names = set()  # Tên file cũ đã xử lý
            processed_new_names = set()  # Tên file mới (đã rename)
            processed_info = {}  # Thông tin chi tiết
            
            # 1. Đọc từ processed_files.log (format cũ)
            log_file = os.path.join(folder, "Subtitles", "processed_files.log")
            if os.path.exists(log_file):
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
                    except (json.JSONDecodeError, IOError):
                        pass

            mkv_files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".mkv"))

            # Phân loại: đã xử lý (có tiền tố HOẶC có trong log) vs chưa xử lý
            processed_files = []
            pending_files = []
            for mkv in mkv_files:
                # Check: có tiền tố resolution HOẶC có trong log (cả old_name và new_name)
                has_prefix = self.is_already_processed_by_name(mkv)
                in_log = mkv in processed_old_names or mkv in processed_new_names
                
                if has_prefix or in_log:
                    processed_files.append(mkv)
                else:
                    pending_files.append(mkv)

            self.file_tree.blockSignals(True)
            self.file_tree.clear()
            
            # Hiển thị file chưa xử lý trước (màu vàng)
            for mkv in pending_files:
                file_path = os.path.abspath(os.path.join(folder, mkv))
                options = self.file_options.setdefault(file_path, FileOptions(file_path))

                self.ensure_options_metadata(file_path, options)

                size = self.format_file_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "?"
                
                item = QtWidgets.QTreeWidgetItem(self.file_tree)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.Checked if options.process_enabled else QtCore.Qt.Unchecked)
                
                item.setText(0, f"{mkv} ({size})")
                item.setText(1, self.get_file_config_summary(options))
                item.setData(0, QtCore.Qt.UserRole, file_path)
                
                # Màu vàng cho file chưa xử lý
                fg = QtGui.QColor("#facc15")
                bg = QtGui.QColor("#2f1b09")
                for col in range(2):
                    item.setForeground(col, fg)
                    item.setBackground(col, bg)
                
                # Placeholder for expand
                ph = QtWidgets.QTreeWidgetItem(item)
                ph.setData(0, QtCore.Qt.UserRole, "placeholder")
                ph.setText(0, "Loading...")

            # Hiển thị file đã xử lý sau (màu xanh)
            for mkv in processed_files:
                file_path = os.path.abspath(os.path.join(folder, mkv))
                options = self.file_options.setdefault(file_path, FileOptions(file_path))

                self.ensure_options_metadata(file_path, options)

                size = self.format_file_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "?"
                
                item = QtWidgets.QTreeWidgetItem(self.file_tree)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                # File đã xử lý mặc định bỏ chọn
                options.process_enabled = False
                item.setCheckState(0, QtCore.Qt.Unchecked)
                
                item.setText(0, f"✓ {mkv} ({size})")
                item.setText(1, self.get_file_config_summary(options))
                item.setData(0, QtCore.Qt.UserRole, file_path)
                
                # Màu xanh cho file đã xử lý
                fg = QtGui.QColor("#bbf7d0")
                bg = QtGui.QColor("#0f2f1a")
                for col in range(2):
                    item.setForeground(col, fg)
                    item.setBackground(col, bg)
                
                # Placeholder for expand
                ph = QtWidgets.QTreeWidgetItem(item)
                ph.setData(0, QtCore.Qt.UserRole, "placeholder")
                ph.setText(0, "Loading...")

            self.file_count_label.setText(f"{len(processed_files)}/{len(mkv_files)}")

        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Lỗi", str(e))
        finally:
            self.file_tree.blockSignals(False)
            self.update_select_all_state()

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
                    if other_item != item and other_item.isExpanded():
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
                if other_item != item and other_item.isExpanded():
                    other_item.setExpanded(False)
            
            # Toggle expand (mở/đóng config)
            item.setExpanded(not item.isExpanded())

    def on_file_expanded(self, item):
        file_path = item.data(0, QtCore.Qt.UserRole)
        if not file_path or not isinstance(file_path, str) or not os.path.exists(file_path):
            return

        # Clear placeholder
        while item.childCount() > 0:
            item.removeChild(item.child(0))

        options = self.file_options.setdefault(file_path, FileOptions(file_path))

        try:
            if not self.ensure_options_metadata(file_path, options):
                raise RuntimeError("Không đọc được metadata")

            subs = options.cached_subs
            audios = options.cached_audios

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

        export_list = QtWidgets.QWidget()
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
        
        export_layout.addWidget(export_list)
        
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
        # Tính chiều cao dựa trên số audio tracks (mỗi item ~36px)
        audio_height = max(80, min(350, len(audios) * 36 + 20))
        audio_list.setMinimumHeight(audio_height)
        audio_list.setMaximumHeight(audio_height)

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

        srt_mux_list = QtWidgets.QWidget()
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
        
        srt_col_layout.addWidget(srt_mux_list)
        
        # Enable/disable dựa trên mux_audio (không cần check mux_subtitles vì đã bỏ checkbox riêng)
        srt_mux_list.setEnabled(options.mux_audio)
        
        # Thêm 2 cột vào layout
        mux_columns.addWidget(audio_col, 1)
        mux_columns.addWidget(srt_col, 1)
        mux_layout.addLayout(mux_columns)

        def on_mux_audio_toggle(c):
            options.mux_audio = c
            audio_list.setEnabled(c)
            srt_mux_list.setEnabled(c)
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
                srt_mux_list.setEnabled(False)
            elif selected_count > 0 and not options.mux_audio:
                # Tự động bật mux nếu có audio được chọn
                mux_audio_cb.setChecked(True)
                options.mux_audio = True
                audio_list.setEnabled(True)
                srt_mux_list.setEnabled(True)
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
        folder = self.folder_edit.text().strip()
        if not folder:
            QtWidgets.QMessageBox.warning(self, "Lỗi", "Chọn thư mục trước.")
            return
        if self.worker and self.worker.isRunning():
            return

        selected = []
        options_data = {}
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            path = item.data(0, QtCore.Qt.UserRole)
            if item.checkState(0) == QtCore.Qt.Checked and path and os.path.exists(path):
                selected.append(path)
                if path in self.file_options:
                    options_data[path] = self.file_options[path].to_dict()

        if not selected:
            QtWidgets.QMessageBox.information(self, "Info", "Chọn ít nhất 1 file.")
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
        self.worker.finished_signal.connect(self.finish_processing)
        self.worker.start()
        
        # Setup progress bar với range thực tế
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress.setFormat("%v/%m")
        self.progress.setVisible(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_bar.showMessage(f"Đang xử lý 0/{len(selected)} files…")

    def stop_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.terminate()
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_bar.showMessage("Đã dừng", 3000)

    def update_progress(self, current: int, total: int, filename: str):
        """Cập nhật thanh tiến độ"""
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        # Rút gọn tên file nếu quá dài
        short_name = filename if len(filename) <= 40 else filename[:37] + "..."
        self.status_bar.showMessage(f"[{current}/{total}] {short_name}")

    def finish_processing(self, success: bool):
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        os.environ.pop("MKV_FILE_OPTIONS", None)
        self.refresh_file_list()
        self.status_bar.showMessage("Hoàn thành" if success else "Có lỗi - xem log", 5000)

    def log_message(self, text: str, level: str = "INFO"):
        if self.session_log_file:
            try:
                with self.session_log_file.open("a", encoding="utf-8") as f:
                    f.write(f"[{level}] {text}\n")
            except:
                pass
        
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
            from history_manager import HistoryManager
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

    def save_settings(self):
        self.config.update({
            "input_folder": self.folder_edit.text(),
            "auto_upload": self.auto_upload_cb.isChecked(),
            "repo": self.repo_edit.text(),
            "repo_url": self.repo_url_edit.text(),
            "branch": self.branch_edit.text(),
            "token": self.token_edit.text(),
            "force_reprocess": self.force_reprocess_cb.isChecked(),
        })
        save_user_config(self.config)
        self.settings_status.setText("✅ Đã lưu")
        self.refresh_system_status()

    def test_token(self):
        token, repo = self.token_edit.text().strip(), self.repo_edit.text().strip()
        if not token or not repo:
            QtWidgets.QMessageBox.warning(self, "Lỗi", "Cần token và repo.")
            return
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}", 
                           headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if r.status_code == 200:
                QtWidgets.QMessageBox.information(self, "OK", "Token hợp lệ!")
            else:
                QtWidgets.QMessageBox.critical(self, "Lỗi", f"Mã {r.status_code}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Lỗi", str(e))

    def refresh_system_status(self):
        try:
            ok = self.script.check_ffmpeg_available()
            self.status_labels["ffmpeg"].setText(f"FFmpeg: {'✓' if ok else '✗'}")
            self.status_labels["ffmpeg"].setStyleSheet(f"color: {get_status_color('success' if ok else 'warning')};")
        except:
            self.status_labels["ffmpeg"].setText("FFmpeg: ?")

        try:
            ram = self.script.check_available_ram()
            self.status_labels["ram"].setText(f"RAM: {ram:.1f}GB")
            self.status_labels["ram"].setStyleSheet(f"color: {get_status_color('info')};")
        except:
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
