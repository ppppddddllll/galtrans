"""设置页面

编辑翻译引擎、请求参数与界面相关的配置。
保存后写入 config.json，下次任务生效。
"""
from __future__ import annotations

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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# 可选引擎名称（与 ENGINE_REGISTRY 对应）
ENGINE_NAMES = ["deepseek", "deepl", "google", "bing"]
ENGINE_LABELS = {
    "deepseek": "DeepSeek（需 API Key，推荐）",
    "deepl": "DeepL（需 API Key）",
    "google": "Google 免费接口",
    "bing": "Bing 免费接口",
}


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, config) -> None:
        super().__init__()
        self._config = config
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
        layout.addWidget(self._build_deepseek_group())
        layout.addWidget(self._build_deepl_group())
        layout.addWidget(self._build_requests_group())
        layout.addWidget(self._build_overlay_group())
        layout.addStretch(1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("保存设置")
        self._save_btn.clicked.connect(self._save)
        self._reset_btn = QPushButton("恢复默认")
        self._reset_btn.clicked.connect(self._restore_defaults)
        btn_row.addStretch(1)
        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        scroll.setWidget(body)

    def _build_engine_group(self) -> QGroupBox:
        """引擎选择分组"""
        group = QGroupBox("翻译引擎")
        form = QFormLayout(group)

        self._primary_combo = QComboBox()
        for name in ENGINE_NAMES:
            self._primary_combo.addItem(ENGINE_LABELS[name], name)
        form.addRow("首选引擎", self._primary_combo)

        # 降级顺序（多选）
        self._fallback_list = self._make_fallback_list()
        form.addRow("降级引擎（多选）", self._fallback_list)

        hint = QLabel("按优先级顺序尝试：首选失败后依次降级，全部失败返回原文。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("", hint)

        # Token 计费提示
        token_hint = QLabel(
            "提示：仅 DeepSeek 按 Token 计费；Google / Bing / DeepL 免费接口不消耗 Token。"
            "软件内置翻译缓存，相同句子只翻译一次。"
        )
        token_hint.setWordWrap(True)
        token_hint.setStyleSheet("color: gray;")
        form.addRow("", token_hint)

        # 测试按钮
        self._test_btn = QPushButton("测试所有引擎连接")
        self._test_btn.clicked.connect(self._test_engines)
        form.addRow("", self._test_btn)
        return group

    def _make_fallback_list(self):
        """构建引擎多选列表（受控件类型约束用 QComboBox 模拟）"""
        combo = QComboBox()
        combo.setEditable(True)
        combo.setPlaceholderText("直接输入引擎名，逗号分隔（deepseek,deepl,google,bing）")
        return combo

    def _build_deepseek_group(self) -> QGroupBox:
        """DeepSeek 配置分组"""
        group = QGroupBox("DeepSeek 配置")
        form = QFormLayout(group)
        self._ds_key = QLineEdit()
        self._ds_key.setEchoMode(QLineEdit.Password)
        self._ds_url = QLineEdit()
        self._ds_model = QLineEdit()
        self._ds_temp = QDoubleSpinBox()
        self._ds_temp.setRange(0.0, 2.0)
        self._ds_temp.setSingleStep(0.1)
        self._ds_max_tokens = QSpinBox()
        self._ds_max_tokens.setRange(256, 32768)
        self._ds_max_tokens.setSingleStep(512)

        form.addRow("API Key", self._ds_key)
        form.addRow("Base URL", self._ds_url)
        form.addRow("模型", self._ds_model)
        form.addRow("温度", self._ds_temp)
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
        self._dl_url = QLineEdit()
        form.addRow("API Key", self._dl_key)
        form.addRow("API URL", self._dl_url)

        self._dl_test_btn = QPushButton("测试此引擎")
        self._dl_test_btn.clicked.connect(lambda: self._test_one_engine("deepl"))
        form.addRow("", self._dl_test_btn)
        return group

    def _build_requests_group(self) -> QGroupBox:
        """请求参数分组"""
        group = QGroupBox("翻译请求参数")
        form = QFormLayout(group)

        self._timeout = QSpinBox()
        self._timeout.setRange(5, 120)
        self._retry = QSpinBox()
        self._retry.setRange(0, 5)
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 16)
        self._rate_limit = QSpinBox()
        self._rate_limit.setRange(1, 600)
        self._batch = QSpinBox()
        self._batch.setRange(1, 64)
        self._google_en = QCheckBox("启用 Google 免费接口")
        self._bing_en = QCheckBox("启用 Bing 免费接口")

        form.addRow("请求超时(秒)", self._timeout)
        form.addRow("重试次数", self._retry)
        form.addRow("并发数", self._concurrency)
        form.addRow("每分钟上限", self._rate_limit)
        form.addRow("批量条数", self._batch)
        form.addRow("", self._google_en)
        form.addRow("", self._bing_en)
        return group

    def _build_overlay_group(self) -> QGroupBox:
        """悬浮窗配置分组"""
        group = QGroupBox("实时翻译悬浮窗")
        form = QFormLayout(group)

        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.1, 1.0)
        self._opacity.setSingleStep(0.05)
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 40)
        self._history = QSpinBox()
        self._history.setRange(1, 10)
        self._ocr_interval = QDoubleSpinBox()
        self._ocr_interval.setRange(0.2, 5.0)
        self._ocr_interval.setSingleStep(0.1)

        form.addRow("透明度", self._opacity)
        form.addRow("字号", self._font_size)
        form.addRow("历史行数", self._history)
        form.addRow("OCR 间隔(秒)", self._ocr_interval)
        return group

    # ---------- 加载与保存 ----------

    def _load_values(self) -> None:
        """从配置加载值到控件"""
        conf = self._config
        t = conf.get("translate") or {}
        self._set_combo_value(self._primary_combo, t.get("primary", "deepseek"))
        self._fallback_list.setEditText(", ".join(t.get("fallbacks", [])))

        ds = conf.get("deepseek") or {}
        self._ds_key.setText(conf.get_secret("deepseek"))
        self._ds_url.setText(ds.get("base_url", ""))
        self._ds_model.setText(ds.get("model", ""))
        self._ds_temp.setValue(float(ds.get("temperature", 0.8)))
        self._ds_max_tokens.setValue(int(ds.get("max_tokens", 4000)))

        dl = conf.get("deepl") or {}
        self._dl_key.setText(conf.get_secret("deepl"))
        self._dl_url.setText(dl.get("api_url", ""))

        self._timeout.setValue(int(t.get("timeout", 30)))
        self._retry.setValue(int(t.get("max_retry", 2)))
        self._concurrency.setValue(int(t.get("concurrency", 4)))
        self._rate_limit.setValue(int(t.get("rate_limit_per_min", 60)))
        self._batch.setValue(int(t.get("batch_size", 16)))
        self._google_en.setChecked(bool((conf.get("google") or {}).get("enabled", True)))
        self._bing_en.setChecked(bool((conf.get("bing") or {}).get("enabled", True)))

        ov = conf.get("overlay") or {}
        self._opacity.setValue(float(ov.get("opacity", 0.92)))
        self._font_size.setValue(int(ov.get("font_size", 16)))
        self._history.setValue(int(ov.get("history_lines", 3)))
        self._ocr_interval.setValue(float((conf.get("ocr") or {}).get("interval", 0.8)))

    def _set_combo_value(self, combo: QComboBox, name: str) -> None:
        """按数据值选中下拉项"""
        idx = combo.findData(name)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save(self, silent: bool = False) -> None:
        """保存当前界面值到配置

        参数:
            silent: 为 True 时不弹出成功提示（供引擎测试等场景调用）。
        """
        conf = self._config
        primary = self._primary_combo.currentData()
        fallbacks = [
            s.strip()
            for s in self._fallback_list.currentText().split(",")
            if s.strip()
        ]
        conf.set_many("translate", {
            "primary": primary,
            "fallbacks": fallbacks,
            "timeout": self._timeout.value(),
            "max_retry": self._retry.value(),
            "concurrency": self._concurrency.value(),
            "rate_limit_per_min": self._rate_limit.value(),
            "batch_size": self._batch.value(),
        })
        conf.set_many("deepseek", {
            "base_url": self._ds_url.text().strip(),
            "model": self._ds_model.text().strip(),
            "temperature": self._ds_temp.value(),
            "max_tokens": self._ds_max_tokens.value(),
        })
        conf.set_secret("deepseek", self._ds_key.text().strip())
        conf.set_many("deepl", {
            "api_url": self._dl_url.text().strip(),
        })
        conf.set_secret("deepl", self._dl_key.text().strip())
        conf.set("google", "enabled", self._google_en.isChecked())
        conf.set("bing", "enabled", self._bing_en.isChecked())
        conf.set_many("overlay", {
            "opacity": self._opacity.value(),
            "font_size": self._font_size.value(),
            "history_lines": self._history.value(),
        })
        conf.set("ocr", "interval", self._ocr_interval.value())
        if not silent:
            QMessageBox.information(self, "已保存", "设置已保存，下次任务生效。")

    def _restore_defaults(self) -> None:
        """恢复默认设置"""
        from ..config import DEFAULT_CONFIG

        ret = QMessageBox.question(self, "恢复默认", "确定恢复所有设置为默认值？")
        if ret != QMessageBox.Yes:
            return
        # 直接覆盖深层数据并保存
        for section, values in DEFAULT_CONFIG.items():
            self._config.set_many(section, values)
        # 清空加密存储的密钥
        self._config.set_secret("deepseek", "")
        self._config.set_secret("deepl", "")
        self._load_values()

    # ---------- 引擎测试 ----------

    def _test_engines(self) -> None:
        """测试当前配置的所有可用引擎连接"""
        # 先保存当前界面值，确保用最新配置测试
        try:
            self._save(silent=True)
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self, "测试失败", "配置读取失败，无法测试。")
            return

        from ..translate import TranslationManager

        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")
        # 强制界面刷新，避免按钮状态卡顿
        self._test_btn.repaint()

        results: list[str] = []
        try:
            manager = TranslationManager(self._config)
            order = manager.engine_order() or ["(未启用任何引擎)"]
            for name in order:
                engine_cls = None
                from ..translate.manager import ENGINE_REGISTRY

                engine_cls = ENGINE_REGISTRY.get(name)
                if engine_cls is None:
                    results.append(f"✗ {name}: 未知引擎")
                    continue
                try:
                    engine = engine_cls(self._config)
                    ok = engine.health_check()
                    results.append(f"{'✓' if ok else '✗'} {name}: {'连接正常' if ok else '连接失败'}")
                except Exception as exc:  # noqa: BLE001
                    results.append(f"✗ {name}: {exc}")
        finally:
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试所有引擎连接")

        QMessageBox.information(self, "引擎测试结果", "\n".join(results))

    def _test_one_engine(self, name: str) -> None:
        """测试单个引擎连接"""
        # 先保存当前界面值，确保用最新配置测试
        try:
            self._save(silent=True)
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self, "测试失败", "配置读取失败，无法测试。")
            return

        from ..translate.manager import ENGINE_REGISTRY

        engine_cls = ENGINE_REGISTRY.get(name)
        if engine_cls is None:
            QMessageBox.warning(self, "测试失败", f"未知引擎：{name}")
            return
        # 通用测试按钮引用（用于临时禁用）
        btn = getattr(self, f"_{name[:2]}_test_btn", None)
        if btn is not None:
            btn.setEnabled(False)
            btn.setText("测试中...")
            btn.repaint()
        try:
            engine = engine_cls(self._config)
            ok = engine.health_check()
            msg = f"✓ {name}: 连接正常" if ok else f"✗ {name}: 连接失败"
            QMessageBox.information(self, "引擎测试", msg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "引擎测试", f"✗ {name}: {exc}")
        finally:
            if btn is not None:
                btn.setEnabled(True)
                btn.setText("测试此引擎")
