"""翻译调度：多引擎注册、降级、限流、缓存与并发。"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .bing import BingEngine
from .deepseek import DeepSeekEngine
from .deepl import DeepLEngine
from .google import GoogleEngine
from .local_model import LocalModelEngine

# 引擎注册表：名称 -> 类
ENGINE_REGISTRY: dict[str, type] = {
    "deepseek": DeepSeekEngine,
    "deepl": DeepLEngine,
    "google": GoogleEngine,
    "bing": BingEngine,
    "local": LocalModelEngine,
}


class _RateLimiter:
    """令牌桶限流（线程安全）。"""

    def __init__(self, tokens_per_min: int) -> None:
        self._rate = max(tokens_per_min, 1) / 60.0
        self._tokens = float(tokens_per_min)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """阻塞直到获得一个令牌。"""
        with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self._rate * (now - self._last) + self._tokens, self._rate * 60.0)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._rate
                time.sleep(wait)


class TranslationManager:
    """多引擎调度管理器。"""

    def __init__(
        self,
        config: Any,
        glossary: Any = None,
        engine_names: list[str] | None = None,
    ) -> None:
        self.config = config
        self.glossary = glossary
        tconf = config.get("translate") or {}
        self._target_lang = tconf.get("target_lang", "zh-CN")
        self._max_retry = int(tconf.get("max_retry", 2))
        self._concurrency = int(tconf.get("concurrency", 4))
        self._batch_size = int(tconf.get("batch_size", 16))
        self._rate_limit = int(tconf.get("rate_limit_per_min", 60))
        self._engines: dict[str, Any] = {}
        self._cooldowns: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self._cache_lock = threading.Lock()
        self._load_engines(engine_names)

    def _load_engines(self, engine_names: list[str] | None) -> None:
        """实例化引擎；engine_names 为空时按 primary + fallbacks 顺序。"""
        names = engine_names or []
        if not names:
            tconf = self.config.get("translate") or {}
            primary = tconf.get("primary", "deepseek")
            names = [primary, *(tconf.get("fallbacks") or [])]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            engine_cls = ENGINE_REGISTRY.get(name)
            if engine_cls is None:
                continue
            try:
                self._engines[name] = engine_cls(self.config, self.glossary)
            except Exception:  # noqa: BLE001
                continue

    def engine_order(self) -> list[str]:
        """返回当前可用引擎名称列表。"""
        return list(self._engines.keys())

    def _available(self, name: str) -> bool:
        """判断引擎是否在冷却期内。"""
        with self._cooldown_lock:
            return self._cooldowns.get(name, 0) < time.monotonic()

    def _mark_cooldown(self, name: str, seconds: float = 30.0) -> None:
        """把引擎标记为冷却。"""
        with self._cooldown_lock:
            self._cooldowns[name] = time.monotonic() + seconds

    def _translate_one(self, engine: Any, batch: list[str]) -> list[str]:
        """单引擎翻译一批，带重试与限流。"""
        for attempt in range(self._max_retry + 1):
            self._limiter.acquire()
            try:
                return engine.translate_batch(batch, self._target_lang)
            except Exception as exc:  # noqa: BLE001
                if attempt >= self._max_retry:
                    raise
                time.sleep(1 + attempt)
                if not hasattr(engine, "translate_batch"):
                    raise
                last_exc = exc
        raise last_exc  # type: ignore[name-defined]

    def translate_batch(
        self,
        texts: list[str],
        on_progress: Callable[[int, int], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> list[str]:
        """批量翻译：缓存、分批、并发、降级。

        全部引擎失败时返回原文并触发 on_error("全部引擎失败", 失败详情)。
        """
        self._limiter = _RateLimiter(self._rate_limit)
        results: list[str] = [""] * len(texts)
        need: list[tuple[int, str]] = []
        with self._cache_lock:
            for idx, text in enumerate(texts):
                text = (text or "").strip()
                if not text:
                    results[idx] = ""
                    continue
                cached = self._cache.get(text)
                if cached is not None:
                    results[idx] = cached
                    continue
                need.append((idx, text))
        if not need:
            return results

        # 分批
        batches: list[list[tuple[int, str]]] = []
        for i in range(0, len(need), self._batch_size):
            batches.append(need[i : i + self._batch_size])

        def _work(batch: list[tuple[int, str]]) -> None:
            texts_batch = [t for _, t in batch]
            failures: list[str] = []
            translated: list[str] | None = None
            for name in self.engine_order():
                if not self._available(name):
                    continue
                engine = self._engines[name]
                try:
                    translated = self._translate_one(engine, texts_batch)
                    break
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{name}: {exc}")
                    self._mark_cooldown(name)
            if translated is None:
                if on_error is not None:
                    on_error("全部引擎失败", "; ".join(failures) or "无可用引擎")
                translated = texts_batch
            with self._cache_lock:
                for (idx, text), out in zip(batch, translated):
                    self._cache[text] = out
                    results[idx] = out
            if on_progress is not None:
                on_progress(len(batch), len(need))

        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            futures = [pool.submit(_work, b) for b in batches]
            for f in futures:
                f.result()

        return results

    def clear_cache(self) -> None:
        """清空翻译缓存。"""
        with self._cache_lock:
            self._cache.clear()
