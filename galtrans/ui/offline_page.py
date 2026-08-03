"""离线汉化页面

功能：
- 选择游戏目录与输出目录
- 一键执行「扫描 -> 翻译 -> 生成补丁 -> 导出对照表」
- 展示实时进度与日志，支持取消
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..pipeline import run_offline
from ..translate import TranslationManager


class _OfflineWorker(QWidget):
    """在后台线程执行离线汉化流程的封装

    通过信号把进度与结果传回界面线程，避免卡顿。
    """

    progress = Signal(str, int, int, str)   # 阶段/当前/总数/消息
    finished = Signal(str)                   # 完成或失败信息

    def __init__(
        self,
        game_dir: str,
        output_dir: str,
        translator: TranslationManager,
        glossary,
    ) -> None:
        super().__init__()
        self._game_dir = game_dir
        self._output_dir = output_dir
        self._translator = translator
        self._glossary = glossary
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        """请求取消当前任务"""
        self._cancel.set()

    def run(self) -> None:
        """线程入口，执行完整流程"""
        def _progress(stage, done, total, msg):
            self.progress.emit(stage, done, total, msg)

        try:
            run_offline(
                Path(self._game_dir),
                Path(self._output_dir),
                self._translator,
                self._glossary,
                progress=_progress,
                cancel=self._cancel,
            )
            if self._cancel.is_set():
                self.finished.emit("任务已取消")
            else:
                self.finished.emit("汉化完成")
        except Exception as exc:
            self.finished.emit(f"汉化失败：{exc}")


class OfflinePage(QWidget):
    """离线汉化页面"""

    # 用户点击「前往设置」时发出，主窗口切换页面
    goto_settings = Signal()

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._worker: _OfflineWorker | None = None
        self._thread: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """构建界面布局（步骤引导式，整页可滚动）"""
        # 外层滚动区域：内容超出窗口高度时可滚动
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        outer = QVBoxLayout(container)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 16, 20, 16)

        # 页面标题与说明
        title = QLabel("离线汉化")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        subtitle = QLabel("适用于支持 Ren'Py、Kirikiri 引擎的游戏。三步完成：选择目录 → 配置引擎 → 开始汉化。")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        # 步骤 1：选择游戏目录或 exe
        step1 = QWidget()
        step1.setObjectName("card")
        s1 = QVBoxLayout(step1)
        s1.setContentsMargins(16, 14, 16, 14)
        s1.setSpacing(8)
        step1_title = QLabel("① 选择游戏")
        step1_title.setObjectName("cardTitle")
        s1.addWidget(step1_title)

        row1 = QHBoxLayout()
        self._game_edit = QLineEdit()
        self._game_edit.setPlaceholderText("选择游戏目录，或直接选中游戏 exe（自动定位到所在目录）")
        self._game_edit.setAcceptDrops(True)
        self._game_edit.dragEnterEvent = self._drag_enter
        self._game_edit.dropEvent = self._drop_game
        self._game_btn = QPushButton("选择目录")
        self._game_btn.clicked.connect(self._pick_game_dir)
        self._game_exe_btn = QPushButton("选择游戏 exe")
        self._game_exe_btn.clicked.connect(self._pick_game_exe)
        row1.addWidget(self._game_edit, 1)
        row1.addWidget(self._game_btn)
        row1.addWidget(self._game_exe_btn)
        s1.addLayout(row1)
        outer.addWidget(step1)

        # 步骤 2：选择输出目录
        step2 = QWidget()
        step2.setObjectName("card")
        s2 = QVBoxLayout(step2)
        s2.setContentsMargins(16, 14, 16, 14)
        s2.setSpacing(8)
        step2_title = QLabel("② 选择输出目录")
        step2_title.setObjectName("cardTitle")
        s2.addWidget(step2_title)

        row2 = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("汉化输出目录（补丁与对照表将写入此处）")
        self._out_btn = QPushButton("浏览...")
        self._out_btn.clicked.connect(self._pick_out_dir)
        row2.addWidget(self._out_edit, 1)
        row2.addWidget(self._out_btn)
        s2.addLayout(row2)
        outer.addWidget(step2)

        # 步骤 3：开始汉化
        step3 = QWidget()
        step3.setObjectName("card")
        s3 = QVBoxLayout(step3)
        s3.setContentsMargins(16, 14, 16, 14)
        s3.setSpacing(8)
        step3_title = QLabel("③ 开始汉化")
        step3_title.setObjectName("cardTitle")
        s3.addWidget(step3_title)

        # 引擎配置提示（点击跳转到设置页）
        self._engine_hint = QLabel()
        self._engine_hint.setObjectName("bannerText")
        self._engine_hint.setWordWrap(True)
        self._engine_hint.setTextFormat(Qt.RichText)
        self._engine_hint.setOpenExternalLinks(False)
        self._engine_hint.linkActivated.connect(self._on_engine_hint_link)
        s3.addWidget(self._engine_hint)
        self._refresh_engine_hint()

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("开始汉化")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start_job)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_job)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch(1)
        s3.addLayout(btn_row)
        outer.addWidget(step3)

        # 运行状态区（进度条 + 状态），独立于步骤卡片
        status_card = QWidget()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(6)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        status_layout.addWidget(self._progress)
        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("subtitleLabel")
        status_layout.addWidget(self._status_label)
        outer.addWidget(status_card)

        # 汉化完成后使用说明
        done_card = QWidget()
        done_card.setObjectName("banner")
        done_layout = QVBoxLayout(done_card)
        done_layout.setContentsMargins(12, 8, 12, 8)
        done_layout.setSpacing(2)
        done_title = QLabel("汉化完成后如何使用")
        done_title.setObjectName("bannerTitle")
        done_layout.addWidget(done_title)
        done_hint = QLabel(
            "补丁在输出目录 patch/ 中，覆盖到游戏根目录（建议先备份）即可启动中文版；"
            "translation_table.csv 为对照表，可用 Excel 校对；还原原版用备份覆盖回去即可。"
        )
        done_hint.setObjectName("bannerText")
        done_hint.setWordWrap(True)
        done_layout.addWidget(done_hint)
        outer.addWidget(done_card)

        # 日志区（固定高度，随整页滚动）
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("logView")
        self._log.setMaximumBlockCount(2000)
        self._log.setMinimumHeight(140)
        outer.addWidget(self._log)

        # 目录变化时联动按钮状态
        self._game_edit.textChanged.connect(self._update_start_state)
        self._out_edit.textChanged.connect(self._update_start_state)

    def _pick_game_dir(self) -> None:
        """选择游戏目录"""
        path = QFileDialog.getExistingDirectory(self, "选择游戏目录", self._game_edit.text())
        if path:
            self._game_edit.setText(path)

    def _pick_game_exe(self) -> None:
        """选择游戏 exe 文件，自动定位到所在目录"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏 exe", self._game_edit.text(), "可执行文件 (*.exe);;所有文件 (*)"
        )
        if path:
            self._game_edit.setText(self._normalize_game_path(path))

    def _drag_enter(self, event: QDragEnterEvent) -> None:
        """拖拽进入：接受文件拖入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_game(self, event: QDropEvent) -> None:
        """拖放：把拖入的文件/目录填入输入框"""
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self._game_edit.setText(self._normalize_game_path(path))
            event.acceptProposedAction()

    @staticmethod
    def _normalize_game_path(path: str) -> str:
        """把用户输入归一化为游戏目录路径。

        若指向 .exe 等文件，则取其父目录；否则原样返回。
        """
        p = Path(path.strip())
        if p.is_file():
            return str(p.parent)
        return str(p)

    def _pick_out_dir(self) -> None:
        """选择输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self._out_edit.text())
        if path:
            self._out_edit.setText(path)

    def _update_start_state(self) -> None:
        """根据输入状态决定开始按钮是否可用"""
        ready = bool(self._game_edit.text()) and bool(self._out_edit.text())
        self._start_btn.setEnabled(ready and not self._busy())

    def _refresh_engine_hint(self) -> None:
        """刷新引擎配置提示（进入页面时调用）"""
        from ..translate.manager import ENGINE_REGISTRY

        conf = self._config
        tconf = conf.get("translate") or {}
        primary = tconf.get("primary", "deepseek")
        # 首选引擎是否需要 key
        engine_cls = ENGINE_REGISTRY.get(primary)
        needs_key = bool(engine_cls and engine_cls.needs_key)
        # 读取该引擎段的 key（优先加密存储，兼容旧明文）
        key = conf.get_secret(primary)
        if needs_key and not key:
            self._engine_hint.setText(
                f"⚠ 首选引擎 <b>{primary}</b> 需要 API Key，当前未配置。<br>"
                f"请 <a href=\"settings\" style=\"color:#3b82f6;\">前往设置页</a> 填写，否则将自动降级到其他引擎。"
            )
        else:
            label = "已配置" if needs_key else "免费引擎，无需 Key"
            self._engine_hint.setText(f"✓ 首选引擎 <b>{primary}</b>（{label}）")
        self._engine_hint.setStyleSheet(
            "color: #d97706; background: #fffbeb; border-radius: 6px; padding: 8px;"
            if needs_key and not key
            else "color: #16a34a; background: #f0fdf4; border-radius: 6px; padding: 8px;"
        )

    def _busy(self) -> bool:
        """是否正在执行任务"""
        return self._worker is not None

    def _on_engine_hint_link(self, href: str) -> None:
        """点击引擎提示中的链接"""
        if href == "settings":
            self.goto_settings.emit()

    def _start_job(self) -> None:
        """启动后台汉化线程"""
        game_dir = self._normalize_game_path(self._game_edit.text())
        output_dir = self._out_edit.text().strip()
        if not game_dir or not output_dir:
            return
        # 归一化后的目录回填到输入框，便于用户确认
        if game_dir != self._game_edit.text().strip():
            self._game_edit.setText(game_dir)

        # 依据配置构建翻译管理器
        translator = TranslationManager(self._config, self._glossary)

        self._worker = _OfflineWorker(game_dir, output_dir, translator, self._glossary)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)

        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._set_busy_ui(True)
        self._log_append("任务开始...")
        self._thread.start()

    def _cancel_job(self) -> None:
        """请求取消任务"""
        if self._worker:
            self._worker.request_cancel()
            self._log_append("取消请求已发送，等待停止...")

    def _on_progress(self, stage: str, done: int, total: int, msg: str) -> None:
        """处理进度信号"""
        if stage == "translate" and total > 0:
            self._progress.setValue(int(done / total * 100))
            self._status_label.setText(f"翻译中 {done}/{total}")
        elif stage == "patch" and total > 0:
            self._progress.setValue(int(done / total * 100))
            self._status_label.setText(f"生成补丁 {done}/{total}")
        elif stage == "scan":
            self._status_label.setText("扫描解析中...")
            self._progress.setRange(0, 0)  # 不确定进度，转圈
        elif stage == "done":
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._status_label.setText("完成")
        self._log_append(msg)

    def _on_finished(self, info: str) -> None:
        """任务结束处理"""
        self._set_busy_ui(False)
        self._log_append(info)
        self._status_label.setText(info)
        self._worker = None
        self._thread = None
        self._progress.setRange(0, 100)
        self._update_start_state()

    def _set_busy_ui(self, busy: bool) -> None:
        """切换界面为忙碌/空闲状态"""
        self._start_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._game_edit.setEnabled(not busy)
        self._out_edit.setEnabled(not busy)
        self._game_btn.setEnabled(not busy)
        self._game_exe_btn.setEnabled(not busy)
        self._out_btn.setEnabled(not busy)

    def _log_append(self, text: str) -> None:
        """追加一行日志"""
        self._log.appendPlainText(text)
