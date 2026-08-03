"""主窗口

左侧导航栏 + 右侧页面堆叠：
- 离线汉化
- 实时翻译
- 术语表
- 设置
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import Config
from ..glossary import Glossary
from .glossary_page import GlossaryPage
from .offline_page import OfflinePage
from .realtime_page import RealtimePage
from .settings_page import SettingsPage

# 导航项：显示名 + 图标字符
PAGE_NAMES = ["离线汉化", "实时翻译", "术语表", "设置"]
PAGE_ICONS = ["📦", "🖥", "📖", "⚙️"]


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config: Config, glossary: Glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self.setWindowTitle("「大图书馆」汉化工具")
        self.resize(960, 680)
        self.setMinimumSize(800, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        """构建界面：左侧导航 + 右侧页面"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧导航
        nav_widget = QWidget()
        nav_widget.setObjectName("navWidget")
        nav_widget.setFixedWidth(180)
        nav = QVBoxLayout(nav_widget)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(0)

        title = QLabel("大图书馆")
        title.setObjectName("navTitle")
        nav.addWidget(title)

        self._nav_list = QListWidget()
        self._nav_list.setObjectName("navList")
        for name, icon in zip(PAGE_NAMES, PAGE_ICONS):
            item = QListWidgetItem(f"{icon}  {name}")
            item.setSizeHint(item.sizeHint())
            self._nav_list.addItem(item)
        self._nav_list.currentRowChanged.connect(self._switch_page)
        nav.addWidget(self._nav_list, 1)

        version_label = QLabel(f"v{__version__}")
        version_label.setObjectName("versionLabel")
        version_label.setAlignment(Qt.AlignCenter)
        nav.addWidget(version_label)

        layout.addWidget(nav_widget)

        # 右侧页面堆叠
        self._stack = QStackedWidget()
        self._offline_page = OfflinePage(self._config, self._glossary)
        self._realtime_page = RealtimePage(self._config, self._glossary)
        self._glossary_page = GlossaryPage(self._config, self._glossary)
        self._settings_page = SettingsPage(self._config)
        self._stack.addWidget(self._offline_page)
        self._stack.addWidget(self._realtime_page)
        self._stack.addWidget(self._glossary_page)
        self._stack.addWidget(self._settings_page)
        layout.addWidget(self._stack, 1)

        # 离线页「前往设置」跳转
        self._offline_page.goto_settings.connect(self._goto_settings)

        self._nav_list.setCurrentRow(0)

    def _goto_settings(self) -> None:
        """跳转到设置页"""
        self._nav_list.setCurrentRow(self._stack.indexOf(self._settings_page))

    def _switch_page(self, row: int) -> None:
        """切换页面"""
        if 0 <= row < self._stack.count():
            self._stack.setCurrentIndex(row)
