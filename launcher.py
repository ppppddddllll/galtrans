"""顶层启动入口（供 PyInstaller 打包与直接运行）

PyInstaller 会把该文件作为顶层脚本（__main__）执行，
因此这里必须用绝对导入加载 galtrans 包，避免相对导入报错。

用法：
    python launcher.py
"""
from __future__ import annotations

import sys


def main() -> int:
    """启动 GUI"""
    from galtrans.main import main as run_app

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
