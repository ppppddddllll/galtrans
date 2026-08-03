"""DeepSeek 大语言模型翻译引擎

使用 OpenAI 兼容的 chat/completions 接口。
针对 Galgame 场景设计了专门的系统提示词，保证：
- 保留占位符（{xxx}、[label]、%s 等）不被改动
- 专有名词（人名、地名、术语）遵循术语表
- 口语化、贴近日系 ACG 语境，避免机翻腔
"""
from __future__ import annotations

import re
from typing import Any

import requests

from .base import TranslationEngine, TranslateError

# 系统提示词：Galgame 翻译规则
SYSTEM_PROMPT = (
    "你是一位专业的日本 Galgame（视觉小说）本地化译者，擅长将日文翻译为简体中文。\n"
    "翻译时必须遵守以下规则：\n"
    "1. 输出只包含译文正文，不添加任何解释、注释或前后缀。\n"
    "2. 保持原文的占位符与标记完全不变，包括但不限于：{名称}、[label]、%s、$var、\\n、变量名等，原样保留。\n"
    "3. 保持说话人的语气与口癖，女性角色、傲娇、关西腔等语言特征需在译文中体现。\n"
    "4. 翻译要口语化、自然，符合中文 ACG 语境，不要生硬直译，不要用翻译腔。\n"
    "5. 专有名词（人名、地名、招式名）使用下方术语表给出的译名；未给出的按通用 ACG 译名处理。\n"
    "6. 多句连续文本保持语序与情绪连贯，逐句对应。\n"
)

# 用于保护占位符的正则（发送前替换，接收后还原，双保险）
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]|%[sd]")

# 格式错误时的重试次数
_FORMAT_RETRY = 2


class DeepSeekEngine(TranslationEngine):
    """基于 DeepSeek 的 LLM 翻译引擎"""

    name = "deepseek"
    needs_key = True

    def __init__(self, config: Any, glossary: Any | None = None) -> None:
        super().__init__(config, glossary)
        conf = config.get("deepseek")
        self.api_key = config.get_secret("deepseek") or conf.get("api_key", "")
        self.base_url = conf.get("base_url", "https://api.deepseek.com").rstrip("/")
        self.model = conf.get("model", "deepseek-chat")
        self.temperature = conf.get("temperature", 0.8)
        self.max_tokens = conf.get("max_tokens", 4000)
        self.timeout = config.get("translate", "timeout", 30)
        self._session = requests.Session()

    def translate_batch(self, texts: list[str], target_lang: str) -> list[str]:
        """批量翻译：单次请求放入多条文本，要求逐行对应返回"""
        if not texts:
            return []
        if not self.api_key:
            raise TranslateError("DeepSeek 未配置 API Key，请在设置中填写")

        # 术语表注入
        prepared = [self._apply_glossary(t, self.glossary) for t in texts]

        # 占位符保护：把动态内容替换为安全标记，防止 LLM 改动
        protected, markers = _protect_placeholders(prepared)

        prompt = _build_user_prompt(protected, target_lang, self.glossary)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(_FORMAT_RETRY):
            try:
                raw = self._chat(messages)
                translated = _parse_response(raw, len(protected))
                # 还原占位符并做占位符一致性校验
                restored = [_restore_placeholders(t, markers) for t in translated]
                _verify_placeholders(protected, restored)
                return restored
            except TranslateError:
                raise
            except Exception as exc:  # 解析/校验失败则重试
                last_error = exc
        raise TranslateError(f"DeepSeek 响应解析失败：{last_error}")

    def _chat(self, messages: list[dict]) -> str:
        """调用 chat/completions 接口，返回回复文本"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslateError(f"DeepSeek 网络请求失败：{exc}") from exc

        if resp.status_code == 401:
            raise TranslateError("DeepSeek API Key 无效或已过期")
        if resp.status_code == 429:
            raise TranslateError("DeepSeek 请求过于频繁（限流），请稍后再试")
        if resp.status_code != 200:
            raise TranslateError(f"DeepSeek 接口返回异常状态码 {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise TranslateError("DeepSeek 返回内容格式异常") from exc


# ---------- 占位符保护逻辑 ----------

_PLACEHOLDER_TOKEN = "《《《{idx}》》》"


def _protect_placeholders(texts: list[str]) -> tuple[list[str], list[str]]:
    """把文本中的动态占位符替换为安全标记，返回(替换后文本, 标记列表)"""
    protected: list[str] = []
    markers: list[str] = []

    def _repl(match: re.Match) -> str:
        token = _PLACEHOLDER_TOKEN.format(idx=len(markers))
        markers.append(match.group(0))
        return token

    for text in texts:
        protected.append(_PLACEHOLDER_RE.sub(_repl, text))
    return protected, markers


def _restore_placeholders(text: str, markers: list[str]) -> str:
    """把 LLM 返回内容中的安全标记还原为原始占位符"""
    for idx, marker in enumerate(markers):
        text = text.replace(_PLACEHOLDER_TOKEN.format(idx=idx), marker)
    return text


def _verify_placeholders(originals: list[str], translated: list[str]) -> None:
    """校验占位符一致性：LLM 可能增删占位符，需抛出异常触发重试"""
    if len(originals) != len(translated):
        raise ValueError("译文行数与原文不一致")

    src_tokens = [_PLACEHOLDER_RE.findall(t) for t in originals]
    dst_tokens = [_PLACEHOLDER_RE.findall(t) for t in translated]
    for i, (src, dst) in enumerate(zip(src_tokens, dst_tokens)):
        if sorted(src) != sorted(dst):
            raise ValueError(f"第 {i} 行占位符不一致：原文 {src}，译文 {dst}")


# ---------- 用户提示词构造 ----------

def _build_user_prompt(texts: list[str], target_lang: str, glossary: Any | None) -> str:
    """构造批量翻译的用户提示词

    使用「标号:内容」格式让模型逐行对应，解析更可靠。
    """
    lines = []
    for idx, text in enumerate(texts):
        # 空行或纯空白不送入，解析时对齐
        lines.append(f"{idx + 1}: {text}")

    glossary_part = ""
    if glossary is not None and glossary.enabled:
        pairs = glossary.pairs()
        if pairs:
            glossary_part = "\n\n术语表：\n" + "\n".join(f"{jp} => {cn}" for jp, cn in pairs)

    return (
        f"请将下面 {len(texts)} 行日文翻译成简体中文（{target_lang}）。"
        f"翻译目标语言：{target_lang}。\n"
        f"要求：逐行翻译，按「序号: 译文」的格式输出，每行一条，不要合并或遗漏任何一行。"
        f"{glossary_part}\n\n待翻译内容：\n" + "\n".join(lines)
    )


# ---------- 响应解析 ----------

def _parse_response(raw: str, expected_count: int) -> list[str]:
    """解析模型返回内容为逐行译文列表"""
    raw = raw.strip()
    # 统一换行
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 匹配「序号: 内容」或「序号. 内容」
        m = re.match(r"^\d+[:：.、]\s*(.*)$", line)
        if m:
            content = m.group(1).strip()
            # 跳过可能残留的说明文字
            if content and not content.startswith(("译文", "翻译", "待翻译")):
                lines.append(content)
            continue
        # 兜底：不是序号格式，直接当作文本
        if not lines or len(lines) == expected_count:
            lines.append(line)

    if len(lines) < expected_count:
        # 兜底：可能模型没带序号，按原样拆分
        plain_lines = [l.strip() for l in raw.split("\n") if l.strip()]
        if len(plain_lines) >= expected_count:
            return plain_lines[:expected_count]
        raise ValueError(f"解析结果只有 {len(lines)} 行，期望 {expected_count} 行")
    return lines[:expected_count]
