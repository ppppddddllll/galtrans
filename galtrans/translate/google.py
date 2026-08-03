"""Google 翻译免费接口（无需 Key，稳定性依赖网络环境）。"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from .base import TranslateError, TranslationEngine


class GoogleEngine(TranslationEngine):
    """Google Translate Web 免费接口。"""

    name = "google"
    needs_key = False

    _URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, config: Any, glossary: Any = None) -> None:
        super().__init__(config, glossary)
        self.timeout = int((config.get("translate") or {}).get("timeout", 30))

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译（多行合并一次请求，行数对齐）。"""
        target = "zh-CN" if target_lang.lower().startswith("zh") else target_lang
        cleaned = [(t or "").strip() for t in texts]
        joined = "\n".join(cleaned)
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": quote(joined, safe=""),
        }
        try:
            resp = requests.get(self._URL, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"Google 请求失败：{exc}") from exc
        if resp.status_code != 200:
            raise TranslateError(f"Google 接口异常状态码 {resp.status_code}")
        try:
            translated = "".join(seg[0] for seg in resp.json()[0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TranslateError("Google 响应格式异常") from exc
        lines = translated.split("\n")
        # 对齐行数：多退少补
        if len(lines) < len(cleaned):
            lines += [""] * (len(cleaned) - len(lines))
        return lines[: len(cleaned)]
