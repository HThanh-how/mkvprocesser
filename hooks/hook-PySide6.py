"""
PyInstaller hook để đảm bảo bundle đầy đủ PySide6 package
PySide6 cần bundle cả binaries (DLLs trên Windows) nên phải dùng collect_all
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# Collect tất cả submodules của PySide6
hiddenimports = collect_submodules('PySide6')

# Collect tất cả data files và binaries (QUAN TRỌNG: PySide6 có DLLs)
datas, binaries, hiddenimports_all = collect_all('PySide6')
hiddenimports += hiddenimports_all

# Đảm bảo bundle các module chính
hiddenimports.extend([
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtWidgets',
    'PySide6.QtGui',
    'PySide6.QtNetwork',
    'PySide6.QtOpenGL',
    'PySide6.QtQml',
])

