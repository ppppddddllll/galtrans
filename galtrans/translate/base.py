"""翻译引擎基类与公共异常。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TranslateError(Exception):
    """翻译过程中发生的错误。"""


class TranslationEngine(ABC):
    """翻译引擎抽象基类。"""

    name: str = "base"
    needs_key: bool = False

    def __init__(self, config: Any, glossary: Any = None) -> None:
        self.config = config
        self.glossary = glossary

    @abstractmethod
    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译，返回与输入等长的译文列表。"""

    @staticmethod
    def _apply_glossary(text: str, glossary: Any) -> str:
        """对单条文本应用术语表（未启用时原样返回）。"""
        if glossary is None or not getattr(glossary, "enabled", False):
            return text
        return glossary.apply_glossary(text)

    def health_check(self) -> bool:
        """自检：尝试翻译一条测试文本。"""
        try:
            self.translate_batch(["テスト"], "zh-CN")
            return True
        except Exception:  # noqa: BLE001
            return False
