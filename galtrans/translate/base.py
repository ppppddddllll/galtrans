"""翻译引擎抽象基类

所有翻译引擎实现 `translate_batch` 方法，返回与输入等长的译文列表。
接口设计为批量形式，便于合并请求、降低延迟。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TranslateError(Exception):
    """翻译失败（网络/限流/密钥错误等）"""


class TranslationEngine(ABC):
    """翻译引擎基类"""

    #: 引擎唯一标识，用于配置与日志
    name = "base"

    #: 是否需要在配置中提供密钥
    needs_key = False

    def __init__(self, config: Any, glossary: Any | None = None) -> None:
        self.config = config
        self.glossary = glossary  # 术语表对象，可能为 None

    @abstractmethod
    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译文本列表，返回译文列表

        注意：必须保持顺序与输入一致；失败时抛 TranslateError。
        """
        raise NotImplementedError

    # ---------- 工具方法 ----------

    @staticmethod
    def _apply_glossary(text: str, glossary: Any | None) -> str:
        """翻译前用术语表做预替换，降低 LLM 对专名的自由发挥"""
        if glossary is None or not glossary.enabled:
            return text
        return glossary.apply_glossary(text)

    def health_check(self) -> bool:
        """轻量自检，用于降级调度时跳过不可用引擎"""
        try:
            self.translate_batch(["テスト"], "zh-CN")
            return True
        except Exception:
            return False
