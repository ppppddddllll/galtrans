"""解析器包。"""
from .base import ParseResult, ScriptParser, TextSegment
from .kirikiri import KirikiriParser, detect_encoding
from .renpy import RenPyParser

PARSERS: list[type[ScriptParser]] = [KirikiriParser, RenPyParser]

__all__ = [
    "KirikiriParser",
    "ParseResult",
    "PARSERS",
    "RenPyParser",
    "ScriptParser",
    "TextSegment",
    "detect_encoding",
]
