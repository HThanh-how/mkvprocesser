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
import importlib.util
import types
from pathlib import Path

# QUAN TRỌNG: Import này giúp PyInstaller phát hiện và bundle gui package
# PyInstaller phân tích code tĩnh, nên import này PHẢI được thấy ngay
# (không được wrap trong if/else vì PyInstaller không chạy code)
# Khi chạy thực tế, nếu import fail sẽ được xử lý trong _load_gui_module()
try:
    from gui.gui_pyside_app import main as _gui_main_preload
except ImportError:
    # Import fail là bình thường khi chạy từ bundle hoặc chưa config sys.path
    # Sẽ được xử lý lại trong _load_gui_module() sau khi config sys.path
    _gui_main_preload = None


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
        
        # Thêm src/ nếu có (một số PyInstaller config có thể bundle vào src/)
        src_path = base_dir / "src"
        if src_path.exists():
            src_str = str(src_path)
            if src_str not in sys.path:
                sys.path.insert(0, src_str)
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


def _load_gui_module():
    """Load GUI module với fallback cho cả source và bundle."""
    _configure_sys_path()
    
    # Nếu đã import thành công ở trên, dùng luôn
    if _gui_main_preload is not None:
        return _gui_main_preload
    
    # Thử import lại sau khi đã config sys.path
    try:
        from gui.gui_pyside_app import main
        return main
    except ImportError:
        pass
    
    # Fallback: load trực tiếp bằng importlib
    if hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
        # Thử các path có thể (theo thứ tự ưu tiên)
        possible_paths = [
            base_dir / "gui" / "gui_pyside_app" / "__init__.py",  # Nếu bundle trực tiếp
            base_dir / "src" / "gui" / "gui_pyside_app" / "__init__.py",  # Nếu bundle vào src/
        ]
        
        for gui_module_path in possible_paths:
            if gui_module_path.exists():
                # Tạo module name đúng
                module_name = "gui.gui_pyside_app"
                spec = importlib.util.spec_from_file_location(module_name, str(gui_module_path))
                if spec and spec.loader:
                    # Đảm bảo parent modules được tạo
                    if "gui" not in sys.modules:
                        sys.modules["gui"] = types.ModuleType("gui")
                    if "gui.gui_pyside_app" not in sys.modules:
                        sys.modules["gui.gui_pyside_app"] = types.ModuleType("gui.gui_pyside_app")
                    
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    return module.main
        
        # Nếu không tìm thấy, list tất cả files trong _MEIPASS để debug
        debug_info = f"Cannot find GUI module. Searched in:\n"
        for path in possible_paths:
            debug_info += f"  - {path}\n"
        debug_info += f"\n_MEIPASS: {base_dir}\n"
        if base_dir.exists():
            debug_info += f"Contents (first 30):\n"
            for item in list(base_dir.iterdir())[:30]:
                debug_info += f"  - {item.name} ({'DIR' if item.is_dir() else 'FILE'})\n"
                if item.is_dir() and item.name == "gui":
                    # List contents of gui directory
                    try:
                        for subitem in list(item.iterdir())[:10]:
                            debug_info += f"    - {subitem.name}\n"
                    except Exception:
                        pass
        raise ImportError(debug_info)
    else:
        # Từ source, import phải work
        from gui.gui_pyside_app import main
        return main


# Load GUI module
run_gui_app = _load_gui_module()


def main() -> None:
    """Entry point cho cả local run lẫn bản đóng gói."""
    run_gui_app()


if __name__ == "__main__":
    main()

