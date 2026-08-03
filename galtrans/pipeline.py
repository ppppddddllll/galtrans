"""离线汉化流水线：扫描 → 翻译 → 生成补丁 → 导出对照表。"""
from __future__ import annotations

import csv
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .parsers import PARSERS, ParseResult
from .parsers.renpy import list_rpa_entries, extract_rpy_from_rpa

# 进度回调：(阶段, 当前, 总数, 消息)；阶段为 scan/translate/patch/done
ProgressCb = Callable[[str, int, int, str], None]


@dataclass
class ScanStats:
    """扫描统计。"""

    files: int = 0
    segments: int = 0
    skipped_files: int = 0


@dataclass
class OfflineJob:
    """一次离线汉化任务。"""

    game_dir: str
    output_dir: str
    parse_results: list[ParseResult] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)

    def cancel_requested(self) -> bool:
        return self.cancel.is_set()


def _match_parser(file_path: Path) -> Any:
    """返回匹配的解析器类，无则 None。"""
    for parser_cls in PARSERS:
        if parser_cls.supports(file_path):
            return parser_cls
    return None


def _scan_rpa_archives(game_dir: Path, progress: ProgressCb | None, stats: ScanStats) -> list[ParseResult]:
    """扫描 .rpa 档案内的 .rpy 文件。"""
    results: list[ParseResult] = []
    for rpa_path in game_dir.rglob("*.rpa"):
        try:
            entries = list_rpa_entries(rpa_path)
        except Exception:  # noqa: BLE001
            continue
        for entry in entries:
            try:
                raw = extract_rpy_from_rpa(rpa_path, entry)
            except Exception:  # noqa: BLE001
                continue
            rel = f"{rpa_path.name}:{entry}"
            parser = _match_parser(Path(entry))
            if parser is None:
                stats.skipped_files += 1
                continue
            result = parser().parse_bytes(raw, rpa_path, rel)
            if result.segments:
                results.append(result)
                stats.segments += len(result.segments)
            stats.files += 1
    return results


def scan_game(game_dir: str, progress: ProgressCb | None = None) -> tuple[list[ParseResult], ScanStats]:
    """扫描游戏目录，返回解析结果与统计。"""
    game_path = Path(game_dir)
    stats = ScanStats()
    results: list[ParseResult] = []

    files = [p for p in game_path.rglob("*") if p.is_file() and _match_parser(p) is not None]
    for idx, file_path in enumerate(files):
        if progress is not None:
            progress("scan", idx, len(files), str(file_path.relative_to(game_path)))
        try:
            parser = _match_parser(file_path)
            rel = str(file_path.relative_to(game_path))
            result = parser().parse(file_path, rel)
        except Exception:  # noqa: BLE001
            stats.skipped_files += 1
            continue
        if result.segments:
            results.append(result)
            stats.segments += len(result.segments)
        stats.files += 1

    results.extend(_scan_rpa_archives(game_path, progress, stats))
    return results, stats


def _scan_all(game_dir: str, job: OfflineJob, progress: ProgressCb | None) -> list[ParseResult]:
    """扫描全部文件（含 RPA）。"""
    all_results, _ = scan_game(game_dir, progress)
    job.parse_results = all_results
    return all_results


def _write_patch(results: list[ParseResult], patch_dir: Path, job: OfflineJob, progress: ProgressCb | None) -> None:
    """把译文写回脚本，生成 patch 目录镜像结构。"""
    for idx, result in enumerate(results):
        if job.cancel_requested():
            return
        if progress is not None:
            progress("patch", idx, len(results), result.rel_path)
        parser_cls = _match_parser(result.file_path) or (PARSERS[0] if results else None)
        rebuilt = parser_cls.rebuild(result)
        out_path = patch_dir / result.rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        encoding = result.encoding
        if encoding in ("utf-16", "utf-16-le", "utf-8-sig"):
            rebuilt = rebuilt
        try:
            out_path.write_text(rebuilt, encoding=encoding, errors="replace")
        except (UnicodeEncodeError, LookupError):
            out_path.write_text(rebuilt, encoding="utf-8", errors="replace")


def _export_table(segments: list[ParseResult], output_dir: Path, job: OfflineJob, progress: ProgressCb | None) -> None:
    """导出翻译对照表 CSV（utf-8-sig 供 Excel 直接打开）。"""
    if job.cancel_requested():
        return
    csv_path = output_dir / "translation_table.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["文件", "行号", "原文", "译文"])
        for result in segments:
            for seg in result.segments:
                writer.writerow([result.rel_path, seg.line_no + 1, seg.original, seg.translated])


def run_offline(
    game_dir: str,
    output_dir: str,
    translator: Any,
    glossary: Any = None,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> OfflineJob:
    """执行离线汉化，返回任务对象（含 parse_results 供后续使用）。

    阶段：scan → translate → patch → done。
    """
    job = OfflineJob(game_dir=game_dir, output_dir=output_dir)
    if cancel is not None:
        job.cancel = cancel

    # 阶段 1：扫描
    if job.cancel_requested():
        return job
    all_results = _scan_all(game_dir, job, progress)

    # 阶段 2：翻译
    if job.cancel_requested():
        return job
    all_segments = [seg for r in all_results for seg in r.segments]
    total = len(all_segments)
    if total > 0:
        texts = [seg.original for seg in all_segments]
        if progress is None:
            translated = translator.translate_batch(texts)
        else:
            def _on_progress(done: int, count: int) -> None:
                progress("translate", done, total, f"翻译中 {done}/{total}")

            translated = translator.translate_batch(texts, on_progress=_on_progress)
        for seg, text in zip(all_segments, translated):
            seg.translated = text

    # 阶段 3：生成补丁
    if job.cancel_requested():
        return job
    patch_dir = Path(output_dir) / "patch"
    _write_patch(all_results, patch_dir, job, progress)

    # 阶段 4：导出对照表
    _export_table(all_results, Path(output_dir), job, progress)

    if progress is not None:
        progress("done", total, total, "汉化完成")
    return job
