"""解析器包"""
from .base import ParseResult, ScriptParser, TextSegment
from .kirikiri import KirikiriParser, detect_encoding
from .renpy import RenPyParser

# 注册所有解析器
PARSERS = [KirikiriParser, RenPyParser]

__all__ = [
    "ParseResult",
    "ScriptParser",
    "TextSegment",
    "KirikiriParser",
    "RenPyParser",
    "detect_encoding",
    "PARSERS",
]
