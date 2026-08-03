"""顶层入口脚本（PyInstaller 打包用）

必须使用绝对导入：打包后入口被当作顶层模块执行，
包内相对导入会报 ImportError: attempted relative import。
"""
from galtrans.main import main as run_app

if __name__ == "__main__":
    run_app()
