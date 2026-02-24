"""
PreviewDialog component for MKV Processor GUI.
"""
from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui

class PreviewDialog(QtWidgets.QDialog):
    """Dialog to preview renaming and extraction results."""
    
    def __init__(self, preview_data: list[dict], parent=None):
        super().__init__(parent)
        self.preview_data = preview_data
        self.setWindowTitle("Preview Results")
        self.resize(800, 600)
        self.build_ui()
        
    def build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Original File", "Action", "Proposed Result"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        
        self.table.setRowCount(len(self.preview_data))
        for i, row in enumerate(self.preview_data):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(row.get("original", "")))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(row.get("action", "")))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(row.get("proposed", "")))
            
        layout.addWidget(self.table)
        
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
