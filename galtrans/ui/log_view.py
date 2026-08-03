"""Minecraft 服务器风格的日志视图组件。

每条日志带 `[HH:MM:SS] [级别]` 前缀，按级别着色：
- INFO    白色（默认）
- WARN    黄色
- ERROR   红色
- DEBUG   灰色
"""

from datetime import datetime
from html import escape

from PySide6.QtWidgets import QTextEdit

# 级别颜色
_INFO_COLOR = "#e2e8f0"
_WARN_COLOR = "#facc15"
_ERROR_COLOR = "#f87171"
_DEBUG_COLOR = "#94a3b8"

# 级别前缀
_INFO = "INFO"
_WARN = "WARN"
_ERROR = "ERROR"
_DEBUG = "DEBUG"


def _stamp() -> str:
    """当前时间戳 [HH:MM:SS]。"""
    return datetime.now().strftime("[%H:%M:%S]")


def _render(level: str, color: str, message: str) -> str:
    """渲染一行带时间戳与级别前缀的 HTML。"""
    text = escape(message)
    return (
        f'<span style="color:{_DEBUG_COLOR}">{escape(_stamp())}</span> '
        f'<span style="color:{color};font-weight:bold;">[{level}]</span> '
        f'<span style="color:{color}">{text}</span>'
    )


class LogView(QTextEdit):
    """分级彩色日志视图。"""

    def __init__(self, max_blocks: int = 2000, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setObjectName("logView")
        self.document().setMaximumBlockCount(max_blocks)
        self.setAcceptRichText(True)
        # 等宽字体增强日志质感
        self.setStyleSheet(
            "QTextEdit#logView { font-family: 'Consolas', 'Courier New', monospace; }"
        )

    def info(self, message: str) -> None:
        """记录 INFO 级别日志。"""
        self._append(_INFO, _INFO_COLOR, message)

    def warn(self, message: str) -> None:
        """记录 WARN 级别日志。"""
        self._append(_WARN, _WARN_COLOR, message)

    def error(self, message: str) -> None:
        """记录 ERROR 级别日志。"""
        self._append(_ERROR, _ERROR_COLOR, message)

    def debug(self, message: str) -> None:
        """记录 DEBUG 级别日志。"""
        self._append(_DEBUG, _DEBUG_COLOR, message)

    def _append(self, level: str, color: str, message: str) -> None:
        """内部追加一行。"""
        self.append(_render(level, color, message))


__all__ = ["LogView"]
