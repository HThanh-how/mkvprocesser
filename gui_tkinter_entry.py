"""
Entry point cho GUI tkinter - tương thích ngược

LƯU Ý: File này có tên gui.py conflict với package gui trong src/gui.
Sử dụng importlib để tránh conflict.

Cấu trúc:
- Source: project_root/src/gui/gui.py
- Bundle: _MEIPASS/gui/gui.py (không có src/)
"""
import sys
import importlib.util
from pathlib import Path


def _load_gui_module():
    """
    Load module gui.gui trực tiếp bằng importlib.
    Tránh conflict với file gui.py (file này) khi import.
    
    - Từ bundle: _MEIPASS/gui/gui.py
    - Từ source: project_root/src/gui/gui.py
    """
    if hasattr(sys, "_MEIPASS"):
        # ===== Chạy từ PyInstaller bundle =====
        # Trong bundle: gui/ nằm trực tiếp trong _MEIPASS
        base_dir = Path(sys._MEIPASS)
        gui_module_path = base_dir / "gui" / "gui.py"
        
        # Thêm _MEIPASS vào sys.path
        base_str = str(base_dir)
        if base_str not in sys.path:
            sys.path.insert(0, base_str)
    else:
        # ===== Chạy từ source =====
        base_dir = Path(__file__).resolve().parent
        src_path = base_dir / "src"
        gui_module_path = src_path / "gui" / "gui.py"
        
        # Thêm src vào sys.path cho các import tiếp theo
        src_str = str(src_path)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)
    
    if not gui_module_path.exists():
        raise ImportError(f"Cannot find GUI module at {gui_module_path}")
    
    spec = importlib.util.spec_from_file_location("_gui_tkinter", str(gui_module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load GUI module from {gui_module_path}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gui_tkinter"] = module
    spec.loader.exec_module(module)
    return module


# Load GUI module
_gui_module = _load_gui_module()

# Export main function
main = getattr(_gui_module, "main", None)

# Import và chạy GUI
if __name__ == "__main__":
    if main is not None:
        main()
    else:
        raise RuntimeError("GUI main function not found")

