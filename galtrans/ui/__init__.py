"""GUI 界面包

包含主窗口、离线汉化页、实时翻译页、术语表页、设置页、悬浮窗
与 OCR 语言包引导对话框。
"""
from .language_guide import LanguageGuideDialog
from .main_window import MainWindow
from .overlay import OverlayWindow

__all__ = ["MainWindow", "OverlayWindow", "LanguageGuideDialog"]
