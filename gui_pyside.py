"""
Entry point cho GUI PySide6 - tương thích ngược

Cấu trúc khi chạy từ source:
  - project_root/src/gui/
  - project_root/src/mkvprocessor/
  
Cấu trúc khi chạy từ PyInstaller bundle:
  - _MEIPASS/gui/
  - _MEIPASS/mkvprocessor/
"""
import sys
from pathlib import Path


def _configure_sys_path() -> None:
    """
    Bổ sung đường dẫn khi chạy cả từ source lẫn PyInstaller.
    
    - Từ source: thêm src/ vào sys.path
    - Từ bundle: thêm _MEIPASS vào sys.path (gui/ và mkvprocessor/ ở đó)
    """
    if hasattr(sys, "_MEIPASS"):
        # ===== Chạy từ PyInstaller bundle =====
        # Trong bundle: gui/ và mkvprocessor/ nằm trực tiếp trong _MEIPASS
        base_dir = Path(sys._MEIPASS)
        base_str = str(base_dir)
        
        # Thêm _MEIPASS vào đầu sys.path
        if base_str in sys.path:
            sys.path.remove(base_str)
        sys.path.insert(0, base_str)
    else:
        # ===== Chạy từ source =====
        base_dir = Path(__file__).resolve().parent
        base_str = str(base_dir)
        
        # Xóa base_dir khỏi sys.path (tránh conflict với gui.py ở root)
        if base_str in sys.path:
            sys.path.remove(base_str)
        
        # Thêm src/ vào đầu sys.path
        src_path = base_dir / "src"
        if src_path.exists():
            src_str = str(src_path)
            if src_str in sys.path:
                sys.path.remove(src_str)
            sys.path.insert(0, src_str)
        
        # Thêm base_dir SAU src (để src/gui được ưu tiên hơn gui.py)
        if base_str not in sys.path:
            sys.path.append(base_str)


_configure_sys_path()

# Import GUI modules sau khi sys.path đã được cấu hình
from gui.gui_pyside_app import main as run_gui_app  # noqa: E402


def main() -> None:
    """Entry point cho cả local run lẫn bản đóng gói."""
    run_gui_app()


if __name__ == "__main__":
    main()

