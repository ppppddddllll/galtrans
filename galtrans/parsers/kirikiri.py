"""Kirikiri/KAG（吉里吉里）脚本解析器

处理 .ks/.txt 脚本：
- 编码自动检测（SJIS/cp932、UTF-16LE、UTF-8）
- 去除控制标签（[wait] [l] [r] 等）、内嵌脚本（{...}）、颜色码（<#...>）
- 提取含日文的文本片段作为待翻译内容
- 回写时保留原始标签与结构
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import ParseResult, ScriptParser, TextSegment

# 日文字符检测：平假名、片假名、汉字
_JP_RE = re.compile(
    r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf]"
)


def detect_encoding(data: bytes) -> str:
    """检测脚本文件编码

    策略：
    1. BOM 优先
    2. 空字节占比高 -> UTF-16LE
    3. 尝试 UTF-8（有严格字节结构，识别可靠）
    4. 尝试 cp932（日文 S-JIS）
    """
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"

    # UTF-16LE 无 BOM：空字节占比高（ASCII 字符的高字节为 0x00）。
    # 阈值按 1/6 判（约 >16.7%）；utf-8/cp932 日文脚本几乎无空字节，不会误判。
    nulls = data.count(b"\x00")
    if nulls > len(data) // 6:
        return "utf-16-le"

    # utf-8 先尝试：UTF-8 有严格的字节结构约束，SJIS 字节序列几乎无法通过校验；
    # cp932 则几乎能解码任意字节，若排在前面会误判 utf-8 文件为 cp932。
    for enc in ("utf-8", "cp932"):
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "cp932"


class KirikiriParser(ScriptParser):
    """吉里吉里 KAG 脚本解析器"""

    name = "kirikiri"
    extensions = (".ks", ".txt", ".kst", ".ksc")

    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析 .ks 文件，返回待翻译片段列表"""
        raw = file_path.read_bytes()
        encoding = detect_encoding(raw)
        content = raw.decode(encoding, errors="replace")
        # 统一换行为 \n 便于行号与偏移计算
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        segments: list[TextSegment] = []
        skipped = 0

        # 记录原始行边界（按 \n 切分，保留内容）
        lines = content.split("\n")
        offset = 0
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            # 跳过注释行 / 标签行 / 空行
            if not stripped or stripped.startswith(";") or stripped.startswith("*"):
                if not stripped:
                    pass
                elif stripped.startswith(";"):
                    pass
                offset += len(line) + 1
                continue

            found = self._extract_line(line, offset, line_no, rel_path)
            if found:
                segments.extend(found)
            else:
                skipped += 1
            offset += len(line) + 1

        result = ParseResult(
            file_path=file_path,
            rel_path=rel_path,
            content=content,
            encoding=encoding,
            segments=segments,
            skipped=skipped,
        )
        return result

    def _extract_line(
        self, line: str, base_offset: int, line_no: int, rel_path: str
    ) -> list[TextSegment]:
        """提取单行中的可翻译文本片段

        扫描过程中跳过：
        - [ ... ]  控制标签
        - { ... }  内嵌脚本
        - <#...>  颜色码
        - @ 开头命令（行内）
        剩余连续字符构成候选文本。
        """
        segments: list[TextSegment] = []
        i = 0
        length = len(line)
        # 缓冲当前文本片段
        buf_start = -1
        buf: list[str] = []

        def _flush() -> None:
            nonlocal buf_start, buf
            if buf_start >= 0:
                text = "".join(buf)
                text = text.strip()
                if text and _JP_RE.search(text) and len(text.strip()) >= 1:
                    # 定位片段真实起始（跳过前导空白）
                    stripped_len = len(line[buf_start:]) - len(line[buf_start:].lstrip())
                    start = buf_start + stripped_len
                    segments.append(
                        TextSegment(
                            original=text,
                            line_no=line_no,
                            offset=base_offset + start,
                            context=rel_path,
                        )
                    )
                buf_start = -1
                buf = []

        while i < length:
            ch = line[i]
            # 控制标签 [ ... ]
            if ch == "[":
                _flush()
                end = line.find("]", i)
                if end == -1:
                    break
                i = end + 1
                continue
            # 内嵌脚本 { ... }
            if ch == "{":
                _flush()
                end = line.find("}", i)
                if end == -1:
                    break
                i = end + 1
                continue
            # 颜色码 <#xxxxxx> 或结束标签 </#> 或 <\#>
            # 注意：不 flush 缓冲区，让颜色码前后的文本保持连续（如「<#ff0000>頑張る</#>」）
            if ch == "<" and i + 1 < length and (
                line[i + 1] == "#" or line[i + 1 : i + 3] in ("/#", "\\#")
            ):
                end = line.find(">", i)
                if end == -1:
                    break
                i = end + 1
                continue
            # 行内 @ 命令（后随空格或到行尾）
            if ch == "@":
                _flush()
                m = re.match(r"@[^\s\[]*", line[i:])
                if m:
                    i += len(m.group(0))
                    continue
                i += 1
                continue

            # 普通字符：累积到缓冲区
            if buf_start < 0:
                buf_start = i
            buf.append(ch)
            i += 1

        _flush()
        return segments
