"""Google 免费翻译接口引擎

使用 translate.googleapis.com 的免费接口，无需 API Key。
仅供个人学习使用，稳定性一般，失败由降级调度兜底。
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests

from .base import TranslationEngine, TranslateError


class GoogleEngine(TranslationEngine):
    """Google 免费翻译引擎"""

    name = "google"
    needs_key = False

    _URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, config: Any, glossary: Any | None = None) -> None:
        super().__init__(config, glossary)
        self.timeout = config.get("translate", "timeout", 30)
        self._session = requests.Session()

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        # Google 目标语言码
        target = "zh-CN" if target_lang.lower().startswith("zh") else target_lang
        # 用空行分隔合并请求（Google 会按行分段返回）
        joined = "\n".join(texts)
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": quote(joined, safe=""),
        }
        try:
            resp = self._session.get(self._URL, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"Google 网络请求失败：{exc}") from exc

        if resp.status_code != 200:
            raise TranslateError(f"Google 接口异常状态码 {resp.status_code}")

        try:
            data = resp.json()
            translated = "".join(seg[0] for seg in data[0] if seg and seg[0])
        except (ValueError, IndexError, TypeError) as exc:
            raise TranslateError("Google 返回内容格式异常") from exc

        # Google 合并翻译后行数可能与原文不一致，按行数对齐补齐
        parts = translated.split("\n")
        if len(parts) == len(texts):
            return parts
        # 数量不匹配时做启发式对齐
        result = []
        for i, text in enumerate(texts):
            if i < len(parts):
                result.append(parts[i])
            else:
                result.append("")
        return result
