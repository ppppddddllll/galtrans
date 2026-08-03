"""DeepL 翻译引擎（免费 API，需 API Key）。"""
from __future__ import annotations

from typing import Any

import requests

from .base import TranslateError, TranslationEngine


class DeepLEngine(TranslationEngine):
    """DeepL v2 翻译接口。"""

    name = "deepl"
    needs_key = True

    def __init__(self, config: Any, glossary: Any = None) -> None:
        super().__init__(config, glossary)
        conf = config.get("deepl") or {}
        self.api_key = config.get_secret("deepl") or conf.get("api_key", "")
        self.api_url = conf.get("api_url", "https://api-free.deepl.com/v2/translate")

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译（单条请求，最多 50 条）。"""
        if not self.api_key:
            raise TranslateError("DeepL 未配置 API Key")
        target = "ZH" if target_lang.lower().startswith("zh") else target_lang.upper()
        results: list[str] = []
        for text in texts[:50]:
            text = (text or "").strip()
            if not text:
                results.append("")
                continue
            if self.glossary is not None:
                text = self._apply_glossary(text, self.glossary)
            data = {"auth_key": self.api_key, "target_lang": target, "text": text}
            try:
                resp = requests.post(self.api_url, data=data, timeout=30)
            except requests.RequestException as exc:
                raise TranslateError(f"DeepL 请求失败：{exc}") from exc
            if resp.status_code == 403:
                raise TranslateError("DeepL API Key 无效")
            if resp.status_code == 429:
                raise TranslateError("DeepL 请求过于频繁（429）")
            if resp.status_code != 200:
                raise TranslateError(f"DeepL 接口异常状态码 {resp.status_code}")
            try:
                results.append(resp.json()["translations"][0]["text"])
            except (KeyError, IndexError, ValueError) as exc:
                raise TranslateError("DeepL 响应格式异常") from exc
        return results
