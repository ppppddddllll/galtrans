"""OCR 语言包安装引导对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .. import ocr

# 安装步骤文案（HTML）
GUIDE_STEPS = """
<h3>安装日语 OCR 语言包</h3>
<p>Windows 内置 OCR 需要安装对应语言的识别包，日语 OCR 用于识别游戏画面中的日文文本。</p>
<ol>
    <li>按 <b>Win + I</b> 打开「设置」</li>
    <li>进入「<b>时间和语言</b>」→「<b>语言</b>」</li>
    <li>点击「<b>添加语言</b>」，搜索并选择「<b>日本語</b>」</li>
    <li>安装完成后返回本页，点击「<b>重新检测</b>」</li>
</ol>
<p>如果没有日语语言包，OCR 会自动回退到已安装的中文语言，识别日文效果会受限。</p>
"""


class LanguageGuideDialog(QDialog):
    """OCR 语言包安装引导对话框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR 语言包引导")
        self.setMinimumWidth(560)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        """构建界面。"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._status_label = QLabel()
        self._status_label.setObjectName("bannerTitle")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setHtml(GUIDE_STEPS)
        guide.setMinimumHeight(240)
        layout.addWidget(guide)

        self._langs_label = QLabel()
        self._langs_label.setObjectName("subtitleLabel")
        self._langs_label.setWordWrap(True)
        layout.addWidget(self._langs_label)

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton("打开 Windows 语言设置")
        self._open_btn.clicked.connect(self._open_language_settings)
        self._retest_btn = QPushButton("重新检测")
        self._retest_btn.clicked.connect(self.refresh_status)
        self._close_btn = QPushButton("关闭")
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._open_btn)
        btn_row.addWidget(self._retest_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def refresh_status(self) -> None:
        """刷新当前 OCR 语言可用状态。"""
        try:
            status = ocr.detect_ocr_status()
            if status.get("ja_available"):
                self._status_label.setText("✓ 日语 OCR 引擎已就绪")
                self._status_label.setStyleSheet("color: #16a34a;")
            else:
                self._status_label.setText("⚠ 未检测到日语 OCR，请按下方步骤安装语言包")
                self._status_label.setStyleSheet("color: #d97706;")
            langs = status.get("available_langs") or []
            if langs:
                self._langs_label.setText(f"当前可用 OCR 语言：{', '.join(langs)}")
            else:
                self._langs_label.setText("当前系统未检测到任何可用的 OCR 语言。")
        except Exception:  # noqa: BLE001
            self._status_label.setText("⚠ 无法检测 OCR 组件状态")
            self._status_label.setStyleSheet("color: #ef4444;")

    def _open_language_settings(self) -> None:
        """打开 Windows 语言设置页面。"""
        import os

        for uri in ("ms-settings:language", "ms-settings:regionlanguage"):
            try:
                os.startfile(uri)  # noqa: S606
                return
            except OSError:
                continue
        self._show_fallback_hint()

    def _show_fallback_hint(self) -> None:
        """打开设置失败时的提示。"""
        QMessageBox.information(
            self,
            "手动打开",
            "无法自动打开系统设置，请按 Win + I 手动打开「设置 → 时间和语言 → 语言」，"
            "然后添加「日本語」语言。",
        )
