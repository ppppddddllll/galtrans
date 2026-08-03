# -*- mode: python ; coding: utf-8 -*-
"""Galgame 一键汉化工具打包配置（onefile 单文件模式 + 瘦身）

用法:
    pyinstaller build.spec --noconfirm --distpath dist --workpath build

瘦身策略:
    - 排除 PySide6 用不到的 Qt 模块（Quick/Qml/Pdf/OpenGL/Network）
    - 排除 numpy（PIL 的可选依赖，本程序只用 ImageGrab 不涉及数组）
    - winrt 仅收集 OCR 实际用到的子包
"""
from PyInstaller.utils.hooks import collect_all

# 收集 winrt 命名空间包（含 .pyd 二进制、system/runtime/windows 子包）
winrt_datas, winrt_binaries, winrt_hidden = collect_all("winrt")

# PySide6 只保留实际用到的模块，排除体积大且无用的 Qt 模块
# （QtWidgets 运行仅需 Core/Gui/Widgets + 平台插件）
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
    datas=winrt_datas + [("assets/app.ico", ".")],
    hiddenimports=[
        *winrt_hidden,
        "winrt.system",
        "winrt.runtime",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.globalization",
        "winrt.windows.graphics.imaging",
        "winrt.windows.media.ocr",
        "winrt.windows.storage",
        "winrt.windows.storage.streams",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchvision",
        "torchaudio",
        "frida",
        "frida_tools",
        "pytest",
        "numpy",
        "numpy.libs",
        *_EXCLUDE_QT,
    ],
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/app_multi.ico",
)
