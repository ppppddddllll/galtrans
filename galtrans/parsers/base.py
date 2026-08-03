"""解析器基类与公共数据结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TextSegment:
    """一条可翻译的文本片段。"""

    original: str
    translated: str = ""
    line_no: int = 0
    offset: int = 0
    context: str = ""


@dataclass
class ParseResult:
    """一次文件解析的结果。"""

    file_path: Path
    rel_path: str
    content: str
    encoding: str = "utf-8"
    segments: list[TextSegment] = field(default_factory=list)
    skipped: int = 0


class ScriptParser(ABC):
    """脚本解析器抽象基类。"""

    name: str = "base"
    extensions: tuple[str, ...] = ()

    @classmethod
    def supports(cls, path: Path) -> bool:
        """判断是否支持该文件扩展名。"""
        return path.suffix.lower() in cls.extensions

    @abstractmethod
    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析文件，返回含文本片段的 ParseResult。"""

    @staticmethod
    def rebuild(result: ParseResult) -> str:
        """按偏移从后往前替换已翻译片段，返回重写后的完整内容。"""
        content = result.content
        for seg in sorted(result.segments, key=lambda s: -s.offset):
            if seg.translated and seg.translated != seg.original:
                content = content[: seg.offset] + seg.translated + content[seg.offset + len(seg.original) :]
        return content
