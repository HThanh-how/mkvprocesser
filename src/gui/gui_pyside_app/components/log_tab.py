"""
LogTab component for MKV Processor GUI.
"""
from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui
import os
import json
from pathlib import Path
from mkvprocessor.i18n import t

class LogTab(QtWidgets.QWidget):
    """Log tab with sub-tabs for session, history, errors, and SRT logs."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.srt_count = 0
        self.build_ui()
        
    def build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        self.log_tabs = QtWidgets.QTabWidget()
        self.log_tabs.setObjectName("logSubTabs")
        
        # === Session Tab ===
        session_tab = QtWidgets.QWidget()
        session_layout = QtWidgets.QVBoxLayout(session_tab)
        session_layout.setContentsMargins(0, 4, 0, 0)
        
        session_header = QtWidgets.QHBoxLayout()
        session_header.addStretch()
        
        self.copy_log_btn = QtWidgets.QToolButton()
        self.copy_log_btn.setText("📋")
        self.copy_log_btn.clicked.connect(self.copy_log)
        session_header.addWidget(self.copy_log_btn)
        
        self.clear_btn = QtWidgets.QToolButton()
        self.clear_btn.setText("🗑")
        self.clear_btn.clicked.connect(self.clear_log)
        session_header.addWidget(self.clear_btn)
        
        self.open_folder_btn = QtWidgets.QToolButton()
        self.open_folder_btn.setText("📂")
        self.open_folder_btn.clicked.connect(self.open_logs_folder)
        session_header.addWidget(self.open_folder_btn)
        
        session_layout.addLayout(session_header)
        
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        self.log_view.setFont(QtGui.QFont("Consolas", 9))
        self.log_view.appendPlainText("=== MKV Processor Log ===")
        self.log_view.appendPlainText("Chờ xử lý file...")
        session_layout.addWidget(self.log_view, 1)
        
        self.log_tabs.addTab(session_tab, "📝 Session")
        
        # === History Tab ===
        history_tab = QtWidgets.QWidget()
        history_layout = QtWidgets.QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 4, 0, 0)
        
        history_header = QtWidgets.QHBoxLayout()
        history_header.addStretch()
        self.refresh_history_btn = QtWidgets.QToolButton()
        self.refresh_history_btn.setText("🔄")
        self.refresh_history_btn.setToolTip("Refresh lịch sử")
        self.refresh_history_btn.clicked.connect(self.refresh_history_view)
        history_header.addWidget(self.refresh_history_btn)
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
        
        # === Errors Tab ===
        errors_tab = QtWidgets.QWidget()
        errors_layout = QtWidgets.QVBoxLayout(errors_tab)
        errors_layout.setContentsMargins(0, 4, 0, 0)
        
        errors_header = QtWidgets.QHBoxLayout()
        errors_header.addStretch()
        self.clear_errors_btn = QtWidgets.QToolButton()
        self.clear_errors_btn.setText("🗑")
        self.clear_errors_btn.setToolTip("Clear errors")
        self.clear_errors_btn.clicked.connect(self.clear_errors)
        errors_header.addWidget(self.clear_errors_btn)
        errors_layout.addLayout(errors_header)
        
        self.errors_view = QtWidgets.QPlainTextEdit()
        self.errors_view.setReadOnly(True)
        self.errors_view.setObjectName("errorsView")
        self.errors_view.setFont(QtGui.QFont("Consolas", 9))
        palette = self.errors_view.palette()
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#f87171"))
        self.errors_view.setPalette(palette)
        errors_layout.addWidget(self.errors_view, 1)
        
        self.log_tabs.addTab(errors_tab, "⚠️ Errors")
        
        # === SRT Tab ===
        srt_tab = QtWidgets.QWidget()
        srt_layout = QtWidgets.QVBoxLayout(srt_tab)
        srt_layout.setContentsMargins(0, 4, 0, 0)
        
        srt_header = QtWidgets.QHBoxLayout()
        srt_header.addStretch()
        self.clear_srt_btn = QtWidgets.QToolButton()
        self.clear_srt_btn.setText("🗑")
        self.clear_srt_btn.setToolTip("Xóa log SRT")
        self.clear_srt_btn.clicked.connect(self.clear_srt_log)
        srt_header.addWidget(self.clear_srt_btn)
        srt_layout.addLayout(srt_header)
        
        self.srt_view = QtWidgets.QPlainTextEdit()
        self.srt_view.setReadOnly(True)
        self.srt_view.setObjectName("srtView")
        self.srt_view.setFont(QtGui.QFont("Consolas", 9))
        palette = self.srt_view.palette()
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#4ade80"))
        self.srt_view.setPalette(palette)
        srt_layout.addWidget(self.srt_view, 1)
        
        self.log_tabs.addTab(srt_tab, "📄 SRT (0)")
        
        layout.addWidget(self.log_tabs)

    def copy_log(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.copy_log_btn.setText("✅")
        QtCore.QTimer.singleShot(2000, lambda: self.copy_log_btn.setText("📋"))
        
    def clear_log(self):
        self.log_view.clear()
        
    def clear_errors(self):
        self.errors_view.clear()
        
    def clear_srt_log(self):
        self.srt_view.clear()
        self.srt_count = 0
        self.log_tabs.setTabText(3, "📄 SRT (0)")
        
    def open_logs_folder(self):
        """Delegate to parent (MainWindow) for correct folder context."""
        if self.parent and hasattr(self.parent, 'open_logs_folder'):
            self.parent.open_logs_folder()
        else:
            try:
                log_folder = Path("logs")
                log_folder.mkdir(parents=True, exist_ok=True)
                os.startfile(log_folder)
            except Exception as e:
                self.log_view.appendPlainText(f"[ERROR] Không thể mở thư mục logs: {e}")

    def refresh_history_view(self):
        """Delegate to parent (MainWindow) for correct folder and data context."""
        if self.parent and hasattr(self.parent, 'refresh_history_view'):
            self.parent.refresh_history_view()
        else:
            # Fallback nếu không có parent
            try:
                history_file = Path("history.json")
                if not history_file.exists():
                    return
                with open(history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                history_list = history_data if isinstance(history_data, list) else history_data.get("history", [])
                self.history_table.setRowCount(0)
                for item in reversed(history_list[-50:]):
                    row = self.history_table.rowCount()
                    self.history_table.insertRow(row)
                    self.history_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item.get("original_name", "")))
                    self.history_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.get("new_name", "")))
                    self.history_table.setItem(row, 2, QtWidgets.QTableWidgetItem(item.get("timestamp", "")))
                    self.history_table.setItem(row, 3, QtWidgets.QTableWidgetItem(item.get("signature", "")))
            except Exception as e:
                self.log_view.appendPlainText(f"[ERROR] Lỗi đọc history: {e}")
