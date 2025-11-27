"""
GUI PySide6 cho MKV Processor.

Package này chứa các module:
- file_options: Class FileOptions lưu trữ options cho mỗi file MKV
- worker: Worker thread để xử lý MKV trong background
- theme: Stylesheet/theme cho GUI
- main_window: MainWindow - cửa sổ chính của ứng dụng
"""
from __future__ import annotations

import sys

from PySide6 import QtCore, QtWidgets

from .main_window import MainWindow

__all__ = ["MainWindow", "main"]


def main():
    """Entry point cho ứng dụng GUI"""
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
