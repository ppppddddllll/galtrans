"""实时翻译核心模块。

在后台线程中循环执行：截屏指定区域 → OCR 识别文本 → 与上次结果去重
比较 → 调用翻译引擎 → 通过回调推送译文。停止通过 threading.Event 控制。
"""

from __future__ import annotations

import threading
import time
import unicodedata
from typing import Callable, Optional

from .ocr import OcrError, capture_region, ocr_image

# 回调类型：原文 -> 译文
ResultCb = Callable[[str, str], None]
# 状态回调：消息
StatusCb = Callable[[str], None]

# 日文字符区间（用于判断文本是否仍是日文原文）
_JAPANESE_RANGES = [
    (0x3040, 0x309F),  # 平假名
    (0x30A0, 0x30FF),  # 片假名
]


def _looks_translated(text: str) -> bool:
    """粗略判断文本是否已不是纯日文原文（出现非日文字符即视为可能已翻译）。"""
    for ch in text:
        code = ord(ch)
        if unicodedata.category(ch).startswith("P"):
            continue
        in_jp = any(lo <= code <= hi for lo, hi in _JAPANESE_RANGES)
        if not in_jp:
            # 是汉字/字母/数字/其他 → 视为已翻译
            return True
    return False


def normalize_text(text: str) -> str:
    """清洗 OCR 文本：去除每行首尾空白、丢弃空行、压缩重复空行。"""
    lines = [line.strip() for line in text.splitlines()]
    cleaned = []
    for line in lines:
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


class RealtimeSession:
    """实时翻译会话。

    属性:
        translator: TranslationManager 实例。
        bbox: (left, top, right, bottom) 截屏区域。
        interval: 轮询间隔（秒）。
        on_result: 新译文回调 (原文, 译文)。
        on_status: 状态消息回调。
        stop_event: 外部可调用 request_stop() 触发。
    """

    def __init__(
        self,
        translator,
        bbox: tuple,
        interval: float = 0.8,
        on_result: Optional[ResultCb] = None,
        on_status: Optional[StatusCb] = None,
        ocr_func: Optional[Callable[[], str]] = None,
    ) -> None:
        self.translator = translator
        self.bbox = bbox
        self.interval = interval
        self.on_result = on_result
        self.on_status = on_status
        # 可注入的 OCR 函数，便于测试；默认走真实截图识别
        self._ocr_func = ocr_func or (lambda: ocr_image(capture_region(bbox), "ja"))
        self._stop_event = threading.Event()
        # 上次原文与译文，用于去重
        self._last_text: Optional[str] = None
        self._last_translated: Optional[str] = None
        # 连续 OCR 失败计数，用于状态提示
        self._error_streak = 0
        # 上次翻译失败信息，用于去重提示
        self._last_fail_msg: Optional[str] = None

    def request_stop(self) -> None:
        """请求停止循环。"""
        self._stop_event.set()

    def _emit_status(self, message: str) -> None:
        """发送状态消息（带时间戳）。"""
        if self.on_status is not None:
            ts = time.strftime("%H:%M:%S")
            self.on_status(f"[{ts}] {message}")

    def run(self) -> None:
        """主循环，阻塞直到 request_stop 被调用。

        每次轮询：截屏区域 → OCR → 清洗 → 若与上次原文不同则翻译。
        """
        self._emit_status("实时翻译已启动")
        while not self._stop_event.is_set():
            try:
                text = self._ocr_once()
            except OcrError as exc:
                self._handle_ocr_error(exc)
                self._sleep_interval()
                continue

            text = normalize_text(text)
            if not text:
                self._handle_empty()
                self._sleep_interval()
                continue

            if text != self._last_text:
                self._handle_new_text(text)
            self._sleep_interval()

        self._emit_status("实时翻译已停止")

    def _ocr_once(self) -> str:
        """执行一次截图与 OCR。"""
        return self._ocr_func()

    def _handle_ocr_error(self, exc: OcrError) -> None:
        """处理 OCR 失败：累积计数，首次报错提示，避免刷屏。"""
        self._error_streak += 1
        if self._error_streak == 1:
            self._emit_status(f"OCR 失败: {exc}")

    def _handle_empty(self) -> None:
        """OCR 结果为空：重置错误计数，不触发翻译。"""
        self._error_streak = 0
        if self._last_text is not None:
            # 画面文本消失，保留上一次译文不推送
            self._last_text = None

    def _handle_new_text(self, text: str) -> None:
        """新文本出现：调用翻译并回调推送。"""
        self._error_streak = 0
        self._last_text = text
        try:
            translated = self._translate(text)
        except Exception as exc:  # noqa: BLE001
            translated = text
            self._emit_status(f"翻译失败: {exc}")
        self._last_translated = translated
        if self.on_result is not None:
            self.on_result(text, translated)

    def _translate(self, text: str) -> str:
        """调用翻译引擎。单条文本通过 manager 批量接口翻译。

        翻译失败时上报原因（去重，同一原因只提示一次），返回原文。
        """
        failures: list[str] = []

        def _on_error(_name: str, message: str) -> None:
            if message and message not in failures:
                failures.append(message)
            if self.on_status is not None:
                ts = time.strftime("%H:%M:%S")
                # 去重：与上次失败信息相同则不重复上报
                if message != getattr(self, "_last_fail_msg", None):
                    self._last_fail_msg = message
                    self.on_status(f"[{ts}] 翻译失败: {message}")

        results = self.translator.translate_batch([text], on_error=_on_error)
        if not results:
            return text
        # 引擎失败时结果与原文相同，且记录到了失败信息 → 明确标记失败
        result = results[0]
        if result == text and failures and not _looks_translated(result):
            if self.on_status is not None:
                self.on_status("译文与原文相同（翻译可能失败），请检查引擎配置")
        return result

    def _sleep_interval(self) -> None:
        """按间隔睡眠，支持中途被停止。"""
        self._stop_event.wait(self.interval)
