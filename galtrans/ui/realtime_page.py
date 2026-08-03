"""实时翻译页面

功能：
- 框选屏幕区域（OCR 识别范围）
- 启动/停止实时翻译循环
- 显示原文与译文，或推送到置顶悬浮窗
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import ocr
from ..realtime import RealtimeSession
from ..translate import TranslationManager
from ..translate.manager import ENGINE_REGISTRY
from .language_guide import LanguageGuideDialog
from .overlay import OverlayWindow

# 引擎下拉框显示名
_ENGINE_LABELS = {
    "bing": "Bing（最快，免 Key）",
    "google": "Google（免 Key）",
    "deepl": "DeepL（需 Key）",
    "deepseek": "DeepSeek（最准，需 Key）",
}


class _RegionSelector(QWidget):
    """全屏半透明遮罩，供用户拖拽框选屏幕区域。

    发出 region_selected 信号：(left, top, right, bottom)（物理像素）。
    """

    region_selected = Signal(tuple)

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._start: QPoint | None = None
        self._end: QPoint | None = None

    def show_and_select(self) -> None:
        """显示并进入框选状态（覆盖整个虚拟桌面，兼容多显示器）。"""
        # 窗口未显示前 self.screen() 可能为 None，直接用主屏的虚拟桌面几何
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        # 使用整个虚拟桌面的几何区域，避免副屏无法框选
        self.setGeometry(screen.virtualGeometry())
        self.show()

    def _to_logical(self, global_pos: QPoint) -> QPoint:
        """将全局（物理）坐标转为窗口局部（逻辑）坐标。"""
        return self.mapFromGlobal(global_pos)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._end = self._start
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self._end = event.globalPosition().toPoint()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self._end = event.globalPosition().toPoint()
            # 将 Qt 逻辑坐标转换为屏幕物理坐标（乘鼠标所在屏幕的 DPI 缩放比）
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen is not None else 1.0
            left = min(self._start.x(), self._end.x()) * dpr
            top = min(self._start.y(), self._end.y()) * dpr
            right = max(self._start.x(), self._end.x()) * dpr
            bottom = max(self._start.y(), self._end.y()) * dpr
            # 转成整数边界（右/下取整避免截取少 1 像素）
            self.region_selected.emit(
                (int(left), int(top), int(right) + 1, int(bottom) + 1)
            )
        self._start = None
        self._end = None
        self.close()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制半透明遮罩与选框（坐标用窗口局部坐标系）。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        if self._start is not None and self._end is not None:
            # 全局坐标转局部坐标再绘制
            rect = QRect(
                self.mapFromGlobal(self._start),
                self.mapFromGlobal(self._end),
            ).normalized()
            painter.setPen(QPen(QColor(0, 200, 255), 2))
            painter.drawRect(rect)
            # 在选框内挖空，便于看清游戏内容
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
        painter.end()


class RealtimePage(QWidget):
    """实时翻译页面"""

    # 跨线程信号：后台线程通过 emit 通知 GUI 线程更新界面
    result_ready = Signal(str, str)    # (原文, 译文)
    status_ready = Signal(str)         # 状态消息

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._session: RealtimeSession | None = None
        self._thread: threading.Thread | None = None
        self._region: tuple | None = None
        self._overlay: OverlayWindow | None = None
        self._selector: _RegionSelector | None = None
        self._build_ui()
        # 信号默认在主线程触发，跨线程 emit 自动排到 GUI 线程
        self.result_ready.connect(self._on_result)
        self.status_ready.connect(self._on_status)

    def _build_ui(self) -> None:
        """构建界面布局"""
        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 16, 20, 16)

        # 页面标题与说明
        title = QLabel("实时翻译")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        subtitle = QLabel("适用于任意游戏：框选游戏文字区域，OCR 识别后实时翻译，可叠加置顶悬浮窗。")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        # OCR 语言状态横幅
        self._ocr_banner = QWidget()
        self._ocr_banner.setObjectName("banner")
        banner_layout = QHBoxLayout(self._ocr_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self._ocr_status = QLabel()
        self._ocr_status.setObjectName("bannerTitle")
        self._guide_btn = QPushButton("日语 OCR 引导")
        self._guide_btn.setObjectName("successBtn")
        self._guide_btn.clicked.connect(self._open_guide)
        self._retest_btn = QPushButton("重新检测")
        self._retest_btn.clicked.connect(self._refresh_ocr_status)
        banner_layout.addWidget(self._ocr_status, 1)
        banner_layout.addWidget(self._retest_btn)
        banner_layout.addWidget(self._guide_btn)
        outer.addWidget(self._ocr_banner)
        self._refresh_ocr_status()

        # 顶部：区域选择与开关
        top = QHBoxLayout()
        self._region_btn = QPushButton("框选屏幕区域")
        self._region_btn.clicked.connect(self._pick_region)
        self._region_label = QLabel("未选择区域")
        # 引擎选择（实时翻译独立配置）
        self._engine_combo = QComboBox()
        for name, label in _ENGINE_LABELS.items():
            self._engine_combo.addItem(label, name)
        rt_conf = self._config.get("realtime") or {}
        saved_engine = rt_conf.get("engine", "bing")
        idx = self._engine_combo.findData(saved_engine)
        if idx >= 0:
            self._engine_combo.setCurrentIndex(idx)
        self._start_btn = QPushButton("开始翻译")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._toggle_session)
        self._overlay_check = QCheckBox("显示悬浮窗")
        self._overlay_check.setChecked(True)
        self._overlay_check.toggled.connect(self._toggle_overlay)
        top.addWidget(self._region_btn)
        top.addWidget(self._region_label, 1)
        top.addWidget(QLabel("引擎"))
        top.addWidget(self._engine_combo)
        top.addWidget(self._start_btn)
        top.addWidget(self._overlay_check)
        outer.addLayout(top)

        # 文本显示区：左原文右译文
        text_row = QGridLayout()
        text_row.setHorizontalSpacing(8)
        self._original_view = QPlainTextEdit()
        self._original_view.setReadOnly(True)
        self._original_view.setPlaceholderText("OCR 原文将显示在这里")
        self._translated_view = QPlainTextEdit()
        self._translated_view.setReadOnly(True)
        self._translated_view.setPlaceholderText("翻译结果将显示在这里")
        text_row.addWidget(QLabel("原文"), 0, 0)
        text_row.addWidget(QLabel("译文"), 0, 1)
        text_row.addWidget(self._original_view, 1, 0)
        text_row.addWidget(self._translated_view, 1, 1)
        outer.addLayout(text_row, 1)

        # 状态日志
        self._status_label = QLabel("就绪")
        outer.addWidget(self._status_label)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("logView")
        self._log.setMaximumBlockCount(1000)
        outer.addWidget(self._log, 0)

    # ---------- OCR 状态 ----------

    def _refresh_ocr_status(self) -> None:
        """刷新 OCR 语言状态横幅"""
        status = ocr.detect_ocr_status()
        if status["ja_available"]:
            self._ocr_status.setText("✓ 日语 OCR 引擎已就绪")
            self._guide_btn.setObjectName("successBtn")
            self._guide_btn.setText("日语 OCR 引导")
        else:
            current = status["current_lang"]
            if current == "none":
                self._ocr_status.setText("✗ 未检测到任何 OCR 语言，实时翻译不可用，请安装日语语言包")
            else:
                self._ocr_status.setText(f"⚠ 未安装日语 OCR（当前回退：{current}），识别效果有限，建议安装日语语言包")
            self._guide_btn.setObjectName("dangerBtn")
            self._guide_btn.setText("查看安装引导")
        # 触发样式刷新
        self._ocr_banner.setStyleSheet("")
        self._ocr_status.setStyleSheet("")

    def _open_guide(self) -> None:
        """打开语言包安装引导对话框"""
        dialog = LanguageGuideDialog(self)
        dialog.exec()

    def _pick_region(self) -> None:
        """弹出全屏遮罩让用户框选区域。"""
        self._selector = _RegionSelector()
        self._selector.region_selected.connect(self._on_region_selected)
        self._selector.show_and_select()

    def _on_region_selected(self, region: tuple) -> None:
        """收到框选结果。"""
        self._region = region
        left, top, right, bottom = region
        self._region_label.setText(f"区域 ({left}, {top}) - ({right}, {bottom})")
        self._start_btn.setEnabled(True)
        self._log_append(f"已选择区域: {region}")

    def _toggle_session(self) -> None:
        """启动或停止实时翻译会话。"""
        if self._session is None:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self) -> None:
        """启动实时翻译线程。"""
        if self._region is None:
            return
        ocr_conf = self._config.get("ocr") or {}
        interval = float(ocr_conf.get("interval", 0.8))

        # 保存本次选择的引擎（实时翻译独立配置）
        engine_name = self._engine_combo.currentData() or "bing"
        self._config.set("realtime", "engine", engine_name)

        # 用指定引擎构建翻译器（仅该引擎，不降级到离线配置）
        translator = TranslationManager(
            self._config, self._glossary, engine_names=[engine_name]
        )
        self._session = RealtimeSession(
            translator,
            self._region,
            interval=interval,
            on_result=self.result_ready.emit,
            on_status=self.status_ready.emit,
        )
        self._thread = threading.Thread(target=self._session.run, daemon=True)
        self._start_btn.setText("停止翻译")
        self._region_btn.setEnabled(False)
        self._engine_combo.setEnabled(False)
        self._log_append(f"实时翻译启动（引擎：{engine_name}）")
        self._thread.start()

    def _stop_session(self) -> None:
        """停止实时翻译线程。"""
        if self._session is not None:
            self._session.request_stop()
            self._session = None
            self._thread = None
        self._start_btn.setText("开始翻译")
        self._region_btn.setEnabled(True)
        self._engine_combo.setEnabled(True)
        self._log_append("实时翻译已请求停止")

    def _on_result(self, original: str, translated: str) -> None:
        """收到新译文：更新界面并推送悬浮窗。"""
        self._original_view.setPlainText(original)
        self._translated_view.setPlainText(translated)
        if self._overlay_check.isChecked():
            if self._overlay is None:
                self._overlay = OverlayWindow(self._config)
            self._overlay.show_translation(original, translated)

    def _on_status(self, message: str) -> None:
        """状态消息更新。"""
        self._status_label.setText(message)
        self._log_append(message)

    def _toggle_overlay(self, checked: bool) -> None:
        """开关悬浮窗。"""
        if checked:
            if self._overlay is None:
                self._overlay = OverlayWindow(self._config)
            self._overlay.show()
        else:
            if self._overlay is not None:
                self._overlay.hide()

    def _log_append(self, text: str) -> None:
        """追加一行日志。"""
        self._log.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        """页面关闭前停止会话并清理悬浮窗。"""
        self._stop_session()
        if self._overlay is not None:
            self._overlay.close()
        super().closeEvent(event)
