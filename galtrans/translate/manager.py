"""翻译调度管理器

职责：
1. 根据配置实例化可用引擎
2. 按顺序尝试（primary -> fallbacks）实现自动降级
3. 速率限制（令牌桶）与并发控制（线程池）
4. 缓存重复文本的翻译结果
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .base import TranslationEngine, TranslateError
from .bing import BingEngine
from .deepseek import DeepSeekEngine
from .deepl import DeepLEngine
from .google import GoogleEngine

# 引擎注册表：名称 -> 类
ENGINE_REGISTRY: dict[str, type[TranslationEngine]] = {
    DeepSeekEngine.name: DeepSeekEngine,
    DeepLEngine.name: DeepLEngine,
    GoogleEngine.name: GoogleEngine,
    BingEngine.name: BingEngine,
}


class _RateLimiter:
    """简单令牌桶限流器（线程安全）"""

    def __init__(self, tokens_per_min: int) -> None:
        self.rate = tokens_per_min / 60.0  # 每秒补充令牌数
        self.capacity = max(tokens_per_min, 1)
        self.tokens = self.capacity
        self._lock = threading.Lock()
        self._last = time.monotonic()

    def acquire(self) -> None:
        """阻塞直到获得一个令牌"""
        with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self._last) * self.rate)
                self._last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                # 等待一个令牌的时间
                wait = (1 - self.tokens) / self.rate
                time.sleep(max(wait, 0.01))


class TranslationManager:
    """多引擎翻译调度器"""

    def __init__(
        self,
        config: Any,
        glossary: Any | None = None,
        engine_names: list[str] | None = None,
    ) -> None:
        self.config = config
        self.glossary = glossary
        tconf = config.get("translate") or {}
        self.target_lang = tconf.get("target_lang", "zh-CN")
        self.max_retry = tconf.get("max_retry", 2)
        self.concurrency = tconf.get("concurrency", 4)
        self.batch_size = tconf.get("batch_size", 16)

        self._engines: dict[str, TranslationEngine] = {}
        self._load_engines(engine_names)

        rate_limit = tconf.get("rate_limit_per_min", 60)
        self._limiter = _RateLimiter(rate_limit)

        # 缓存
        self._cache: dict[str, str] = {}
        self._cache_lock = threading.Lock()

        # 降级状态
        self._cooldown_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _load_engines(self, engine_names: list[str] | None = None) -> None:
        """按配置实例化引擎。

        参数:
            engine_names: 显式指定引擎顺序（如实时翻译页独立配置）。
                为 None 时从 config.translate 读取 primary + fallbacks。
        """
        if engine_names is None:
            tconf = self.config.get("translate") or {}
            engine_names = [tconf.get("primary", "deepseek")] + list(tconf.get("fallbacks", []))
        for name in engine_names:
            if name in ENGINE_REGISTRY:
                try:
                    self._engines[name] = ENGINE_REGISTRY[name](self.config, self.glossary)
                except Exception:
                    continue

    def engine_order(self) -> list[str]:
        """返回当前引擎顺序（用于界面展示）"""
        return list(self._engines.keys())

    def _available(self, name: str) -> bool:
        """检查引擎是否在冷却期之外"""
        with self._lock:
            return time.monotonic() > self._cooldown_until.get(name, 0.0)

    def _mark_cooldown(self, name: str, seconds: float = 30.0) -> None:
        """引擎连续失败后冷却一段时间"""
        with self._lock:
            self._cooldown_until[name] = time.monotonic() + seconds

    def _translate_one(self, engine: TranslationEngine, batch: list[str]) -> list[str]:
        """使用指定引擎翻译一批（带重试）"""
        last_error: TranslateError | None = None
        for attempt in range(self.max_retry + 1):
            self._limiter.acquire()
            try:
                return engine.translate_batch(batch, self.target_lang)
            except TranslateError as exc:
                last_error = exc
                if attempt < self.max_retry:
                    time.sleep(1 + attempt)
        raise last_error or TranslateError("未知翻译错误")

    def translate_batch(
        self,
        texts: list[str],
        on_progress=None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> list[str]:
        """翻译文本列表，自动降级

        参数:
            on_progress(batch_done, total): 可选进度回调（线程安全）。
            on_error(engine_name, message): 可选失败回调（线程安全）。
                每当某引擎翻译失败时被调用，可用于界面提示"翻译失败原因"。
        """
        results: list[str | None] = [None] * len(texts)
        todo_indices: list[int] = []
        for i, text in enumerate(texts):
            text = text.strip()
            if not text:
                results[i] = ""
                continue
            cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
                continue
            todo_indices.append(i)

        total = len(todo_indices)
        if total == 0:
            return [r or "" for r in results]

        batches = [todo_indices[i : i + self.batch_size] for i in range(0, total, self.batch_size)]

        def _work(batch: list[int]) -> None:
            """处理一个批次：尝试所有可用引擎"""
            texts_batch = [texts[i] for i in batch]
            engine_names = self.engine_order()
            failures: list[str] = []
            for name in engine_names:
                engine = self._engines.get(name)
                if engine is None or not self._available(name):
                    continue
                try:
                    translated = self._translate_one(engine, texts_batch)
                    if len(translated) != len(batch):
                        raise TranslateError("返回条数与请求不符")
                    for idx, res in zip(batch, translated):
                        results[idx] = res
                        if res and res != texts[idx]:
                            with self._cache_lock:
                                self._cache[texts[idx]] = res
                    return  # 成功
                except (TranslateError, Exception) as exc:
                    # 记录并继续下一个引擎
                    failures.append(f"{name}: {exc}")
                    if name != engine_names[-1]:
                        self._mark_cooldown(name, 10.0)
                    continue
            # 所有引擎都失败：原样返回，并上报失败原因
            if on_error is not None:
                on_error("全部引擎失败", "；".join(failures) or "无可用引擎")
            for idx in batch:
                results[idx] = texts[idx]

        done_count = 0
        done_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(_work, b) for b in batches]
            for _fut in as_completed(futures):
                _fut.result()
                with done_lock:
                    done_count += 1
                if on_progress:
                    on_progress(done_count, len(batches))

        return [r or "" for r in results]

    def clear_cache(self) -> None:
        """清空翻译缓存"""
        with self._cache_lock:
            self._cache.clear()
