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
import importlib
import importlib.util
import types
from pathlib import Path

# Hint cho PyInstaller về dependency gui_pyside_app mà không thực thi import
if False:  # pragma: no cover
    from gui.gui_pyside_app import main as _pyi_hint  # noqa: F401


def _clear_conflicting_gui_module() -> None:
    """
    Loại bỏ module gui bị shadow bởi file gui.py ở root (_MEIPASS).
    Nếu module gui không phải package (không có __path__), xóa để ưu tiên
    package thật trong src/gui khi import sau đó.
    """
    existing = sys.modules.get("gui")
    if existing is not None and not hasattr(existing, "__path__"):
        sys.modules.pop("gui", None)


def _load_tk_gui():
    """
    Load giao diện tkinter làm phương án dự phòng nếu PySide6 lỗi.
    Ưu tiên bản trong package gui (src/gui/gui.py) đã bundle vào _MEIPASS.
    """
    tk_candidates = []
    if hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
        tk_candidates.extend([
            base_dir / "gui" / "gui.py",
            base_dir / "src" / "gui" / "gui.py",
        ])
    else:
        base_dir = Path(__file__).resolve().parent
        tk_candidates.append(base_dir / "src" / "gui" / "gui.py")

    for path in tk_candidates:
        if not path.exists():
            continue
        spec = importlib.util.spec_from_file_location("gui.tk_gui", str(path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["gui.tk_gui"] = module
            spec.loader.exec_module(module)
            main = getattr(module, "main", None)
            if callable(main):
                return main
    searched = "\n".join(f"  - {p}" for p in tk_candidates)
    raise ImportError(f"Cannot load tkinter fallback. Searched:\n{searched}")


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
    _clear_conflicting_gui_module()
    
    # Thử import chuẩn sau khi đã config sys.path
    try:
        from gui.gui_pyside_app import main
        return main
    except ImportError:
        # Sẽ fallback ở bước dưới
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
    else:
        # Từ source, import PySide phải work nếu đã cài deps
        try:
            from gui.gui_pyside_app import main
            return main
        except ImportError:
            pass

    # PySide thất bại, chuyển sang tkinter fallback
    try:
        return _load_tk_gui()
    except ImportError as tk_err:
        # Nếu vẫn lỗi, cung cấp debug chi tiết
        debug_info = "Cannot find GUI module (PySide) and tkinter fallback.\n"
        if hasattr(sys, "_MEIPASS"):
            base_dir = Path(sys._MEIPASS)
            debug_info += f"_MEIPASS: {base_dir}\n"
            if base_dir.exists():
                debug_info += "Contents (first 20):\n"
                for item in list(base_dir.iterdir())[:20]:
                    kind = "DIR" if item.is_dir() else "FILE"
                    debug_info += f"  - {item.name} ({kind})\n"
        debug_info += f"Tk fallback error: {tk_err}"
        raise ImportError(debug_info)


# Load GUI module
run_gui_app = _load_gui_module()


def main() -> None:
    """Entry point cho cả local run lẫn bản đóng gói."""
    run_gui_app()


if __name__ == "__main__":
    main()

