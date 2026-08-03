"""离线汉化页：步骤引导式选择游戏目录 → 输出目录 → 开始汉化。"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..pipeline import run_offline
from ..translate.manager import ENGINE_REGISTRY, TranslationManager
from .log_view import LogView


class _OfflineWorker(QWidget):
    """离线汉化后台任务（运行在独立线程）。"""

    progress = Signal(str, int, int, str)
    finished = Signal(str)

    def __init__(self, game_dir: str, output_dir: str, translator, glossary) -> None:
        super().__init__()
        self._game_dir = game_dir
        self._output_dir = output_dir
        self._translator = translator
        self._glossary = glossary
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        """请求取消任务。"""
        self._cancel.set()

    def run(self) -> None:
        """执行汉化流水线。"""
        try:
            job = run_offline(
                self._game_dir,
                self._output_dir,
                self._translator,
                self._glossary,
                progress=lambda stage, done, total, msg: self.progress.emit(
                    stage, done, total, msg
                ),
                cancel=self._cancel,
            )
            if self._cancel.is_set():
                self.finished.emit("任务已取消")
            else:
                self.finished.emit(f"汉化完成：共 {len(job.parse_results)} 个文件")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(f"汉化失败：{exc}")


class OfflinePage(QWidget):
    """离线汉化页面。"""

    goto_settings = Signal()

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._worker = None
        self._thread = None
        self._build_ui()
        self._refresh_engine_hint()

    def _build_ui(self) -> None:
        """构建界面。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setSpacing(10)

        title = QLabel("离线汉化")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("三步完成：① 选择游戏 → ② 选择输出目录 → ③ 开始汉化")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(subtitle)

        # ① 选择游戏
        card1 = QWidget()
        card1.setObjectName("card")
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(16, 12, 16, 12)
        t1 = QLabel("① 选择游戏")
        t1.setObjectName("cardTitle")
        c1.addWidget(t1)
        row1 = QHBoxLayout()
        self._game_edit = QLineEdit()
        self._game_edit.setPlaceholderText(
            "选择游戏目录，或直接选中游戏 exe（自动定位到所在目录）"
        )
        self._game_edit.setAcceptDrops(True)
        self._game_edit.dragEnterEvent = self._drag_enter
        self._game_edit.dropEvent = self._drop_game
        self._game_btn = QPushButton("选择目录")
        self._game_btn.clicked.connect(self._pick_game_dir)
        self._game_exe_btn = QPushButton("选择游戏 exe")
        self._game_exe_btn.clicked.connect(self._pick_game_exe)
        row1.addWidget(self._game_edit, 1)
        row1.addWidget(self._game_exe_btn)
        row1.addWidget(self._game_btn)
        c1.addLayout(row1)
        layout.addWidget(card1)

        # ② 选择输出目录
        card2 = QWidget()
        card2.setObjectName("card")
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(16, 12, 16, 12)
        t2 = QLabel("② 选择输出目录")
        t2.setObjectName("cardTitle")
        c2.addWidget(t2)
        row2 = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("汉化补丁与对照表的输出位置（建议非游戏目录）")
        self._out_btn = QPushButton("浏览...")
        self._out_btn.clicked.connect(self._pick_out_dir)
        row2.addWidget(self._out_edit, 1)
        row2.addWidget(self._out_btn)
        c2.addLayout(row2)
        layout.addWidget(card2)

        # ③ 开始汉化
        card3 = QWidget()
        card3.setObjectName("card")
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(16, 12, 16, 12)
        t3 = QLabel("③ 开始汉化")
        t3.setObjectName("cardTitle")
        c3.addWidget(t3)
        self._engine_hint = QLabel()
        self._engine_hint.setObjectName("bannerText")
        self._engine_hint.setWordWrap(True)
        self._engine_hint.setTextFormat(Qt.TextFormat.RichText)
        self._engine_hint.setOpenExternalLinks(False)
        self._engine_hint.linkActivated.connect(self._on_engine_hint_link)
        c3.addWidget(self._engine_hint)
        row3 = QHBoxLayout()
        self._start_btn = QPushButton("开始汉化")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start_job)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_job)
        row3.addWidget(self._start_btn)
        row3.addWidget(self._cancel_btn)
        row3.addStretch(1)
        c3.addLayout(row3)
        layout.addWidget(card3)

        # 运行状态区
        status_card = QWidget()
        status_card.setObjectName("card")
        sc = QVBoxLayout(status_card)
        sc.setContentsMargins(16, 12, 16, 12)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._status_label = QLabel("等待开始")
        self._status_label.setObjectName("subtitleLabel")
        sc.addWidget(self._progress)
        sc.addWidget(self._status_label)
        layout.addWidget(status_card)

        # 汉化后使用说明（紧凑横幅）
        done_card = QWidget()
        done_card.setObjectName("banner")
        dc = QVBoxLayout(done_card)
        dc.setContentsMargins(16, 10, 16, 10)
        done_title = QLabel("汉化完成后如何使用")
        done_title.setObjectName("bannerTitle")
        done_text = QLabel(
            "补丁在输出目录 patch/ 中，覆盖到游戏根目录（建议先备份）即可启动中文版；"
            "translation_table.csv 为对照表，可用 Excel 校对；还原原版用备份覆盖回去即可。"
        )
        done_text.setObjectName("bannerText")
        done_text.setWordWrap(True)
        dc.addWidget(done_title)
        dc.addWidget(done_text)
        layout.addWidget(done_card)

        # 日志
        self._log = LogView(max_blocks=2000)
        self._log.setMinimumHeight(140)
        layout.addWidget(self._log)

        layout.addStretch(1)
        scroll.setWidget(body)

        self._game_edit.textChanged.connect(self._update_start_state)
        self._out_edit.textChanged.connect(self._update_start_state)

    # ---------- 选择路径 ----------

    def _pick_game_dir(self) -> None:
        """选择游戏目录。"""
        path = QFileDialog.getExistingDirectory(self, "选择游戏目录")
        if path:
            self._game_edit.setText(path)

    def _pick_game_exe(self) -> None:
        """选择游戏 exe（自动定位到所在目录）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏 exe", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if path:
            self._game_edit.setText(self._normalize_game_path(path))

    def _drag_enter(self, event: QDragEnterEvent) -> None:
        """接受文件拖入。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_game(self, event: QDropEvent) -> None:
        """处理拖入的游戏目录/exe。"""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._game_edit.setText(self._normalize_game_path(path))

    @staticmethod
    def _normalize_game_path(path: str) -> str:
        """若选中 exe 文件则返回其所在目录，否则原样返回。"""
        p = Path(path.strip())
        if p.is_file():
            return str(p.parent)
        return path.strip()

    def _pick_out_dir(self) -> None:
        """选择输出目录。"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self._out_edit.setText(path)

    # ---------- 状态管理 ----------

    def _busy(self) -> bool:
        """是否正在执行任务。"""
        return self._worker is not None

    def _update_start_state(self) -> None:
        """根据输入更新开始按钮可用状态。"""
        self._start_btn.setEnabled(
            bool(self._game_edit.text().strip())
            and bool(self._out_edit.text().strip())
            and not self._busy()
        )

    def _refresh_engine_hint(self) -> None:
        """刷新首选引擎提示（缺 Key 时给出警告并可跳转设置）。"""
        tconf = self._config.get("translate") or {}
        primary = tconf.get("primary", "deepseek")
        engine_cls = ENGINE_REGISTRY.get(primary)
        needs_key = bool(engine_cls and engine_cls.needs_key)
        has_key = bool(self._config.get_secret(primary))
        if needs_key and not has_key:
            self._engine_hint.setText(
                f'⚠ 首选引擎 <b>{primary}</b> 需要 API Key，当前未配置。<br>'
                f'请 <a href="settings" style="color:#2563eb;">前往设置页</a> 填写，'
                f'否则将自动降级到其他引擎。'
            )
            self._engine_hint.setStyleSheet("color: #d97706;")
        else:
            status = "已配置" if has_key else "无需 Key"
            self._engine_hint.setText(f"✓ 首选引擎 {primary}（{status}）")
            self._engine_hint.setStyleSheet("color: #16a34a;")

    def _on_engine_hint_link(self, href: str) -> None:
        """引擎提示链接点击。"""
        if href == "settings":
            self.goto_settings.emit()

    # ---------- 任务控制 ----------

    def _start_job(self) -> None:
        """启动汉化任务。"""
        game_dir = self._normalize_game_path(self._game_edit.text())
        if game_dir != self._game_edit.text():
            self._game_edit.setText(game_dir)
        output_dir = self._out_edit.text().strip()
        if not game_dir or not output_dir:
            return

        translator = TranslationManager(self._config, self._glossary)
        self._worker = _OfflineWorker(game_dir, output_dir, translator, self._glossary)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._log_append(f"开始汉化：{game_dir} → {output_dir}")
        self._set_busy_ui(True)
        self._thread.start()
    def _cancel_job(self) -> None:
        """取消任务。"""
        if self._worker is not None:
            self._worker.request_cancel()
            self._status_label.setText("正在取消...")

    def _on_progress(self, stage: str, done: int, total: int, message: str) -> None:
        """处理进度信号。"""
        if stage == "scan":
            self._progress.setRange(0, 0)  # 转圈
            self._status_label.setText(f"扫描中... {message}")
        elif stage in ("translate", "patch"):
            if total > 0:
                self._progress.setRange(0, total)
                self._progress.setValue(done)
            self._status_label.setText(message)
        elif stage == "done":
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._status_label.setText(message)
        if message:
            self._log_append(message)

    def _on_finished(self, message: str) -> None:
        """任务完成回调。"""
        self._set_busy_ui(False)
        self._status_label.setText(message)
        self._log_append(message)

    def _set_busy_ui(self, busy: bool) -> None:
        """切换忙碌状态 UI。"""
        self._start_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._game_exe_btn.setEnabled(not busy)
        self._game_btn.setEnabled(not busy)
        self._out_btn.setEnabled(not busy)
        if not busy:
            self._worker = None
            self._thread = None
        self._update_start_state()

    def _log_append(self, message: str) -> None:
        """按内容分级追加日志（失败→ERROR，警告→WARN，其余→INFO）。"""
        if "失败" in message or "错误" in message or "异常" in message:
            self._log.error(message)
        elif message.startswith("⚠") or "取消" in message:
            self._log.warn(message)
        else:
            self._log.info(message)
