"""Ren'Py 脚本解析器

处理 .rpy 脚本：
- 词法识别对话行（say 语句），区分代码/资源行
- 支持 .rpa 归档解包（RPA-3.0 格式，实质为带前缀的 zip）
- 回写保留原格式
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from .base import ParseResult, ScriptParser, TextSegment

# 非对话语句关键字（行首 token 命中则跳过）
_CODE_KEYWORDS = {
    "label", "scene", "show", "hide", "play", "stop", "queue", "pause",
    "window", "with", "voice", "image", "transform", "define", "default",
    "init", "python", "return", "jump", "call", "menu", "if", "elif",
    "else", "while", "for", "function", "at", "on", "camera", "add",
    "text", "viewport", "vbox", "hbox", "side", "use", "screen", "style",
    "translate", "renpy", "layer", "zorder", "block", "pass", "nvl",
    "centered", "window",
}
# 允许出现对话文本的行首关键字（仍然提取其后字符串）
_DIALOGUE_LEADERS = {"extend", "narrator"}

# 字符串字面量正则：支持单双引号、三引号、转义（单行内）
_STRING_RE = re.compile(
    r'"""([^"\\]*(?:\\.[^"\\]*)*)"""|'
    r"'''([^'\\]*(?:\\.[^'\\]*)*)'''|"
    r'"([^"\\\n]*(?:\\.[^"\\\n]*)*)"|'
    r"'([^'\\\n]*(?:\\.[^'\\\n]*)*)'"
)


def _split_tokens(stripped: str) -> list[str]:
    """简单分词：按空白切分，保留引号内字符串为一个 token"""
    tokens: list[str] = []
    i = 0
    n = len(stripped)
    while i < n:
        if stripped[i].isspace():
            i += 1
            continue
        if stripped[i] in "\"'":
            m = _STRING_RE.match(stripped[i:])
            if m:
                tokens.append(m.group(0))
                i += len(m.group(0))
                continue
            i += 1
            continue
        # 读取到一个空白或字符串前的连续字符
        j = i
        while j < n and not stripped[j].isspace() and stripped[j] not in "\"'":
            j += 1
        tokens.append(stripped[i:j])
        i = j
    return tokens


def _is_dialogue_line(stripped: str) -> bool:
    """判断一行是否是需要翻译的对话行"""
    if not stripped or stripped.startswith("#"):
        return False
    tokens = _split_tokens(stripped)
    if not tokens:
        return False
    first = tokens[0]
    # 去除可能的前缀符号（如 $、->）
    bare = first.lstrip("$@")

    # 第一个 token 是字符串 -> 对话（叙述或带引号的说话人）
    if first.startswith(("\"", "'")):
        return True
    # 关键字直接跳过
    if bare in _CODE_KEYWORDS:
        return False
    if bare in _DIALOGUE_LEADERS:
        return True
    # 标识符后紧跟字符串 -> 形如 `sakura "你好"`
    if len(tokens) >= 2 and tokens[1].startswith(("\"", "'")):
        return True
    return False


def extract_strings(stripped: str, line_base: int) -> list[tuple[str, int]]:
    """提取一行中所有字符串字面量，返回 (内容, 文本实际起点绝对偏移)"""
    results: list[tuple[str, int]] = []
    for m in _STRING_RE.finditer(stripped):
        groups = m.groups()
        # 四组捕获，取非空者
        content = next((g for g in groups if g is not None), "")
        # 引号前缀长度：三引号为 3，否则为 1
        prefix_len = 3 if (groups[0] is not None or groups[1] is not None) else 1
        # 去掉转义引号
        content = content.replace("\\\"", "\"").replace("\\'", "'")
        results.append((content, line_base + m.start() + prefix_len))
    return results


class RenPyParser(ScriptParser):
    """Ren'Py 脚本解析器"""

    name = "renpy"
    extensions = (".rpy",)

    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析 .rpy 文件，提取对话字符串"""
        raw = file_path.read_bytes()
        return self.parse_bytes(raw, file_path, rel_path)

    def parse_bytes(self, raw: bytes, file_path: Path, rel_path: str) -> ParseResult:
        """从字节内容解析 .rpy（支持 .rpa 内文件）"""
        content = raw.decode("utf-8", errors="replace")
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        segments: list[TextSegment] = []
        skipped = 0

        lines = content.split("\n")
        offset = 0
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if _is_dialogue_line(stripped):
                for text, abs_off in extract_strings(stripped, 0):
                    # 补齐行首缩进偏移：abs_off 是相对 stripped 的，需加上 lead
                    lead = len(line) - len(line.lstrip())
                    offset_abs = offset + lead + abs_off
                    # 去除首尾空白并同步调整偏移
                    text = text.strip()
                    if not text:
                        continue
                    # 计算右侧空白以修正偏移：strip 只影响首部
                    leading = len(line) - len(line.lstrip())
                    _ = leading  # 已用 lead 处理
                    segments.append(
                        TextSegment(
                            original=text,
                            line_no=line_no,
                            offset=offset_abs,
                            context=rel_path,
                        )
                    )
            else:
                skipped += 1
            offset += len(line) + 1

        return ParseResult(
            file_path=file_path,
            rel_path=rel_path,
            content=content,
            encoding="utf-8",
            segments=segments,
            skipped=skipped,
        )


# ---------- .rpa 归档支持 ----------

_RPA_ZIP_MAGIC = b"PK\x03\x04"


def open_rpa(path: Path) -> zipfile.ZipFile | None:
    """打开 .rpa 归档文件，返回 ZipFile（失败返回 None）

    RPA 格式：文件头若干字节 + zip 数据。通过搜索 PK magic 定位 zip 起点。
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    idx = data.find(_RPA_ZIP_MAGIC)
    if idx < 0:
        return None
    try:
        return zipfile.ZipFile(io.BytesIO(data[idx:]))
    except zipfile.BadZipFile:
        return None


def list_rpa_entries(path: Path) -> list[str]:
    """列出 .rpa 归档内的 .rpy 文件名（相对路径）"""
    zf = open_rpa(path)
    if zf is None:
        return []
    try:
        return [n for n in zf.namelist() if n.lower().endswith(".rpy")]
    finally:
        zf.close()


def extract_rpy_from_rpa(path: Path, entry: str) -> bytes:
    """从 .rpa 中读取指定 .rpy 条目内容"""
    zf = open_rpa(path)
    if zf is None:
        raise FileNotFoundError(f"无法打开归档：{path}")
    try:
        return zf.read(entry)
    finally:
        zf.close()
