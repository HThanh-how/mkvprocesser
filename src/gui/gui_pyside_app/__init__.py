"""
PySide6 GUI for MKV Processor.

This package contains the following modules:
- file_options: FileOptions class stores options for each MKV file
- worker: Worker thread to process MKV files in background
- theme: Stylesheet/theme for GUI
- main_window: MainWindow - main application window
"""
from __future__ import annotations

import sys

from PySide6 import QtCore, QtWidgets

from .main_window import MainWindow

__all__ = ["MainWindow", "main"]


def main() -> None:
    """Entry point for GUI application."""
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
