# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（目录模式）

自 v0.2 起支持本地模型（torch/transformers），体积较大，改回目录模式。
打包命令：
    python -X utf8 -m PyInstaller build.spec --noconfirm --distpath dist --workpath build
"""
from PyInstaller.utils.hooks import collect_all

# 收集 winrt 命名空间下全部二进制（OCR 依赖）
winrt_datas, winrt_binaries, winrt_hidden = collect_all("winrt")

# 排除用不到的 Qt 模块以减小体积
_EXCLUDE_QT = [
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtConcurrent",
    "PySide6.QtQmlModels",
    "PySide6.QtQuickWidgets",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=winrt_binaries,
    datas=[("assets/app.ico", ".")] + winrt_datas,
    hiddenimports=[
        "winrt.system",
        "winrt.runtime",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.globalization",
        "winrt.windows.graphics.imaging",
        "winrt.windows.media.ocr",
        "winrt.windows.storage",
        "winrt.windows.storage.streams",
    ]
    + winrt_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torchvision",
        "torchaudio",
        "frida",
        "frida_tools",
        "pytest",
        "numpy",
        "numpy.libs",
    ]
    + _EXCLUDE_QT,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="大图书馆汉化工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_multi.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="大图书馆汉化工具",
)
