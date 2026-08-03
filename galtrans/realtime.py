"""实时翻译核心：后台线程 OCR → 去重 → 翻译 → 回调。"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable

from .ocr import OcrError, capture_region, ocr_image

# 回调类型
ResultCb = Callable[[str, str], None]   # (原文, 译文)
StatusCb = Callable[[str], None]        # (状态消息)

# 日文假名范围（用于检测译文是否仍为日文）
_JAPANESE_RANGES = [(0x3040, 0x309F), (0x30A0, 0x30FF)]


def _looks_translated(text: str) -> bool:
    """粗略判断文本是否已被翻译成非日文（逐字符，跳过标点）。"""
    import unicodedata

    for ch in text:
        if unicodedata.category(ch).startswith("P"):
            continue
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _JAPANESE_RANGES):
            return False
    return True


def normalize_text(text: str) -> str:
    """清洗 OCR 文本：去行首尾空白与空行。"""
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


class RealtimeSession:
    """实时翻译会话（运行在后台线程）。"""

    def __init__(
        self,
        translator: Any,
        bbox: tuple[int, int, int, int],
        interval: float = 0.4,
        on_result: ResultCb | None = None,
        on_status: StatusCb | None = None,
        ocr_func: Callable[[], str] | None = None,
    ) -> None:
        self.translator = translator
        self.bbox = bbox
        self.interval = interval
        self._on_result = on_result
        self._on_status = on_status
        if ocr_func is None:
            self._ocr_func: Callable[[], str] = lambda: ocr_image(capture_region(bbox), "ja")
        else:
            self._ocr_func = ocr_func
        self._stop_event = threading.Event()
        self._last_text: str | None = None
        self._error_streak = 0
        self._last_fail_msg: str | None = None
        self._last_empty_emitted = False

    def request_stop(self) -> None:
        """请求停止会话。"""
        self._stop_event.set()

    def _emit_status(self, message: str) -> None:
        """带时间戳发出状态消息。"""
        if self._on_status is not None:
            stamp = datetime.now().strftime("%H:%M:%S")
            self._on_status(f"[{stamp}] {message}")

    def _sleep_interval(self) -> None:
        """可中断的间隔睡眠。"""
        self._stop_event.wait(self.interval)

    def _handle_ocr_error(self, exc: Exception) -> None:
        """OCR 错误提示（首次报错，避免刷屏）。"""
        self._error_streak += 1
        if self._error_streak == 1:
            self._emit_status(f"OCR 失败：{exc}")

    def _handle_empty(self) -> None:
        """屏幕无文本时重置状态，并首次提示。"""
        self._error_streak = 0
        self._last_text = None
        if not self._last_empty_emitted:
            self._last_empty_emitted = True
            self._emit_status("OCR 区域未识别到文字，请确认框选了游戏文本区域")

    def _on_error(self, message: str, detail: str) -> None:
        """翻译失败回调（去重上报）。"""
        full = f"{message}: {detail}"
        if full != self._last_fail_msg:
            self._last_fail_msg = full
            self._emit_status(f"翻译失败: {message}（{detail}）")

    def _translate(self, text: str) -> str:
        """翻译单条文本，失败时返回原文并提示。"""
        try:
            result = self.translator.translate_batch([text], on_error=self._on_error)
            translated = result[0] if result else text
            if translated == text and not _looks_translated(text):
                self._emit_status("译文与原文相同（翻译可能失败），请检查引擎配置")
            return translated
        except Exception as exc:  # noqa: BLE001
            self._on_error("翻译异常", str(exc))
            return text

    def _handle_new_text(self, text: str) -> None:
        """处理新文本：翻译并回调。"""
        self._error_streak = 0
        self._last_empty_emitted = False
        self._last_text = text
        translated = self._translate(text)
        if self._on_result is not None:
            self._on_result(text, translated)

    def run(self) -> None:
        """主循环：OCR → 清洗 → 去重 → 翻译。"""
        while not self._stop_event.is_set():
            try:
                raw = self._ocr_func()
            except OcrError as exc:
                self._handle_ocr_error(exc)
                self._sleep_interval()
                continue
            text = normalize_text(raw)
            if not text:
                self._handle_empty()
            elif text != self._last_text:
                self._handle_new_text(text)
            self._sleep_interval()
