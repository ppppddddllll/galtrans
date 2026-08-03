"""实时翻译页：框选区域 + 选择引擎 + 开始/停止 + 悬浮窗显示。"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import ocr
from ..realtime import RealtimeSession
from ..translate.local_model import is_model_downloaded
from ..translate.manager import TranslationManager
from .language_guide import LanguageGuideDialog
from .log_view import LogView
from .overlay import OverlayWindow

# 引擎选项（显示名 → 引擎名）
_ENGINE_LABELS = {
    "local": "本地模型（离线最快）",
    "bing": "Bing（最快，免 Key）",
    "google": "Google（免 Key）",
    "deepl": "DeepL（需 Key）",
    "deepseek": "DeepSeek（最准，需 Key）",
}


class _RegionSelector(QWidget):
    """全屏半透明遮罩，拖拽框选区域。"""

    region_selected = Signal(tuple)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._start = None
        self._end = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

    def show_and_select(self) -> None:
        """显示并进入框选状态（覆盖整个虚拟桌面，兼容多显示器）。"""
        # 窗口未显示前 self.screen() 可能为 None，直接用主屏的虚拟桌面几何
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        # 使用整个虚拟桌面的几何区域，避免副屏无法框选
        self.setGeometry(screen.virtualGeometry())
        self.show()
        # 确保置顶激活，能接收鼠标事件
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc 取消框选。"""
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制遮罩与选框。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        if self._start is not None and self._end is not None:
            start = self.mapFromGlobal(self._start)
            end = self.mapFromGlobal(self._end)
            rect = QRect(start, end).normalized()
            painter.setPen(QPen(QColor(0, 200, 255), 2))
            painter.drawRect(rect)
            # 在选框内挖空，便于看清游戏内容
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._end = self._start
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._start is not None:
            self._end = event.globalPosition().toPoint()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._start is not None:
            self._end = event.globalPosition().toPoint()
            # 转物理像素（适配 DPI 缩放）
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen is not None else 1.0
            left = min(self._start.x(), self._end.x()) * dpr
            top = min(self._start.y(), self._end.y()) * dpr
            right = max(self._start.x(), self._end.x()) * dpr
            bottom = max(self._start.y(), self._end.y()) * dpr
            self.region_selected.emit(
                (int(left), int(top), int(right) + 1, int(bottom) + 1)
            )
        self._start = None
        self._end = None
        self.close()
        event.accept()


class RealtimePage(QWidget):
    """实时翻译页面。"""

    result_ready = Signal(str, str)
    status_ready = Signal(str)

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._session = None
        self._thread = None
        self._overlay = None
        self._region = None
        self._selector = None
        self._top_was_visible = True
        self._minimized_main = False
        self.result_ready.connect(self._on_result)
        self.status_ready.connect(self._on_status)
        self._build_ui()
        self._refresh_ocr_status()

    def _build_ui(self) -> None:
        """构建界面。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setSpacing(8)

        title = QLabel("实时翻译")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "框选游戏文本区域，自动 OCR 并翻译。适合日文文本无法直接提取的游戏。"
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # OCR 语言状态横幅
        banner = QWidget()
        banner.setObjectName("banner")
        bc = QVBoxLayout(banner)
        bc.setContentsMargins(16, 10, 16, 10)
        self._ocr_status = QLabel()
        self._ocr_status.setObjectName("bannerTitle")
        self._ocr_status.setWordWrap(True)
        self._retest_btn = QPushButton("重新检测")
        self._retest_btn.clicked.connect(self._refresh_ocr_status)
        self._guide_btn = QPushButton("日语 OCR 引导")
        self._guide_btn.setObjectName("successBtn")
        self._guide_btn.clicked.connect(self._open_guide)
        row = QHBoxLayout()
        row.addWidget(self._ocr_status, 1)
        row.addWidget(self._retest_btn)
        row.addWidget(self._guide_btn)
        bc.addLayout(row)
        layout.addWidget(banner)

        # 顶部操作行
        top = QHBoxLayout()
        self._region_btn = QPushButton("框选屏幕区域")
        self._region_btn.clicked.connect(self._pick_region)
        self._region_label = QLabel("未选择区域")
        self._region_label.setObjectName("subtitleLabel")
        top.addWidget(self._region_btn)
        top.addWidget(self._region_label, 1)
        top.addWidget(QLabel("引擎"))
        self._engine_combo = QComboBox()
        for name, label in _ENGINE_LABELS.items():
            self._engine_combo.addItem(label, name)
        rtconf = self._config.get("realtime") or {}
        default_engine = rtconf.get("engine", "bing")
        idx = self._engine_combo.findData(default_engine)
        self._engine_combo.setCurrentIndex(max(0, idx))
        top.addWidget(self._engine_combo)
        # 翻译间隔等可调变量
        top.addWidget(QLabel("间隔(秒)"))
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.1, 10.0)
        self._interval_spin.setSingleStep(0.1)
        self._interval_spin.setValue(
            float((self._config.get("ocr") or {}).get("interval", 0.4))
        )
        self._interval_spin.setToolTip("OCR 轮询间隔（秒），越小越频繁")
        top.addWidget(self._interval_spin)
        self._start_btn = QPushButton("开始")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._toggle_session)
        self._overlay_check = QCheckBox("显示悬浮窗")
        self._overlay_check.setChecked(True)
        top.addWidget(self._start_btn)
        top.addWidget(self._overlay_check)
        layout.addLayout(top)

        # 原文 / 译文
        text_grid = QGridLayout()
        text_grid.setSpacing(8)
        text_grid.addWidget(QLabel("原文（OCR）"), 0, 0)
        text_grid.addWidget(QLabel("译文"), 0, 1)
        self._original_view = QPlainTextEdit()
        self._original_view.setReadOnly(True)
        self._original_view.setMaximumBlockCount(1000)
        self._translated_view = QPlainTextEdit()
        self._translated_view.setReadOnly(True)
        self._translated_view.setMaximumBlockCount(1000)
        text_grid.addWidget(self._original_view, 1, 0)
        text_grid.addWidget(self._translated_view, 1, 1)
        layout.addLayout(text_grid, 1)

        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("subtitleLabel")
        layout.addWidget(self._status_label)

        self._log = LogView(max_blocks=1000)
        self._log.setFixedHeight(120)
        layout.addWidget(self._log)

        scroll.setWidget(body)

    # ---------- OCR 状态 ----------

    def _refresh_ocr_status(self) -> None:
        """刷新 OCR 语言状态。"""
        try:
            status = ocr.detect_ocr_status()
        except Exception:  # noqa: BLE001
            status = {"ja_available": False, "current_lang": "未知", "available_langs": []}
        if status.get("ja_available"):
            self._ocr_status.setText("✓ 日语 OCR 引擎已就绪")
            self._ocr_status.setStyleSheet("color: #16a34a;")
            self._guide_btn.setObjectName("successBtn")
            self._guide_btn.setText("日语 OCR 引导")
        else:
            current = status.get("current_lang") or "无"
            self._ocr_status.setText(f"⚠ 未安装日语 OCR（当前回退：{current}）")
            self._ocr_status.setStyleSheet("color: #d97706;")
            self._guide_btn.setObjectName("dangerBtn")
            self._guide_btn.setText("查看安装引导")
        self._guide_btn.style().unpolish(self._guide_btn)
        self._guide_btn.style().polish(self._guide_btn)

    def _open_guide(self) -> None:
        """打开 OCR 语言包引导。"""
        LanguageGuideDialog(self).exec()
        self._refresh_ocr_status()

    # ---------- 区域选择 ----------

    def _pick_region(self) -> None:
        """弹出区域选择遮罩（框选期间隐藏主窗口）。"""
        top = self.window()
        if top is not None and top is not self:
            self._top_was_visible = top.isVisible()
            top.hide()
        selector = _RegionSelector()
        # 必须保存引用，否则局部变量被 GC 回收导致遮罩立即消失
        self._selector = selector
        selector.region_selected.connect(self._on_region_selected)
        selector.region_selected.connect(lambda _: self._restore_top())
        selector.closed.connect(self._restore_top)
        selector.closed.connect(self._on_selector_closed)
        selector.show_and_select()

    def _on_selector_closed(self) -> None:
        """遮罩关闭后清空引用。"""
        self._selector = None

    def _restore_top(self) -> None:
        """恢复被隐藏的主窗口。"""
        top = self.window()
        if (
            top is not None
            and top is not self
            and getattr(self, "_top_was_visible", True)
        ):
            top.show()
            top.raise_()
            top.activateWindow()

    def _on_region_selected(self, region: tuple) -> None:
        """区域选中回调。"""
        self._region = region
        left, top, right, bottom = region
        self._region_label.setText(
            f"区域 ({left}, {top}) - ({right}, {bottom}) 尺寸 {right - left}×{bottom - top}"
        )
        self._start_btn.setEnabled(True)

    # ---------- 会话控制 ----------

    def _toggle_session(self) -> None:
        """开始/停止切换。"""
        if self._session is None:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self) -> None:
        """启动实时翻译会话。"""
        if self._region is None:
            return
        interval = float(self._interval_spin.value())
        self._config.set("ocr", "interval", interval)
        engine_name = self._engine_combo.currentData() or "bing"

        if engine_name == "local" and not is_model_downloaded(self._config):
            self._log.warn("⚠ 本地模型未下载，请先到设置页下载模型")
            self.status_ready.emit("⚠ 本地模型未下载，请先到设置页下载模型")
            return

        self._config.set("realtime", "engine", engine_name)
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
        self._thread = __import__("threading").Thread(
            target=self._session.run, daemon=True
        )
        self._thread.start()

        self._start_btn.setText("停止")
        self._region_btn.setEnabled(False)
        self._engine_combo.setEnabled(False)
        self._interval_spin.setEnabled(False)
        self._log.info(f"实时翻译启动（引擎：{engine_name}，间隔：{interval} 秒）")

        # 自动最小化主窗口，避免遮挡游戏（停止时恢复）
        top = self.window()
        if top is not None and top is not self and top.isVisible():
            self._minimized_main = True
            top.showMinimized()
        else:
            self._minimized_main = False

        # 悬浮窗「停止翻译」入口：确保悬浮窗存在并连接停止信号
        if self._overlay is None:
            self._overlay = OverlayWindow(self._config)
            self._overlay.stop_requested.connect(self._stop_session)
            if self._overlay_check.isChecked():
                self._overlay.show()

    def _stop_session(self) -> None:
        """停止会话。"""
        if self._session is not None:
            self._session.request_stop()
            # 等待后台线程退出，避免其继续回调重建悬浮窗
            if self._thread is not None:
                self._thread.join(timeout=self._session.interval + 1.0)
            self._session = None
            self._thread = None
        self._start_btn.setText("开始")
        self._region_btn.setEnabled(True)
        self._engine_combo.setEnabled(True)
        self._interval_spin.setEnabled(True)
        self._log.info("实时翻译已停止")

        # 恢复被最小化的主窗口
        if getattr(self, "_minimized_main", False):
            self._minimized_main = False
            top = self.window()
            if top is not None and top is not self:
                top.showNormal()
                top.raise_()
                top.activateWindow()

        # 停止翻译时关闭悬浮窗
        if self._overlay is not None:
            self._overlay.clear()
            self._overlay.close()
            self._overlay = None

    # ---------- 回调 ----------

    def _on_result(self, original: str, translated: str) -> None:
        """处理翻译结果。"""
        self._original_view.appendPlainText(original)
        self._translated_view.appendPlainText(translated)
        if self._overlay_check.isChecked():
            if self._overlay is None:
                self._overlay = OverlayWindow(self._config)
                self._overlay.stop_requested.connect(self._stop_session)
            self._overlay.show_translation(original, translated)

    def _on_status(self, message: str) -> None:
        """处理状态消息。"""
        self._status_label.setText(message)
        self._log_append(message)

    def _toggle_overlay(self) -> None:
        """显示/隐藏悬浮窗。"""
        if self._overlay is not None:
            if self._overlay.isVisible():
                self._overlay.hide()
            else:
                self._overlay.show()

    def _log_append(self, message: str) -> None:
        """按内容分级追加日志（失败→ERROR，警告→WARN，其余→INFO）。"""
        if "失败" in message or "错误" in message or "异常" in message:
            self._log.error(message)
        elif message.startswith("⚠") or "未下载" in message:
            self._log.warn(message)
        else:
            self._log.info(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭时清理会话与悬浮窗。"""
        self._stop_session()
        if self._overlay is not None:
            self._overlay.close()
        super().closeEvent(event)
