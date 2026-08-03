"""解析器抽象基类

统一模型：
- 解析脚本文件得到「原文片段」列表（每个片段记录原文、偏移、行号）
- 翻译后调用 rebuild 将译文回写到文本内容
- 补丁生成 = 用回写后的内容写出文件（不改原游戏）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TextSegment:
    """一个待翻译的文本片段"""

    original: str            # 原文
    translated: str = ""     # 译文（翻译后填充）
    line_no: int = 0         # 行号（1 起）
    offset: int = 0          # 在文件内容中的字符偏移
    context: str = ""        # 上下文（如所在文件相对路径）


@dataclass
class ParseResult:
    """一次解析的结果"""

    file_path: Path          # 原始文件路径
    rel_path: str            # 相对游戏目录的路径
    content: str             # 解码后的完整文本内容
    encoding: str            # 检测到的编码
    segments: list[TextSegment] = field(default_factory=list)
    skipped: int = 0         # 跳过的不可翻译片段数


class ScriptParser(ABC):
    """脚本解析器基类"""

    name = "base"
    extensions: tuple[str, ...] = ()

    @classmethod
    def supports(cls, path: Path) -> bool:
        """判断是否支持该文件"""
        return path.suffix.lower() in cls.extensions

    @abstractmethod
    def parse(self, file_path: Path, rel_path: str) -> ParseResult:
        """解析脚本文件，提取待翻译片段"""
        raise NotImplementedError

    @staticmethod
    def rebuild(result: ParseResult) -> str:
        """将译文回写到内容，返回回写后的文本

        默认实现：按偏移从后往前替换（offset 不变，从后替换避免位移）。
        """
        content = result.content
        segments = sorted(
            [s for s in result.segments if s.translated and s.translated != s.original],
            key=lambda s: s.offset,
            reverse=True,
        )
        for seg in segments:
            content = content[: seg.offset] + seg.translated + content[seg.offset + len(seg.original) :]
        return content
