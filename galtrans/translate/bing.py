"""Bing 免费翻译接口（无需 Key，速度快）。"""
from __future__ import annotations

import uuid
from typing import Any

import requests

from .base import TranslateError, TranslationEngine


class BingEngine(TranslationEngine):
    """Bing/Microsoft Translator edge 免费接口。"""

    name = "bing"
    needs_key = False

    _URL = "https://api-edge.cognitive.microsofttranslator.com/translate"

    def __init__(self, config: Any, glossary: Any = None) -> None:
        super().__init__(config, glossary)
        self.timeout = int((config.get("translate") or {}).get("timeout", 30))

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译（JSON 数组一次请求）。"""
        target = "zh-Hans" if target_lang.lower().startswith("zh") else target_lang
        cleaned = [(t or "").strip() for t in texts]
        payload = [{"Text": t} for t in cleaned]
        params = {"api-version": "3.0", "to": target, "from": "ja"}
        headers = {"X-ClientTraceId": str(uuid.uuid4()), "Content-Type": "application/json"}
        try:
            resp = requests.post(self._URL, json=payload, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"Bing 请求失败：{exc}") from exc
        if resp.status_code == 429:
            raise TranslateError("Bing 请求过于频繁（429）")
        if resp.status_code != 200:
            raise TranslateError(f"Bing 接口异常状态码 {resp.status_code}")
        try:
            items = resp.json()
            return [item["translations"][0]["text"] for item in items]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TranslateError("Bing 响应格式异常") from exc
