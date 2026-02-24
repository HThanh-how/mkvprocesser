"""
SettingsTab component for MKV Processor GUI.
Handles configuration, GitHub integration, and updates.
"""
from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui
import os
import sys
import json
from pathlib import Path
import importlib

from mkvprocessor.config_manager import save_user_config, get_config_path, load_raw_user_config
from mkvprocessor.theme import DARK_THEME, get_status_color

class UpdateDownloadWorker(QtCore.QThread):
    """Worker thread để download update trong background."""
    progress_signal = QtCore.Signal(int, int, int)
    finished_signal = QtCore.Signal(object)
    error_signal = QtCore.Signal(str)

    def __init__(self, update_manager, exe_asset, parent=None):
        super().__init__(parent)
        self.update_manager = update_manager
        self.exe_asset = exe_asset

    def run(self):
        try:
            def progress_callback(url, downloaded, total):
                if total > 0:
                    percent = int(downloaded * 100 / total)
                    self.progress_signal.emit(downloaded, total, percent)
            
            download_path = self.update_manager.download_update(self.exe_asset, progress_callback)
            self.finished_signal.emit(download_path)
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(None)

class SettingsTab(QtWidgets.QWidget):
    """Settings tab for app configuration."""
    
    def __init__(self, parent=None, config=None, log_view=None):
        super().__init__(parent)
        self.config = config if config else {}
        self.log_view = log_view
        self.update_manager = None
        self._update_manager_imported = False
        self.update_download_worker = None
        self.status_labels = getattr(parent, "status_labels", {}) if parent else {}
        
        self.build_ui()
        
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

    def _get_update_manager(self):
        """Lazy load UpdateManager"""
        if not self._update_manager_imported:
            try:
                # Basic import attempt
                from mkvprocessor.update_manager import UpdateManager
                self.update_manager = UpdateManager()
            except Exception:
                # Fallback complex import logic from MainWindow if needed
                # For now assume standard import works or fail gracefully
                try:
                    import mkvprocessor.update_manager as um
                    self.update_manager = um.UpdateManager()
                except Exception as e:
                    if self.log_view:
                        self.log_view.appendPlainText(f"[WARNING] UpdateManager unavailable: {e}")
                    self.update_manager = None
            finally:
                self._update_manager_imported = True
        return self.update_manager

    def build_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 8, 12, 12)
        scroll_layout.setSpacing(8)

        card = QtWidgets.QFrame()
        card.setObjectName("settingsCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(16)

        header_layout = QtWidgets.QVBoxLayout()
        header_layout.addWidget(QtWidgets.QLabel("Settings"))
        header_layout.addWidget(QtWidgets.QLabel("Cấu hình ứng dụng và tích hợp GitHub."))
        card_layout.addLayout(header_layout)

        # === General Group ===
        gen_group = QtWidgets.QGroupBox("Cấu hình Chung")
        gen_layout = QtWidgets.QFormLayout(gen_group)
        
        self.language_combo = QtWidgets.QComboBox()
        try:
            from mkvprocessor.i18n import get_supported_languages
            languages = get_supported_languages()
            current_lang = self.config.get("language", "vi")
            for lang_code, lang_name in languages.items():
                self.language_combo.addItem(f"{lang_name} ({lang_code})", lang_code)
                if lang_code == current_lang:
                    self.language_combo.setCurrentIndex(self.language_combo.count() - 1)
            self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        except ImportError:
            pass
        gen_layout.addRow("Language", self.language_combo)
        
        self.auto_upload_cb = QtWidgets.QCheckBox("Enable auto upload to GitHub")
        self.auto_upload_cb.setChecked(self.config.get("auto_upload", False))
        gen_layout.addRow("", self.auto_upload_cb)
        
        self.force_reprocess_cb = QtWidgets.QCheckBox("Always reprocess")
        self.force_reprocess_cb.setChecked(self.config.get("force_reprocess", False))
        gen_layout.addRow("", self.force_reprocess_cb)
        
        card_layout.addWidget(gen_group)

        # === Output Folder Group ===
        out_group = QtWidgets.QGroupBox("Thư mục Output")
        out_layout = QtWidgets.QFormLayout(out_group)
        
        self.dubbed_folder_edit = QtWidgets.QLineEdit(self.config.get("output_folder_dubbed", ""))
        dub_btn = QtWidgets.QToolButton()
        dub_btn.setText("📁")
        dub_btn.clicked.connect(lambda: self._browse_output_folder("dubbed"))
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(self.dubbed_folder_edit)
        out_row.addWidget(dub_btn)
        out_layout.addRow("Lồng tiếng", out_row)
        
        self.subs_folder_edit = QtWidgets.QLineEdit(self.config.get("output_folder_subtitles", ""))
        sub_btn = QtWidgets.QToolButton()
        sub_btn.setText("📁")
        sub_btn.clicked.connect(lambda: self._browse_output_folder("subtitles"))
        sub_row = QtWidgets.QHBoxLayout()
        sub_row.addWidget(self.subs_folder_edit)
        sub_row.addWidget(sub_btn)
        out_layout.addRow("Subtitles", sub_row)
        
        self.original_folder_edit = QtWidgets.QLineEdit(self.config.get("output_folder_original", ""))
        orig_btn = QtWidgets.QToolButton()
        orig_btn.setText("📁")
        orig_btn.clicked.connect(lambda: self._browse_output_folder("original"))
        orig_row = QtWidgets.QHBoxLayout()
        orig_row.addWidget(self.original_folder_edit)
        orig_row.addWidget(orig_btn)
        out_layout.addRow("Original", orig_row)
        
        card_layout.addWidget(out_group)
        
        # === Cache Group ===
        cache_group = QtWidgets.QGroupBox("SSD Caching")
        cache_layout = QtWidgets.QFormLayout(cache_group)
        self.use_ssd_cache_cb = QtWidgets.QCheckBox("Enable SSD Output Caching")
        self.use_ssd_cache_cb.setChecked(self.config.get("use_ssd_cache", True))
        cache_layout.addRow(self.use_ssd_cache_cb)
        
        self.cache_dir_edit = QtWidgets.QLineEdit(self.config.get("temp_cache_dir", ""))
        cache_btn = QtWidgets.QToolButton()
        cache_btn.setText("📁")
        cache_btn.clicked.connect(lambda: self._browse_output_folder("cache"))
        cache_row = QtWidgets.QHBoxLayout()
        cache_row.addWidget(self.cache_dir_edit)
        cache_row.addWidget(cache_btn)
        cache_layout.addRow("Cache Folder", cache_row)
        
        card_layout.addWidget(cache_group)

        # === GitHub Group ===
        git_group = QtWidgets.QGroupBox("GitHub Integration")
        git_layout = QtWidgets.QFormLayout(git_group)
        
        self.repo_edit = QtWidgets.QLineEdit(self.config.get("repo", ""))
        git_layout.addRow("Repository", self.repo_edit)
        
        self.repo_url_edit = QtWidgets.QLineEdit(self.config.get("repo_url", ""))
        self.repo_url_edit.setReadOnly(True)
        git_layout.addRow("Repo URL", self.repo_url_edit)
        
        self.branch_edit = QtWidgets.QLineEdit(self.config.get("branch", "main"))
        git_layout.addRow("Branch", self.branch_edit)
        
        self.token_edit = QtWidgets.QLineEdit(self.config.get("token", ""))
        self.token_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.token_toggle_btn = QtWidgets.QToolButton()
        self.token_toggle_btn.setText("👁️")
        self.token_toggle_btn.setCheckable(True)
        self.token_toggle_btn.toggled.connect(self.toggle_token_visibility)
        token_row = QtWidgets.QHBoxLayout()
        token_row.addWidget(self.token_edit)
        token_row.addWidget(self.token_toggle_btn)
        git_layout.addRow("Token", token_row)
        
        btn_row = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_settings)
        test_btn = QtWidgets.QPushButton("🔄 Test Token")
        test_btn.clicked.connect(self.test_token)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(test_btn)
        git_layout.addRow(btn_row)
        
        self.settings_status = QtWidgets.QLabel("")
        git_layout.addRow(self.settings_status)
        
        card_layout.addWidget(git_group)
        
        # === Updates Group ===
        updates_group = QtWidgets.QGroupBox("Updates")
        updates_layout = QtWidgets.QVBoxLayout(updates_group)
        
        self.check_update_btn = QtWidgets.QPushButton("🔍 Check for Updates")
        self.check_update_btn.clicked.connect(self.check_for_updates)
        updates_layout.addWidget(self.check_update_btn)
        
        self.update_status_label = QtWidgets.QLabel("")
        updates_layout.addWidget(self.update_status_label)
        
        self.download_update_btn = QtWidgets.QPushButton("⬇️ Download Update")
        self.download_update_btn.setEnabled(False)
        self.download_update_btn.clicked.connect(self.download_update)
        updates_layout.addWidget(self.download_update_btn)
        
        self.restart_update_btn = QtWidgets.QPushButton("🔄 Restart & Update")
        self.restart_update_btn.setEnabled(False)
        self.restart_update_btn.clicked.connect(self.restart_and_update)
        updates_layout.addWidget(self.restart_update_btn)
        
        self.update_progress_bar = QtWidgets.QProgressBar()
        self.update_progress_bar.setVisible(False)
        updates_layout.addWidget(self.update_progress_bar)
        
        card_layout.addWidget(updates_group)

        scroll_layout.addWidget(card)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area)

    def _browse_output_folder(self, folder_type: str):
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

    def toggle_token_visibility(self, checked: bool):
        if checked:
            self.token_edit.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self.token_edit.setEchoMode(QtWidgets.QLineEdit.Password)

    def on_language_changed(self, index: int):
        try:
            from mkvprocessor.i18n import set_language
            lang_code = self.language_combo.itemData(index)
            if lang_code:
                set_language(lang_code)
                self.config["language"] = lang_code
                save_user_config(self.config)
        except (ImportError, AttributeError):
            pass

    def save_settings(self):
        self.config.update({
            "auto_upload": self.auto_upload_cb.isChecked(),
            "repo": self.repo_edit.text(),
            "repo_url": self.repo_url_edit.text(),
            "branch": self.branch_edit.text(),
            "token": self.token_edit.text(),
            "force_reprocess": self.force_reprocess_cb.isChecked(),
            "output_folder_dubbed": self.dubbed_folder_edit.text().strip(),
            "output_folder_subtitles": self.subs_folder_edit.text().strip(),
            "output_folder_original": self.original_folder_edit.text().strip(),
            "use_ssd_cache": self.use_ssd_cache_cb.isChecked(),
            "temp_cache_dir": self.cache_dir_edit.text().strip(),
        })
        save_user_config(self.config)
        self.settings_status.setText("✅ Saved")
        
        # Verify Github status update if parent has status labels
        if "github" in self.status_labels:
            if self.config.get("auto_upload"):
                self.status_labels["github"].setText("GitHub: ✓ Auto")
                self.status_labels["github"].setStyleSheet(f"color: {get_status_color('success')};")
            else:
                self.status_labels["github"].setText("GitHub: Tắt")
                self.status_labels["github"].setStyleSheet(f"color: {get_status_color('warning')};")

    def test_token(self):
        token, repo = self.token_edit.text().strip(), self.repo_edit.text().strip()
        if not token or not repo:
            QtWidgets.QMessageBox.warning(self, "Error", "Token and repo are required.")
            return
        try:
            import requests
            r = requests.get(f"https://api.github.com/repos/{repo}", 
                           headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if r.status_code == 200:
                self.show_info_message("OK", "Token hợp lệ!")
            else:
                QtWidgets.QMessageBox.critical(self, "Error", f"Status code {r.status_code}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def check_for_updates(self):
        update_manager = self._get_update_manager()
        if not update_manager:
            return
        
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("Checking...")
        try:
            has_update, release_info = update_manager.check_for_updates()
            if has_update and release_info:
                self.latest_release_info = release_info
                self.update_status_label.setText(f"New version available: {release_info.get('version')}")
                self.download_update_btn.setEnabled(True)
            else:
                self.update_status_label.setText("Up to date.")
        except Exception as e:
            self.update_status_label.setText(f"Error: {e}")
        finally:
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText("🔍 Check for Updates")

    def download_update(self):
        update_manager = self._get_update_manager()
        if not update_manager or not hasattr(self, 'latest_release_info'):
            return
            
        release_info = self.latest_release_info
        assets = release_info.get("assets", [])
        exe_asset = update_manager.find_exe_asset(assets)
        
        if exe_asset:
            self.download_update_btn.setEnabled(False)
            self.update_progress_bar.setVisible(True)
            self.update_download_worker = UpdateDownloadWorker(update_manager, exe_asset, self)
            self.update_download_worker.progress_signal.connect(lambda d, t, p: self.update_progress_bar.setValue(p))
            self.update_download_worker.finished_signal.connect(self._on_download_finished)
            self.update_download_worker.start()

    def _on_download_finished(self, download_path):
        self.update_progress_bar.setVisible(False)
        if download_path:
            self.downloaded_update_file = download_path
            self.update_status_label.setText("Download complete. Ready to install.")
            self.restart_update_btn.setEnabled(True)
        else:
            self.update_status_label.setText("Download failed.")
            self.download_update_btn.setEnabled(True)

    def restart_and_update(self):
        if hasattr(self, 'downloaded_update_file') and self.update_manager:
             self.update_manager.install_update(self.downloaded_update_file)
             self.update_manager.restart_application()
