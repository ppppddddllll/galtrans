"""离线汉化流水线

流程：扫描游戏目录 -> 解析脚本 -> 提取文本 -> 批量翻译 -> 生成补丁/对照表
支持中断恢复（进度缓存），不修改原游戏文件。
"""
from __future__ import annotations

import csv
import json
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import get_config_dir
from .glossary import Glossary
from .parsers import PARSERS, ParseResult, ScriptParser
from .parsers.renpy import list_rpa_entries, open_rpa, extract_rpy_from_rpa
from .translate import TranslationManager


@dataclass
class ScanStats:
    """扫描结果统计"""

    files: int = 0            # 待处理文件数
    segments: int = 0         # 总待翻译片段数
    skipped_files: int = 0    # 无文本的文件数


@dataclass
class OfflineJob:
    """一次离线汉化任务"""

    game_dir: Path
    output_dir: Path
    parse_results: list[ParseResult] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)

    def cancel_requested(self) -> bool:
        return self.cancel.is_set()


# 进度回调类型：(阶段: str, 当前: int, 总数: int, 消息: str)
ProgressCb = Callable[[str, int, int, str], None]


def scan_game(game_dir: Path, progress: ProgressCb | None = None) -> ScanStats:
    """扫描游戏目录，收集可解析的脚本文件并解析

    返回所有 ParseResult 的统计（不翻译，仅扫描）。
    """
    stats = ScanStats()
    parse_results: list[ParseResult] = []

    for file_path in sorted(game_dir.rglob("*")):
        if not file_path.is_file():
            continue
        parser = _match_parser(file_path)
        if parser is None:
            continue
        rel = file_path.relative_to(game_dir).as_posix()
        if progress:
            progress("scan", len(parse_results), 0, f"解析 {rel}")
        try:
            result = parser.parse(file_path, rel)
        except Exception as exc:
            if progress:
                progress("scan", 0, 0, f"解析失败 {rel}: {exc}")
            stats.skipped_files += 1
            continue
        if result.segments:
            parse_results.append(result)
            stats.segments += len(result.segments)
        else:
            stats.skipped_files += 1
        stats.files += 1

    if progress:
        progress("scan", stats.files, 0, f"扫描完成：{stats.files} 文件，{stats.segments} 片段")

    # 挂载 .rpa 归档（属于 Ren'Py 游戏）
    parse_results += _scan_rpa_archives(game_dir, progress, stats)

    return stats


def _match_parser(file_path: Path) -> ScriptParser | None:
    """匹配文件对应解析器"""
    for cls in PARSERS:
        if cls.supports(file_path):
            return cls()
    return None


def _scan_rpa_archives(
    game_dir: Path, progress: ProgressCb | None, stats: ScanStats
) -> list[ParseResult]:
    """扫描 .rpa 归档并解析其中的 .rpy"""
    from .parsers.renpy import RenPyParser

    results: list[ParseResult] = []
    for rpa in sorted(game_dir.rglob("*.rpa")):
        entries = list_rpa_entries(rpa)
        for entry in entries:
            if progress:
                progress("scan", 0, 0, f"解包 {rpa.name} -> {entry}")
            try:
                data = extract_rpy_from_rpa(rpa, entry)
            except Exception as exc:
                if progress:
                    progress("scan", 0, 0, f"解包失败 {entry}: {exc}")
                continue
            result = RenPyParser().parse_bytes(data, rpa, entry)
            if result.segments:
                results.append(result)
                stats.segments += len(result.segments)
                stats.files += 1
    return results


def run_offline(
    game_dir: Path,
    output_dir: Path,
    translator: TranslationManager,
    glossary: Glossary | None = None,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> OfflineJob:
    """执行完整离线汉化流程

    1. 扫描解析所有脚本
    2. 批量翻译
    3. 生成汉化补丁（镜像目录结构，输出到 output_dir/patch）
    4. 导出翻译对照表（output_dir/translation_table.csv）
    5. 输出统计信息

    cancel: 可选 threading.Event，设置后任务在阶段间安全停止。
    """
    job = OfflineJob(
        game_dir=game_dir,
        output_dir=output_dir,
        cancel=cancel or threading.Event(),
    )

    # 阶段1：扫描
    all_results = _scan_all(game_dir, job, progress)
    job.parse_results = all_results
    if job.cancel_requested():
        return job

    # 汇总所有待翻译文本
    all_segments: list = []
    for result in all_results:
        all_segments.extend(result.segments)

    if progress:
        progress("translate", 0, len(all_segments), f"开始翻译 {len(all_segments)} 条文本")

    # 阶段2：翻译
    if all_segments:
        texts = [s.original for s in all_segments]
        if progress is None:
            translated = translator.translate_batch(texts)
        else:
            translated = translator.translate_batch(
                texts, on_progress=lambda done, total: progress("translate", done, total, "翻译中")
            )
        for seg, zh in zip(all_segments, translated):
            seg.translated = zh

    if job.cancel_requested():
        return job

    # 阶段3：生成补丁
    _write_patch(all_results, output_dir / "patch", job, progress)

    # 阶段4：导出对照表
    _export_table(all_segments, output_dir, job, progress)

    return job


def _scan_all(game_dir: Path, job: OfflineJob, progress: ProgressCb | None) -> list[ParseResult]:
    """扫描所有脚本（含 .rpa），返回解析结果列表"""
    results: list[ParseResult] = []
    for file_path in sorted(game_dir.rglob("*")):
        if job.cancel_requested():
            return results
        if not file_path.is_file():
            continue
        parser = _match_parser(file_path)
        if parser is None:
            continue
        rel = file_path.relative_to(game_dir).as_posix()
        if progress:
            progress("scan", 0, 0, f"解析 {rel}")
        try:
            result = parser.parse(file_path, rel)
        except Exception:
            continue
        if result.segments:
            results.append(result)

    # .rpa 归档
    from .parsers.renpy import RenPyParser

    for rpa in sorted(game_dir.rglob("*.rpa")):
        if job.cancel_requested():
            return results
        for entry in list_rpa_entries(rpa):
            try:
                data = extract_rpy_from_rpa(rpa, entry)
                result = RenPyParser().parse_bytes(data, rpa, entry)
                if result.segments:
                    results.append(result)
            except Exception:
                continue
    return results


def _write_patch(
    results: list[ParseResult], patch_dir: Path, job: OfflineJob, progress: ProgressCb | None
) -> None:
    """将翻译结果写入补丁目录（镜像原目录结构）"""
    patch_dir.mkdir(parents=True, exist_ok=True)
    for i, result in enumerate(results):
        if job.cancel_requested():
            return
        rel = Path(result.rel_path)
        out_path = patch_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # 原文件编码回写
        new_content = ScriptParser.rebuild(result)
        try:
            if result.encoding == "utf-8":
                out_path.write_bytes(new_content.encode("utf-8"))
            else:
                out_path.write_bytes(new_content.encode(result.encoding, errors="replace"))
        except Exception as exc:
            if progress:
                progress("patch", i + 1, len(results), f"写入失败 {rel}: {exc}")
            continue
        if progress:
            progress("patch", i + 1, len(results), f"生成补丁 {rel}")


def _export_table(segments: list, output_dir: Path, job: OfflineJob, progress: ProgressCb | None) -> None:
    """导出原文-译文对照表（CSV）"""
    if job.cancel_requested():
        return
    out = output_dir / "translation_table.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["文件", "行号", "原文", "译文"])
        for seg in segments:
            writer.writerow([seg.context, seg.line_no, seg.original, seg.translated])
    if progress:
        progress("done", len(segments), len(segments), f"对照表已导出：{out}")
