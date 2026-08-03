"""DeepL 免费 API 翻译引擎

官方免费版 https://api-free.deepl.com，需注册获取 API Key。
单次请求最大 50 条文本。
"""
from __future__ import annotations

from typing import Any

import requests

from .base import TranslationEngine, TranslateError


class DeepLEngine(TranslationEngine):
    """DeepL 翻译引擎"""

    name = "deepl"
    needs_key = True

    def __init__(self, config: Any, glossary: Any | None = None) -> None:
        super().__init__(config, glossary)
        conf = config.get("deepl")
        self.api_key = config.get_secret("deepl") or conf.get("api_key", "")
        self.api_url = conf.get("api_url", "https://api-free.deepl.com/v2/translate")
        self.timeout = config.get("translate", "timeout", 30)

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        if not self.api_key:
            raise TranslateError("DeepL 未配置 API Key，请在设置中填写")

        # DeepL 的目标语言码格式（JA->ZH 需要 ZH）
        target = "ZH" if target_lang.lower().startswith("zh") else target_lang.upper()

        params = {
            "auth_key": self.api_key,
            "target_lang": target,
            "text": texts[:50],  # DeepL 单请求上限 50 条
        }
        try:
            resp = requests.post(self.api_url, data=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"DeepL 网络请求失败：{exc}") from exc

        if resp.status_code == 403:
            raise TranslateError("DeepL API Key 无效或已过期")
        if resp.status_code == 429:
            raise TranslateError("DeepL 请求次数已用尽（免费版每月 50 万字符）")
        if resp.status_code != 200:
            raise TranslateError(f"DeepL 接口异常状态码 {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            return [item["text"] for item in data["translations"]]
        except (ValueError, KeyError) as exc:
            raise TranslateError("DeepL 返回内容格式异常") from exc
