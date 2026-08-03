"""程序入口

用法：python -m galtrans
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
    """定位应用图标文件路径。

    打包环境下图标与可执行文件同目录；源码运行环境下在 assets/ 下。
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return os.path.join(bundle_dir, "app.ico")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico")


def main() -> int:
    """启动 GUI 应用"""
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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
