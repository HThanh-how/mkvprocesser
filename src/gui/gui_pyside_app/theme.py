"""
Theme - Stylesheet cho PySide6 GUI.
"""

DARK_THEME = """
QMainWindow {
    background: #0d1117;
    color: #e8eaed;
}
QWidget {
    color: #e8eaed;
    font-size: 12px;
}
QLabel {
    color: #e8eaed;
}

/* Cards */
#card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
#compactCard {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
}

/* Settings card & layout */
#settingsCard {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}
#settingsTitle {
    font-size: 18px;
    font-weight: 600;
    color: #f0f6fc;
}
#settingsSubtitle {
    font-size: 12px;
    color: #8b949e;
}
#settingsGroup {
    background: #0d1117;
    border-radius: 8px;
    border: 1px solid #21262d;
}
#settingsGroupTitle {
    font-size: 13px;
    font-weight: 600;
    color: #c9d1d9;
}
#settingsFieldLabel {
    color: #8b949e;
    font-size: 12px;
}
#settingsStatusLabel {
    font-size: 12px;
    color: #a5b4fc;
}
#settingsUpdatesHint {
    font-size: 12px;
    color: #94a3b8;
}

/* Inputs */
QLineEdit {
    background: #0d1117;
    color: #e8eaed;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus {
    border-color: #58a6ff;
}
QLineEdit#pillInput {
    background: #0d1117;
    border-radius: 12px;
    padding: 4px 12px;
}

/* ComboBox */
QComboBox {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 150px;
}
QComboBox:hover {
    border-color: #58a6ff;
    background: #161b22;
}
QComboBox:focus {
    border-color: #58a6ff;
    background: #161b22;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
    background: transparent;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #8b949e;
    width: 0;
    height: 0;
    margin-right: 8px;
}
QComboBox::down-arrow:hover {
    border-top-color: #c9d1d9;
}
QComboBox QAbstractItemView {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    selection-background-color: #1f6feb;
    selection-color: white;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    padding: 6px 12px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:hover {
    background: #21262d;
}
QComboBox QAbstractItemView::item:selected {
    background: #1f6feb;
    color: white;
}
#languageCombo {
    background: #161b22;
    color: #c9d1d9;
    font-weight: 500;
}

/* Buttons */
QPushButton {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}
QPushButton:hover {
    background: #30363d;
    border-color: #8b949e;
}
QPushButton:pressed {
    background: #161b22;
}
#primaryButton {
    background: #238636;
    border-color: #238636;
    color: white;
}
#primaryButton:hover {
    background: #2ea043;
}
#dangerButton {
    background: #da3633;
    border-color: #da3633;
    color: white;
}
#dangerButton:hover {
    background: #f85149;
}
#miniButton {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    min-width: 30px;
}
#miniButton:hover {
    background: #30363d;
}

/* Tool buttons */
QToolButton, QToolButton#tinyButton, QToolButton#smallGhostButton {
    background: transparent;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px;
    min-width: 24px;
    min-height: 24px;
}
QToolButton:hover {
    background: #21262d;
}
#ghostButton {
    background: transparent;
    border: none;
}
#ghostButton:hover {
    background: #21262d;
}

/* Tabs */
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: #161b22;
    color: #8b949e;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #0d1117;
    color: #f0f6fc;
    border-bottom: 2px solid #58a6ff;
}
QTabBar::tab:hover {
    color: #c9d1d9;
}

/* Checkboxes */
QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #0d1117;
}
QCheckBox::indicator:checked {
    background: #58a6ff;
    border-color: #58a6ff;
}
QCheckBox::indicator:hover {
    border-color: #58a6ff;
}
#selectAllCheckbox {
    font-weight: 600;
    font-size: 13px;
}

/* File tree */
#fileTree {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    outline: none;
}
#fileTree::item {
    padding: 4px;
    border-radius: 4px;
}
#fileTree::item:selected {
    background: #1f6feb;
}
#fileTree::item:hover {
    background: #21262d;
}
#fileTree::branch {
    background: transparent;
}
QHeaderView::section {
    background: #161b22;
    color: #8b949e;
    border: none;
    padding: 6px;
    font-weight: 600;
}

/* Options widget */
#optionsWidget {
    background: #161b22;
    border-radius: 6px;
}
#optionsGroup {
    font-size: 12px;
    font-weight: 600;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    margin-top: 6px;
    padding: 8px;
    background: #161b22;
}
#optionsGroup::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    background: #161b22;
}
#groupTitleCheckbox {
    font-size: 12px;
    font-weight: 600;
    color: #c9d1d9;
    margin-bottom: 4px;
}

/* Audio list */
#audioList {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    outline: none;
}
#audioList::item {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 4px;
    padding: 6px 8px;
    margin: 2px;
}
#audioList::item:selected {
    background: #1f6feb;
    border-color: #58a6ff;
}
#audioList::item:hover {
    background: #21262d;
}

/* Labels */
#fileCountLabel {
    color: #8b949e;
    font-size: 11px;
    background: #21262d;
    padding: 2px 8px;
    border-radius: 10px;
}
#statusInline {
    color: #8b949e;
    font-size: 11px;
}
#hintLabel {
    color: #6e7681;
    font-size: 10px;
    font-style: italic;
}
#sectionLabel {
    color: #c9d1d9;
    font-size: 11px;
    font-weight: bold;
    margin-top: 8px;
    margin-bottom: 4px;
}

/* Progress */
#progressBar {
    background: #21262d;
    border: none;
    border-radius: 4px;
    height: 4px;
}
#progressBar::chunk {
    background: #58a6ff;
    border-radius: 4px;
}

/* Log view */
#logView, #errorsView, #srtView {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px;
    font-family: Consolas, monospace;
}

#logView {
    color: #c9d1d9;
}

#errorsView {
    color: #f87171;
}

#srtView {
    color: #4ade80;
}

/* Log sub-tabs */
#logSubTabs::pane {
    border: none;
    background: transparent;
}
#logSubTabs::tab-bar {
    alignment: left;
}
#logSubTabs QTabBar::tab {
    background: #21262d;
    color: #8b949e;
    padding: 6px 12px;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
    font-size: 11px;
}
#logSubTabs QTabBar::tab:selected {
    background: #30363d;
    color: #f0f6fc;
}
#logSubTabs QTabBar::tab:hover:!selected {
    background: #282e36;
}

/* History table */
#historyTable {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    gridline-color: #21262d;
}
#historyTable::item {
    padding: 4px 8px;
    color: #c9d1d9;
}
#historyTable::item:alternate {
    background: #161b22;
}
#historyTable::item:selected {
    background: #1f6feb;
}
#historyTable QHeaderView::section {
    background: #21262d;
    color: #8b949e;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #30363d;
    font-weight: bold;
    font-size: 11px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #0d1117;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #0d1117;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #484f58;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* Form */
QFormLayout {
    spacing: 8px;
}

/* Context menu (right-click menu) */
QMenu {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #1f6feb;
    color: white;
}
QMenu::item:disabled {
    color: #6e7681;
}
"""


def get_status_color(mood: str) -> str:
    return {
        "success": "#3fb950",
        "warning": "#d29922",
        "info": "#58a6ff",
        "error": "#f85149",
    }.get(mood, "#8b949e")
