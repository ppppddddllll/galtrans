"""实时翻译悬浮窗模块。

参考网易云音乐桌面歌词悬浮窗风格：
- 细长横条，深色半透明渐变背景 + 亮色描边，居中显示
- 最新译文用大号加粗白色（当前"歌词"），历史用小号半透明白（类似前一句）
- 底部一条缓慢推进的细进度条装饰
- 支持拖拽移动、位置保存
- 右键菜单可实时调节背景透明度、字号、窗口大小、字体与文字颜色
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

# 位置选项常量
POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"

# 背景渐变配色常量
_BG_START = (15, 15, 20)
_BG_MID = (28, 28, 38)
_BG_END = (15, 15, 20)
_CORNER_RADIUS = 12

# 悬浮窗基准尺寸（被 scale 缩放）
_BASE_WIDTH = 900
_BASE_HEIGHT = 120

# 字体下拉可选列表
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
    """把 #rrggbb 颜色转为 rgba() 字符串。"""
    color = QColor(hex_color)
    if not color.isValid():
        color = QColor("#ffffff")
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _build_slider_action(
    menu: QMenu,
    title: str,
    value: int,
    vmin: int,
    vmax: int,
    on_change: Callable[[int], None],
) -> QWidgetAction:
    """在菜单中内嵌一个带标题与实时数值显示的滑块项。"""
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.setContentsMargins(8, 2, 8, 2)
    hbox = QHBoxLayout()
    hbox.addWidget(QLabel(title))
    value_label = QLabel(str(value))
    hbox.addWidget(value_label, 1)
    vbox.addLayout(hbox)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(vmin, vmax)
    slider.setValue(value)
    vbox.addWidget(slider)
    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)

    def _on_changed(v: int) -> None:
        value_label.setText(str(v))
        on_change(v)

    slider.valueChanged.connect(_on_changed)
    return action


def _build_combo_action(
    menu: QMenu,
    title: str,
    items: list[str],
    current: str,
    on_change: Callable[[str], None],
) -> QWidgetAction:
    """在菜单中内嵌一个带标题的下拉选择项。"""
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.setContentsMargins(8, 2, 8, 2)
    vbox.addWidget(QLabel(title))
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    combo.setCurrentText(current)
    vbox.addWidget(combo)
    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)
    combo.currentTextChanged.connect(on_change)
    return action


def _build_color_action(
    menu: QMenu,
    title: str,
    color_hex: str,
    on_pick: Callable[[str], None],
) -> QWidgetAction:
    """在菜单中内嵌一个可点击选择颜色的按钮项。"""
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.setContentsMargins(8, 2, 8, 2)
    vbox.addWidget(QLabel(title))
    button = QPushButton()
    button.setMinimumWidth(120)
    vbox.addWidget(button)

    def _apply_button(color: str) -> None:
        button.setText(color)
        button.setStyleSheet(
            f"background-color: {color}; color: #000000; border-radius: 4px;"
        )

    _apply_button(color_hex)
    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)

    def _on_clicked() -> None:
        initial = QColor(color_hex)
        color = QColorDialog.getColor(initial, menu, "选择文字颜色")
        if color.isValid():
            _apply_button(color.name())
            on_pick(color.name())

    button.clicked.connect(_on_clicked)
    return action


class OverlayWindow(QWidget):
    """网易云歌词风格的半透明置顶悬浮窗。

    参数:
        config: Config 实例，读取 overlay 段配置。
    """

    def __init__(self, config: Any) -> None:
        super().__init__(None)
        self._config = config
        # 无边框、置顶、工具窗（不占任务栏）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 用于窗口拖拽的状态
        self._drag_offset = None  # type: ignore[assignment]

        # 原文（小号半透明白，居中）
        self._original_label = QLabel(self)
        self._original_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_label.setWordWrap(True)
        self._original_label.setVisible(False)

        # 译文（富文本：最新大字加粗白色 + 历史小字）
        self._lyric_label = QLabel(self)
        self._lyric_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lyric_label.setWordWrap(True)
        self._lyric_label.setTextFormat(Qt.TextFormat.RichText)

        # 底部细进度条装饰（网易云歌词进度感）
        self._progress = QProgressBar(self)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(3)
        layout.addWidget(self._original_label)
        layout.addWidget(self._lyric_label, 1)
        layout.addWidget(self._progress)
        self.setLayout(layout)

        # 子控件不再接收鼠标事件，保证拖拽事件全部落到窗口上
        for child in (self._original_label, self._lyric_label, self._progress):
            child.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # 历史记录列表：译文
        self._history: list[str] = []
        self._apply_style()
        self._apply_position()
        self.hide()

        # 进度条缓慢推进动画
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_progress)
        self._timer.start(120)

    def _advance_progress(self) -> None:
        """让进度条缓慢推进，模拟歌词播放进度。"""
        value = self._progress.value() + 1
        if value >= 100:
            value = 0
        self._progress.setValue(value)

    def _apply_style(self) -> None:
        """根据配置应用字号、字体、文字颜色，并记录背景透明度。"""
        oconf = self._config.get("overlay") or {}
        opacity = float(oconf.get("opacity", 0.92))
        font_size = int(oconf.get("font_size", 16))
        font_family = oconf.get("font_family", "Microsoft YaHei")
        text_color = oconf.get("text_color", "#ffffff")

        # 背景透明度（0.0~1.0）存下供 paintEvent 绘制
        self._bg_alpha = int(255 * min(max(opacity, 0.0), 1.0))

        # 原文：小号半透明（使用当前文字颜色）
        original_font = QFont(font_family, max(11, font_size - 5))
        self._original_label.setFont(original_font)
        self._original_label.setStyleSheet(
            f"color: {_hex_to_rgba(text_color, 150)}; background: transparent;"
        )

        # 译文字号（大字版）与字体族、文字颜色
        self._font_family = font_family
        self._font_size = font_size
        self._text_color = text_color

        # 进度条样式：细横条
        self._progress.setStyleSheet(
            "QProgressBar { background: rgba(255, 255, 255, 35);"
            " border: none; border-radius: 1px; }"
            "QProgressBar::chunk { background: rgba(255, 255, 255, 170);"
            " border-radius: 1px; }"
        )

        # 字号/颜色变化后立即刷新译文富文本
        if self._history:
            self._lyric_label.setText(self._build_lyric_html(self._history))

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制圆角渐变背景与描边，保证悬浮窗始终有背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        # 深色横向渐变背景
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor(*_BG_START, self._bg_alpha))
        gradient.setColorAt(0.5, QColor(*_BG_MID, self._bg_alpha))
        gradient.setColorAt(1.0, QColor(*_BG_END, self._bg_alpha))
        painter.fillPath(path, gradient)

        # 亮色细描边
        pen = QPen(QColor(255, 255, 255, self._bg_alpha // 3))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def _build_lyric_html(self, history: list[str]) -> str:
        """把译文历史渲染为富文本：最新行大字加粗，历史行小号。"""
        size = self._font_size + 8
        small = max(11, self._font_size - 3)
        color = self._text_color if hasattr(self, "_text_color") else "#ffffff"
        parts = []
        for idx, line in enumerate(history):
            text = _html_escape(line)
            if idx == len(history) - 1:
                parts.append(
                    f'<span style="color:{color}; font-size:{size}px;'
                    f' font-weight:bold;">{text}</span>'
                )
            else:
                parts.append(
                    f'<span style="color:{_hex_to_rgba(color, 120)};'
                    f' font-size:{small}px;">{text}</span>'
                )
        return "<br>".join(parts)

    def _apply_position(self) -> None:
        """将窗口放到屏幕顶部或底部居中。

        窗口未显示时 self.screen() 可能为 None，改用主屏虚拟桌面兜底，
        避免悬浮窗显示在错误位置或不可见。
        """
        oconf = self._config.get("overlay") or {}
        position = oconf.get("position", POSITION_TOP)
        saved = oconf.get("window_pos")
        # 若保存过位置则恢复，否则用默认顶部/底部居中
        if saved and isinstance(saved, list) and len(saved) == 2:
            self.setGeometry(int(saved[0]), int(saved[1]), self.width(), self.height())
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        scale = float(oconf.get("scale", 1.0))
        width = int(min(geo.width() - 40, _BASE_WIDTH) * scale)
        height = int(_BASE_HEIGHT * scale)
        # 记录基准尺寸，供 _apply_scale 参考
        self._base_width = _BASE_WIDTH
        self._base_height = _BASE_HEIGHT
        x = geo.x() + (geo.width() - width) // 2
        if position == POSITION_BOTTOM:
            y = geo.y() + geo.height() - height - 30
        else:
            y = geo.y() + 30
        self.setGeometry(x, y, width, height)

    def show_translation(self, original: str, translated: str) -> None:
        """推送新的翻译结果，追加到历史记录。

        历史记录条数由配置 overlay.history_lines 决定，超出后丢弃最旧的。
        """
        oconf = self._config.get("overlay") or {}
        history_lines = int(oconf.get("history_lines", 3))
        self._history.append(translated)
        if len(self._history) > max(history_lines, 1):
            self._history.pop(0)

        # 原文（小字）有内容才显示
        if original:
            self._original_label.setText(original)
            self._original_label.setVisible(True)
        else:
            self._original_label.setVisible(False)

        self._lyric_label.setText(self._build_lyric_html(self._history))

        if not self.isVisible():
            self.show()
        # 确保悬浮窗在最上层，避免被游戏窗口遮挡
        self.raise_()
        self.activateWindow()

    def clear(self) -> None:
        """清空历史记录并隐藏窗口。"""
        self._history.clear()
        self._original_label.clear()
        self._lyric_label.clear()
        self._original_label.setVisible(False)
        self.hide()

    # ---- 拖拽移动 ----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        event.accept()

    # ---- 右键菜单调节 ----
    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键弹出调节菜单：透明度、字号、窗口大小、字体、文字颜色。"""
        oconf = self._config.get("overlay") or {}
        opacity = float(oconf.get("opacity", 0.92))
        font_size = int(oconf.get("font_size", 16))
        font_family = oconf.get("font_family", "Microsoft YaHei")
        text_color = oconf.get("text_color", "#ffffff")
        scale = float(oconf.get("scale", 1.0))

        menu = QMenu(self)

        def _set_opacity(v: int) -> None:
            self._config.set("overlay", "opacity", round(v / 100, 2))
            self._config.save()
            self._apply_style()
            self.update()

        def _set_font_size(v: int) -> None:
            self._config.set("overlay", "font_size", v)
            self._config.save()
            self._apply_style()

        def _set_scale(v: int) -> None:
            self._config.set("overlay", "scale", round(v / 100, 2))
            self._config.save()
            self._apply_scale()

        def _set_font_family(name: str) -> None:
            if not name:
                return
            self._config.set("overlay", "font_family", name)
            self._config.save()
            self._apply_style()

        def _set_text_color(hex_color: str) -> None:
            self._config.set("overlay", "text_color", hex_color)
            self._config.save()
            self._apply_style()

        _build_slider_action(menu, "背景透明度", int(opacity * 100), 20, 100, _set_opacity)
        _build_slider_action(menu, "字号", font_size, 10, 40, _set_font_size)
        _build_slider_action(menu, "窗口大小", int(scale * 100), 50, 150, _set_scale)

        # 字体下拉：合并系统字体与常用列表，避免重复
        system_fonts = QFontDatabase().families()
        choices = list(dict.fromkeys(_FONT_CHOICES + system_fonts))
        _build_combo_action(menu, "字体", choices, font_family, _set_font_family)

        _build_color_action(menu, "文字颜色", text_color, _set_text_color)

        menu.exec(event.globalPos())
        event.accept()

    def _apply_scale(self) -> None:
        """按配置的 scale 重新调整窗口大小（保持窗口中心不变）。"""
        oconf = self._config.get("overlay") or {}
        scale = float(oconf.get("scale", 1.0))
        base_w = getattr(self, "_base_width", _BASE_WIDTH)
        base_h = getattr(self, "_base_height", _BASE_HEIGHT)
        new_width = max(200, int(base_w * scale))
        new_height = max(60, int(base_h * scale))
        center = self.frameGeometry().center()
        self.setGeometry(
            center.x() - new_width // 2, center.y() - new_height // 2,
            new_width, new_height,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭时保存当前窗口位置到配置。"""
        try:
            self._config.set("overlay", "window_pos", [self.x(), self.y()])
            self._config.save()
        except Exception:
            pass
        super().closeEvent(event)

    @staticmethod
    def _color_from_rgba(rgba: list) -> QColor:
        """从 rgba 列表构造 QColor。"""
        r, g, b, a = rgba
        return QColor(r, g, b, a)
