"""「大图书馆」汉化工具入口

启动 GUI 主窗口。
"""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import Config
from .glossary import Glossary
from .ui import MainWindow
from .ui.style import apply_style


def _resolve_icon_path() -> str:
    """返回应用图标路径（打包环境或源码环境）。"""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidate = os.path.join(bundle_dir, "app.ico")
        if os.path.exists(candidate):
            return candidate
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "assets", "app.ico")


def main() -> None:
    """程序入口：初始化配置、样式与主窗口。"""
    app = QApplication(sys.argv)
    app.setApplicationName("大图书馆汉化工具")

    apply_style(app)

    icon_path = _resolve_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    config = Config()
    glossary = Glossary()
    window = MainWindow(config, glossary)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
