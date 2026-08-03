"""OCR 语言包引导对话框

当系统未安装日语 OCR 语言包时，向用户展示分步安装引导：
1. 说明日语 OCR 的重要性
2. 分步指引如何安装 Windows 日语语言包
3. 提供「打开语言设置」快捷按钮（跳转系统设置页）
4. 实时刷新检测状态
"""
from __future__ import annotations

import os
import sys

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

# 安装步骤引导文案（Windows 10/11）
GUIDE_STEPS = """<b>为什么需要日语 OCR？</b>
实时翻译依赖 OCR 识别游戏画面中的日文文字。若未安装日语语言包，
系统只能用中文/英文引擎识别，日文将识别不准甚至无法识别。

<b>如何安装日语语言包（Windows 10 / 11）：</b>
1. 按 <b>Win + I</b> 打开「设置」
2. 进入「时间和语言」→「语言」
3. 点击「添加语言」，搜索并选择「日本語」
4. 语言包下载完成后，回到本页点击「重新检测」

安装完成后，本工具的实时翻译会自动优先使用日语 OCR。"""


class LanguageGuideDialog(QDialog):
    """OCR 语言包安装引导对话框"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR 语言包引导")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._build_ui()
        self.refresh_status()

    # ---------- 界面构建 ----------

    def _build_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 状态横幅：显示日语是否可用
        self._status_label = QLabel()
        self._status_label.setObjectName("bannerTitle")
        layout.addWidget(self._status_label)

        # 引导步骤说明
        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setHtml(GUIDE_STEPS)
        guide.setMinimumHeight(240)
        guide.setMaximumHeight(320)
        layout.addWidget(guide)

        # 当前可用语言
        self._langs_label = QLabel()
        self._langs_label.setObjectName("subtitleLabel")
        self._langs_label.setWordWrap(True)
        layout.addWidget(self._langs_label)

        # 底部操作按钮
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

    # ---------- 行为 ----------

    def refresh_status(self) -> None:
        """刷新日语 OCR 可用状态与当前语言列表"""
        status = ocr.detect_ocr_status()
        if status["ja_available"]:
            self._status_label.setObjectName("statusOk")
            self._status_label.setText("✓ 日语 OCR 引擎已就绪")
        else:
            self._status_label.setObjectName("statusWarn")
            self._status_label.setText("未检测到日语 OCR，请按下方步骤安装语言包")
        # 动态更新样式
        self._status_label.setStyleSheet(
            "color: #16a34a; font-weight: bold;"
            if status["ja_available"]
            else "color: #d97706; font-weight: bold;"
        )

        langs = status["available_langs"]
        if langs:
            self._langs_label.setText(f"当前系统已识别的 OCR 语言：{'、'.join(langs)}")
        else:
            self._langs_label.setText("当前系统未检测到任何可用的 OCR 语言。")

    def _open_language_settings(self) -> None:
        """打开 Windows 语言设置页面（ms-settings 协议）"""
        try:
            if sys.platform == "win32":
                # Windows 11 用 language，Win10 用 regionlanguage；先尝试前者
                os.startfile("ms-settings:language")
            else:
                self._show_fallback_hint()
        except Exception:  # noqa: BLE001
            try:
                os.startfile("ms-settings:regionlanguage")
            except Exception:  # noqa: BLE001
                self._show_fallback_hint()

    def _show_fallback_hint(self) -> None:
        """打开失败时的文字提示"""
        QMessageBox.information(
            self,
            "手动打开",
            "请手动打开：设置 → 时间和语言 → 语言 → 添加语言 → 日本語",
        )
