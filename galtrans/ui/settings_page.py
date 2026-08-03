"""设置页面

编辑翻译引擎、本地模型、请求参数与界面相关的配置。
保存后写入 config.json，下次任务生效。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# 可选引擎名称（与 ENGINE_REGISTRY 对应）
ENGINE_NAMES = ["deepseek", "deepl", "google", "bing", "local"]
ENGINE_LABELS = {
    "deepseek": "DeepSeek（需 API Key，推荐）",
    "deepl": "DeepL（需 API Key）",
    "google": "Google 免费接口",
    "bing": "Bing 免费接口",
    "local": "本地模型（离线）",
}


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, config) -> None:
        super().__init__()
        self._config = config
        self._download_thread = None
        self._poll_timer = None
        self._build_ui()
        self._load_values()

    # ---------- 界面构建 ----------

    def _build_ui(self) -> None:
        """构建界面（使用滚动区域以适配小屏）"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

        layout = QVBoxLayout(body)
        layout.setSpacing(12)

        layout.addWidget(self._build_engine_group())
        layout.addWidget(self._build_local_model_group())
        layout.addWidget(self._build_deepseek_group())
        layout.addWidget(self._build_deepl_group())
        layout.addWidget(self._build_requests_group())
        layout.addWidget(self._build_overlay_group())
        layout.addStretch(1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._reset_btn = QPushButton("恢复默认")
        self._reset_btn.clicked.connect(self._restore_defaults)
        self._save_btn = QPushButton("保存设置")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.clicked.connect(self._save)
        btn_row.addStretch(1)
        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        scroll.setWidget(body)

    def _make_fallback_list(self) -> QComboBox:
        """可编辑的降级引擎输入框"""
        combo = QComboBox()
        combo.setEditable(True)
        combo.setPlaceholderText("直接输入引擎名，逗号分隔（deepseek,deepl,google,bing）")
        combo.setInsertPolicy(QComboBox.NoInsert)
        return combo

    def _build_engine_group(self) -> QGroupBox:
        """翻译引擎选择分组"""
        group = QGroupBox("翻译引擎")
        form = QFormLayout(group)

        self._primary_combo = QComboBox()
        for name in ENGINE_NAMES:
            self._primary_combo.addItem(ENGINE_LABELS.get(name, name), name)
        form.addRow("首选引擎", self._primary_combo)

        self._fallback_list = self._make_fallback_list()
        form.addRow("降级引擎", self._fallback_list)

        hint = QLabel("首选引擎不可用或失败时，按此处顺序自动降级。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("", hint)

        token_hint = QLabel(
            "提示：仅 DeepSeek 按 Token 计费；Google / Bing / DeepL 免费接口不消耗 Token。"
            "软件内置翻译缓存，相同句子只翻译一次。"
        )
        token_hint.setWordWrap(True)
        token_hint.setStyleSheet("color: gray;")
        form.addRow("", token_hint)

        self._test_btn = QPushButton("测试所有引擎连接")
        self._test_btn.clicked.connect(self._test_engines)
        form.addRow("", self._test_btn)
        return group

    def _build_local_model_group(self) -> QGroupBox:
        """本地模型（离线翻译）配置分组"""
        group = QGroupBox("本地模型（离线翻译）")
        form = QFormLayout(group)

        self._local_model_edit = QLineEdit()
        self._local_model_edit.setPlaceholderText("shun89/opus-mt-ja-zh")
        form.addRow("模型名", self._local_model_edit)

        self._local_endpoint_edit = QLineEdit()
        self._local_endpoint_edit.setPlaceholderText("留空用官方源，国内可填 https://hf-mirror.com")
        form.addRow("下载镜像", self._local_endpoint_edit)

        self._local_status = QLabel("未检测")
        self._local_status.setStyleSheet("color: gray;")
        form.addRow("模型状态", self._local_status)

        self._local_path = QLabel("-")
        self._local_path.setWordWrap(True)
        self._local_path.setStyleSheet("color: gray;")
        form.addRow("模型路径", self._local_path)

        # 下载进度条（默认隐藏，开始下载时显示）
        self._local_progress = QProgressBar()
        self._local_progress.setRange(0, 100)
        self._local_progress.setValue(0)
        self._local_progress.hide()
        form.addRow("", self._local_progress)

        btn_row = QHBoxLayout()
        self._local_download_btn = QPushButton("下载模型")
        self._local_download_btn.clicked.connect(self._download_local_model)
        self._local_test_btn = QPushButton("测试此引擎")
        self._local_test_btn.clicked.connect(lambda: self._test_one_engine("local"))
        btn_row.addWidget(self._local_download_btn)
        btn_row.addWidget(self._local_test_btn)
        btn_row.addStretch(1)
        form.addRow("", btn_row)

        hint = QLabel(
            "说明：下载后可离线翻译，无网络延迟。模型约 300MB，下载到本地用户目录，"
            "仅用于实时翻译。下载速度取决于网络与镜像配置。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("", hint)
        return group

    def _build_deepseek_group(self) -> QGroupBox:
        """DeepSeek 配置分组"""
        group = QGroupBox("DeepSeek 配置")
        form = QFormLayout(group)

        self._ds_key = QLineEdit()
        self._ds_key.setEchoMode(QLineEdit.Password)
        self._ds_key.setPlaceholderText("sk-...（加密保存，仅存本机）")
        form.addRow("API Key", self._ds_key)

        self._ds_url = QLineEdit()
        self._ds_url.setPlaceholderText("https://api.deepseek.com")
        form.addRow("API 地址", self._ds_url)

        self._ds_model = QLineEdit()
        self._ds_model.setPlaceholderText("deepseek-chat")
        form.addRow("模型名", self._ds_model)

        self._ds_temp = QDoubleSpinBox()
        self._ds_temp.setRange(0, 2)
        self._ds_temp.setSingleStep(0.1)
        self._ds_temp.setDecimals(1)
        form.addRow("温度", self._ds_temp)

        self._ds_max_tokens = QSpinBox()
        self._ds_max_tokens.setRange(256, 32768)
        self._ds_max_tokens.setSingleStep(512)
        form.addRow("最大 Tokens", self._ds_max_tokens)

        self._ds_test_btn = QPushButton("测试此引擎")
        self._ds_test_btn.clicked.connect(lambda: self._test_one_engine("deepseek"))
        form.addRow("", self._ds_test_btn)
        return group

    def _build_deepl_group(self) -> QGroupBox:
        """DeepL 配置分组"""
        group = QGroupBox("DeepL 配置")
        form = QFormLayout(group)

        self._dl_key = QLineEdit()
        self._dl_key.setEchoMode(QLineEdit.Password)
        self._dl_key.setPlaceholderText("DeepL 免费版 API Key（加密保存）")
        form.addRow("API Key", self._dl_key)

        self._dl_url = QLineEdit()
        self._dl_url.setPlaceholderText("https://api-free.deepl.com/v2/translate")
        form.addRow("API 地址", self._dl_url)

        self._dl_test_btn = QPushButton("测试此引擎")
        self._dl_test_btn.clicked.connect(lambda: self._test_one_engine("deepl"))
        form.addRow("", self._dl_test_btn)
        return group

    def _build_requests_group(self) -> QGroupBox:
        """请求参数分组"""
        group = QGroupBox("请求参数")
        form = QFormLayout(group)

        self._timeout = QSpinBox()
        self._timeout.setRange(5, 120)
        form.addRow("超时（秒）", self._timeout)

        self._retry = QSpinBox()
        self._retry.setRange(0, 5)
        form.addRow("失败重试次数", self._retry)

        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 16)
        form.addRow("并发线程数", self._concurrency)

        self._rate_limit = QSpinBox()
        self._rate_limit.setRange(1, 600)
        form.addRow("每分钟请求上限", self._rate_limit)

        self._batch = QSpinBox()
        self._batch.setRange(1, 64)
        form.addRow("单批行数", self._batch)

        self._google_en = QCheckBox("启用 Google 免费接口")
        self._bing_en = QCheckBox("启用 Bing 免费接口")
        form.addRow("", self._google_en)
        form.addRow("", self._bing_en)
        return group

    def _build_overlay_group(self) -> QGroupBox:
        """悬浮窗与 OCR 参数分组"""
        group = QGroupBox("悬浮窗与 OCR")
        form = QFormLayout(group)

        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.1, 1.0)
        self._opacity.setSingleStep(0.05)
        self._opacity.setDecimals(2)
        form.addRow("悬浮窗透明度", self._opacity)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 40)
        form.addRow("悬浮窗字号", self._font_size)

        self._history = QSpinBox()
        self._history.setRange(1, 10)
        form.addRow("悬浮窗历史行数", self._history)

        self._ocr_interval = QDoubleSpinBox()
        self._ocr_interval.setRange(0.2, 5.0)
        self._ocr_interval.setSingleStep(0.1)
        self._ocr_interval.setDecimals(1)
        form.addRow("OCR 间隔（秒）", self._ocr_interval)
        return group

    # ---------- 数据加载与保存 ----------

    def _load_values(self) -> None:
        """从配置回填各控件"""
        conf = self._config
        tconf = conf.get("translate") or {}
        dconf = conf.get("deepseek") or {}
        dlconf = conf.get("deepl") or {}
        lconf = conf.get("local") or {}
        oconf = conf.get("overlay") or {}
        rconf = conf.get("realtime") or {}

        primary = tconf.get("primary", "deepseek")
        idx = self._primary_combo.findData(primary)
        if idx >= 0:
            self._primary_combo.setCurrentIndex(idx)
        self._fallback_list.setEditText(",".join(tconf.get("fallbacks") or []))

        self._ds_key.setText(conf.get_secret("deepseek"))
        self._ds_url.setText(dconf.get("base_url", "https://api.deepseek.com"))
        self._ds_model.setText(dconf.get("model", "deepseek-chat"))
        self._ds_temp.setValue(float(dconf.get("temperature", 0.8)))
        self._ds_max_tokens.setValue(int(dconf.get("max_tokens", 4000)))

        self._dl_key.setText(conf.get_secret("deepl"))
        self._dl_url.setText(dlconf.get("api_url", "https://api-free.deepl.com/v2/translate"))

        self._timeout.setValue(int(tconf.get("timeout", 30)))
        self._retry.setValue(int(tconf.get("max_retry", 2)))
        self._concurrency.setValue(int(tconf.get("concurrency", 4)))
        self._rate_limit.setValue(int(tconf.get("rate_limit_per_min", 60)))
        self._batch.setValue(int(tconf.get("batch_size", 16)))
        self._google_en.setChecked(bool(tconf.get("google_enabled", True)))
        self._bing_en.setChecked(bool(tconf.get("bing_enabled", True)))

        self._opacity.setValue(float(oconf.get("opacity", 0.92)))
        self._font_size.setValue(int(oconf.get("font_size", 16)))
        self._history.setValue(int(oconf.get("history_lines", 3)))

        orconf = conf.get("ocr") or {}
        self._ocr_interval.setValue(float(orconf.get("interval", 0.4)))

        self._local_model_edit.setText(lconf.get("model", "shun89/opus-mt-ja-zh"))
        self._local_endpoint_edit.setText(lconf.get("endpoint", ""))
        self._refresh_local_status()

    def _save(self, silent: bool = False) -> None:
        """保存当前设置到配置。silent 时不弹提示框。"""
        conf = self._config
        fallback_text = self._fallback_list.currentText().strip()
        fallbacks = [s.strip() for s in fallback_text.split(",") if s.strip()]

        conf.set_many(
            "translate",
            {
                "primary": self._primary_combo.currentData() or "deepseek",
                "fallbacks": fallbacks,
                "timeout": self._timeout.value(),
                "max_retry": self._retry.value(),
                "concurrency": self._concurrency.value(),
                "rate_limit_per_min": self._rate_limit.value(),
                "batch_size": self._batch.value(),
                "google_enabled": self._google_en.isChecked(),
                "bing_enabled": self._bing_en.isChecked(),
            },
        )
        conf.set_secret("deepseek", self._ds_key.text().strip())
        conf.set_many(
            "deepseek",
            {
                "base_url": self._ds_url.text().strip() or "https://api.deepseek.com",
                "model": self._ds_model.text().strip() or "deepseek-chat",
                "temperature": self._ds_temp.value(),
                "max_tokens": self._ds_max_tokens.value(),
            },
        )
        conf.set_secret("deepl", self._dl_key.text().strip())
        conf.set_many(
            "deepl",
            {"api_url": self._dl_url.text().strip() or "https://api-free.deepl.com/v2/translate"},
        )
        conf.set_many(
            "local",
            {
                "model": self._local_model_edit.text().strip(),
                "endpoint": self._local_endpoint_edit.text().strip(),
            },
        )
        conf.set_many(
            "overlay",
            {
                "opacity": self._opacity.value(),
                "font_size": self._font_size.value(),
                "history_lines": self._history.value(),
            },
        )
        conf.set("ocr", "interval", self._ocr_interval.value())

        if not silent:
            QMessageBox.information(self, "保存设置", "已保存。")

    def _restore_defaults(self) -> None:
        """恢复默认设置"""
        from ..config import DEFAULT_CONFIG

        self._config.set_many("translate", dict(DEFAULT_CONFIG["translate"]))
        self._config.set_many("deepseek", dict(DEFAULT_CONFIG["deepseek"]))
        self._config.set_many("deepl", dict(DEFAULT_CONFIG["deepl"]))
        self._config.set_many("google", dict(DEFAULT_CONFIG["google"]))
        self._config.set_many("bing", dict(DEFAULT_CONFIG["bing"]))
        self._config.set_many("local", dict(DEFAULT_CONFIG["local"]))
        self._config.set_many("overlay", dict(DEFAULT_CONFIG["overlay"]))
        self._config.set_many("ocr", dict(DEFAULT_CONFIG["ocr"]))
        self._config.set_secret("deepseek", "")
        self._config.set_secret("deepl", "")
        self._load_values()

    # ---------- 引擎测试 ----------

    def _test_engines(self) -> None:
        """测试所有已注册引擎的连接状态"""
        try:
            self._save(silent=True)
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self, "测试失败", "配置保存失败，无法测试。")
            return

        from ..translate.manager import ENGINE_REGISTRY, TranslationManager

        results: list[str] = []
        try:
            manager = TranslationManager(self._config)
            for name in manager.engine_order():
                engine_cls = ENGINE_REGISTRY.get(name)
                if engine_cls is None:
                    continue
                try:
                    ok = engine_cls(self._config).health_check()
                except Exception:  # noqa: BLE001
                    ok = False
                results.append(
                    f"{'✓' if ok else '✗'} {name}: {'连接正常' if ok else '连接失败'}"
                )
        except Exception as exc:  # noqa: BLE001
            results.append(f"✗ 调度器初始化失败：{exc}")

        if not results:
            results.append("未配置任何引擎。")
        QMessageBox.information(self, "引擎测试结果", "\n".join(results))

    def _test_one_engine(self, name: str) -> None:
        """测试单个引擎"""
        try:
            self._save(silent=True)
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self, "测试失败", "配置保存失败，无法测试。")
            return

        from ..translate.manager import ENGINE_REGISTRY

        engine_cls = ENGINE_REGISTRY.get(name)
        if engine_cls is None:
            QMessageBox.warning(self, "测试失败", f"未知引擎：{name}")
            return

        # 临时禁用对应测试按钮，防止重复点击
        btn_name = {"deepseek": "_ds_test_btn", "deepl": "_dl_test_btn", "local": "_local_test_btn"}.get(name)
        btn = getattr(self, btn_name, None) if btn_name else None
        if btn is not None:
            btn.setEnabled(False)
            btn.setText("测试中...")
            btn.repaint()
        try:
            ok = engine_cls(self._config).health_check()
            msg = f"✓ {name}: 连接正常" if ok else f"✗ {name}: 连接失败"
            QMessageBox.information(self, "引擎测试", msg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "引擎测试", f"✗ {name}: {exc}")
        finally:
            if btn is not None:
                btn.setEnabled(True)
                btn.setText("测试此引擎")

    # ---------- 本地模型下载 ----------

    def _download_local_model(self) -> None:
        """后台线程下载本地模型，进度通过轮询定时器反馈。"""
        from ..translate.local_model import download_model

        try:
            self._save(silent=True)
        except Exception:  # noqa: BLE001
            pass

        self._local_download_btn.setEnabled(False)
        self._local_download_btn.setText("下载中...")
        self._local_progress.setValue(0)
        self._local_progress.show()
        self._local_status.setText("正在下载模型...")
        self._local_status.setStyleSheet("color: orange;")
        self._local_status.repaint()

        state: dict = {"done": False, "progress": (0, 0, ""), "error": ""}

        def _update_progress(done: int, total: int, filename: str) -> None:
            """下载线程回调：仅写入共享状态（线程安全，不做 UI 操作）。"""
            state["progress"] = (done, total, filename)

        def _worker() -> None:
            try:
                download_model(self._config, _update_progress)
                state["done"] = True
            except Exception as exc:  # noqa: BLE001
                state["error"] = str(exc)

        self._download_thread = threading.Thread(target=_worker, daemon=True)
        self._download_thread.start()

        from PySide6.QtCore import QTimer

        def _poll() -> None:
            """GUI 线程轮询共享状态并更新 UI；下载结束后停止定时器。"""
            done, total, filename = state["progress"]
            if filename and total > 0:
                percent = int(done * 100 // total)
                self._local_progress.setValue(percent)
                self._local_status.setText(f"正在下载模型... {filename} {percent}%")

            if state["done"]:
                if self._poll_timer is not None:
                    self._poll_timer.stop()
                self._local_download_btn.setEnabled(True)
                self._local_download_btn.setText("下载模型")
                self._refresh_local_status()
                QMessageBox.information(self, "下载完成", "本地模型已下载。")
            elif state["error"]:
                if self._poll_timer is not None:
                    self._poll_timer.stop()
                self._local_download_btn.setEnabled(True)
                self._local_download_btn.setText("下载模型")
                self._local_progress.hide()
                self._local_status.setText("下载失败")
                self._local_status.setStyleSheet("color: red;")
                QMessageBox.warning(self, "下载失败", state["error"])

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(_poll)
        self._poll_timer.start(300)

    def _refresh_local_status(self) -> None:
        """刷新本地模型状态显示"""
        from ..translate.local_model import get_models_dir, is_model_downloaded

        try:
            model = (self._config.get("local") or {}).get("model") or "shun89/opus-mt-ja-zh"
            ok = is_model_downloaded(self._config, model)
        except Exception:  # noqa: BLE001
            ok = False

        self._local_path.setText(get_models_dir(self._config))
        if ok:
            self._local_status.setText("✓ 已下载")
            self._local_status.setStyleSheet("color: green;")
            self._local_download_btn.setText("重新下载")
        else:
            self._local_status.setText("未下载")
            self._local_status.setStyleSheet("color: gray;")
            self._local_download_btn.setText("下载模型")
