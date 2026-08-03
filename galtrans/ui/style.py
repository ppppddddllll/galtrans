"""全局样式表（QSS），提供统一的视觉风格。"""
from __future__ import annotations

# 调色板常量
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_DARK = "#1d4ed8"
BG = "#f5f7fa"
CARD_BG = "#ffffff"
TEXT_MAIN = "#1f2937"
TEXT_SUB = "#6b7280"
BORDER = "#e5e7eb"
DANGER = "#ef4444"
OK_GREEN = "#16a34a"
WARN = "#d97706"

_QSS = f"""
/* ===== 全局基础 ===== */
QWidget {{
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
    color: {TEXT_MAIN};
}}
QMainWindow, QWidget#navWidget {{
    background-color: {BG};
}}

/* ===== 左侧导航 ===== */
QWidget#navWidget {{
    background-color: #111827;
    border: none;
}}
QLabel#navTitle {{
    color: #ffffff;
    font-size: 17px;
    font-weight: bold;
    padding: 18px 16px 10px 16px;
}}
QListWidget#navList {{
    background: transparent;
    border: none;
    outline: none;
    color: #d1d5db;
    font-size: 14px;
}}
QListWidget#navList::item {{
    height: 42px;
    padding-left: 18px;
    border-radius: 8px;
    margin: 2px 8px;
}}
QListWidget#navList::item:hover {{
    background: rgba(255, 255, 255, 0.06);
    color: #ffffff;
}}
QListWidget#navList::item:selected {{
    background: {ACCENT};
    color: #ffffff;
}}
QLabel#versionLabel {{
    color: #6b7280;
    font-size: 11px;
    padding: 8px 16px 12px 16px;
}}

/* ===== 页面标题 ===== */
QLabel#pageTitle {{
    font-size: 22px;
    font-weight: bold;
    color: {TEXT_MAIN};
    padding: 8px 0 2px 0;
}}
QLabel#subtitleLabel {{
    color: {TEXT_SUB};
    font-size: 12px;
    padding-bottom: 10px;
}}

/* ===== 卡片 ===== */
QFrame#card, QWidget#card {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#cardTitle {{
    font-size: 15px;
    font-weight: bold;
    color: {TEXT_MAIN};
    padding: 4px 0;
}}

/* ===== 横幅（提示/警告）===== */
QWidget#banner {{
    background-color: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 10px;
}}
QLabel#bannerTitle {{
    font-size: 14px;
    font-weight: bold;
    color: {ACCENT_DARK};
    padding: 2px 0;
}}
QLabel#bannerText {{
    color: {TEXT_MAIN};
    font-size: 12px;
}}

/* ===== 输入控件 ===== */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QPlainTextEdit {{
    font-family: "Consolas", "Microsoft YaHei", monospace;
}}

/* ===== 按钮 ===== */
QPushButton {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
    color: {TEXT_MAIN};
}}
QPushButton:hover {{
    background-color: #f3f4f6;
    border-color: #d1d5db;
}}
QPushButton:pressed {{
    background-color: #e5e7eb;
}}
QPushButton:disabled {{
    color: #9ca3af;
    background-color: #f9fafb;
}}
QPushButton#primaryBtn {{
    background-color: {ACCENT};
    border: none;
    color: #ffffff;
    font-weight: bold;
    padding: 8px 22px;
}}
QPushButton#primaryBtn:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryBtn:disabled {{
    background-color: #93c5fd;
    color: #eff6ff;
}}
QPushButton#dangerBtn {{
    background-color: {DANGER};
    border: none;
    color: #ffffff;
}}
QPushButton#dangerBtn:hover {{
    background-color: #dc2626;
}}
QPushButton#successBtn {{
    background-color: {OK_GREEN};
    border: none;
    color: #ffffff;
}}
QPushButton#successBtn:hover {{
    background-color: #15803d;
}}

/* ===== 进度条 ===== */
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 5px;
    background-color: #f3f4f6;
    text-align: center;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}

/* ===== 表格 ===== */
QTableWidget {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
}}
QHeaderView::section {{
    background-color: #f9fafb;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: bold;
}}

/* ===== 分组框 ===== */
QGroupBox {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TEXT_MAIN};
}}

/* ===== 状态色标签 ===== */
QLabel#statusOk {{
    color: {OK_GREEN};
    font-weight: bold;
}}
QLabel#statusWarn {{
    color: {WARN};
    font-weight: bold;
}}
QLabel#statusError {{
    color: {DANGER};
    font-weight: bold;
}}

/* ===== 日志视图 ===== */
QPlainTextEdit#logView, QTextEdit#logView {{
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 8px;
    font-family: "Consolas", monospace;
    font-size: 12px;
}}

/* ===== 滚动条 ===== */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #d1d5db;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #9ca3af;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ===== 复选框 ===== */
QCheckBox {{
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
"""


def apply_style(app) -> None:
    """将全局样式应用到应用实例。"""
    app.setStyleSheet(_QSS)
