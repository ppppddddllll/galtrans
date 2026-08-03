"""Kirikiri（吉里吉里）脚本解析器。

支持编码检测（utf-8 / cp932 / utf-16-le）与文本提取，跳过
控制标签、内嵌脚本与颜色码，保持颜色码前后文本连续。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import ParseResult, ScriptParser, TextSegment

# 日文判定（平假名/片假名/汉字）
_JP_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf]")


def detect_encoding(data: bytes) -> str:
    """检测脚本编码。

    优先 BOM，其次空字节占比（UTF-16LE），再依次尝试 utf-8 / cp932
    （utf-8 结构严格优先，避免 utf-8 日文脚本被误判为 cp932）。
    """
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    nulls = data.count(b"\x00")
    if nulls > len(data) // 6:
        return "utf-16-le"
    for enc in ("utf-8", "cp932"):
        try:
            data.decode(enc)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "cp932"


class KirikiriParser(ScriptParser):
    """Kirikiri .ks 脚本解析。"""

    name = "kirikiri"
    extensions = (".ks", ".txt", ".kst", ".ksc")

    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析 .ks 文件。"""
        raw = file_path.read_bytes()
        encoding = detect_encoding(raw)
        content = raw.decode(encoding, errors="replace")
        # 统一换行
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        rel = rel_path.replace("\\", "/")
        result = ParseResult(file_path=file_path, rel_path=rel, content=content, encoding=encoding)

        line_no = 0
        offset = 0
        for line in content.split("\n"):
            stripped = line.lstrip()
            if not stripped or stripped.startswith(";") or stripped.startswith("*"):
                offset += len(line) + 1
                continue
            self._extract_line(line, offset, line_no, rel, result)
            offset += len(line) + 1
            line_no += 1
        return result

    def _extract_line(self, line: str, base_offset: int, line_no: int, rel: str, result: ParseResult) -> None:
        """从单行提取文本片段（跳过标签/脚本/颜色码，保持颜色码前后连续）。"""
        buf: list[str] = []
        seg_start = 0
        i = 0

        def flush() -> None:
            nonlocal buf, seg_start
            text = "".join(buf).strip()
            if text and _JP_RE.search(text):
                # 计算片段在文件中的绝对偏移（含前导空白）
                leading = len("".join(buf)) - len("".join(buf).lstrip())
                seg_start_abs = base_offset + seg_start + leading
                result.segments.append(
                    TextSegment(original=text, line_no=line_no, offset=seg_start_abs, context=rel)
                )
            buf = []
            seg_start = i

        while i < len(line):
            ch = line[i]
            # 控制标签 [..]
            if ch == "[":
                end = line.find("]", i)
                if end != -1:
                    flush()
                    i = end + 1
                    continue
            # 内嵌脚本 {..}
            if ch == "{":
                end = line.find("}", i)
                if end != -1:
                    flush()
                    i = end + 1
                    continue
            # 颜色码 <#..> 或 </#> 或 <\#>：跳过但不中断当前文本
            if ch == "<":
                if line.startswith("<#", i):
                    end = line.find(">", i)
                    if end != -1:
                        i = end + 1
                        continue
                elif line[i : i + 4] in ("</#>", "<\\#>"):
                    i += 4
                    continue
            # 行内 @ 命令（如 @r）：flush 并跳过整段命令
            if ch == "@":
                flush()
                m = re.match(r"@[^\s\[]*", line[i:])
                if m:
                    i += len(m.group(0))
                    continue
            if not buf:
                seg_start = i
            buf.append(ch)
            i += 1
        flush()
