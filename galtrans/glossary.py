"""术语表模块

存储「日文 -> 中文」术语对照，支持：
- 加载/保存 JSON
- 应用术语到文本（贪心最长匹配，避免子串误替换）
- 导出导入（用于与其他工具交换）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import get_config_dir


class Glossary:
    """术语表对象"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_config_dir() / "glossary.json")
        # 存储顺序保留插入序，优先匹配更长的条目
        self._pairs: list[tuple[str, str]] = []
        self.enabled = True
        self._load()
        # 构建最长匹配正则
        self._regex: re.Pattern | None = None
        self._rebuild_regex()

    def _load(self) -> None:
        """从磁盘加载术语表"""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                # 兼容 {日文: 中文} 或 {"pairs": [[jp, cn]]}
                if "pairs" in data and isinstance(data["pairs"], list):
                    self._pairs = [tuple(p) for p in data["pairs"] if len(p) == 2]
                else:
                    self._pairs = list(data.items())
        except (json.JSONDecodeError, OSError):
            self._pairs = []

    def save(self) -> None:
        """持久化术语表"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump({"pairs": self._pairs}, fp, ensure_ascii=False, indent=2)

    def _rebuild_regex(self) -> None:
        """按长度降序构建匹配正则，保证最长匹配优先"""
        if not self._pairs:
            self._regex = None
            return
        # 需要先转义正则特殊字符
        patterns = [re.escape(jp) for jp, _ in sorted(self._pairs, key=lambda p: len(p[0]), reverse=True)]
        self._regex = re.compile("|".join(patterns))

    def add(self, japanese: str, chinese: str) -> None:
        """新增或更新术语条目"""
        japanese = japanese.strip()
        chinese = chinese.strip()
        if not japanese:
            return
        for i, (jp, cn) in enumerate(self._pairs):
            if jp == japanese:
                self._pairs[i] = (japanese, chinese)
                break
        else:
            self._pairs.append((japanese, chinese))
        self._rebuild_regex()
        self.save()

    def remove(self, japanese: str) -> None:
        """删除术语条目"""
        self._pairs = [p for p in self._pairs if p[0] != japanese]
        self._rebuild_regex()
        self.save()

    def clear(self) -> None:
        """清空术语表"""
        self._pairs = []
        self._regex = None
        self.save()

    def pairs(self) -> list[tuple[str, str]]:
        """返回所有术语对"""
        return list(self._pairs)

    def apply_glossary(self, text: str) -> str:
        """应用术语表到文本（翻译前调用）

        用法：把专有名词直接替换为中文，可显著提升 LLM 译名一致性。
        """
        if not self.enabled or self._regex is None or not text:
            return text
        return self._regex.sub(lambda m: self._to_cn(m.group(0)), text)

    def _to_cn(self, japanese: str) -> str:
        """根据日文查找对应中文"""
        for jp, cn in self._pairs:
            if jp == japanese:
                return cn
        return japanese

    def export(self, path: Path) -> None:
        """导出术语表到指定文件"""
        path = Path(path)
        path.write_text(json.dumps({"pairs": self._pairs}, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_from(self, path: Path) -> int:
        """从文件导入术语，返回导入条数（覆盖同名条目）"""
        path = Path(path)
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            if "pairs" in data:
                new_pairs = data["pairs"]
            else:
                new_pairs = list(data.items())
        elif isinstance(data, list):
            new_pairs = data
        else:
            new_pairs = []

        count = 0
        for p in new_pairs:
            if isinstance(p, (list, tuple)) and len(p) == 2:
                self.add(str(p[0]), str(p[1]))
                count += 1
        return count
