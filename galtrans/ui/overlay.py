"""网易云音乐歌词风格悬浮窗。

细长横条 + 深色渐变半透明背景 + 原文小字 + 译文大字 + 进度条。
支持拖动、右键菜单调节（透明度/字号/大小/字体/文字颜色）。
"""
from __future__ import annotations

from html import escape as _html_escape

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QLabel,
    QMenu,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

# 位置常量
POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"

# 渐变背景色（深色）
_BG_START = (15, 15, 20)
_BG_MID = (28, 28, 38)
_BG_END = (15, 15, 20)
_CORNER_RADIUS = 12

# 基准尺寸
_BASE_WIDTH = 560
_BASE_HEIGHT = 100

# 可选字体列表
_FONT_CHOICES = [
    "Microsoft YaHei",
    "微软雅黑",
    "SimHei",
    "SimSun",
    "DengXian",
    "Arial",
    "Segoe UI",
    "Noto Sans CJK SC",
]


def _hex_to_rgba(hex_color: str, alpha: int) -> str:
    """十六进制颜色转 rgba 字符串，无效时回退白色。"""
    color = QColor(hex_color)
    if not color.isValid():
        color = QColor("#ffffff")
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _build_slider_action(
    menu: QMenu, title: str, value: int, vmin: int, vmax: int, on_change
) -> QAction:
    """构建带实时数值显示的滑块菜单项。"""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider

    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(12, 4, 12, 4)
    title_label = QLabel(title)
    value_label = QLabel(str(value))
    slider = QSlider(Qt.Horizontal)
    slider.setRange(vmin, vmax)
    slider.setValue(value)
    slider.valueChanged.connect(lambda v: (value_label.setText(str(v)), on_change(v)))
    row.addWidget(title_label)
    row.addWidget(slider, 1)
    row.addWidget(value_label)

    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    return action


def _build_combo_action(
    menu: QMenu, title: str, items: list[str], current: str, on_change
) -> QAction:
    """构建字体选择菜单项（可编辑下拉框）。"""
    from PySide6.QtWidgets import QHBoxLayout, QLabel

    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(12, 4, 12, 4)
    row.addWidget(QLabel(title))
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    if current in items:
        combo.setCurrentText(current)
    combo.currentTextChanged.connect(on_change)
    combo.setMinimumWidth(200)
    row.addWidget(combo, 1)

    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    return action


def _build_color_action(menu: QMenu, title: str, color_hex: str, on_pick) -> QAction:
    """构建颜色选择菜单项。"""
    from PySide6.QtWidgets import QHBoxLayout, QLabel

    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(12, 4, 12, 4)
    row.addWidget(QLabel(title))
    btn = QPushButton("选择颜色...")
    btn.clicked.connect(lambda: on_pick())
    row.addWidget(btn, 1)

    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    return action


class OverlayWindow(QWidget):
    """网易云歌词风格悬浮窗。"""

    # 请求停止实时翻译（右键菜单「停止翻译」触发）
    stop_requested = Signal()

    def __init__(self, config) -> None:
        super().__init__()
        self._config = config
        self._history: list[str] = []
        self._drag_offset = None
        self._base_width = _BASE_WIDTH
        self._base_height = _BASE_HEIGHT

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_widgets()
        self._apply_style()
        self._apply_position()
        self.hide()

        # 歌词进度条动画
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_progress)
        self._timer.start(120)

    def _build_widgets(self) -> None:
        """构建子控件。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(3)

        # 译文为标题（大号，在上），原文为副标题（小号，在下）
        self._lyric_label = QLabel()
        self._lyric_label.setAlignment(Qt.AlignCenter)
        self._lyric_label.setTextFormat(Qt.RichText)
        self._lyric_label.setWordWrap(True)

        self._original_label = QLabel()
        self._original_label.setAlignment(Qt.AlignCenter)
        self._original_label.hide()

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)

        layout.addWidget(self._lyric_label, 1)
        layout.addWidget(self._original_label)
        layout.addWidget(self._progress)

        # 让子控件不拦截鼠标事件，保证拖拽生效
        for child in (self._original_label, self._lyric_label, self._progress):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            child.setFocusPolicy(Qt.NoFocus)

    def _apply_style(self) -> None:
        """从配置读取样式并应用。"""
        oconf = self._config.get("overlay") or {}
        opacity = float(oconf.get("opacity", 0.92))
        self._bg_alpha = int(255 * max(0.0, min(1.0, opacity)))
        self._font_size = int(oconf.get("font_size", 16))
        self._font_family = oconf.get("font_family", "Microsoft YaHei")
        self._text_color = oconf.get("text_color", "#ffffff")

        font = QFont(self._font_family)
        font.setPointSize(max(11, self._font_size - 5))
        self._original_label.setFont(font)
        self._original_label.setStyleSheet(
            f"color: {_hex_to_rgba(self._text_color, 150)}; background: transparent;"
        )

        self._progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,{self._bg_alpha // 6}); border: none; }}"
            f"QProgressBar::chunk {{ background: rgba(255,255,255,{self._bg_alpha // 2}); }}"
        )

        if self._history:
            self._lyric_label.setText(self._build_lyric_html(self._history))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制圆角渐变背景与描边。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            self.rect().adjusted(0.5, 0.5, -0.5, -0.5),
            _CORNER_RADIUS,
            _CORNER_RADIUS,
        )
        from PySide6.QtGui import QLinearGradient

        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(*_BG_START, self._bg_alpha))
        grad.setColorAt(0.5, QColor(*_BG_MID, self._bg_alpha))
        grad.setColorAt(1.0, QColor(*_BG_END, self._bg_alpha))
        painter.fillPath(path, grad)
        painter.setPen(QPen(QColor(255, 255, 255, self._bg_alpha // 3), 1))
        painter.drawPath(path)

    def _build_lyric_html(self, history: list[str]) -> str:
        """把历史译文拼成歌词 HTML（最新行高亮）。"""
        if not history:
            return ""
        latest = history[-1]
        older = history[:-1]
        parts = []
        for line in older:
            color = _hex_to_rgba(self._text_color, 120)
            size = max(11, self._font_size - 3)
            parts.append(f'<span style="color:{color}; font-size:{size}px;">{_html_escape(line)}</span>')
        color = self._text_color
        size = self._font_size + 8
        parts.append(f'<span style="color:{color}; font-size:{size}px; font-weight:bold;">{_html_escape(latest)}</span>')
        return "<br>".join(parts)

    def _apply_position(self) -> None:
        """根据配置定位窗口。"""
        oconf = self._config.get("overlay") or {}
        scale = float(oconf.get("scale", 1.0))
        saved_pos = oconf.get("window_pos")
        if isinstance(saved_pos, list) and len(saved_pos) == 2:
            x, y = self._clamp_to_screen(
                int(saved_pos[0]), int(saved_pos[1]), self.width(), self.height()
            )
            self.setGeometry(x, y, self.width(), self.height())
            return

        from PySide6.QtGui import QGuiApplication

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self._base_width = _BASE_WIDTH
        self._base_height = _BASE_HEIGHT
        width = int(min(geo.width() - 40, _BASE_WIDTH) * scale)
        height = int(min(geo.height() - 40, _BASE_HEIGHT) * scale)
        x = geo.x() + (geo.width() - width) // 2
        position = oconf.get("position", "top")
        if position == POSITION_BOTTOM:
            y = geo.y() + geo.height() - height - 30
        else:
            y = geo.y() + 30
        self.setGeometry(x, y, width, height)

    def _apply_scale(self) -> None:
        """按缩放比例重设窗口大小（保持中心，且不越出屏幕）。"""
        oconf = self._config.get("overlay") or {}
        scale = float(oconf.get("scale", 1.0))
        center = self.frameGeometry().center()
        width = max(200, int(self._base_width * scale))
        height = max(60, int(self._base_height * scale))
        # 尺寸钳制：窗口不能大于屏幕可用区
        from PySide6.QtGui import QGuiApplication

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            width = min(width, geo.width() - 20)
            height = min(height, geo.height() - 20)
            width = max(200, width)
            height = max(60, height)
        x = center.x() - width // 2
        y = center.y() - height // 2
        x, y = self._clamp_to_screen(x, y, width, height)
        self.setGeometry(x, y, width, height)

    def _clamp_to_screen(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """把窗口位置钳制在当前屏幕可用区域内，避免飞出屏幕。"""
        from PySide6.QtGui import QGuiApplication

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return x, y
        geo = screen.availableGeometry()
        max_x = geo.x() + max(0, geo.width() - width)
        max_y = geo.y() + max(0, geo.height() - height)
        return max(geo.x(), min(x, max_x)), max(geo.y(), min(y, max_y))

    def show_translation(self, original: str, translated: str) -> None:
        """显示新的翻译结果。"""
        oconf = self._config.get("overlay") or {}
        history_lines = int(oconf.get("history_lines", 3))
        self._history.append(translated)
        if len(self._history) > history_lines:
            self._history = self._history[-history_lines:]

        if original.strip():
            self._original_label.setText(original)
            self._original_label.show()
        else:
            self._original_label.hide()

        self._lyric_label.setText(self._build_lyric_html(self._history))
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()

    def clear(self) -> None:
        """清空内容并隐藏。"""
        self._history.clear()
        self._original_label.clear()
        self._original_label.hide()
        self._lyric_label.clear()
        self.hide()

    def _advance_progress(self) -> None:
        """推进进度条（模拟歌词进度）。"""
        value = self._progress.value() + 1
        if value >= 100:
            value = 0
        self._progress.setValue(value)

    # ---------- 拖拽移动 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None

    # ---------- 右键调节菜单 ----------

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        oconf = self._config.get("overlay") or {}
        menu = QMenu(self)

        # 停止翻译入口（实时翻译时主窗口可能被最小化）
        stop_action = menu.addAction("⏹ 停止翻译")
        stop_action.triggered.connect(self.stop_requested.emit)
        menu.addSeparator()

        def _set(section: str, key: str, value) -> None:
            self._config.set(section, key, value)

        menu.addAction(
            _build_slider_action(
                menu,
                "背景透明度",
                int(float(oconf.get("opacity", 0.92)) * 100),
                20,
                100,
                lambda v: (
                    _set("overlay", "opacity", round(v / 100, 2)),
                    self._apply_style(),
                ),
            )
        )
        menu.addAction(
            _build_slider_action(
                menu,
                "字号",
                int(oconf.get("font_size", 16)),
                10,
                40,
                lambda v: (
                    _set("overlay", "font_size", v),
                    self._apply_style(),
                ),
            )
        )
        menu.addAction(
            _build_slider_action(
                menu,
                "窗口大小",
                int(float(oconf.get("scale", 1.0)) * 100),
                50,
                150,
                lambda v: (
                    _set("overlay", "scale", round(v / 100, 2)),
                    self._apply_scale(),
                ),
            )
        )

        families = _FONT_CHOICES + sorted(set(QFontDatabase().families()))
        seen = set()
        families = [f for f in families if not (f in seen or seen.add(f))]
        menu.addAction(
            _build_combo_action(
                menu,
                "字体",
                families,
                oconf.get("font_family", "Microsoft YaHei"),
                lambda f: (
                    _set("overlay", "font_family", f),
                    self._apply_style(),
                ),
            )
        )
        menu.addAction(
            _build_color_action(
                menu,
                "文字颜色",
                oconf.get("text_color", "#ffffff"),
                lambda: self._pick_color(oconf.get("text_color", "#ffffff")),
            )
        )
        menu.exec(event.globalPos())

    def _pick_color(self, current: str) -> None:
        """弹出颜色选择器。"""
        color = QColorDialog.getColor(
            QColor(current), self, "选择文字颜色", QColorDialog.ShowAlphaChannel
        )
        if color.isValid():
            self._config.set("overlay", "text_color", color.name())
            self._apply_style()

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭时保存窗口位置。"""
        pos = (self.x(), self.y())
        self._config.set("overlay", "window_pos", list(pos))
        super().closeEvent(event)

    @staticmethod
    def _color_from_rgba(rgba: str) -> str:
        """rgba(...) 字符串转十六进制颜色（兼容旧配置）。"""
        try:
            inner = rgba.strip().split("(", 1)[1].rstrip(")")
            parts = [int(p) for p in inner.split(",")[:3]]
            return "#{:02x}{:02x}{:02x}".format(*parts)
        except Exception:  # noqa: BLE001
            return "#ffffff"
