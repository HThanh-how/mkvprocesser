"""
PyInstaller hook để đảm bảo bundle đầy đủ psutil
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect tất cả submodules của psutil
hiddenimports = collect_submodules('psutil')

# Collect tất cả data files và binaries
datas, binaries, hiddenimports_all = collect_all('psutil')
hiddenimports += hiddenimports_all

