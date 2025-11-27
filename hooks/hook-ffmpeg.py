"""
PyInstaller hook để đảm bảo bundle đầy đủ ffmpeg-python
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect tất cả submodules của ffmpeg
hiddenimports = collect_submodules('ffmpeg')

# Collect tất cả data files và binaries
datas, binaries, hiddenimports_all = collect_all('ffmpeg')
hiddenimports += hiddenimports_all

