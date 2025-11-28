"""
PyInstaller hook để đảm bảo bundle đầy đủ gui package
"""
from PyInstaller.utils.hooks import collect_submodules
import importlib.util

# QUAN TRỌNG: PyInstaller sẽ tự động tìm package gui nếu --paths có src/
# Hook này chỉ đảm bảo bundle đầy đủ submodules

# Kiểm tra xem package gui có tồn tại không
hiddenimports = []
try:
    # Thử tìm package gui trong sys.path
    spec = importlib.util.find_spec('gui')
    if spec is not None and spec.submodule_search_locations is not None:
        # Package tồn tại, collect submodules
        hiddenimports = collect_submodules('gui')
    else:
        # Package không tìm thấy, có thể nằm trong src/
        # PyInstaller sẽ tự bundle khi thấy import trong entry script
        pass
except Exception:
    # Nếu có lỗi, bỏ qua - PyInstaller sẽ tự bundle khi thấy import
    pass

# KHÔNG dùng collect_data_files và collect_dynamic_libs vì có thể gây warnings
# Package sẽ được bundle qua --add-data trong build script

