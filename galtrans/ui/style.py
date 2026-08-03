"""全局样式表

提供统一现代简洁风格，参考同类工具（LunaTranslator 等）的清爽配色：
- 浅色背景 + 强调色（蓝色系）
- 圆角卡片、柔和阴影、hover 反馈
- 统一字号与控件间距
"""
from __future__ import annotations

# 主题强调色
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_DARK = "#1d4ed8"

# 背景与前景
BG = "#f5f7fa"
CARD_BG = "#ffffff"
TEXT_MAIN = "#1f2937"
TEXT_SUB = "#6b7280"
BORDER = "#e5e7eb"
DANGER = "#ef4444"
OK_GREEN = "#16a34a"
WARN = "#d97706"

QSS = f"""
* {{
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT_MAIN};
}}

QWidget {{
    background: {BG};
}}

/* ---------- 导航栏 ---------- */
#navWidget {{
    background: {CARD_BG};
    border-right: 1px solid {BORDER};
}}

#navTitle {{
    font-size: 15px;
    font-weight: bold;
    color: {ACCENT_DARK};
    padding: 16px 14px 10px 14px;
    background: transparent;
}}

#navList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}}

#navList::item {{
    height: 40px;
    border-radius: 8px;
    padding-left: 14px;
    color: {TEXT_SUB};
    margin: 2px 6px;
}}

#navList::item:hover {{
    background: #eef2ff;
    color: {ACCENT_DARK};
}}

#navList::item:selected {{
    background: {ACCENT};
    color: white;
    font-weight: bold;
}}

#versionLabel {{
    color: {TEXT_SUB};
    font-size: 12px;
    padding: 8px;
    background: transparent;
}}

/* ---------- 页面通用 ---------- */
#pageTitle {{
    font-size: 18px;
    font-weight: bold;
    color: {TEXT_MAIN};
    background: transparent;
}}

#subtitleLabel {{
    color: {TEXT_SUB};
    background: transparent;
}}

#card {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

#cardTitle {{
    font-size: 14px;
    font-weight: bold;
    color: {TEXT_MAIN};
    background: transparent;
    padding-bottom: 6px;
}}

#banner {{
    border-radius: 8px;
    padding: 10px 14px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
}}

#bannerTitle {{
    font-weight: bold;
    color: {ACCENT_DARK};
    background: transparent;
}}

#bannerText {{
    color: {TEXT_MAIN};
    background: transparent;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}

QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}

QPlainTextEdit, QTextEdit {{
    font-family: "Consolas", "Microsoft YaHei", monospace;
    background: {CARD_BG};
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 16px;
}}

QPushButton:hover {{
    background: #f3f4f6;
    border-color: #d1d5db;
}}

QPushButton:pressed {{
    background: #e5e7eb;
}}

QPushButton:disabled {{
    color: #9ca3af;
    background: #f3f4f6;
}}

QPushButton#primaryBtn {{
    background: {ACCENT};
    border: none;
    color: white;
    font-weight: bold;
    padding: 8px 24px;
}}

QPushButton#primaryBtn:hover {{
    background: {ACCENT_HOVER};
}}

QPushButton#primaryBtn:pressed {{
    background: {ACCENT_DARK};
}}

QPushButton#primaryBtn:disabled {{
    background: #bfdbfe;
    color: #eff6ff;
}}

QPushButton#dangerBtn {{
    color: {DANGER};
    border-color: #fca5a5;
}}

QPushButton#dangerBtn:hover {{
    background: #fef2f2;
}}

QPushButton#successBtn {{
    color: {OK_GREEN};
    border-color: #86efac;
}}

QPushButton#successBtn:hover {{
    background: #f0fdf4;
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: #e5e7eb;
    border: none;
    border-radius: 6px;
    text-align: center;
    height: 16px;
    color: {TEXT_MAIN};
}}

QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 6px;
}}

/* ---------- 表格 ---------- */
QTableWidget {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
}}

QTableWidget::item {{
    padding: 6px 8px;
}}

QTableWidget::item:selected {{
    background: #dbeafe;
    color: {TEXT_MAIN};
}}

QHeaderView::section {{
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px;
    font-weight: bold;
    color: {TEXT_SUB};
}}

/* ---------- 复选框 ---------- */
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD_BG};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ---------- 分组框 ---------- */
QGroupBox {{
    font-weight: bold;
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    background: {CARD_BG};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {ACCENT_DARK};
    background: transparent;
}}

/* ---------- 滚动区 ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ---------- 状态标签 ---------- */
#statusOk {{
    color: {OK_GREEN};
    font-weight: bold;
    background: transparent;
}}

#statusWarn {{
    color: {WARN};
    font-weight: bold;
    background: transparent;
}}

#statusError {{
    color: {DANGER};
    font-weight: bold;
    background: transparent;
}}

#logView {{
    background: #111827;
    color: #e5e7eb;
    border-radius: 8px;
    border: none;
}}
"""


def apply_style(app) -> None:
    """将全局样式应用到 QApplication"""
    app.setStyleSheet(QSS)
