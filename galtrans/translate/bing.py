"""Bing 免费翻译接口引擎

使用微软 Edge 翻译的公开接口，无需 API Key，无需登录。
稳定性尚可，失败由降级调度兜底。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import requests

from .base import TranslationEngine, TranslateError


class BingEngine(TranslationEngine):
    """Bing 免费翻译引擎"""

    name = "bing"
    needs_key = False

    _URL = "https://api-edge.cognitive.microsofttranslator.com/translate"

    def __init__(self, config: Any, glossary: Any | None = None) -> None:
        super().__init__(config, glossary)
        self.timeout = config.get("translate", "timeout", 30)
        self._session = requests.Session()

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        target = "zh-Hans" if target_lang.lower().startswith("zh") else target_lang

        body = [{"Text": t} for t in texts]
        headers = {
            "Content-Type": "application/json",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        params = {
            "api-version": "3.0",
            "to": target,
            "from": "ja",
        }
        try:
            resp = self._session.post(
                self._URL, params=params, headers=headers, json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise TranslateError(f"Bing 网络请求失败：{exc}") from exc

        if resp.status_code == 429:
            raise TranslateError("Bing 请求过于频繁，请稍后再试")
        if resp.status_code != 200:
            raise TranslateError(f"Bing 接口异常状态码 {resp.status_code}")

        try:
            data = resp.json()
            results = []
            for item in data:
                if item.get("translations"):
                    results.append(item["translations"][0]["text"])
                else:
                    results.append("")
            return results
        except (ValueError, KeyError, IndexError) as exc:
            raise TranslateError("Bing 返回内容格式异常") from exc
