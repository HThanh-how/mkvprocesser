"""
GUI Application for MKV Video Processing Toolkit.
Uses tkinter (built-in Python) - no additional installation required.
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import queue
import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path

import requests

import sys
from pathlib import Path

def _append_path(path: Path) -> None:
    if path.exists():
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
_append_path(src_dir)

if getattr(sys, "frozen", False):
    base_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    _append_path(base_dir)
    _append_path(base_dir / "src")

BASE_DIR = Path(getattr(sys, '_MEIPASS', current_dir))
_append_path(BASE_DIR)

from mkvprocessor.config_manager import load_user_config, save_user_config

def load_script_module():
    """Load processing core module, supporting legacy fallbacks."""
    preferred_modules = [
        ("mkvprocessor", "processing_core"),
        ("mkvprocessor", "legacy_api"),
        ("", "processing_core"),
        ("", "legacy_api"),
    ]

    for pkg, name in preferred_modules:
        try:
            if pkg:
                module = importlib.import_module(f"{pkg}.{name}")
            else:
                module = importlib.import_module(name)
            return module
        except ModuleNotFoundError:
            continue

    # Manual fallback: search bundled file
    for candidate in (
        "processing_core.py",
        "processing_core.pyc",
        "legacy_api.py",
        "legacy_api.pyc",
    ):
        script_file = BASE_DIR / candidate
        if script_file.exists():
            spec = importlib.util.spec_from_file_location("processing_core", script_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                sys.modules["processing_core"] = module
                return module
    raise ImportError("Cannot locate processing_core module")

# Check if running from executable (PyInstaller) or source code
IS_EXECUTABLE = getattr(sys, 'frozen', False)

# IMPORTANT: Import ffmpeg và psutil để PyInstaller bundle kèm
try:
    import ffmpeg  # type: ignore
    import psutil  # type: ignore
except ImportError:
    pass

try:
    from mkvprocessor.ffmpeg_helper import (  # type: ignore
        check_ffmpeg_available as bundled_ffmpeg_check,
    )
except ImportError:
    try:
        from ffmpeg_helper import check_ffmpeg_available as bundled_ffmpeg_check  # type: ignore
    except ImportError:
        bundled_ffmpeg_check = None  # type: ignore[assignment]

# Import processing functions (legacy name kept for compatibility)
process_main = None
check_ffmpeg_available = None
check_available_ram = None
get_file_size_gb = None
read_processed_files = None
create_folder = None
import_success = False

try:
    script_module = load_script_module()
    process_main = getattr(script_module, "main", None)
    check_ffmpeg_available = getattr(script_module, "check_ffmpeg_available", None)
    check_available_ram = getattr(script_module, "check_available_ram", None)
    get_file_size_gb = getattr(script_module, "get_file_size_gb", None)
    read_processed_files = getattr(script_module, "read_processed_files", None)
    create_folder = getattr(script_module, "create_folder", None)
    import_success = all([
        process_main,
        check_ffmpeg_available,
        check_available_ram,
        get_file_size_gb,
        read_processed_files,
        create_folder,
    ])
except Exception as e:
    import_error = str(e)
    if not IS_EXECUTABLE:
        import logging
        logging.error(f"Error importing script: {import_error}")


class MKVProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 MKV Video Processing Toolkit")
        self.root.geometry("1280x840")
        self.root.resizable(True, True)
        
        # Queue for communication between processing thread and GUI
        self.log_queue = queue.Queue()
        
        # State variables
        self.is_processing = False
        self.processing_error = False
        self.config = load_user_config()
        self.current_folder = tk.StringVar(value=self.config.get("input_folder", "."))
        self.auto_upload_var = tk.BooleanVar(value=self.config.get("auto_upload", False))
        self.repo_var = tk.StringVar(value=self.config.get("repo", "HThanh-how/Subtitles"))
        self.branch_var = tk.StringVar(value=self.config.get("branch", "main"))
        self.logs_dir_var = tk.StringVar(value=self.config.get("logs_dir", "logs"))
        self.subtitle_dir_var = tk.StringVar(value=self.config.get("subtitle_dir", "subtitles"))
        self.token_var = tk.StringVar(value=self.config.get("token", ""))
        self.show_token = tk.BooleanVar(value=False)

        # Define color palette in Apple liquid glass style (bold but still readable)
        self.bg_color = "#050d1f"
        self.card_bg = "#112030"
        self.card_border = "#1f2f45"
        self.card_overlay = "#1a2d44"
        self.text_primary = "#f6f9ff"
        self.text_secondary = "#97abc8"
        self.accent_primary = "#7fd3ff"
        self.accent_secondary = "#e0b2ff"
        self.success_color = "#67f7c8"
        self.warning_color = "#ffd38b"
        self.error_color = "#ff8e9e"
        
        self.setup_ui()
        self.check_dependencies()
        self.process_log_queue()
        
    def setup_ui(self) -> None:
        """Set up the entire UI in liquid glass style."""
        self.root.configure(bg=self.bg_color)
        self.root.minsize(1280, 820)
        self.setup_styles()

        self.main_frame = tk.Frame(self.root, bg=self.bg_color)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=36, pady=(28, 18))

        self.main_frame.grid_columnconfigure(0, weight=3, minsize=720)
        self.main_frame.grid_columnconfigure(1, weight=2, minsize=460)
        self.main_frame.grid_rowconfigure(0, weight=0)
        self.main_frame.grid_rowconfigure(1, weight=1)

        hero_card = self.create_glass_card(self.main_frame)
        hero_card.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 26))
        self.build_hero_card(hero_card)

        left_column = tk.Frame(self.main_frame, bg=self.bg_color)
        left_column.grid(row=1, column=0, sticky="nsew", padx=(0, 22))
        left_column.grid_rowconfigure(0, weight=0)
        left_column.grid_rowconfigure(1, weight=1)

        right_column = tk.Frame(self.main_frame, bg=self.bg_color)
        right_column.grid(row=1, column=1, sticky="nsew")
        right_column.grid_rowconfigure(0, weight=0)
        right_column.grid_rowconfigure(1, weight=0)
        right_column.grid_rowconfigure(2, weight=1)

        source_card = self.create_glass_card(left_column)
        source_card.grid(row=0, column=0, sticky="nsew", pady=(0, 20))
        self.build_source_card(source_card)

        mkv_card = self.create_glass_card(left_column)
        mkv_card.grid(row=1, column=0, sticky="nsew")
        self.build_mkv_card(mkv_card)

        system_card = self.create_glass_card(right_column)
        system_card.grid(row=0, column=0, sticky="nsew", pady=(0, 18))
        self.build_system_card(system_card)

        settings_card = self.create_glass_card(right_column)
        settings_card.grid(row=1, column=0, sticky="nsew", pady=(0, 18))
        self.build_settings_card(settings_card)

        log_card = self.create_glass_card(right_column)
        log_card.grid(row=2, column=0, sticky="nsew")
        self.build_log_card(log_card)

        self.status_bar = tk.Label(
            self.root,
            text="Sẵn sàng",
            anchor=tk.W,
            bg=self.bg_color,
            fg=self.text_secondary,
            font=("Segoe UI", 10)
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=36, pady=(0, 22))

        self.update_github_status()
        self.update_hero_summary()

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Glass.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=8,
            foreground=self.text_primary,
            background=self.card_overlay,
            borderwidth=0
        )
        style.map(
            "Glass.TButton",
            background=[("active", self.card_border)]
        )

        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            foreground="#021018",
            background=self.accent_primary,
            borderwidth=0
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#84e1ff")]
        )

        style.configure(
            "Glass.TEntry",
            foreground=self.text_primary,
            fieldbackground=self.card_overlay,
            background=self.card_overlay,
            bordercolor=self.card_border,
            lightcolor=self.card_border,
            darkcolor=self.card_border,
            insertcolor=self.text_primary,
            padding=6,
            relief="flat"
        )
        style.map(
            "Glass.TEntry",
            bordercolor=[("focus", self.accent_primary)],
            lightcolor=[("focus", self.accent_primary)],
            darkcolor=[("focus", self.accent_primary)]
        )

        style.configure(
            "Glass.TCheckbutton",
            background=self.card_bg,
            foreground=self.text_secondary,
            font=("Segoe UI", 10),
            focuscolor=self.accent_primary
        )
        style.map(
            "Glass.TCheckbutton",
            foreground=[("active", self.text_primary)]
        )

        style.configure(
            "Glass.Horizontal.TProgressbar",
            troughcolor=self.card_bg,
            bordercolor=self.card_bg,
            background=self.accent_primary,
            lightcolor=self.accent_secondary,
            darkcolor=self.accent_primary
        )

    def create_glass_card(self, parent):
        card = tk.Frame(
            parent,
            bg=self.card_bg,
            padx=24,
            pady=20,
            bd=0,
            highlightthickness=1,
            highlightbackground=self.card_border,
            highlightcolor=self.card_border
        )
        return card

    def create_pill_label(self, parent, title, value):
        frame = tk.Frame(parent, bg=self.card_overlay, padx=12, pady=8)
        frame.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(
            frame,
            text=title.upper(),
            font=("Segoe UI", 9, "bold"),
            fg=self.text_secondary,
            bg=self.card_overlay
        ).pack(anchor=tk.W)
        label = tk.Label(
            frame,
            text=value,
            font=("Segoe UI", 12, "bold"),
            fg=self.text_primary,
            bg=self.card_overlay
        )
        label.pack(anchor=tk.W)
        return label

    def build_hero_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text="MKV Processor Studio",
            font=("Segoe UI Semibold", 26),
            fg=self.text_primary,
            bg=self.card_bg
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            text="Liquid glass dashboard giúp quản lý toàn bộ quy trình tách MKV, audio, phụ đề và đồng bộ GitHub trong một nơi duy nhất.",
            wraplength=900,
            justify="left",
            font=("Segoe UI", 12),
            fg=self.text_secondary,
            bg=self.card_bg
        ).grid(row=1, column=0, sticky="w", pady=(8, 16))

        pills = tk.Frame(card, bg=self.card_bg)
        pills.grid(row=2, column=0, sticky="w")
        self.hero_folder_value = self.create_pill_label(pills, "Thư mục đang xử lý", self.current_folder.get())
        upload_status = "Bật" if self.auto_upload_var.get() else "Tắt"
        self.hero_upload_value = self.create_pill_label(pills, "Tự động upload", upload_status)
        self.hero_repo_value = self.create_pill_label(pills, "Repository", self.repo_var.get())

    def build_source_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text="01. Chuẩn bị thư mục MKV",
            font=("Segoe UI Semibold", 16),
            fg=self.text_primary,
            bg=self.card_bg
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            text="Chọn thư mục nguồn, xem tổng quan dung lượng và chạy xử lý ngay tại đây.",
            font=("Segoe UI", 11),
            fg=self.text_secondary,
            bg=self.card_bg
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        entry_frame = tk.Frame(card, bg=self.card_bg)
        entry_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        entry_frame.columnconfigure(0, weight=1)

        folder_entry = ttk.Entry(
            entry_frame,
            textvariable=self.current_folder,
            font=("Segoe UI", 11),
            style="Glass.TEntry"
        )
        folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(entry_frame, text="Chọn thư mục", style="Glass.TButton", command=self.browse_folder).grid(row=0, column=1)

        stats_frame = tk.Frame(card, bg=self.card_bg)
        stats_frame.grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.folder_status = tk.Label(
            stats_frame,
            text="Thư mục: Đang kiểm tra...",
            fg=self.text_secondary,
            bg=self.card_bg,
            font=("Segoe UI", 11, "bold")
        )
        self.folder_status.pack(anchor="w")

        actions_frame = tk.Frame(card, bg=self.card_bg)
        actions_frame.grid(row=4, column=0, sticky="ew", pady=(8, 8))
        actions_frame.columnconfigure(0, weight=1)

        buttons_frame = tk.Frame(actions_frame, bg=self.card_bg)
        buttons_frame.grid(row=0, column=0, sticky="w")

        self.process_btn = ttk.Button(
            buttons_frame,
            text="🚀 Bắt đầu xử lý",
            style="Accent.TButton",
            command=self.start_processing
        )
        self.process_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(
            buttons_frame,
            text="⏹ Dừng",
            style="Glass.TButton",
            command=self.stop_processing,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT)

        ttk.Button(
            buttons_frame,
            text="🔄 Làm mới danh sách",
            style="Glass.TButton",
            command=self.refresh_mkv_list
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            buttons_frame,
            text="📂 Mở logs",
            style="Glass.TButton",
            command=self.view_processed_log
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            buttons_frame,
            text="📋 Copy log",
            style="Glass.TButton",
            command=self.copy_log_text
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.progress = ttk.Progressbar(
            actions_frame,
            mode="indeterminate",
            style="Glass.Horizontal.TProgressbar"
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def build_system_card(self, card):
        tk.Label(
            card,
            text="02. Trạng thái hệ thống",
            font=("Segoe UI Semibold", 16),
            fg=self.text_primary,
            bg=self.card_bg
        ).pack(anchor="w")
        tk.Label(
            card,
            text="Theo dõi nhanh FFmpeg, RAM, thư mục và đồng bộ GitHub.",
            font=("Segoe UI", 11),
            fg=self.text_secondary,
            bg=self.card_bg
        ).pack(anchor="w", pady=(4, 14))

        def status_label(text):
            return tk.Label(
                card,
                text=text,
                fg=self.text_secondary,
                bg=self.card_bg,
                font=("Segoe UI", 12, "bold"),
                pady=6
            )

        self.ffmpeg_status = status_label("FFmpeg • Đang kiểm tra...")
        self.ffmpeg_status.pack(anchor="w", fill="x")

        self.ram_status = status_label("RAM • Đang kiểm tra...")
        self.ram_status.pack(anchor="w", fill="x")

        self.github_status = status_label("GitHub • Chưa cấu hình")
        self.github_status.pack(anchor="w", fill="x")

    def build_mkv_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        header = tk.Frame(card, bg=self.card_bg)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header,
            text="03. Danh sách file MKV",
            font=("Segoe UI Semibold", 16),
            fg=self.text_primary,
            bg=self.card_bg
        ).pack(anchor="w")
        self.mkv_count_label = tk.Label(
            header,
            text="Chưa có dữ liệu",
            font=("Segoe UI", 11),
            fg=self.text_secondary,
            bg=self.card_bg
        )
        self.mkv_count_label.pack(anchor="w", pady=(4, 10))

        list_frame = tk.Frame(card, bg=self.card_bg)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.mkv_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.SINGLE,
            activestyle="none",
            bg=self.card_overlay,
            fg=self.text_primary,
            highlightthickness=1,
            highlightbackground=self.card_border,
            bd=0,
            relief="flat",
            font=("Consolas", 11),
            selectbackground=self.accent_primary,
            selectforeground="#020f18",
            exportselection=False
        )
        self.mkv_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.mkv_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.mkv_listbox.config(yscrollcommand=scrollbar.set)

    def build_settings_card(self, card):
        card.grid_columnconfigure(1, weight=1)
        tk.Label(
            card,
            text="04. Đồng bộ và GitHub",
            font=("Segoe UI Semibold", 16),
            fg=self.text_primary,
            bg=self.card_bg
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(
            card,
            text="Nhập thông tin GitHub, token và thư mục lưu để auto upload.",
            font=("Segoe UI", 11),
            fg=self.text_secondary,
            bg=self.card_bg
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        ttk.Checkbutton(
            card,
            text="Bật tự động upload lên GitHub",
            variable=self.auto_upload_var,
            command=self.on_setting_change,
            style="Glass.TCheckbutton"
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))

        fields = [
            ("Repository", self.repo_var),
            ("Branch", self.branch_var),
            ("Thư mục logs", self.logs_dir_var),
            ("Thư mục subtitles", self.subtitle_dir_var),
        ]
        row_index = 3
        for label_text, var in fields:
            tk.Label(
                card,
                text=label_text,
                fg=self.text_secondary,
                bg=self.card_bg,
                font=("Segoe UI", 10, "bold")
            ).grid(row=row_index, column=0, sticky="e", padx=(0, 8), pady=4)
            entry = ttk.Entry(card, textvariable=var, style="Glass.TEntry")
            entry.grid(row=row_index, column=1, sticky="ew", pady=4)
            row_index += 1

        tk.Label(
            card,
            text="GitHub Token",
            fg=self.text_secondary,
            bg=self.card_bg,
            font=("Segoe UI", 10, "bold")
        ).grid(row=row_index, column=0, sticky="ne", padx=(0, 8), pady=4)
        token_entry = ttk.Entry(card, textvariable=self.token_var, show="•", style="Glass.TEntry")
        token_entry.grid(row=row_index, column=1, sticky="ew", pady=4)
        row_index += 1

        ttk.Checkbutton(
            card,
            text="Hiển thị token",
            variable=self.show_token,
            command=lambda: token_entry.config(show="" if self.show_token.get() else "•"),
            style="Glass.TCheckbutton"
        ).grid(row=row_index, column=1, sticky="w", pady=(0, 10))
        row_index += 1

        buttons = tk.Frame(card, bg=self.card_bg)
        buttons.grid(row=row_index, column=0, columnspan=2, sticky="w", pady=(4, 10))
        ttk.Button(buttons, text="💾 Lưu cấu hình", style="Accent.TButton", command=self.save_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(buttons, text="🔌 Kiểm tra kết nối", style="Glass.TButton", command=self.test_connection).pack(side=tk.LEFT)

        row_index += 1
        self.settings_status = tk.Label(
            card,
            text="",
            fg=self.text_secondary,
            bg=self.card_bg,
            font=("Segoe UI", 10, "italic")
        )
        self.settings_status.grid(row=row_index, column=0, columnspan=2, sticky="w")

    def build_log_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        tk.Label(
            card,
            text="05. Nhật ký xử lý",
            font=("Segoe UI Semibold", 16),
            fg=self.text_primary,
            bg=self.card_bg
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            text="Theo dõi realtime log ở dạng chữ mono, dễ đọc khi xử lý dài.",
            font=("Segoe UI", 11),
            fg=self.text_secondary,
            bg=self.card_bg
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        self.log_text = scrolledtext.ScrolledText(
            card,
            height=12,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg=self.card_overlay,
            fg=self.text_primary,
            insertbackground=self.text_primary,
            relief="flat"
        )
        self.log_text.grid(row=2, column=0, sticky="nsew")

    def refresh_mkv_list(self):
        """Cập nhật danh sách file MKV trong listbox."""
        if not hasattr(self, "mkv_listbox"):
            return
        folder = self.current_folder.get()
        self.mkv_listbox.delete(0, tk.END)
        if not folder or not os.path.exists(folder):
            self.mkv_count_label.config(text="Thư mục không hợp lệ")
            return

        try:
            mkv_files = [
                f for f in os.listdir(folder)
                if f.lower().endswith(".mkv")
            ]
        except Exception as exc:
            self.mkv_count_label.config(text=f"Lỗi đọc thư mục: {exc}")
            return

        mkv_files.sort(key=lambda x: x.lower())
        for file in mkv_files:
            path = os.path.join(folder, file)
            try:
                size_gb = os.path.getsize(path) / (1024 ** 3)
                display = f"{file}   ·   {size_gb:.2f} GB"
            except OSError:
                display = file
            self.mkv_listbox.insert(tk.END, display)

        count = len(mkv_files)
        if count:
            self.mkv_count_label.config(text=f"{count} file MKV sẵn sàng xử lý")
        else:
            self.mkv_count_label.config(text="Không tìm thấy file MKV nào")

    def update_hero_summary(self):
        """Đồng bộ thông tin hero pills."""
        if hasattr(self, "hero_folder_value"):
            self.hero_folder_value.config(text=self.current_folder.get() or "(chưa chọn)")
        if hasattr(self, "hero_upload_value"):
            self.hero_upload_value.config(text="Bật" if self.auto_upload_var.get() else "Tắt")
        if hasattr(self, "hero_repo_value"):
            self.hero_repo_value.config(text=self.repo_var.get() or "N/A")

    # (old tab-based layout removed)

    def collect_settings_from_ui(self):
        return {
            "auto_upload": self.auto_upload_var.get(),
            "repo": self.repo_var.get().strip(),
            "branch": self.branch_var.get().strip() or "main",
            "logs_dir": self.logs_dir_var.get().strip() or "logs",
            "subtitle_dir": self.subtitle_dir_var.get().strip() or "subtitles",
            "token": self.token_var.get().strip(),
            "input_folder": self.current_folder.get(),
        }

    def on_setting_change(self):
        self.update_github_status()
        self.update_hero_summary()

    def save_settings(self):
        data = self.collect_settings_from_ui()
        save_user_config(data)
        self.config.update(data)
        self.settings_status.config(text="✅ Đã lưu cấu hình!", fg=self.success_color)
        self.update_github_status()
        self.update_hero_summary()

    def test_connection(self):
        data = self.collect_settings_from_ui()
        if not data["auto_upload"]:
            messagebox.showwarning("Thông tin", "Bạn chưa bật chế độ tự động upload.")
            return
        if not data["token"]:
            messagebox.showerror("Thiếu token", "Vui lòng nhập GitHub token.")
            return
        try:
            headers = {
                "Authorization": f"Bearer {data['token']}",
                "Accept": "application/vnd.github+json",
            }
            resp = requests.get(f"https://api.github.com/repos/{data['repo']}", headers=headers, timeout=10)
            if resp.status_code == 200:
                messagebox.showinfo("Thành công", "Kết nối GitHub thành công!")
                self.settings_status.config(text="✅ Kết nối GitHub thành công!", fg=self.success_color)
            else:
                messagebox.showerror("Lỗi", f"Không thể kết nối (mã {resp.status_code}). Kiểm tra repo/token.")
                self.settings_status.config(text=f"❌ Lỗi kết nối: {resp.status_code}", fg=self.error_color)
        except Exception as exc:
            messagebox.showerror("Lỗi", f"Không thể kết nối GitHub: {exc}")
            self.settings_status.config(text=f"❌ Lỗi kết nối: {exc}", fg=self.error_color)

    def update_github_status(self):
        if not hasattr(self, "github_status"):
            return
        if self.auto_upload_var.get() and self.token_var.get().strip():
            text = "GitHub • Đồng bộ đã bật"
            color = self.success_color
        elif self.auto_upload_var.get():
            text = "GitHub • Thiếu token"
            color = self.warning_color
        else:
            text = "GitHub • Đang tắt"
            color = self.text_secondary
        self.github_status.config(text=text, fg=color)
        
    def log(self, message, level="INFO"):
        """Thêm message vào log queue"""
        if level == "ERROR":
            self.processing_error = True
        self.log_queue.put((message, level))
        
    def write_log(self, message, level="INFO"):
        """Ghi log vào text widget"""
        self.log_text.insert(tk.END, f"[{level}] {message}\n")
        self.log_text.see(tk.END)
        
        # Màu sắc theo level
        if level == "ERROR":
            self.status_bar.config(text=f"❌ Lỗi: {message[:50]}", fg=self.error_color)
        elif level == "SUCCESS":
            self.status_bar.config(text=f"✅ {message[:50]}", fg=self.success_color)
        elif level == "WARNING":
            self.status_bar.config(text=f"⚠️ {message[:50]}", fg=self.warning_color)
        else:
            self.status_bar.config(text=message[:80], fg=self.text_secondary)
            
    def process_log_queue(self):
        """Xử lý queue log từ thread xử lý"""
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                self.write_log(message, level)
        except queue.Empty:
            pass
        finally:
            # Lên lịch kiểm tra lại sau 100ms
            self.root.after(100, self.process_log_queue)
            
    def check_dependencies(self):
        """Kiểm tra dependencies"""
        def check():
            # Kiểm tra FFmpeg
            if check_ffmpeg_available:
                try:
                    if check_ffmpeg_available():
                        self.root.after(0, lambda: self.ffmpeg_status.config(
                            text="FFmpeg: ✅ Đã cài đặt",
                            fg=self.success_color
                        ))
                        self.log("FFmpeg đã được cài đặt", "SUCCESS")
                    else:
                        self.root.after(0, lambda: self.ffmpeg_status.config(
                            text="FFmpeg: ❌ Chưa cài đặt",
                            fg=self.error_color
                        ))
                        self.log("FFmpeg chưa được cài đặt. Vui lòng cài đặt FFmpeg.", "ERROR")
                except Exception as e:
                    self.root.after(0, lambda: self.ffmpeg_status.config(
                        text="FFmpeg: ⚠️ Lỗi kiểm tra",
                        fg=self.warning_color
                    ))
                    self.log(f"Lỗi kiểm tra FFmpeg: {str(e)}", "WARNING")
            else:
                # Chỉ hiển thị warning nếu đang chạy từ source code
                if not IS_EXECUTABLE:
                    self.root.after(0, lambda: self.ffmpeg_status.config(
                        text="FFmpeg: ⚠️ Không thể kiểm tra (thiếu dependencies)",
                        fg=self.warning_color
                    ))
                    self.log("Thiếu thư viện Python. Chạy: pip install -r requirements.txt", "WARNING")
                else:
                    # Nếu chạy từ executable, thử kiểm tra FFmpeg trực tiếp
                    try:
                        import subprocess
                        result = subprocess.run(['ffmpeg', '-version'], 
                                               capture_output=True, 
                                               check=True)
                        self.root.after(0, lambda: self.ffmpeg_status.config(
                            text="FFmpeg: ✅ Đã cài đặt",
                            fg=self.success_color
                        ))
                        self.log("FFmpeg đã được cài đặt", "SUCCESS")
                    except:
                        # Kiểm tra FFmpeg local trong package
                        if bundled_ffmpeg_check and bundled_ffmpeg_check():
                            self.root.after(0, lambda: self.ffmpeg_status.config(
                                text="FFmpeg: ✅ Đã bundle",
                                fg=self.success_color
                            ))
                            self.log("FFmpeg đã được bundle trong package", "SUCCESS")
                        else:
                            self.root.after(0, lambda: self.ffmpeg_status.config(
                                text="FFmpeg: ❌ Chưa cài đặt",
                                fg=self.error_color
                            ))
                            self.log("FFmpeg chưa được cài đặt", "ERROR")
            
            # Kiểm tra RAM
            if check_available_ram:
                try:
                    ram = check_available_ram()
                    self.root.after(0, lambda r=ram: self.ram_status.config(
                        text=f"RAM: ✅ {r:.2f} GB khả dụng",
                        fg=self.success_color
                    ))
                except Exception as e:
                    self.root.after(0, lambda: self.ram_status.config(
                        text="RAM: ⚠️ Không thể kiểm tra",
                        fg=self.warning_color
                    ))
            else:
                # Chỉ hiển thị warning nếu đang chạy từ source code
                if not IS_EXECUTABLE:
                    self.root.after(0, lambda: self.ram_status.config(
                        text="RAM: ⚠️ Không thể kiểm tra (thiếu dependencies)",
                        fg=self.warning_color
                    ))
                else:
                    # Nếu chạy từ executable, thử import psutil trực tiếp
                    try:
                        import psutil
                        memory = psutil.virtual_memory()
                        ram_gb = memory.available / (1024 ** 3)
                        self.root.after(0, lambda r=ram_gb: self.ram_status.config(
                            text=f"RAM: ✅ {r:.2f} GB khả dụng",
                            fg=self.success_color
                        ))
                    except:
                        self.root.after(0, lambda: self.ram_status.config(
                            text="RAM: ⚠️ Không thể kiểm tra",
                            fg=self.warning_color
                        ))
            
            # Kiểm tra thư mục
            self.update_folder_status()
            self.root.after(0, self.update_github_status)
            
        threading.Thread(target=check, daemon=True).start()
        
    def browse_folder(self):
        """Chọn thư mục để xử lý"""
        folder = filedialog.askdirectory(
            title="Chọn thư mục chứa file MKV",
            initialdir=self.current_folder.get()
        )
        if folder:
            self.current_folder.set(folder)
            self.config["input_folder"] = folder
            save_user_config(self.collect_settings_from_ui())
            self.update_folder_status()
            self.update_hero_summary()
            
    def update_folder_status(self):
        """Cập nhật trạng thái thư mục"""
        folder = self.current_folder.get()
        if not folder or not os.path.exists(folder):
            self.folder_status.config(
                text="Thư mục • Không hợp lệ",
                fg=self.error_color
            )
            self.refresh_mkv_list()
            return
            
        # Đếm file MKV
        try:
            mkv_files = [f for f in os.listdir(folder) if f.lower().endswith('.mkv')]
            count = len(mkv_files)
            if count > 0:
                self.folder_status.config(
                    text=f"Thư mục • {count} file MKV tìm thấy",
                    fg=self.success_color
                )
                self.log(f"Tìm thấy {count} file MKV trong thư mục", "INFO")
            else:
                self.folder_status.config(
                    text="Thư mục • Không có file MKV",
                    fg=self.warning_color
                )
        except Exception as e:
            self.folder_status.config(
                text=f"Thư mục • Lỗi: {str(e)}",
                fg=self.error_color
            )
        finally:
            self.refresh_mkv_list()
            self.update_hero_summary()
            
    def start_processing(self):
        """Bắt đầu xử lý trong thread riêng"""
        if self.is_processing:
            messagebox.showwarning("Cảnh báo", "Đang xử lý, vui lòng đợi...")
            return
            
        folder = self.current_folder.get()
        if not folder or not os.path.exists(folder):
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục hợp lệ!")
            return
        self.config["input_folder"] = folder
        save_user_config(self.collect_settings_from_ui())
            
        # Kiểm tra FFmpeg
        ffmpeg_ok = False
        if check_ffmpeg_available:
            ffmpeg_ok = check_ffmpeg_available()
        elif IS_EXECUTABLE:
            # Nếu chạy từ executable, thử kiểm tra trực tiếp
            try:
                import subprocess
                subprocess.run(['ffmpeg', '-version'], 
                               capture_output=True, check=True)
                ffmpeg_ok = True
            except:
                ffmpeg_ok = bool(bundled_ffmpeg_check and bundled_ffmpeg_check())
        
        if not ffmpeg_ok:
            response = messagebox.askyesno(
                "Cảnh báo",
                "FFmpeg chưa được cài đặt. Bạn có muốn tiếp tục không?\n"
                "(Có thể gặp lỗi trong quá trình xử lý)"
            )
            if not response:
                return
                
        # Xác nhận
        mkv_files = [f for f in os.listdir(folder) if f.lower().endswith('.mkv')]
        if not mkv_files:
            messagebox.showwarning("Cảnh báo", "Không tìm thấy file MKV nào trong thư mục!")
            return
            
        response = messagebox.askyesno(
            "Xác nhận",
            f"Bạn có chắc muốn xử lý {len(mkv_files)} file MKV trong thư mục này?\n\n"
            f"Thư mục: {folder}"
        )
        if not response:
            return
            
        # Bắt đầu xử lý
        self.is_processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.processing_error = False
        self.log_text.delete(1.0, tk.END)
        self.log(f"Bắt đầu xử lý {len(mkv_files)} file MKV...", "INFO")
        
        # Chạy trong thread riêng
        def process():
            try:
                # Thử import lại script.py trong thread này (có thể cần thiết khi chạy từ executable)
                process_main_func = process_main
                
                if not process_main_func:
                    # Thử import lại
                    try:
                        script_module = load_script_module()
                        process_main_func = getattr(script_module, "main", None)
                        if not process_main_func:
                            raise ImportError("Không tìm thấy hàm main trong script.py")
                        self.log("Đã import script.py thành công", "INFO")
                    except ImportError as import_err:
                        self.log(f"Lỗi import script.py: {str(import_err)}", "ERROR")
                        import traceback
                        self.log(traceback.format_exc(), "ERROR")
                        self.log("Vui lòng đảm bảo script.py và dependencies có trong package", "ERROR")
                        return
                
                if process_main_func:
                    # Redirect stdout/stderr để capture log
                    import io
                    
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    
                    try:
                        # Tạo StringIO để capture output
                        log_capture = io.StringIO()
                        sys.stdout = log_capture
                        sys.stderr = log_capture
                        
                        # Chạy xử lý với thư mục đã chọn
                        process_main_func(folder)
                        
                        # Lấy output
                        output = log_capture.getvalue()
                        for line in output.split('\n'):
                            if line.strip():
                                self.log(line, "INFO")
                                
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr
                else:
                    self.log("Không thể import script.py. Vui lòng kiểm tra lại.", "ERROR")
                    
            except Exception as e:
                self.log(f"Lỗi khi xử lý: {str(e)}", "ERROR")
                import traceback
                self.log(traceback.format_exc(), "ERROR")
            finally:
                # Khôi phục UI
                self.root.after(0, self.processing_finished)
                
        threading.Thread(target=process, daemon=True).start()
        
    def stop_processing(self):
        """Dừng xử lý (chỉ có thể dừng bằng cách đóng ứng dụng)"""
        if self.is_processing:
            response = messagebox.askyesno(
                "Xác nhận",
                "Bạn có chắc muốn dừng xử lý?\n"
                "(Quá trình hiện tại sẽ hoàn thành file đang xử lý)"
            )
            if response:
                self.is_processing = False
                self.log("Người dùng yêu cầu dừng xử lý...", "WARNING")
                
    def processing_finished(self):
        """Gọi khi xử lý hoàn tất"""
        self.is_processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()
        if self.processing_error:
            self.log("Quá trình kết thúc nhưng có lỗi. Xem log chi tiết.", "WARNING")
            messagebox.showwarning("Hoàn thành (có lỗi)", "Đã kết thúc nhưng xuất hiện lỗi. Vui lòng xem log để biết chi tiết.")
        else:
            self.log("Hoàn thành xử lý!", "SUCCESS")
            messagebox.showinfo("Hoàn thành", "Đã xử lý xong tất cả file!")
        
    def view_processed_log(self):
        """Mở thư mục logs và hiển thị file JSON mới nhất."""
        logs_dir = Path(self.logs_dir_var.get() or "logs")
        if not logs_dir.exists():
            messagebox.showinfo("Thông tin", f"Chưa có thư mục logs ({logs_dir}).")
            return

        json_files = sorted(logs_dir.glob("*.json"), reverse=True)
        if not json_files:
            messagebox.showinfo("Thông tin", f"Chưa có file log trong {logs_dir}.")
            return

        latest = json_files[0]
        log_window = tk.Toplevel(self.root)
        log_window.title(f"📊 Log: {latest.name}")
        log_window.geometry("900x600")

        text_widget = scrolledtext.ScrolledText(log_window, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            content = latest.read_text(encoding="utf-8")
            parsed = json.loads(content)
            text_widget.insert(1.0, json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception as e:
            text_widget.insert(1.0, f"Lỗi khi đọc log: {e}")

    def copy_log_text(self):
        """Copy toàn bộ log hiện tại vào clipboard"""
        content = self.log_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("Thông tin", "Chưa có log để copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_bar.config(text="Đã copy log vào clipboard", fg=self.accent_primary)


def main():
    """Hàm main để chạy GUI"""
    root = tk.Tk()
    app = MKVProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

