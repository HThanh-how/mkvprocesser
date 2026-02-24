"""
ProcessingTab component for MKV Processor GUI.
"""
from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui
import os
from mkvprocessor.i18n import t
from .preview_dialog import PreviewDialog

class ProcessingTab(QtWidgets.QWidget):
    """Main processing tab with file list and controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setAcceptDrops(True)
        self.build_ui()
        
        # Start status refresh timer
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_system_status)
        self.refresh_timer.start(60000)
        QtCore.QTimer.singleShot(1000, self.refresh_system_status)

    def refresh_system_status(self):
        """Refresh system status."""
        try:
            from ..theme import get_status_color
        except ImportError:
            from theme import get_status_color  # type: ignore
        from mkvprocessor.config_manager import get_config_path, load_user_config
        
        # Lazy load script module
        try:
            # Try importing from candidates
            module_candidates = ["mkvprocessor.processing_core", "mkvprocessor.script"]
            script = None
            for name in module_candidates:
                try:
                    script = __import__(name, fromlist=['check_ffmpeg_available'])
                    break
                except ImportError:
                    continue
            
            if script:
                ok = script.check_ffmpeg_available()
                self.status_labels["ffmpeg"].setText(f"FFmpeg: {'✓' if ok else '✗'}")
                self.status_labels["ffmpeg"].setStyleSheet(f"color: {get_status_color('success' if ok else 'warning')};")
                
                ram = script.check_available_ram()
                self.status_labels["ram"].setText(f"RAM: {ram:.1f}GB")
                self.status_labels["ram"].setStyleSheet(f"color: {get_status_color('info')};")
        except Exception:
            pass
            
        # Check GitHub status
        try:
            config = load_user_config()
            if not config.get("token"):
                self.status_labels["github"].setText("GitHub: Cấu hình →")
                self.status_labels["github"].setStyleSheet(f"color: {get_status_color('warning')}; text-decoration: underline;")
            elif config.get("auto_upload"):
                self.status_labels["github"].setText("GitHub: ✓ Auto")
                self.status_labels["github"].setStyleSheet(f"color: {get_status_color('success')};")
            else:
                self.status_labels["github"].setText("GitHub: Tắt")
                self.status_labels["github"].setStyleSheet(f"color: {get_status_color('warning')};")
        except Exception:
            pass

    
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QtGui.QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            # Handle multiple files or folders
            paths = [url.toLocalFile() for url in urls]
            if paths:
                # Update folder_edit if it's a directory, or just process files
                last_path = paths[-1]
                if os.path.isdir(last_path):
                    self.folder_edit.setText(last_path)
                    # Trigger refresh in parent
                    if hasattr(self.parent, "on_folder_edit_finished"):
                        self.parent.on_folder_edit_finished()
                else:
                    # Logic to add specific files will go here
                    pass

        
    def build_ui(self):
        tab_layout = QtWidgets.QVBoxLayout(self)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(6)

        # Folder + Status Card
        header_card = QtWidgets.QFrame()
        header_card.setObjectName("compactCard")
        header_layout = QtWidgets.QHBoxLayout(header_card)
        header_layout.setSpacing(12)
        header_layout.setContentsMargins(12, 6, 12, 6)

        folder_label = QtWidgets.QLabel("📁")
        header_layout.addWidget(folder_label)
        
        self.folder_edit = QtWidgets.QLineEdit()
        self.folder_edit.setObjectName("pillInput")
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Chọn thư mục chứa video…")
        header_layout.addWidget(self.folder_edit)

        self.edit_folder_btn = QtWidgets.QToolButton()
        self.edit_folder_btn.setText("✏️")
        header_layout.addWidget(self.edit_folder_btn)

        self.browse_btn = QtWidgets.QToolButton()
        self.browse_btn.setObjectName("tinyButton")
        self.browse_btn.setText("📂")
        header_layout.addWidget(self.browse_btn)

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
            self.status_labels[key] = lbl
            header_layout.addWidget(lbl)


        header_layout.addStretch()
        tab_layout.addWidget(header_card)

        # File List Card
        file_card = QtWidgets.QFrame()
        file_card.setObjectName("card")
        file_layout = QtWidgets.QVBoxLayout(file_card)
        file_layout.setSpacing(4)
        file_layout.setContentsMargins(8, 6, 8, 6)

        file_header = QtWidgets.QHBoxLayout()
        self.select_all_cb = QtWidgets.QCheckBox("Video Files")
        file_header.addWidget(self.select_all_cb)
        file_header.addStretch()
        
        self.file_count_label = QtWidgets.QLabel("0 file")
        file_header.addWidget(self.file_count_label)
        
        self.reload_btn = QtWidgets.QToolButton()
        self.reload_btn.setText("🔄")
        file_header.addWidget(self.reload_btn)
        file_layout.addLayout(file_header)

        self.file_tree = QtWidgets.QTreeWidget()
        self.file_tree.setObjectName("fileTree")
        self.file_tree.setHeaderLabels(["File", "Cấu hình"])
        file_layout.addWidget(self.file_tree, 1)

        tab_layout.addWidget(file_card, 1)

        # Controls Card
        controls_card = QtWidgets.QFrame()
        controls_layout = QtWidgets.QHBoxLayout(controls_card)
        
        self.start_btn = QtWidgets.QPushButton("🚀 Start Processing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(lambda: self.start_btn.setEnabled(False))
        
        self.stop_btn = QtWidgets.QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setVisible(False)
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        
        # Granular progress bar
        self.file_progress = QtWidgets.QProgressBar()
        self.file_progress.setObjectName("fileProgress")
        self.file_progress.setTextVisible(True)
        self.file_progress.setFormat("Current: %p%")
        controls_layout.addWidget(self.file_progress)
        
        self.total_progress = QtWidgets.QProgressBar()
        self.total_progress.setObjectName("totalProgress")
        self.total_progress.setFormat("Total: %v/%m files")
        controls_layout.addWidget(self.total_progress)

        controls_layout.addStretch()

        
        tab_layout.addWidget(controls_card)
