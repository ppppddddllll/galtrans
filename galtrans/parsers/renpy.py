"""Ren'Py 脚本解析器。

识别对话行（含 menu 选择枝），提取字符串文本，支持 .rpa 档案解包。
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from .base import ParseResult, ScriptParser, TextSegment

# Ren'Py 代码关键字（对话外不提取）
_CODE_KEYWORDS = {
    "label", "scene", "show", "hide", "play", "stop", "queue", "pause",
    "window", "with", "voice", "image", "transform", "define", "default",
    "init", "python", "return", "jump", "call", "menu", "if", "elif",
    "else", "while", "for", "function", "at", "on", "camera", "add",
    "text", "viewport", "vbox", "hbox", "side", "use", "screen", "style",
    "translate", "renpy", "layer", "zorder", "block", "pass", "nvl",
    "centered", "window",
}

# 对话引导词（其后字符串即对话）
_DIALOGUE_LEADERS = {"extend", "narrator"}

# 字符串正则（三引号 + 单双引号，支持转义）
_STRING_RE = re.compile(r'"""((?:[^"\\]|\\.)*)"""|"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'')

# RPA 包 zip 魔数
_RPA_ZIP_MAGIC = b"PK\x03\x04"


def _split_tokens(stripped: str) -> list[str]:
    """简单分词：按空白/引号边界切分。"""
    return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', stripped)


def _is_dialogue_line(stripped: str) -> bool:
    """判断一行是否为对话（字符串开头、extend/narrator、或标识符后跟字符串）。"""
    tokens = _split_tokens(stripped)
    if not tokens:
        return False
    first = tokens[0]
    if first.startswith(('"', "'")):
        return True
    if first.rstrip(":") in _DIALOGUE_LEADERS:
        return True
    if len(tokens) >= 2 and tokens[1].startswith(('"', "'")):
        if first.rstrip(":").replace("_", "").isalnum():
            return True
    return False


def extract_strings(stripped: str, line_base: int) -> list[tuple[str, int]]:
    """提取字符串，返回 [(内容, 绝对偏移)]。

    偏移为字符串首个字符（引号之后）在文件中的绝对位置。
    """
    result: list[tuple[str, int]] = []
    for match in _STRING_RE.finditer(stripped):
        content = next((g for g in match.groups() if g is not None), "")
        if not content:
            continue
        # 引号前缀长度（一个引号或三引号）
        quote_len = 3 if stripped[match.start() : match.start() + 3] == '"""' else 1
        abs_off = line_base + match.start() + quote_len
        result.append((content, abs_off))
    return result


class RenPyParser(ScriptParser):
    """Ren'Py .rpy 脚本解析。"""

    name = "renpy"
    extensions = (".rpy",)

    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析 .rpy 文件。"""
        raw = file_path.read_bytes()
        return self.parse_bytes(raw, file_path, rel_path)

    def parse_bytes(self, raw: bytes, file_path: Path, rel_path: str) -> ParseResult:
        """从字节解析（支持从 RPA 解包的内容）。"""
        try:
            content = raw.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, UnicodeError):
            content = raw.decode("utf-8", errors="replace")
        rel = rel_path.replace("\\", "/")
        result = ParseResult(file_path=file_path, rel_path=rel, content=content, encoding="utf-8")

        offset = 0
        line_no = 0
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and _is_dialogue_line(stripped):
                for text, abs_off in extract_strings(stripped, 0):
                    # 行首空白偏移
                    lead = len(line) - len(line.lstrip())
                    seg_offset = offset + lead + abs_off
                    result.segments.append(
                        TextSegment(original=text, line_no=line_no, offset=seg_offset, context=rel)
                    )
            offset += len(line) + 1
            line_no += 1
        return result


# ---------- RPA 档案支持 ----------


def open_rpa(path: Path | str) -> zipfile.ZipFile:
    """打开 .rpa 档案（跳过 RPA 头定位 zip 起点）。"""
    path = Path(path)
    data = path.read_bytes()
    idx = data.find(_RPA_ZIP_MAGIC)
    if idx == -1:
        raise ValueError(f"不是有效的 RPA 档案：{path}")
    return zipfile.ZipFile(io.BytesIO(data[idx:]))


def list_rpa_entries(path: Path | str) -> list[str]:
    """列出 .rpa 档案中的 .rpy 条目。"""
    with open_rpa(path) as zf:
        return [name for name in zf.namelist() if name.lower().endswith(".rpy")]


def extract_rpy_from_rpa(path: Path | str, entry: str) -> bytes:
    """从 .rpa 档案中读取指定 .rpy 条目内容。"""
    with open_rpa(path) as zf:
        return zf.read(entry)
