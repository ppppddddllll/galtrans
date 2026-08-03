"""DeepSeek 引擎：基于 LLM 的高质量 Galgame 翻译。"""
from __future__ import annotations

import re
from typing import Any

import requests

from .base import TranslateError, TranslationEngine

# 翻译系统提示词（保留占位符、语气口癖、逐句对应、术语表）
SYSTEM_PROMPT = """你是一名专业的 Galgame（美少女游戏）日译中翻译。翻译要求：
1. 保留所有占位符原样输出，例如 {name}、[label]、%s、变量名等，不得改动或翻译。
2. 保持角色的语气、口癖、称呼风格（如 あたし→我、お前→你/你这家伙），口语化自然。
3. 逐条对应翻译，输出格式严格为「序号: 译文」，每条独立一行，数量与输入完全一致。
4. 术语表（若有）中的专名必须使用给定中文译名，不得自行更改。
5. 不要添加任何解释、注释或额外内容。"""

_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]|%[sd]")
_PLACEHOLDER_TOKEN = "《《《{idx}》》》"
_FORMAT_RETRY = 2


def _protect_placeholders(texts: list[str]) -> tuple[list[str], list[str]]:
    """把占位符替换为唯一标记，返回（保护后文本, 标记列表）。"""
    protected: list[str] = []
    markers: list[str] = []
    for text in texts:
        counter = 0

        def _replace(match: re.Match) -> str:
            nonlocal counter
            marker = _PLACEHOLDER_TOKEN.format(idx=len(markers))
            markers.append(match.group(0))
            counter += 1
            return marker

        protected.append(_PLACEHOLDER_RE.sub(_replace, text))
    return protected, markers


def _restore_placeholders(text: str, markers: list[str]) -> str:
    """把标记还原为原始占位符。"""
    for idx, marker in enumerate(markers):
        text = text.replace(_PLACEHOLDER_TOKEN.format(idx=idx), marker)
    return text


def _verify_placeholders(originals: list[str], translated: list[str]) -> None:
    """校验译文与原文占位符一致性。"""
    if len(originals) != len(translated):
        raise ValueError("译文行数与原文不一致")
    for orig, trans in zip(originals, translated):
        orig_tokens = set(_PLACEHOLDER_RE.findall(orig))
        trans_tokens = set(_PLACEHOLDER_RE.findall(trans))
        if orig_tokens != trans_tokens:
            raise ValueError("占位符不一致")


def _build_user_prompt(texts: list[str], target_lang: str, glossary: Any) -> str:
    """构建用户提示词（「序号: 内容」格式 + 术语表注入）。"""
    lines = []
    glossary_block = ""
    if glossary is not None and getattr(glossary, "enabled", False):
        pairs = glossary.pairs()
        if pairs:
            entries = "；".join(f"{jp}={cn}" for jp, cn in pairs)
            glossary_block = f"\n术语表（必须使用以下译名）：{entries}\n"
    for idx, text in enumerate(texts, start=1):
        lines.append(f"{idx}: {text}")
    return f"目标语言：{target_lang}{glossary_block}\n" + "\n".join(lines)


def _parse_response(raw: str, expected_count: int) -> list[str]:
    """解析「序号: 译文」响应；兜底按行拆分。"""
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    result: list[str] = []
    for line in lines:
        match = re.match(r"^\s*(\d+)\s*[:：]\s*(.*)$", line)
        if match:
            result.append(match.group(2).strip())
    if len(result) >= expected_count:
        return result[:expected_count]
    # 兜底：直接按行
    fallback = [ln.split(":", 1)[-1].strip() for ln in lines if ":" in ln]
    if len(fallback) >= expected_count:
        return fallback[:expected_count]
    raise ValueError("响应格式无法解析")


class DeepSeekEngine(TranslationEngine):
    """DeepSeek Chat API 翻译引擎。"""

    name = "deepseek"
    needs_key = True

    def __init__(self, config: Any, glossary: Any = None) -> None:
        super().__init__(config, glossary)
        conf = config.get("deepseek") or {}
        self.api_key = config.get_secret("deepseek") or conf.get("api_key", "")
        self.base_url = (conf.get("base_url") or "https://api.deepseek.com").rstrip("/")
        self.model = conf.get("model", "deepseek-chat")
        self.temperature = float(conf.get("temperature", 0.8))
        self.max_tokens = int(conf.get("max_tokens", 4000))
        self.timeout = int((config.get("translate") or {}).get("timeout", 30))

    def _chat(self, system: str, user: str) -> str:
        """调用 Chat Completions 接口，返回内容文本。"""
        if not self.api_key:
            raise TranslateError("DeepSeek 未配置 API Key")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"DeepSeek 请求失败：{exc}") from exc
        if resp.status_code == 401:
            raise TranslateError("DeepSeek API Key 无效")
        if resp.status_code == 429:
            raise TranslateError("DeepSeek 请求过于频繁（429）")
        if resp.status_code != 200:
            raise TranslateError(f"DeepSeek 接口异常状态码 {resp.status_code}")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslateError("DeepSeek 响应格式异常") from exc

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译（含占位符保护、格式校验与重试）。"""
        cleaned = [(text or "").strip() for text in texts]
        protected, markers = _protect_placeholders(cleaned)
        prompt = _build_user_prompt(protected, target_lang, self.glossary)

        last_error: Exception | None = None
        for _ in range(_FORMAT_RETRY + 1):
            raw = self._chat(SYSTEM_PROMPT, prompt)
            try:
                parsed = _parse_response(raw, len(cleaned))
                translated = [_restore_placeholders(p, markers) for p in parsed]
                _verify_placeholders(cleaned, translated)
                return translated
            except (ValueError, TranslateError) as exc:
                last_error = exc
        raise TranslateError(f"DeepSeek 响应解析失败：{last_error}")
