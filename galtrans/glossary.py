"""术语表模块：日文专名到中文的映射与自动替换。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class Glossary:
    """术语表，支持最长匹配正则替换与导入导出。"""

    def __init__(self, path: Path | None = None) -> None:
        from .config import get_config_dir

        self._path = path or (get_config_dir() / "glossary.json")
        self._pairs: list[tuple[str, str]] = []
        self.enabled = True
        self._regex: re.Pattern | None = None
        self._load()

    def _load(self) -> None:
        """从磁盘加载词条（兼容旧格式 {jp: cn} 与新格式 {"pairs": [...]}）。"""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            self.enabled = bool(data.get("enabled", True))
            pairs = data.get("pairs", [])
        else:
            pairs = data
        for item in pairs:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                self._pairs.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict) and "jp" in item and "cn" in item:
                self._pairs.append((str(item["jp"]), str(item["cn"])))
        self._rebuild_regex()

    def save(self) -> None:
        """持久化到磁盘。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"enabled": self.enabled, "pairs": [list(p) for p in self._pairs]}
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    def _rebuild_regex(self) -> None:
        """按长度降序构建最长匹配正则（词条越长优先匹配）。"""
        if not self._pairs:
            self._regex = None
            return
        pattern = "|".join(re.escape(jp) for jp, _ in sorted(self._pairs, key=lambda p: -len(p[0])))
        self._regex = re.compile(pattern)

    def add(self, jp: str, cn: str) -> None:
        """新增词条（同名覆盖）。"""
        jp = jp.strip()
        cn = cn.strip()
        if not jp:
            return
        self._pairs = [p for p in self._pairs if p[0] != jp]
        self._pairs.append((jp, cn))
        self._rebuild_regex()
        self.save()

    def remove(self, jp: str) -> None:
        """删除词条。"""
        self._pairs = [p for p in self._pairs if p[0] != jp]
        self._rebuild_regex()
        self.save()

    def clear(self) -> None:
        """清空全部词条。"""
        self._pairs = []
        self._rebuild_regex()
        self.save()

    def pairs(self) -> list[tuple[str, str]]:
        """返回全部词条。"""
        return list(self._pairs)

    def apply_glossary(self, text: str) -> str:
        """把文本中匹配的日文专名替换为中文。"""
        if not self.enabled or not self._regex:
            return text
        return self._regex.sub(lambda m: self._to_cn(m.group(0)), text)

    def _to_cn(self, jp: str) -> str:
        """查词条，无则原样返回。"""
        for old, new in self._pairs:
            if old == jp:
                return new
        return jp

    def export(self, path: Path | str) -> None:
        """导出词条为 JSON 列表 [[jp, cn], ...]。"""
        with open(path, "w", encoding="utf-8") as fp:
            json.dump([list(p) for p in self._pairs], fp, ensure_ascii=False, indent=2)

    def import_from(self, path: Path | str) -> int:
        """从 JSON 导入词条（覆盖同名），返回导入条数。"""
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        count = 0
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                self.add(str(item[0]), str(item[1]))
                count += 1
        return count
